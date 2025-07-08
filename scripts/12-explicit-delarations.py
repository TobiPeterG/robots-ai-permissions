#!/usr/bin/env python3
import csv
import json
import sys
import argparse
from pathlib import Path
from collections import defaultdict

def load_domains_with_both(csv_path: Path):
    """Return domains that have both robots.txt and ai.txt listed in the CSV."""
    out = []
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            files = {f.strip() for f in row["files"].split(";") if f.strip()}
            if "robots.txt" in files and "ai.txt" in files:
                out.append(row["domain"])
    return out

def load_permissions_map(json_path: Path):
    """Load the JSON produced by 06-map-permissions.py."""
    return json.loads(json_path.read_text(encoding="utf-8"))

def main():
    p = argparse.ArgumentParser(
        description="Aggregate explicit UA allow/disallow counts and conflicts from permissions_map.json"
    )
    p.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).parent / "analysis_output" / "domain_files_map.csv",
        help="Path to domain_files_map.csv",
    )
    p.add_argument(
        "--map",
        type=Path,
        default=Path(__file__).parent / "permissions_map.json",
        help="Path to permissions_map.json",
    )
    args = p.parse_args()

    if not args.csv.is_file() or not args.map.is_file():
        print("❌ Missing CSV or JSON map", file=sys.stderr)
        sys.exit(1)

    domains = load_domains_with_both(args.csv)
    perm_map = load_permissions_map(args.map)

    # counters by UA string
    counters = defaultdict(lambda: {
        "robots_allow": 0,
        "robots_disallow": 0,
        "ai_allow": 0,
        "ai_disallow": 0,
        "conflicts": 0,
    })

    for domain in domains:
        block = perm_map.get(domain)
        if not block:
            continue
        rob = block.get("robots", {})
        ai  = block.get("ai", {})

        # union of explicit UA keys (skip the wildcard "*")
        uas = set(rob) | set(ai)
        uas.discard("*")

        for ua in uas:
            ra = bool(rob.get(ua, {}).get("allow"))
            rd = bool(rob.get(ua, {}).get("disallow"))
            aa = bool(ai.get(ua, {}).get("allow"))
            ad = bool(ai.get(ua, {}).get("disallow"))

            if ra:
                counters[ua]["robots_allow"] += 1
            if rd:
                counters[ua]["robots_disallow"] += 1
            if aa:
                counters[ua]["ai_allow"] += 1
            if ad:
                counters[ua]["ai_disallow"] += 1

            if (ra and ad) or (rd and aa):
                counters[ua]["conflicts"] += 1

    # print the summary table, sorted by descending conflicts
    print(f"{'UA':30s} {'R+':>4s} {'R-':>4s} {'A+':>4s} {'A-':>4s} {'C':>4s}")
    print("-" * 60)
    for ua, cnt in sorted(counters.items(),
                          key=lambda kv: kv[1]["conflicts"],
                          reverse=True):
        print(
            ua.ljust(30),
            str(cnt["robots_allow"]).rjust(4),
            str(cnt["robots_disallow"]).rjust(4),
            str(cnt["ai_allow"]).rjust(4),
            str(cnt["ai_disallow"]).rjust(4),
            str(cnt["conflicts"]).rjust(4),
        )

if __name__ == "__main__":
    main()
