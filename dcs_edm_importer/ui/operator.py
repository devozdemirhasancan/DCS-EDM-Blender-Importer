"""
Blender import operator.

Exposes ``import_scene.dcs_edm`` and a "DCS World EDM (.edm)" entry in
the File -> Import menu. Operator properties are forwarded into an
:class:`ImportOptions` instance, so the UI and the programmatic API
share the exact same surface.
"""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, StringProperty
from bpy.types import Operator, OperatorFileListElement
from bpy_extras.io_utils import ImportHelper

from ..blender.importer import ImportOptions, import_edm


class EDM_OT_Import(Operator, ImportHelper):
    """Import a DCS World EDM (.edm) model into the current scene."""

    bl_idname = "import_scene.dcs_edm"
    bl_label = "Import DCS World EDM"
    bl_description = "Import one or more DCS World .edm model files"
    bl_options = {"UNDO", "PRESET"}

    filename_ext = ".edm"
    filter_glob: StringProperty(default="*.edm;*.EDM", options={"HIDDEN"})

    files: CollectionProperty(
        name="File Path",
        type=OperatorFileListElement,
    )
    directory: StringProperty(subtype="DIR_PATH")

    # ----- import options exposed as Blender properties --------------------
    apply_y_up: BoolProperty(
        name="DCS Y-up Correction",
        description="Rotate -90° around X so DCS Y-up models stand upright in Blender (Z-up)",
        default=True,
    )
    create_collection: BoolProperty(
        name="Wrap in Collection",
        description="Put all imported objects inside a Collection named after the file",
        default=True,
    )
    import_rig: BoolProperty(
        name="Build Armature",
        description="Create an armature with one bone per animating node",
        default=True,
    )
    import_animations: BoolProperty(
        name="Import Animations",
        description="Generate keyframe actions for DCS argument-driven animations",
        default=True,
    )
    import_shells: BoolProperty(
        name="Import Collision Shells",
        description="Also import invisible collision shell meshes (wireframe display)",
        default=False,
    )
    import_lights: BoolProperty(
        name="Import Lights",
        description="Create Blender point lights from EDM LightNode entries",
        default=True,
    )
    import_connectors: BoolProperty(
        name="Import Connectors",
        description="Create Empty objects from EDM Connector attachments",
        default=True,
    )
    extra_texture_path: StringProperty(
        name="Extra Texture Folder",
        description="Optional additional folder to search for textures",
        default="",
        subtype="DIR_PATH",
    )

    # ----- UI ----------------------------------------------------------
    def draw(self, context):
        layout = self.layout

        col = layout.column(heading="Scene")
        col.prop(self, "apply_y_up")
        col.prop(self, "create_collection")

        col = layout.column(heading="Geometry")
        col.prop(self, "import_shells")

        col = layout.column(heading="Rig & Animation")
        col.prop(self, "import_rig")
        sub = col.column()
        sub.enabled = self.import_rig
        sub.prop(self, "import_animations")

        col = layout.column(heading="Extras")
        col.prop(self, "import_lights")
        col.prop(self, "import_connectors")

        col = layout.column(heading="Textures")
        col.prop(self, "extra_texture_path", text="")

    # ----- execution ------------------------------------------------------
    def execute(self, context):
        options = ImportOptions(
            import_shells=self.import_shells,
            import_lights=self.import_lights,
            import_connectors=self.import_connectors,
            import_rig=self.import_rig,
            import_animations=self.import_animations,
            apply_y_up=self.apply_y_up,
            create_collection=self.create_collection,
            extra_texture_paths=[self.extra_texture_path] if self.extra_texture_path else [],
        )

        # Multi-file import: ImportHelper sets `self.files` for batch picks.
        import os
        directory = self.directory or os.path.dirname(self.filepath)
        targets = [
            os.path.join(directory, f.name) for f in self.files if f.name
        ] or [self.filepath]

        any_failed = False
        for path in targets:
            result = import_edm(context, path, options)
            if "CANCELLED" in result:
                any_failed = True
        if any_failed and len(targets) == 1:
            self.report({"ERROR"}, f"Failed to import {targets[0]}")
            return {"CANCELLED"}
        return {"FINISHED"}


def _menu_func(self, context):
    self.layout.operator(
        EDM_OT_Import.bl_idname,
        text="DCS World EDM (.edm)",
    )


def register():
    bpy.utils.register_class(EDM_OT_Import)
    bpy.types.TOPBAR_MT_file_import.append(_menu_func)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_func)
    bpy.utils.unregister_class(EDM_OT_Import)
