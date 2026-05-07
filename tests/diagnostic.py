"""
Diagnostic dump: list every scene node type encountered.

Useful when investigating why a particular .edm file fails to parse.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_parser import setup_pkg


def main():
    parser = setup_pkg()
    workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for filename in os.listdir(workspace):
        if not filename.lower().endswith(".edm"):
            continue
        path = os.path.join(workspace, filename)
        print(f"\n=== {filename} ===")
        try:
            data = parser.parse_edm(path)
        except Exception as exc:
            print(f"  parse failed: {exc}")
            continue
        types = Counter(n.type for n in data.nodes)
        for tname, count in sorted(types.items(), key=lambda x: -x[1]):
            print(f"  {tname:25s} {count:4d}")
        for cat, items in data.extra_render_items.items():
            print(f"  extra_category: {cat} -> {len(items)} item(s)")


if __name__ == "__main__":
    main()
