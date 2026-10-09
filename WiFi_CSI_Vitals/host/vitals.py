"""CSI -> presence / breathing / heart-rate signal processing (single TX->RX link)."""
import numpy as np
from scipy.signal import butter, sosfiltfilt, find_peaks

FS = 50.0  # uniform processing rate (Hz)


def resample(ts_ms, X, fs=FS):
    """Irregular (ts, X[T,K]) -> uniform grid at fs. Returns (t_grid_s, X_uniform)."""
    t = (np.asarray(ts_ms, dtype=np.float64) - ts_ms[0]) / 1000.0
    t, idx = np.unique(t, return_index=True)
    X = np.asarray(X)[idx]
    g = np.arange(0, t[-1], 1.0 / fs)
    out = np.empty((len(g), X.shape[1]), dtype=np.float32)
    for k in range(X.shape[1]):
        out[:, k] = np.interp(g, t, X[:, k])
    return g, out


def valid_subcarriers(A):
    """Drop null/guard subcarriers (amplitude ~0) and ones with huge outliers."""
    m = A.mean(0)
    return np.where(m > 0.25 * np.median(m[m > 0]))[0]


def despike(A, k=4.0):
    """Hampel-ish clipping per subcarrier to kill occasional AGC jumps."""
    med = np.median(A, 0)
    mad = np.median(np.abs(A - med), 0) + 1e-6
    return np.clip(A, med - k * 1.4826 * mad * 3, med + k * 1.4826 * mad * 3)


def bandpass(X, lo, hi, fs=FS, order=4):
    sos = butter(order, [lo, hi], btype="band", fs=fs, output="sos")
    return sosfiltfilt(sos, X, axis=0)


def band_pca(A, lo, hi, fs=FS, ncomp=3):
    """Band-limit all subcarriers then take the top principal components (time series)."""
    B = bandpass(A, lo, hi, fs)
    B = B / (B.std(0) + 1e-6)
    U, S, _ = np.linalg.svd(B - B.mean(0), full_matrices=False)
    return U[:, :ncomp] * S[:ncomp]


def spectrum(x, fs=FS, lo=0.1, hi=3.0, nfft=8192):
    x = (x - x.mean()) * np.hanning(len(x))
    P = np.abs(np.fft.rfft(x, nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1 / fs)
    m = (f >= lo) & (f <= hi)
    return f[m], P[m]


def peak_rate(comps, lo, hi, fs=FS):
    """Pick the component with the cleanest spectral peak. Returns (bpm, snr)."""
    best = (None, 0.0)
    for c in comps.T:
        f, P = spectrum(c, fs, lo, hi)
        i = int(np.argmax(P))
        # SNR: peak (+/-0.03 Hz) energy versus the rest of the band
        pk = (np.abs(f - f[i]) < 0.03)
        snr = P[pk].sum() / (P[~pk].sum() + 1e-9) * (~pk).sum() / max(pk.sum(), 1)
        if snr > best[1]:
            best = (f[i] * 60.0, snr)
    return best


def motion_level(A, fs=FS):
    """Gross-motion energy: RMS of 0.5-8 Hz content, averaged over subcarriers (normalised by DC)."""
    B = bandpass(A, 0.5, 8.0, fs)
    return float(np.mean(B.std(0) / (A.mean(0) + 1e-6)))


def analyze(ts_ms, csi_amp, baseline=None):
    """csi_amp: [T,K] amplitudes covering the last ~30 s. Returns dict of results."""
    g, A = resample(ts_ms, csi_amp)
    if len(g) < FS * 12:
        return None
    idx = valid_subcarriers(A)
    A = despike(A[:, idx])
    mot = motion_level(A)
    # Breathing: 0.1-0.5 Hz (6-30 bpm) over the whole window
    br_comps = band_pca(A, 0.10, 0.50)
    br, br_snr = peak_rate(br_comps, 0.10, 0.50)
    # Heart: 0.8-2.0 Hz (48-120 bpm). Notch out anything at 2x breathing is skipped; harmonics
    # are handled by the trained model when available.
    hr_comps = band_pca(A, 0.80, 2.00)
    hr, hr_snr = peak_rate(hr_comps, 0.80, 2.00)
    # slow-band energy (breathing amplitude relative to noise floor)
    slow = float(np.mean(bandpass(A, 0.10, 0.50).std(0) / (A.mean(0) + 1e-6)))
    out = dict(motion=mot, slow=slow, br=br, br_snr=br_snr, hr=hr, hr_snr=hr_snr,
               hr_comps=hr_comps, A=A, fs=FS)
    nb = baseline or {"motion": 0.0, "slow": 0.0}
    out["present"] = bool(mot > 1.15 * nb["motion"] + 1e-3 or slow > 1.2 * nb["slow"] + 5e-4)
    return out


def ppg_hr(ts_ms, ir, fs=FS):
    """Reference heart rate from a finger PPG window. Returns (bpm, snr) or (None, 0)."""
    ir = np.asarray(ir, dtype=np.float64)
    if len(ir) < 10 or ir.mean() < 20000:  # no finger
        return None, 0.0
    g, X = resample(ts_ms, ir[:, None], fs)
    if len(g) < fs * 8:
        return None, 0.0
    comp = bandpass(X, 0.7, 3.0, fs)
    return peak_rate(comp, 0.7, 3.0, fs)
