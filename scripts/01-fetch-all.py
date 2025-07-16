#!/usr/bin/env python3
"""
Domain-corpus builder with per-zone PLD extraction & external merge-sort.

Usage:
    ./fetch.py [--force]

Produces under txt_downloads/YYYY-MM-DD/:
  zones/             raw .zone files
  domains_by_zone/   one .txt per zone PLD list
  domains_sorted.txt merged sorted+unique PLDs
  splits/            split_00000.txt, split_00001.txt, … (10k lines each)
"""

import os
import sys
import json
import csv
import gzip
import shutil
import subprocess
import argparse
import io
import zipfile

from datetime import datetime as _dt, timezone
from pathlib import Path
from typing import Set, List, Tuple

import requests
from tqdm import tqdm
from publicsuffix2 import get_sld
import urllib3.util.connection as urllib_conn
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor

urllib_conn.HAS_IPV6 = False

# ────────────────────────── CONFIGURATION ───────────────────────────────
HERE = Path(__file__).parent
TXT_ROOT = HERE / "txt_downloads"
UA = "zrdz/0.4"
CZDS_THREADS = int(os.getenv("CZDS_THREADS", "16"))
PARSE_WORKERS = int(os.getenv("PARSE_WORKERS", "0")) or os.cpu_count()
SORT_THREADS = CZDS_THREADS
SPLIT_SIZE = 10_000

AUTH_URL = ""
CZDS_URL = ""
TLDS_FILTER: List[str] = []


def die(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def load_config():
    global AUTH_URL, CZDS_URL, TLDS_FILTER
    try:
        cfg = json.loads(os.environ.get("CZDS_CONFIG", "") or (HERE / "config.json").read_text())
        AUTH_URL    = cfg["authentication.base.url"]
        CZDS_URL    = cfg["czds.base.url"]
        TLDS_FILTER = cfg.get("tlds", [])
        os.environ["CZDS_USERNAME"] = cfg["icann.account.username"]
        os.environ["CZDS_PASSWORD"] = cfg["icann.account.password"]
    except Exception as e:
        die(f"config error: {e}")


def fetch_to(url: str, dest: Path, headers=None) -> Path:
    if dest.exists():
        return dest
    hdr = {"User-Agent": UA, **(headers or {})}
    with requests.get(url, headers=hdr, stream=True, timeout=90) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return dest


def authenticate() -> str:
    user = os.getenv("CZDS_USERNAME"); pwd = os.getenv("CZDS_PASSWORD")
    if not (user and pwd):
        die("Set CZDS_USERNAME and CZDS_PASSWORD")
    url = AUTH_URL.rstrip("/") + "/api/authenticate"
    r = requests.post(url, json={"username": user, "password": pwd},
                      headers={"Content-Type": "application/json", "Accept": "application/json"},
                      timeout=30)
    if r.status_code != 200:
        die(f"Auth failed {r.status_code}")
    return r.json()["accessToken"]


def do_get(url: str, token: str):
    return requests.get(url,
                        headers={"Authorization": f"Bearer {token}", "User-Agent": UA},
                        stream=True, timeout=60)


def fetch_czds(zones_dir: Path) -> List[Path]:
    token = authenticate()
    resp = do_get(f"{CZDS_URL.rstrip('/')}/czds/downloads/links", token)
    links = resp.json() if resp.status_code == 200 else []
    if TLDS_FILTER:
        links = [u for u in links if any(u.endswith(f"{t}.zone") for t in TLDS_FILTER)]

    zones_dir.mkdir(parents=True, exist_ok=True)
    out, retry = [], []
    with ThreadPoolExecutor(CZDS_THREADS) as ex:
        futs = {ex.submit(_download_zone, u, zones_dir, token): u for u in links}
        for f in tqdm(as_completed(futs), total=len(futs), unit="zone"):
            p = f.result()
            (out if p else retry).append(p or futs[f])
    if retry:
        token = authenticate()
        with ThreadPoolExecutor(CZDS_THREADS) as ex:
            futs = {ex.submit(_download_zone, u, zones_dir, token): u for u in retry}
            for f in tqdm(as_completed(futs), total=len(futs), unit="zone"):
                p = f.result()
                if p:
                    out.append(p)
    return out


def _download_zone(url: str, out_dir: Path, token: str) -> Path | None:
    fn = out_dir / url.rsplit("/", 1)[-1]
    if fn.exists():
        return fn
    try:
        r = do_get(url, token)
        if r.status_code == 200:
            with open(fn, "wb") as f:
                for c in r.iter_content(1 << 16):
                    f.write(c)
            return fn
        if r.status_code == 401:
            return None
        print(f"[CZDS] {url} -> {r.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"[CZDS] {url} error {e}", file=sys.stderr)
    return None


def parse_zone_to_file(zf: Path, out_txt: Path):
    plds = set()
    try:
        sig = zf.open("rb").read(2)
        opener = gzip.open if sig == b"\x1f\x8b" else open
        with opener(zf, "rt", encoding="utf-8", errors="ignore") as fh:
            for ln in fh:
                if ln.startswith(";") or not ln.strip():
                    continue
                lbl = ln.split()[0].rstrip(".")
                if "*" in lbl or lbl.count(".") != 1:
                    continue
                d = get_sld(lbl.lower().lstrip("*."))
                if d:
                    plds.add(d)
    except Exception:
        print(f"[Warn] skipping corrupted {zf.name}", file=sys.stderr)
    out_txt.write_text("\n".join(plds), encoding="utf-8")


def download_cc(zones_dir: Path) -> Set[str]:
    plds = set()
    p = fetch_to(
        "https://data.commoncrawl.org/projects/hyperlinkgraph/cc-main-2025-mar-apr-may/domain/cc-main-2025-mar-apr-may-domain-vertices.txt.gz",
        zones_dir / "cc.gz"
    )
    with gzip.open(p, "rt", encoding="utf-8", errors="ignore") as fh:
        for ln in fh:
            parts = ln.split()
            if len(parts) > 1:
                d = get_sld(parts[1].strip())
                if d:
                    plds.add(d)
    return plds


def download_tranco(zones_dir: Path) -> Set[str]:
    """
    Fetch Tranco Top 1M via the ZIP “tip” link, unpack and extract PLDs.
    """
    plds: Set[str] = set()
    zones_dir.mkdir(parents=True, exist_ok=True)

    zip_path = zones_dir / "tranco.zip"
    fetch_to("https://tranco-list.eu/top-1m.csv.zip", zip_path)
    with zipfile.ZipFile(zip_path, "r") as z:
        # find the CSV inside the ZIP
        csv_name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(csv_name) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            for _, dom in reader:
                pld = get_sld(dom.lower())
                if pld:
                    plds.add(pld)
    zip_path.unlink()  # clean up
    return plds


def download_cl(zones_dir: Path) -> Set[str]:
    plds = set()
    repo = zones_dir / "citizenlab"
    if repo.exists():
        subprocess.run(["git", "-C", str(repo), "pull", "--quiet"], check=True)
    else:
        subprocess.run(
            ["git", "clone", "--depth=1", "https://github.com/citizenlab/test-lists.git", str(repo)],
            check=True
        )
    for cf in repo.rglob("*.csv"):
        with open(cf, newline="") as fh:
            for r in csv.DictReader(fh):
                dom = (r.get("url") or r.get("domain") or "").split("/")[0].lower()
                d = get_sld(dom)
                if d:
                    plds.add(d)
    return plds


def collect() -> Set[str]:
    zones_dir = Path(WORKING_DIRECTORY)
    with ThreadPoolExecutor(3) as ex:
        fcc = ex.submit(download_cc, zones_dir)
        ftr = ex.submit(download_tranco, zones_dir)
        fcl = ex.submit(download_cl, zones_dir)
    zones = fetch_czds(zones_dir)
    plds = set()
    plds |= fcc.result() | ftr.result() | fcl.result()
    return plds

def parse_zone_pair(pair):
    """Unpack (zone_path, out_txt) and call parse_zone_to_file()."""
    zf, out_txt = pair
    parse_zone_to_file(zf, out_txt)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    today = _dt.now(timezone.utc).strftime("%Y-%m-%d")
    base = TXT_ROOT / today
    zones_dir = base / "zones"
    byzone_dir = base / "domains_by_zone"
    splits_dir = base / "splits"

    if splits_dir.exists() and any(splits_dir.iterdir()) and not args.force:
        print(f"⇢ {today} splits exist, skipping")
        return
    if args.force and base.exists():
        shutil.rmtree(base)

    for d in (zones_dir, byzone_dir, splits_dir):
        d.mkdir(parents=True, exist_ok=True)
    global WORKING_DIRECTORY
    WORKING_DIRECTORY = str(zones_dir)

    load_config()
    start = _dt.now(timezone.utc)
    print(f"🚀 {start.isoformat()} → {base}")

    print(f"⇢ downloading")
    # download & collect PLDs
    collect()

    print(f"⇢ parsing")
    # parse each zone to its own txt
    zone_files = [
        p for p in zones_dir.rglob("*")
        if p.is_file() and (p.suffix == ".zone" or p.name.endswith(".zone.gz"))
    ]
    tasks: List[Tuple[Path, Path]] = [
        (zf, byzone_dir / (zf.name + ".txt")) for zf in zone_files
    ]
    with ProcessPoolExecutor(PARSE_WORKERS) as ex:
        list(
            tqdm(
                ex.map(parse_zone_pair, tasks),
                total=len(tasks),
                desc="Per-zone",
            )
        )

    print(f"⇢ merging")
    # merge-sort
    merged = base / "domains_sorted.txt"
    cmd = [
        "sort", f"--parallel={SORT_THREADS}", "-u", "-m",
        *map(str, (byzone_dir / f.name for f in byzone_dir.iterdir())),
        "-o", str(merged)
    ]
    subprocess.run(cmd, check=True)

    print(f"⇢ splitting")
    # split
    subprocess.run([
        "split", "-l", str(SPLIT_SIZE), "-d", "--additional-suffix", ".txt",
        str(merged), str(splits_dir / "split_")
    ], check=True)

    merged.unlink()

    dur = (_dt.now(timezone.utc) - start).total_seconds()
    print(f"✅ done in {dur:.1f}s")

if __name__ == "__main__":
    main()
