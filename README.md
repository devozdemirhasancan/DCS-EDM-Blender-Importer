# DCS World EDM Importer for Blender

[![CI](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/actions/workflows/ci.yml/badge.svg)](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/actions/workflows/ci.yml)
[![Release](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/actions/workflows/release.yml/badge.svg)](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/releases)
[![Pages](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/actions/workflows/pages.yml/badge.svg)](https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Blender 4.x add-on that imports Eagle Dynamics' DCS World `.edm` 3-D
models into the current scene — geometry, materials, textures, rig,
**skin weights** and DCS-argument-driven animations — in a single
click.

📚 **Full docs:** <https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/>
📖 **Wiki / cheat-sheets:** <https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/wiki>
📦 **Latest release:** <https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/releases/latest>

> **Türkçe:** Eagle Dynamics tarafından geliştirilen DCS World'ün özel
> `.edm` 3B model formatını Blender 4.x'e modüler bir eklenti ile içe
> aktarır. Geometri, malzemeler, dokular, kemik (rig) yapısı, **skin
> ağırlıkları** ve DCS argüman tabanlı animasyonlar tek tıklamada
> içeri çekilir.

---

## What's new in 0.3

| Area                | Improvement                                                                                                                        |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Skin weights**    | `SkinNode` per-vertex bone weights become real Blender vertex groups. Each skinned mesh gets an `Armature` modifier so it deforms when the rig animates. |
| **NumberNode recovery** | Cursor-resync heuristic: scans up to 1 MiB forward for the next valid render-item type. `f-16c_bl50_ED.edm` now imports **319/319** render nodes (was 11). |
| **Multi-UV layers** | Every present UV channel (4-8) becomes its own Blender UV layer (`UVMap`, `UVMap.001`…) — required for decals / lightmaps.        |
| **LOD metadata**    | Each mesh records its parent `LodNode`'s distance band as `edm_lod_min` / `edm_lod_max` custom properties.                          |
| **Animation chain** | Rest-pose math now follows the spec formula `mat * Translate(pos) * Quat1 * Scale * Quat2`; rotation keyframes pre-compose `Quat1`. |
| **Bone coverage**   | Plain `Bone` nodes are now included in the armature so SkinNode references resolve cleanly.                                        |
| **Repo workflows**  | GitHub Actions for CI, automated zip releases, GitHub Pages, and Wiki sync.                                                        |

See [`docs/`](docs/) and the [wiki](wiki/) for full details.

## Highlights vs. v0.1

| What                                | v0.1 (single file)                  | **v0.3 (modular)**                                                                                                |
| ----------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Geometry, normals, UVs              | ✅                                  | ✅                                                                                                                |
| **Multi-UV layers**                 | ❌                                  | ✅                                                                                                                |
| Texture auto-resolution             | ✅                                  | ✅ (cached, faster, more search paths)                                                                            |
| Materials                           | basic Principled BSDF               | **MATERIAL_NAME-aware** (glass / chrome / self-illum / mirror presets), spec map inverted to roughness            |
| **UV V-flip** for DDS               | ❌                                  | ✅                                                                                                                |
| **Parent-chain world transforms**   | ❌ (used only for mirror detection) | ✅ — animated parts land in the correct default pose                                                              |
| **Multi-parent RenderNode split**   | ❌                                  | ✅ (per-part objects with damage-arg metadata)                                                                    |
| Armature / rig                      | partial                             | bone per animating + bone node, parented to `Bone` chain                                                          |
| **Skin weights → vertex groups**    | ❌                                  | ✅                                                                                                                |
| Animations (pos / rot / scale)      | ❌                                  | ✅ per-argument actions, stacked in NLA                                                                           |
| Visibility animations               | ❌                                  | ✅ `hide_render` action per argument                                                                              |
| Connectors                          | ❌                                  | ✅ Empty (Cube)                                                                                                   |
| Light nodes                         | ❌                                  | ✅ Blender point lights                                                                                           |
| Collision shells                    | optional                            | optional, wireframe display                                                                                       |
| **NumberNode recovery**             | ❌ (parsing aborted)                 | ✅ resync heuristic                                                                                               |
| **LOD metadata**                    | ❌                                  | ✅ as object custom properties                                                                                    |
| Code organisation                   | 1167-line single file               | 12 small modules + standalone test suite + CI                                                                     |

---

## Installation

### Option 1 — Pre-built zip (recommended)

Download `dcs_edm_importer-<version>.zip` from the
[latest release](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/releases/latest).

In Blender: **Edit → Preferences → Add-ons → Install…** and pick the
zip. Tick the **DCS World EDM Importer** check-box to enable it.

### Option 2 — Build from source

```powershell
git clone https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer.git
cd DCS-EDM-Blender-Importer
.\build.ps1
# → build/dcs_edm_importer-0.3.0.zip
```

### Option 3 — Symlink the source folder for development

See the [Development guide](https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/development/).

---

## Usage

**File → Import → DCS World EDM (.edm)**

The dialog options are documented in detail at the
[Usage page of the docs](https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/usage/).

After import, every imported object carries `edm_*` custom properties
(`edm_node_type`, `edm_parent_node`, `edm_damage_arg`,
`edm_is_collision`, `edm_lod_min`, `edm_lod_max`, `edm_name`) for use
in scripts and filters.

Animations are imported as muted NLA strips named `<model>_argNNN` —
un-mute the track for the argument you want and scrub the timeline.

---

## File layout

```
dcs_edm_importer/
├── __init__.py            # bl_info + register/unregister, reload-aware
├── blender_manifest.toml  # Blender 4.2+ Extension manifest
│
├── edm/                   # pure-Python parser (no bpy dependency)
│   ├── reader.py
│   ├── types.py
│   └── parser.py          # named-type dispatch + resync recovery
│
├── blender/               # Blender scene construction
│   ├── transforms.py
│   ├── textures.py
│   ├── materials.py       # MATERIAL_NAME-aware Principled BSDF
│   ├── meshes.py          # multi-UV, multi-parent split, skin weights
│   ├── armature.py        # rig + per-argument NLA actions
│   ├── extras.py          # connectors, light nodes
│   └── importer.py        # top-level orchestration
│
└── ui/
    └── operator.py        # ImportHelper File→Import operator

docs/        # Jekyll docs site (deployed to GitHub Pages)
wiki/        # Markdown synced to the GitHub Wiki by Actions
tests/       # Standalone parser smoke / data-integrity tests
.github/     # Issue / PR templates + CI / release / Pages / Wiki workflows
```

---

## Tested files

| File                         | Module                  | Result                                                                       |
| ---------------------------- | ----------------------- | ---------------------------------------------------------------------------- |
| `f-16c_bl50.edm` (72 MB)     | F-16C Viper             | ✅ Full import — 296 render nodes, 16 lights, 20 connectors, 297 mats       |
| `f-16c_bl50_ED.edm` (48 MB)  | F-16C Viper (ED-build)  | ✅ Full import — 319/319 render nodes via NumberNode resync recovery        |

Got more files to test? Add a row in
[`wiki/Compatibility-Matrix.md`](wiki/Compatibility-Matrix.md) and open
a PR — the wiki auto-syncs.

---

## Known limitations

- **Animation transform chain** is partially applied. We compose
  `Quat1` with the keyframe rotation correctly, but `Quat2` is treated
  as identity (true for nearly every aircraft). Visible drift only on
  parts whose `Quat2` is non-default.
- **NumberNode body layout** is still undocumented; we skip past it
  via the resync heuristic rather than parsing it. The data within
  appears to control rendering hints; for a model viewer / editor this
  has no visible effect.
- **No EDM export.** Round-tripping requires authoring valid
  `indexA` / `indexB` cross-checks, the v10 string lookup table and
  every node's binary layout — sizable reverse-engineering project.

See the [Troubleshooting page](https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/troubleshooting/)
for fixes to common runtime issues.

---

## Developing

The parser sub-package has no Blender dependency, so you can iterate
on it with plain Python:

```powershell
python tests/test_parser.py
python tests/test_data_integrity.py
```

CI runs the same tests on Python 3.10 and 3.11 against every push.

After Blender-side edits, **F3 → Reload Scripts** reloads every
sub-module without restarting Blender (the package's `__init__.py` is
reload-aware).

For more, see the
[Development guide](https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/development/)
and [Contributing](wiki/Contributing.md).

---

## Releasing

Push a tag and the workflow does the rest:

```powershell
git tag v0.3.1
git push origin v0.3.1
```

`.github/workflows/release.yml` builds the zip, runs the parser smoke
test, creates a GitHub Release, and attaches the asset.

---

## Credits & licence

Format reverse-engineered originally by
[ndevenish/Blender_ioEDM](https://github.com/ndevenish/Blender_ioEDM)
and documented in their
[EDM Specification](https://ndevenish.github.io/Blender_ioEDM/EDM_Specification.html).

DCS World and the EDM format are property of Eagle Dynamics SA. This
add-on is community-developed and not affiliated with or endorsed by
Eagle Dynamics. Released under the [MIT license](LICENSE).
