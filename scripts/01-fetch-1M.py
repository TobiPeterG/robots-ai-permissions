#!/usr/bin/env python3
"""
Tranco-only domain list builder with PLD extraction & merge-sort + splitting.

Usage:
    ./01-fetch.py [--force]

Produces under txt_downloads/YYYY-MM-DD/:
  domains_sorted.txt    merged sorted+unique PLDs
  splits/               split_00000.txt, split_00001.txt, … (10k lines each)
"""

import os
import sys
import csv
import shutil
import argparse
import io
import zipfile

from datetime import datetime as _dt, timezone
from pathlib import Path
from publicsuffix2 import get_sld
import requests
from tqdm import tqdm

# ────────────────────────── CONFIGURATION ───────────────────────────────
HERE = Path(__file__).parent
TXT_ROOT = HERE / "txt_downloads"
UA = "zrdz/0.4"
SPLIT_SIZE = 10_000

def die(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)

def fetch_to(url: str, dest: Path, headers=None) -> Path:
    """Download url to dest if not already present."""
    if dest.exists():
        return dest
    hdr = {"User-Agent": UA, **(headers or {})}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=hdr, stream=True, timeout=90) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return dest

def download_tranco(zones_dir: Path) -> set[str]:
    """Fetch Tranco Top 1M zip, unpack CSV, and extract PLDs."""
    zones_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zones_dir / "tranco.zip"
    print(f"⇢ downloading Tranco ZIP")
    fetch_to("https://tranco-list.eu/top-1m.csv.zip", zip_path)

    plds: set[str] = set()
    print(f"⇢ unpacking and parsing CSV")
    with zipfile.ZipFile(zip_path, "r") as z:
        # find the first .csv entry
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            die("No CSV file found inside Tranco ZIP")
        with z.open(names[0]) as csvfile:
            # wrap binary stream in text
            reader = csv.reader(io.TextIOWrapper(csvfile, encoding="utf-8"))
            for _, dom in reader:
                pld = get_sld(dom.lower())
                if pld:
                    plds.add(pld)

    zip_path.unlink()
    return plds

def write_sorted(plds: set[str], base: Path) -> Path:
    """Write sorted unique PLDs to domains_sorted.txt."""
    out = base / "domains_sorted.txt"
    base.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for d in sorted(plds):
            fh.write(d + "\n")
    return out

def split_file(sorted_file: Path, splits_dir: Path) -> None:
    """Split the sorted file into chunks of SPLIT_SIZE lines."""
    splits_dir.mkdir(parents=True, exist_ok=True)
    with open(sorted_file, "r", encoding="utf-8") as fh:
        idx = 0
        while True:
            lines = [fh.readline() for _ in range(SPLIT_SIZE)]
            lines = [l for l in lines if l]
            if not lines:
                break
            part = splits_dir / f"split_{idx:05d}.txt"
            with open(part, "w", encoding="utf-8") as out:
                out.writelines(lines)
            idx += 1

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="Re-fetch and rebuild even if outputs exist")
    args = p.parse_args()

    today = _dt.now(timezone.utc).strftime("%Y-%m-%d")
    base = TXT_ROOT / today
    splits_dir = base / "splits"
    zones_dir = base / "tranco_data"

    # Skip if already done
    if splits_dir.exists() and any(splits_dir.iterdir()) and not args.force:
        print(f"⇢ {today} splits exist, skipping")
        return
    if args.force and base.exists():
        shutil.rmtree(base)

    # Prepare directories
    (zones_dir).mkdir(parents=True, exist_ok=True)
    start = _dt.now(timezone.utc)
    print(f"🚀 {start.isoformat()} → {base}")

    # download & collect PLDs from Tranco zip
    plds = download_tranco(zones_dir)

    # write sorted unique PLDs
    print("⇢ writing sorted PLDs")
    sorted_file = write_sorted(plds, base)

    # split into chunks
    print("⇢ splitting into files of up to 10k lines")
    split_file(sorted_file, splits_dir)
    sorted_file.unlink()  # remove the merged file

    dur = (_dt.now(timezone.utc) - start).total_seconds()
    print(f"✅ done in {dur:.1f}s")

if __name__ == "__main__":
    main()
