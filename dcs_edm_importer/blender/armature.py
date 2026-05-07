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
  * The lowest-numbered action is set as the armature's *active* action
    so the user sees animation immediately when scrubbing the timeline.
  * Other actions are kept in ``bpy.data.actions`` for the user to
    select via the Action Editor's "Browse" dropdown.
  * Visibility arguments become per-object ``hide_render`` actions
    (handled in :func:`apply_visibility_actions`).

Why no NLA stack? The previous implementation pushed every action into
its own NLA track *muted by default*, which silently broke the
"timeline scrub shows nothing" path for users. Keeping actions in
the library and binding the most-likely default makes the UI obvious.

Frame mapping: argument value 0.0 -> frame 1, 1.0 -> frame 101.

Why include plain Bones in the armature? Because SkinNode references
them by index. Without them in the armature, skin weights have nowhere
to attach. Static bones simply don't have any keyframe data.
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
        self._activate_default_action()
        return arm_obj

    # ----------------------------------------------------------- internals
    def _create_bones(self, bone_indices: List[int], arm_data) -> None:
        edit_bones = arm_data.edit_bones
        for idx in bone_indices:
            node = self._nodes[idx]
            bone_name = self._bone_name_for(idx, node)
            bone = edit_bones.new(bone_name)

            world = xf.world_matrix_for_node(idx, self._nodes)
            head = world.translation
            # A length of 0.05 (5 cm) gives the bone enough volume that
            # Blender doesn't auto-delete it but stays small enough to be
            # invisible against a typical aircraft mesh.
            bone.head = head
            bone.tail = head + mathutils.Vector((0.0, 0.05, 0.0))
            self._bone_for_node[idx] = bone_name

    def _set_bone_parents(self, bone_indices: List[int], arm_data) -> None:
        edit_bones = arm_data.edit_bones
        for idx in bone_indices:
            node = self._nodes[idx]
            parent_idx = self._first_rig_ancestor(getattr(node, "parent_idx", -1))
            if parent_idx >= 0 and parent_idx in self._bone_for_node:
                child = edit_bones[self._bone_for_node[idx]]
                child.parent = edit_bones[self._bone_for_node[parent_idx]]

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
        # Sanitise: spaces and dots break fcurve datapaths. Append the
        # scene-graph index to guarantee uniqueness.
        raw = (getattr(node, "name", "") or "bone").replace(" ", "_").replace(".", "_")
        return f"{raw}_{idx:04d}"

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

        Pose-bone keyframes are written *as-is* — DCS keyframe values
        already describe the local delta relative to the rest pose,
        which is exactly what Blender's pose-bone ``location`` /
        ``rotation_quaternion`` / ``scale`` datapaths expect. Pre-
        composing ``Quat1`` (as our previous implementation did) ended
        up double-applying the rest rotation in many cases, so we
        keep the fcurve values direct.

        The bone's rest pose already includes ``Quat1`` because we
        built it from :func:`world_matrix_for_node` which composes the
        full ``base.matrix * Translate(pos) * Quat1 * Scale * Quat2``
        chain.
        """
        # ---- Position keyframes ---------------------------------------
        for arg, keys in node.pos_data:
            if not keys:
                continue
            action = self._action_for_arg(arg)
            data_path = f'pose.bones["{bone_name}"].location'
            for key in keys:
                frame = _arg_to_frame(key.frame)
                value = tuple(key.value)
                for ch in range(min(3, len(value))):
                    fc = self._fcurve(action, data_path, ch, bone_name)
                    fc.keyframe_points.insert(frame, float(value[ch]))

        # ---- Rotation keyframes ---------------------------------------
        for arg, keys in node.rot_data:
            if not keys:
                continue
            action = self._action_for_arg(arg)
            data_path = f'pose.bones["{bone_name}"].rotation_quaternion'
            for key in keys:
                frame = _arg_to_frame(key.frame)
                key_quat = xf.quat_from_wxyz(key.value)
                for ch, comp in enumerate(
                    (key_quat.w, key_quat.x, key_quat.y, key_quat.z)
                ):
                    fc = self._fcurve(action, data_path, ch, bone_name)
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
                if len(key.value) >= 3:
                    sx, sy, sz = key.value[0], key.value[1], key.value[2]
                else:
                    sx = sy = sz = 1.0
                for ch, comp in enumerate((sx, sy, sz)):
                    fc = self._fcurve(action, data_path, ch, bone_name)
                    fc.keyframe_points.insert(frame, float(comp))

    @staticmethod
    def _fcurve(action, data_path: str, index: int, group: str):
        fc = action.fcurves.find(data_path, index=index)
        if fc is None:
            fc = action.fcurves.new(data_path, index=index, action_group=group)
        return fc

    def _action_for_arg(self, arg: int) -> bpy.types.Action:
        action = self._actions.get(arg)
        if action is None:
            action = bpy.data.actions.new(f"{self._model_name}_arg{arg:03d}")
            action["edm_argument"] = int(arg)
            # Mark with a fake-user so the action survives the next
            # "Save & Reload" round-trip even when no armature is
            # currently bound to it.
            action.use_fake_user = True
            self._actions[arg] = action
        return action

    def _activate_default_action(self) -> None:
        """Bind the lowest-numbered action so timeline scrubbing works.

        DCS argument 0 is, by overwhelming convention, the aileron — so
        new users immediately see *something* moving when they scrub the
        timeline. They can pick a different action via the Action
        Editor's "Browse" dropdown.
        """
        if not self._arm_obj or not self._actions:
            return
        ad = self._arm_obj.animation_data
        if ad is None:
            return
        first_arg = min(self._actions.keys())
        ad.action = self._actions[first_arg]


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
            action_name = f"{model_name}_vis_arg{arg:03d}_{idx:04d}"
            action = bpy.data.actions.new(action_name)
            action["edm_argument"] = int(arg)
            action.use_fake_user = True
            curve = action.fcurves.new("hide_render")
            for (start, end) in ranges:
                f_start = _arg_to_frame(start)
                f_end = _arg_to_frame(min(end, 1.0)) if end < 1e6 else _arg_to_frame(1.0)
                kp = curve.keyframe_points.insert(f_start, 0.0)
                kp.interpolation = "CONSTANT"
                kp = curve.keyframe_points.insert(f_end, 1.0)
                kp.interpolation = "CONSTANT"
