#include <esp_now.h>
#include <WiFi.h>

// ==========================================
// CHANGE THIS FOR EACH BOARD (1, 2, 3, or 4)
// ==========================================
#define MY_NODE_ID 4

// High-speed structure to pack and log matrix records in RAM
typedef struct struct_message {
  uint8_t senderId;
  int16_t rssiMatrix[5][5]; 
} struct_message;

struct_message txData;
struct_message rxData;

// Global 2D tables tracking link metrics across nodes [From][To]
int16_t liveMatrix[5][5];
float baselineMatrix[5][5];
int sampleCounts[5][5];

unsigned long phaseStartTime;
const unsigned long CALIBRATION_DURATION = 30000; // 30 seconds
bool isCalibrated = false;

unsigned long lastSerialPrint = 0;

// Broadcast MAC Address to allow seamless mesh communication
uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// Inbound packet interceptor managing matrix tracking sync across nodes
void OnDataRecv(const esp_now_recv_info_t * recv_info, const uint8_t *incomingData, int len) {
  memcpy(&rxData, incomingData, sizeof(rxData));
  uint8_t remoteNode = rxData.senderId;
  int16_t immediateRssi = recv_info->rx_ctrl->rssi;

  if (remoteNode >= 1 && remoteNode <= 4) {
    // Record direct peer-to-peer connection signal strength
    liveMatrix[remoteNode][MY_NODE_ID] = immediateRssi;
    liveMatrix[MY_NODE_ID][remoteNode] = immediateRssi; 
    
    // Crucial: Sync the paths that don't involve the server!
    for(int i = 1; i <= 4; i++) {
      for(int j = 1; j <= 4; j++) {
        if(rxData.rssiMatrix[i][j] < 0 && rxData.rssiMatrix[i][j] > -100) {
          // If we receive data about a path, update our local records
          if (i != MY_NODE_ID && j != MY_NODE_ID) {
            liveMatrix[i][j] = rxData.rssiMatrix[i][j];
          }
        }
      }
    }

    // Accumulate signal baseline variables if within the calibration window
    if (!isCalibrated) {
      sampleCounts[remoteNode][MY_NODE_ID]++;
      if (baselineMatrix[remoteNode][MY_NODE_ID] == -100.0) {
        baselineMatrix[remoteNode][MY_NODE_ID] = immediateRssi;
        baselineMatrix[MY_NODE_ID][remoteNode] = immediateRssi;
      } else {
        // Smooth out noise using a running average
        baselineMatrix[remoteNode][MY_NODE_ID] = (baselineMatrix[remoteNode][MY_NODE_ID] * 0.95) + (immediateRssi * 0.05);
        baselineMatrix[MY_NODE_ID][remoteNode] = baselineMatrix[remoteNode][MY_NODE_ID];
      }
      
      // Also build baseline averages for non-server node paths via shared mesh updates
      for(int i = 1; i <= 4; i++) {
        for(int j = 1; j <= 4; j++) {
          if (i != MY_NODE_ID && j != MY_NODE_ID && rxData.rssiMatrix[i][j] < 0 && rxData.rssiMatrix[i][j] > -100) {
            if(baselineMatrix[i][j] == -100.0) {
              baselineMatrix[i][j] = rxData.rssiMatrix[i][j];
            } else {
              baselineMatrix[i][j] = (baselineMatrix[i][j] * 0.98) + (rxData.rssiMatrix[i][j] * 0.02);
            }
          }
        }
      }
    }
  }
}

void setup() {
  // Blazing fast baud rate to handle rapid console streaming without lagging the processor
  Serial.begin(921600); 
  
  // Initialize tracking tables to clear old garbage numbers
  for(int i = 0; i < 5; i++) {
    for(int j = 0; j < 5; j++) {
      liveMatrix[i][j] = -100;
      baselineMatrix[i][j] = -100.0;
      sampleCounts[i][j] = 0;
    }
  }

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW Init Failed");
    return;
  }
  
  esp_now_register_recv_cb(esp_now_recv_cb_t(OnDataRecv));

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, broadcastAddress, 6);
  peerInfo.channel = 1; 
  peerInfo.encrypt = false;
  esp_now_add_peer(&peerInfo);

  txData.senderId = MY_NODE_ID;
  phaseStartTime = millis();

  if (MY_NODE_ID == 1) {
    Serial.println("\n====================================================");
    Serial.println("SYSTEM ONLINE: Starting 30-Second Room Calibration...");
    Serial.println("====================================================\n");
  }
}

void loop() {
  unsigned long currentMillis = millis();

  // Shift from calibration to active radar checking tracking frames
  if (!isCalibrated && (currentMillis - phaseStartTime >= CALIBRATION_DURATION)) {
    isCalibrated = true;
    if (MY_NODE_ID == 1) {
      Serial.println("\n✅ CALIBRATION LOCKED! Starting Live Radar Streaming...\n");
    }
  }

  // Node 1 processes and prints the radar proximity alerts to your laptop screen
  if (MY_NODE_ID == 1 && isCalibrated && (currentMillis - lastSerialPrint >= 100)) {
    lastSerialPrint = currentMillis;

    float nodeDrops[5] = {0, 0, 0, 0, 0};
    
    Serial.print("PATHS -> ");
    // Calculate deviations across ALL 6 permutations
    int pathIndex = 1;
    for (int i = 1; i <= 4; i++) {
      for (int j = i + 1; j <= 4; j++) {
        int16_t live = liveMatrix[i][j];
        float base = baselineMatrix[i][j];
        float dev = (live > -100 && base > -100) ? (base - live) : 0;
        if(dev < 0) dev = 0; // Drop negative anomalies

        // Print individual tracking path statuses
        Serial.printf("[%d-%d: Live %ddB / Dev %.1f]  ", i, j, live, dev);
        
        // Accumulate signal loss to attribute proximity to neighboring nodes
        nodeDrops[i] += dev;
        nodeDrops[j] += dev;
      }
    }
    Serial.println();

    // Determine which node is witnessing the most intense structural attenuation
    int nearestNode = 0;
    float maxDrop = 0;
    for(int n = 1; n <= 4; n++) {
      if(nodeDrops[n] > maxDrop) {
        maxDrop = nodeDrops[n];
        nearestNode = n;
      }
    }

    // Print proximity estimation context if changes exceed general room thresholds
    if (maxDrop > 12.0) { 
      Serial.printf("🚨 PROXIMITY ALERT: Human detected near [NODE %d] (Total Path Drop: %.1f dB)\n\n", nearestNode, maxDrop);
    } else {
      Serial.println("Room Status: Clear / No Target Movement\n");
    }
  }

  // Interleave transmissions using 25ms round-robin slots to stop packets colliding
  if ((currentMillis % 100) / 25 == (MY_NODE_ID - 1)) {
    for(int i = 1; i <= 4; i++) {
      for(int j = 1; j <= 4; j++) {
        txData.rssiMatrix[i][j] = liveMatrix[i][j];
      }
    }
    esp_now_send(broadcastAddress, (uint8_t *) &txData, sizeof(txData));
    delay(2); // Small stability delay
  }
}
