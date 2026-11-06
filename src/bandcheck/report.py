from __future__ import annotations

import csv
from collections import Counter
from typing import List

from .check import Verdict, summary_by_rate


def summary_line(vs: List[Verdict]) -> str:
    c = Counter(v.level for v in vs)
    return (f"{len(vs)} files: {c['PASS']} pass, {c['WARN']} warn (band-limited), {c['REVIEW']} need a look, "
            f"{c['FAIL']} fail (much less bandwidth than claimed), {c['ERROR']} unreadable")


def text(vs: List[Verdict], show_pass: bool = False) -> str:
    L = []
    for v in vs:
        if v.level == "PASS" and not show_pass:
            continue
        src = f"  likely: {v.likely_source}" if v.likely_source else ""
        L.append(f"{v.level:6} {v.file}  {v.sample_rate or '-'} Hz  {v.reason}{src}")
    rows = summary_by_rate(vs)
    if rows:
        L += ["", "By sample rate:"]
        for r in rows:
            mc = f", median cut-off {r['median_cutoff_hz'] / 1000:.1f} kHz" if r["median_cutoff_hz"] else ""
            L.append(f"  {r['rate']} Hz: {r['files']} files, {r['flagged']} flagged{mc}")
    L += ["", summary_line(vs)]
    return "\n".join(L)


def write_csv(path, vs: List[Verdict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "sample_rate", "cutoff_hz", "cutoff_fraction", "verdict", "reason", "likely_source", "seconds_analysed"])
        for v in vs:
            w.writerow([v.file, v.sample_rate or "", "" if v.cutoff_hz is None else round(v.cutoff_hz, 1),
                        "" if v.fraction is None else round(v.fraction, 3), v.level, v.reason, v.likely_source, round(v.seconds, 1)])
