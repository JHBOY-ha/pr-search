#!/usr/bin/env python3
"""Re-rank an existing pr-search batch output in place, without re-searching.

Only the ordering of each row's top-N picks is recomputed, using the current
quality_of / cn_priority logic (pixel-dimension detection + domestic-priority
gated by resolution). Rows whose order doesn't change are left untouched. The
magnets/titles already in the CSV are reused — no network calls.

Usage:  python3 rerank_magnets.py <magnets.csv>
Writes a .bak backup, then rewrites the file atomically.
"""
import csv
import importlib.util
import os
import sys

# Load the pr-search module to reuse its scoring functions.
_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "prs", os.path.join(_here, "pr-search.py"))
prs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prs)


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python3 rerank_magnets.py <magnets.csv>")
    path = sys.argv[1]
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        sys.exit("empty CSV")
    header = rows[0]

    # Locate the magnet_N / quality_N / seeders_N / title_N column groups.
    groups = []  # list of (magnet_i, quality_i, seeders_i, title_i)
    n = 1
    while f"magnet_{n}" in header:
        groups.append((header.index(f"magnet_{n}"), header.index(f"quality_{n}"),
                       header.index(f"seeders_{n}"), header.index(f"title_{n}")))
        n += 1
    if not groups:
        sys.exit("no magnet_N columns found — is this a pr-search output?")

    # Query columns, to recompute relevance offline.
    def col(*names):
        low = [h.strip().lower().lstrip("﻿") for h in header]
        for n_ in names:
            if n_ in low:
                return low.index(n_)
        return None
    en_i = col("titleen", "title_en", "english", "en")
    zh_i = col("title", "title_zh", "name", "电影名")
    yr_i = col("year", "年份", "年代")

    # Back up the ORIGINAL file before we mutate anything.
    bak = path + ".bak"
    if not os.path.exists(bak):
        with open(bak, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(rows)

    def rank_key(pick, query, year):
        """Sort key: (a) low-relevance picks (wrong film — subtitle contains the
        query words, wrong season/episode, year mismatch) sink to the bottom;
        (b) among relevant ones, cn-priority first, then quality, then seeders."""
        title = pick["title"]
        fake = {"title": title, "size": 0}
        rel = prs.relevance(query, year, title)
        q = prs.quality_of(fake)
        cn_pri = prs.is_domestic(fake) and q["resolution"] in prs._CN_PRIORITY_RES
        s = pick["seeders"]
        seed = int(s) if s.strip().isdigit() else -1
        # relevance bucket first (>=0.85 good), then the usual ordering.
        return (0 if rel >= 0.85 else 1, 0 if cn_pri else 1, -q["score"], -seed)

    def cell(row, i):
        return row[i].strip() if i is not None and i < len(row) else ""

    changed = 0
    for row in rows[1:]:
        query = cell(row, en_i) or cell(row, zh_i)
        year = cell(row, yr_i)
        # Gather non-empty picks for this row.
        picks = []
        for (mi, qi, si, ti) in groups:
            if mi < len(row) and row[mi].strip():
                picks.append({"magnet": row[mi], "quality": row[qi],
                              "seeders": row[si], "title": row[ti]})
        if len(picks) < 2:
            continue  # nothing to reorder
        reordered = sorted(picks, key=lambda p: rank_key(p, query, year))
        if reordered == picks:
            continue
        changed += 1
        # Write the reordered picks back, padding remaining groups empty.
        for slot, (mi, qi, si, ti) in enumerate(groups):
            if slot < len(reordered):
                p = reordered[slot]
                row[mi], row[qi], row[si], row[ti] = (
                    p["magnet"], p["quality"], p["seeders"], p["title"])
            else:
                row[mi] = row[qi] = row[si] = row[ti] = ""

    # Atomic rewrite.
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    os.replace(tmp, path)
    print(f"Re-ranked {changed} row(s) → {path}  (backup: {bak})")


if __name__ == "__main__":
    main()
