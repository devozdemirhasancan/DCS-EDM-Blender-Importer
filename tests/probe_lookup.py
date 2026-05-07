"""
Print a slice of the v10 string lookup table for f-16c_bl50_ED.edm so we
can see exactly which type-name corresponds to which lookup index.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_parser import setup_pkg


def main():
    parser_mod = setup_pkg()
    target = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "f-16c_bl50_ED.edm",
    )
    with open(target, "rb") as fh:
        p = parser_mod.EDMFileParser(fh)
        p.r.read_raw(3)
        p.r.version = p.r.ushort()
        p._read_string_lookup_table()
        table = p.r.string_table
    print(f"{len(table)} strings")
    for i, s in enumerate(table):
        print(f"  [{i:3d}]  {s!r}")


if __name__ == "__main__":
    main()
