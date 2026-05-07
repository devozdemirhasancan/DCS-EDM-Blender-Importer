# Texture Map

EDM material `TEXTURES` lists carry an integer `index` per texture
that doesn't directly say "diffuse" or "normal" — DCS infers role from
the index value. Here's the canonical mapping.

| Index | Role             | Typical filename hints                                  | Color space |
| :---: | ---------------- | -------------------------------------------------------- | ----------- |
| 0     | Diffuse / albedo | (anything)                                               | sRGB        |
| 1     | Normal map       | `_normal`, `_nm`, sometimes `_bump`                      | Non-Color   |
| 2     | Specular / RoughMet | `_spec`, `_specular`, `_roughmet`                     | Non-Color   |
| 3     | Numerals / decals | `*_bort_number`, `*_numbers`                            | sRGB        |
| 4     | Glass dirt       | `*_glassdirt`                                            | sRGB        |
| 5     | Damage diffuse   | `*_damage`, `*_dam`                                      | sRGB        |
| 8     | Light / emission | `Flame_*`, `BANO`, `*_light`                             | sRGB        |
| 9     | Ambient occlusion (rare) | `*_ao`                                            | Non-Color   |
| 10    | Damage normals   | `*_damage_normal`, `*_glass_damage_nm`                   | Non-Color   |

## What the importer does today

The importer wires up indices **0**, **1**, and **2** automatically:

- Index 0 → Principled BSDF **Base Color** (and **Alpha** if the
  material's `HAS_ALPHA_CHANNEL` flag is set).
- Index 1 → Normal Map node → BSDF **Normal**.
- Index 2 → Invert → BSDF **Roughness** (because EDM stores specular
  brightness, which is roughness inverted).

Indices 3, 4, 5, 8, 9, 10 are **loaded** if they're referenced (the
texture nodes appear in the shader graph) but are **not auto-wired**
— DCS uses these via custom shaders that have no Principled BSDF
equivalent. Drag them onto whatever Mix Shader / Decal node setup you
prefer.

## RoughMet packing

Modern DCS modules use a single "RoughMet" texture that packs three
maps into RGB:

| Channel | Role                |
| :-----: | ------------------- |
| R       | Roughness           |
| G       | Metallic            |
| B       | (unused / ambient)  |

If you see `*_roughmet` filenames, you can:

1. Add a **Separate Color** node after the texture.
2. Wire R → Roughness, G → Metallic.
3. Disconnect the default Invert node the importer added.

This will eventually become an importer option once we add a setting
to identify RoughMet vs. legacy specular materials.
