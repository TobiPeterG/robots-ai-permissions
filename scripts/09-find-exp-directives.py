#!/usr/bin/env python3
import re
import sys
import csv
import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from typing import List, Tuple

# Experimental directives to look for
DIRECTIVES = ["DisallowAITraining", "Content-Usage"]
DIRECTIVE_RE = re.compile(
    r'^\s*(?P<directive>' + "|".join(DIRECTIVES) + r')\s*:\s*(?P<value>.+)$',
    re.IGNORECASE
)

def find_latest_date_folder(root: Path) -> Path:
    dates = [d for d in root.iterdir() 
             if d.is_dir() and re.match(r'\d{4}-\d{2}-\d{2}$', d.name)]
    if not dates:
        raise RuntimeError(f"No date-stamped folders under {root}")
    return sorted(dates)[-1]

def load_csv_domains(csv_path: Path) -> List[Tuple[str, List[str]]]:
    """
    Read domain_files_map.csv, return list of (domain, [files...])
    """
    out = []
    with csv_path.open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            files = [f.strip() for f in row['files'].split(';') if f.strip()]
            if any(f in ("robots.txt", "ai.txt") for f in files):
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

def scan_domain(args: Tuple[str, List[str], Path]) -> List[Tuple[str,str,str,str,int]]:
    """
    For a single domain, open robots.txt and/or ai.txt if present,
    search for our experimental directives, return list of:
      (domain, filename, directive, value, lineno)
    """
    domain, files, files_root = args
    try:
        domain_dir = find_domain_dir(files_root, domain)
    except FileNotFoundError:
        return []

    results = []
    for fname in ("robots.txt", "ai.txt"):
        if fname not in files:
            continue
        fpath = domain_dir / fname
        if not fpath.is_file():
            continue
        for lineno, line in enumerate(
            fpath.read_text(encoding="utf-8", errors="ignore").splitlines(),
            start=1
        ):
            m = DIRECTIVE_RE.match(line)
            if m:
                results.append((
                    domain,
                    fname,
                    m.group("directive"),
                    m.group("value").strip(),
                    lineno
                ))
    return results

def main():
    p = argparse.ArgumentParser(
        description="Detect DisallowAITraining/Content-Usage in robots.txt or ai.txt via CSV"
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
        print("No domains with robots.txt or ai.txt in CSV.", file=sys.stderr)
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
    results = []
    with ProcessPoolExecutor() as pool:
        for res in pool.map(scan_domain, tasks):
            results.extend(res)

    if not results:
        print("No DisallowAITraining or Content-Usage directives found.")
        return

    # Print table
    print(f"{'Domain':30} {'File':10} {'Directive':20} {'Value':15} {'Line'}")
    print("-"*90)
    for domain, fname, directive, value, lineno in sorted(results):
        print(f"{domain:30} {fname:10} {directive:20} {value:15} {lineno}")

if __name__ == "__main__":
    main()
