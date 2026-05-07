# Quick Start

Get your first DCS aircraft into Blender in under a minute.

## 1. Install the add-on

Download the latest pre-built zip:
**[Releases page →](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/releases/latest)**

In Blender:

1. **Edit → Preferences → Add-ons → Install…**
2. Pick `dcs_edm_importer-<version>.zip`.
3. Tick the **DCS World EDM Importer** check-box.

## 2. Import your first model

1. **File → Import → DCS World EDM (.edm)**.
2. Navigate into your DCS install (default options work for most files):
   - `C:\Program Files\Eagle Dynamics\DCS World\Mods\aircraft\F-16C\Shapes\f-16c_bl50.edm`
3. Click **Import**.

The first import takes a few seconds — Blender is parsing the file,
loading textures, building meshes, materials and the rig.

## 3. Find your model

It lands in a new Collection named after the file. The Outliner shows:

- `<model>_rig` — the armature (one bone per animating part).
- A long list of mesh objects — one per render node.
- Empty (Cube) objects — connectors / hardpoints.
- POINT lights — light nodes.

## 4. Preview an animation

DCS encodes every animation as an "argument" (e.g. `arg 0` = aileron).
Each argument becomes one Blender action:

1. Open the **NLA editor**.
2. Find the track called `<model>_arg002` (DCS argument 2 = elevator).
3. Click the speaker icon to **un-mute** the track.
4. Press the spacebar — the elevator deflects.

## 5. Tinker

Every imported object has a handful of `edm_*` custom properties
visible in the **Object Properties → Custom Properties** panel —
including `edm_damage_arg`, `edm_lod_min`, `edm_lod_max`. Useful when
you want to filter or hide specific kinds of geometry.

That's it! For deeper details, see
[the full docs](https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/usage/).
