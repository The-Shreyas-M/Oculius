// MAX30102 high-accuracy HR + SpO2 for ESP32-S3
// Maxim's official algorithm (FreqS=25) with hardware FIFO at 25 sps
// and strictly contiguous, evenly-paced 100-sample windows.
#define I2C_BUFFER_LENGTH 128
#include <Arduino.h>
#include <Wire.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"

MAX30105 particleSensor;

#define SDA_PIN 8
#define SCL_PIN 9

#define IR_FINGER_THRESHOLD 50000
#define BUFFER_LENGTH 100

int32_t spo2, heartRate;
int8_t validSPO2, validHR;
uint32_t irBuffer[BUFFER_LENGTH];
uint32_t redBuffer[BUFFER_LENGTH];

bool fingerDetected = false;

// Discard any samples queued in the library buffer (backlog).
void flushFifo() {
  particleSensor.check();
  while (particleSensor.available())
    particleSensor.nextSample();
}

// Fill the FIFO with new data, discarding stale samples.
void waitForNew() {
  do {
    particleSensor.check();
  } while (particleSensor.available() == 0);
}

// Collect BUFFER_LENGTH contiguous samples, one per FIFO arrival.
// Hardware config (SR=100, SMP_AVE=4) makes the FIFO deliver 25 sps,
// so 100 samples = exactly 4.0 s — matching the algorithm's FreqS=25.
// Channels are swapped: many MAX30102 breakouts report Red/IR swapped.
void collectWindow(unsigned long *elapsedMs) {
  unsigned long t0 = millis();
  int count = 0;
  while (count < BUFFER_LENGTH) {
    waitForNew();
    redBuffer[count] = particleSensor.getFIFOIR();   // physical IR -> Red slot
    irBuffer[count]  = particleSensor.getFIFORed();   // physical Red -> IR slot
    particleSensor.nextSample();
    count++;
  }
  *elapsedMs = millis() - t0;
}

// Insertion-sort median of last N values to damp output jitter.
#define DAMP 5
int32_t hrDamp[DAMP], spDamp[DAMP];
int dampIdx = 0;
int32_t median(int32_t *v, int n) {
  int32_t t[DAMP];
  for (int i = 0; i < n; i++) t[i] = v[i];
  for (int i = 0; i < n - 1; i++)
    for (int j = i + 1; j < n; j++)
      if (t[j] < t[i]) { int32_t x = t[i]; t[i] = t[j]; t[j] = x; }
  return t[n / 2];
}

void setup() {
  Serial.begin(115200);
  delay(2000);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);
  Wire.setBufferSize(128);

  // warmup: first I2C read after power-on can return garbage
  Wire.beginTransmission(0x57);
  Wire.write(0x00);
  Wire.endTransmission();
  Wire.requestFrom((uint8_t)0x57, (uint8_t)1);
  if (Wire.available()) Wire.read();
  delay(50);

  Serial.println("Initializing MAX30102...");
  bool ok = false;
  for (int i = 0; i < 5 && !ok; i++) {
    ok = particleSensor.begin(Wire, I2C_SPEED_FAST);
    if (!ok) delay(100);
  }
  if (!ok) {
    Serial.println("Sensor init FAILED. Check wiring / pull-ups.");
    while (1);
  }
  Serial.println("Sensor OK.");

  // SR=100, SMP_AVE=4  ->  FIFO delivers 100/4 = 25 samples/s (matches FreqS)
  // Red+IR | 411us PW | 4096 ADC range
  particleSensor.setup(60, 4, 2, 100, 411, 4096);
  particleSensor.setPulseAmplitudeRed(0x1F);
  particleSensor.setPulseAmplitudeIR(0x1F);

  flushFifo();
  Serial.println("Ready. Place finger flat on sensor and hold still.");
}

void loop() {
  flushFifo();
  unsigned long elapsed = 0;
  collectWindow(&elapsed);

  // Finger gate: decide from THIS window's IR DC level (no separate FIFO reads).
  long dc = 0;
  for (int i = 0; i < BUFFER_LENGTH; i++) dc += irBuffer[i];
  dc /= BUFFER_LENGTH;

  if (fingerDetected) {
    if (dc < IR_FINGER_THRESHOLD) fingerDetected = false;   // finger lifted
  } else {
    if (dc >= IR_FINGER_THRESHOLD + 15000) fingerDetected = true;  // finger placed
  }

  if (!fingerDetected) {
    dampIdx = 0;
    Serial.println("No finger detected. Place finger on sensor.");
    return;
  }

  maxim_heart_rate_and_oxygen_saturation(irBuffer, BUFFER_LENGTH, redBuffer,
                                         &spo2, &validSPO2, &heartRate, &validHR);

  if (validSPO2 && validHR && dc > 30000 && dc < 230000 && heartRate >= 40 && heartRate <= 200) {
    hrDamp[dampIdx % DAMP] = heartRate;
    spDamp[dampIdx % DAMP] = spo2;
    dampIdx++;
    if (dampIdx >= DAMP) {
      int32_t hr = median(hrDamp, DAMP);
      int32_t sp = median(spDamp, DAMP);
      Serial.print("HR: ");
      Serial.print(hr);
      Serial.print(" bpm | SpO2: ");
      Serial.print(sp);
      Serial.println(" %");
    }
  } else {
    dampIdx = 0;
    Serial.println("Hold finger steady on sensor...");
  }
}