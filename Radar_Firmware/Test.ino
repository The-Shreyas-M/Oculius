#include <esp_now.h>
#include <WiFi.h>

// Set to true for Node 1 (Laptop/COM3), false for Node 2 (Wall Adapter)
#define IS_NODE_1 true 

// Define a simple handshake/ping packet
typedef struct struct_message {
  uint32_t count;
} struct_message;

struct_message txData;

// Broadcast MAC address targets all ESP-NOW devices on the same channel
uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// Timing and Calibration variables
unsigned long phaseStartTime;
const unsigned long CALIBRATION_DURATION = 30000; // 30 seconds (in milliseconds)
bool isCalibrated = false;

// Signal filtering variables
float rssiBaseline = 0;
int sampleCount = 0;
uint32_t packetCounter = 0;

// Callback function executed when an ESP-NOW packet is received
void OnDataRecv(const esp_now_recv_info_t * recv_info, const uint8_t *incomingData, int len) {
  // Extract raw hardware signal strength (RSSI)
  int16_t currentRssi = recv_info->rx_ctrl->rssi; 
  
  if (!isCalibrated) {
    // 30-Second Calibration: Calculate running exponential moving average
    sampleCount++;
    if (rssiBaseline == 0) {
      rssiBaseline = currentRssi;
    } else {
      rssiBaseline = (rssiBaseline * 0.95) + (currentRssi * 0.05);
    }
  } else {
    // Post-Calibration Radar Mode (Only Node 1 handles serial printing tasks)
    if (IS_NODE_1) {
      float deviation = rssiBaseline - currentRssi;
      Serial.print("CALIBRATED_BASE:");
      Serial.print(rssiBaseline);
      Serial.print(",CURRENT_RSSI:");
      Serial.print(currentRssi);
      Serial.print(",DEVIATION:");
      Serial.println(deviation);
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  // Set Wi-Fi to Station mode and disconnect from any home routers
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  // Initialize ESP-NOW protocol
  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW");
    return;
  }
  
  // Register the reception callback function
  esp_now_register_recv_cb(esp_now_recv_cb_t(OnDataRecv));
  
  // Register the Broadcast Peer profile
  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, broadcastAddress, 6);
  peerInfo.channel = 1; // Both nodes must match channel 1
  peerInfo.encrypt = false;
  
  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("Failed to add broadcast peer");
    return;
  }

  phaseStartTime = millis();
  
  if (IS_NODE_1) {
    Serial.println("--- SYSTEM INITIALIZED (NODE 1) ---");
    Serial.println("Starting 30-second calibration. Keep the room completely clear...");
  }
}

void loop() {
  unsigned long currentMillis = millis();

  // Handle phase switching after 30 seconds pass
  if (!isCalibrated && (currentMillis - phaseStartTime >= CALIBRATION_DURATION)) {
    isCalibrated = true;
    if (IS_NODE_1) {
      Serial.println("--- CALIBRATION COMPLETE ---");
      Serial.print("Locked Baseline RSSI: ");
      Serial.print(rssiBaseline);
      Serial.print(" dBm over ");
      Serial.print(sampleCount);
      Serial.println(" data packets.");
      Serial.println("Entering active radar tracking mode...");
    }
  }

  // Round-robin transmission logic to prevent airwave collisions
  // Node 1 transmits on even 50ms intervals, Node 2 transmits on odd 50ms intervals
  bool myTurn = (IS_NODE_1) ? ((currentMillis % 100) < 50) : ((currentMillis % 100) >= 50);

  if (myTurn) {
    txData.count = packetCounter++;
    esp_now_send(broadcastAddress, (uint8_t *) &txData, sizeof(txData));
    delay(15); // Short yield to let hardware transmit smoothly
  }
}
