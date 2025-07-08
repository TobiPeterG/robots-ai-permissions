#!/usr/bin/env python3
import re
import sys
import os
import argparse
import csv
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

def find_latest_date_folder(txt_root: Path) -> Path:
    """Return the most recent subdirectory named YYYY-MM-DD under txt_root."""
    date_dirs = [
        d for d in txt_root.iterdir()
        if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}$", d.name)
    ]
    if not date_dirs:
        raise RuntimeError(f"No date folders found in {txt_root}")
    return sorted(date_dirs)[-1]

def scan_domain(domain_dir: Path) -> tuple[str, set[str]]:
    """
    Check which of robots.txt, ai.txt, llms.txt exist in this domain directory.
    Always returns (domain_name, set_of_found_files) -- possibly empty.
    """
    found = {
        name for name in ("robots.txt", "ai.txt", "llms.txt")
        if (domain_dir / name).is_file()
    }
    return domain_dir.name, found

def process_split(split_dir: Path) -> dict[str, set[str]]:
    """
    Scan one split_NNNNN folder concurrently over its domains.
    Returns a mapping domain → set(of found filenames), including empty sets.
    """
    local_map: dict[str, set[str]] = {}
    subdirs = [d for d in split_dir.iterdir() if d.is_dir()]
    # Use threads since filesystem checks are lightweight/IO-bound
    with ThreadPoolExecutor(max_workers=min(64, os.cpu_count() * 4)) as pool:
        for domain, files in pool.map(scan_domain, subdirs):
            local_map[domain] = files
    return local_map

def analyze(date_folder: Path, out_dir: Path):
    files_root = date_folder / "files"
    splits = sorted([
        d for d in files_root.iterdir()
        if d.is_dir() and re.match(r"split_\d{5}$", d.name)
    ])
    if not splits:
        print(f"❌ No split_xxxxx folders under {files_root}", file=sys.stderr)
        sys.exit(1)

    # Gather all domains across splits in parallel
    domain_map: dict[str, set[str]] = {}
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        for split_result in pool.map(process_split, splits):
            for dom, files in split_result.items():
                if dom in domain_map:
                    domain_map[dom].update(files)
                else:
                    domain_map[dom] = set(files)

    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV: domain -> semicolon-separated list of found files
    csv_path = out_dir / "domain_files_map.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["domain", "files"])
        for domain in sorted(domain_map):
            writer.writerow([domain, ";".join(sorted(domain_map[domain]))])

    # domains with robots.txt
    robots_path = out_dir / "plds_with_robots.txt"
    with open(robots_path, "w", encoding="utf-8") as fh:
        for domain, files in sorted(domain_map.items()):
            if "robots.txt" in files:
                fh.write(domain + "\n")

    # domains with ai.txt or llms.txt
    ai_llms_path = out_dir / "plds_with_ai_or_llms.txt"
    with open(ai_llms_path, "w", encoding="utf-8") as fh:
        for domain, files in sorted(domain_map.items()):
            if files.intersection({"ai.txt", "llms.txt"}):
                fh.write(domain + "\n")

    # domains with none of the three files
    none_path = out_dir / "plds_with_no_files.txt"
    with open(none_path, "w", encoding="utf-8") as fh:
        for domain, files in sorted(domain_map.items()):
            if not files:
                fh.write(domain + "\n")

    print(f"✅ Analysis complete. Outputs written to {out_dir}")

def main():
    p = argparse.ArgumentParser(
        description="Concurrently scan latest txt_downloads/YYYY-MM-DD/files for robots.txt, ai.txt, llms.txt"
    )
    p.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).parent / "txt_downloads",
        help="Root folder containing date‐stamped downloads"
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "analysis_output",
        help="Where to write the CSV and lists"
    )
    args = p.parse_args()

    try:
        latest = find_latest_date_folder(args.root)
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    print(f"→ Using latest download: {latest.name}")
    analyze(latest, args.out)

if __name__ == "__main__":
    main()
