#!/usr/bin/env python3
import argparse
import csv
import sys
from pathlib import Path

def main():
    p = argparse.ArgumentParser(
        description="Summarize counts of which domains have robots.txt, ai.txt, and/or llms.txt"
    )
    p.add_argument(
        "--analysis-dir",
        type=Path,
        default=Path(__file__).parent / "analysis_output",
        help="Directory containing domain_files_map.csv"
    )
    args = p.parse_args()

    csv_path = args.analysis_dir / "domain_files_map.csv"
    if not csv_path.is_file():
        print(f"❌ Cannot find {csv_path}", file=sys.stderr)
        sys.exit(1)

    # Initialize counters
    count_none = 0
    count_robots = 0
    count_ai_or_llms = 0
    count_both_robots_and_llm = 0
    count_ai = 0
    count_llms = 0
    count_ai_and_llms = 0
    count_robots_and_ai = 0
    count_robots_and_llms = 0

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            files_field = row["files"].strip()
            files = set(files_field.split(";")) if files_field else set()

            has_robots = "robots.txt" in files
            has_ai = "ai.txt" in files
            has_llms = "llms.txt" in files
            has_any_llmfile = has_ai or has_llms

            if not files:
                count_none += 1
            if has_robots:
                count_robots += 1
            if has_any_llmfile:
                count_ai_or_llms += 1
            if has_robots and has_any_llmfile:
                count_both_robots_and_llm += 1
            if has_ai:
                count_ai += 1
            if has_llms:
                count_llms += 1
            if has_ai and has_llms:
                count_ai_and_llms += 1
            if has_robots and has_ai:
                count_robots_and_ai += 1
            if has_robots and has_llms:
                count_robots_and_llms += 1

    # Print summary
    print(f"Domains with NO files:                                {count_none}")
    print(f"Domains with robots.txt:                              {count_robots}")
    print(f"Domains with ai.txt or llms.txt:                      {count_ai_or_llms}")
    print(f"Domains with BOTH robots.txt AND (ai.txt/llms.txt):    {count_both_robots_and_llm}")
    print(f"Domains with ai.txt:                                  {count_ai}")
    print(f"Domains with llms.txt:                                {count_llms}")
    print(f"Domains with BOTH ai.txt AND llms.txt:                {count_ai_and_llms}")
    print(f"Domains with robots.txt AND ai.txt:                   {count_robots_and_ai}")
    print(f"Domains with robots.txt AND llms.txt:                 {count_robots_and_llms}")

if __name__ == "__main__":
    main()

