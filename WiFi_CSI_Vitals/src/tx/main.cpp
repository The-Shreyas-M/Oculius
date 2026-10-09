// Oculius TX (classic ESP32): sends 100 Hz ESP-NOW broadcast frames at an HT (802.11n)
// rate so the receiver gets HT-LTF CSI on every frame. No router needed.
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#define WIFI_CHANNEL 6
#define TX_RATE_HZ   100

static const uint8_t BCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static uint32_t seq = 0;

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_promiscuous(false);
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N);
  esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT20);
  esp_wifi_set_ps(WIFI_PS_NONE);

  if (esp_now_init() != ESP_OK) {
    Serial.println("esp_now_init failed");
    while (1) delay(1000);
  }
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, BCAST, 6);
  peer.channel = WIFI_CHANNEL;
  peer.ifidx = WIFI_IF_STA;
  peer.encrypt = false;
  esp_now_add_peer(&peer);
  // HT MCS0 (long GI) -> frames carry an HT-LTF, giving the RX full CSI
  esp_wifi_config_espnow_rate(WIFI_IF_STA, WIFI_PHY_RATE_MCS0_LGI);

  Serial.printf("TX ready. MAC %s ch %d @ %d Hz\n", WiFi.macAddress().c_str(), WIFI_CHANNEL, TX_RATE_HZ);
}

void loop() {
  static uint32_t next = 0;
  uint32_t now = micros();
  if ((int32_t)(now - next) < 0) return;
  next = (next == 0 ? now : next) + 1000000UL / TX_RATE_HZ;
  uint8_t payload[8];
  memcpy(payload, &seq, 4);
  memcpy(payload + 4, "OCUL", 4);
  seq++;
  esp_now_send(BCAST, payload, sizeof(payload));
}
