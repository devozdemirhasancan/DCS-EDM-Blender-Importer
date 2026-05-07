---
title: Architecture
layout: default
nav_order: 4
permalink: /architecture/
---

# Architecture
{: .no_toc }

The add-on is split across small modules so each piece can be tested
in isolation and replaced independently. Nothing in `dcs_edm_importer/edm/`
imports `bpy`, which means you can run the parser standalone — useful
for debugging .edm files outside Blender.
{: .fs-5 .fw-300 }

1. TOC
{:toc}

---

## Module map

```
dcs_edm_importer/
├── __init__.py            # bl_info + register/unregister, reload-aware
├── blender_manifest.toml  # Blender 4.2+ Extension manifest
│
├── edm/                   # pure-Python parser (no bpy dependency)
│   ├── reader.py          # low-level binary primitives
│   ├── types.py           # dataclasses for every node / material
│   └── parser.py          # named-type dispatch + recovery
│
├── blender/               # Blender scene construction
│   ├── transforms.py      # axis correction + world-matrix walker
│   ├── textures.py        # cached, multi-path texture resolver
│   ├── materials.py       # MATERIAL_NAME-aware Principled BSDF
│   ├── meshes.py          # mesh + UV flip + multi-parent split + skin weights
│   ├── armature.py        # rig + per-argument NLA actions
│   ├── extras.py          # connectors, light nodes
│   └── importer.py        # top-level orchestration
│
└── ui/
    └── operator.py        # ImportHelper File→Import operator
```

## Phase pipeline

`importer.import_edm` runs eight phases. Each phase is independent of
the others — replacing `MaterialBuilder` with a custom one doesn't
require touching the parser, for example.

```
.edm file
   │
   │  edm.parse_edm
   ▼
ParsedEDM ──┐ (pure data, hashable, picklable)
            │
            ▼
  ┌─────────────────────────┐
  │  blender.importer       │
  │  ───────────────────────│
  │  1. make collection     │
  │  2. axis matrix         │
  │  3. texture resolver    │
  │  4. armature builder    │  → bone_for_node map
  │  5. mesh builder        │  ← consumes bone_for_node for skin weights
  │  6. extras (lights/...) │
  │  7. parent-to-bone      │
  │  8. visibility actions  │
  └─────────────────────────┘
            │
            ▼
   Blender scene
```

## Why a separate parser package?

Two reasons:

1. **Iteration speed** — running the parser via `python tests/test_parser.py`
   completes in under a second on a 70 MB EDM, vs. ~10 s to launch
   Blender, register the add-on and trigger an import.
2. **External tooling** — the parser is plain Python with stdlib only,
   so you can use it from CLI scripts, web services, or other 3-D
   tooling without dragging in `bpy`.

The parser exposes a small public API:

```python
from dcs_edm_importer.edm import parse_edm

data = parse_edm("path/to/aircraft.edm")
print(f"version={data.version}, render_nodes={len(data.render_nodes)}")
for material in data.materials:
    print(material.name, material.material_name, material.textures)
```

## How node parsing works

`EDMFileParser` is dispatch-table driven. Adding a new node type is two
edits:

1. Write the reader method (`_my_new_node` returning a dataclass from
   `edm.types`).
2. Register the EDM type-name → reader method binding in
   `_build_dispatch`.

Each reader method consumes exactly the bytes its node owns and returns
a fully populated dataclass. The base helper `_read_base_node` covers
the universal `name + version + properties_set` header.

## How recovery works

When the parser hits an unknown named-type inside a render-items
category (most often the "NumberNode body layout varies" issue), it:

1. Catches the failure for that single item.
2. Calls `_try_resync_to(...)` which scans up to 1 MiB forward in
   single-byte increments looking for a uint that decodes as the
   lookup-table index of a *known* render-node type.
3. If found, rewinds to that offset, logs how many bytes it skipped,
   and continues.
4. If not found within the window, propagates the original error and
   returns whatever items were already decoded.

In production this lets `f-16c_bl50_ED.edm` recover all 319 of its
render nodes despite the file containing 9 NumberNode entries with
non-standard payloads.

## Coordinate systems

EDM files are **Y-up** (DCS / OpenSceneGraph convention). Blender is
**Z-up**. The conversion is a single -90° rotation around X, computed
once per import in
[`blender.transforms.axis_correction_matrix`]({{ site.baseurl }}/_modules/transforms/) and applied at the **collection / armature root** rather than per
vertex.

Matrices in EDM files are **column-major** (OpenGL); Blender's
`mathutils.Matrix` is **row-major**, so we transpose every read matrix
once in `edm_matrix_to_blender`.

Quaternions in EDM are stored `(x, y, z, w)`; Blender's `Quaternion`
takes `(w, x, y, z)`. The parser does this swap once on read so all
downstream code can use Blender's convention.

## Testing

| File                              | What it tests                                                        |
| --------------------------------- | -------------------------------------------------------------------- |
| `tests/test_parser.py`            | Smoke-test: every .edm in repo root parses without exceptions.       |
| `tests/test_data_integrity.py`    | Spot-checks dataclass fields populate correctly.                     |
| `tests/diagnostic.py`             | Diagnostic dump of node-type counts.                                 |
| `tests/diagnostic_render.py`      | Per-item byte-size dump for the RENDER_NODES category.               |
| `tests/probe_lookup.py`           | Prints the v10 string lookup table.                                  |
| `tests/probe_numbernode.py`       | Investigative tool used to debug the NumberNode resync heuristic.    |

CI runs the smoke test on Python 3.10 and 3.11 against every push and
PR — see [`.github/workflows/ci.yml`](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/blob/main/.github/workflows/ci.yml).
