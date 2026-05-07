# Troubleshooting Recipes

Copy-paste fixes for the most common annoyances. Always start by
opening Blender's **system console** so you can see what the importer
is logging.

## Recipe 1 — Hide every collision shell after import

```python
import bpy
for obj in bpy.context.scene.objects:
    if obj.get("edm_is_collision"):
        obj.hide_set(True)
        obj.hide_render = True
```

## Recipe 2 — Auto-unmute a single argument's animation

```python
import bpy

WANTED_ARG = 2   # 2 = elevator on most aircraft

for arm in [o for o in bpy.data.objects if o.type == "ARMATURE"]:
    ad = arm.animation_data
    if ad is None:
        continue
    for track in ad.nla_tracks:
        track.mute = True
        for strip in track.strips:
            if strip.action.get("edm_argument") == WANTED_ARG:
                track.mute = False
```

## Recipe 3 — Bake every animation into the action editor

When you want to scrub multiple arguments at once:

```python
import bpy
arm = bpy.context.active_object  # must be the armature
for track in arm.animation_data.nla_tracks:
    track.mute = False
# Then File → Bake → Bake Animation
```

## Recipe 4 — Spot connectors

```python
import bpy
for obj in bpy.context.scene.objects:
    if obj.type == "EMPTY" and obj.get("edm_node_type") == "Connector":
        obj.show_name = True
        obj.empty_display_size = 0.15
```

## Recipe 5 — Filter by LOD

Show only the highest-detail level (lowest `edm_lod_min`):

```python
import bpy
all_lod_objs = [o for o in bpy.context.scene.objects if "edm_lod_min" in o]
if all_lod_objs:
    closest = min(o.get("edm_lod_min", 0.0) for o in all_lod_objs)
    for obj in bpy.context.scene.objects:
        lod_min = obj.get("edm_lod_min")
        if lod_min is not None and lod_min > closest + 1.0:
            obj.hide_set(True)
```

## Recipe 6 — Un-pack every imported texture into the .blend

If you want a fully self-contained .blend file:

```python
import bpy
bpy.ops.file.pack_all()
```

## Recipe 7 — Replace all materials with a flat clay shader

Useful for sculpting / modelling references:

```python
import bpy
clay = bpy.data.materials.new("CLAY")
clay.use_nodes = True
bsdf = clay.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1.0)
bsdf.inputs["Roughness"].default_value = 0.9

for obj in bpy.context.scene.objects:
    if obj.type != "MESH":
        continue
    obj.data.materials.clear()
    obj.data.materials.append(clay)
```

## Recipe 8 — Force-reload a missing texture

When the texture wasn't on disk during import but you've since added
it:

```python
import bpy, os
for img in bpy.data.images:
    if img.filepath and not os.path.exists(bpy.path.abspath(img.filepath)):
        # Try a manual override path here
        candidate = "C:/path/to/textures/" + os.path.basename(img.filepath)
        if os.path.exists(candidate):
            img.filepath = candidate
            img.reload()
```
