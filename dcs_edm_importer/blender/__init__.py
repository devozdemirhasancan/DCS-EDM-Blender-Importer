"""
dcs_edm_importer.blender
========================

Blender-specific helpers that turn a parsed :class:`ParsedEDM` into a
working scene of meshes, materials, armatures and lights.

Sub-modules deliberately do **not** import each other transitively beyond
what is strictly needed, so individual pieces can be tested in isolation
(e.g. by mocking ``bpy``).
"""

from .importer import import_edm

__all__ = ["import_edm"]
