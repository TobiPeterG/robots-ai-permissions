#!/usr/bin/env python3
import re
import sys
import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

# Files to validate
FILE_NAMES = ("robots.txt", "ai.txt", "llms.txt")

# Regexes
HTML_MARKERS = (
    re.compile(r'^\s*<!doctype html', re.IGNORECASE),
    re.compile(r'<html', re.IGNORECASE),
)
USER_AGENT_RE = re.compile(r'^\s*User-Agent\s*:', re.IGNORECASE)
MD_PATTERNS = [
    re.compile(r'^\s*#{1,6}\s+', re.MULTILINE),  # headings
    re.compile(r'^\s*>\s+', re.MULTILINE),       # blockquote
    re.compile(r'^\s*[-*+]\s+', re.MULTILINE),   # bullet list
    re.compile(r'\[.+?\]\(.+?\)'),               # links
    re.compile(r'```'),                          # code fence
]

def find_latest_date_folder(root: Path) -> Path:
    dates = [
        d for d in root.iterdir()
        if d.is_dir() and re.match(r'\d{4}-\d{2}-\d{2}$', d.name)
    ]
    if not dates:
        raise RuntimeError(f"No date folders in {root}")
    return sorted(dates)[-1]

def looks_like_html(text: str) -> bool:
    head = text[:2048]
    return any(p.search(head) for p in HTML_MARKERS)

def has_user_agent(text: str) -> bool:
    return bool(USER_AGENT_RE.search(text))

def is_markdown(text: str) -> bool:
    return any(p.search(text) for p in MD_PATTERNS)

def process_split(split_dir: Path) -> dict[str, int]:
    counts = {
        "robots_html": 0,
        "ai_html": 0,
        "llms_html": 0,
        "robots_nouseragent": 0,
        "ai_nouseragent": 0,
        "llms_nomarkdown": 0,
    }

    for domain_dir in split_dir.iterdir():
        if not domain_dir.is_dir():
            continue

        for name in FILE_NAMES:
            f = domain_dir / name
            if not f.is_file():
                continue

            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # remove HTML masquerades
            if looks_like_html(text):
                f.unlink()
                counts[f"{name.split('.')[0]}_html"] += 1
                continue

            # validate
            if name in ("robots.txt", "ai.txt"):
                if not has_user_agent(text):
                    f.unlink()
                    counts[f"{name.split('.')[0]}_nouseragent"] += 1
            else:  # llms.txt
                if not is_markdown(text):
                    f.unlink()
                    counts["llms_nomarkdown"] += 1

    return counts

def main():
    root = Path(__file__).parent / "txt_downloads"
    try:
        latest = find_latest_date_folder(root)
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    files_root = latest / "files"
    if not files_root.is_dir():
        print(f"❌ Expected {files_root}", file=sys.stderr)
        sys.exit(1)

    splits = sorted(
        p for p in files_root.iterdir()
        if p.is_dir() and re.match(r'split_\d{5}$', p.name)
    )
    if not splits:
        print(f"❌ No split folders in {files_root}", file=sys.stderr)
        sys.exit(1)

    total = {k: 0 for k in (
        "robots_html","ai_html","llms_html",
        "robots_nouseragent","ai_nouseragent","llms_nomarkdown"
    )}

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        for result in pool.map(process_split, splits):
            for k, v in result.items():
                total[k] += v

    print(f"Clean & validate report for {latest.name}:")
    print(f"  • robots.txt removed (HTML):            {total['robots_html']:,}")
    print(f"  • ai.txt removed (HTML):                {total['ai_html']:,}")
    print(f"  • llms.txt removed (HTML):              {total['llms_html']:,}")
    print(f"  • robots.txt removed (no User-Agent):   {total['robots_nouseragent']:,}")
    print(f"  • ai.txt removed (no User-Agent):       {total['ai_nouseragent']:,}")
    print(f"  • llms.txt removed (not Markdown):      {total['llms_nomarkdown']:,}")

if __name__ == "__main__":
    main()
