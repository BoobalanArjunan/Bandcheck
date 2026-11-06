"""Compare the real bandwidth of a file with what its sample rate promises, and give a verdict."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

from .spectrum import Spectrum, find_cliff, load_mono, mean_spectrum

FULL_FRACTION = 0.90       # cut-off at or above this share of the Nyquist frequency: full band
FULL_HZ = 19500.0          # ... or at or above this frequency, whatever the sample rate
FAKE_FRACTION = 0.60       # cut-off below this share of Nyquist: the file holds much less than it claims
NATIVE_RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100)
RATE_LOW, RATE_HIGH = 0.90, 1.12     # the measured cut-off sits at 0.9 to 1.12 times the source's Nyquist (resampler filters)

OK, LIMITED, FAKE, UNSURE, ERROR = "OK", "LIMITED", "FAKE", "UNSURE", "ERROR"


@dataclass
class Verdict:
    file: str
    sample_rate: Optional[int]
    status: str
    cutoff_hz: Optional[float]
    reason: str
    likely_source: str = ""
    seconds: float = 0.0

    @property
    def level(self) -> str:
        return {OK: "PASS", LIMITED: "WARN", UNSURE: "REVIEW", FAKE: "FAIL", ERROR: "ERROR"}[self.status]

    @property
    def fraction(self) -> Optional[float]:
        return None if (self.cutoff_hz is None or not self.sample_rate) else self.cutoff_hz / (self.sample_rate / 2)


def source_guess(cutoff_hz: float, sample_rate: int) -> str:
    """One cut-off cannot tell an upsampled file from a lossy encode, so every candidate is listed."""
    rates = [r for r in NATIVE_RATES if r < sample_rate and RATE_LOW <= cutoff_hz / (r / 2) <= RATE_HIGH]
    parts = (["upsampled from " + " or ".join(f"{r} Hz" for r in rates)] if rates else []) + ["a lossy encoder's lowpass (MP3/AAC)"]
    return " or ".join(parts)


def judge(sp: Optional[Spectrum], file: str = "", sample_rate: Optional[int] = None, need_hz: Optional[float] = None) -> Verdict:
    if sp is None:
        return Verdict(file, sample_rate, UNSURE, None, "too short, silent or too few loud parts to measure a bandwidth")
    sr, nyq, secs = sp.sample_rate, sp.sample_rate / 2, sp.active_seconds
    c = find_cliff(sp)
    if c is None:
        return Verdict(file, sr, OK, None, "no sharp cut-off found", "", secs)
    frac = c.cutoff_hz / nyq
    kHz = c.cutoff_hz / 1000
    if need_hz is not None and c.cutoff_hz < need_hz:
        return Verdict(file, sr, FAKE, c.cutoff_hz, f"sound stops at {kHz:.1f} kHz, but {need_hz / 1000:g} kHz is required", source_guess(c.cutoff_hz, sr), secs)
    if frac >= FULL_FRACTION or c.cutoff_hz >= FULL_HZ:
        return Verdict(file, sr, OK, c.cutoff_hz, f"sound reaches {kHz:.1f} kHz ({100 * frac:.0f}% of the way to {nyq / 1000:g} kHz)", "", secs)
    if frac < FAKE_FRACTION:
        return Verdict(file, sr, FAKE, c.cutoff_hz, f"sound stops at {kHz:.1f} kHz, only {100 * frac:.0f}% of the way to {nyq / 1000:g} kHz", source_guess(c.cutoff_hz, sr), secs)
    return Verdict(file, sr, LIMITED, c.cutoff_hz, f"sound stops at {kHz:.1f} kHz ({100 * frac:.0f}% of the way to {nyq / 1000:g} kHz)", source_guess(c.cutoff_hz, sr), secs)


def check_file(path, need_hz: Optional[float] = None) -> Verdict:
    p = Path(path)
    try:
        x, sr = load_mono(p)
    except Exception as e:  # unreadable audio
        return Verdict(p.name, None, ERROR, None, f"could not read audio: {e}")
    return judge(mean_spectrum(x, sr), p.name, sr, need_hz)


def summary_by_rate(vs: List[Verdict]) -> List[dict]:
    """One row per sample rate: files, how many are flagged (WARN or FAIL), median cut-off among those with a cut-off."""
    rows = {}
    for v in vs:
        if v.sample_rate is None:
            continue
        r = rows.setdefault(v.sample_rate, {"rate": v.sample_rate, "files": 0, "flagged": 0, "cutoffs": []})
        r["files"] += 1
        r["flagged"] += v.level in ("WARN", "FAIL")
        if v.cutoff_hz:
            r["cutoffs"].append(v.cutoff_hz)
    out = []
    for r in sorted(rows.values(), key=lambda r: r["rate"]):
        out.append({"rate": r["rate"], "files": r["files"], "flagged": r["flagged"],
                    "median_cutoff_hz": float(np.median(r["cutoffs"])) if r["cutoffs"] else None})
    return out
