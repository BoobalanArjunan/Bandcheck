"""Audio -> long-term average spectrum, and the search for a sharp cut-off in it.

A file that was upsampled, or lowpassed by a lossy encoder, has real sound up to some frequency and almost nothing
above it, with a steep drop in between (a "cliff"). Natural sound fades gradually. So BandCheck looks for the steepest
drop in the average spectrum and reports where it is. Light on purpose: numpy, scipy, soundfile only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import soundfile as sf
from scipy.signal import medfilt, stft

MAX_SECONDS = 120.0          # long files: only the middle 2 minutes are used
MIN_SECONDS = 2.0
ACTIVE_FLOOR_DB = -30.0      # frames more than 30 dB below the loudest frame are ignored
MIN_ACTIVE_FRAMES = 4
SEARCH_FROM_HZ = 2500.0      # a cliff below this is not looked for (speech and music change a lot down there)
EDGE_MARGIN_HZ = 500.0       # a cliff must leave at least this much spectrum above it to compare
SIDE_GAP_HZ, SIDE_SPAN_HZ = 200.0, 1000.0   # compare the level just below the cliff with the level just above it
GRID_HZ = 50.0
CLIFF_DB = 25.0              # the drop that counts as a cliff
KNEE_DB = 10.0               # the cut-off is reported where the level has fallen this far below the band's own level
SMOOTH_HZ = 100.0


@dataclass
class Spectrum:
    freqs: np.ndarray
    level_db: np.ndarray         # average power per bin, dB, relative to its own maximum
    sample_rate: int
    seconds: float               # length of the audio analysed
    active_seconds: float        # time in frames that were loud enough to use


@dataclass
class Cliff:
    cutoff_hz: float
    drop_db: float               # level just below the cut-off minus level just above it
    floor_db: float              # median level of everything above the cut-off, relative to just below it


def load_mono(path, max_seconds: float = MAX_SECONDS):
    """Reads the file at its OWN sample rate (no resampling) -> (mono float64, sample rate)."""
    x, sr = sf.read(str(path), dtype="float64", always_2d=True)
    x = x.mean(axis=1)
    n = int(max_seconds * sr)
    if len(x) > n:
        s = (len(x) - n) // 2
        x = x[s:s + n]
    return x, int(sr)


def mean_spectrum(x: np.ndarray, sr: int) -> Optional[Spectrum]:
    """Average power spectrum over the loud frames. None if the audio is too short, silent or has too few loud frames."""
    if len(x) < MIN_SECONDS * sr or not np.any(np.abs(x) > 1e-9):
        return None
    n = int(2 ** round(np.log2(max(sr / 10.0, 256))))        # about 10 Hz per bin
    n = min(max(n, 512), 8192)
    _, _, Z = stft(x, fs=sr, nperseg=n, noverlap=n // 2, boundary=None, padded=False)
    P = np.abs(Z) ** 2
    energy = P.sum(axis=0)
    if energy.max() <= 0:
        return None
    active = energy > energy.max() * 10 ** (ACTIVE_FLOOR_DB / 10)
    if active.sum() < MIN_ACTIVE_FRAMES:
        return None
    S = P[:, active].mean(axis=1)
    L = 10 * np.log10(S + 1e-30)
    L -= L.max()
    freqs = np.linspace(0, sr / 2, len(L))
    hop = n // 2
    return Spectrum(freqs, L, sr, len(x) / sr, float(active.sum() * hop / sr))


def find_cliff(sp: Spectrum) -> Optional[Cliff]:
    """The sharpest drop (at least CLIFF_DB) in the smoothed average spectrum, or None if the spectrum fades gradually."""
    f, nyq = sp.freqs, sp.sample_rate / 2
    df = f[1] - f[0]
    k = max(3, int(SMOOTH_HZ / df) | 1)
    Ls = medfilt(sp.level_db, k)
    best_g, best_d = None, 0.0
    for g in np.arange(SEARCH_FROM_HZ, nyq - EDGE_MARGIN_HZ, GRID_HZ):
        lo = (f >= g - SIDE_SPAN_HZ) & (f < g - SIDE_GAP_HZ)
        hi = (f > g + SIDE_GAP_HZ) & (f <= min(g + SIDE_SPAN_HZ, nyq))
        if lo.sum() < 3 or hi.sum() < 3:
            continue
        d = float(np.median(Ls[lo]) - np.median(Ls[hi]))
        if d > best_d:
            best_g, best_d = g, d
    if best_g is None or best_d < CLIFF_DB:
        return None
    lo = (f >= best_g - SIDE_SPAN_HZ) & (f < best_g - SIDE_GAP_HZ)
    hi = (f > best_g + SIDE_GAP_HZ) & (f <= min(best_g + SIDE_SPAN_HZ, nyq))
    below, above = float(np.median(Ls[lo])), float(np.median(Ls[hi]))
    knee = below - min(KNEE_DB, (below - above) / 2)         # where the level has fallen 10 dB: the edge of the usable band
    win = (f >= best_g - SIDE_SPAN_HZ) & (f <= best_g + SIDE_SPAN_HZ)
    idx = np.nonzero(win & (Ls <= knee))[0]
    cutoff = float(f[idx[0]]) if len(idx) else float(best_g)
    rest = f > cutoff + SIDE_GAP_HZ
    if rest.sum() < 3:
        return None
    floor = float(np.median(Ls[rest]) - below)
    if -floor < CLIFF_DB - 5:        # content comes back above the drop: a notch or a gap, not a cut-off
        return None
    return Cliff(cutoff, best_d, floor)
