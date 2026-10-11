# Oculius

<p align="center">
  <img src="https://img.shields.io/badge/Status-Experimental-orange" alt="Status: Experimental" />
  <img src="https://img.shields.io/badge/Platform-ESP32%20%2F%20Python-C++%20%7C%20Python-blue" alt="Platform: ESP32 / Python" />
  <img src="https://img.shields.io/badge/Focus-Wireless%20Vitals-8A2BE2" alt="Focus: Wireless Vitals" />
</p>

A research-oriented repository exploring wireless sensing for human presence and vital-sign estimation using ESP32 devices, Wi-Fi CSI, radar-inspired firmware, and lightweight signal processing.

Oculius is not a polished consumer product. It is a collection of experimental prototypes, firmware sketches, data-processing scripts, and exploratory ideas for detecting motion, presence, breathing, and heart activity without traditional wearable sensors.

---

## Why this project exists

The core idea behind Oculius is simple but ambitious:

- use wireless signals to infer whether a person is present
- estimate breathing behavior from signal variation
- attempt to recover heart-related motion from radio/channel differences
- explore low-cost hardware using ESP32-class devices and Python-based analysis

This repo contains several parallel approaches:

- radar-style ESP32 firmware experiments
- server-side visualization and data collection
- Wi-Fi CSI-based vital monitoring prototypes
- a smaller embedded Vitals project with transmitter/receiver experiments

---

## Repository overview

```text
Oculius/
├── Radar_Firmware/            # ESP32/Radar firmware experiments and Arduino sketches
├── Radar_Server/              # Python GUI/server tooling for radar-style visualization
├── Test/                      # Small test sketches and validation code
├── Vitals/                    # Embedded vital-sign experiments and notes
├── WiFi_CSI_Vitals/           # Main research prototype: Wi-Fi CSI-based presence/BR/HR
├── Radar_idea_prompt.txt      # Initial project brief / concept prompt
├── README.md                  # This file
└── ...
```

---

## Major components

### 1) Radar firmware

The `Radar_Firmware/` folder contains Arduino/ESP32 sketches exploring radar-like signal behavior and sensor/serial processing. These files are useful as early prototypes and diagnostics rather than final, production-quality code.

Examples include:

- `Final.ino`
- `Test.ino`
- `GUI with python but noise.ino`
- `Almost there serially but inacccurate.ino`

These represent iterative attempts to detect movement and infer human presence using radio signal changes.

### 2) Radar server / GUI

The `Radar_Server/` directory contains Python-based visualization code, likely intended to display the network graph or a basic UI for radar-style data.

Key file:

- `radar_gui_v1.py`

This fits the project’s exploratory nature: simple GUI tooling, often used to visualize signal or room activity during experiments.

### 3) Vitals project

The `Vitals/` folder contains a smaller embedded system focused on heartbeat/breathing-oriented sensor work.

It includes:

- `main.py` — likely Python-side processing or test orchestration
- `transmitter/transmitter.ino`
- `reciever/reciever.ino`
- `TODO.txt` — notes emphasizing the challenge of accurate heartbeat estimation

This part of the repo makes the core research difficulty explicit: getting reliable heart-rate estimates from weak wireless measurements remains non-trivial.

### 4) WiFi CSI vitals prototype

The `WiFi_CSI_Vitals/` directory is the most substantial and best-documented subsystem in the repository.

It is built around:

- ESP32 transmitter and receiver nodes
- Wi-Fi CSI capture
- Python-driven host analysis
- optional MAX30102 reference sensor for training and validation
- a lightweight LSTM model for heart-rate estimation

This is the primary component that most closely matches the project's stated goal: using a Wi-Fi link to estimate presence and, experimentally, breathing and heart rate.

---

## Project architecture

```text
                 +----------------------+
                 |   ESP32 TX node      |
                 | broadcasts CSI frames|
                 +----------+-----------+
                            |
                            | 2.4 GHz wireless link
                            v
                 +----------------------+
                 |   ESP32 RX node      |
                 | records CSI + RSSI   |
                 +----------+-----------+
                            |
                            | UART / USB
                            v
                 +----------------------+
                 |   PC / host Python   |
                 | calibrate / live /   |
                 | record / train       |
                 +----------------------+
                            |
               +------------+------------+
               |                         |
               v                         v
       Presence / breathing     Heart-rate model
       signal processing          (experimental LSTM)
```

---

## What works and what is experimental

The project is candid about the current validity of the measurements.

From the project’s own notes in `WiFi_CSI_Vitals/README.md`:

- presence detection can be workable after calibration
- breathing estimation may function under favorable conditions
- heart-rate estimation is still experimental
- the project is best treated as a research prototype rather than a validated monitoring system

This repo is intentionally honest: the results are promising for a low-cost experimental setup, but not yet reliable enough to be treated as a clinically meaningful or production-ready heart-rate monitor.

---

## Quick start

The main prototype is under `WiFi_CSI_Vitals/`.

### 1) Open the main project folder

```bash
cd WiFi_CSI_Vitals
```

### 2) Flash the devices

The project documentation indicates re-flashing via PlatformIO is the intended flow:

```bash
pio run -e tx -t upload
pio run -e rx -t upload
```

### 3) Calibrate the room

This should be done once per layout and environment:

```bash
python host/oculius.py calibrate
```

### 4) Run a live readout

```bash
python host/oculius.py live
```

### 5) Optional: collect training data for heart rate

```bash
python host/oculius.py record 20
```

Then train the model:

```bash
python host/train.py
```

---

## Hardware assumptions

This repo is strongly oriented around low-cost ESP32 hardware.

Typical setup in the Wi-Fi CSI project includes:

- ESP32 transmitter node
- ESP32-S3 receiver node
- 2.4 GHz Wi-Fi link
- optional MAX30102 sensor for training/reference labeling
- Python host processing on a PC

The project text also emphasizes physical placement and environmental stability:

- keep devices at chest height
- avoid sitting directly between transmitter and receiver
- keep furniture and metal away from the signal path
- avoid strong motion sources like ceiling fans during measurements

These are important because small environmental shifts can dominate the subtle motion corresponding to breathing or pulse.

---

## Key files and references

### Main documentation

- `WiFi_CSI_Vitals/README.md` — the most detailed project guide and usage reference
- `Radar_idea_prompt.txt` — original concept and direction for the project
- `Vitals/TODO.txt` — notes highlighting the challenge of extracting heartbeat reliably

### Core implementation folders

- `WiFi_CSI_Vitals/host/` — Python analysis pipeline
- `WiFi_CSI_Vitals/src/tx/` — transmitter firmware
- `WiFi_CSI_Vitals/src/rx/` — receiver firmware
- `WiFi_CSI_Vitals/lib/MAX3010x/` — MAX30102 support library code

---

## Development notes

This repository is best understood as a hands-on research sandbox:

- it experiments with CSI-based inference
- it mixes embedded firmware, Python tooling, and signal processing
- it tests physical sensing assumptions in real environments
- it iterates quickly, with several prototype folders rather than a single polished product

The work is part technical prototype, part experimentation log, and part learning project.

---

## Repository status

This project demonstrates a meaningful exploration of wireless human sensing using inexpensive hardware. It is especially useful for:

- embedded systems experimentation
- signal-processing prototyping
- IoT and wireless sensing learning
- research into CSI-based motion and vital estimation

However, it should be approached as an experimental codebase, not a turnkey product or validated clinical tool.

---

## A note on the name

Oculius suggests a vision-like or observation-focused concept: sensing what is happening in a room by observing subtle electromagnetic changes. That matches the project’s spirit: using the environment itself as a sensor.

---

## Contributing

This repo is an exploratory research project, so contributions are welcome if they help with:

- cleaner architecture and structure
- more robust data pipelines
- better documentation and examples
- stronger signal-processing methods
- easier setup for reproducing experiments

If you are working on the project, keep the experimental nature of the work in mind and document assumptions clearly.

---

## License

No explicit license file was identified in the repository at the time this README was prepared. If you plan to reuse or build on this project, confirm the licensing terms before distribution or commercialization.

---

## Final thought

Oculius sits at the intersection of embedded systems, wireless sensing, and health-tech experimentation. It is a compelling example of a project that explores whether subtle wireless signal changes can reveal physical presence and vital activity without direct contact sensors.

If you are interested in research prototypes, low-cost radio sensing, or ESP32-based signal processing, this repository is a strong example of that exploration in motion.

---

<p align="center">
  <em>Built for experimentation. Intended for learning, prototyping, and research.</em>
</p>
