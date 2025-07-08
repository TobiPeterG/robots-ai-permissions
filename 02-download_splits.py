#!/usr/bin/env python3
"""
Process each split_NNNNN.txt:

  • Copy split file into txt_downloads/YYYY-MM-DD/
  • Create folder txt_downloads/YYYY-MM-DD/split_NNNNN/
  • In that folder, per-domain subfolders with robots.txt, ai.txt, llms.txt

Usage:
    ./process_splits.py [--force]
"""

import argparse
import shutil
import sys
import logging
from datetime import datetime as _dt, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import requests
import traceback

# Configuration
HERE = Path(__file__).parent
TXT_ROOT = HERE / "txt_downloads"
DOMAINS_PER_SPLIT = 10_000
THREADS_PER_SPLIT = 64
TIMEOUT = 10  # seconds per HTTP GET

class Tee:
    """Write to both a stream (stdout/stderr) and a logger."""
    def __init__(self, stream, logger, level):
        self.stream = stream
        self.logger = logger
        self.level = level

    def write(self, message):
        self.stream.write(message)
        message = message.rstrip('\n')
        if message:
            self.logger.log(self.level, message)

    def flush(self):
        self.stream.flush()


def setup_logging(date_folder: Path):
    """
    Create a logger that writes INFO to stdout and all
    messages to a log file in date_folder/process_splits.log.
    """
    log_path = date_folder / "process_splits.log"
    date_folder.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("process_splits")
    logger.setLevel(logging.DEBUG)

    # File handler (everything DEBUG+ goes to file)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(fh)

    # Replace stdout/stderr with tees
    sys.stdout = Tee(sys.stdout, logger, logging.INFO)
    sys.stderr = Tee(sys.stderr, logger, logging.ERROR)

    return logger


def download_for_domain(domain: str, root: Path):
    dest = root / domain
    dest.mkdir(exist_ok=True, parents=True)
    for name in ("robots.txt", "ai.txt", "llms.txt"):
        for proto in ("https", "http"):
            url = f"{proto}://{domain}/{name}"
            try:
                resp = requests.get(url, timeout=TIMEOUT)
                if resp.status_code == 200 and resp.text:
                    (dest / name).write_text(resp.text, encoding="utf-8")
                    break
            except Exception:
                continue

def process_split(split_path: Path, date_folder: Path, force: bool):
    name = split_path.stem  # e.g. "split_00000"
    copy_target = date_folder / "files" / split_path.name
    work_folder = date_folder / "files" / name

    try:
        if copy_target.exists() and work_folder.exists() and not force:
            print(f"SKIP {name}")
            return

        if force and date_folder.exists():
            if work_folder.exists():
                shutil.rmtree(work_folder)
            if copy_target.exists():
                copy_target.unlink()

        work_folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(split_path, copy_target)

        domains = [
            d.strip()
            for d in split_path.read_text(encoding="utf-8").splitlines()
            if d.strip()
        ]

        print(f"→ {name}: fetching {len(domains)} domains with {THREADS_PER_SPLIT} threads…")
        with ThreadPoolExecutor(max_workers=THREADS_PER_SPLIT) as pool:
            pool.map(lambda dom: download_for_domain(dom, work_folder), domains)
        print(f"✓ {name} done")

    except Exception as e:
        print(f"‼ Error processing {name}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="Re-process even if folder exists")
    args = p.parse_args()

    today = _dt.now(timezone.utc).strftime("%Y-%m-%d")
    base = TXT_ROOT / today
    splits_dir = base / "splits"

    # set up logging
    setup_logging(base)

    splits = sorted(splits_dir.glob("split_*.txt"))
    if not splits:
        print("❌ No split_*.txt found in splits/", file=sys.stderr)
        sys.exit(1)

    # Process each split in its own process
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(processes=min(len(splits), ctx.cpu_count())) as pool:
        pool.starmap(
            process_split,
            [(split, base, args.force) for split in splits]
        )


if __name__ == "__main__":
    main()
