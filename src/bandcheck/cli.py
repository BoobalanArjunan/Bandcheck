from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

from . import __version__
from .check import check_file
from .report import text, write_csv

AUDIO_EXT = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aiff", ".aif"}


def find_audio(source: Path):
    if source.is_file():
        return [source]
    return sorted(p for p in source.rglob("*") if p.suffix.lower() in AUDIO_EXT and not p.name.startswith("._") and "__MACOSX" not in p.parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bandcheck", description="Find audio files whose real frequency range is lower than their sample rate claims.")
    ap.add_argument("--version", action="version", version=f"bandcheck {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check one file or every audio file in a folder")
    c.add_argument("source", type=Path)
    c.add_argument("--need-hz", type=float, help="fail files whose sound stops below this frequency (for example 8000 for 16 kHz speech models)")
    c.add_argument("--out", type=Path, help="write every verdict to this CSV")
    c.add_argument("--show-pass", action="store_true", help="also list files that passed")
    c.add_argument("--jobs", type=int, default=1, help="files analysed in parallel (default 1)")
    a = ap.parse_args(argv)

    if not a.source.exists():
        print(f"error: {a.source} not found", file=sys.stderr)
        return 2
    files = find_audio(a.source)
    if not files:
        print("error: no audio files found", file=sys.stderr)
        return 2
    job = partial(check_file, need_hz=a.need_hz)
    if a.jobs > 1:
        with ProcessPoolExecutor(a.jobs) as ex:
            vs = list(ex.map(job, files, chunksize=1))
    else:
        vs = [job(f) for f in files]
    print(text(vs, a.show_pass))
    if a.out:
        write_csv(a.out, vs)
    return 1 if any(v.level == "FAIL" for v in vs) else 0


if __name__ == "__main__":
    sys.exit(main())
