#!/usr/bin/env python3
import re
import json
import sys
import csv
import argparse
from pathlib import Path
from typing import List, Tuple

AI_SUBSTRINGS = [
    "gptbot",
    "claudebot", "claude-user", "claude-searchbot",
    "ccbot", "google-extended", "applebot-extended",
    "facebookbot", "meta-externalagent", "diffbot",
    "perplexitybot", "perplexity-user",
    "omgili", "omgilibot", "imagesiftbot",
    "bytespider", "tiktokspider", "amazonbot",
    "youbot", "semrushbot-ocob", "petalbot",
    "velenpublicwebcrawler", "turnitinbot", "timpibot",
    "oai-searchbot", "icc-crawler", "ai2bot",
    "dataforseobot", "awariobot", "google-cloudvertexbot",
    "pangu-bot", "kangaroo bot", "sentibot",
    "img2dataset", "meltwater", "seekr",
    "peer39_crawler", "cohere", "duckassistbot",
    "scrapy", "cotoyogi", "aihitbot",
    "factset_spyderbot", "firecrawlagent",
]

# regex to pull out User-Agent / Allow / Disallow lines
DIRECTIVE_RE = re.compile(r'^\s*(User-Agent|Allow|Disallow)\s*:\s*(\S.*)$', re.IGNORECASE)

def find_latest_date_folder(root: Path) -> Path:
    dates = [d for d in root.iterdir() if d.is_dir() and re.match(r'\d{4}-\d{2}-\d{2}$', d.name)]
    if not dates:
        raise RuntimeError(f"No date‐stamped folders under {root}")
    return sorted(dates)[-1]

def load_domains_with_both(csv_path: Path) -> List[str]:
    out = []
    with csv_path.open(newline='', encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            files = {f.strip() for f in row['files'].split(';') if f.strip()}
            if 'robots.txt' in files and 'ai.txt' in files:
                out.append(row['domain'])
    return out

def load_permissions_map(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))

def find_domain_dir(files_root: Path, domain: str) -> Path:
    for split in files_root.iterdir():
        cand = split / domain
        if cand.is_dir():
            return cand
    raise FileNotFoundError(f"No folder for domain {domain}")

def find_directive_lines(fp: Path, directive: str, path_value: str) -> List[Tuple[int,str]]:
    matches = []
    for lineno, line in enumerate(fp.read_text(encoding='utf-8', errors='ignore').splitlines(), start=1):
        m = DIRECTIVE_RE.match(line)
        if not m:
            continue
        field, val = m.group(1).lower(), m.group(2).strip()
        if field == directive.lower() and val == path_value:
            matches.append((lineno, line))
    return matches

def main():
    p = argparse.ArgumentParser(
        description="Show exactly which lines in robots.txt vs ai.txt conflict for AI agents"
    )
    p.add_argument("--root", type=Path,
                   default=Path(__file__).parent/"txt_downloads",
                   help="Root of txt_downloads/YYYY-MM-DD")
    p.add_argument("--csv", type=Path,
                   default=Path(__file__).parent/"analysis_output"/"domain_files_map.csv",
                   help="domain_files_map.csv")
    p.add_argument("--map", type=Path,
                   default=Path(__file__).parent/"permissions_map.json",
                   help="permissions_map.json")
    args = p.parse_args()

    domains = load_domains_with_both(args.csv)
    perm_map = load_permissions_map(args.map)
    latest   = find_latest_date_folder(args.root)
    files_root = latest/"files"

    conflicts = []

    for domain in domains:
        if domain not in perm_map:
            continue
        rob_block = perm_map[domain].get("robots", {})
        ai_block  = perm_map[domain].get("ai", {})

        # gather every UA key we might compare: explicit ones + wildcard if present
        candidate_uas = set(rob_block) | set(ai_block)
        if "*" in rob_block or "*" in ai_block:
            candidate_uas.add("*")

        for ua_key in sorted(candidate_uas):
            # only keep explicit AIs or the wildcard
            if ua_key != "*" and not any(sub in ua_key.lower() for sub in AI_SUBSTRINGS):
                continue

            rob_rules = rob_block.get(ua_key) or rob_block.get("*", {"allow": [], "disallow": []})
            ai_rules  = ai_block.get(ua_key)  or ai_block.get("*", {"allow": [], "disallow": []})

            rob_allow    = set(rob_rules.get("allow", []))
            rob_disallow = set(rob_rules.get("disallow", []))
            ai_allow     = set(ai_rules.get("allow", []))
            ai_disallow  = set(ai_rules.get("disallow", []))

            # conflicts:
            for path in sorted(ai_allow & rob_disallow):
                conflicts.append((domain, ua_key, path, "ai_allow/rob_disallow"))
            for path in sorted(ai_disallow & rob_allow):
                conflicts.append((domain, ua_key, path, "ai_disallow/rob_allow"))

    doms_with_conflict = {c[0] for c in conflicts}
    print("AI‐Agent Permissions Conflict Report")
    print(f"  Total domains checked:  {len(domains)}")
    print(f"  Domains with conflicts: {len(doms_with_conflict)}")
    print(f"  Fully consistent:       {len(domains) - len(doms_with_conflict)}")
    print()

    if not conflicts:
        return

    # drill into each conflict
    for domain, ua, path, kind in conflicts:
        print(f"--- Domain: {domain} | UA: {ua} | Conflict: {kind} | Path: {path}")
        dn      = find_domain_dir(files_root, domain)
        rob_fp  = dn/"robots.txt"
        ai_fp   = dn/"ai.txt"

        if kind == "ai_allow/rob_disallow":
            for lino, line in find_directive_lines(ai_fp,   "Allow",   path):
                print(f"  ai.txt    line {lino}: {line}")
            for lino, line in find_directive_lines(rob_fp,  "Disallow",path):
                print(f"  robots.txt line {lino}: {line}")

        else:  # ai_disallow/rob_allow
            for lino, line in find_directive_lines(ai_fp,   "Disallow",path):
                print(f"  ai.txt    line {lino}: {line}")
            for lino, line in find_directive_lines(rob_fp,  "Allow",   path):
                print(f"  robots.txt line {lino}: {line}")

        print()

if __name__ == "__main__":
    main()
