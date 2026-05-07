# DCS World EDM Importer for Blender 4.x

Blender 4.0 / 4.1 / 4.2+ add-on that imports DCS World `.edm` model files
(aircraft, cockpits, world objects) into the current scene, complete with
geometry, materials, textures, an armature, and DCS-argument-driven
animations.

> **Türkçe:** Eagle Dynamics tarafından geliştirilen DCS World'ün özel
> `.edm` 3B model formatını Blender 4.x'e modüler bir eklenti ile
> içe aktarır. Geometri, malzemeler, dokular, kemik (rig) yapısı ve DCS
> argüman tabanlı animasyonlar tek tıklamada içeri çekilir.

---

## Highlights

| What | v0.1 (single file) | **v0.2 (modular)** |
|------|--------------------|---------------------|
| Geometry, normals, UVs            | ✅ | ✅ |
| Texture auto-resolution           | ✅ | ✅ (cached, faster, more search paths) |
| Materials                         | basic Principled BSDF | **MATERIAL_NAME-aware** (glass / chrome / self-illum / mirror presets), spec map inverted to roughness |
| **UV V-flip** for DDS textures    | ❌ | ✅ |
| **Parent-chain world transforms** | ❌ (used only for mirror detection) | ✅ — animated parts land in the correct default pose |
| **Multi-parent RenderNode split** | ❌ | ✅ (per-part objects with damage-arg metadata) |
| Armature / rig                    | partial | bone per animating node, NLA stacks |
| Animations (pos / rot / scale)    | ❌ | ✅ per-argument actions |
| Visibility animations             | ❌ | ✅ `hide_render` action per argument |
| Connectors                        | ❌ | ✅ Empty objects, Cube display |
| Light nodes                       | ❌ | ✅ Blender point lights |
| Collision shells                  | optional | optional, wireframe display |
| Code organisation                 | 1167-line single file | 12 small modules + standalone test suite |

---

## Installation

### Option 1 — Pre-built zip (recommended)

```powershell
# in the project root
.\build.ps1
# → build/dcs_edm_importer-0.2.0.zip
```

In Blender: `Edit ▸ Preferences ▸ Add-ons ▸ Install…` and pick the zip.
Enable the **DCS World EDM Importer** check-box.

### Option 2 — Manual copy

Copy the `dcs_edm_importer/` folder into Blender's add-ons directory:

| OS | Default path |
|----|--------------|
| Windows | `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\` |
| macOS   | `~/Library/Application Support/Blender/<version>/scripts/addons/` |
| Linux   | `~/.config/blender/<version>/scripts/addons/` |

Restart Blender and enable the add-on.

---

## Usage

`File ▸ Import ▸ DCS World EDM (.edm)`

The dialog exposes:

- **DCS Y-up Correction** — rotate -90° around X so DCS Y-up models stand
  upright in Blender's Z-up world (default ON).
- **Wrap in Collection** — group everything inside a Collection named
  after the file (default ON).
- **Import Collision Shells** — also import the (normally invisible)
  collision shells; they're shown as wireframes (default OFF).
- **Build Armature** — create one bone per animating node (default ON).
- **Import Animations** — generate keyframe actions for every DCS
  argument referenced by the model (default ON).
- **Import Lights** — create Blender Point lights from `LightNode`
  entries (default ON).
- **Import Connectors** — create Empty objects from `Connector` entries
  (default ON).
- **Extra Texture Folder** — extra search root if your textures live
  outside the standard DCS install paths.

Multi-file selection in the Import dialog imports each file in turn.

### Texture search order

1. The folder containing the `.edm`
2. `<edm-folder>/textures/`, `<edm-folder>/../textures/`,
   `<edm-folder>/../../textures/`, `Bazar/World/textures/`
3. The user-supplied **Extra Texture Folder**
4. Standard DCS install paths:
   - `C:\Program Files\Eagle Dynamics\DCS World\…`
   - `C:\Program Files\Eagle Dynamics\DCS World OpenBeta\…`
   - `C:\Program Files (x86)\Steam\steamapps\common\DCSWorld\…`
   - and a few D:/E:-drive variants

Supported formats: `.dds`, `.png`, `.tga`, `.bmp`, `.jpg`.

---

## File layout

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
│   ├── meshes.py          # mesh + UV flip + multi-parent split
│   ├── armature.py        # rig + per-argument NLA actions
│   ├── extras.py          # connectors, light nodes
│   └── importer.py        # top-level orchestration
│
└── ui/
    └── operator.py        # ImportHelper File→Import operator
```

The split lets you:

- **Reuse the parser** outside Blender (see `tests/test_parser.py`).
- **Hot-reload** any module without restarting Blender (`__init__.py`
  detects re-execution and reloads sub-modules).
- **Replace pieces** independently — for example you can swap
  `MaterialBuilder` for a node-group-based shader without touching the
  parser.

---

## Tested files

| File | Module | Result |
|------|--------|--------|
| `f-16c_bl50.edm` (72 MB)     | F-16C Viper | ✅ Full import (296 render nodes, 16 lights, 20 connectors, 297 materials) |
| `f-16c_bl50_ED.edm` (48 MB)  | F-16C Viper (ED-modified) | ⚠️ Partial (NumberNode body layout outside the public spec; first 11 SkinNodes import correctly, then the category recovers gracefully) |

---

## Known limitations

- **Skin weights are not yet applied to vertex groups.** Skinned meshes
  import as static geometry parented to their first bone.
- **Animation transform chain** (the `tf_Matrix · Translate · Quat1 ·
  KeyRot · Scale` formula from the EDM spec) is applied as a simple
  per-bone keyframe stream. Visually correct for hinge / slide motions
  but may drift on parts whose `quat2` is non-identity.
- **NumberNode body layout** is undocumented and varies between source
  files; on files where it differs from the simple base + uint shape we
  recover gracefully but stop importing further render-items in that
  category.
- **No EDM export.** The intent is round-trip to and from Blender, but
  writing valid index-A / index-B tables and material blobs requires
  more reverse-engineering than parsing did.

---

## Developer notes

The parser is fully driven by a dispatch table; adding a new EDM node
type is one method on `EDMFileParser` and one entry in
`_build_dispatch`. The pure-Python `dcs_edm_importer.edm` package has no
dependencies beyond the Python stdlib, so you can run
`python tests/test_parser.py` to smoke-test against any new files.

Re-build the install zip with `.\build.ps1` after edits.

---

## Credits & licence

Format reverse-engineered originally by
[ndevenish/Blender_ioEDM](https://github.com/ndevenish/Blender_ioEDM)
and documented in their
[EDM Specification](https://ndevenish.github.io/Blender_ioEDM/EDM_Specification.html).

DCS World and the EDM format are property of Eagle Dynamics SA. This
add-on is community-developed and not affiliated with or endorsed by
Eagle Dynamics. Released under the MIT license.
