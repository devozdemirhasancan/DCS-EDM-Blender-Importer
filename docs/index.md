---
title: Home
layout: home
nav_order: 1
description: "Import DCS World EDM models into Blender 4.x with full materials, rig and animations."
permalink: /
---

# DCS EDM Blender Importer
{: .fs-9 }

A Blender 4.x add-on that imports Eagle Dynamics' DCS World `.edm` 3-D
models — geometry, materials, textures, rig and DCS-argument-driven
animations — in a single click.
{: .fs-6 .fw-300 }

[Download the latest release](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/releases/latest){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View on GitHub](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer){: .btn .fs-5 .mb-4 .mb-md-0 }

---

## What you get

- **Geometry** — vertex positions, normals, multi-channel UV layers,
  custom split normals.
- **Materials** — `MATERIAL_NAME`-aware Principled BSDF presets for
  glass, chrome, mirror, self-illuminated, etc.
- **Textures** — automatic resolution against the EDM's directory and
  the standard DCS install paths (`Bazar/World/textures/`, …).
- **Rig** — one armature bone per animating or skin-bound node, placed
  at the correct rest position from the parent chain.
- **Skin weights** — every `SkinNode`'s vertex bones become real Blender
  vertex groups, with an `Armature` modifier so the mesh deforms as
  the rig animates.
- **Animations** — every DCS argument (`arg 0` = aileron, `arg 1` =
  elevator, …) becomes its own action, stacked in NLA tracks ready to
  scrub.
- **Visibility** — `ArgVisibilityNode` becomes a per-object
  `hide_render` action keyed against the same DCS argument.
- **Connectors** — Empty (Cube) attachments for hardpoints, gun points,
  refuel receptacles.
- **Lights** — point lights from `LightNode` entries.
- **LOD metadata** — every mesh records the distance band of its parent
  `LodNode`, queryable via custom properties (`edm_lod_min`,
  `edm_lod_max`).

## Quick start

```bash
git clone https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer.git
cd DCS-EDM-Blender-Importer
.\build.ps1
```

Then in Blender: **Edit → Preferences → Add-ons → Install…** and pick
`build/dcs_edm_importer-<version>.zip`.

Or just download the latest pre-built zip from
[Releases](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/releases/latest).

## Tested files

| File                       | Module          | Result                                                                       |
| -------------------------- | --------------- | ---------------------------------------------------------------------------- |
| `f-16c_bl50.edm` (72 MB)   | F-16C Viper     | ✅ Full import (296 render nodes, 16 lights, 20 connectors, 297 materials) |
| `f-16c_bl50_ED.edm` (48 MB)| F-16C ED-build  | ✅ Full import (319 render nodes via NumberNode resync recovery)            |

## Documentation

- [Installation]({{ site.baseurl }}/installation/) — three install routes
- [Usage]({{ site.baseurl }}/usage/) — every option in the import dialog
- [Architecture]({{ site.baseurl }}/architecture/) — module layout & extension points
- [EDM Format]({{ site.baseurl }}/format/) — primer on the binary format
- [Troubleshooting]({{ site.baseurl }}/troubleshooting/) — common issues
- [Development]({{ site.baseurl }}/development/) — contributing & release process

---

DCS World and the EDM format are property of Eagle Dynamics SA. This
project is community-developed and not affiliated with Eagle Dynamics.
