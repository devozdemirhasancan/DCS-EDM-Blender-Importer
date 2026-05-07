---
title: EDM Format Primer
layout: default
nav_order: 5
permalink: /format/
---

# EDM Format Primer
{: .no_toc }

A practical summary of the binary format you'll need to understand if
you want to extend the parser, debug a misbehaving import, or write
new tooling around `.edm` files.
{: .fs-5 .fw-300 }

This page condenses the [official spec](https://ndevenish.github.io/Blender_ioEDM/EDM_Specification.html);
read that for the absolute reference.

1. TOC
{:toc}

---

## Container

Every .edm file starts with a small header followed by a flat list of
named types:

```
b'EDM'                  // magic, 3 bytes
ushort  version;        // 8 or 10 — both supported
[ if version == 10:
  uint    lookupSize;
  byte    lookup[lookupSize];   // null-separated UTF-8/win-1251 strings
]
map<string,uint>   indexA;      // type-name → count cross-check
map<string,uint>   indexB;      // ditto for sub-types
named_type         rootNode;    // always model::RootNode
uint               nodeCount;
named_type         nodes[nodeCount];   // transform & animation graph
uint               parents[nodeCount]; // parent index per node
map<string, list<named_type>>  renderItems;
```

Everything is **little-endian**. Strings in v8 are length-prefixed
windows-1251 byte sequences; in v10 they are uint indices into the
file-global lookup table loaded right after the magic.

## Math types

| Type           | Layout                          | Notes                          |
| -------------- | ------------------------------- | ------------------------------ |
| `osg::Vec3d`   | 3 doubles                       | World coordinates / positions  |
| `osg::Matrixd` | 16 doubles, **column-major**    | Transposed for Blender         |
| `osg::Matrixf` | 16 floats, **column-major**     | Texture matrices               |
| `osg::Quaternion` | 4 floats `xyzw`             | Reordered to `wxyz` for Blender |

## Node types

The parser handles every type in the spec, plus a few that don't appear
in the public spec but are observed in real files (`NumberNode`).

### Transform / animation graph

| Type                  | What it represents                                                 |
| --------------------- | ------------------------------------------------------------------ |
| `model::Node`         | Empty / passthrough.                                              |
| `model::TransformNode`| Static 4x4 matrix.                                                 |
| `model::Bone`         | Two matrices (m1 = local pose, m2 = inverse bind for skinning).    |
| `model::LodNode`      | Distance bands; each child node is one LOD level.                  |
| `model::BillboardNode`| Camera-aligned attachment (154 opaque bytes after the header).     |
| `model::ArgAnimationNode`        | Generic argument-driven transform animation.            |
| `model::ArgPositionNode`/`Rotation`/`Scale` | Same payload as ArgAnimation, narrower.       |
| `model::ArgAnimatedBone`         | ArgAnimationNode + extra bone matrix for skinning.      |
| `model::ArgVisibilityNode`       | Per-argument hide/show ranges (no transform).            |

### Render items

| Type                          | What it represents                                |
| ----------------------------- | ------------------------------------------------- |
| `model::RenderNode`           | Standard renderable mesh.                         |
| `model::SkinNode`             | Mesh skinned to a list of bones.                  |
| `model::ShellNode`            | Collision shell mesh (own embedded vertex format).|
| `model::SegmentsNode`         | Line segments (rare).                             |
| `model::FakeOmniLightsNode` / `FakeSpotLightsNode` / `FakeALSNode` | Light-FX placeholders. |
| `model::LightNode`            | Real light source.                                |
| `model::Connector`            | Named attachment point.                           |

### Common header

Every node-derived type starts with the same five fields:

```
uint_string   name;
uint          version;
uint          props_count;
named_type    props[props_count];   // PropertiesSet
```

This is what `EDMFileParser._read_base_node` consumes.

## Materials

Each material is a `map<string, X>` where the value type depends on the
key. The parser dispatches on the key string in `_apply_material_key`:

| Key                              | Value                | What we do with it                                                            |
| -------------------------------- | -------------------- | ------------------------------------------------------------------------------ |
| `MATERIAL_NAME`                  | string               | Drives the Principled BSDF preset (`glass_material`, `chrome_material`, …).   |
| `NAME`                           | string               | Final Blender material name.                                                  |
| `BLENDING`                       | uchar enum           | 0=opaque, 1=blend, 2=alpha-test, 3=additive blend.                            |
| `CULLING`                        | uchar                | Whether to enable backface culling.                                           |
| `VERTEX_FORMAT`                  | `count + uchar[N]`   | Channel sizes; drives `MeshBuilder._extract_attributes`.                      |
| `TEXTURE_COORDINATES_CHANNELS`   | `count + uint[N]`    | Per-texture UV-channel mask. Mostly `-1` (unused).                            |
| `TEXTURES`                       | list                 | Texture entries (index, filename, transform matrix).                          |
| `UNIFORMS`                       | PropertiesSet        | Static shader uniforms (`specFactor`, `selfIlluminationColor`, …).            |
| `ANIMATED_UNIFORMS`              | PropertiesSet        | Argument-driven uniforms (limited support today).                             |
| `SHADOWS` / `DECAL` / `…`        | uchar                | Misc render flags, mostly preserved as `mat["edm_*"]` custom props.           |

## Vertex format channels

Channels are indexed by their position in the format's `uchar` array.
The most common channels:

| Index | Size | Meaning                                                             |
| :---: | :--: | ------------------------------------------------------------------- |
|   0   |   4  | Position. The 4th float references the parent index for splitting.  |
|   1   |   3  | Normals.                                                            |
|   4   |   2  | UV0 (primary texture). V is mirrored on read.                       |
|   5   |   2  | UV1 (decals / secondary).                                           |
|   6-8 |   2  | Additional UV layers (rare).                                        |
|  20   |   3  | Reserved.                                                           |
|  21   |   8  | Bone indices (4 floats) + bone weights (4 floats), interleaved.     |

Total stride is `sum(channels)`. Most files use stride 26 or stride 9
(position + normal + UV0 only).

## RenderNode "PARENTDATA"

When a `RenderNode` lists more than one parent (DCS optimises by merging
geometry that shares a material), the structure is:

```
uint   count;            // > 1
struct PARENT_ENTRY {
    uint   parent_node_idx;
    int    indexStart;
    int    damage_arg;    // -1 for non-damage parts
} parents[count];
```

The importer slices the index buffer at each `indexStart` to produce
one Blender object per parent — that way each part can have its own
`edm_damage_arg` custom property, separate animation parenting, etc.

## Index buffer

```
uchar  data_type;     // 0 = uchar, 1 = ushort, 2 = uint
uint   entries;
uint   unknown;       // 0, 1 or 5 — never used downstream
INDEXVALUE  indices[entries];
```

The size of `INDEXVALUE` is determined by `data_type`; small meshes
fit in `uchar`, mid-size in `ushort`, and full-aircraft pieces use
`uint`.

## Animation argument frames

EDM stores keyframes with double-precision frames in the
[0, 1] range. We map them into Blender's integer frame space by:

```
blender_frame = round(arg_value * 100) + 1
```

So argument value 0 lands on frame 1 and argument value 1 lands on
frame 101. Negative values are allowed for some controls and produce
negative frames, which Blender supports.
