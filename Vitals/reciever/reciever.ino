#include "esp_wifi.h"
#include "esp_wifi_types.h"
#include <WiFi.h>
#include <WiFiUdp.h>

#define WIFI_CHANNEL 3
WiFiUDP udp;

void csi_rx_cb(void *ctx, wifi_csi_info_t *data) {
    if (!data || !data->buf || data->len < 18) return; 

    int8_t *csi_matrix = (int8_t *)data->buf;
    
    // Pull the pure, unmodified signal magnitude out of the 8th subcarrier pair
    float real = csi_matrix[16];
    float imag = csi_matrix[17];
    float raw_amplitude = sqrt(real * real + imag * imag);

    // Print raw tag directly to your PC port
    Serial.print("RAW_VAL:"); 
    Serial.println(raw_amplitude, 2);
}

void setup() {
    Serial.begin(115200);
    while (!Serial);

    WiFi.mode(WIFI_STA);
    WiFi.begin("CSI_Vitals_Net", "12345678");

    while (WiFi.status() != WL_CONNECTED) {
        delay(200);
    }

    wifi_csi_config_t csi_config = {0};
    csi_config.lltf_en = true;
    csi_config.htltf_en = true;
    csi_config.manu_scale = 1; 

    esp_wifi_set_csi(&csi_config);
    esp_wifi_set_csi_rx_cb(&csi_rx_cb, NULL);
    esp_wifi_set_csi(true); 

    udp.begin(8888);
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        WiFi.disconnect();
        WiFi.begin("CSI_Vitals_Net", "12345678");
        delay(1000);
        return;
    }

    udp.beginPacket(IPAddress(192, 168, 4, 1), 9999);
    udp.write(0xA5);
    udp.endPacket();
    delay(25); // Blasts at a rock-solid 40Hz sample rate
}
