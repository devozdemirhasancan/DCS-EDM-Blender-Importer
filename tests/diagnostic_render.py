"""
Trace each RENDER_NODES item until one fails.

Adds extra logging around the named-type dispatch so we can see exactly
which node was read last and how big it was.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_parser import setup_pkg


def main():
    parser_mod = setup_pkg()
    types_mod = sys.modules["dcs_edm_importer.edm.types"]

    workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = os.path.join(workspace, "f-16c_bl50_ED.edm")
    if not os.path.isfile(target):
        print("missing target file")
        return

    with open(target, "rb") as fh:
        # Replicate the EDMFileParser.parse logic but stop at the failing point
        p = parser_mod.EDMFileParser(fh)
        magic = p.r.read_raw(3)
        version = p.r.ushort()
        p.r.version = version
        if version == 10:
            p._read_string_lookup_table()
        p._read_index_map()
        p._read_index_map()
        root = p._read_named_type()
        print(f"root parsed at byte {p.r.tell()}")

        node_count = p.r.uint()
        print(f"node_count = {node_count}")
        for i in range(node_count):
            before = p.r.tell()
            node = p._read_named_type()
            after = p.r.tell()
            # only print first / last few and any that look weird
            if i < 3 or i > node_count - 3:
                print(f"  scene_node[{i:4d}] {node.type:25s} {after - before:8d} bytes  name={node.name!r}")
        parents = p.r.ints(node_count)
        print(f"parents read, now at byte {p.r.tell()}")

        cat_count = p.r.uint()
        print(f"category count = {cat_count}")
        for c in range(cat_count):
            cat_name = p.r.string()
            cat_offset = p.r.tell()
            item_count = p.r.uint()
            print(f"\n category #{c} = {cat_name!r}, items={item_count}, at byte {cat_offset}")
            for i in range(item_count):
                pre = p.r.tell()
                try:
                    type_name = p.r.string()
                except Exception as exc:
                    print(f"  item[{i}] type-read failed at byte {pre}: {exc}")
                    return
                handler = p._dispatch.get(type_name)
                if handler is None:
                    print(f"  item[{i}] UNKNOWN named type {type_name!r} at byte {pre}")
                    # Hex dump 64 bytes back
                    fh.seek(max(0, pre - 64))
                    data = fh.read(128)
                    print(f"  context bytes: {data.hex(' ', 4)}")
                    return
                node = handler()
                post = p.r.tell()
                # Print all RENDER_NODES items so we can see which one is sized weirdly
                if cat_name == "RENDER_NODES":
                    name = getattr(node, "name", "?")
                    extra = ""
                    if hasattr(node, "vertex_data"):
                        extra = f"  verts={len(node.vertex_data)} idx={len(node.index_data)} mat={getattr(node, 'material_id', '?')}"
                        if hasattr(node, "bones"):
                            extra += f" bones={len(node.bones)}"
                    print(f"  item[{i:3d}] {type_name:30s} {post - pre:10d} bytes  name={name!r}{extra}")
                elif i < 3:
                    name = getattr(node, "name", "?")
                    print(f"  item[{i}] {type_name:30s} {post - pre:10d} bytes  name={name!r}")


if __name__ == "__main__":
    main()
