"""
Mesh creation from EDM geometry nodes.

Each :class:`RenderNode`, :class:`ShellNode` and :class:`SkinNode` becomes
a Blender ``Object``. Important behaviours:

  * **Vertex format aware** — the channel offsets specified in the
    material's VERTEX_FORMAT (or in the ShellNode itself) are used to
    pull position / normal / UV / bone-weight data from each vertex.
  * **UV V-flip** — Blender's UV V coordinate is the inverse of OpenGL's.
    We mirror it so textures appear right-side-up.
  * **Multi-parent split** — when a RenderNode lists more than one
    ParentEntry, the index buffer is sliced per parent and a separate
    Blender object is produced. This matches DCS's runtime behaviour of
    splitting merged meshes back into individual parts.
  * **Mirror handling** — if the accumulated parent transform has a
    negative determinant we flip the face winding so the lighting is
    correct.

Each created object stores ``edm_*`` custom properties (damage argument,
collision flag, parent index) so users / scripts can inspect or filter
them later.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import bpy
import mathutils

from ..edm import types as t
from . import transforms as xf


# ---------------------------------------------------------------------------
#  Vertex-data extraction
# ---------------------------------------------------------------------------


def _vertex_format_for(node, materials: Sequence[t.Material]) -> Optional[t.VertexFormat]:
    """Return the right VertexFormat for any geometry node."""
    if isinstance(node, t.ShellNode):
        return node.vertex_format
    mat_id = getattr(node, "material_id", None)
    if mat_id is None or mat_id < 0 or mat_id >= len(materials):
        return None
    return materials[mat_id].vertex_format


def _extract_attributes(
    vtx: Tuple[float, ...],
    fmt: Optional[t.VertexFormat],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float]]:
    """Pull (position, normal, uv) out of a single vertex tuple.

    Falls back to sane defaults when channels are missing.
    """
    if fmt is None or len(fmt.channels) < 1:
        # Best guess: standard 4-pos / 3-nor / 2-uv layout
        position = (vtx[0], vtx[1], vtx[2])
        normal = (vtx[4], vtx[5], vtx[6]) if len(vtx) >= 7 else (0.0, 0.0, 1.0)
        uv = (vtx[7], vtx[8]) if len(vtx) >= 9 else (0.0, 0.0)
        return position, normal, uv

    pos_off = fmt.offset_of(t.VertexFormat.POSITION)
    if pos_off < 0:
        pos_off = 0
    position = (vtx[pos_off], vtx[pos_off + 1], vtx[pos_off + 2])

    nor_off = fmt.offset_of(t.VertexFormat.NORMAL)
    if nor_off >= 0 and nor_off + 2 < len(vtx):
        normal = (vtx[nor_off], vtx[nor_off + 1], vtx[nor_off + 2])
    else:
        normal = (0.0, 0.0, 1.0)

    uv_off = fmt.offset_of(t.VertexFormat.UV0)
    if uv_off >= 0 and uv_off + 1 < len(vtx):
        # EDM stores OpenGL-style UVs (origin bottom-left). Blender uses
        # the same convention internally, but DCS textures (specifically
        # DDS exports) are flipped relative to the EDM v-coordinate, so
        # we mirror V here for visually correct results.
        uv = (vtx[uv_off], 1.0 - vtx[uv_off + 1])
    else:
        uv = (0.0, 0.0)

    return position, normal, uv


def _extract_bone_data(
    vtx: Tuple[float, ...],
    fmt: Optional[t.VertexFormat],
) -> Optional[Tuple[Tuple[int, int, int, int], Tuple[float, float, float, float]]]:
    """If the vertex format includes bone data, extract (indices, weights)."""
    if fmt is None:
        return None
    off = fmt.offset_of(t.VertexFormat.BONE_WEIGHTS)
    size = fmt.size_of(t.VertexFormat.BONE_WEIGHTS)
    if off < 0 or size < 4 or off + 7 >= len(vtx):
        return None
    # Per spec there are 8 floats: 4 indices interleaved with 4 weights.
    indices = (
        int(vtx[off]),
        int(vtx[off + 1]),
        int(vtx[off + 2]),
        int(vtx[off + 3]),
    )
    weights = (
        float(vtx[off + 4]),
        float(vtx[off + 5]),
        float(vtx[off + 6]),
        float(vtx[off + 7]),
    )
    return indices, weights


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
    ):
        self._materials = materials
        self._material_builder = material_builder
        self._collection = collection
        self._nodes = nodes
        self._axis_mat = axis_mat

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
        # SkinNodes don't have ParentEntry rows; they're parented via
        # `bones`. We treat them as a single object whose 'parent' is the
        # first bone entry — the actual skinning is set up later in the
        # armature module.
        parent_entries = [t.ParentEntry(node=node.bones[0])] if node.bones else []
        return self._build_geometry(
            node,
            fallback,
            material_id=node.material_id,
            parent_entries=parent_entries,
            is_collision=False,
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

        # Determine slice-points so we can split a multi-parent RenderNode
        # into per-parent meshes.
        slices = self._slice_per_parent(parent_entries, len(index_data))

        results: List[bpy.types.Object] = []
        for slice_idx, (parent_entry, idx_start, idx_end) in enumerate(slices):
            slice_indices = index_data[idx_start:idx_end]
            if not slice_indices:
                continue

            obj_name = self._object_name(node, fallback_name, slice_idx, len(slices))
            world_mat = self._world_matrix_for_parent(parent_entry.node)
            is_mirror = world_mat.determinant() < -1e-6

            obj = self._make_blender_mesh(
                obj_name,
                vertex_data,
                slice_indices,
                fmt,
                is_mirror=is_mirror,
            )
            if obj is None:
                continue

            obj.matrix_world = self._axis_mat @ world_mat
            obj["edm_node_type"] = node.type
            obj["edm_parent_node"] = int(parent_entry.node)
            obj["edm_damage_arg"] = int(parent_entry.damage_arg)
            obj["edm_is_collision"] = bool(is_collision)
            if hasattr(node, "name"):
                obj["edm_name"] = node.name

            if is_collision:
                # Render collision shells as non-rendering wireframes so they
                # don't interfere with the main view.
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
            # No parent metadata at all; treat the whole node as one piece.
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

    def _make_blender_mesh(
        self,
        name: str,
        vertex_data: Sequence[Tuple[float, ...]],
        index_data: Sequence[int],
        fmt: Optional[t.VertexFormat],
        is_mirror: bool,
    ) -> Optional[bpy.types.Object]:
        # Compress vertex set to only what the indices actually reference.
        # This both saves memory and avoids "loose" vertices in the mesh.
        used_indices = sorted({i for i in index_data if 0 <= i < len(vertex_data)})
        if not used_indices:
            return None
        remap = {old: new for new, old in enumerate(used_indices)}
        new_vertices = [vertex_data[i] for i in used_indices]
        new_indices = [remap[i] for i in index_data if i in remap]
        if len(new_indices) < 3 or len(new_indices) % 3 != 0:
            return None

        positions: List[Tuple[float, float, float]] = []
        normals: List[Tuple[float, float, float]] = []
        uvs: List[Tuple[float, float]] = []
        for vtx in new_vertices:
            pos, nor, uv = _extract_attributes(vtx, fmt)
            positions.append(pos)
            normals.append(nor)
            uvs.append(uv)

        faces = [
            (new_indices[i], new_indices[i + 1], new_indices[i + 2])
            for i in range(0, len(new_indices), 3)
        ]
        if is_mirror:
            faces = [(a, c, b) for (a, b, c) in faces]

        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(positions, [], faces)
        mesh.update()

        # Custom split normals
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
            # use_auto_smooth only existed up to Blender 4.0; in 4.1+ it
            # was removed in favour of the Smooth-by-Angle modifier.
            if hasattr(mesh, "use_auto_smooth"):
                mesh.use_auto_smooth = True

        # UV layer
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for poly in mesh.polygons:
            for loop_idx in poly.loop_indices:
                uv_layer.data[loop_idx].uv = uvs[mesh.loops[loop_idx].vertex_index]

        return bpy.data.objects.new(name, mesh)
