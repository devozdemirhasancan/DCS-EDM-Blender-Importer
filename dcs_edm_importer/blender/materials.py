"""
EDM -> Blender material conversion.

We map DCS shader categories (``def_material``, ``glass_material``,
``self_illum_material`` ...) onto a Principled BSDF preset and then layer
on the textures and uniforms that the EDM material defines.

Why Principled BSDF?
    It's the standard PBR shader in Blender 4.x and survives any export
    (glTF, FBX, Cycles/Eevee both work). Where DCS uses non-PBR concepts
    (e.g. ``selfIlluminationValue``) we route them to the closest
    Principled input (``Emission Strength``).

Because Blender 4.0 changed the default Principled BSDF input names
(e.g. ``Emission`` -> ``Emission Color``, ``Specular`` -> ``Specular IOR Level``)
we look up sockets by name with a small fallback table.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional

import bpy

from ..edm import types as t
from .textures import TextureResolver


# ---------------------------------------------------------------------------
#  Texture role -> Principled BSDF socket mapping
# ---------------------------------------------------------------------------

# EDM texture indices (per the spec) and the Principled BSDF input we want
# to drive with them. ``None`` for sockets means we attach the texture but
# don't link it to any input — useful when we want it kept around for the
# user to wire manually.
_DIFFUSE_INDEX = 0
_NORMAL_INDEX = 1
_SPECULAR_INDEX = 2

# Materials whose final-render output should glow regardless of lighting.
_SELF_ILLUM_MATERIALS = frozenset({
    "self_illum_material",
    "additive_self_illum_material",
    "transparent_self_illum_material",
    "lines_material",
    "bano_material",
    "fake_omni_lights",
    "fake_spot_lights",
    "fake_als_lights",
})

# Materials that should be treated as transparent / glassy.
_GLASS_MATERIALS = frozenset({
    "glass_material",
    "transparent_self_illum_material",
})

# Materials that should be more reflective / metallic-ish.
_METALLIC_MATERIALS = frozenset({
    "chrome_material",
    "mirror_material",
})


# ---------------------------------------------------------------------------
#  Helpers for Blender 4.x socket-name compatibility
# ---------------------------------------------------------------------------


def _input(bsdf, *candidates: str):
    """Return the first matching socket on ``bsdf`` from ``candidates``.

    Allows us to write ``_input(bsdf, "Emission Color", "Emission")`` and
    work on any Blender 3.x or 4.x release.
    """
    for name in candidates:
        if name in bsdf.inputs:
            return bsdf.inputs[name]
    return None


def _set_socket(bsdf, value, *candidates: str) -> None:
    socket = _input(bsdf, *candidates)
    if socket is None:
        return
    try:
        socket.default_value = value
    except (TypeError, AttributeError):
        pass


# ---------------------------------------------------------------------------
#  Builder
# ---------------------------------------------------------------------------


class MaterialBuilder:
    """Creates / caches Blender materials for a single EDM import session."""

    def __init__(self, resolver: TextureResolver):
        self._resolver = resolver
        self._cache: Dict[str, bpy.types.Material] = {}

    # ------------------------------------------------------------- public
    def build(self, edm_mat: t.Material, fallback_name: str) -> bpy.types.Material:
        name = self._material_name(edm_mat, fallback_name)
        if name in self._cache:
            return self._cache[name]
        if name in bpy.data.materials:
            mat = bpy.data.materials[name]
            self._cache[name] = mat
            return mat

        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        mat["edm_material"] = edm_mat.material_name
        mat["edm_blending"] = edm_mat.blending

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        out = nodes.new("ShaderNodeOutputMaterial")
        out.location = (320, 0)
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        self._configure_shader_for_material(bsdf, edm_mat)
        self._apply_textures(mat, bsdf, edm_mat)
        self._apply_blending(mat, edm_mat)

        self._cache[name] = mat
        return mat

    # ----------------------------------------------------------- internal
    @staticmethod
    def _material_name(edm_mat: t.Material, fallback: str) -> str:
        return edm_mat.name or edm_mat.material_name or fallback

    @staticmethod
    def _configure_shader_for_material(bsdf, edm_mat: t.Material) -> None:
        """Apply uniform-driven defaults to the Principled BSDF."""
        uniforms = edm_mat.uniforms or {}

        # Reflection / specular
        spec_factor = float(uniforms.get("specFactor", 0.5))
        _set_socket(bsdf, max(0.0, min(1.0, spec_factor)),
                    "Specular IOR Level", "Specular")

        spec_power = float(uniforms.get("specPower", 0.5))
        # specPower 0..1 in EDM uniforms, used to drive roughness inversely.
        roughness = max(0.0, min(1.0, 1.0 - spec_power))
        _set_socket(bsdf, roughness, "Roughness")

        diffuse_value = uniforms.get("diffuseValue")
        if isinstance(diffuse_value, (int, float)):
            # Slight desaturation when diffuseValue < 1 so the model isn't
            # unrealistically bright.
            v = float(diffuse_value)
            _set_socket(bsdf, (v, v, v, 1.0), "Base Color")

        if edm_mat.material_name in _METALLIC_MATERIALS:
            _set_socket(bsdf, 1.0, "Metallic")
            _set_socket(bsdf, 0.05, "Roughness")

        if edm_mat.material_name in _GLASS_MATERIALS:
            _set_socket(bsdf, 0.05, "Roughness")
            _set_socket(bsdf, 1.5, "IOR")
            _set_socket(bsdf, 0.0, "Metallic")
            transmission = _input(bsdf, "Transmission Weight", "Transmission")
            if transmission is not None:
                transmission.default_value = 0.95

        if edm_mat.material_name in _SELF_ILLUM_MATERIALS:
            illum = float(uniforms.get("selfIlluminationValue", 1.0))
            color = uniforms.get("selfIlluminationColor", (1.0, 1.0, 1.0))
            color4 = (color[0], color[1], color[2], 1.0) if len(color) >= 3 else (1.0, 1.0, 1.0, 1.0)
            _set_socket(bsdf, color4, "Emission Color", "Emission")
            _set_socket(bsdf, max(0.5, illum), "Emission Strength")

    def _apply_textures(self, mat: bpy.types.Material, bsdf, edm_mat: t.Material) -> None:
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        diffuse = edm_mat.texture_by_index(_DIFFUSE_INDEX)
        if diffuse is not None:
            tex_node = self._make_image_node(nodes, diffuse, color_space="sRGB")
            tex_node.location = (-540, 240)
            base_color = _input(bsdf, "Base Color")
            if base_color is not None:
                links.new(tex_node.outputs["Color"], base_color)
            # Alpha channel routing if the material flags an alpha mask
            if edm_mat.has_alpha_channel:
                alpha = _input(bsdf, "Alpha")
                if alpha is not None:
                    links.new(tex_node.outputs["Alpha"], alpha)
            # Self-illuminated materials route the same texture to emission
            if edm_mat.material_name in _SELF_ILLUM_MATERIALS:
                emission = _input(bsdf, "Emission Color", "Emission")
                if emission is not None:
                    links.new(tex_node.outputs["Color"], emission)

        normal = edm_mat.texture_by_index(_NORMAL_INDEX)
        if normal is not None:
            tex_node = self._make_image_node(nodes, normal, color_space="Non-Color")
            tex_node.location = (-820, -40)
            nm_node = nodes.new("ShaderNodeNormalMap")
            nm_node.location = (-540, -40)
            links.new(tex_node.outputs["Color"], nm_node.inputs["Color"])
            normal_in = _input(bsdf, "Normal")
            if normal_in is not None:
                links.new(nm_node.outputs["Normal"], normal_in)

        spec = edm_mat.texture_by_index(_SPECULAR_INDEX)
        if spec is not None:
            tex_node = self._make_image_node(nodes, spec, color_space="Non-Color")
            tex_node.location = (-820, -320)
            roughness_in = _input(bsdf, "Roughness")
            if roughness_in is not None:
                # EDM spec maps store specular brightness; invert to get roughness.
                invert = nodes.new("ShaderNodeInvert")
                invert.location = (-540, -320)
                links.new(tex_node.outputs["Color"], invert.inputs["Color"])
                links.new(invert.outputs["Color"], roughness_in)

    def _make_image_node(self, nodes, texture: t.Texture, color_space: str = "sRGB"):
        tex_node = nodes.new("ShaderNodeTexImage")
        tex_node.label = texture.name
        path = self._resolver.resolve(texture.name)
        if path:
            try:
                img = bpy.data.images.load(path, check_existing=True)
                if color_space == "Non-Color" and hasattr(img, "colorspace_settings"):
                    img.colorspace_settings.name = "Non-Color"
                tex_node.image = img
            except RuntimeError as exc:
                print(f"[EDM] Warning: could not load texture {path!r}: {exc}")
        else:
            print(f"[EDM] Texture not found on disk: {texture.name!r}")
        return tex_node

    @staticmethod
    def _apply_blending(mat: bpy.types.Material, edm_mat: t.Material) -> None:
        """Translate the EDM BLENDING enum into Blender material settings."""
        # 0=None, 1=Blend, 2=Alpha Test, 3=Additive Blending
        blending = edm_mat.blending or 0
        if blending == 0:
            mat.blend_method = "OPAQUE"
        elif blending == 1:
            mat.blend_method = "BLEND"
        elif blending == 2:
            mat.blend_method = "CLIP"
        elif blending == 3:
            mat.blend_method = "BLEND"
            # Additive: drive emission so it ADDs in the final compositor pass.
        else:
            mat.blend_method = "OPAQUE"

        # CULLING == 0 in EDM means "no culling" -> show backface.
        mat.use_backface_culling = bool(edm_mat.culling)
