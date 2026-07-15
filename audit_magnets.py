#!/usr/bin/env python3
"""Audit an existing pr-search batch output: flag rows whose picks look wrong.

Re-scores every pick's title against the row's own English/Chinese title and
year using the *current* relevance() logic (which now demotes non-leading
single-word matches, whole-season packs, and year mismatches). A pick is
"weak" if its relevance falls below the threshold; a row is flagged when its
top pick is weak — i.e. the row most likely holds the wrong film.

Read-only. Prints a report; does not modify the CSV.

Usage:  python3 audit_magnets.py <magnets.csv> [--min-relevance 0.85]
"""
import csv
import importlib.util
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "prs", os.path.join(_here, "pr-search.py"))
prs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prs)


def main():
    args = sys.argv[1:]
    thr = 0.85
    if "--min-relevance" in args:
        i = args.index("--min-relevance")
        thr = float(args[i + 1]); del args[i:i + 2]
    if len(args) != 1:
        sys.exit("usage: python3 audit_magnets.py <magnets.csv> [--min-relevance F]")
    path = args[0]
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header = rows[0]

    # Column indices.
    def col(*names):
        low = [h.strip().lower().lstrip("﻿") for h in header]
        for n in names:
            if n in low:
                return low.index(n)
        return None
    en_i = col("titleen", "title_en", "english", "en")
    zh_i = col("title", "title_zh", "name", "电影名")
    yr_i = col("year", "年份", "年代")
    n = 1
    tgroups = []
    while f"title_{n}" in header:
        tgroups.append(header.index(f"title_{n}"))
        n += 1

    flagged = []
    for ri, r in enumerate(rows[1:], 1):
        def cell(i):
            return r[i].strip() if i is not None and i < len(r) else ""
        en = cell(en_i); zh = cell(zh_i); yr = cell(yr_i)
        query = en or zh
        picks = [r[ti] for ti in tgroups if ti < len(r) and r[ti].strip()]
        if not picks:
            continue  # no result at all — separate concern, skip here
        # Score the FIRST pick (the one that matters most).
        rel1 = prs.relevance(query, yr, picks[0])
        if rel1 < thr:
            # Also report the best relevance among all picks, to see if a good
            # one exists lower down.
            best = max(prs.relevance(query, yr, p) for p in picks)
            flagged.append((ri, query, yr, rel1, best, picks[0]))

    print(f"Audited {len(rows) - 1} rows · threshold {thr}\n"
          f"Flagged {len(flagged)} row(s) whose top pick looks wrong:\n")
    for ri, q, yr, rel1, best, top in flagged:
        print(f"  row {ri:3}  {q!r} ({yr})  top-rel={rel1:.2f} best={best:.2f}")
        print(f"           #1: {top[:70]}")


if __name__ == "__main__":
    main()
