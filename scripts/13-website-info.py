#!/usr/bin/env python3
"""
Analyze domains with ai.txt and/or llms.txt, comparing country and industry
information, and differentiating by file presence.

Usage:
    python3 13-website-info.py [--csv PATH] [--workers N]
"""
import csv
import argparse
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

# ──────────────────────── CONFIGURATION ──────────────────────────────────

WHOIS_API = "https://ipwhois.app/json/{domain}"
IPAPI_API = "http://ip-api.com/json/{domain}?fields=country"

# Heuristic industry classification by top-level domain (TLD)
TLD_INDUSTRY_MAP = {
    "edu":  "Education",
    "gov":  "Government",
    "org":  "Non-profit",
    "com":  "Commercial",
    "net":  "Network",
    "ai":   "Tech/AI",
    "io":   "Tech",
    "info": "Information",
}

# ──────────────────────── LOOKUP FUNCTIONS ───────────────────────────────

def get_country_ipwhois(domain: str) -> str:
    try:
        r = requests.get(WHOIS_API.format(domain=domain), timeout=5)
        data = r.json()
        return data.get("country", "Unknown")
    except Exception:
        return "Error"


def get_country_ipapi(domain: str) -> str:
    try:
        r = requests.get(IPAPI_API.format(domain=domain), timeout=5)
        return r.json().get("country", "Unknown")
    except Exception:
        return "Error"


def get_industry_tld(domain: str) -> str:
    parts = domain.lower().rsplit('.', 1)
    tld = parts[1] if len(parts) == 2 else ""
    return TLD_INDUSTRY_MAP.get(tld, "Other")

# ──────────────────────── ANALYSIS PIPELINE ──────────────────────────────

def load_domains(csv_path: Path):
    """
    Read the CSV and return a list of (domain, files_set).
    """
    domains = []
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            files = {f.strip() for f in row["files"].split(";") if f.strip()}
            if files & {"ai.txt", "llms.txt"}:
                domains.append((row["domain"], files))
    return domains


def analyze_domain(args):
    """
    Analyze one domain: presence of ai.txt/llms.txt, country lookups, industry.
    """
    domain, files = args
    # determine file type category
    has_ai = 'ai.txt' in files
    has_llms = 'llms.txt' in files
    if has_ai and has_llms:
        file_type = 'both'
    elif has_ai:
        file_type = 'ai_only'
    else:
        file_type = 'llms_only'

    return {
        'domain': domain,
        'file_type': file_type,
        'country_whois': get_country_ipwhois(domain),
        'country_ipapi': get_country_ipapi(domain),
        'industry_tld': get_industry_tld(domain),
    }


def print_table(rows: list[dict]):
    # Define headers and corresponding keys
    columns = [
        ("Files",        "file_type"),
        ("Domain",       "domain"),
        ("Country (Whois)", "country_whois"),
        ("Country (ip-api)",  "country_ipapi"),
        ("Industry (TLD)",   "industry_tld"),
    ]

    # compute column widths
    widths = []
    for header, key in columns:
        max_len = max(
            len(str(r.get(key, ""))) for r in rows + [{key: header}]
        )
        widths.append(max_len)

    # print header
    header_line = " | ".join(
        header.ljust(width) for (header, _), width in zip(columns, widths)
    )
    print(header_line)
    print("-" * len(header_line))

    # print rows
    for r in rows:
        line = " | ".join(
            str(r.get(key, "")).ljust(width)
            for (_, key), width in zip(columns, widths)
        )
        print(line)


def print_summary(rows: list[dict]):
    # summarize counts
    file_counter = Counter(r['file_type'] for r in rows)
    country_counter = Counter(r['country_whois'] for r in rows)
    industry_counter = Counter(r['industry_tld'] for r in rows)

    print("\nCountry distribution:")
    for c, cnt in country_counter.most_common():
        print(f"  {c:<15} {cnt}")

    print("\nIndustry distribution:")
    for ind, cnt in industry_counter.most_common():
        print(f"  {ind:<15} {cnt}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare country & industry info across domains"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).parent / "analysis_output" / "domain_files_map.csv",
        help="Path to domain_files_map.csv"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Max concurrent lookup threads"
    )
    args = parser.parse_args()

    if not args.csv.is_file():
        print(f"❌ CSV not found at {args.csv}")
        return

    domains = load_domains(args.csv)
    print(f"→ Analyzing {len(domains)} domains with ai.txt/llms.txt...")

    with ThreadPoolExecutor(max_workers=args.workers) as exe:
        results = list(exe.map(analyze_domain, domains))

    print_table(results)
    print_summary(results)


if __name__ == "__main__":
    main()
