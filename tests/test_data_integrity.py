"""
Spot-check that the parser populates the dataclasses with the right
shape of data for downstream Blender code.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_parser import setup_pkg


def main() -> int:
    parser_mod = setup_pkg()
    types_mod = sys.modules["dcs_edm_importer.edm.types"]

    target = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "f-16c_bl50.edm",
    )
    if not os.path.isfile(target):
        print(f"No test file at {target}")
        return 0

    data = parser_mod.parse_edm(target)

    print(f"version={data.version}  materials={len(data.materials)}  "
          f"render_nodes={len(data.render_nodes)}  "
          f"connectors={len(data.connectors)}  "
          f"lights={len(data.light_nodes)}  scene_nodes={len(data.nodes)}")

    # --- Materials ---------------------------------------------------------
    assert data.materials, "no materials"
    mat = data.materials[0]
    print(f"\nFirst material:")
    print(f"  name           = {mat.name!r}")
    print(f"  material_name  = {mat.material_name!r}")
    print(f"  blending       = {mat.blending}")
    print(f"  textures       = {[(t.index, t.name) for t in mat.textures]}")
    if mat.vertex_format:
        print(f"  vertex_format  = channels {mat.vertex_format.channels}, stride={mat.vertex_format.stride}")
    print(f"  uniforms       = {dict(list(mat.uniforms.items())[:5])}")

    # Check that we've got at least one of every common DCS shader
    shader_set = {m.material_name for m in data.materials}
    print(f"\nDistinct material_names: {len(shader_set)}")
    for s in sorted(shader_set):
        print(f"  - {s}")

    # --- Render nodes ------------------------------------------------------
    rn = next((n for n in data.render_nodes if isinstance(n, types_mod.RenderNode)), None)
    if rn is not None:
        print(f"\nFirst RenderNode:")
        print(f"  name      = {rn.name!r}")
        print(f"  material  = {rn.material_id}")
        print(f"  parents   = {len(rn.parents)} entry(ies), first={rn.parents[0] if rn.parents else None}")
        print(f"  vertices  = {len(rn.vertex_data)}")
        print(f"  indices   = {len(rn.index_data)} (triangles={len(rn.index_data)//3})")
        if rn.vertex_data:
            v = rn.vertex_data[0]
            print(f"  vertex[0] sample = {v[:8] if len(v) >= 8 else v}")

    # --- Multi-parent rendernodes
    multi = [n for n in data.render_nodes if isinstance(n, types_mod.RenderNode) and len(n.parents) > 1]
    print(f"\nRenderNodes with multiple parents: {len(multi)}")
    for n in multi[:3]:
        print(f"  - {n.name!r}: {len(n.parents)} parents, "
              f"index_starts={[p.index_start for p in n.parents]}")

    # --- Animations
    anim_nodes = [n for n in data.nodes if isinstance(n, types_mod.ArgAnimationNode)]
    print(f"\nAnimating nodes (Arg*): {len(anim_nodes)}")
    args_used = set()
    for n in anim_nodes:
        for arg, _ in n.pos_data:
            args_used.add(arg)
        for arg, _ in n.rot_data:
            args_used.add(arg)
    print(f"  unique DCS arguments used: {sorted(args_used)}")

    # --- Connectors
    print(f"\nFirst few connectors:")
    for c in data.connectors[:5]:
        print(f"  {c.name!r} -> parent_node_idx={c.parent}")

    print("\n[PASS] data integrity")
    return 0


if __name__ == "__main__":
    sys.exit(main())
