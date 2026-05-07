"""
Top-level orchestration of an EDM import.

This module wires the parser, mesh builder, material builder, armature
builder and extras together. It is intentionally written as a small set
of small functions so most callers will only ever hit
:func:`import_edm`.

Logical phases:

1. **Parse** the file into :class:`ParsedEDM`.
2. **Prepare** the destination collection and the global axis matrix.
3. **Resolve** textures / build the texture cache.
4. **Build the rig** from animating nodes, if requested.
5. **Build geometry** (RenderNode, SkinNode, optional ShellNode).
6. **Parent meshes** onto the rig if there's an animating ancestor.
7. **Place extras** (connectors, lights).
8. **Apply visibility actions** to the right Blender objects.

Each phase is a private function and reports a one-line status to the
console so the user can see what happened.
"""

from __future__ import annotations

import os
import time
import traceback
from typing import Dict, List, Optional, Sequence

import bpy
import mathutils

from ..edm import parse_edm, types as t
from ..edm.parser import EDMParseError
from .armature import ArmatureBuilder, apply_visibility_actions
from .extras import create_connector, create_light
from .materials import MaterialBuilder
from .meshes import MeshBuilder
from .textures import TextureResolver
from . import transforms as xf


# ---------------------------------------------------------------------------
#  Options
# ---------------------------------------------------------------------------


class ImportOptions:
    """Container for the operator's bool/enum settings.

    Attributes
    ----------
    import_shells : bool
        Also import collision shell nodes (hidden in the viewport).
    import_lights : bool
        Create Blender lights from LightNode entries.
    import_connectors : bool
        Create Empty objects from Connector entries.
    import_rig : bool
        Build an armature from animating nodes (recommended).
    import_animations : bool
        Generate keyframe actions for the rig.
    apply_y_up : bool
        Rotate the imported model -90° around X (DCS Y-up -> Blender Z-up).
    create_collection : bool
        Wrap everything in a Collection named after the file.
    extra_texture_paths : list[str]
        Optional extra directories to search for textures.
    """
    __slots__ = (
        "import_shells",
        "import_lights",
        "import_connectors",
        "import_rig",
        "import_animations",
        "apply_y_up",
        "create_collection",
        "extra_texture_paths",
    )

    def __init__(
        self,
        import_shells: bool = False,
        import_lights: bool = True,
        import_connectors: bool = True,
        import_rig: bool = True,
        import_animations: bool = True,
        apply_y_up: bool = True,
        create_collection: bool = True,
        extra_texture_paths: Optional[Sequence[str]] = None,
    ):
        self.import_shells = import_shells
        self.import_lights = import_lights
        self.import_connectors = import_connectors
        self.import_rig = import_rig
        self.import_animations = import_animations
        self.apply_y_up = apply_y_up
        self.create_collection = create_collection
        self.extra_texture_paths = list(extra_texture_paths or [])


# ---------------------------------------------------------------------------
#  Public entry point
# ---------------------------------------------------------------------------


def import_edm(
    context: bpy.types.Context,
    filepath: str,
    options: Optional[ImportOptions] = None,
) -> set:
    """Run a full EDM import. Returns the operator return-set."""
    options = options or ImportOptions()
    started_at = time.time()
    print(f"\n[EDM] Importing {filepath!r}")

    try:
        parsed = parse_edm(filepath)
    except EDMParseError as exc:
        print(f"[EDM] Parse error: {exc}")
        return {"CANCELLED"}
    except (OSError, IOError) as exc:
        print(f"[EDM] I/O error: {exc}")
        return {"CANCELLED"}
    except Exception:
        traceback.print_exc()
        return {"CANCELLED"}

    model_name = os.path.splitext(os.path.basename(filepath))[0]
    print(
        f"[EDM]   v{parsed.version}  materials={len(parsed.materials)}  "
        f"render_nodes={len(parsed.render_nodes)}  "
        f"shell_nodes={len(parsed.shell_nodes)}  "
        f"lights={len(parsed.light_nodes)}  "
        f"connectors={len(parsed.connectors)}  "
        f"scene_nodes={len(parsed.nodes)}"
    )

    collection = _make_collection(context, model_name, options)
    axis_mat = xf.axis_correction_matrix("Y" if options.apply_y_up else "Z")
    resolver = TextureResolver(filepath, options.extra_texture_paths)

    material_builder = MaterialBuilder(resolver)

    arm_builder: Optional[ArmatureBuilder] = None
    if options.import_rig:
        try:
            arm_builder = ArmatureBuilder(parsed.nodes, axis_mat, collection, model_name)
            arm_builder.build()
        except Exception:
            print("[EDM] Warning: rig build failed; continuing without armature.")
            traceback.print_exc()
            arm_builder = None

    mesh_builder = MeshBuilder(
        materials=parsed.materials,
        material_builder=material_builder,
        collection=collection,
        nodes=parsed.nodes,
        axis_mat=axis_mat,
    )

    obj_for_node: Dict[int, bpy.types.Object] = {}
    n_meshes = 0

    for i, node in enumerate(parsed.render_nodes):
        if isinstance(node, t.RenderNode):
            objs = mesh_builder.build_render_node(node, f"{model_name}_render_{i:04d}")
        elif isinstance(node, t.SkinNode):
            objs = mesh_builder.build_skin_node(node, f"{model_name}_skin_{i:04d}")
        else:
            objs = []
        for obj in objs:
            n_meshes += 1
            _maybe_parent_to_bone(obj, parsed.nodes, arm_builder, obj_for_node)

    if options.import_shells:
        for i, node in enumerate(parsed.shell_nodes):
            if isinstance(node, t.ShellNode):
                objs = mesh_builder.build_shell_node(node, f"{model_name}_shell_{i:04d}")
                for obj in objs:
                    n_meshes += 1
                    _maybe_parent_to_bone(obj, parsed.nodes, arm_builder, obj_for_node)

    n_connectors = 0
    if options.import_connectors:
        for connector in parsed.connectors:
            if isinstance(connector, t.Connector):
                obj = create_connector(connector, parsed.nodes, axis_mat, collection)
                _maybe_parent_to_bone(obj, parsed.nodes, arm_builder, obj_for_node)
                n_connectors += 1

    n_lights = 0
    if options.import_lights:
        for light in parsed.light_nodes:
            if isinstance(light, t.LightNode):
                obj = create_light(light, parsed.nodes, axis_mat, collection)
                if obj is not None:
                    _maybe_parent_to_bone(obj, parsed.nodes, arm_builder, obj_for_node)
                    n_lights += 1

    if options.import_animations and arm_builder is not None:
        try:
            apply_visibility_actions(parsed.nodes, obj_for_node, model_name)
        except Exception:
            print("[EDM] Warning: visibility action build failed.")
            traceback.print_exc()

    # Restore object mode and select the new collection's root for clarity.
    if context.object is not None:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    if arm_builder and arm_builder.armature is not None:
        context.view_layer.objects.active = arm_builder.armature

    elapsed = time.time() - started_at
    print(
        f"[EDM] Done in {elapsed:.2f}s  "
        f"meshes={n_meshes}  lights={n_lights}  connectors={n_connectors}"
    )
    return {"FINISHED"}


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------


def _make_collection(
    context: bpy.types.Context,
    model_name: str,
    options: ImportOptions,
) -> bpy.types.Collection:
    if not options.create_collection:
        return context.scene.collection
    coll = bpy.data.collections.new(model_name)
    context.scene.collection.children.link(coll)
    return coll


def _maybe_parent_to_bone(
    obj: bpy.types.Object,
    nodes: Sequence,
    arm_builder: Optional[ArmatureBuilder],
    obj_for_node: Dict[int, bpy.types.Object],
) -> None:
    """Parent ``obj`` to the right armature bone if there's an animating ancestor.

    Also records a node->object mapping for later visibility-action wiring.
    """
    parent_node = int(obj.get("edm_parent_node", -1))
    if parent_node >= 0:
        # Use the *parent* (not the object itself) so that visibility
        # actions can be hooked even if the parent is the visibility node
        # rather than an arg-anim node.
        obj_for_node[parent_node] = obj

    if arm_builder is None or arm_builder.armature is None:
        return

    anim_idx = xf.find_animating_ancestor(parent_node, nodes)
    if anim_idx < 0 or anim_idx not in arm_builder.bone_for_node:
        return

    arm = arm_builder.armature
    bone_name = arm_builder.bone_for_node[anim_idx]

    # Preserve the world placement we computed earlier even after we
    # change the parenting hierarchy.
    world_mat = obj.matrix_world.copy()
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    bone = arm.data.bones.get(bone_name)
    if bone is not None:
        # Compose the inverse so that obj stays put visually while the
        # bone's rest pose now "owns" its placement.
        obj.matrix_parent_inverse = (
            arm.matrix_world @ bone.matrix_local
        ).inverted()
    obj.matrix_world = world_mat
