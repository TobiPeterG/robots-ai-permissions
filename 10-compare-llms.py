#!/usr/bin/env python3
import re
import sys
import csv
import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from typing import List, Tuple

# Regexes
LINK_RE = re.compile(r'\[.*?\]\((https?://[^)]+|/[^)]+)\)')
DISALLOW_RE = re.compile(r'^\s*Disallow\s*:\s*(\S.*)$', re.IGNORECASE)
DIRECTIVE_RE = re.compile(
    r'^\s*(DisallowAITraining|Content-Usage)\s*:\s*(\S.*)$',
    re.IGNORECASE
)

def find_latest_date_folder(root: Path) -> Path:
    dates = [
        d for d in root.iterdir()
        if d.is_dir() and re.match(r'\d{4}-\d{2}-\d{2}$', d.name)
    ]
    if not dates:
        raise RuntimeError(f"No date-stamped folders under {root}")
    return sorted(dates)[-1]

def load_csv_domains(csv_path: Path) -> List[Tuple[str, List[str]]]:
    """
    Read domain_files_map.csv, return list of (domain, [files...]),
    but only keep those with llms.txt and at least one of robots.txt or ai.txt.
    """
    out = []
    with csv_path.open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            files = [f.strip() for f in row['files'].split(';') if f.strip()]
            if 'llms.txt' in files and any(f in ('robots.txt', 'ai.txt') for f in files):
                out.append((row['domain'], files))
    return out

def find_domain_dir(files_root: Path, domain: str) -> Path:
    """
    Search each split_xxxxx folder for a subdirectory named domain.
    Return the first match.
    """
    for split in files_root.iterdir():
        if not split.is_dir():
            continue
        cand = split / domain
        if cand.is_dir():
            return cand
    raise FileNotFoundError(f"No folder for domain {domain}")

def load_disallows(fp: Path) -> List[Tuple[str,str]]:
    """
    Read Disallow and experimental directives as (pattern, directive_name).
    """
    res = []
    for line in fp.read_text(encoding='utf-8', errors='ignore').splitlines():
        m = DISALLOW_RE.match(line)
        if m:
            res.append((m.group(1).strip(), 'Disallow'))
            continue
        m2 = DIRECTIVE_RE.match(line)
        if m2 and m2.group(1).lower() == 'disallowaitraining':
            val = m2.group(2).strip()
            if val == '/':
                res.append(('/', 'DisallowAITraining'))
        elif m2 and m2.group(1).lower() == 'content-usage':
            res.append((m2.group(2).strip(), 'Content-Usage'))
    return res

def normalize_link(domain: str, url: str) -> str:
    """
    Convert absolute or relative URL to a path on the domain.
    """
    if url.startswith('/'):
        return url
    # strip scheme
    parts = re.split(r'https?://', url, maxsplit=1)[-1]
    # strip domain
    if parts.startswith(domain):
        parts = parts[len(domain):]
    # take path portion
    if '/' in parts:
        return '/' + parts.split('/',1)[1]
    return '/'

def scan_domain(args: Tuple[str, List[str], Path]) -> List[Tuple[str,int,str,str,str]]:
    """
    For domain, scan llms.txt links, check against disallow patterns
    from robots.txt/ai.txt. Return list of conflicts:
      (domain, line_no, link_url, blocking_file, directive_name)
    """
    domain, files, files_root = args
    try:
        domain_dir = find_domain_dir(files_root, domain)
    except FileNotFoundError:
        return []
    llms_fp = domain_dir / "llms.txt"
    if not llms_fp.is_file():
        return []

    disallows = []
    if 'robots.txt' in files:
        robots_fp = domain_dir / "robots.txt"
        if robots_fp.is_file():
            for pat, dname in load_disallows(robots_fp):
                disallows.append((pat, 'robots.txt', dname))
    if 'ai.txt' in files:
        ai_fp = domain_dir / "ai.txt"
        if ai_fp.is_file():
            for pat, dname in load_disallows(ai_fp):
                disallows.append((pat, 'ai.txt', dname))

    if not disallows:
        return []

    conflicts = []
    for lineno, line in enumerate(llms_fp.read_text(
            encoding='utf-8', errors='ignore'
        ).splitlines(), start=1):
        for m in LINK_RE.finditer(line):
            url = m.group(1)
            path = normalize_link(domain, url)
            for pat, fname, directive in disallows:
                if pat == '/' or path.startswith(pat):
                    conflicts.append((domain, lineno, url, fname, directive))
    return conflicts

def main():
    p = argparse.ArgumentParser(
        description="Find llms.txt links that point to paths blocked by robots.txt or ai.txt (using CSV map)"
    )
    p.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).parent/"analysis_output"/"domain_files_map.csv",
        help="domain_files_map.csv"
    )
    p.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).parent/"txt_downloads",
        help="Root directory containing date-stamped subfolders"
    )
    args = p.parse_args()

    domains = load_csv_domains(args.csv)
    if not domains:
        print("No domains with llms.txt + robots.txt/ai.txt in CSV.", file=sys.stderr)
        sys.exit(0)

    try:
        latest = find_latest_date_folder(args.root)
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    files_root = latest/"files"
    if not files_root.is_dir():
        print(f"❌ Expected {files_root}", file=sys.stderr)
        sys.exit(1)

    tasks = [(dom, fs, files_root) for dom, fs in domains]
    all_conflicts = []
    with ProcessPoolExecutor() as pool:
        for res in pool.map(scan_domain, tasks):
            all_conflicts.extend(res)

    # remove exact duplicates (same domain,line,url,file,directive)
    seen = set()
    unique_conflicts = []
    for c in all_conflicts:
        if c not in seen:
            seen.add(c)
            unique_conflicts.append(c)

    if not unique_conflicts:
        print("✅ No llms.txt links pointing to blocked paths found.")
        return

    print(f"{'Domain':20} {'Line':4} {'Link':40} {'Blocked By':10} {'Directive'}")
    print("-"*100)
    for domain, lino, url, fname, directive in unique_conflicts:
        print(f"{domain:20} {lino:<4} {url:40} {fname:10} {directive}")

if __name__ == "__main__":
    main()
