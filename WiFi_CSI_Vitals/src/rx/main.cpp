// Oculius RX (ESP32-S3): captures CSI from the TX board and reads a MAX30102 (ground-truth
// pulse). Everything is streamed to the PC as binary frames over the USB-UART at 921600 baud.
//   frame: A5 5A | type | len(u16 LE) | payload | xor(type,len,payload)
//   type 1 CSI : ts_ms u32 | rssi i8 | channel u8 | sig_mode u8 | raw int8 I/Q pairs...
//   type 2 PPG : ts_ms u32 | red u32 | ir u32
#define I2C_BUFFER_LENGTH 128
#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "MAX30105.h"

#define WIFI_CHANNEL 6
#define SDA_PIN 8
#define SCL_PIN 9
static const uint8_t TX_MAC[6] = {0x00, 0x70, 0x07, 0x17, 0x11, 0x74};

#define MAX_CSI 400
struct CsiItem { uint32_t ts; int8_t rssi; uint8_t ch; uint8_t sig; uint16_t len; int8_t buf[MAX_CSI]; };
#define RING 24
static CsiItem ring[RING];
static volatile uint32_t head = 0, tail = 0, dropped = 0;

static void IRAM_ATTR csiCb(void *ctx, wifi_csi_info_t *info) {
  if (!info || !info->buf || memcmp(info->mac, TX_MAC, 6) != 0) return;
  uint32_t nh = (head + 1) % RING;
  if (nh == tail) { dropped++; return; }
  CsiItem &it = ring[head];
  it.ts = millis();
  it.rssi = info->rx_ctrl.rssi;
  it.ch = info->rx_ctrl.channel;
  it.sig = info->rx_ctrl.sig_mode;
  it.len = info->len > MAX_CSI ? MAX_CSI : info->len;
  memcpy(it.buf, info->buf, it.len);
  head = nh;
}

static void sendFrame(uint8_t type, const uint8_t *hdr, size_t hl, const uint8_t *body, size_t bl) {
  uint16_t len = hl + bl;
  uint8_t pre[5] = {0xA5, 0x5A, type, (uint8_t)(len & 0xFF), (uint8_t)(len >> 8)};
  uint8_t x = type ^ pre[3] ^ pre[4];
  for (size_t i = 0; i < hl; i++) x ^= hdr[i];
  for (size_t i = 0; i < bl; i++) x ^= body[i];
  Serial.write(pre, 5);
  Serial.write(hdr, hl);
  if (bl) Serial.write(body, bl);
  Serial.write(&x, 1);
}

MAX30105 ppg;
static bool ppgOk = false;

void setup() {
  Serial.begin(921600);
  Serial.setTxBufferSize(8192);
  delay(500);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);
  Serial.print("\nI2C scan (SDA=8 SCL=9):");
  int found = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) { Serial.printf(" 0x%02X", a); found++; }
  }
  Serial.printf(" -> %d device(s)\n", found);
  for (int i = 0; i < 3 && !ppgOk; i++) { ppgOk = ppg.begin(Wire, I2C_SPEED_FAST); if (!ppgOk) delay(100); }
  if (ppgOk) {
    // 200 Hz internal, avg 4 -> 50 samples/s, red+IR, 411us pulse, 16384 nA range
    ppg.setup(0x6F, 4, 2, 200, 411, 16384);
  }

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_promiscuous(false);
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N);
  esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT20);
  esp_wifi_set_ps(WIFI_PS_NONE);
  esp_now_init();  // ESP-NOW rx path makes the driver hand frames to the CSI callback

  wifi_csi_config_t cfg = {};
  cfg.lltf_en = true;
  cfg.htltf_en = true;
  cfg.stbc_htltf2_en = true;
  cfg.ltf_merge_en = true;
  cfg.channel_filter_en = false;  // keep per-subcarrier amplitude un-smoothed
  cfg.manu_scale = false;
  esp_wifi_set_csi_config(&cfg);
  esp_wifi_set_csi_rx_cb(csiCb, nullptr);
  esp_wifi_set_csi(true);

  Serial.printf("\nOCULIUS RX ready ppg=%d mac=%s\n", ppgOk, WiFi.macAddress().c_str());
}

void loop() {
  while (tail != head) {
    CsiItem &it = ring[tail];
    uint8_t h[7];
    memcpy(h, &it.ts, 4);
    h[4] = it.rssi; h[5] = it.ch; h[6] = it.sig;
    sendFrame(1, h, 7, (uint8_t *)it.buf, it.len);
    tail = (tail + 1) % RING;
  }
  if (ppgOk) {
    ppg.check();
    while (ppg.available()) {
      uint8_t h[12];
      uint32_t ts = millis(), r = ppg.getFIFORed(), ir = ppg.getFIFOIR();
      memcpy(h, &ts, 4); memcpy(h + 4, &r, 4); memcpy(h + 8, &ir, 4);
      sendFrame(2, h, 12, nullptr, 0);
      ppg.nextSample();
    }
  }
}
