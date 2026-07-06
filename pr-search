#!/usr/bin/env python3
"""pr-search — command-line torrent search via a local Prowlarr instance.

Examples:
  pr-search ubuntu 24.04                 # search all indexers, sorted by seeders
  pr-search -n 30 debian                 # show up to 30 results
  pr-search -i 5,3 nyaa one piece        # limit to indexer ids 5 and 3
  pr-search -c 2000 dune                 # only category 2000 (Movies)
  pr-search --list-indexers              # list configured indexers and exit
  pr-search -m ubuntu | pbcopy           # print only magnet links (pipe-friendly)
  pr-search --copy 2 ubuntu              # copy the magnet of result #2 to clipboard

Env overrides:
  PROWLARR_URL   (default http://localhost:9696)
  PROWLARR_KEY   (default: read from Prowlarr's config.xml)
"""
import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DEFAULT_URL = os.environ.get("PROWLARR_URL", "http://localhost:9696")
CONFIG_XML = os.path.expanduser(
    "~/Library/Application Support/Prowlarr/config.xml"
)

# ---- ANSI colors (disabled when not a tty) --------------------------------
_tty = sys.stdout.isatty()
def c(code, s):
    return f"\033[{code}m{s}\033[0m" if _tty else s
DIM, BOLD, GREEN, YELLOW, CYAN, RED = "2", "1", "32", "33", "36", "31"


def get_api_key():
    key = os.environ.get("PROWLARR_KEY")
    if key:
        return key
    try:
        root = ET.parse(CONFIG_XML).getroot()
        el = root.find("ApiKey")
        if el is not None and el.text:
            return el.text.strip()
    except Exception:
        pass
    sys.exit(
        "Could not find API key. Set PROWLARR_KEY or ensure config.xml exists at:\n  "
        + CONFIG_XML
    )


def api_get(path, key, params=None):
    url = f"{DEFAULT_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"X-Api-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from Prowlarr: {e.read().decode(errors='replace')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach Prowlarr at {DEFAULT_URL}: {e.reason}")


# ---- minimal bencode decoder (stdlib only) --------------------------------
def _bdecode(data, pos=0):
    """Decode one bencoded value starting at `pos`; return (value, next_pos)."""
    ch = data[pos:pos + 1]
    if ch == b"i":  # integer: i<digits>e
        end = data.index(b"e", pos)
        return int(data[pos + 1:end]), end + 1
    if ch == b"l":  # list: l...e
        pos += 1
        out = []
        while data[pos:pos + 1] != b"e":
            v, pos = _bdecode(data, pos)
            out.append(v)
        return out, pos + 1
    if ch == b"d":  # dict: d<key><val>...e
        pos += 1
        out = {}
        while data[pos:pos + 1] != b"e":
            k, pos = _bdecode(data, pos)
            v, pos = _bdecode(data, pos)
            out[k] = v
        return out, pos + 1
    if ch.isdigit():  # byte string: <len>:<bytes>
        colon = data.index(b":", pos)
        length = int(data[pos:colon])
        start = colon + 1
        return data[start:start + length], start + length
    raise ValueError(f"bad bencode at {pos}")


def _bencode(v):
    if isinstance(v, int):
        return b"i" + str(v).encode() + b"e"
    if isinstance(v, bytes):
        return str(len(v)).encode() + b":" + v
    if isinstance(v, list):
        return b"l" + b"".join(_bencode(x) for x in v) + b"e"
    if isinstance(v, dict):
        items = sorted(v.items())
        return b"d" + b"".join(_bencode(k) + _bencode(val) for k, val in items) + b"e"
    raise TypeError(type(v))


def torrent_bytes_to_magnet(raw, fallback_name=""):
    """Parse a .torrent blob into a minimal magnet: link (infohash + name)."""
    meta, _ = _bdecode(raw)
    info = meta[b"info"]
    infohash = hashlib.sha1(_bencode(info)).hexdigest()
    name = info.get(b"name", b"").decode(errors="replace") or fallback_name
    parts = [f"xt=urn:btih:{infohash}"]
    if name:
        parts.append("dn=" + urllib.parse.quote(name))
    return "magnet:?" + "&".join(parts)


def slim_magnet(magnet):
    """Strip a magnet down to its essential parts: xt (infohash) and dn (name).

    Trackers (&tr=) are dropped — modern clients find peers via DHT/PEX from
    the infohash alone, so the long tracker list is optional noise.
    """
    if not magnet.startswith("magnet:?"):
        return magnet
    xt = dn = None
    for kv in magnet[len("magnet:?"):].split("&"):
        if kv.startswith("xt=") and xt is None:
            xt = kv
        elif kv.startswith("dn=") and dn is None:
            dn = kv
    parts = [p for p in (xt, dn) if p]
    return "magnet:?" + "&".join(parts) if parts else magnet


def resolve_magnet(r, key):
    """Return a slim magnet: link, fetching+parsing the .torrent if needed."""
    mag = magnet_of(r)
    if mag.startswith("magnet:"):
        return slim_magnet(mag)
    # proxy URL -> download .torrent -> derive magnet
    proxy = r.get("magnetUrl") or r.get("downloadUrl")
    if not proxy:
        return mag
    req = urllib.request.Request(proxy, headers={"X-Api-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
        if body[:1] == b"d":  # looks like bencode
            return torrent_bytes_to_magnet(body, r.get("title", ""))
    except Exception:
        pass
    return mag  # give up, return the proxy url


def human_size(n):
    n = n or 0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def human_age(hours):
    if hours is None:
        return "?"
    if hours < 24:
        return f"{hours:.0f}h"
    days = hours / 24
    if days < 30:
        return f"{days:.0f}d"
    if days < 365:
        return f"{days/30:.0f}mo"
    return f"{days/365:.1f}y"


def magnet_of(r):
    """Return a real magnet: link if possible, else the Prowlarr download URL."""
    guid = r.get("guid") or ""
    if guid.startswith("magnet:"):
        return guid
    mu = r.get("magnetUrl") or ""
    if mu.startswith("magnet:"):
        return mu
    h = r.get("infoHash")
    if h:
        dn = urllib.parse.quote(r.get("title") or "")
        return f"magnet:?xt=urn:btih:{h}&dn={dn}"
    return mu or r.get("downloadUrl") or ""


# ---- quality scoring (Prowlarr has no bitrate field; parse from title) ----
# Prowlarr returns no resolution/source/codec/bitrate — the only signal is the
# release title text plus seeders and file size. We parse the title for the
# usual scene tags and combine them into a single weighted score.
RES_SCORES = [
    (re.compile(r"\b(2160p|4k|uhd)\b", re.I), 4, "2160p"),
    (re.compile(r"\b1080p\b", re.I), 3, "1080p"),
    (re.compile(r"\b720p\b", re.I), 2, "720p"),
    (re.compile(r"\b(480p|576p|sd)\b", re.I), 1, "480p"),
]
SOURCE_SCORES = [
    (re.compile(r"\bremux\b", re.I), 6, "Remux"),
    (re.compile(r"\b(blu-?ray|bdrip|bdremux)\b", re.I), 5, "BluRay"),
    (re.compile(r"\bweb-?(dl|rip)\b", re.I), 4, "WEB"),
    (re.compile(r"\bhdtv\b", re.I), 3, "HDTV"),
    (re.compile(r"\b(dvdrip|dvd)\b", re.I), 2, "DVD"),
    (re.compile(r"\b(cam|ts|telesync|hdcam|hdts)\b", re.I), 0, "CAM"),
]
CODEC_SCORES = [
    (re.compile(r"\b(av1)\b", re.I), 3, "AV1"),
    (re.compile(r"\b(x265|h\.?265|hevc)\b", re.I), 2, "x265"),
    (re.compile(r"\b(x264|h\.?264|avc)\b", re.I), 1, "x264"),
]


def _match_first(title, table):
    for rx, score, label in table:
        if rx.search(title):
            return score, label
    return 0, ""


def quality_of(r):
    """Derive resolution/source/codec + a weighted score from a result."""
    t = r.get("title") or ""
    res_s, res_l = _match_first(t, RES_SCORES)
    src_s, src_l = _match_first(t, SOURCE_SCORES)
    cod_s, cod_l = _match_first(t, CODEC_SCORES)
    seeders = r.get("seeders") or 0
    size_gb = (r.get("size") or 0) / 1e9
    # Weighted: resolution dominates, then source/codec, then a capped seeders
    # contribution so a mega-seeded SD rip can't outrank a 1080p one. Tiny
    # files (likely fake/samples) are penalised.
    seed_pts = min(seeders, 200) * 0.5
    penalty = -30 if size_gb and size_gb < 0.2 else 0
    score = res_s * 25 + src_s * 8 + cod_s * 5 + seed_pts + penalty
    return {
        "score": round(score, 1),
        "resolution": res_l, "source": src_l, "codec": cod_l,
    }


# ---- title relevance (Prowlarr has no genre; match title tokens instead) ---
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "and", "in", "on", "to", "part"}


def _tokens(s):
    return [w for w in _WORD_RE.findall((s or "").lower()) if w not in _STOP]


_EPISODE_RE = re.compile(
    r"(\bS\d{1,2}E\d{1,2}\b|\bEP?\s?\d{1,3}\b|\s-\s\d{1,3}\b|"
    r"\b\d{1,3}\s?集\b|\[\d{1,3}\])", re.I)


def _contiguous_run(q, toks):
    """Longest run of query tokens `q` appearing in order & contiguously in
    the title token list `toks`, as a fraction of len(q)."""
    if not q:
        return 0.0
    best = 0
    for start in range(len(toks)):
        run = 0
        while (run < len(q) and start + run < len(toks)
               and toks[start + run] == q[run]):
            run += 1
        best = max(best, run)
    return best / len(q)


def relevance(query_en, year, title):
    """How well a result title matches the wanted film (0..1).

    Uses the longest *contiguous, in-order* run of query tokens — so
    "21 Grams" matches "21.Grams.2003" fully but only half-matches an anime
    episode "... - 21". A matching year nudges it up; an episode/season
    marker (SxxExx, "- 21", "[12]") pushes it down, since we want movies.
    """
    q = _tokens(query_en)
    if not q:
        return 0.0
    toks = _tokens(title)
    score = _contiguous_run(q, toks)
    if year and str(year) in (title or ""):
        score = min(1.0, score + 0.2)
    if _EPISODE_RE.search(title or ""):
        score *= 0.4
    return score


def list_indexers(key):
    data = api_get("/api/v1/indexer", key)
    print(c(BOLD, f"{'ID':>4}  {'NAME':<24} {'PROTO':<8} ENABLED"))
    for i in sorted(data, key=lambda x: x.get("id", 0)):
        en = c(GREEN, "yes") if i.get("enable") else c(RED, "no")
        print(f"{i.get('id'):>4}  {i.get('name',''):<24} {i.get('protocol',''):<8} {en}")


def search(key, query, indexer_ids=None, categories=None, fetch=150):
    """Run one Prowlarr search; return the raw result list."""
    params = {"query": query, "type": "search", "limit": fetch}
    if indexer_ids:
        params["indexerIds"] = indexer_ids
    if categories:
        params["categories"] = categories
    return api_get("/api/v1/search", key, params)


# ---- batch CSV processing --------------------------------------------------
def _resolve_col(header, spec, default_names):
    """Map a --xxx-col spec (name or 1-based index) to a 0-based column index.

    Falls back to matching any of `default_names` against the header. Returns
    None if not found (batch mode then treats that field as empty).
    """
    if spec:
        if spec.isdigit():
            return int(spec) - 1
        low = [h.strip().lower() for h in header]
        if spec.lower() in low:
            return low.index(spec.lower())
        sys.exit(f"column '{spec}' not found in header: {header}")
    low = [h.strip().lower().lstrip("﻿") for h in header]
    for name in default_names:
        if name in low:
            return low.index(name)
    return None


def batch(args, key):
    with open(args.batch, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        sys.exit("CSV is empty.")

    has_header = not args.no_header
    header = rows[0] if has_header else [f"col{i+1}" for i in range(len(rows[0]))]
    data = rows[1:] if has_header else rows

    en_i = _resolve_col(header, args.en_col, ["title_en", "english", "en"])
    zh_i = _resolve_col(header, args.zh_col, ["title", "title_zh", "name", "电影名"])
    yr_i = _resolve_col(header, args.year_col, ["year", "年份", "年代"])
    if en_i is None and zh_i is None:
        sys.exit("Could not find a title column. Use --en-col / --zh-col to set it "
                 f"(header seen: {header}).")

    indexer_ids = args.indexer_ids.split(",") if args.indexer_ids else None
    categories = args.categories.split(",") if args.categories else ["2000"]
    topn = args.top
    min_seeders = args.min_seeders if args.min_seeders else 5  # batch default

    # Build output header: original columns + magnet_N / info_N triples.
    out_header = list(header)
    for n in range(1, topn + 1):
        out_header += [f"magnet_{n}", f"quality_{n}", f"seeders_{n}", f"title_{n}"]

    out_rows = []
    for ri, row in enumerate(data, 1):
        row = list(row) + [""] * (len(header) - len(row))  # pad short rows

        def cell(i):
            return row[i].strip() if i is not None and i < len(row) else ""

        title_en = cell(en_i)
        title_zh = cell(zh_i)
        year = cell(yr_i)
        label = title_en or title_zh or f"row{ri}"

        # Query: prefer English name + year (best hit-rate on public trackers).
        primary = title_en or title_zh
        query = f"{primary} {year}".strip() if year else primary
        log_pre = f"[{ri}/{len(data)}] {label!r:.50}"

        if not primary:
            print(f"{log_pre}  — no title, skipped", file=sys.stderr)
            out_rows.append(row + [""] * (topn * 4))
            continue

        try:
            raw = search(key, query, indexer_ids, categories)
        except SystemExit:
            raise
        except Exception as e:
            print(f"{log_pre}  — search error: {e}", file=sys.stderr)
            out_rows.append(row + [""] * (topn * 4))
            continue

        # Fallback: if EN+year found nothing, retry with EN alone, then ZH.
        if not raw and year and title_en:
            raw = search(key, title_en, indexer_ids, categories)
        if not raw and title_zh and title_zh != primary:
            raw = search(key, f"{title_zh} {year}".strip(), indexer_ids, categories)

        # Score every candidate, filter by seeders and title relevance.
        cand = []
        for r in raw:
            seeders = r.get("seeders") or 0
            if seeders < min_seeders:
                continue
            rel = relevance(title_en or title_zh, year, r.get("title"))
            if rel < args.min_relevance:
                continue
            q = quality_of(r)
            # Relevance is a multiplier, not an additive term: a weak title
            # match (e.g. an anime "- 21" for "21 Grams") can't be rescued by
            # a high seeder count. Full matches keep their quality score.
            r["_rank"] = q["score"] * rel
            r["_q"] = q
            r["_rel"] = rel
            cand.append(r)

        cand.sort(key=lambda x: (-x["_rank"], -(x.get("seeders") or 0)))
        picks = cand[:topn]

        extra = []
        for r in picks:
            mag = resolve_magnet(r, key)
            q = r["_q"]
            qtag = "/".join(x for x in (q["resolution"], q["source"], q["codec"]) if x)
            extra += [mag, qtag, str(r.get("seeders") or 0), r.get("title") or ""]
        extra += [""] * ((topn - len(picks)) * 4)  # pad to fixed width
        out_rows.append(row + extra)

        status = (f"{len(picks)} pick(s), best="
                  f"{picks[0]['_q']['resolution'] or '?'} "
                  f"S:{picks[0].get('seeders')}" if picks else "no match")
        print(f"{log_pre}  — {len(cand)} candidates → {status}")

    out_path = args.out or (os.path.splitext(args.batch)[0] + "_magnets.csv")
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(out_header)
        w.writerows(out_rows)
    print(f"\nWrote {len(out_rows)} rows → {out_path}")


def main():
    ap = argparse.ArgumentParser(
        prog="pr-search", description="Search torrents via local Prowlarr."
    )
    ap.add_argument("query", nargs="*", help="search terms")
    ap.add_argument("-n", "--limit", type=int, default=25, help="max results (default 25)")
    ap.add_argument("-i", "--indexers", dest="indexer_ids",
                    help="comma-separated indexer ids to search")
    ap.add_argument("-c", "--categories", help="comma-separated category ids")
    ap.add_argument("-s", "--sort", choices=["seeders", "size", "age"],
                    default="seeders", help="sort key (default seeders)")
    ap.add_argument("--min-seeders", type=int, default=0, help="filter out low-seed results")
    ap.add_argument("-m", "--magnets", action="store_true",
                    help="print only magnet links, one per line")
    ap.add_argument("--copy", type=int, metavar="N",
                    help="copy magnet of result #N to clipboard (macOS pbcopy)")
    ap.add_argument("--save", type=int, metavar="N",
                    help="download result #N's .torrent file to the current directory")
    ap.add_argument("--json", action="store_true", help="dump raw JSON results")
    ap.add_argument("--list-indexers", action="store_true", help="list indexers and exit")

    b = ap.add_argument_group("batch mode (process a CSV of film metadata)")
    b.add_argument("--batch", metavar="CSV", help="input CSV to process row by row")
    b.add_argument("--out", metavar="CSV", help="output path (default: <input>_magnets.csv)")
    b.add_argument("--top", type=int, default=3, help="magnets to keep per film (default 3)")
    b.add_argument("--min-relevance", type=float, default=0.5,
                   help="min title-token match 0..1 to accept a result (default 0.5)")
    b.add_argument("--no-header", action="store_true",
                   help="input CSV has no header row")
    b.add_argument("--en-col", help="English-title column (name or 1-based index)")
    b.add_argument("--zh-col", help="Chinese-title column (name or 1-based index)")
    b.add_argument("--year-col", help="year column (name or 1-based index)")
    args = ap.parse_args()

    key = get_api_key()

    if args.list_indexers:
        list_indexers(key)
        return

    if args.batch:
        batch(args, key)
        return

    if not args.query:
        ap.error("no search terms given (use --list-indexers to see indexers)")

    # Prowlarr returns up to `limit` per indexer; fetch a bit extra for filtering.
    params = {"query": " ".join(args.query), "type": "search",
              "limit": max(args.limit * 3, 50)}
    if args.indexer_ids:
        params["indexerIds"] = args.indexer_ids.split(",")
    if args.categories:
        params["categories"] = args.categories.split(",")

    results = api_get("/api/v1/search", key, params)

    if args.min_seeders:
        results = [r for r in results if (r.get("seeders") or 0) >= args.min_seeders]

    keymap = {
        "seeders": lambda r: -(r.get("seeders") or 0),
        "size": lambda r: -(r.get("size") or 0),
        "age": lambda r: (r.get("ageHours") if r.get("ageHours") is not None else 1e12),
    }
    results.sort(key=keymap[args.sort])
    results = results[: args.limit]

    if not results:
        print("No results.", file=sys.stderr)
        sys.exit(1)

    if args.copy is not None:
        idx = args.copy - 1
        if not (0 <= idx < len(results)):
            sys.exit(f"--copy index out of range (1..{len(results)})")
        mag = resolve_magnet(results[idx], key)
        subprocess.run(["pbcopy"], input=mag.encode(), check=True)
        kind = "magnet" if mag.startswith("magnet:") else "proxy url"
        print(f"Copied {kind} of #{args.copy}: {results[idx].get('title')}")
        return

    if args.save is not None:
        idx = args.save - 1
        if not (0 <= idx < len(results)):
            sys.exit(f"--save index out of range (1..{len(results)})")
        r = results[idx]
        proxy = r.get("magnetUrl") or r.get("downloadUrl") or ""
        mag = magnet_of(r)
        if mag.startswith("magnet:") and not proxy.startswith("http"):
            sys.exit("This result is a magnet link, not a .torrent file. Use --copy.")
        req = urllib.request.Request(proxy, headers={"X-Api-Key": key})
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
        safe = "".join(ch if ch.isalnum() or ch in "-._ " else "_"
                       for ch in (r.get("title") or "download"))[:150]
        path = os.path.join(os.getcwd(), safe + ".torrent")
        with open(path, "wb") as f:
            f.write(body)
        print(f"Saved: {path}")
        return

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if args.magnets:
        for r in results:
            print(resolve_magnet(r, key))
        return

    # Pretty table
    for n, r in enumerate(results, 1):
        seed = r.get("seeders") or 0
        leech = r.get("leechers") or 0
        seed_col = GREEN if seed >= 10 else (YELLOW if seed >= 1 else RED)
        title = r.get("title") or ""
        print(f"{c(BOLD, f'{n:>3}.')} {title}")
        meta = (
            f"     {c(seed_col, f'S:{seed:<5}')} {c(DIM, f'L:{leech:<5}')} "
            f"{c(CYAN, human_size(r.get('size')) ):<18} "
            f"{c(DIM, human_age(r.get('ageHours')) ):<12} "
            f"{c(DIM, r.get('indexer',''))}"
        )
        print(meta)
        mag = magnet_of(r)
        if mag.startswith("magnet:"):
            print(f"     {c(GREEN, 'magnet')} {c(DIM, slim_magnet(mag))}")
        else:
            print(f"     {c(YELLOW, 'proxy ')} {c(DIM, '(resolve with --copy/--save)')}")
    print(c(DIM, f"\n{len(results)} results · sort={args.sort} · "
                 f"copy one with: pr-search --copy N {' '.join(args.query)}"))


if __name__ == "__main__":
    main()
