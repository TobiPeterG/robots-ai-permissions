#!/usr/bin/env python3
import json
from pathlib import Path

def load_permissions(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def compare_rules(rob, ai):
    """
    rob and ai are dicts: {'allow': [...], 'disallow': [...]}
    Returns dict of intersections/differences.
    """
    rob_allow = set(rob.get("allow", []))
    ai_allow  = set(ai.get("allow", []))
    rob_dis  = set(rob.get("disallow", []))
    ai_dis    = set(ai.get("disallow", []))

    return {
        "allow_equal": sorted(rob_allow & ai_allow),
        "allow_only_robots": sorted(rob_allow - ai_allow),
        "allow_only_ai":      sorted(ai_allow - rob_allow),
        "disallow_equal": sorted(rob_dis & ai_dis),
        "disallow_only_robots": sorted(rob_dis - ai_dis),
        "disallow_only_ai":      sorted(ai_dis - rob_dis),
    }

def main():
    perms = load_permissions("permissions_map.json")
    diff = {}

    for domain, blocks in perms.items():
        rob_block = blocks.get("robots", {})
        ai_block  = blocks.get("ai", {})

        # all UAs we'll compare (including wildcard)
        uas = set(rob_block) | set(ai_block)
        uas.add("*")

        domain_diff = {}
        for ua in sorted(uas):
            # fallback to '*' if UA not present
            rob_rules = rob_block.get(ua) or rob_block.get("*", {"allow": [], "disallow": []})
            ai_rules  = ai_block.get(ua)  or ai_block.get("*",  {"allow": [], "disallow": []})

            domain_diff[ua] = compare_rules(rob_rules, ai_rules)

        diff[domain] = domain_diff

    # write out
    out_path = Path("permissions_diff.json")
    out_path.write_text(json.dumps(diff, indent=2), encoding="utf-8")
    print(f"Wrote diff for {len(diff)} domains to {out_path}")

if __name__ == "__main__":
    main()
