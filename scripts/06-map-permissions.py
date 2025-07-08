#!/usr/bin/env python3
import re
import json
import sys
import csv
import argparse
import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from urllib.robotparser import RobotFileParser

def find_latest_date_folder(root: Path) -> Path:
    dates = [d for d in root.iterdir()
             if d.is_dir() and re.match(r'\d{4}-\d{2}-\d{2}$', d.name)]
    if not dates:
        raise RuntimeError(f"No date folders in {root}")
    return sorted(dates)[-1]

def load_domains_with_both(csv_path: Path) -> list[str]:
    domains = []
    with csv_path.open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            files = {f.strip() for f in row['files'].split(';') if f.strip()}
            if 'robots.txt' in files and 'ai.txt' in files:
                domains.append(row['domain'])
    return domains

def parse_rules(filepath: Path, url: str) -> dict[str, dict[str, list[str]]]:
    """
    Parse a local robots-style file into a dict:
      { user_agent: { 'allow': [...], 'disallow': [...] }, ... }
    """
    text = filepath.read_text(encoding='utf-8', errors='ignore')
    lines = [line.strip() for line in text.splitlines()]
    parser = RobotFileParser()
    parser.set_url(url)
    parser.parse(lines)

    rules = {}
    entries = list(parser.entries)
    if parser.default_entry:
        entries.append(parser.default_entry)

    for entry in entries:
        for ua in entry.useragents:
            rules.setdefault(ua, {'allow': [], 'disallow': []})
            for rule in entry.rulelines:
                target = 'allow' if rule.allowance else 'disallow'
                rules[ua][target].append(rule.path)
    return rules

def process_domain(args: tuple[str, Path]) -> tuple[str, dict] | None:
    domain, files_root = args
    # locate the folder under any split
    domain_dir = None
    for split in files_root.iterdir():
        p = split / domain
        if p.is_dir():
            domain_dir = p
            break
    if not domain_dir:
        return None

    rob_fp = domain_dir / "robots.txt"
    ai_fp  = domain_dir / "ai.txt"
    if not (rob_fp.is_file() and ai_fp.is_file()):
        return None

    try:
        rob_rules = parse_rules(rob_fp, f"https://{domain}/robots.txt")
        ai_rules  = parse_rules(ai_fp , f"https://{domain}/ai.txt")
    except Exception:
        return None

    return domain, {'robots': rob_rules, 'ai': ai_rules}

def main():
    p = argparse.ArgumentParser(
        description="Map robots.txt vs ai.txt permissions via urllib.robotparser"
    )
    p.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).parent / "txt_downloads",
        help="Root of txt_downloads/YYYY-MM-DD"
    )
    p.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).parent / "analysis_output" / "domain_files_map.csv",
        help="domain_files_map.csv"
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "permissions_map.json",
        help="Output JSON path"
    )
    args = p.parse_args()

    # load domains
    try:
        domains = load_domains_with_both(args.csv)
    except FileNotFoundError:
        print(f"❌ CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    if not domains:
        print("ℹ️  No domains with both robots.txt and ai.txt.", file=sys.stderr)
        sys.exit(0)

    # latest download folder
    latest = find_latest_date_folder(args.root)
    files_root = latest / "files"

    # parse in parallel
    tasks = [(dom, files_root) for dom in domains]
    result = {}
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        for out in pool.map(process_domain, tasks):
            if out:
                domain, rules = out
                result[domain] = rules

    # write JSON
    args.out.write_text(json.dumps(result, indent=2))
    print(f"Wrote permissions map for {len(result)} domains to {args.out}")

if __name__ == "__main__":
    main()
