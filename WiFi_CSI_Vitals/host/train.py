"""Train the CSI->HR LSTM using MAX30102 finger-PPG as ground truth.
   python host/train.py            (uses every data/rec_*.npz)
"""
import glob, os, sys
import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vitals, model

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WIN = 30.0
STRIDE = 2.0


def build(path):
    d = np.load(path)
    cts, amp, pts, ir = d["csi_ts"], d["csi_amp"], d["ppg_ts"], d["ir"]
    X, Y, base_err = [], [], []
    t = cts[0] + WIN * 1000
    while t < cts[-1]:
        m = (cts > t - WIN * 1000) & (cts <= t)
        p = (pts > t - 12000) & (pts <= t)
        t += STRIDE * 1000
        if m.sum() < WIN * 60 or p.sum() < 400:
            continue
        ref, snr = vitals.ppg_hr(pts[p], ir[p])
        if ref is None or snr < 15 or not (45 <= ref <= 120):
            continue
        r = vitals.analyze(cts[m], amp[m])
        if r is None:
            continue
        x = model.seq_features(r["hr_comps"])
        if x is None:
            continue
        X.append(x); Y.append(ref); base_err.append(abs(r["hr"] - ref))
    return np.array(X), np.array(Y), np.array(base_err)


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "data", "rec_*.npz")))
    if not files:
        sys.exit("No recordings in data/. Run: python host/oculius.py record 20")
    Xs, Ys, Bs, Fi = [], [], [], []
    for i, f in enumerate(files):
        x, y, b = build(f)
        print(f"{os.path.basename(f)}: {len(y)} labelled windows")
        if len(y):
            Xs.append(x); Ys.append(y); Bs.append(b); Fi += [i] * len(y)
    X, Y, B = np.concatenate(Xs), np.concatenate(Ys), np.concatenate(Bs)
    n = len(Y)
    if n < 100:
        sys.exit(f"Only {n} labelled windows - record more (need ~100+, i.e. 15+ min with finger on sensor).")
    # chronological split: last 20 % validation (no leakage between neighbouring windows)
    cut = int(n * 0.8)
    tr, va = slice(0, cut), slice(cut, n)
    cls = np.clip(np.round(Y) - model.BINS[0], 0, model.NB - 1).astype(int)
    soft = np.exp(-0.5 * ((model.BINS[None] - Y[:, None]) / 1.5) ** 2)
    soft /= soft.sum(1, keepdims=True)
    Xt, St = torch.from_numpy(X), torch.from_numpy(soft.astype(np.float32))
    net = model.HRNet()
    opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-3)
    best, best_state = 1e9, None
    for ep in range(60):
        net.train()
        perm = torch.randperm(cut)
        for i in range(0, cut, 32):
            idx = perm[i:i + 32]
            xb = Xt[idx] * (1 + 0.1 * torch.randn(len(idx), 1, 1))
            loss = -(St[idx] * torch.log_softmax(net(xb), -1)).sum(1).mean()
            opt.zero_grad(); loss.backward(); opt.step()
        net.eval()
        with torch.no_grad():
            pred = model.BINS[net(Xt[va]).argmax(-1).numpy()]
        mae = np.abs(pred - Y[va]).mean() if n - cut else 0
        if mae < best:
            best, best_state = mae, {k: v.clone() for k, v in net.state_dict().items()}
        if ep % 5 == 0:
            print(f"epoch {ep:2d} loss {loss.item():.3f} val MAE {mae:.2f} bpm")
    print(f"\nBest val MAE: {best:.2f} bpm | spectral-peak baseline on same data: {B[va].mean():.2f} bpm "
          f"| predict-the-mean: {np.abs(Y[va] - Y[tr].mean()).mean():.2f} bpm")
    if best >= np.abs(Y[va] - Y[tr].mean()).mean():
        print("WARNING: model is no better than guessing your average HR -> CSI isn't carrying your pulse yet. "
              "Improve placement (see README) and record more data; model NOT saved.")
        return
    os.makedirs(os.path.dirname(model.MODEL_PATH), exist_ok=True)
    torch.save(best_state, model.MODEL_PATH)
    print("saved", os.path.abspath(model.MODEL_PATH))


if __name__ == "__main__":
    main()
