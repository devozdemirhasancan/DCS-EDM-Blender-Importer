"""
Top-level orchestration of an EDM import.

Wires the parser, mesh builder, material builder, armature builder and
extras together. Most callers only need :func:`import_edm`.

Logical phases:

1. **Parse** the file into :class:`ParsedEDM`.
2. **Prepare** the destination collection, the global axis matrix, and a
   LOD lookup table from any ``LodNode`` entries.
3. **Resolve** textures / build the texture cache.
4. **Build the rig** from animating + bone nodes (if requested).
5. **Build geometry** (RenderNode, SkinNode, optional ShellNode), feeding
   armature info in so SkinNodes get vertex groups + Armature modifiers.
6. **Bind meshes to bones** — a uniform "single vertex group + Armature
   modifier" approach so static and animated meshes follow the rig with
   one mechanism. See :func:`_attach_to_rig`.
7. **Place extras** (connectors, lights), bone-parented when applicable.
8. **Apply visibility actions** to the right Blender objects.
"""

from __future__ import annotations

import os
import time
import traceback
from typing import Dict, List, Optional, Sequence, Tuple

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
    """Container for the operator's bool / enum settings."""
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
    lod_lookup = _build_lod_lookup(parsed.nodes)
    print(f"[EDM]   texture search paths: {len(resolver.search_paths)}")

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
        lod_lookup=lod_lookup,
    )
    if arm_builder is not None:
        mesh_builder.attach_armature(
            arm_builder.armature, arm_builder.bone_for_node
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
            _attach_to_rig(obj, parsed.nodes, arm_builder)
            _record_obj_for_node(obj, obj_for_node)

    if options.import_shells:
        for i, node in enumerate(parsed.shell_nodes):
            if isinstance(node, t.ShellNode):
                objs = mesh_builder.build_shell_node(node, f"{model_name}_shell_{i:04d}")
                for obj in objs:
                    n_meshes += 1
                    _attach_to_rig(obj, parsed.nodes, arm_builder)
                    _record_obj_for_node(obj, obj_for_node)

    n_connectors = 0
    if options.import_connectors:
        for connector in parsed.connectors:
            if isinstance(connector, t.Connector):
                obj = create_connector(connector, parsed.nodes, axis_mat, collection)
                _attach_extra_to_bone(obj, parsed.nodes, arm_builder)
                _record_obj_for_node(obj, obj_for_node)
                n_connectors += 1

    n_lights = 0
    if options.import_lights:
        for light in parsed.light_nodes:
            if isinstance(light, t.LightNode):
                obj = create_light(light, parsed.nodes, axis_mat, collection)
                if obj is not None:
                    _attach_extra_to_bone(obj, parsed.nodes, arm_builder)
                    _record_obj_for_node(obj, obj_for_node)
                    n_lights += 1

    if options.import_animations and arm_builder is not None:
        try:
            apply_visibility_actions(parsed.nodes, obj_for_node, model_name)
        except Exception:
            print("[EDM] Warning: visibility action build failed.")
            traceback.print_exc()

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
    if arm_builder and arm_builder._actions:
        print(
            f"[EDM]   actions: {len(arm_builder._actions)} "
            f"(active = {arm_builder._arm_obj.animation_data.action.name if arm_builder._arm_obj.animation_data and arm_builder._arm_obj.animation_data.action else 'none'})"
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


def _build_lod_lookup(nodes: Sequence) -> Dict[int, Tuple[float, float]]:
    """Map every direct child of a LodNode to its (min, max) distance.

    The EDM spec says a LodNode's ``levels`` array is matched positionally
    to its children. We build the inverse map (child_idx -> (min, max))
    so a render mesh can stamp its LOD range without scanning the whole
    graph every time.
    """
    parent_to_children: Dict[int, List[int]] = {}
    for i, n in enumerate(nodes):
        p = getattr(n, "parent_idx", -1)
        if p < 0:
            continue
        parent_to_children.setdefault(p, []).append(i)

    lookup: Dict[int, Tuple[float, float]] = {}
    for i, n in enumerate(nodes):
        if not isinstance(n, t.LodNode):
            continue
        children = parent_to_children.get(i, [])
        for child_idx, level in zip(children, n.levels):
            lookup[child_idx] = (level.distance_min, level.distance_max)
    return lookup


def _record_obj_for_node(
    obj: bpy.types.Object,
    obj_for_node: Dict[int, bpy.types.Object],
) -> None:
    parent_node = int(obj.get("edm_parent_node", -1))
    if parent_node >= 0:
        obj_for_node[parent_node] = obj


def _attach_to_rig(
    obj: bpy.types.Object,
    nodes: Sequence,
    arm_builder: Optional[ArmatureBuilder],
) -> None:
    """Attach a mesh object to the rig using a uniform mechanism.

    Unifies static and animated meshes:

      * If the mesh is already a SkinNode (it already has its own
        Armature modifier), we leave it alone — re-binding would
        double-deform.
      * Otherwise we object-parent to the armature, give the mesh a
        single full-weight vertex group named after the closest rig
        ancestor, and add an Armature modifier. The mesh follows that
        bone exactly, including all DCS argument animations.

    This avoids Blender's "bone parent puts the child at the bone tail"
    quirk that produced the visible offsets in earlier revisions.
    """
    if arm_builder is None or arm_builder.armature is None:
        return
    if obj.type != "MESH":
        return
    # SkinNode meshes already have an Armature modifier with proper weights.
    if obj.modifiers and any(m.type == "ARMATURE" for m in obj.modifiers):
        return

    parent_node = int(obj.get("edm_parent_node", -1))
    if parent_node < 0:
        return
    bone_idx = _first_rig_ancestor(parent_node, nodes, arm_builder.bone_for_node)
    if bone_idx < 0 or bone_idx not in arm_builder.bone_for_node:
        return

    bone_name = arm_builder.bone_for_node[bone_idx]
    arm = arm_builder.armature

    # Preserve the world matrix we already computed (axis_mat @ world_mat).
    world_mat = obj.matrix_world.copy()
    obj.parent = arm
    obj.matrix_world = world_mat

    # Single full-weight vertex group + Armature modifier so the mesh
    # follows the bone for every keyframe of every action.
    if bone_name not in obj.vertex_groups:
        vg = obj.vertex_groups.new(name=bone_name)
        vg.add([v.index for v in obj.data.vertices], 1.0, "REPLACE")

    modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
    modifier.object = arm
    modifier.use_vertex_groups = True
    modifier.use_bone_envelopes = False


def _attach_extra_to_bone(
    obj: bpy.types.Object,
    nodes: Sequence,
    arm_builder: Optional[ArmatureBuilder],
) -> None:
    """Bone-parent connectors / lights so they follow the rig.

    We *can't* use the vertex-group-with-modifier trick on Empty/Light
    objects because they have no mesh, so we fall back to a classic
    ``parent_type='BONE'`` parenting and re-apply the world matrix once
    parenting is in place — this lets Blender compute the correct
    ``matrix_parent_inverse`` automatically.
    """
    if arm_builder is None or arm_builder.armature is None:
        return
    parent_node = int(obj.get("edm_parent_node", -1))
    if parent_node < 0:
        return
    bone_idx = _first_rig_ancestor(parent_node, nodes, arm_builder.bone_for_node)
    if bone_idx < 0 or bone_idx not in arm_builder.bone_for_node:
        return
    bone_name = arm_builder.bone_for_node[bone_idx]
    arm = arm_builder.armature

    world_mat = obj.matrix_world.copy()
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    obj.matrix_world = world_mat


def _first_rig_ancestor(
    node_idx: int,
    nodes: Sequence,
    bone_for_node: Dict[int, str],
) -> int:
    """Walk up the parent chain, returning the first node that has a bone."""
    seen: set = set()
    while 0 <= node_idx < len(nodes):
        if node_idx in seen:
            return -1
        seen.add(node_idx)
        if node_idx in bone_for_node:
            return node_idx
        node_idx = getattr(nodes[node_idx], "parent_idx", -1)
    return -1
