#include <esp_now.h>
#include <WiFi.h>

// ==========================================
// CHANGE THIS FOR EACH BOARD (1, 2, 3, or 4)
// ==========================================
#define MY_NODE_ID 1

// The explicit 2D structure to pack and broadcast the entire room's data over the air
typedef struct struct_message {
  uint8_t senderId;
  int16_t rssiMatrix[5][5]; // Packs the whole 2D grid into the wireless packet
} struct_message;

struct_message txData;
struct_message rxData;

int16_t liveMatrix[5][5];
int16_t baselineMatrix[5][5];
bool isCalibrated = false;
unsigned long phaseStartTime;
unsigned long lastSerialPrint = 0;

uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

void OnDataRecv(const esp_now_recv_info_t * recv_info, const uint8_t *incomingData, int len) {
  memcpy(&rxData, incomingData, sizeof(rxData));
  uint8_t remoteNode = rxData.senderId;
  int16_t immediateRssi = recv_info->rx_ctrl->rssi;

  if (remoteNode >= 1 && remoteNode <= 4) {
    // Record direct connection signal strength to this remote node
    liveMatrix[remoteNode][MY_NODE_ID] = immediateRssi;
    liveMatrix[MY_NODE_ID][remoteNode] = immediateRssi; 
    
    // CRUCIAL OVER-THE-AIR SYNC: Pull the cross-paths from the wireless packet
    for(int i = 1; i <= 4; i++) {
      for(int j = 1; j <= 4; j++) {
        if(rxData.rssiMatrix[i][j] < 0 && rxData.rssiMatrix[i][j] > -100) {
          // If we don't have a direct connection to these nodes, trust the mesh data
          if (i != MY_NODE_ID && j != MY_NODE_ID) {
            liveMatrix[i][j] = rxData.rssiMatrix[i][j];
          }
        }
      }
    }

    if (!isCalibrated) {
      if (baselineMatrix[remoteNode][MY_NODE_ID] == -100) {
        baselineMatrix[remoteNode][MY_NODE_ID] = immediateRssi;
        baselineMatrix[MY_NODE_ID][remoteNode] = immediateRssi;
      } else {
        baselineMatrix[remoteNode][MY_NODE_ID] = (baselineMatrix[remoteNode][MY_NODE_ID] * 0.95) + (immediateRssi * 0.05);
        baselineMatrix[MY_NODE_ID][remoteNode] = baselineMatrix[remoteNode][MY_NODE_ID];
      }
    }
  }
}

void setup() {
  Serial.begin(921600); 
  
  for(int i = 0; i < 5; i++) {
    for(int j = 0; j < 5; j++) {
      liveMatrix[i][j] = -100;
      baselineMatrix[i][j] = -100;
    }
  }

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) return;
  esp_now_register_recv_cb(OnDataRecv);

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, broadcastAddress, 6);
  peerInfo.channel = 1; 
  peerInfo.encrypt = false;
  esp_now_add_peer(&peerInfo);

  txData.senderId = MY_NODE_ID;
  phaseStartTime = millis();
}

void loop() {
  unsigned long currentMillis = millis();

  // Handle baseline collection timing
  if (!isCalibrated && (currentMillis - phaseStartTime >= 30000)) {
    isCalibrated = true;
    
    // Automatically copy initial live values to baseline for paths Node 1 can't see directly
    if (MY_NODE_ID == 1) {
      for(int i = 1; i <= 4; i++) {
        for(int j = 1; j <= 4; j++) {
          if (baselineMatrix[i][j] == -100 && liveMatrix[i][j] > -100) {
            baselineMatrix[i][j] = liveMatrix[i][j];
          }
        }
      }
    }
  }

  // Node 1 streams the correctly ordered 6 paths straight to your laptop
  if (MY_NODE_ID == 1 && (currentMillis - lastSerialPrint >= 50)) {
    lastSerialPrint = currentMillis;
    
    Serial.print("RADAR:");
    // Print explicit Live Vector Order: 1-2, 1-3, 1-4, 2-3, 2-4, 3-4
    Serial.printf("%d,%d,%d,%d,%d,%d|", 
      liveMatrix[1][2], liveMatrix[1][3], liveMatrix[1][4], 
      liveMatrix[2][3], liveMatrix[2][4], liveMatrix[3][4]);
      
    // Print explicit Baseline Vector Order: 1-2, 1-3, 1-4, 2-3, 2-4, 3-4
    Serial.printf("%d,%d,%d,%d,%d,%d\n", 
      baselineMatrix[1][2], baselineMatrix[1][3], baselineMatrix[1][4], 
      baselineMatrix[2][3], baselineMatrix[2][4], baselineMatrix[3][4]);
  }

  // Round-Robin micro timing slots to guarantee clean airwaves
  if ((currentMillis % 100) / 25 == (MY_NODE_ID - 1)) {
    for(int i = 1; i <= 4; i++) {
      for(int j = 1; j <= 4; j++) {
        txData.rssiMatrix[i][j] = liveMatrix[i][j];
      }
    }
    esp_now_send(broadcastAddress, (uint8_t *) &txData, sizeof(txData));
    delay(2); 
  }
}
