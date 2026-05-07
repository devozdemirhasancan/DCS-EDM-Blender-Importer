"""
Coordinate-system and parent-chain helpers for the Blender importer.

EDM uses **Y-up** (DCS / OpenSceneGraph convention) while Blender uses
**Z-up**. The conversion is a -90° rotation around the X axis. This is
expressed once as :func:`axis_correction_matrix` and reused everywhere.

Matrices in EDM files are stored **column-major** (OpenGL).
:func:`edm_matrix_to_blender` transposes them so they line up with
``mathutils.Matrix`` which is row-major.

Parent chain math:
    The scene-graph parent relationships matter for placement. A render
    node's vertex data is in the *local space* of its parent transform
    chain. To put it in world space you must accumulate every transform
    on the chain up to the root.

    :func:`world_matrix_for_node` does exactly that, treating each node
    type appropriately:

      * TransformNode -> the node's stored matrix is its local pose.
      * ArgAnimationNode and friends -> we use the *rest pose* derived
        from the ``base`` data so animated parts are placed correctly
        when no animation is active.
      * Other nodes -> identity.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

import mathutils

from ..edm import types as t


# ---------------------------------------------------------------------------
#  Matrix conversions
# ---------------------------------------------------------------------------


def edm_matrix_to_blender(m16: Sequence[float]) -> mathutils.Matrix:
    """Convert a 16-float column-major EDM matrix to a Blender Matrix."""
    if not m16 or len(m16) < 16:
        return mathutils.Matrix.Identity(4)
    return mathutils.Matrix(
        (m16[0:4], m16[4:8], m16[8:12], m16[12:16])
    ).transposed()


def axis_correction_matrix(up_axis: str = "Y") -> mathutils.Matrix:
    """Return the matrix that rotates EDM space into Blender space.

    For the standard DCS convention (Y up) we rotate -90° around X; this
    moves +Y onto +Z and -Z onto +Y so the model stands upright. Setting
    ``up_axis`` to anything else returns identity (no rotation applied).
    """
    if up_axis.upper() == "Y":
        return mathutils.Euler(
            (math.radians(-90.0), 0.0, 0.0), "XYZ"
        ).to_matrix().to_4x4()
    return mathutils.Matrix.Identity(4)


def quat_from_wxyz(q: Tuple[float, float, float, float]) -> mathutils.Quaternion:
    """Convenience: tuple ``(w, x, y, z)`` -> :class:`mathutils.Quaternion`."""
    return mathutils.Quaternion((q[0], q[1], q[2], q[3]))


# ---------------------------------------------------------------------------
#  Per-node local transforms
# ---------------------------------------------------------------------------


def _arg_anim_rest_matrix(node: t.ArgAnimationNode) -> mathutils.Matrix:
    """Build the rest-pose matrix for an ArgAnimationNode.

    Per the reference EDM importer, the per-node static transform is::

        rest = matrix * Translate(position) * Quat1 * Scale * Quat2

    `Quat2` is rarely non-identity and `matrix` is most often the identity
    on the geometry side; but compounding all five lets us place animated
    parts correctly even when their default-pose differs from origin.
    """
    base = node.base
    m = edm_matrix_to_blender(base.matrix)
    t_mat = mathutils.Matrix.Translation(base.position)
    q1_mat = quat_from_wxyz(base.quat1).to_matrix().to_4x4()
    q2_mat = quat_from_wxyz(base.quat2).to_matrix().to_4x4()

    sx, sy, sz = base.scale if base.scale else (1.0, 1.0, 1.0)
    s_mat = mathutils.Matrix.Diagonal((sx, sy, sz, 1.0))

    return m @ t_mat @ q1_mat @ s_mat @ q2_mat


def local_matrix_for_node(node) -> mathutils.Matrix:
    """Return the local-space matrix of a single scene node.

    Falls back to identity for nodes that don't define a transform
    (plain ``Node``, render items themselves, etc.).
    """
    if node is None:
        return mathutils.Matrix.Identity(4)
    if isinstance(node, t.TransformNode):
        return edm_matrix_to_blender(node.matrix)
    if isinstance(node, t.ArgAnimationNode):
        return _arg_anim_rest_matrix(node)
    if isinstance(node, t.BoneNode):
        # Spec: m1 is the bone's local transform; m2 is the inverse bind
        # used for skinning. For static placement, m1 is what we want.
        return edm_matrix_to_blender(node.matrix1)
    return mathutils.Matrix.Identity(4)


def world_matrix_for_node(
    node_idx: int, nodes: Sequence
) -> mathutils.Matrix:
    """Walk the parent chain from ``node_idx`` to the root and accumulate.

    Each node's local matrix is multiplied **on the left** by its parent
    chain so the result places the node in world space.

    Cycle detection is included so that malformed scene-graphs (which we
    have observed in some heavily-modded files) don't loop forever.
    """
    matrix = mathutils.Matrix.Identity(4)
    idx = node_idx
    visited: set = set()
    chain = []
    while 0 <= idx < len(nodes):
        if idx in visited:
            break
        visited.add(idx)
        chain.append(idx)
        idx = getattr(nodes[idx], "parent_idx", -1)
    # Multiply parent-most first so:  parent @ ... @ node
    for i in reversed(chain):
        matrix = matrix @ local_matrix_for_node(nodes[i])
    return matrix


# ---------------------------------------------------------------------------
#  Animation-ancestor lookup
# ---------------------------------------------------------------------------


def find_animating_ancestor(node_idx: int, nodes: Sequence) -> int:
    """Return the index of the first animating ancestor or -1.

    Used to decide whether a render node should be parented to an armature
    bone (because something above it is animated) or just placed with a
    static world matrix.
    """
    idx = node_idx
    visited: set = set()
    while 0 <= idx < len(nodes):
        if idx in visited:
            return -1
        visited.add(idx)
        node = nodes[idx]
        if node.type in t.ANIMATING_NODE_TYPES:
            return idx
        idx = getattr(node, "parent_idx", -1)
    return -1
