"""
Find the actual byte-size of NumberNode in `f-16c_bl50_ED.edm` by
walking the next 64 bytes after a known NumberNode and seeing which
offset yields a valid named-type lookup.
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_parser import setup_pkg


def main():
    parser_mod = setup_pkg()
    workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = os.path.join(workspace, "f-16c_bl50_ED.edm")

    fh = open(target, "rb")
    p = parser_mod.EDMFileParser(fh)
    p.r.read_raw(3)
    version = p.r.ushort()
    p.r.version = version
    p._read_string_lookup_table()
    table = p.r.string_table
    print(f"v{version}, {len(table)} strings in lookup table")

    # Find indices of useful strings
    name_to_idx = {s: i for i, s in enumerate(table)}
    skin_idx = name_to_idx.get("model::SkinNode")
    rend_idx = name_to_idx.get("model::RenderNode")
    print(f"  SkinNode -> {skin_idx},  RenderNode -> {rend_idx}")
    print(f"  string @ idx 18 = {table[18]!r}")  # we know failure points to 18

    # Skip to the failing area: byte 1665269 is start of NumberNode (item 10)
    # We computed: pre of item 10 + 4 (string read) + body = next pre.
    # From the diagnostic output: item 10 reported 20 bytes total, so
    # body starts at 1665269 (= 1665285 - 16) and ends at 1665285.
    # Let's hex-print from 1665260 to 1665320 and try possible boundaries.

    fh.seek(1665260)
    blob = fh.read(80)
    print(f"\nbytes 1665260..1665340:")
    for i in range(0, len(blob), 16):
        bs = blob[i:i + 16]
        u = struct.unpack(f"<{len(bs)//4}I", bs[:len(bs)//4*4])
        print(f"  +{1665260 + i:7d}: " + " ".join(f"{b:08x}" for b in u))

    # Now try every 4-byte aligned offset from 1665269 to 1665320 — for each,
    # read the next uint as a lookup index and report what string it maps to.
    print("\nProbing possible 'next named type' boundaries:")
    for offset in range(1665260, 1665320, 4):
        fh.seek(offset)
        idx = struct.unpack("<I", fh.read(4))[0]
        if 0 <= idx < len(table):
            print(f"  byte {offset:8d}: idx={idx:5d} -> {table[idx]!r}")
        else:
            print(f"  byte {offset:8d}: idx={idx:5d} -> <out-of-range>")

    fh.close()


if __name__ == "__main__":
    main()
