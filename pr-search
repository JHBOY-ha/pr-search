#!/usr/bin/env python3
"""pr-search — command-line torrent search via a local Prowlarr instance.

Examples:
  pr-search ubuntu 24.04                 # search all indexers, sorted by seeders
  pr-search -n 30 debian                 # show up to 30 results
  pr-search -i 5,3 nyaa one piece        # limit to indexer ids 5 and 3
  pr-search -c 2000 dune                 # only category 2000 (Movies)
  pr-search 帕丁顿熊 2014                   # default: domestic-first, no remux/disc
  pr-search --remux --no-cn-first dune   # opt out of the two defaults
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


# ---- seeder-count reliability --------------------------------------------
# Some indexers are magnet/DHT aggregators (52BT, BTdirectory, Magnet Cat …)
# that don't track a swarm, so they stamp every result with a constant
# placeholder (seeders=1). Sorting/filtering on that number is meaningless and,
# worse, batch mode's --min-seeders would drop every result from such a site.
# We detect it per-indexer within a result set: if an indexer returns several
# results whose seeder counts never vary and sit at <=1, treat its seeder
# numbers as UNKNOWN rather than real.
def flag_unreliable_seeders(results):
    """Tag results whose indexer reports a constant placeholder seeder count.

    Mutates each result in place: sets r["_seed_unknown"] = True/False.
    """
    by_indexer = {}
    for r in results:
        by_indexer.setdefault(r.get("indexerId"), []).append(r)
    for group in by_indexer.values():
        seeds = [g.get("seeders") for g in group if g.get("seeders") is not None]
        # Need a few samples to conclude "never varies"; a single result that
        # happens to have 1 seeder is not evidence of a broken indexer.
        degenerate = (len(seeds) >= 3 and len(set(seeds)) == 1 and seeds[0] <= 1)
        for g in group:
            g["_seed_unknown"] = degenerate


def seeders_display(r):
    """Seeder count for display: None when the indexer's number is unreliable."""
    if r.get("_seed_unknown"):
        return None
    return r.get("seeders")


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
    # When the indexer's seeder count is a placeholder (see
    # flag_unreliable_seeders), give a small neutral credit instead of scoring
    # it as "1 seeder" — otherwise every result from an aggregator site is
    # unfairly ranked as near-dead.
    if r.get("_seed_unknown"):
        seed_pts = 20  # neutral: ~40 real seeders' worth, neither boosted nor buried
    else:
        seed_pts = min(seeders, 200) * 0.5
    penalty = -30 if size_gb and size_gb < 0.2 else 0
    score = res_s * 25 + src_s * 8 + cod_s * 5 + seed_pts + penalty
    return {
        "score": round(score, 1),
        "resolution": res_l, "source": src_l, "codec": cod_l,
    }


# ---- subtitle handling & origin (parsed from the release title) -----------
# The user wants to (a) skip releases with *hardcoded* subtitles (内嵌/硬字幕 —
# burned into the picture, can't be turned off) in favour of soft/muxed/
# external subs, and (b) prefer *domestic* (Chinese) releases. The release
# title is the only signal Prowlarr gives us, so these are heuristics, not
# guarantees.
_HARDSUB_RE = re.compile(r"内嵌|硬字幕|硬字|内嵌中字", re.I)
_SOFTSUB_RE = re.compile(
    r"内封|软字幕|外挂|外掛|特效字幕|简繁英|简繁双语|双语字幕|简繁中字|"
    r"简繁|繁简|chs&?eng|cht&?eng|ass字幕", re.I)
_CHSUB_RE = re.compile(r"中字|中英|中文字幕|国语中字|简体中文|繁体中文|简中|繁中|双字", re.I)
# A "TC/CAM/枪版" release that carries Chinese subs almost always has them
# burned in; a BluRay/WEB/Remux almost always ships them as a selectable track.
# T[SC] is matched with letter-boundaries (not \b) so "TC1080P"/"HDTS" hit but
# "watch"/"TrueHD" don't.
_CAMISH_RE = re.compile(
    r"(?<![a-z])(?:hd)?t[sc](?![a-z])|抢先|枪版|槍版|偷拍|喳", re.I)


def subtitle_of(r):
    """Classify a release's subtitle handling from its title.

    Returns one of:
      'hard' — subtitles burned into the picture (avoid)
      'soft' — muxed/external/selectable subtitles (prefer)
      'cn'   — has Chinese subs but the type is unclear
      ''     — no subtitle signal in the title
    """
    t = r.get("title") or ""
    if _HARDSUB_RE.search(t):
        return "hard"
    if _SOFTSUB_RE.search(t):
        return "soft"
    if _CHSUB_RE.search(t):
        src = _match_first(t, SOURCE_SCORES)[1]
        if src == "CAM" or _CAMISH_RE.search(t):
            return "hard"
        if src in ("Remux", "BluRay", "WEB"):
            return "soft"
        return "cn"
    return ""


_CN_MARK_RE = re.compile(
    r"国语|國語|国配|國配|粤语|粵語|华语|華語|中字|简繁|繁简|简体|繁体|\bCHN\b|"
    r"高清影视之家|中文字幕|国英|双语", re.I)
_CJK_RE = re.compile(r"[一-鿿]")
_KANA_RE = re.compile(r"[぀-ヿ]")  # Japanese hiragana/katakana


def is_domestic(r):
    """Heuristic: does this look like a Chinese-origin / Chinese-audio release?"""
    t = r.get("title") or ""
    if _CN_MARK_RE.search(t):
        return True
    # A title carrying several Han characters (and no Japanese kana, to avoid
    # mislabelling anime) reads as a domestic release.
    return len(_CJK_RE.findall(t)) >= 2 and not _KANA_RE.search(t)


# ---- disc-image / remux detection (poor playback compatibility) -----------
# "Original disc" releases — full UHD/BD folder rips (BDMV/ISO) and Remuxes —
# are huge (tens of GB) and often carry raw HEVC + Dolby Vision / lossless
# audio in a container many players & TVs choke on. Re-encoded releases carry
# a software encoder tag (x264/x265) and are far more compatible. This flags
# the disc/remux kind so it can be excluded.
#
# Encoder-agnostic disc markers: "UHD BluRay" / "Blu-ray Disc" / "Complete
# BluRay" with no x264/x265 re-encode tag ⇒ it's the disc itself, not a rip.
_DISC_RE = re.compile(r"\bUHD\s*Blu-?ray\b|\bBlu-?ray\s*Disc\b|\bcomplete\s*bluray\b", re.I)


def is_remux(r):
    """True if the release looks like a disc image / remux (huge, low-compat).

    Signals, any of:
      • an explicit remux / 原盘 / BDMV / ISO tag;
      • a "UHD BluRay"-style disc marker with NO x264/x265 re-encode tag
        — i.e. the untouched disc;
      • sheer size: a release above ~40 GB is a disc/remux in practice.
    """
    t = r.get("title") or ""
    if re.search(r"remux|原盘|原盤|\bBDMV\b|\bISO\b", t, re.I):
        return True
    size_gb = (r.get("size") or 0) / 1e9
    if size_gb >= 40:  # nothing re-encoded is this big
        return True
    # Disc marker present and no software-encoder tag ⇒ raw disc.
    if _DISC_RE.search(t) and not re.search(r"\bx26[45]\b", t, re.I):
        return True
    return False




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
    the title token list `toks`, as a fraction of len(q). Returns
    (fraction, start_index_of_best_run)."""
    if not q:
        return 0.0, 0
    best, best_start = 0, 0
    for start in range(len(toks)):
        run = 0
        while (run < len(q) and start + run < len(toks)
               and toks[start + run] == q[run]):
            run += 1
        if run > best:
            best, best_start = run, start
    return best / len(q), best_start


_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def relevance(query_en, year, title):
    """How well a result title matches the wanted film (0..1).

    Uses the longest *contiguous, in-order* run of query tokens — so
    "21 Grams" matches "21.Grams.2003" fully but only half-matches an anime
    episode "... - 21".

    Year is a strong signal for single-word titles (Paprika 2018 vs Paprika
    2006, Yellowstone vs Murder at Yellowstone City 2022): an exact year match
    nudges up; a title that carries a *different* year is heavily penalised.
    An episode/season marker (SxxExx, "- 21", "[12]") also pushes down.
    """
    q = _tokens(query_en)
    if not q:
        return 0.0
    toks = _tokens(title)
    score, start = _contiguous_run(q, toks)
    # The film title usually leads the release name. If the matched run starts
    # deep inside the title (e.g. "Yellowstone" inside "Murder at Yellowstone
    # City"), it's probably a different film that merely contains the word.
    if start >= 2 and score >= 0.99:
        score *= 0.5
    if year and str(year).isdigit():
        years = set(_YEAR_RE.findall(title or ""))
        if years:
            if str(year) in years:
                score = min(1.0, score + 0.2)
            elif all(abs(int(y) - int(year)) > 1 for y in years):
                score *= 0.3  # title names a clearly different year
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

    out_path = args.out or (os.path.splitext(args.batch)[0] + "_magnets.csv")

    # Resume: if the output already exists, count its data rows and skip that
    # many input rows. Rows are written in input order, so a row count is a
    # safe checkpoint. --restart forces a fresh run.
    done = 0
    if os.path.exists(out_path) and not args.restart:
        with open(out_path, newline="", encoding="utf-8-sig") as f:
            done = max(0, sum(1 for _ in f) - 1)
        if done >= len(data):
            print(f"All {len(data)} rows already done in {out_path} "
                  f"(use --restart to redo).")
            return
        print(f"Resuming: {done} rows already in {out_path}, "
              f"continuing from row {done + 1}.")

    mode = "a" if done else "w"
    f = open(out_path, mode, newline="", encoding="utf-8-sig")
    w = csv.writer(f)
    if not done:
        w.writerow(out_header)

    processed = 0
    try:
        for ri, row in enumerate(data, 1):
            if ri <= done:
                continue
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
                w.writerow(row + [""] * (topn * 4)); f.flush()
                continue

            try:
                raw = search(key, query, indexer_ids, categories)
            except SystemExit:
                raise
            except Exception as e:
                print(f"{log_pre}  — search error: {e}", file=sys.stderr)
                w.writerow(row + [""] * (topn * 4)); f.flush()
                continue

            # Fallback: if EN+year found nothing, retry with EN alone, then ZH.
            if not raw and year and title_en:
                raw = search(key, title_en, indexer_ids, categories)
            if not raw and title_zh and title_zh != primary:
                raw = search(key, f"{title_zh} {year}".strip(), indexer_ids, categories)

            # Flag indexers that report placeholder seeder counts so the
            # seeder filter below doesn't wipe out every result from an
            # aggregator site (52BT, BTdirectory, Magnet Cat …).
            flag_unreliable_seeders(raw)

            # Score every candidate, filter by seeders and title relevance.
            cand = []
            for r in raw:
                seeders = r.get("seeders") or 0
                # Only enforce --min-seeders where the count is trustworthy.
                if not r.get("_seed_unknown") and seeders < min_seeders:
                    continue
                if args.no_hardsub and subtitle_of(r) == "hard":
                    continue
                if args.no_remux and is_remux(r):
                    continue
                rel = relevance(title_en or title_zh, year, r.get("title"))
                if rel < args.min_relevance:
                    continue
                q = quality_of(r)
                # Relevance is a multiplier, not additive: a weak title match
                # can't be rescued by a high seeder count. Full matches keep
                # their quality score.
                r["_rank"] = q["score"] * rel
                r["_q"] = q
                r["_rel"] = rel
                r["_cn"] = is_domestic(r)
                cand.append(r)

            # Tie-break sort key: real seeders descending, unknown counts last.
            def _seed_tb(x):
                return -1 if x.get("_seed_unknown") else (x.get("seeders") or 0)
            # --cn-first floats domestic releases to the top, ordered among
            # themselves (and among the rest) by rank then seeders.
            if args.cn_first:
                cand.sort(key=lambda x: (0 if x["_cn"] else 1,
                                         -x["_rank"], -_seed_tb(x)))
            else:
                cand.sort(key=lambda x: (-x["_rank"], -_seed_tb(x)))

            # Walk candidates best-first; keep only those that resolve to a
            # real magnet: link. A proxy URL that fails to parse is skipped
            # rather than written as a dead link, so we fall through to the
            # next-best candidate until we have topn good ones.
            picks = []
            for r in cand:
                if len(picks) >= topn:
                    break
                mag = resolve_magnet(r, key)
                if not mag.startswith("magnet:"):
                    continue
                r["_magnet"] = mag
                picks.append(r)

            extra = []
            for r in picks:
                q = r["_q"]
                sub = subtitle_of(r)
                sub_tag = {"hard": "内嵌", "soft": "内封", "cn": "中字"}.get(sub, "")
                bits = [q["resolution"], q["source"], q["codec"]]
                if r.get("_cn"):
                    bits.append("国内")
                if is_remux(r):
                    bits.append("原盘")
                if sub_tag:
                    bits.append(sub_tag)
                qtag = "/".join(x for x in bits if x)
                sd = seeders_display(r)
                seed_cell = "?" if sd is None else str(sd)
                extra += [r["_magnet"], qtag, seed_cell, r.get("title") or ""]
            extra += [""] * ((topn - len(picks)) * 4)  # pad to fixed width
            w.writerow(row + extra); f.flush()
            processed += 1

            if picks:
                bsd = seeders_display(picks[0])
                status = (f"{len(picks)} pick(s), best="
                          f"{picks[0]['_q']['resolution'] or '?'} "
                          f"S:{'?' if bsd is None else bsd}")
            else:
                status = "no match"
            print(f"{log_pre}  — {len(cand)} candidates → {status}")
    finally:
        f.close()
    print(f"\nDone. Processed {processed} rows this run → {out_path}")


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
    ap.add_argument("--no-hardsub", action="store_true",
                    help="drop releases whose subtitles look burned-in (内嵌/硬字幕, TC/CAM 中字)")
    # Defaults on: domestic-first ordering and dropping disc images/remuxes.
    # Each has an opt-out (--no-cn-first / --remux) that flips the same dest.
    ap.add_argument("--cn-first", dest="cn_first", action="store_true", default=True,
                    help="sort domestic (国语/中字/华语) releases first (default on)")
    ap.add_argument("--no-cn-first", dest="cn_first", action="store_false",
                    help="disable domestic-first ordering")
    ap.add_argument("--no-remux", dest="no_remux", action="store_true", default=True,
                    help="drop disc images / remuxes (原盘/Remux/BDMV, huge & poor player compatibility; default on)")
    ap.add_argument("--remux", dest="no_remux", action="store_false",
                    help="keep disc images / remuxes in results")
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
    b.add_argument("--min-relevance", type=float, default=0.85,
                   help="min title match 0..1 to accept a result (default 0.85)")
    b.add_argument("--restart", action="store_true",
                   help="ignore any existing output and reprocess from row 1")
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

    flag_unreliable_seeders(results)

    # --min-seeders filters on real seeder counts only. Results from indexers
    # with placeholder counts (S:?) are kept regardless — we can't judge them,
    # so we don't drop them.
    if args.min_seeders:
        results = [r for r in results
                   if r.get("_seed_unknown")
                   or (r.get("seeders") or 0) >= args.min_seeders]

    if args.no_hardsub:
        results = [r for r in results if subtitle_of(r) != "hard"]

    if args.no_remux:
        results = [r for r in results if not is_remux(r)]

    # For sorting by seeders, an unknown count sorts as -1 (after real counts,
    # so genuinely-seeded results lead) rather than as its fake value.
    def seed_sort(r):
        return -1 if r.get("_seed_unknown") else (r.get("seeders") or 0)
    keymap = {
        "seeders": lambda r: -seed_sort(r),
        "size": lambda r: -(r.get("size") or 0),
        "age": lambda r: (r.get("ageHours") if r.get("ageHours") is not None else 1e12),
    }
    base = keymap[args.sort]
    # --cn-first is a primary sort key layered on top of the chosen sort: all
    # domestic releases float up, ordered among themselves by the base key.
    sort_key = (lambda r: (0 if is_domestic(r) else 1, base(r))) if args.cn_first else base
    results.sort(key=sort_key)
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
        leech = r.get("leechers") or 0
        sd = seeders_display(r)  # None when the indexer's count is unreliable
        if sd is None:
            seed_str, seed_col = "S:?", DIM
        else:
            seed_col = GREEN if sd >= 10 else (YELLOW if sd >= 1 else RED)
            seed_str = f"S:{sd:<5}"
        title = r.get("title") or ""
        print(f"{c(BOLD, f'{n:>3}.')} {title}")
        sub = subtitle_of(r)
        tags = []
        if is_domestic(r):
            tags.append(c(GREEN, "国内"))
        if is_remux(r):
            tags.append(c(RED, "原盘"))
        if sub == "hard":
            tags.append(c(RED, "内嵌"))
        elif sub == "soft":
            tags.append(c(GREEN, "内封/外挂"))
        elif sub == "cn":
            tags.append(c(YELLOW, "中字?"))
        tag_str = ("  " + " ".join(tags)) if tags else ""
        meta = (
            f"     {c(seed_col, f'{seed_str:<7}')} {c(DIM, f'L:{leech:<5}')} "
            f"{c(CYAN, human_size(r.get('size')) ):<18} "
            f"{c(DIM, human_age(r.get('ageHours')) ):<12} "
            f"{c(DIM, r.get('indexer',''))}{tag_str}"
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
