"""
DCS World EDM Importer for Blender 4.x
======================================

A Blender add-on that imports Eagle Dynamics' proprietary ``.edm`` model
files (used by DCS World) into the current scene, complete with:

  * Geometry, normals, UVs and materials
  * MATERIAL_NAME-aware shader presets (glass, chrome, self-illuminated)
  * Texture auto-resolution (DCS install heuristics)
  * Armature with one bone per animating node
  * Per-argument animation actions, stacked in NLA tracks
  * Visibility animations (ArgVisibilityNode)
  * Connectors as Empties, LightNodes as Blender Lights
  * Optional collision shell import

The implementation is split across these modules:

  * :mod:`dcs_edm_importer.edm`     -- pure-Python EDM parser
  * :mod:`dcs_edm_importer.blender` -- Blender scene construction
  * :mod:`dcs_edm_importer.ui`      -- File -> Import operator

Reload-friendly: when the user hits "Reload Scripts" Blender re-imports
this package; we walk our own sub-modules and reload them too so changes
made in the source tree take effect without restarting Blender.
"""

bl_info = {
    "name": "DCS World EDM Importer",
    "author": "devozdemirhasancan",
    "version": (0, 3, 0),
    "blender": (4, 0, 0),
    "location": "File > Import > DCS World EDM (.edm)",
    "description": (
        "Import DCS World EDM 3D model files with materials, textures, "
        "rig, skin weights and DCS-argument-driven animations."
    ),
    "warning": "",
    "doc_url": "https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/",
    "tracker_url": "https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/issues",
    "category": "Import-Export",
}


# ---------------------------------------------------------------------------
#  Reload-aware module loading
# ---------------------------------------------------------------------------
#
# Blender reloads add-ons by re-executing __init__.py, but does NOT
# reload sub-modules. Any time the user hits the "Reload Scripts" button
# we therefore walk our own sub-package and reload manually, which keeps
# the developer feedback-loop tight.

if "bpy" in locals():
    import importlib

    _modules = (
        "edm.reader",
        "edm.types",
        "edm.parser",
        "edm",
        "blender.transforms",
        "blender.textures",
        "blender.materials",
        "blender.meshes",
        "blender.armature",
        "blender.extras",
        "blender.importer",
        "blender",
        "ui.operator",
        "ui",
    )
    for _name in _modules:
        _full = __name__ + "." + _name
        _mod = locals().get(_name.split(".")[-1])
        if _mod is None:
            try:
                _mod = importlib.import_module(_full)
            except Exception:
                continue
        try:
            importlib.reload(_mod)
        except Exception as exc:
            print(f"[EDM] reload skipped: {_full} ({exc})")

import bpy

from .ui import register_ui, unregister_ui


def register():
    register_ui()


def unregister():
    unregister_ui()


if __name__ == "__main__":
    register()
