"""
Armature & animation builder.

The EDM scene-graph encodes animation through:
  * ``ArgAnimationNode`` (and its position/rotation/scale specialisations)
  * ``ArgAnimatedBone`` for skin-bound animated bones
  * Plain ``Bone`` (static, used by SkinNode references)
  * ``ArgVisibilityNode`` for argument-driven hide/show

We translate that into Blender like so:

  * Every animating-or-bone node becomes one **bone** in a single
    armature, positioned at its rest-pose translation (computed by
    walking the parent chain).
  * Each unique animation argument becomes one **action**
    (``<model>_arg<NN>``) whose fcurves drive the relevant bones'
    ``location`` / ``rotation_quaternion`` / ``scale``.
  * Visibility arguments become per-object ``hide_render`` actions,
    handled in :func:`apply_visibility_actions` (called by the importer
    after meshes are built).

Frame mapping: argument value 0.0 -> frame 1, 1.0 -> frame 101.

Why include plain Bones in the armature? Because SkinNode references
them by index. Without them in the armature, skin weights have nowhere
to attach. Static bones simply don't have any keyframe data.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import bpy
import mathutils

from ..edm import types as t
from . import transforms as xf


# Frames per unit of animation argument. 100 gives DCS-like resolution
# without overwhelming Blender's timeline.
FRAMES_PER_UNIT = 100
FRAME_OFFSET = 1   # so argument value 0.0 maps to frame 1, not 0


# Node types that should appear in the armature, even if they don't have
# any animation data attached. This is broader than
# ``ANIMATING_NODE_TYPES`` because SkinNode bone references can target
# plain (static) Bone nodes.
_RIG_NODE_TYPES = frozenset(t.ANIMATING_NODE_TYPES | {
    t.NodeType.BONE.value,
    t.NodeType.ARG_ANIMATED_BONE.value,
})


def _arg_to_frame(arg_value: float) -> int:
    return int(round(arg_value * FRAMES_PER_UNIT)) + FRAME_OFFSET


# ---------------------------------------------------------------------------


class ArmatureBuilder:
    """Builds the armature, bones, and animation actions for a single import."""

    def __init__(
        self,
        nodes,
        axis_mat: mathutils.Matrix,
        collection: bpy.types.Collection,
        model_name: str,
    ):
        self._nodes = nodes
        self._axis_mat = axis_mat
        self._collection = collection
        self._model_name = model_name

        self._arm_obj: Optional[bpy.types.Object] = None
        self._bone_for_node: Dict[int, str] = {}
        self._actions: Dict[int, bpy.types.Action] = {}

    # ------------------------------------------------------------- public
    @property
    def armature(self) -> Optional[bpy.types.Object]:
        return self._arm_obj

    @property
    def bone_for_node(self) -> Dict[int, str]:
        return self._bone_for_node

    def build(self) -> Optional[bpy.types.Object]:
        bone_indices = [
            i for i, n in enumerate(self._nodes)
            if n.type in _RIG_NODE_TYPES
        ]
        if not bone_indices:
            return None

        arm_data = bpy.data.armatures.new(f"{self._model_name}_rig")
        arm_obj = bpy.data.objects.new(f"{self._model_name}_rig", arm_data)
        self._collection.objects.link(arm_obj)
        arm_obj.matrix_world = self._axis_mat
        self._arm_obj = arm_obj

        # Save the previous active object so we can restore it.
        prev_active = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = arm_obj
        try:
            bpy.ops.object.mode_set(mode="EDIT")
            self._create_bones(bone_indices, arm_data)
            self._set_bone_parents(bone_indices, arm_data)
        finally:
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                pass
            if prev_active is not None:
                bpy.context.view_layer.objects.active = prev_active

        self._build_actions()
        self._stack_actions_into_nla()
        return arm_obj

    # ----------------------------------------------------------- internals
    def _create_bones(self, bone_indices: List[int], arm_data) -> None:
        edit_bones = arm_data.edit_bones
        for idx in bone_indices:
            node = self._nodes[idx]
            bone_name = self._bone_name_for(idx, node)
            bone = edit_bones.new(bone_name)

            # Place the bone at the node's rest-pose translation derived
            # from the parent chain so meshes parented to the bone land
            # at the correct default position. The bone's "tail" sits a
            # tiny distance away in armature-local Z so the bone has
            # nonzero length (Blender requires this).
            world = xf.world_matrix_for_node(idx, self._nodes)
            head = world.translation
            bone.head = head
            bone.tail = head + mathutils.Vector((0.0, 0.0, 0.05))
            self._bone_for_node[idx] = bone_name

    def _set_bone_parents(self, bone_indices: List[int], arm_data) -> None:
        edit_bones = arm_data.edit_bones
        for idx in bone_indices:
            node = self._nodes[idx]
            parent_idx = self._first_rig_ancestor(getattr(node, "parent_idx", -1))
            if parent_idx >= 0 and parent_idx in self._bone_for_node:
                child = edit_bones[self._bone_for_node[idx]]
                child.parent = edit_bones[self._bone_for_node[parent_idx]]
                # Connect head to parent's tail when the child sits exactly
                # on the parent's head — looks tidier in the viewport.

    def _first_rig_ancestor(self, idx: int) -> int:
        seen = set()
        while 0 <= idx < len(self._nodes):
            if idx in seen:
                return -1
            seen.add(idx)
            if idx in self._bone_for_node:
                return idx
            idx = getattr(self._nodes[idx], "parent_idx", -1)
        return -1

    def _bone_name_for(self, idx: int, node) -> str:
        # Sanitise: spaces and dots break fcurve datapaths.
        raw = (getattr(node, "name", "") or f"bone_{idx}").replace(" ", "_").replace(".", "_")
        if raw not in self._bone_for_node.values():
            return raw
        return f"{raw}_{idx:03d}"

    # ------------------------------------------------------------ actions
    def _build_actions(self) -> None:
        if self._arm_obj is None:
            return
        if self._arm_obj.animation_data is None:
            self._arm_obj.animation_data_create()

        for idx, bone_name in self._bone_for_node.items():
            node = self._nodes[idx]
            if isinstance(node, t.ArgAnimationNode):
                self._build_arg_anim_actions(node, bone_name)

    def _build_arg_anim_actions(self, node: t.ArgAnimationNode, bone_name: str) -> None:
        """Generate per-argument fcurves for one ArgAnimationNode.

        We follow the spec formula
            transform = mat * Translate(pos) * Quat1 * keyRot * Scale
        but apply it as a *delta from rest* in pose-bone space, since
        Blender's pose bones are evaluated relative to the bone's edit
        (rest) pose. The rest pose itself was placed at the world
        position derived from the same parent chain in :meth:`_create_bones`,
        so rotations/translations come out visually correct.
        """
        base = node.base
        q1 = xf.quat_from_wxyz(base.quat1)

        # ---- Position keyframes ---------------------------------------
        for arg, keys in node.pos_data:
            if not keys:
                continue
            action = self._action_for_arg(arg)
            data_path = f'pose.bones["{bone_name}"].location'
            for key in keys:
                frame = _arg_to_frame(key.frame)
                # Use the key value directly; the rig already encodes the
                # base position at rest, so this is the local delta.
                value = tuple(key.value)
                for ch in range(min(3, len(value))):
                    fc = (
                        action.fcurves.find(data_path, index=ch)
                        or action.fcurves.new(data_path, index=ch, action_group=bone_name)
                    )
                    fc.keyframe_points.insert(frame, float(value[ch]))

        # ---- Rotation keyframes ---------------------------------------
        # The reference importer applies ``leftRot * keyRot * rightRot``
        # where leftRot includes both the matrix's rotation and base.quat1.
        # We do the same so file-stored absolute rotations turn into
        # correct local pose rotations.
        for arg, keys in node.rot_data:
            if not keys:
                continue
            action = self._action_for_arg(arg)
            data_path = f'pose.bones["{bone_name}"].rotation_quaternion'
            # Pre-compose: q1 stays constant per node, applied as left.
            for key in keys:
                frame = _arg_to_frame(key.frame)
                key_quat = xf.quat_from_wxyz(key.value)
                # Combine as q1 * keyQuat — yields the local pose rotation
                # relative to the bone's rest, which already contains the
                # parent chain via edit-bone placement.
                combined = q1 @ key_quat
                for ch, comp in enumerate((combined.w, combined.x, combined.y, combined.z)):
                    fc = (
                        action.fcurves.find(data_path, index=ch)
                        or action.fcurves.new(data_path, index=ch, action_group=bone_name)
                    )
                    fc.keyframe_points.insert(frame, float(comp))

        # ---- Scale keyframes ------------------------------------------
        for arg, (keys_a, _keys_b) in node.scale_data:
            if not keys_a:
                continue
            action = self._action_for_arg(arg)
            data_path = f'pose.bones["{bone_name}"].scale'
            for key in keys_a:
                frame = _arg_to_frame(key.frame)
                # Spec stores 4 doubles; first three are XYZ scale.
                sx, sy, sz, _ = key.value
                for ch, comp in enumerate((sx, sy, sz)):
                    fc = (
                        action.fcurves.find(data_path, index=ch)
                        or action.fcurves.new(data_path, index=ch, action_group=bone_name)
                    )
                    fc.keyframe_points.insert(frame, float(comp))

    def _action_for_arg(self, arg: int) -> bpy.types.Action:
        action = self._actions.get(arg)
        if action is None:
            action = bpy.data.actions.new(f"{self._model_name}_arg{arg:03d}")
            action["edm_argument"] = int(arg)
            self._actions[arg] = action
        return action

    def _stack_actions_into_nla(self) -> None:
        if not self._arm_obj or not self._actions:
            return
        ad = self._arm_obj.animation_data
        if ad is None:
            return
        for arg, action in sorted(self._actions.items()):
            track = ad.nla_tracks.new()
            track.name = action.name
            try:
                strip = track.strips.new(action.name, 1, action)
                # Compute the action range from its fcurves. Default to a
                # sensible 1..101 if the action only has unit-time keys.
                max_frame = 101
                for fc in action.fcurves:
                    for kp in fc.keyframe_points:
                        if kp.co[0] > max_frame:
                            max_frame = int(kp.co[0])
                strip.action_frame_start = 1
                strip.action_frame_end = max_frame
                track.mute = True   # Don't auto-play; let users enable per-track.
            except RuntimeError:
                continue
        ad.action = None


# ---------------------------------------------------------------------------
#  Visibility actions (applied to mesh objects themselves)
# ---------------------------------------------------------------------------


def apply_visibility_actions(
    nodes,
    obj_for_node: Dict[int, bpy.types.Object],
    model_name: str,
) -> None:
    """Translate every ArgVisibilityNode into ``hide_render`` fcurves."""
    for idx, node in enumerate(nodes):
        if not isinstance(node, t.ArgVisibilityNode):
            continue
        obj = obj_for_node.get(idx)
        if obj is None:
            continue
        if obj.animation_data is None:
            obj.animation_data_create()
        for arg, ranges in node.vis_data:
            action_name = f"{model_name}_vis_arg{arg:03d}_{idx}"
            action = bpy.data.actions.new(action_name)
            action["edm_argument"] = int(arg)
            curve = action.fcurves.new("hide_render")
            for (start, end) in ranges:
                f_start = _arg_to_frame(start)
                # Cap unrealistically large 'end' (often 1e300 in DCS files
                # to mean "permanently visible") at 1.0 = frame 101.
                f_end = _arg_to_frame(min(end, 1.0)) if end < 1e6 else _arg_to_frame(1.0)
                kp = curve.keyframe_points.insert(f_start, 0.0)
                kp.interpolation = "CONSTANT"
                kp = curve.keyframe_points.insert(f_end, 1.0)
                kp.interpolation = "CONSTANT"
            track = obj.animation_data.nla_tracks.new()
            track.name = action_name
            try:
                track.strips.new(action_name, 1, action)
            except RuntimeError:
                pass
