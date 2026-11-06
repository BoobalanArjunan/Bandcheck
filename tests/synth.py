"""Synthetic audio with a KNOWN real bandwidth: broadband noise with a falling spectrum, a few harmonic tones and clicks,
optionally lowpassed (a lossy-encoder-like cut) or upsampled from a lower rate. Written as 16-bit PCM so a real
quantisation floor exists above the cut-off, as in real files."""
import numpy as np
from scipy.signal import firwin, fftconvolve, resample_poly

TILT = 0.75      # amplitude falls as f**-0.75 (about 4.5 dB per octave), a gentler fall than most real music


def make_full(sr, seconds=20.0, seed=0, tilt=TILT, level=0.3):
    """Sound that reaches the Nyquist frequency."""
    rng = np.random.RandomState(seed)
    n = int(seconds * sr)
    X = np.fft.rfft(rng.randn(n))
    f = np.fft.rfftfreq(n, 1 / sr)
    f[0] = f[1]
    x = np.fft.irfft(X * (f / 1000.0) ** -tilt, n)
    t = np.arange(n) / sr
    env = 0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * t + rng.rand() * 6) ** 2        # slow loudness swell
    x = x / np.std(x) * env
    for f0 in (110.0, 220.0, 440.0):                                            # a few tones with harmonics
        for h in range(1, 12):
            if f0 * h < sr / 2 * 0.9:
                x += 0.15 / h * np.sin(2 * np.pi * f0 * h * t + rng.rand() * 6)
    for c in np.arange(0.25, seconds, 0.5):                                     # clicks (broadband)
        i = int(c * sr)
        x[i:i + 3] += 4.0 * rng.randn(3)
    return (level * x / np.abs(x).max()).astype(np.float64)


def lowpass(x, sr, cutoff_hz, transition_hz=400.0):
    """Steep FIR lowpass, like an encoder's lowpass."""
    nt = int(4 * sr / transition_hz) | 1
    return fftconvolve(x, firwin(nt, cutoff_hz, fs=sr), mode="same")


def upsampled(sr, from_sr, seconds=20.0, seed=0):
    """Sound that really only reaches from_sr/2, stored at sr."""
    low = make_full(from_sr, seconds, seed)
    from math import gcd
    g = gcd(int(sr), int(from_sr))
    y = resample_poly(low, sr // g, from_sr // g)
    return 0.9 * y / np.abs(y).max() * 0.3


def to_pcm16(x):
    return np.round(np.clip(x, -1, 1) * 32767).astype(np.int16)
