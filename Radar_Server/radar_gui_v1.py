import serial
import threading
import time
import math
import tkinter as tk
from tkinter import ttk

# =========================================================================
# CONFIGURATION - CHANGE THIS TO MATCH YOUR EXACT LAPTOP SERIAL PORT
# =========================================================================
SERIAL_PORT = 'COM3'
BAUD_RATE = 921600

class RadarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Real-Time Multi-Person Wi-Fi Radar")
        self.root.geometry("650x700")
        self.root.configure(bg="#0f172a")

        # Title Label
        title = tk.Label(root, text="Real-Time Multi-Person Wi-Fi Radar", font=("Arial", 16, "bold"), fg="#38bdf8", bg="#0f172a")
        title.pack(pady=5)

        # Status Tracking Label
        self.status_var = tk.StringVar(value="⏳ Connecting to ESP32 on " + SERIAL_PORT + "...")
        self.status_lbl = tk.Label(root, textvariable=self.status_var, font=("Arial", 11, "bold"), fg="#fbbf24", bg="#0f172a")
        self.status_lbl.pack(pady=5)

        # Main Visualization Canvas Window
        self.canvas = tk.Canvas(root, width=600, height=600, bg="#1e293b", highlightthickness=2, highlightbackground="#334155")
        self.canvas.pack(pady=10)

        # Map precisely to your room's clockwise square layout layout coordinates
        self.nodes = {
            4: {"x": 120, "y": 120, "label": "Node 4"},
            1: {"x": 480, "y": 120, "label": "Node 1 (Server)"},
            3: {"x": 120, "y": 480, "label": "Node 3"},
            2: {"x": 480, "y": 480, "label": "Node 2"}
        }

        # Vector mapping path matching order from the ESP32 matrix output strings
        self.path_mapping = [
            (1, 2), (1, 3), (1, 4),
            (2, 3), (2, 4), (3, 4)
        ]

        # Shared data cache for threading communication loops
        self.live_data = [0] * 6
        self.base_data = [0] * 6
        self.data_ready = False
        self.running = True

        # Initialize background background thread to monitor serial stream ports
        self.serial_thread = threading.Thread(target=self.read_serial_stream, daemon=True)
        self.serial_thread.start()

        # Kickstart fast layout canvas loop refreshes
        self.update_gui_canvas()

    def read_serial_stream(self):
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(1) # Let serial stream port settle down safely
            self.status_var.set("🟢 Listening to Hardware Grid Feed...")
            self.status_lbl.config(fg="#10b981")

            while self.running:
                if ser.in_waiting > 0:
                    try:
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        if line.startswith("RADAR:"):
                            raw_data = line.replace("RADAR:", "")
                            parts = raw_data.split("|")
                            if len(parts) == 2:
                                # Safely clean up values array elements
                                self.live_data = [int(x) for x in parts[0].split(",")]
                                self.base_data = [int(x) for x in parts[1].split(",")]
                                self.data_ready = True
                    except Exception:
                        continue
        except Exception as e:
            self.status_var.set(f"🔴 Serial Failure: Verify Port Connection ({str(e)})")
            self.status_lbl.config(fg="#ef4444")

    def update_gui_canvas(self):
        if self.data_ready:
            self.canvas.delete("all")
            active_anomalies = []
            has_active_packets = False

            # Draw and trace link vectors
            for idx, path in enumerate(self.path_mapping):
                live = self.live_data[idx]
                base = self.base_data[idx]
                
                n1 = self.nodes[path[0]]
                n2 = self.nodes[path[1]]

                # Draw baseline setup indicators if lines are uninitialized (-100)
                if live <= -100:
                    self.canvas.create_line(n1["x"], n1["y"], n2["x"], n2["y"], fill="#475569", width=1, dash=(4,4))
                    continue

                has_active_packets = True
                dev = base - live

                # Highlight vectors if signal attenuation drops past 8.5dBm
                if dev > 8.5:
                    line_color = "#ef4444"
                    line_width = 5
                    # Append broken vector line midpoint coordinates to processing group
                    active_anomalies.append(((n1["x"] + n2["x"]) / 2, (n1["y"] + n2["y"]) / 2))
                else:
                    line_color = "#38bdf8"
                    line_width = 2

                self.canvas.create_line(n1["x"], n1["y"], n2["x"], n2["y"], fill=line_color, width=line_width)

                # Overlay real-time dB tracker numbers at mid-points
                mid_x = (n1["x"] + n2["x"]) / 2
                mid_y = (n1["y"] + n2["y"]) / 2
                txt = f"{live}dB (D:{int(dev)})"
                self.canvas.create_text(mid_x, mid_y - 10, text=txt, fill="#94a3b8", font=("Arial", 9))

            # MULTI-PERSON TRACKING MECHANISM:
            # Cluster localized anomalies into distinct target markers
            tracking_targets = []
            for ax, ay in active_anomalies:
                added_to_group = False
                for target in tracking_targets:
                    distance = math.hypot(target["x"] - ax, target["y"] - ay)
                    if distance < 180: # Multi-Person grouping tolerance
                        target["points"].append((ax, ay))
                        target["x"] = sum(p[0] for p in target["points"]) / len(target["points"])
                        target["y"] = sum(p[1] for p in target["points"]) / len(target["points"])
                        added_to_group = True
                        break
                if not added_to_group:
                    tracking_targets.append({"x": ax, "y": ay, "points": [(ax, ay)]})

            # Plot colored tracking spheres for each separate target person found
            for idx, target in enumerate(tracking_targets):
                dot_color = "#ef4444" if idx == 0 else "#a855f7" # Person 1 is Red, Person 2 is Purple
                r = 18
                self.canvas.create_oval(target["x"]-r, target["y"]-r, target["x"]+r, target["y"]+r, fill=dot_color, outline="#f8fafc", width=2)

            if has_active_packets:
                self.status_var.set("🟢 Active Radar Grid Tracker Operational")
                self.status_lbl.config(fg="#10b981")
            else:
                self.status_var.set("⏳ Waiting for Nodes 2, 3, 4 to send wireless data pack...")
                self.status_lbl.config(fg="#fbbf24")

            # Always render solid nodes structure markers clearly on layout
            for node_id, node in self.nodes.items():
                color = "#10b981" if node_id == 1 else "#0284c7"
                r = 10
                self.canvas.create_oval(node["x"]-r, node["y"]-r, node["x"]+r, node["y"]+r, fill=color, outline="#f8fafc", width=2)
                self.canvas.create_text(node["x"], node["y"] + 22, text=node["label"], fill="#f8fafc", font=("Arial", 10, "bold"))

        # Schedule next canvas screen frame calculation check (at a super fast 50ms interval)
        self.root.after(50, self.update_gui_canvas)

    def close(self):
        self.running = False
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = RadarApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()
