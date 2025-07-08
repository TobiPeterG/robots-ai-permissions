#!/usr/bin/env python3
import re
import sys
import csv
import json
import argparse
from pathlib import Path
from difflib import get_close_matches
from typing import List, Dict, Tuple

# Known AI crawler substrings (lowercase)
AI_AGENTS = [
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

def load_csv_domains(csv_path: Path) -> List[str]:
    """Domains that have both robots.txt and ai.txt."""
    domains = []
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            files = {f.strip() for f in row["files"].split(";") if f.strip()}
            if "robots.txt" in files and "ai.txt" in files:
                domains.append(row["domain"])
    return domains

def load_permissions_map(path: Path) -> Dict[str, Dict]:
    return json.loads(path.read_text(encoding="utf-8"))

def classify_ua(ua: str) -> bool:
    """Return True if ua (lowercased) contains any known AI substring."""
    ua_l = ua.lower()
    return any(agent in ua_l for agent in AI_AGENTS)

def main():
    p = argparse.ArgumentParser(
        description="Detect likely-typo AI-crawler UAs from permissions_map.json"
    )
    p.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).parent / "analysis_output" / "domain_files_map.csv",
        help="domain_files_map.csv",
    )
    p.add_argument(
        "--map",
        type=Path,
        default=Path(__file__).parent / "permissions_map.json",
        help="permissions_map.json",
    )
    args = p.parse_args()

    if not args.csv.is_file() or not args.map.is_file():
        print("❌ Missing CSV or JSON map", file=sys.stderr)
        sys.exit(1)

    domains = load_csv_domains(args.csv)
    perm_map = load_permissions_map(args.map)

    print(f"{'Domain':30} {'File':10} {'Unknown UA':30} {'Suggestion'}")
    print("-" * 85)

    for domain in domains:
        if domain not in perm_map:
            continue
        rob = perm_map[domain].get("robots", {})
        ai  = perm_map[domain].get("ai", {})

        # Collect all explicit UA keys
        keys = set(rob) | set(ai)
        # don't try to correct the wildcard
        keys.discard("*")

        for ua in sorted(keys):
            if classify_ua(ua):
                # known; skip
                continue

            # only keep UAs where we can suggest at least one close match
            sug = get_close_matches(ua.lower(), AI_AGENTS, n=1, cutoff=0.6)
            if not sug:
                continue

            # determine which file(s) mention this UA
            if ua in rob:
                print(f"{domain:30} {'robots.txt':10} {ua:30} {sug[0]}")
            if ua in ai:
                print(f"{domain:30} {'ai.txt':10}    {ua:30} {sug[0]}")

if __name__ == "__main__":
    main()
