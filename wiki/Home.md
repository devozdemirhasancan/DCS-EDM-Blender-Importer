# DCS EDM Blender Importer Wiki

> **Tip:** This wiki is auto-synced from the [`wiki/`](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/tree/main/wiki) folder in the main repository. Edit the markdown files there and open a PR — the changes appear here automatically once merged.

A Blender 4.x add-on that imports Eagle Dynamics' DCS World `.edm` 3-D
models into your scene with full materials, textures, rig and
DCS-argument-driven animations.

For the polished, searchable documentation site see
[the GitHub Pages site](https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/).

This wiki is a more informal scratch-pad: file notes, FAQ, screenshots,
community recipes.

## Pages

- [[Quick Start]] — install and import your first model in 60 seconds.
- [[FAQ]] — common questions, common gotchas.
- [[DCS Argument Numbers]] — what each `arg <N>` controls in the major
  modules.
- [[Texture Map]] — which DCS texture goes where (diffuse vs. normal vs.
  roughmet vs. damage map).
- [[Compatibility Matrix]] — known-good module + Blender combinations.
- [[Troubleshooting Recipes]] — copy-paste fixes for the most common
  problems.
- [[Contributing]] — how to add new node types / material presets.

## Quick links

- 📦 [Latest release](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/releases/latest)
- 📚 [Full docs](https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/)
- 🐛 [Open issues](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/issues)
- 💬 [Discussions](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/discussions)

## What's new in v0.2

- ✅ Modular package (12 modules vs. one 1,167-line file)
- ✅ Skin weights via vertex groups + Armature modifier
- ✅ Multi-UV layer support
- ✅ NumberNode resync heuristic (recovers entire models that previously partial-imported)
- ✅ MATERIAL_NAME-aware shader presets (glass, chrome, mirror, self-illum)
- ✅ LOD metadata as object custom properties
- ✅ Connectors → Empty (Cube)
- ✅ LightNode → Blender point light
- ✅ Visibility actions for `ArgVisibilityNode`
- ✅ GitHub Actions for CI + automated releases + Pages + Wiki sync
- ✅ Blender 4.2 Extension manifest

DCS World and the EDM format are property of Eagle Dynamics SA. This
project is community-developed and not affiliated with Eagle Dynamics.
