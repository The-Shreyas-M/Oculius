# Oculius — Wi-Fi presence, breathing & heart-rate with two ESP32s

```
 classic ESP32 (TX)  ~~~ 2.4 GHz, 100 frames/s ~~~>  ESP32-S3 (RX) ──USB──> PC (Python)
 wall adapter                                          + MAX30102 (finger, training only)
```

* **TX (classic ESP32, COM4)** broadcasts 100 ESP-NOW frames/s on channel 6 at an 802.11n rate. No router needed.
* **RX (ESP32-S3 N8R8, COM3)** records the CSI (channel state info) of every frame and streams it to the PC. It also reads the MAX30102, which is your **ground truth** for training.
* **PC** (`host/`) computes presence, breathing rate and heart rate. An LSTM learns *your* heart rate from CSI using the MAX30102 as the label.

Both boards are already flashed. Reflash with `pio run -e tx -t upload` (TX) and `pio run -e rx -t upload` (RX).

## What to expect (be honest with yourself)

| Thing | Realistic with 2 ESP32s |
|---|---|
| Presence | Good, once calibrated (`calibrate` below). |
| Breathing rate | Good when you sit still, ±1–2 br/min. |
| Heart rate | **Experimental.** The heartbeat moves the chest by ~0.1–0.5 mm, close to the noise floor of one ESP32 link. Without training, the spectral peak is often noise (you'll see `snr` of about 4–6; real beats show `snr` > 15). The LSTM trained on your own recordings gets it much better, but only in the same setup you trained in. |

PulseFi / RuView-style accuracy comes from tuned hardware, many subcarriers and per-room training. With 2 ESPs the best you can do is a clean setup plus training in that exact setup.

## MAX30102 wiring (to the ESP32-S3)

| MAX30102 pin | ESP32-S3 pin |
|---|---|
| VIN / VCC | **3V3** (not 5V) |
| GND | GND |
| SDA | **GPIO 8** |
| SCL | **GPIO 9** |
| INT | not connected |

Use short wires (under 20 cm). Only the S3 gets the sensor. The classic ESP32 never needs one. You only wear it while **recording training data**. In normal use you don't need it.

## Placement (this matters more than any code)

1. **Distance:** put TX and RX **1.5–3 m apart**, facing each other across the space where you sit. Closer than 1 m saturates the receiver (RSSI better than -30). Farther than 4 m is weak. Aim for **RSSI between -35 and -55** (shown in `live`).
2. **Height:** put both boards **at your chest/sternum height when seated, about 0.9–1.1 m off the floor**. Use a shelf, a stack of books or a tripod. Don't leave them on the floor.
3. **Where you sit:** do **NOT sit between the boards**. Your torso blocks 2.4 GHz and drops the signal by 15–25 dB (RSSI went -40 to -64 in testing). Put both boards on the **same side of you**, e.g. on the desk or a shelf in front of you, about 1.5–2 m apart, so the straight line between them passes **about 0.4–0.8 m in front of your chest**, parallel to your torso. Your breathing then changes the reflected path without blocking the direct one. Check that RSSI stays around -40 to -55 with you sitting there.
4. **Orientation:** stand both boards **upright, the same way up**, with the antenna end (the end with the small PCB trace and no USB plug) **pointing up**. Matching polarization gives the strongest, cleanest signal. Keep the boards **at least 30 cm away from the laptop, monitors, routers and metal**. Don't put the RX on top of the laptop.
5. **The TX "behind my back" idea:** a TX behind you with the RX in front puts your body right on the line, which is the blocked case from step 3. Prefer both boards in front of you or to one side.
6. **Chair:** the **metal-rod chair is a bad reflector** right next to the link. Use a wooden/plastic chair, or at least keep the metal away from the line between the boards. A stool or a sofa also works.
7. **Ceiling fan: turn it OFF** while measuring or recording. The blades and airflow add strong motion at frequencies right next to your breathing and pulse bands. If you must run it, make sure it's well away from the link, and expect worse results.
8. **Stay still:** sit upright, relaxed, arms resting in your lap or on the desk, **don't type, talk, or shift**. Any body motion is a million times bigger than a heartbeat. For the cleanest data, rest your forearms and breathe normally for a minute before starting.
9. **Everything fixed:** don't move the boards, the chair or large objects between runs. Both the baseline and the trained model are tied to this exact layout. If you move something, recalibrate and retrain.
10. **USB cable:** the S3 stays tethered to the PC, so use a short USB extension or a cable of about 1.5–2 m to reach the shelf. Put the PC off the line between the boards if you can.

## Using it

Run these from this folder. Close any serial monitor first, because only one program can hold COM3.

```powershell
# 1. Empty-room baseline (leave the room, fan as it will be, ~60 s). Do this once per layout.
python host/oculius.py calibrate

# 2. Live readout, once per second (sit in your spot)
python host/oculius.py live
```

Reading the output: `PRESENT/empty`, `rate` (CSI frames/s, should be 85–100), `rssi` (target -35 to -55), `BR` in breaths per minute, `HR` in bpm, `snr` (higher is more trustworthy). `ref HR` appears when the MAX30102 has your finger on it.

### Training the heart-rate LSTM

1. Wire the MAX30102 as above. Sit in your spot (fan off). Rest your **left index finger lightly** on the sensor, without pressing hard. Keep that hand still and relaxed.
2. Record about 20 minutes of calm sitting, and make a few sessions on different days or times:
   ```powershell
   python host/oculius.py record 20
   ```
   Make sure the printout says `ir` above 20000 (finger detected). Windows without a clean finger signal are skipped automatically.
3. Train. It reads every `data/rec_*.npz`, takes the MAX30102 HR as the label, and holds out the last 20% of the data to validate:
   ```powershell
   python host/train.py
   ```
   It prints the validation error against two baselines: the plain spectral peak, and "just guess your average HR". If the model can't beat guessing your average, it refuses to save, which means CSI isn't carrying your pulse yet. Fix placement and record more.
4. Run `python host/oculius.py live` again. With `models/hr_lstm.pt` present it uses the LSTM (`lstm NN%` is its confidence), and prints the reference HR next to it while your finger is on the sensor so you can see the error yourself.

A resting heart rate varies only by a few bpm, so a model trained only on resting data may just learn "about your usual HR". To make it learn real signal, include some recordings after light exercise (when your HR is 90–110). That gives it a wider range to learn from.

## Troubleshooting

* **`rate` is 0 or the output says "waiting for CSI":** check that TX is powered, and that nothing else uses channel 6 heavily. Change `WIFI_CHANNEL` in both `src/tx/main.cpp` and `src/rx/main.cpp` and reflash.
* **`ppg=0` / no `ref HR`:** the MAX30102 isn't detected. Check SDA=GPIO8, SCL=GPIO9, 3V3 and GND.
* **`PRESENT` when the room is empty:** run `calibrate` again with the fan in its normal state, or turn the fan off.
* **BR looks stuck near 6–8:** that's the low edge of the search band. Your signal is just noise, so improve placement or sit still.
* **`legacy/ppg_finger_only.cpp`** is the old standalone MAX30102 sketch, kept for reference.

## Status (2026-10-09)

* Hardware, firmware, CSI capture (about 98 Hz, RSSI -42 to -46 at 30 cm) and the MAX30102 reference all work.
* Presence detection works after `calibrate`; the thresholds are tuned for one room and one layout.
* **Wi-Fi heart rate was NOT validated.** In the one recording with a clean PPG reference, neither amplitude nor sanitised-phase CSI showed the pulse. Other takes had a bad reference or too much motion. The LSTM trainer has only been smoke-tested on synthetic data and has never produced a real model.
* Breathing from CSI was not validated against a trustworthy reference either.
* The project was stopped here; treat the heart-rate and breathing numbers as experimental.
