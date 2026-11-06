"""Real-data check for bandcheck. Needs a folder of REAL audio files (for example LibriSpeech, or music you may use).

    python scripts/real_data_check.py --audio-dir ~/LibriSpeech/dev-clean --out real_check
    python scripts/real_data_check.py --audio-dir ~/music --out real_check --mp3      # also plant MP3 encodes (needs ffmpeg)

It answers:
  1. WHAT BANDCHECK SAYS ABOUT YOUR FILES AS THEY ARE: PASS / WARN / FAIL / REVIEW counts, the cut-off found per sample rate,
     and the flagged files. A flagged original is not automatically a false alarm: LibriSpeech, for example, was made from
     MP3 audiobooks, so some of its files may truly be band-limited. Look at a few flagged files in a spectrogram viewer
     and decide for yourself. This is the check that matters most.
  2. PLANTED UPSAMPLING: for files that PASS, it makes copies downsampled to 8, 11.025 and 16 kHz and brought back to the
     original rate (so the real bandwidth is KNOWN), and counts how many BandCheck flags and how close its cut-off is.
  3. (--mp3) MP3 COPIES at 64 and 128 kbps: the cut-offs BandCheck finds (the encoder's lowpass depends on the encoder).
Your original files are never changed. Copies go under <out>/planted/. Writes <out>/results.md and <out>/verdicts.csv.
"""
from __future__ import annotations

import argparse
import random
import shutil
import statistics
import subprocess
import sys
from collections import Counter
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from bandcheck.check import check_file, summary_by_rate
from bandcheck.cli import find_audio
from bandcheck.report import write_csv

RATES = (8000, 11025, 16000)


def resampled_roundtrip(x, sr, low):
    g = gcd(sr, low)
    y = resample_poly(x, low // g, sr // g)
    z = resample_poly(y, sr // g, low // g)
    return z[: len(x)]


def mp3_roundtrip(src: Path, dst: Path, kbps: int) -> bool:
    tmp = dst.with_suffix(".mp3")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:a", "libmp3lame", "-b:a", f"{kbps}k", str(tmp)], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), str(dst)], check=True)
        return True
    except Exception:
        return False
    finally:
        tmp.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio-dir", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=200, help="files to use (default 200)")
    ap.add_argument("--out", type=Path, default=Path("real_check"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mp3", action="store_true", help="also plant MP3 copies (needs ffmpeg with libmp3lame)")
    a = ap.parse_args()
    files = find_audio(a.audio_dir)
    if len(files) < 10:
        sys.exit(f"only {len(files)} audio files found; need at least 10")
    rng = random.Random(a.seed)
    rng.shuffle(files)
    files = files[: a.limit]
    a.out.mkdir(parents=True, exist_ok=True)
    pl = a.out / "planted"
    pl.mkdir(exist_ok=True)
    if a.mp3 and not shutil.which("ffmpeg"):
        sys.exit("--mp3 needs ffmpeg on the PATH")

    base = []
    for i, f in enumerate(files, 1):
        base.append(check_file(f))
        if i % 25 == 0:
            print(f"  originals {i}/{len(files)}", flush=True)
    write_csv(a.out / "verdicts.csv", base)
    c = Counter(v.level for v in base)

    lines = ["# bandcheck real-data check", "", f"Files used: {len(files)} from `{a.audio_dir}`", "",
             "## 1. The files as they are", "",
             f"PASS {c['PASS']}, WARN {c['WARN']}, FAIL {c['FAIL']}, REVIEW {c['REVIEW']}, ERROR {c['ERROR']}", "",
             "| sample rate | files | flagged (WARN or FAIL) | median cut-off |", "|---|---|---|---|"]
    for r in summary_by_rate(base):
        mc = f"{r['median_cutoff_hz'] / 1000:.1f} kHz" if r["median_cutoff_hz"] else "none found"
        lines.append(f"| {r['rate']} Hz | {r['files']} | {r['flagged']} | {mc} |")
    flagged = [v for v in base if v.level in ("WARN", "FAIL")][:20]
    if flagged:
        lines += ["", "First flagged files (open a few in a spectrogram viewer and check by eye):", ""]
        lines += [f"- {v.level} {v.file}: {v.reason}" for v in flagged]

    lines += ["", "## 2. Planted upsampling (known true bandwidth)", "",
              "| copy | files tried | flagged (WARN/FAIL) | FAIL | median cut-off / true bandwidth |", "|---|---|---|---|---|"]
    passed = [(f, v) for f, v in zip(files, base) if v.level == "PASS"]
    for low in RATES:
        tried = flagged_n = fail_n = 0
        ratios = []
        for f, v in passed:
            if not v.sample_rate or v.sample_rate <= low:
                continue
            x, sr = sf.read(str(f), dtype="float64", always_2d=True)
            x = x.mean(axis=1)
            dst = pl / f"{f.stem}__from{low}.wav"
            sf.write(str(dst), np.clip(resampled_roundtrip(x, sr, low), -1, 1), sr, subtype="PCM_16")
            pv = check_file(dst)
            tried += 1
            flagged_n += pv.level in ("WARN", "FAIL")
            fail_n += pv.level == "FAIL"
            if pv.cutoff_hz:
                ratios.append(pv.cutoff_hz / (low / 2))
        med = f"{statistics.median(ratios):.2f}" if ratios else "n/a"
        lines.append(f"| from {low} Hz | {tried} | {flagged_n} | {fail_n} | {med} |")
    lines += ["", "The last column is 1.00 when the cut-off sits exactly at the source's Nyquist frequency; resampler filters put it a little above."]

    if a.mp3:
        lines += ["", "## 3. MP3 copies (cut-off found; the true lowpass depends on the encoder)", "",
                  "| bitrate | files tried | flagged (WARN/FAIL) | median cut-off |", "|---|---|---|---|"]
        for kbps in (64, 128):
            tried = flagged_n = 0
            cuts = []
            for f, v in passed:
                dst = pl / f"{f.stem}__mp3_{kbps}.wav"
                if not mp3_roundtrip(f, dst, kbps):
                    continue
                pv = check_file(dst)
                tried += 1
                flagged_n += pv.level in ("WARN", "FAIL")
                if pv.cutoff_hz:
                    cuts.append(pv.cutoff_hz)
            med = f"{statistics.median(cuts) / 1000:.1f} kHz" if cuts else "none found"
            lines.append(f"| {kbps} kbps | {tried} | {flagged_n} | {med} |")

    (a.out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
