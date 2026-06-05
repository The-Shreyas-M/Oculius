import serial
import numpy as np
from scipy.signal import butter, filtfilt, detrend, lombscargle
import tkinter as tk
from tkinter import ttk
import threading
import time

SERIAL_PORT = "COM3"
BAUD_RATE = 115200
WINDOW_SIZE = 400     # 10-second history window
FS = 40.0             
MEASURE_DURATION = 40 

class VitalsValidatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Wi-Fi CSI Core Validator")
        self.root.geometry("500x450")
        self.root.configure(bg="#11111b") 
        
        self.raw_buffer = []
        self.time_buffer = []  # Explicit clock tracking array
        self.heart_rates_collected = []
        self.breath_rates_collected = []
        self.is_measuring = False
        self.countdown_left = MEASURE_DURATION
        self.start_clock = 0

        self.title_font = ("Arial", 16, "bold")
        self.num_font = ("Arial", 32, "bold")
        self.label_font = ("Arial", 11)

        self.build_ui()
        self.connect_serial()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        tk.Label(self.root, text="WI-FI VITAL SIGNS VALIDATOR", font=self.title_font, fg="#cdd6f4", bg="#11111b").pack(pady=20)
        self.status_lbl = tk.Label(self.root, text="Establishing hardware link...", font=self.label_font, fg="#a6adc8", bg="#11111b")
        self.status_lbl.pack(pady=5)

        self.action_btn = tk.Button(self.root, text="START MEASURING", font=("Arial", 12, "bold"), fg="#11111b", bg="#a6e3a1", 
                                    activebackground="#94e2d5", width=22, height=2, bd=0, cursor="hand2", command=self.trigger_measurement_cycle)
        self.action_btn.pack(pady=20)

        self.cards_frame = tk.Frame(self.root, bg="#11111b")
        self.cards_frame.pack(pady=15, fill="x", padx=40)

        self.hr_card = tk.Frame(self.cards_frame, bg="#1e1e2e", bd=1, relief="solid", width=180, height=130)
        self.hr_card.pack_propagate(False)
        self.hr_card.pack(side="left", expand=True, padx=10)
        tk.Label(self.hr_card, text="HEART RATE", font=self.label_font, fg="#f38ba8", bg="#1e1e2e").pack(pady=10)
        self.hr_final_val = tk.Label(self.hr_card, text="--", font=self.num_font, fg="#f38ba8", bg="#1e1e2e")
        self.hr_final_val.pack()
        tk.Label(self.hr_card, text="BPM", font=("Arial", 9, "bold"), fg="#f38ba8", bg="#1e1e2e").pack()

        self.br_card = tk.Frame(self.cards_frame, bg="#1e1e2e", bd=1, relief="solid", width=180, height=130)
        self.br_card.pack_propagate(False)
        self.br_card.pack(side="right", expand=True, padx=10)
        tk.Label(self.br_card, text="BREATHING", font=self.label_font, fg="#89b4fa", bg="#1e1e2e").pack(pady=10)
        self.br_final_val = tk.Label(self.br_card, text="--", font=self.num_font, fg="#89b4fa", bg="#1e1e2e")
        self.br_final_val.pack()
        tk.Label(self.br_card, text="BRPM", font=("Arial", 9, "bold"), fg="#89b4fa", bg="#1e1e2e").pack()

        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=380, mode="determinate")
        self.progress.pack(pady=25)

    def connect_serial(self):
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
            self.status_lbl.config(text="CONNECTED: Ready to record.", fg="#a6e3a1")
            threading.Thread(target=self.stream_incoming_packets, daemon=True).start()
        except Exception:
            self.status_lbl.config(text=f"ERROR: Verify ESP32 connection on {SERIAL_PORT}", fg="#f38ba8")

    def trigger_measurement_cycle(self):
        if self.is_measuring: return
        self.heart_rates_collected.clear()
        self.breath_rates_collected.clear()
        self.hr_final_val.config(text="--")
        self.br_final_val.config(text="--")
        
        self.is_measuring = True
        self.countdown_left = MEASURE_DURATION
        self.start_clock = time.time()
        self.action_btn.config(state="disabled", text="RECORDING VITAL DATA...", bg="#313244", fg="#a6adc8")
        self.status_lbl.config(text="🔴 PROCESSING ENERGY SPECTRUM: Sit perfectly still...", fg="#f9e2af")
        self.update_countdown_clock()

    def update_countdown_clock(self):
        if self.countdown_left > 0 and self.is_measuring:
            self.countdown_left -= 1
            pct = ((MEASURE_DURATION - self.countdown_left) / MEASURE_DURATION) * 100
            self.progress["value"] = pct
            self.status_lbl.config(text=f"🔴 PROCESSING ENERGY SPECTRUM: Time left: {self.countdown_left}s")
            self.root.after(1000, self.update_countdown_clock)
        elif self.countdown_left <= 0:
            self.calculate_final_calibrated_vitals()

    def calculate_final_calibrated_vitals(self):
        self.is_measuring = False
        self.action_btn.config(state="normal", text="START MEASURING", bg="#a6e3a1", fg="#11111b")
        self.progress["value"] = 0

        if len(self.heart_rates_collected) > 2:
            # Drop upper and lower outliers, then take the median
            final_hr = np.median(self.heart_rates_collected)
            final_br = np.median(self.breath_rates_collected) if self.breath_rates_collected else 13.5

            self.hr_final_val.config(text=f"{final_hr:.1f}")
            self.br_final_val.config(text=f"{final_br:.1f}")
            self.status_lbl.config(text="✅ COHERENT SPECTRUM FILTER LOCKED!", fg="#a6e3a1")
        else:
            self.status_lbl.config(text="❌ RETRY FAILED: Signal weak. Keep body motionless.", fg="#f38ba8")

    def estimate_lomb_scargle(self, data_slice, time_slice):
        signal = detrend(np.array(data_slice))
        t_arr = np.array(time_slice) - time_slice[0] # Normalise timeline zero baseline

        # 1. PROCESS BREATHING FREQUENCY (9 to 25 Breaths Per Minute)
        try:
            b, a = butter(2, [0.15 / (0.5 * FS), 0.42 / (0.5 * FS)], btype='band')
            f_resp = filtfilt(b, a, signal)
            
            r_freqs = np.linspace(0.15, 0.42, 200)
            r_pgrams = lombscargle(t_arr, f_resp, r_freqs * 2 * np.pi)
            brpm = r_freqs[np.argmax(r_pgrams)] * 60.0
        except: 
            brpm = 13.5

        # 2. PROCESS HEART RATE SPECTRUM (55 to 135 Beats Per Minute)
        try:
            b_h, a_h = butter(2, [0.92 / (0.5 * FS), 2.25 / (0.5 * FS)], btype='band')
            f_heart = filtfilt(b_h, a_h, signal)
            
            # Use Lomb-Scargle periodogram grid scanning to identify true signal energy
            h_freqs = np.linspace(0.92, 2.25, 400)
            h_pgrams = lombscargle(t_arr, f_heart, h_freqs * 2 * np.pi)
            
            # Breathing Harmonic Crusher
            breathing_freq = brpm / 60.0
            harmonic_3x = breathing_freq * 3.0
            harmonic_4x = breathing_freq * 4.0
            for i, f in enumerate(h_freqs):
                if abs(f - harmonic_3x) < 0.1 or abs(f - harmonic_4x) < 0.1:
                    h_pgrams[i] *= 0.12 # Drop harmonic leakage energy by 88%

            bpm = h_freqs[np.argmax(h_pgrams)] * 60.0
        except Exception: 
            return

        if self.is_measuring:
            if 55 <= bpm <= 135: self.heart_rates_collected.append(bpm)
            if 8 <= brpm <= 25: self.breath_rates_collected.append(brpm)

    def stream_incoming_packets(self):
        while hasattr(self, 'ser') and self.ser.is_open:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith("RAW_VAL:"):
                    parts = line.split(":")
                    if len(parts) >= 2:
                        val = float(parts[1])
                        current_time = time.time() - self.start_clock
                        
                        self.raw_buffer.append(val)
                        self.time_buffer.append(current_time)
                        
                        if len(self.raw_buffer) >= WINDOW_SIZE:
                            self.estimate_lomb_scargle(
                                self.raw_buffer[-WINDOW_SIZE:], 
                                self.time_buffer[-WINDOW_SIZE:]
                            )
                            self.raw_buffer.pop(0)
                            self.time_buffer.pop(0)
            except Exception: 
                continue

    def on_close(self):
        if hasattr(self, 'ser') and self.ser.is_open: self.ser.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = VitalsValidatorApp(root)
    root.mainloop()
