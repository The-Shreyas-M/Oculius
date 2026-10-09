"""LSTM heart-rate estimator on top of CSI spectral frames (labels come from the MAX30102)."""
import os
import numpy as np
import torch
import torch.nn as nn
from vitals import FS, spectrum

BINS = np.arange(45, 121)          # 45..120 bpm, 1 bpm classes
NB = len(BINS)
STEPS = 16                         # sequence length (1 s apart)
SUB = 10.0                         # seconds of signal behind each step
NCOMP = 3
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "hr_lstm.pt")


def frame_feature(comps_win):
    """comps_win [n, NCOMP] -> [NCOMP*NB] normalised spectrum on the bpm grid."""
    out = []
    for c in comps_win.T:
        f, P = spectrum(c, FS, 0.7, 2.1, nfft=4096)
        v = np.interp(BINS / 60.0, f, P)
        out.append(v / (v.sum() + 1e-9))
    return np.concatenate(out).astype(np.float32)


def seq_features(hr_comps):
    """hr_comps: [T, >=NCOMP] HR-band PCA components of a ~30 s window -> [STEPS, NCOMP*NB]."""
    comps = hr_comps[:, :NCOMP]
    if comps.shape[1] < NCOMP:
        comps = np.pad(comps, ((0, 0), (0, NCOMP - comps.shape[1])))
    n, w = len(comps), int(SUB * FS)
    ends = n - (np.arange(STEPS)[::-1] * int(FS)).astype(int)
    if ends[0] < w:
        return None
    return np.stack([frame_feature(comps[e - w:e]) for e in ends])


class HRNet(nn.Module):
    def __init__(self, nin=NCOMP * NB, hid=96):
        super().__init__()
        self.lstm = nn.LSTM(nin, hid, num_layers=2, batch_first=True, dropout=0.2)
        self.head = nn.Linear(hid, NB)

    def forward(self, x):
        o, _ = self.lstm(x * 20.0)
        return self.head(o[:, -1])


_net = None


def load():
    global _net
    if _net is None and os.path.exists(MODEL_PATH):
        _net = HRNet()
        _net.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
        _net.eval()
    return _net


def predict(hr_comps):
    """Returns (bpm, confidence 0-1) or None if no trained model / not enough data."""
    net = load()
    if net is None:
        return None
    x = seq_features(hr_comps)
    if x is None:
        return None
    with torch.no_grad():
        p = torch.softmax(net(torch.from_numpy(x)[None]), -1)[0].numpy()
    i = int(p.argmax())
    lo, hi = max(0, i - 3), min(NB, i + 4)
    bpm = float((BINS[lo:hi] * p[lo:hi]).sum() / p[lo:hi].sum())
    return bpm, float(p[lo:hi].sum())
