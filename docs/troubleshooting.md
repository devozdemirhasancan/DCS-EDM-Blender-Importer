---
title: Troubleshooting
layout: default
nav_order: 6
permalink: /troubleshooting/
---

# Troubleshooting
{: .no_toc }

Common problems and how to diagnose them. Open Blender's system console
first (Window → Toggle System Console on Windows, or run Blender from a
terminal on macOS / Linux) — the importer prints every interesting
event prefixed with `[EDM]`.
{: .fs-5 .fw-300 }

1. TOC
{:toc}

---

## "Nothing imports / scene is empty"

Check the system console. The most common reasons:

- The file isn't a valid EDM. The parser prints
  `Not an EDM file (magic=...)` when the first three bytes aren't
  `b'EDM'`. (Some users accidentally pick `.edm.bak` or `.7z` files.)
- The EDM version isn't 8 or 10. Newer beta builds occasionally bump
  the version; please [open an issue](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/issues)
  with the file's version number.
- The `.edm` parsed fine but every render node lives under an unknown
  ancestor type. The parser logs `[EDM] Recovered: skipped N bytes...`
  in this case — see "Partial import" below.

## "Textures are missing"

The console will show one warning line per missing texture:

```
[EDM] Texture not found on disk: 'f16_bl50_main_1'
```

Cross-reference the name against your DCS install. Common fixes:

- Set the **Extra Texture Folder** option on the import dialog to a
  mod's `textures/` directory.
- Verify the textures actually exist on disk (some DCS modules ship
  textures inside `.zip` archives that DCS unpacks at runtime).
- The importer searches case-insensitively, but it will not look
  inside .zip files. If your textures are still packed, extract them
  first.

## "Model is upside down / sideways"

DCS uses Y-up internally. The importer applies a -90° X rotation to
correct for Blender's Z-up world by default. If you want raw Y-up
geometry (e.g. for round-tripping back to DCS), turn off the
**DCS Y-up Correction** option on the import dialog.

## "Animated parts are at the origin"

This was the v0.1 behaviour and is fixed in v0.2+ — make sure you're
using the modular package and not the legacy single-file. The parent
chain is now applied to every render node's world matrix.

If you're using v0.2+ and a part is still wrong, it's most likely an
`ArgAnimationNode` whose `quat2` is non-identity (rare, but observed
in some ejection seats). Open an issue with the offending file.

## "Mesh deforms strangely when I scrub the timeline"

The animation transform chain in the spec
(`mat * Translate(pos) * Quat1 * keyRot * Scale`) is partially applied
in this version — keyframe rotations correctly compose with `Quat1`
but `Quat2` and the matrix's translation component are still pending.
For most aircraft control surfaces this is invisible; for parts whose
file-stored rest pose is far from identity it may shift slightly.

Workaround: bake the offending bone, or set the animation track to
muted and use the static rest pose.

## "Partial import: 11 of 319 render nodes" (or similar)

Recovery banner. The console shows:

```
[EDM] Recovered: skipped 3642 bytes of unknown data and resynced to 'model::SkinNode'
[EDM] Recovered: skipped 2325 bytes of unknown data and resynced to 'model::SkinNode'
...
```

The parser hit an unknown layout (typically `model::NumberNode` with
extra render-control data not in the public spec) and scanned forward
to find the next valid render-item type. **As long as the recovery
banner appears, all subsequent items WERE imported** — the warning
about "stopped after N item(s)" only fires when the resync completely
fails.

If the resync fails:

1. Run `python tests/probe_numbernode.py` against the file (the script
   prints a hex dump of the area surrounding the failure).
2. Open an issue with that dump attached.

## "Blender freezes during import"

Very large modules (~70 MB+) take 1-2 seconds to parse and another 3-5
seconds to build all the meshes/materials. If Blender is frozen for
longer than ~30 seconds:

- Are you importing inside a scene with thousands of existing objects?
  The "Wrap in Collection" option helps because it batches all the new
  objects under a single parent.
- Is your DCS install on a slow drive? Texture lookup walks several
  directories; a slow drive turns that into the bottleneck.
- As a fast workaround: turn off **Import Animations** and
  **Import Lights** to skip the most expensive phases.

## "All my materials look like flat gray plastic"

Two likely causes:

1. The textures didn't load (see "Textures are missing" above).
2. The material's `MATERIAL_NAME` is one we don't yet have a preset
   for. The full mapping is in `dcs_edm_importer/blender/materials.py`
   under `_GLASS_MATERIALS`, `_METALLIC_MATERIALS`, etc. PRs welcome
   for new presets!

Even with a missing preset, the diffuse texture should load — check
the material in the Shader editor; if there's an Image node but no
texture, it's a path/permission issue.

## Reporting a bug

When opening an issue, please include:

- The **EDM file** (or a small reproducer if the file is huge).
- The **full console output** from the import — especially any `[EDM]`
  lines and tracebacks.
- Your **Blender version** (`Help → About` or the splash screen).
- Your **OS** and the path you installed DCS to.

A 30-second screencast of the import going wrong is gold for
reproducing GUI-side issues.
