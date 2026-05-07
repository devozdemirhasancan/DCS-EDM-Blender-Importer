"""
Armature & animation builder.

The EDM scene-graph encodes animation through ``ArgAnimationNode`` (and
its position/rotation/scale specialisations). Each animating node is
driven by a single integer "argument" — DCS publishes a list of these at
runtime (``arg 0`` = aileron, ``arg 1`` = elevator, ...).

We translate that into Blender like so:

  * Every animating node becomes one **bone** in a single armature whose
    rest pose matches the node's static (rest) transform from the file.
  * Each unique argument value becomes one **action** named
    ``<model>_arg<NN>``. Per-bone fcurves drive ``location`` and
    ``rotation_quaternion`` based on the animation's keyframes.
  * Visibility nodes contribute to a separate ``hide_render`` action.

The frame mapping is fixed: argument value ``0.0`` -> frame 1,
argument ``1.0`` -> frame 101 (so 100 frames per unit). DCS animation
arguments are typically in [0, 1] but can be negative for some controls;
that's why frame 0 is reserved as "argument value 0".

This module only **sets up** the rig and animations — it doesn't decide
which mesh is parented to which bone. That decision is made in
:mod:`dcs_edm_importer.blender.importer` after meshes are created.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import bpy
import mathutils

from ..edm import types as t
from . import transforms as xf


# Frames per unit of animation argument. 100 gives DCS-like resolution
# without overwhelming Blender's timeline.
FRAMES_PER_UNIT = 100
FRAME_OFFSET = 1   # so argument value 0.0 maps to frame 1, not 0


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
        anim_indices = [
            i for i, n in enumerate(self._nodes)
            if n.type in t.ANIMATING_NODE_TYPES
        ]
        if not anim_indices:
            return None

        arm_data = bpy.data.armatures.new(f"{self._model_name}_rig")
        arm_obj = bpy.data.objects.new(f"{self._model_name}_rig", arm_data)
        self._collection.objects.link(arm_obj)
        arm_obj.matrix_world = self._axis_mat
        self._arm_obj = arm_obj

        # Edit-mode is required to add bones.
        bpy.context.view_layer.objects.active = arm_obj
        prev_mode = bpy.context.object.mode if bpy.context.object else "OBJECT"
        try:
            bpy.ops.object.mode_set(mode="EDIT")
            self._create_bones(anim_indices, arm_data)
            self._set_bone_parents(anim_indices, arm_data)
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

        self._build_actions()
        self._stack_actions_into_nla()
        return arm_obj

    # ----------------------------------------------------------- internals
    def _create_bones(self, anim_indices: List[int], arm_data) -> None:
        edit_bones = arm_data.edit_bones
        for idx in anim_indices:
            node = self._nodes[idx]
            bone_name = self._bone_name_for(idx, node)
            bone = edit_bones.new(bone_name)

            # Place the bone head at the rest-pose translation derived
            # from the node's parent chain so meshes parented to the bone
            # land at the correct default position.
            world = xf.world_matrix_for_node(idx, self._nodes)
            head = world.translation
            bone.head = head
            # 10 cm tail along world +Z is a sensible default; users will
            # rarely visualise these bones outside debug.
            bone.tail = head + mathutils.Vector((0.0, 0.0, 0.1))
            self._bone_for_node[idx] = bone_name

    def _set_bone_parents(self, anim_indices: List[int], arm_data) -> None:
        edit_bones = arm_data.edit_bones
        for idx in anim_indices:
            node = self._nodes[idx]
            parent_idx = self._first_animating_ancestor(getattr(node, "parent_idx", -1))
            if parent_idx >= 0 and parent_idx in self._bone_for_node:
                child = edit_bones[self._bone_for_node[idx]]
                child.parent = edit_bones[self._bone_for_node[parent_idx]]

    def _first_animating_ancestor(self, idx: int) -> int:
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
        # Sanitise: spaces / dots break fcurve datapaths.
        raw = (getattr(node, "name", "") or f"bone_{idx}").replace(" ", "_").replace(".", "_")
        # Avoid collisions with already-named bones.
        existing = {b for b in self._bone_for_node.values()}
        if raw not in existing:
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
            elif isinstance(node, t.ArgVisibilityNode):
                # Visibility is a per-object property, not a bone property,
                # so we postpone applying it until after the meshes are
                # built. We only stash the data here.
                self._arm_obj["edm_visibility_node_{}".format(idx)] = (
                    "node_{}".format(idx)
                )

    def _build_arg_anim_actions(self, node: t.ArgAnimationNode, bone_name: str) -> None:
        # Position
        for arg, keys in node.pos_data:
            if not keys:
                continue
            action = self._action_for_arg(arg)
            data_path = f'pose.bones["{bone_name}"].location'
            for key in keys:
                frame = _arg_to_frame(key.frame)
                value = tuple(key.value)
                for ch in range(min(3, len(value))):
                    fcurve = (
                        action.fcurves.find(data_path, index=ch)
                        or action.fcurves.new(data_path, index=ch, action_group=bone_name)
                    )
                    fcurve.keyframe_points.insert(frame, value[ch])

        # Rotation (quaternion w,x,y,z)
        for arg, keys in node.rot_data:
            if not keys:
                continue
            action = self._action_for_arg(arg)
            data_path = f'pose.bones["{bone_name}"].rotation_quaternion'
            for key in keys:
                frame = _arg_to_frame(key.frame)
                w, x, y, z = key.value
                for ch, comp in enumerate((w, x, y, z)):
                    fcurve = (
                        action.fcurves.find(data_path, index=ch)
                        or action.fcurves.new(data_path, index=ch, action_group=bone_name)
                    )
                    fcurve.keyframe_points.insert(frame, comp)

        # Scale: spec says we don't fully understand the scale data; we
        # use the first set of 4-float keys (XYZ + uniform).
        for arg, (keys_a, _keys_b) in node.scale_data:
            if not keys_a:
                continue
            action = self._action_for_arg(arg)
            data_path = f'pose.bones["{bone_name}"].scale'
            for key in keys_a:
                frame = _arg_to_frame(key.frame)
                sx, sy, sz, _ = key.value
                for ch, comp in enumerate((sx, sy, sz)):
                    fcurve = (
                        action.fcurves.find(data_path, index=ch)
                        or action.fcurves.new(data_path, index=ch, action_group=bone_name)
                    )
                    fcurve.keyframe_points.insert(frame, comp)

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
                strip.action_frame_start = 1
                strip.action_frame_end = max(
                    101,
                    int(max(
                        (kp.co[0] for fcurve in action.fcurves for kp in fcurve.keyframe_points),
                        default=101,
                    )),
                )
            except RuntimeError:
                # Two actions trying to overlap on the same track —
                # extremely rare but handled defensively.
                continue
        # Clear the active action; the NLA strips encode everything.
        ad.action = None


# ---------------------------------------------------------------------------
#  Visibility actions (applied to mesh objects themselves)
# ---------------------------------------------------------------------------


def apply_visibility_actions(
    nodes,
    obj_for_node: Dict[int, bpy.types.Object],
    model_name: str,
) -> None:
    """Translate every ArgVisibilityNode into hide_render fcurves.

    ``obj_for_node`` maps a node index to the Blender Object that should
    receive the visibility animation. (For meshes parented through an
    animating ancestor that is itself a visibility node, the object is
    the mesh.)
    """
    for idx, node in enumerate(nodes):
        if not isinstance(node, t.ArgVisibilityNode):
            continue
        obj = obj_for_node.get(idx)
        if obj is None:
            # No mesh is directly parented under this visibility node;
            # this can happen for empty ArgVisibilityNodes that just
            # forward visibility to children. Silently ignore.
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
