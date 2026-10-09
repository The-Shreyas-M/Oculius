"""Oculius CLI.
  python host/oculius.py live        # presence + breathing + heart rate, once per second
  python host/oculius.py calibrate   # leave the room, run 30 s -> empty-room baseline
  python host/oculius.py record 20   # record N minutes (CSI + finger PPG) for training
"""
import argparse, json, os, sys, time
from collections import deque
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vitals
from stream import frames

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BASE = os.path.join(ROOT, "baseline.json")
WIN_S = 30


def load_baseline():
    try:
        return json.load(open(BASE))
    except Exception:
        return None


def collect(port, seconds=None, on_second=None):
    """Yield-less collector: keeps rolling buffers, calls on_second(csi_ts, csi_amp, ppg_ts, ppg_ir, rssi)."""
    cts, camp, pts, pir, pred, rs = deque(), deque(), deque(), deque(), deque(), deque()
    t0 = time.time(); last = t0; nframes = 0
    for f in frames(port):
        if f.type == 1:
            cts.append(f.ts); camp.append(np.abs(f.csi)); rs.append(f.rssi); nframes += 1
        else:
            pts.append(f.ts); pir.append(f.ir); pred.append(f.red)
        now = time.time()
        if seconds is None or True:
            while cts and cts[-1] - cts[0] > (WIN_S + 5) * 1000: cts.popleft(); camp.popleft(); rs.popleft()
            while pts and pts[-1] - pts[0] > (WIN_S + 5) * 1000: pts.popleft(); pir.popleft(); pred.popleft()
        if now - last >= 1.0:
            last = now
            stop = on_second(cts, camp, pts, pir, rs, nframes / (now - t0))
            if stop or (seconds and now - t0 > seconds):
                return


def cmd_live(a):
    import model
    base = load_baseline()
    if base is None:
        print("(no baseline.json - run `calibrate` with the room empty for better presence detection)")
    net = model.load()
    print("HR model:", "LSTM loaded" if net else "none (spectral-peak fallback; record + train to improve)")

    def tick(cts, camp, pts, pir, rs, rate):
        if len(cts) < 50:
            print(f"waiting for CSI... {len(cts)} frames"); return
        r = vitals.analyze(list(cts), np.array(camp), base)
        ppg = vitals.ppg_hr(list(pts), list(pir)) if len(pts) > 200 else (None, 0)
        if r is None:
            print(f"collecting {(cts[-1]-cts[0])/1000:4.0f}/{WIN_S}s  rate {rate:.0f} Hz"); return
        hr, how = r["hr"], "fft"
        m = model.predict(r["hr_comps"])
        if m: hr, how = m[0], f"lstm{m[1]*100:3.0f}%"
        pres = "PRESENT" if r["present"] else "empty  "
        ref = f"  | ref HR {ppg[0]:5.1f}" if ppg[0] else ""
        line = f"{pres} rate {rate:3.0f}Hz rssi {np.mean(list(rs)[-50:]):4.0f} mot {r['motion']*1000:5.1f} slow {r['slow']*1000:5.1f}"
        if r["present"]:
            line += f" | BR {r['br']:4.1f}/min (snr {r['br_snr']:4.0f}) | HR {hr:5.1f} ({how}, snr {r['hr_snr']:4.0f}){ref}"
        else:
            line += ref
        print(line)

    collect(a.port, None, tick)


def cmd_calibrate(a):
    acc = {"motion": [], "slow": []}
    print("Calibrating: stay OUT of the room / away from the link for 60 s (fan on as usual)...")

    def tick(cts, camp, pts, pir, rs, rate):
        r = vitals.analyze(list(cts), np.array(camp)) if len(cts) > 50 else None
        if r:
            acc["motion"].append(r["motion"]); acc["slow"].append(r["slow"])
            print(f"  {len(acc['motion'])}/30  motion {r['motion']*1000:.2f}  slow {r['slow']*1000:.2f}")
        return len(acc["motion"]) >= 30

    collect(a.port, 120, tick)
    if acc["motion"]:
        b = {k: float(np.percentile(v, 90)) for k, v in acc.items()}
        json.dump(b, open(BASE, "w")); print("saved", BASE, b)


def cmd_record(a):
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    out = os.path.join(ROOT, "data", time.strftime("rec_%Y%m%d_%H%M%S.npz"))
    C, P = [], []
    t_end = time.time() + a.minutes * 60
    print(f"Recording {a.minutes} min. Finger on the MAX30102, sit still & breathe normally. Ctrl+C to stop early.")
    last = 0
    try:
        for f in frames(a.port):
            if f.type == 1: C.append((f.ts, f.rssi, f.csi))
            else: P.append((f.ts, f.red, f.ir))
            if time.time() - last > 5:
                last = time.time()
                ir = P[-1][2] if P else 0
                print(f"  {int(t_end-time.time())}s left | csi {len(C)} ppg {len(P)} | ir {ir}", "(NO FINGER!)" if ir < 20000 else "")
            if time.time() > t_end: break
    except KeyboardInterrupt:
        pass
    np.savez_compressed(out, csi_ts=np.array([c[0] for c in C]), rssi=np.array([c[1] for c in C]),
                        csi_iq=np.array([c[2] for c in C], dtype=np.complex64),
                        csi_amp=np.array([np.abs(c[2]) for c in C], dtype=np.float32),
                        ppg_ts=np.array([p[0] for p in P]), red=np.array([p[1] for p in P]),
                        ir=np.array([p[2] for p in P]))
    print("saved", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["live", "calibrate", "record"])
    ap.add_argument("minutes", nargs="?", type=float, default=20)
    ap.add_argument("--port", default="COM3")
    a = ap.parse_args()
    {"live": cmd_live, "calibrate": cmd_calibrate, "record": cmd_record}[a.cmd](a)
