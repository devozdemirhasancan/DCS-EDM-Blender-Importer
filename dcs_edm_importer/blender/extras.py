"""
Non-mesh scene objects: connectors, lights and similar attachments.

These objects don't carry geometry but they're important for the
authoring workflow — DCS uses them to bolt cockpits onto fuselages, to
mark hardpoints, to hint at light positions, etc.
"""

from __future__ import annotations

from typing import Optional, Sequence

import bpy
import mathutils

from ..edm import types as t
from . import transforms as xf


def create_connector(
    connector: t.Connector,
    nodes: Sequence,
    axis_mat: mathutils.Matrix,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    """Create an Empty representing one EDM Connector."""
    obj = bpy.data.objects.new(connector.name or "edm_connector", None)
    obj.empty_display_type = "CUBE"
    obj.empty_display_size = 0.05
    obj["edm_node_type"] = "Connector"
    obj["edm_parent_node"] = int(connector.parent)
    if connector.props:
        # Forward any base-properties (e.g. {"Type": "bounding_box"}).
        for k, v in connector.props.items():
            try:
                obj[f"edm_prop_{k}"] = v
            except (TypeError, ValueError):
                pass
    collection.objects.link(obj)
    world = xf.world_matrix_for_node(connector.parent, nodes) if connector.parent >= 0 else mathutils.Matrix.Identity(4)
    obj.matrix_world = axis_mat @ world
    return obj


def create_light(
    light: t.LightNode,
    nodes: Sequence,
    axis_mat: mathutils.Matrix,
    collection: bpy.types.Collection,
) -> Optional[bpy.types.Object]:
    """Create a Blender Point light from an EDM LightNode.

    EDM's light properties are very free-form (varies by aircraft) so we
    do best-effort mapping: 'color' -> light colour, 'distance' /
    'range' -> light distance, default to a medium-energy point light.
    """
    light_data = bpy.data.lights.new(name=light.name or "edm_light", type="POINT")
    obj = bpy.data.objects.new(name=light.name or "edm_light", object_data=light_data)
    collection.objects.link(obj)

    obj["edm_node_type"] = "LightNode"
    obj["edm_parent_node"] = int(light.parent)

    # Best-effort uniform mapping
    props = light.light_props or {}
    color = props.get("color")
    if color and len(color) >= 3:
        light_data.color = (color[0], color[1], color[2])
    energy = props.get("intensity") or props.get("brightness") or 100.0
    try:
        light_data.energy = float(energy) * 100.0
    except (TypeError, ValueError):
        light_data.energy = 100.0
    distance = props.get("distance") or props.get("range")
    if distance:
        try:
            light_data.shadow_soft_size = max(0.05, float(distance) * 0.1)
        except (TypeError, ValueError):
            pass

    world = xf.world_matrix_for_node(light.parent, nodes) if light.parent >= 0 else mathutils.Matrix.Identity(4)
    obj.matrix_world = axis_mat @ world
    return obj
