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
import hashlib
import json
import os
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


def list_indexers(key):
    data = api_get("/api/v1/indexer", key)
    print(c(BOLD, f"{'ID':>4}  {'NAME':<24} {'PROTO':<8} ENABLED"))
    for i in sorted(data, key=lambda x: x.get("id", 0)):
        en = c(GREEN, "yes") if i.get("enable") else c(RED, "no")
        print(f"{i.get('id'):>4}  {i.get('name',''):<24} {i.get('protocol',''):<8} {en}")


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
    args = ap.parse_args()

    key = get_api_key()

    if args.list_indexers:
        list_indexers(key)
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
