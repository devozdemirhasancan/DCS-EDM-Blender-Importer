"""
Mesh creation from EDM geometry nodes.

Each :class:`RenderNode`, :class:`ShellNode` and :class:`SkinNode` becomes
one (or several) Blender ``Object``. Highlights:

  * **Vertex format aware** — channel offsets specified by the material's
    VERTEX_FORMAT (or the ShellNode itself) drive position / normal /
    UV / bone-weight extraction. We don't assume a fixed layout.
  * **Multi-UV** — every present UV channel (4..8) becomes its own
    Blender UV layer (``UVMap``, ``UVMap.001`` ...).
  * **UV V-flip** — Blender's V is the inverse of the OpenGL V the EDM
    file stores; we mirror it once on read.
  * **Multi-parent split** — when a RenderNode lists more than one
    ParentEntry, the index buffer is sliced per parent and a separate
    Blender object produced.
  * **Skin weights** — for SkinNodes, per-vertex bone indices and weights
    are written into named vertex groups and the object gets an
    ``Armature`` modifier so it deforms when the rig animates.
  * **Mirror handling** — when the accumulated parent transform has a
    negative determinant we flip face winding so normals stay outward.
  * **LOD metadata** — meshes record their nearest LOD ancestor's
    distance range as ``edm_lod_min`` / ``edm_lod_max`` custom
    properties, useful for filtering/visibility scripts.

Each created object also stores ``edm_*`` custom properties (damage
argument, collision flag, parent index) so users / scripts can inspect
or filter them later.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import bpy
import mathutils

from ..edm import types as t
from . import transforms as xf


# ---------------------------------------------------------------------------
#  Vertex-data extraction
# ---------------------------------------------------------------------------


# UV channels per the EDM spec. We probe each one and create a Blender UV
# layer whenever we find non-zero data. UV0 (channel 4) is the most common
# and always produces a layer named ``UVMap``.
_UV_CHANNELS = (
    t.VertexFormat.UV0,
    t.VertexFormat.UV1,
    6,
    7,
    8,
)


def _vertex_format_for(node, materials: Sequence[t.Material]) -> Optional[t.VertexFormat]:
    """Return the right VertexFormat for any geometry node."""
    if isinstance(node, t.ShellNode):
        return node.vertex_format
    mat_id = getattr(node, "material_id", None)
    if mat_id is None or mat_id < 0 or mat_id >= len(materials):
        return None
    return materials[mat_id].vertex_format


def _vec3_at(vtx: Sequence[float], offset: int, default: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if offset < 0 or offset + 2 >= len(vtx):
        return default
    return (vtx[offset], vtx[offset + 1], vtx[offset + 2])


def _uv_at(vtx: Sequence[float], offset: int) -> Optional[Tuple[float, float]]:
    if offset < 0 or offset + 1 >= len(vtx):
        return None
    # EDM (and most OpenGL pipelines) put UV origin at the bottom-left.
    # Blender's image space is the same in *theory*, but DCS .dds exports
    # are conventionally flipped relative to that, so we mirror V here so
    # textures appear right-side-up.
    return (vtx[offset], 1.0 - vtx[offset + 1])


def _bone_data_at(
    vtx: Sequence[float],
    fmt: Optional[t.VertexFormat],
) -> Optional[Tuple[Tuple[int, int, int, int], Tuple[float, float, float, float]]]:
    """Pull (indices, weights) out of channel 21 if the format provides it."""
    if fmt is None:
        return None
    off = fmt.offset_of(t.VertexFormat.BONE_WEIGHTS)
    size = fmt.size_of(t.VertexFormat.BONE_WEIGHTS)
    if off < 0 or size < 4 or off + 7 >= len(vtx):
        return None
    return (
        (int(vtx[off]), int(vtx[off + 1]), int(vtx[off + 2]), int(vtx[off + 3])),
        (float(vtx[off + 4]), float(vtx[off + 5]), float(vtx[off + 6]), float(vtx[off + 7])),
    )


def _present_uv_channels(fmt: Optional[t.VertexFormat]) -> List[int]:
    if fmt is None:
        return [t.VertexFormat.UV0]
    return [c for c in _UV_CHANNELS if fmt.size_of(c) >= 2]


# ---------------------------------------------------------------------------
#  Mesh assembly
# ---------------------------------------------------------------------------


class MeshBuilder:
    """Creates Blender mesh objects from EDM geometry nodes."""

    def __init__(
        self,
        materials: Sequence[t.Material],
        material_builder,           # MaterialBuilder, not imported to avoid cycle
        collection: bpy.types.Collection,
        nodes: Sequence,
        axis_mat: mathutils.Matrix,
        lod_lookup: Optional[Dict[int, Tuple[float, float]]] = None,
    ):
        self._materials = materials
        self._material_builder = material_builder
        self._collection = collection
        self._nodes = nodes
        self._axis_mat = axis_mat
        self._lod_lookup = lod_lookup or {}
        # Set later via ``attach_armature`` so the importer can build the
        # armature first and feed it back in.
        self._armature_obj: Optional[bpy.types.Object] = None
        self._bone_for_node: Dict[int, str] = {}

    def attach_armature(
        self,
        armature_obj: Optional[bpy.types.Object],
        bone_for_node: Dict[int, str],
    ) -> None:
        self._armature_obj = armature_obj
        self._bone_for_node = bone_for_node or {}

    # ---------------------------------------------------------------- API
    def build_render_node(self, node: t.RenderNode, fallback: str) -> List[bpy.types.Object]:
        return self._build_geometry(
            node,
            fallback,
            material_id=node.material_id,
            parent_entries=node.parents,
            is_collision=False,
        )

    def build_skin_node(self, node: t.SkinNode, fallback: str) -> List[bpy.types.Object]:
        # Use the first bone reference as the placement parent — the
        # actual deformation comes from the vertex groups + Armature
        # modifier we set up below.
        parent_entries = [t.ParentEntry(node=node.bones[0])] if node.bones else []
        return self._build_geometry(
            node,
            fallback,
            material_id=node.material_id,
            parent_entries=parent_entries,
            is_collision=False,
            skin_bones=node.bones,
        )

    def build_shell_node(self, node: t.ShellNode, fallback: str) -> List[bpy.types.Object]:
        return self._build_geometry(
            node,
            fallback,
            material_id=None,
            parent_entries=[t.ParentEntry(node=node.parent)] if node.parent >= 0 else [],
            is_collision=True,
        )

    # ----------------------------------------------------------- internals
    def _build_geometry(
        self,
        node,
        fallback_name: str,
        material_id: Optional[int],
        parent_entries: Sequence[t.ParentEntry],
        is_collision: bool,
        skin_bones: Optional[Sequence[int]] = None,
    ) -> List[bpy.types.Object]:
        index_data: List[int] = list(getattr(node, "index_data", []) or [])
        vertex_data = list(getattr(node, "vertex_data", []) or [])

        if not index_data or not vertex_data:
            return []
        if len(index_data) % 3 != 0:
            print(
                f"[EDM] Warning: index count {len(index_data)} not divisible "
                f"by 3 in {fallback_name!r}, skipping."
            )
            return []

        fmt = _vertex_format_for(node, self._materials)
        uv_channels = _present_uv_channels(fmt)

        slices = self._slice_per_parent(parent_entries, len(index_data))

        results: List[bpy.types.Object] = []
        for slice_idx, (parent_entry, idx_start, idx_end) in enumerate(slices):
            slice_indices = index_data[idx_start:idx_end]
            if not slice_indices:
                continue

            obj_name = self._object_name(node, fallback_name, slice_idx, len(slices))
            world_mat = self._world_matrix_for_parent(parent_entry.node)
            is_mirror = world_mat.determinant() < -1e-6

            obj_and_used = self._make_blender_mesh(
                obj_name,
                vertex_data,
                slice_indices,
                fmt,
                uv_channels,
                is_mirror=is_mirror,
            )
            if obj_and_used is None:
                continue
            obj, used_vertices = obj_and_used

            obj.matrix_world = self._axis_mat @ world_mat
            obj["edm_node_type"] = node.type
            obj["edm_parent_node"] = int(parent_entry.node)
            obj["edm_damage_arg"] = int(parent_entry.damage_arg)
            obj["edm_is_collision"] = bool(is_collision)
            if hasattr(node, "name"):
                obj["edm_name"] = node.name

            self._apply_lod_metadata(obj, parent_entry.node)

            if is_collision:
                obj.display_type = "WIRE"
                obj.hide_render = True

            self._collection.objects.link(obj)

            if material_id is not None and 0 <= material_id < len(self._materials):
                bl_mat = self._material_builder.build(
                    self._materials[material_id],
                    fallback_name=f"edm_mat_{material_id}",
                )
                if obj.data.materials:
                    obj.data.materials[0] = bl_mat
                else:
                    obj.data.materials.append(bl_mat)

            if skin_bones is not None:
                self._apply_skin_weights(obj, used_vertices, fmt, skin_bones)

            results.append(obj)
        return results

    # ---------------- helpers --------------------------------------------
    @staticmethod
    def _object_name(node, fallback: str, slice_idx: int, n_slices: int) -> str:
        base = getattr(node, "name", "") or fallback
        if n_slices > 1:
            return f"{base}.{slice_idx:03d}"
        return base

    @staticmethod
    def _slice_per_parent(
        parents: Sequence[t.ParentEntry],
        index_count: int,
    ) -> List[Tuple[t.ParentEntry, int, int]]:
        if not parents:
            return [(t.ParentEntry(node=-1), 0, index_count)]
        if len(parents) == 1:
            return [(parents[0], 0, index_count)]
        slices: List[Tuple[t.ParentEntry, int, int]] = []
        for i, entry in enumerate(parents):
            start = max(0, entry.index_start)
            if i + 1 < len(parents):
                end = max(start, parents[i + 1].index_start)
            else:
                end = index_count
            slices.append((entry, start, end))
        return slices

    def _world_matrix_for_parent(self, parent_node_idx: int) -> mathutils.Matrix:
        if parent_node_idx < 0:
            return mathutils.Matrix.Identity(4)
        return xf.world_matrix_for_node(parent_node_idx, self._nodes)

    def _apply_lod_metadata(self, obj: bpy.types.Object, parent_idx: int) -> None:
        """Walk up ancestors looking for LOD info and stamp it on the object."""
        if not self._lod_lookup:
            return
        node_idx = parent_idx
        seen: set = set()
        while 0 <= node_idx < len(self._nodes):
            if node_idx in seen:
                break
            seen.add(node_idx)
            if node_idx in self._lod_lookup:
                lo, hi = self._lod_lookup[node_idx]
                obj["edm_lod_min"] = float(lo)
                obj["edm_lod_max"] = float(hi)
                return
            node_idx = getattr(self._nodes[node_idx], "parent_idx", -1)

    # --------------------------------------------------- mesh construction
    def _make_blender_mesh(
        self,
        name: str,
        vertex_data: Sequence[Tuple[float, ...]],
        index_data: Sequence[int],
        fmt: Optional[t.VertexFormat],
        uv_channels: Sequence[int],
        is_mirror: bool,
    ) -> Optional[Tuple[bpy.types.Object, List[Tuple[float, ...]]]]:
        """Return ``(blender_object, used_vertex_tuples)`` or ``None``.

        The second element preserves the *raw* vertex tuples we kept (post
        index-compression) so callers can subsequently extract bone weight
        data without re-walking the original arrays.
        """
        used_indices = sorted({i for i in index_data if 0 <= i < len(vertex_data)})
        if not used_indices:
            return None
        remap = {old: new for new, old in enumerate(used_indices)}
        new_vertices = [vertex_data[i] for i in used_indices]
        new_indices = [remap[i] for i in index_data if i in remap]
        if len(new_indices) < 3 or len(new_indices) % 3 != 0:
            return None

        # Position offset
        pos_off = fmt.offset_of(t.VertexFormat.POSITION) if fmt else 0
        if pos_off < 0:
            pos_off = 0
        positions = [_vec3_at(v, pos_off, (0.0, 0.0, 0.0)) for v in new_vertices]

        # Normal offset
        nor_off = fmt.offset_of(t.VertexFormat.NORMAL) if fmt else -1
        normals = [_vec3_at(v, nor_off, (0.0, 0.0, 1.0)) for v in new_vertices]

        # Per-channel UV arrays
        uv_data: List[Optional[List[Tuple[float, float]]]] = []
        for ch in uv_channels:
            ch_off = fmt.offset_of(ch) if fmt else (8 if ch == t.VertexFormat.UV0 else -1)
            uvs_for_ch: List[Tuple[float, float]] = []
            for v in new_vertices:
                uv = _uv_at(v, ch_off)
                uvs_for_ch.append(uv if uv is not None else (0.0, 0.0))
            uv_data.append(uvs_for_ch)

        faces = [
            (new_indices[i], new_indices[i + 1], new_indices[i + 2])
            for i in range(0, len(new_indices), 3)
        ]
        if is_mirror:
            faces = [(a, c, b) for (a, b, c) in faces]

        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(positions, [], faces)
        mesh.update()

        # Custom split normals — give materials a believable shading even
        # before the user manually adds a Smooth-by-Angle modifier.
        if normals:
            split_normals: List[Tuple[float, float, float]] = []
            for poly in mesh.polygons:
                for loop_idx in poly.loop_indices:
                    n = normals[mesh.loops[loop_idx].vertex_index]
                    if is_mirror:
                        n = (-n[0], -n[1], -n[2])
                    split_normals.append(n)
            try:
                mesh.normals_split_custom_set(split_normals)
            except (RuntimeError, AttributeError):
                pass
            # ``use_auto_smooth`` was removed in Blender 4.1+ in favour of
            # the Smooth-by-Angle geometry-nodes modifier, so we only set
            # it when present.
            if hasattr(mesh, "use_auto_smooth"):
                mesh.use_auto_smooth = True

        # UV layers — one per non-zero channel.
        for layer_idx, ch in enumerate(uv_channels):
            uv_name = "UVMap" if layer_idx == 0 else f"UVMap.{layer_idx:03d}"
            uv_layer = mesh.uv_layers.new(name=uv_name)
            uvs = uv_data[layer_idx]
            for poly in mesh.polygons:
                for loop_idx in poly.loop_indices:
                    uv_layer.data[loop_idx].uv = uvs[mesh.loops[loop_idx].vertex_index]

        obj = bpy.data.objects.new(name, mesh)
        return obj, new_vertices

    # ------------------------------------------------------- skinning ----
    def _apply_skin_weights(
        self,
        obj: bpy.types.Object,
        used_vertices: Sequence[Tuple[float, ...]],
        fmt: Optional[t.VertexFormat],
        skin_bones: Sequence[int],
    ) -> None:
        """Create per-bone vertex groups and add an Armature modifier."""
        if self._armature_obj is None or not skin_bones:
            return

        # Map skin-local index (0..N-1) -> blender bone name.
        local_to_bone_name: Dict[int, str] = {}
        for local_idx, scene_idx in enumerate(skin_bones):
            bone_name = self._bone_for_node.get(scene_idx)
            if bone_name:
                local_to_bone_name[local_idx] = bone_name

        if not local_to_bone_name:
            return

        # Eagerly create vertex groups so ``add()`` doesn't have to test on
        # each iteration.
        vg_for_local: Dict[int, bpy.types.VertexGroup] = {}
        for local_idx, bone_name in local_to_bone_name.items():
            vg_for_local[local_idx] = obj.vertex_groups.new(name=bone_name)

        # Walk every vertex and assign weights.
        for vert_idx, vtx in enumerate(used_vertices):
            bone_data = _bone_data_at(vtx, fmt)
            if bone_data is None:
                continue
            indices, weights = bone_data
            # Normalise weights so they sum to 1 (DCS's data already is, but
            # it's cheap insurance against the occasional rounding drift).
            total = sum(w for w in weights if w > 0.0) or 1.0
            for local_bone_idx, weight in zip(indices, weights):
                if weight <= 0.0:
                    continue
                vg = vg_for_local.get(local_bone_idx)
                if vg is None:
                    continue
                vg.add([vert_idx], weight / total, "REPLACE")

        # Armature modifier so the rig actually deforms the mesh.
        modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
        modifier.object = self._armature_obj
        modifier.use_vertex_groups = True
        modifier.use_bone_envelopes = False
        # Parent so non-deforming transforms still follow.
        obj.parent = self._armature_obj
