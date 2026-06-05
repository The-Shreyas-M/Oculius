#include <WiFi.h>
#include <WiFiAP.h>

#define WIFI_CHANNEL 3

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("\n--- Launching Active AP Transmitter ---");
    WiFi.mode(WIFI_AP);
    
    // Explicit network layer framework instantiation forcing Channel 3
    bool success = WiFi.softAP("CSI_Vitals_Net", "12345678", WIFI_CHANNEL, 0, 4);
    
    if(success) {
        Serial.println(">>> SUCCESS: Transmitter is Live! <<<");
        Serial.print("IP Address: "); Serial.println(WiFi.softAPIP());
    } else {
        Serial.println("!!! AP Generation Failed !!!");
    }
}

void loop() {
    // Keeps the underlying beacon framework active
    delay(1000);
}
