#!/usr/bin/env python3
"""pr-search — command-line torrent search via a local Prowlarr instance.

Examples:
  pr-search ubuntu 24.04                 # search all indexers, sorted by seeders
  pr-search -n 30 debian                 # show up to 30 results
  pr-search -i 5,3 nyaa one piece        # limit to indexer ids 5 and 3
  pr-search -c 2000 dune                 # only category 2000 (Movies)
  pr-search 帕丁顿熊 2014                   # default: domestic-first, no remux, bitrate-gated
  pr-search --duration 95 帕丁顿熊 2014    # tell it the film length for a tighter bitrate gate
  pr-search --keep-lowbitrate dune       # disable the bitrate gate
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
import time
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
# Pixel-dimension fallback: old rips label resolution as WxH (e.g. 320x240,
# 640x480, 1280x720) instead of 1080p/720p. Map the *height* to a tier so a
# 320x240 XviD is correctly graded as SD, not left unscored (which let it slip
# past the bitrate gate and, being domestic, rank first). Height is the last
# number; anamorphic widths vary so we key on height alone.
_WxH_RE = re.compile(r"\b(\d{3,4})\s?[x×]\s?(\d{3,4})\b", re.I)


def _res_from_dims(title):
    """(score, label) from a WxH tag by height tier, or (0, '') if none."""
    m = _WxH_RE.search(title)
    if not m:
        return 0, ""
    h = int(m.group(2))
    if h >= 1600:
        return 4, "2160p"
    if h >= 900:
        return 3, "1080p"
    if h >= 620:
        return 2, "720p"
    return 1, "480p"  # anything smaller (incl. 320x240) is SD


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
    if not res_l:  # no 2160p/1080p/... tag — try a WxH pixel-dimension tag
        res_s, res_l = _res_from_dims(t)
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


# Resolutions that earn a domestic release the --cn-first top slot. Below this
# (480p/SD, or unreadable resolution), a domestic release is NOT floated ahead
# of higher-quality foreign ones — otherwise a 320x240 XviD avi, being
# "domestic", would outrank a 2160p release purely for having Chinese in its
# title. Such low/unknown-quality domestic rips fall back to normal ranking.
_CN_PRIORITY_RES = {"2160p", "1080p", "720p"}


def cn_priority(r):
    """True if this is a domestic release good enough to float to the top."""
    return is_domestic(r) and quality_of(r)["resolution"] in _CN_PRIORITY_RES


# ---- foreign-dub detection (primary audio is a non-original dub) -----------
# Public RU/UKR/Indian trackers often ship a film whose FIRST audio track is a
# dub (Russian voice-over, Ukrainian, generic "Dubbed", French VF…) rather than
# the original. The user wants these dropped. Signals, from the title only:
#   • Cyrillic text                → Russian/Ukrainian release
#   • RU voice-over tags AVO/MVO/DVO/LVO (author/multi/dual/line voice-over)
#   • Ukrainian as the *first* audio: [UKR_ENG] / [2xUKR_ENG] / [UKR] / Ukrainian
#     — but NOT [ENG] or [ENG_UKR] (English primary, just hosted on a UKR site)
#   • an explicit "Dubbed"/Dublado/Doblado/Doblada/Dublaj word
#   • French dub tags TrueFrench / VFF / VFQ / VFI / VF2 (NOT VOSTFR = subbed)
# Chinese releases (国语/国配/中字…) are the *wanted* kind of dub, so a domestic
# release is never flagged. Deliberate limitation: a bare language name
# (Persian, Hindi, Korean…) is NOT flagged — it is usually the film's *original*
# language; only an explicit dub marker counts, to avoid dropping originals.
_FOREIGN_DUB_RE = re.compile(
    r"[Ѐ-ӿ]"                       # any Cyrillic char (RU/UKR)
    r"|\b(?:AVO|MVO|DVO|LVO)\b"              # Russian voice-over tags
    r"|\b(?:\d+x)?UKR(?=[_ \]]|$)|\bUkrainian\b"  # Ukrainian first (UKR_/2xUKR/[UKR])
    r"|\bDubbed\b|\bDublado\b|\bDoblad[oa]\b|\bDublaj\b"  # generic dub words
    r"|\bTrueFrench\b|\bVF[FQI2]\b",         # French dub (not VOSTFR)
    re.I)


def is_foreign_dub(r):
    """True if the release's primary audio looks like a non-original foreign dub.

    Never flags domestic (Chinese) releases — a Chinese dub is what we want.
    """
    if is_domestic(r):
        return False
    return bool(_FOREIGN_DUB_RE.search(r.get("title") or ""))


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


# ---- bitrate quality gate (approximated from size / duration) -------------
# The user wants to drop releases whose video bitrate is below a per-resolution
# floor:  4K/2160p ≥30000 kbps · 1080p ≥10000 · 720p ≥5000.
#
# Prowlarr gives no bitrate and no duration — only file size. So we approximate:
#     bitrate_kbps ≈ size_bytes * 8 / duration_seconds / 1000
# Two deliberate biases, both toward *keeping* borderline files (we'd rather
# miss a bad rip than delete a good one):
#   • This is the *total* bitrate (video+audio); real video bitrate is a bit
#     lower, so the estimate runs high — lenient, especially for multi-audio
#     domestic releases.
#   • A short default duration makes the estimate higher, not lower.
# When quality can't be judged — resolution unreadable, or bitrate can't be
# estimated (no size/duration) — the release passes only if it's a large file
# (>10 GB), used as a proxy for acceptable quality. Any resolution below 720p
# (480p/SD) is dropped outright.
MIN_BITRATE = {  # kbps floor per resolution label (from quality_of)
    "2160p": 30000,
    "1080p": 10000,
    "720p": 5000,
    # Below 720p (480p/SD) is not listed → dropped by bitrate_ok, not gated.
}
DEFAULT_DURATION_MIN = 100  # fallback film length when none is known (minutes)
FALLBACK_SIZE_BYTES = 10 * 1_000_000_000  # 10 GB — un-judgeable releases pass only if at least this large


def est_bitrate_kbps(r, duration_min):
    """Approximate total bitrate in kbps from size and duration. None if unknown."""
    size = r.get("size") or 0
    if not size or not duration_min or duration_min <= 0:
        return None
    return size * 8 / (duration_min * 60) / 1000


def bitrate_ok(r, duration_min, table=None):
    """True if the release meets the per-resolution bitrate floor.

    When quality can't be judged — resolution unreadable, or bitrate can't be
    estimated — the release passes only if it's a large file (>10 GB), used as
    a proxy for acceptable quality. Any resolution below 720p (480p/SD) is
    dropped outright.
    """
    table = table if table is not None else MIN_BITRATE
    res = quality_of(r)["resolution"]
    size = r.get("size") or 0
    if not res:  # resolution unreadable → judge by file size
        return size > FALLBACK_SIZE_BYTES
    floor = table.get(res)
    if not floor:
        return False  # known resolution below 720p (480p/SD) → drop
    br = est_bitrate_kbps(r, duration_min)
    if br is None:  # can't estimate bitrate → judge by file size
        return size > FALLBACK_SIZE_BYTES
    return br >= floor


# ---- title relevance (Prowlarr has no genre; match title tokens instead) ---
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "and", "in", "on", "to", "part"}

# Leading release-site / group tags that precede the real title on public
# indexers (e.g. "[47BT]新世界.New.World", "47BT.朗读者.The.Reader",
# "【高清控联盟】蜘蛛侠3.Spider.Man.3"). Stripped before position analysis so a
# genuine leading title isn't mistaken for a mid-title match. This is only for
# the START-position heuristic; scoring still sees the original tokens.
_SITE_TAG_RE = re.compile(
    r"^\s*(?:"
    r"[\[【](?=[^\]】]*[一-鿿])[^\]】]*[\]】]"  # bracket tag containing CJK
    r"|[\[【][^\]】]*(?:BT|发布|论坛|字幕组|压制|高清|www)[^\]】]*[\]】]"  # site/group bracket
    r"|www\.[a-z0-9-]+\.[a-z]{2,6}"  # explicit www.<domain>.<tld>
    r"|47bt|52bt|\d+bt"              # bare site tags like 47BT / 52BT
    r")[\s._-]*", re.I)
# A leading Chinese title block (optionally with a trailing number, e.g.
# "蜘蛛侠3", "复仇者联盟4") that precedes the English title on domestic
# releases. Also stripped for position analysis so the English run starts at 0.
_CN_TITLE_PREFIX_RE = re.compile(r"^\s*[一-鿿·:：\s]+\d*[\s._-]*")


def _strip_site_tags(s):
    """Remove leading site/group tags and a leading Chinese-title block from a
    release title, so the English title's position can be judged fairly."""
    prev = None
    while s and s != prev:
        prev = s
        s = _SITE_TAG_RE.sub("", s, count=1)
        s = _CN_TITLE_PREFIX_RE.sub("", s, count=1)
    return s


def _tokens(s):
    return [w for w in _WORD_RE.findall((s or "").lower()) if w not in _STOP]


_EPISODE_RE = re.compile(
    r"(\bS\d{1,2}E\d{1,2}\b|\bS\d{1,2}\b|\bEP?\s?\d{1,3}\b|[\s_]-[\s_]\d{1,3}(?!\d)|"
    r"\b\d{1,3}\s?集\b|\bseason\s?\d{1,2}\b|第\s?\d{1,3}\s?[季集]|\[\d{1,3}\])", re.I)


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
    # Strip leading site/group tags first so a genuine leading title (e.g.
    # "[47BT]新世界.New.World") isn't scored as a mid-title match.
    toks = _tokens(_strip_site_tags(title or ""))
    score, start = _contiguous_run(q, toks)
    # The film title usually leads the release name. If the matched run starts
    # deep inside the title it's probably a *different* film that merely
    # contains the query words:
    #   • "Yellowstone" inside "Murder at Yellowstone City"  (start>=2)
    #   • "Elvis" inside "Agent Elvis" / "Reinventing Elvis"  (start==1)
    # For a SINGLE-word title this is especially unreliable — the word alone is
    # weak evidence — so any non-leading match is penalised hard. For multi-word
    # titles we only penalise a clearly-deep start (>=2), since a leading
    # article/number can legitimately shift the run by one.
    if score >= 0.99 and start >= 1:
        score *= 0.35 if (len(q) == 1 or start >= 2) else 0.5
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


def search_retry(key, query, indexer_ids=None, categories=None, fetch=150,
                 attempts=3):
    """search() with retries on transient failures (timeout / connection reset).

    Prowlarr aggregates every indexer into one request, so a single slow or
    stuck indexer can time the whole call out. That's usually transient — a
    retry succeeds. HTTP errors (bad request etc.) are not retried.
    """
    last = None
    for _ in range(attempts):
        try:
            return search(key, query, indexer_ids, categories, fetch)
        except SystemExit:
            raise  # HTTP/URL errors from api_get — not transient, don't retry
        except Exception as e:
            last = e  # timeout, connection reset, malformed JSON, …
    raise last


# ---- batch CSV processing --------------------------------------------------
def _write_csv_atomic(path, header, rows):
    """Write header+rows to `path` atomically (temp file + os.replace).

    os.replace is atomic on the same filesystem, so a reader/observer sees
    either the whole old file or the whole new file — never a truncated one.
    This is how we snapshot progress after each filled row without ever
    leaving the real output empty.
    """
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        wr.writerows(rows)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


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

    en_i = _resolve_col(header, args.en_col,
                        ["titleen", "title_en", "english", "en"])
    zh_i = _resolve_col(header, args.zh_col, ["title", "title_zh", "name", "电影名"])
    yr_i = _resolve_col(header, args.year_col, ["year", "年份", "年代"])
    rt_i = _resolve_col(header, args.duration_col,
                        ["duration", "runtime", "时长", "片长", "分钟"])
    if en_i is None and zh_i is None:
        sys.exit("Could not find a title column. Use --en-col / --zh-col to set it "
                 f"(header seen: {header}).")

    indexer_ids = args.indexer_ids.split(",") if args.indexer_ids else None
    # No category filter by default. Many releases (esp. foreign / classic /
    # domestic-tagged films) are mislabelled or uncategorised on public
    # indexers, so restricting to category 2000 (Movies) silently drops them —
    # e.g. Tangerine/Peppermint Candy return 0 under 2000 but 40+ unfiltered.
    # Title relevance (relevance()) already screens out unrelated hits, so we
    # let category be opt-in via -c instead.
    categories = args.categories.split(",") if args.categories else None
    topn = args.top
    min_seeders = args.min_seeders if args.min_seeders else 5  # batch default

    # If the input CSV already carries a magnet_1..title_N block (e.g. a prior
    # export or an earlier run written back into the same file), reuse those
    # columns *in place* instead of appending a second, duplicate block. We
    # treat everything from the first magnet_1 column onward as the mutable
    # "extra" region; the columns before it are the untouched base data.
    low_hdr = [h.strip().lower() for h in header]
    mag_start = low_hdr.index("magnet_1") if "magnet_1" in low_hdr else None
    base_header = header[:mag_start] if mag_start is not None else list(header)
    base_ncols = len(base_header)

    # Build output header: base columns + a fresh magnet_N block sized to --top.
    out_header = list(base_header)
    for n in range(1, topn + 1):
        out_header += [f"magnet_{n}", f"quality_{n}", f"seeders_{n}", f"title_{n}"]

    out_path = args.out or (os.path.splitext(args.batch)[0] + "_magnets.csv")

    # Resume by *content*, not row count. A previous run may have written empty
    # rows for films that returned nothing — sometimes because Prowlarr or an
    # indexer hiccupped mid-run (silent HTTP-200 empty results), not because the
    # film is truly absent. So we reuse only rows that already found a magnet;
    # rows with an empty magnet_1 get (re-)searched. Re-running is self-healing.
    #
    # The whole table lives in memory as `out_rows` (one entry per input row).
    # We never truncate the real file: after each row we (re)search, the full
    # table is snapshotted via _write_csv_atomic (temp + atomic rename). So the
    # output is complete at every instant — interrupt any time and every row
    # searched so far is on disk; already-filled rows are skipped on re-run.
    EXTRA_W = topn * 4
    prev_good = {}  # 1-based input-row index -> saved extra cells
    if not args.restart:
        # (a) Seed from the magnet block embedded in the input CSV itself, so a
        #     row that already has a magnet is reused rather than re-searched.
        if mag_start is not None:
            for i, drow in enumerate(data, 1):
                ex = drow[mag_start:]
                if ex and ex[0].strip():  # magnet_1 non-empty
                    prev_good[i] = ex
        # (b) A prior output file overrides — it's the freshest source.
        if os.path.exists(out_path):
            with open(out_path, newline="", encoding="utf-8-sig") as pf:
                pr = list(csv.reader(pf))
            if pr:
                plow = [h.strip().lower() for h in pr[0]]
                m1 = plow.index("magnet_1") if "magnet_1" in plow else None
                for i, prow in enumerate(pr[1:], 1):
                    if m1 is not None and m1 < len(prow) and prow[m1].strip():
                        prev_good[i] = prow[m1:]  # this row's extra cells
        if prev_good:
            n_good = len(prev_good)
            print(f"Resuming: {n_good} rows already have a magnet; "
                  f"re-searching {len(data) - n_good} empty/new row(s).")

    def _pad_extra(extra):
        return (list(extra) + [""] * EXTRA_W)[:EXTRA_W]

    def _base_of(row):
        b = list(row[:base_ncols])
        return b + [""] * (base_ncols - len(b))  # pad short rows

    # Seed the in-memory table: each row = base input cells + extra cells
    # (reused from a prior good run, else blank placeholders).
    out_rows = []
    for ri, row in enumerate(data, 1):
        out_rows.append(_base_of(row) + _pad_extra(prev_good.get(ri, [])))
    # Persist the seeded table once up front so the file is valid immediately.
    _write_csv_atomic(out_path, out_header, out_rows)

    processed = 0
    reused = len(prev_good)
    searched_any = False  # gates the inter-search throttle
    for ri, row in enumerate(data, 1):
        row = _base_of(row)  # base columns only (drops any embedded magnet block)

        # Skip rows a prior run already filled — they're seeded in out_rows.
        if ri in prev_good:
            continue

        def cell(i):
            return row[i].strip() if i is not None and i < len(row) else ""

        title_en = cell(en_i)
        title_zh = cell(zh_i)
        year = cell(yr_i)
        # Per-film duration for the bitrate estimate: use the CSV column if
        # present & numeric, else fall back to --duration.
        rt_raw = re.sub(r"[^\d]", "", cell(rt_i))  # tolerate "95 min" etc.
        duration_min = int(rt_raw) if rt_raw else args.duration
        label = title_en or title_zh or f"row{ri}"

        # Query: prefer English name + year (best hit-rate on public trackers).
        primary = title_en or title_zh
        query = f"{primary} {year}".strip() if year else primary
        log_pre = f"[{ri}/{len(data)}] {label!r:.50}"

        if not primary:
            print(f"{log_pre}  — no title, skipped", file=sys.stderr)
            continue  # row already blank in out_rows

        # Throttle between real searches: hammering Prowlarr back-to-back
        # makes flaky indexers silently return empty result sets (the same
        # query yields 60+ hits one moment and 0 the next). A fixed gap
        # between requests lets them recover. Only sleep before an actual
        # search, not for reused/skipped rows.
        if searched_any and args.delay > 0:
            time.sleep(args.delay)
        searched_any = True

        try:
            raw = search_retry(key, query, indexer_ids, categories)
        except SystemExit:
            raise
        except Exception as e:
            print(f"{log_pre}  — search error (after retries): {e}", file=sys.stderr)
            continue  # row stays blank in out_rows; a re-run will retry it

        # Fallback: if EN+year found nothing, retry with EN alone, then ZH.
        try:
            if not raw and year and title_en:
                raw = search_retry(key, title_en, indexer_ids, categories)
            if not raw and title_zh and title_zh != primary:
                raw = search_retry(key, f"{title_zh} {year}".strip(), indexer_ids, categories)
        except SystemExit:
            raise
        except Exception:
            pass  # keep whatever the primary query returned (possibly none)

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
            if args.no_foreign_dub and is_foreign_dub(r):
                continue
            if args.min_bitrate and not bitrate_ok(r, duration_min):
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
            # Only domestic releases at 720p+ earn the --cn-first top slot; a
            # low/unknown-res domestic rip (e.g. 320x240 XviD) must not outrank
            # a 2160p foreign one just for being domestic.
            r["_cn_pri"] = r["_cn"] and q["resolution"] in _CN_PRIORITY_RES
            cand.append(r)

        # Tie-break sort key: real seeders descending, unknown counts last.
        def _seed_tb(x):
            return -1 if x.get("_seed_unknown") else (x.get("seeders") or 0)
        # --cn-first floats *quality-passing* domestic releases to the top,
        # ordered among themselves (and among the rest) by rank then seeders.
        if args.cn_first:
            cand.sort(key=lambda x: (0 if x["_cn_pri"] else 1,
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

        # Update this row in the in-memory table and snapshot the whole file
        # atomically. The output is therefore complete after every filled row.
        out_rows[ri - 1] = row + extra
        _write_csv_atomic(out_path, out_header, out_rows)
        processed += 1

        if picks:
            bsd = seeders_display(picks[0])
            status = (f"{len(picks)} pick(s), best="
                      f"{picks[0]['_q']['resolution'] or '?'} "
                      f"S:{'?' if bsd is None else bsd}")
        else:
            status = "no match"
        print(f"{log_pre}  — {len(cand)} candidates → {status}")

    print(f"\nDone. Reused {reused} prior row(s), searched {processed} this run "
          f"→ {out_path}")


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
    # Foreign-dub gate: default on. Drops releases whose primary audio looks like
    # a non-original dub (Russian/Ukrainian/generic Dubbed/French VF).
    ap.add_argument("--no-foreign-dub", dest="no_foreign_dub", action="store_true", default=True,
                    help="drop foreign-dubbed releases (Cyrillic/AVO-MVO-DVO/ukr/Dubbed/VFF; default on)")
    ap.add_argument("--keep-foreign-dub", dest="no_foreign_dub", action="store_false",
                    help="keep foreign-dubbed (俄配/乌配/外语配音) releases")
    # Bitrate gate: default on. --keep-lowbitrate opts out; --duration sets the
    # assumed film length used to estimate bitrate from file size.
    ap.add_argument("--min-bitrate", dest="min_bitrate", action="store_true", default=True,
                    help="drop releases below the per-resolution bitrate floor "
                         "(4K≥30000/1080p≥10000/720p≥5000 kbps; default on)")
    ap.add_argument("--keep-lowbitrate", dest="min_bitrate", action="store_false",
                    help="keep low-bitrate releases (disable the bitrate gate)")
    ap.add_argument("--duration", type=int, metavar="MIN", default=DEFAULT_DURATION_MIN,
                    help=f"assumed film length in minutes for bitrate estimation "
                         f"(default {DEFAULT_DURATION_MIN})")
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
    b.add_argument("--delay", type=float, default=5.0, metavar="SEC",
                   help="seconds to wait between searches so flaky indexers "
                        "recover (default 5; set 0 to disable)")
    b.add_argument("--min-relevance", type=float, default=0.85,
                   help="min title match 0..1 to accept a result (default 0.85)")
    b.add_argument("--restart", action="store_true",
                   help="ignore any existing output and reprocess from row 1")
    b.add_argument("--no-header", action="store_true",
                   help="input CSV has no header row")
    b.add_argument("--en-col", help="English-title column (name or 1-based index)")
    b.add_argument("--zh-col", help="Chinese-title column (name or 1-based index)")
    b.add_argument("--year-col", help="year column (name or 1-based index)")
    b.add_argument("--duration-col",
                   help="duration-in-minutes column for bitrate estimation "
                        "(name or 1-based index; falls back to --duration)")
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

    if args.no_foreign_dub:
        results = [r for r in results if not is_foreign_dub(r)]

    if args.min_bitrate:
        results = [r for r in results if bitrate_ok(r, args.duration)]

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
    # --cn-first is a primary sort key layered on top of the chosen sort:
    # quality-passing domestic releases (720p+) float up, ordered among
    # themselves by the base key. Low/unknown-res domestic rips are not floated.
    sort_key = (lambda r: (0 if cn_priority(r) else 1, base(r))) if args.cn_first else base
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
        br = est_bitrate_kbps(r, args.duration)
        br_str = f"~{br/1000:.1f}Mbps" if br else "~?"
        meta = (
            f"     {c(seed_col, f'{seed_str:<7}')} {c(DIM, f'L:{leech:<5}')} "
            f"{c(CYAN, human_size(r.get('size')) ):<18} "
            f"{c(DIM, f'{br_str:<10}')} "
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
