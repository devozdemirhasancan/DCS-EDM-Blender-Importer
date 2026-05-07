# FAQ

## Can I export models back to .edm?

Not in this version. The importer is read-only. Writing valid EDM
files requires correctly authoring the `indexA` / `indexB` cross-check
tables, the v10 string lookup, every node type's binary layout — all
non-trivial reverse engineering. Pull requests welcome.

## Which Blender versions are supported?

Blender 4.0, 4.1 and 4.2+. Older 3.x versions might work for the
basics but no guarantees — the add-on uses Principled BSDF socket
names that changed in Blender 4.

## Why are some animated parts in slightly the wrong place?

The full EDM animation transform formula
`mat * Translate(pos) * Quat1 * keyRot * Scale * Quat2`
is partially applied. We compose `Quat1` correctly, but `Quat2` is
treated as identity (true for nearly every aircraft). If you see
visible drift, open an issue with the offending file — I'll add a
test fixture.

## Why are textures missing?

The most likely cause is that you're importing an EDM whose textures
live somewhere outside the standard DCS install paths. Use the
**Extra Texture Folder** option on the import dialog to point at the
right directory.

If textures are still missing, run Blender from a terminal (or open
the system console on Windows) and look for `[EDM] Texture not found`
lines — they tell you exactly which file the importer expected.

## Why is the model upside-down?

You probably turned off **DCS Y-up Correction** by accident. Re-import
with that option on. DCS uses Y-up internally; Blender uses Z-up; we
need a -90° X rotation to bridge the two.

## Why does my SkinNode mesh follow the rig in T-pose but not deform when I animate?

The SkinNode references bones by index. If any of the referenced
bones aren't in the armature, the mesh has no vertex group to attach
to those weights. Most often this happens when a `Bone` node is
filtered out — open an issue with the file so we can extend the
"include in rig" rule.

## Can I import multiple .edm files at once?

Yes — the import dialog supports multi-selection. Each file lands in
its own Collection.

## Where do imported textures end up?

They're loaded as Blender Image data-blocks. Blender keeps them on
disk at the path the importer found them at; nothing is copied. If
you save the .blend and move the texture, Blender will warn about
"missing image" on next open.

## Does the importer work on Linux / macOS?

The Python parser does. The Blender side does, too — paths use
`os.path.join` throughout. Two caveats:

- The default DCS install paths in `textures.py` are Windows-style.
  Use **Extra Texture Folder** on Linux/macOS to point at where the
  textures actually live.
- `build.ps1` is PowerShell. On Linux/macOS use the `zip-build` step
  from `.github/workflows/ci.yml` as a template.

## How do I report a bug?

Open an issue at
<https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/issues>
and include:

1. The .edm file (or a small reproducer).
2. The full system console output of the import (look for `[EDM]`
   lines and tracebacks).
3. Your Blender version.
4. The `git log -1 --oneline` of the add-on if you built from source.

A 30-second screencast helps a lot for visual issues.
