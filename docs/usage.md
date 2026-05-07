---
title: Usage
layout: default
nav_order: 3
permalink: /usage/
---

# Usage
{: .no_toc }

Once the add-on is installed and enabled, importing an EDM model is a
two-step process: pick the file, choose the options.
{: .fs-5 .fw-300 }

1. TOC
{:toc}

---

## The import dialog

**File → Import → DCS World EDM (.edm)**

The right-hand panel exposes every option that affects the import. All
of them have sensible defaults, so for a quick "just see the model"
import you can leave everything as-is.

### Scene group

| Option              | Default | What it does                                                                                        |
| ------------------- | :-----: | --------------------------------------------------------------------------------------------------- |
| **DCS Y-up Correction** | On  | Rotates the model -90° around X so DCS Y-up models stand upright in Blender's Z-up world.       |
| **Wrap in Collection**  | On  | Puts every imported object inside a Collection named after the file. Easy to hide / select all. |

### Geometry group

| Option                    | Default | What it does                                                                       |
| ------------------------- | :-----: | ---------------------------------------------------------------------------------- |
| **Import Collision Shells** | Off | Also import the (normally invisible) collision shell meshes, displayed as wireframes. |

### Rig & Animation group

| Option                | Default | What it does                                                                                                              |
| --------------------- | :-----: | ------------------------------------------------------------------------------------------------------------------------- |
| **Build Armature**    | On      | Create one armature bone per animating or skin-bound node, placed at its correct rest pose from the parent chain.        |
| **Import Animations** | On      | Generate one keyframe action per DCS argument, stacked into NLA tracks. Visibility actions go on the relevant mesh objects. |

### Extras group

| Option                | Default | What it does                                                                                |
| --------------------- | :-----: | ------------------------------------------------------------------------------------------- |
| **Import Lights**     | On      | Create Blender point lights from EDM `LightNode` entries.                                  |
| **Import Connectors** | On      | Create Empty (Cube display) objects from EDM `Connector` entries (gun points, hardpoints…).|

### Textures group

| Option                  | Default | What it does                                                                                                                              |
| ----------------------- | :-----: | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **Extra Texture Folder** | empty   | Optional extra search root used **before** the standard DCS install paths. Useful when working with a stand-alone mod folder.            |

## Texture search order

The importer tries each location below in order, picking the first hit
for each unique texture name. Supported extensions: `.dds`, `.png`,
`.tga`, `.bmp`, `.jpg`.

1. The folder containing the `.edm`
2. `<edm-folder>/textures/`, `<edm-folder>/../textures/`,
   `<edm-folder>/../../textures/`, `<edm-folder>/Bazar/World/textures/`
3. The user-supplied **Extra Texture Folder**
4. `C:\Program Files\Eagle Dynamics\DCS World\Bazar\World\textures\`
5. `C:\Program Files\Eagle Dynamics\DCS World OpenBeta\Bazar\World\textures\`
6. `C:\Program Files (x86)\Steam\steamapps\common\DCSWorld\Bazar\World\textures\`
7. A few additional D:/E:-drive variants

{: .note }
Texture lookup is case-insensitive and cached per import session, so
repeated misses in large modules don't slow things down.

## What you get in the outliner

After a successful import, you'll see (typically, inside one Collection):

- **`<model>_rig`** — the armature object. Bones are named after the
  EDM scene node they came from.
- **Mesh objects** — one per `RenderNode` (or per `RenderNode` slice
  when an node has multiple parent entries). Skinned meshes have an
  `Armature` modifier already wired up to the rig.
- **Connectors** — Empty (Cube) objects, named after their connector
  (`Gun_point`, `AIR_REFUELING_RECEPTACLE`, …).
- **Lights** — `POINT` lights, parented to the relevant rig bone if any.

Each object has a number of `edm_*` custom properties:

| Property              | What it means                                                              |
| --------------------- | -------------------------------------------------------------------------- |
| `edm_node_type`       | The EDM node class that produced this object (`RenderNode`, `Connector`…). |
| `edm_parent_node`     | The scene-graph index of the immediate parent in the original file.        |
| `edm_damage_arg`      | Damage argument index, or `-1` for parts unaffected by damage modelling.   |
| `edm_is_collision`    | `True` for objects coming from `ShellNode` collision meshes.               |
| `edm_lod_min`         | Minimum LOD distance (metres) for this part, when its ancestors include a `LodNode`. |
| `edm_lod_max`         | Maximum LOD distance for the same.                                         |
| `edm_name`            | The original EDM node name, before Blender deduplicated it.                |

## Working with animations

Animations are imported as **NLA strips** with all tracks **muted** by
default (so the F-curve editor doesn't drown you in 50 simultaneous
animations). To preview a single animation:

1. Open the NLA editor.
2. Find the track named `<model>_arg<NN>` (e.g. `f-16c_bl50_arg002` for
   DCS argument 2 — elevator).
3. Click the speaker icon next to the track to un-mute it.
4. Scrub the timeline. Argument value `0` is at frame 1, value `1` at
   frame 101.

The NLA action also stores the original argument number in a custom
property (`edm_argument`) so scripts can rediscover it programmatically:

```python
import bpy
for action in bpy.data.actions:
    arg = action.get("edm_argument")
    if arg is not None:
        print(f"{action.name} drives DCS argument {arg}")
```

## Working with damage parts

`damage_arg` on EDM render nodes encodes which DCS damage argument
should hide the part when the corresponding damage state activates.
You can hide every "damage 1" part with one Python snippet:

```python
import bpy
for obj in bpy.context.scene.objects:
    if obj.get("edm_damage_arg", -1) >= 0:
        obj.hide_set(True)
```

## Importing many files at once

The Import dialog supports multi-selection — pick several `.edm` files
in one go and the operator imports each into its own Collection.
