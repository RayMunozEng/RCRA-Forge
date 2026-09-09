"""
ui/viewport.py
3D OpenGL viewport widget for RCRA Forge.

Uses PyQt6 QOpenGLWidget with a minimal forward-compatible core profile
shader pipeline. Renders mesh sub-meshes with per-material shading and
supports arcball camera navigation.
"""

import math
import re
import time
from pathlib import Path
import numpy as np
from typing import Optional

from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QImage, QMouseEvent, QWheelEvent

from core.cube_texture import validate_cube_mips
from core.hair_temporal import (
    TEMPORAL_ACC_ALPHA_MOTION_THRESHOLD,
    TEMPORAL_DISOCCLUSION_CAPTURE_DEPTH_BASE,
    TEMPORAL_DISOCCLUSION_CAPTURE_DEPTH_SLOPE,
    TEMPORAL_DISOCCLUSION_CAPTURE_MOTION_THRESHOLD,
    temporal_apply_misc,
    temporal_disocclusion_camera_scale,
    temporal_dither_constants,
)
from ui.camera_controls import AUTODESK_CONTROL_TOOLTIP, autodesk_mouse_mode
from ui.controls_dialog import load_controls

try:
    from OpenGL.GL import *
    from OpenGL.GL.shaders import compileShader, compileProgram
    from OpenGL.raw.GL.VERSION.GL_1_1 import glTexImage2D as _raw_tex_image_2d
    from OpenGL.raw.GL.VERSION.GL_1_3 import glCompressedTexImage2D as _raw_compressed_tex_image_2d
    _HAS_OPENGL = True
except ImportError:
    _HAS_OPENGL = False

from core.mesh import (
    MeshDefinition,
    ModelAsset,
    mesh_decode_corrections_to_numpy,
    mesh_tangents_to_numpy,
    mesh_to_numpy,
)
from core.model_strands import (
    CAPTURED_WIND_STRENGTH as MODEL_STRAND_CAPTURED_WIND_STRENGTH,
    CAPTURED_WIND_TIME as MODEL_STRAND_CAPTURED_WIND_TIME,
    PROFILES as MODEL_STRAND_PROFILES,
    build_group as build_model_strand_group,
    fixture_directory as model_strand_fixture_directory,
    ratchet_strand_fixtures_available,
)


BASE_COLOR_ROLES = ('base_color', 'color_id', 'albedo', 'diffuse')
NORMAL_ROLES = ('normal',)
SPECULAR_COLOR_ROLES = ('specular_color', 'specular')
FUR_CONTROL_ROLES = ('fur_control',)
EMISSIVE_ROLES = ('emissive',)
EFFECT_MASK_ROLES = ('effect_mask', 'mask')
NOISE_ROLES = ('noise',)
RETAIL_LAVA_COLOR_A_ROLES = ('retail_lava_color_a',)
RETAIL_LAVA_COLOR_B_ROLES = ('retail_lava_color_b',)
RETAIL_LAVA_NORMAL_A_ROLES = ('retail_lava_normal_a',)
RETAIL_LAVA_NORMAL_B_ROLES = ('retail_lava_normal_b',)
RETAIL_LAVA_NOISE_ROLES = ('retail_lava_noise',)
RETAIL_LAVA_MASK_A_ROLES = ('retail_lava_mask_a',)
RETAIL_LAVA_MASK_B_ROLES = ('retail_lava_mask_b',)


def _supports_native_raster(
    version: tuple[int, int], extensions,
) -> bool:
    """Return whether one context can provide the recovered raster contract."""
    major, minor = (int(version[0]), int(version[1]))
    extension_names = {
        item.encode('ascii') if isinstance(item, str) else bytes(item)
        for item in extensions
    }
    return (major, minor) >= (4, 5) or b'GL_ARB_clip_control' in extension_names


def _shader_with_raster_mode(source: str, native_upper_left: bool) -> str:
    """Inject the viewport raster convention immediately after ``#version``."""
    if not native_upper_left:
        return source
    version = re.search(r'(?m)^#version[^\r\n]*(?:\r?\n|$)', source)
    if version is None:
        raise ValueError('viewport shader source is missing #version')
    return (
        source[:version.end()]
        + '#define RCRA_NATIVE_UPPER_LEFT 1\n'
        + source[version.end():]
    )


def _postprocess_settings(has_retail_lava: bool) -> tuple[float, float]:
    """Return isolated-view exposure and bloom strength."""
    if has_retail_lava:
        # Rift Apart adapts exposure from the full Blizar cavern.  This neutral
        # reference keeps authored BC6H lava detail visible in isolation while
        # giving the glow less weight than the surface itself.
        return 0.55, 0.20
    return 1.0, 0.55


def _compressed_gl_format(dxgi_format: int, srgb: bool = False):
    """Preserve explicit DXGI sRGB formats, including packed response maps.

    The role hint may promote untagged color textures; it must not demote an
    authored sRGB format. BC7 already observes this rule. Sheep uses BC1 sRGB
    for gloss/specular, so losing the tag changes the recovered hair response.
    """
    if dxgi_format in (0x47, 0x48):
        return 0x8C4D if srgb or dxgi_format == 0x48 else 0x83F1  # sRGB/RGBA S3TC DXT1
    if dxgi_format in (0x4A, 0x4B):
        return 0x8C4E if srgb or dxgi_format == 0x4B else 0x83F2  # sRGB/RGBA S3TC DXT3
    if dxgi_format in (0x4D, 0x4E):
        return 0x8C4F if srgb or dxgi_format == 0x4E else 0x83F3  # sRGB/RGBA S3TC DXT5
    return {
        0x4F: GL_COMPRESSED_RED_RGTC1,
        0x50: GL_COMPRESSED_RED_RGTC1,
        0x51: GL_COMPRESSED_SIGNED_RED_RGTC1,
        0x53: GL_COMPRESSED_RG_RGTC2,
        0x54: GL_COMPRESSED_SIGNED_RG_RGTC2,
        0x5F: GL_COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT,
        0x60: GL_COMPRESSED_RGB_BPTC_SIGNED_FLOAT,
        0x62: GL_COMPRESSED_SRGB_ALPHA_BPTC_UNORM
            if srgb else GL_COMPRESSED_RGBA_BPTC_UNORM,
        0x63: GL_COMPRESSED_SRGB_ALPHA_BPTC_UNORM,
    }.get(dxgi_format)


def _scaled_framebuffer_size(width: int, height: int,
                             device_pixel_ratio: float) -> tuple[int, int]:
    """Convert Qt logical widget dimensions to physical OpenGL pixels."""
    scale = float(device_pixel_ratio)
    if not math.isfinite(scale) or scale <= 0.0:
        scale = 1.0
    return (
        max(1, int(math.floor(max(0, int(width)) * scale + 0.5))),
        max(1, int(math.floor(max(0, int(height)) * scale + 0.5))),
    )


def _is_lava_material(material_name: str) -> bool:
    """Return whether a material should use the animated molten-surface path."""
    name = (material_name or '').replace('\\', '/').lower()
    tokens = set(re.findall(r'[a-z0-9]+', name))
    # Lava-rock assets are solid textured rock with emissive cracks. Sending
    # them through the fully molten shader discards their decoded base colour.
    if tokens.intersection({'rock', 'rocks', 'stone', 'boulder', 'cliff'}):
        return False
    return any(token in name for token in ('lava', 'magma', 'molten'))


def _is_retail_blizar_lava_material(material_name: str) -> bool:
    """Match the decoded Blizar flow graph instance used by rock and lavafall."""
    name = (material_name or '').replace('\\', '/').lower()
    return 'blz_gbl_lava_01_flow' in name


def _uses_molten_shader(material_name: str, source_path: str = '') -> bool:
    """Use molten animation for lava surfaces, never for solid lava-rock models."""
    model_path = (source_path or '').replace('\\', '/').lower()
    return _is_lava_material(material_name) and 'lava_rock' not in model_path


def _is_lava_rock_model(source_path: str = '') -> bool:
    """Identify solid lava-rock geometry that needs restrained crack emission."""
    model_path = (source_path or '').replace('\\', '/').lower()
    return 'lava_rock' in model_path


def _is_lavafall_model(source_path: str = '') -> bool:
    """Identify vertical lavafall meshes that need one-way downward flow."""
    model_path = (source_path or '').replace('\\', '/').lower()
    return 'lavafall' in model_path or 'lava_fall' in model_path


def _lava_flow_sample_offsets(source_path: str = '') -> tuple[tuple[float, float],
                                                               tuple[float, float]]:
    """Return UV sampling velocities for the two animated lava layers.

    Texture features move opposite the sampling offset.  The Blizar lavafall's
    V coordinate increases from its top to its bottom, so negative-V sampling
    makes the visible lava travel downward instead of climbing the waterfall.
    """
    if _is_lavafall_model(source_path):
        return (0.0, -0.090), (0.0, -0.055)
    return (0.024, 0.011), (-0.017, 0.029)


def _resolved_mesh_uvs(positions: np.ndarray, normals: np.ndarray,
                       uvs: np.ndarray, scale: float = 0.55
                       ) -> tuple[np.ndarray, bool]:
    """Preserve authored UVs or generate box projection for world-mapped meshes."""
    if uvs is not None and len(uvs) == len(positions) and len(uvs):
        finite = np.isfinite(uvs).all()
        spans = np.ptp(uvs, axis=0) if finite else np.zeros(2, dtype=np.float32)
        if finite and float(np.max(spans)) > 1e-5:
            return uvs.astype(np.float32, copy=False), False

    projected = np.zeros((len(positions), 2), dtype=np.float32)
    valid_normals = normals is not None and len(normals) == len(positions) \
        and np.isfinite(normals).all() and np.any(np.abs(normals) > 1e-6)
    if valid_normals:
        dominant_axes = np.argmax(np.abs(normals), axis=1)
    else:
        # Top projection is the least surprising fallback for ground/landscape
        # meshes, which are the common game assets authored without UVs.
        dominant_axes = np.full(len(positions), 1, dtype=np.int8)

    x_faces = dominant_axes == 0
    y_faces = dominant_axes == 1
    z_faces = dominant_axes == 2
    projected[x_faces] = positions[x_faces][:, (2, 1)]
    projected[y_faces] = positions[y_faces][:, (0, 2)]
    projected[z_faces] = positions[z_faces][:, (0, 1)]
    projected *= float(scale)
    return projected, True


def _mesh_tangents(positions: np.ndarray, normals: np.ndarray,
                   uvs: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Expand indexed geometry into stable tangent + handedness vertices."""
    count = len(positions)
    tangent_sum = np.zeros((count, 3), dtype=np.float64)
    bitangent_sum = np.zeros((count, 3), dtype=np.float64)
    triangles = np.asarray(indices, dtype=np.int64).reshape((-1, 3))
    for triangle in triangles:
        p0, p1, p2 = positions[triangle]
        uv0, uv1, uv2 = uvs[triangle]
        edge1 = p1 - p0
        edge2 = p2 - p0
        delta1 = uv1 - uv0
        delta2 = uv2 - uv0
        determinant = float(delta1[0] * delta2[1] - delta1[1] * delta2[0])
        if abs(determinant) <= 1e-12:
            continue
        reciprocal = 1.0 / determinant
        tangent = (edge1 * delta2[1] - edge2 * delta1[1]) * reciprocal
        bitangent = (edge2 * delta1[0] - edge1 * delta2[0]) * reciprocal
        tangent_sum[triangle] += tangent
        bitangent_sum[triangle] += bitangent

    result = np.zeros((count, 4), dtype=np.float32)
    for index in range(count):
        normal = np.asarray(normals[index], dtype=np.float64)
        normal_length = np.linalg.norm(normal)
        if normal_length <= 1e-12:
            normal = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        else:
            normal /= normal_length
        tangent = tangent_sum[index] - normal * np.dot(normal, tangent_sum[index])
        tangent_length = np.linalg.norm(tangent)
        if tangent_length <= 1e-12:
            axis = np.array([0.0, 0.0, 1.0], dtype=np.float64) \
                if abs(normal[2]) < 0.999 else np.array([0.0, 1.0, 0.0])
            tangent = np.cross(axis, normal)
            tangent_length = np.linalg.norm(tangent)
        tangent /= max(tangent_length, 1e-12)
        handedness = -1.0 if np.dot(
            np.cross(normal, tangent), bitangent_sum[index],
        ) < 0.0 else 1.0
        result[index, :3] = tangent
        result[index, 3] = handedness
    return result


def _is_alpha_cutout_material(material_name: str) -> bool:
    """Return whether a material is foliage/card geometry with cutout alpha."""
    name = (material_name or '').replace('\\', '/').lower()
    return any(token in name for token in (
        'grass', 'leaf', 'leaves', 'foliage', 'frond', 'fern',
        'flower', 'petal', 'vine', 'ivy', 'shrub',
    ))


def _is_fur_material(material_name: str) -> bool:
    """Return whether this is a rendered fur surface, not a helper shell."""
    name = (material_name or '').replace('\\', '/').lower()
    if 'nofur' in name or 'no_fur' in name:
        return False
    if 'compositeshell' in name or 'composite_shell' in name:
        return False
    return 'fur' in name


def _is_composite_shell_material(material_name: str) -> bool:
    name = (material_name or '').replace('\\', '/').lower()
    return 'compositeshell' in name or 'composite_shell' in name


def _can_draw_fur_strands(*, show_fur: bool, wireframe: bool,
                          is_composite_shell: bool, albedo_tex_id: int,
                          control_tex_id: int) -> bool:
    """Return whether a mesh has the inputs required for the fur-shell pass."""
    return bool(
        show_fur and not wireframe and not is_composite_shell
        and albedo_tex_id > 0 and control_tex_id > 0
    )


def _is_authored_wool(*, density: float, offset_scale: float) -> bool:
    """Identify the installed zero-groom, low-density wool material regime."""
    return float(density) <= 4.0 and abs(float(offset_scale)) <= 1e-8


def _fur_shell_availability(normal_dot_view: float,
                            decode_correction: float = 0.0) -> float:
    """Reproduce the shipped vertex shader's view-dependent shell budget."""
    front = max(0.0, min(
        float(normal_dot_view) - float(decode_correction) * 0.0065 - 0.025,
        1.0,
    ))
    # DXBC uses dp2(r.wwww, r.wwww): both identical lanes contribute.
    return min(2.0 * (1.0 - front) ** 2 + 0.1, 1.0)


def _fur_adjusted_shell_depth(raw_depth: float, normal_dot_view: float,
                              decode_correction: float = 0.0
                              ) -> Optional[float]:
    """Return the renormalized 0-1 shell depth, or None when retail culls it."""
    ratio = float(raw_depth) / _fur_shell_availability(
        normal_dot_view, decode_correction,
    )
    if ratio > 1.0:
        return None
    return max(0.0, ratio)


def _build_fur_layer_volume(size: int = 128, slices: int = 32,
                            seed: int | None = None) -> np.ndarray:
    """Reproduce the executable's procedural ``Default Fur Shells`` volume.

    ``TextureDefaultsInit`` creates a 128x128x32 R8 array with a fixed-seed
    xorshift128 generator.  A squared uniform variate selects each strand's
    slice count; a parabolic profile softens the upper half of the strand.
    ``size`` and ``slices`` remain arguments for small deterministic tests, but
    the retail constants and fixed seed are used by the viewport.
    """
    size = max(1, int(size))
    slices = max(2, int(slices))
    state = [
        0x075BCD15, 0x159A55E5, 0x1F123BB5, 0x05491333,
    ]
    if seed is not None:
        # Non-retail seeds are useful only for deterministic test variants.
        state[0] = int(seed) & 0xFFFFFFFF

    def xorshift128() -> int:
        first = state[0]
        last = state[3]
        mixed = (first ^ ((first << 11) & 0xFFFFFFFF)) & 0xFFFFFFFF
        value = (
            last ^ (last >> 19) ^ mixed ^ (mixed >> 8)
        ) & 0xFFFFFFFF
        state[:] = [state[1], state[2], state[3], value]
        return value

    height_scale = np.float32(slices) * np.float32(2.0 ** -48)
    profiles = []
    for height in range(1, slices + 1):
        # TextureDefaultsInit computes a float32 reciprocal once, then doubles
        # each layer index before multiplying. Division or Python float math
        # changes coverage 203 to 204 for layer 20 of a 28-layer strand.
        inverse_height = np.float32(1.0) / np.float32(height)
        layer = np.arange(1, height + 1, dtype=np.float32)
        profile = np.maximum(
            (layer + layer) * inverse_height - np.float32(1.0),
            np.float32(0.0),
        )
        coverage = np.clip(
            np.float32(1.0) - (profile * profile) * np.float32(0.8),
            np.float32(0.0), np.float32(1.0),
        )
        profiles.append((coverage * np.float32(255.0)).astype(np.uint8))
    result = np.zeros((slices, size, size), dtype=np.uint8)
    for y in range(size):
        for x in range(size):
            random24 = np.float32(xorshift128() >> 8)
            height = int(np.float32(random24 * random24) * height_scale) + 1
            height = min(height, slices)
            result[:height, x, y] = profiles[height - 1]
    return result


def _build_fur_layer_mips(volume: np.ndarray | None = None,
                          levels: int = 4) -> tuple[np.ndarray, ...]:
    """Build the executable's stored integer-average fur mip chain."""
    current = np.ascontiguousarray(
        _build_fur_layer_volume() if volume is None else volume,
        dtype=np.uint8,
    )
    if current.ndim != 3:
        raise ValueError("fur layer volume must have shape (slices, height, width)")

    chain = [current]
    for _ in range(1, max(1, int(levels))):
        height = current.shape[1] & ~1
        width = current.shape[2] & ~1
        if height < 2 or width < 2:
            break
        source = current[:, :height, :width].astype(np.uint16)
        current = np.ascontiguousarray((
            source[:, 0::2, 0::2]
            + source[:, 1::2, 0::2]
            + source[:, 0::2, 1::2]
            + source[:, 1::2, 1::2]
        ) >> 2, dtype=np.uint8)
        chain.append(current)
    return tuple(chain)


def _role_matches(role_key: str, roles: tuple[str, ...]) -> bool:
    """Match a material role and its indexed variants (for example normal_4)."""
    return any(
        role_key == role or role_key.startswith(f"{role}_")
        for role in roles
    )


def _best_texture_slot(slots: dict, roles: tuple[str, ...]):
    """Return the largest valid texture slot matching one of ``roles``."""
    best = None
    best_pixels = -1
    for role_key, slot_data in (slots or {}).items():
        if not _role_matches(role_key, roles) or len(slot_data) < 3:
            continue
        rgba, width, height = slot_data[0], slot_data[1], slot_data[2]
        pixels = int(width) * int(height)
        if rgba and width > 0 and height > 0 and pixels > best_pixels:
            best = slot_data
            best_pixels = pixels
    return best


def _fur_length_from_texture_slot(slot_data, fallback: float = 0.03) -> float:
    """Read the authored leading fur setting carried with a control map."""
    if slot_data and len(slot_data) > 4 and isinstance(slot_data[4], dict):
        settings = slot_data[4].get('fur_settings')
        if settings:
            try:
                length = float(settings[0])
                if length >= 0.0:
                    return length
            except (TypeError, ValueError, IndexError):
                pass
    return float(fallback)


def _fur_density_from_texture_slot(slot_data, fallback: float = 16.0) -> float:
    """Read the authored Fur_Density setting used for area-normalized roots."""
    if slot_data and len(slot_data) > 4 and isinstance(slot_data[4], dict):
        settings = slot_data[4].get('fur_settings')
        if settings:
            try:
                density = float(settings[1])
                if density >= 0.0:
                    return density
            except (TypeError, ValueError, IndexError):
                pass
    return float(fallback)


def _fur_offset_scale_from_texture_slot(slot_data, fallback: float = 0.0) -> float:
    """Read the authored Fur_OffsetScale setting."""
    if slot_data and len(slot_data) > 4 and isinstance(slot_data[4], dict):
        settings = slot_data[4].get('fur_settings')
        if settings:
            try:
                return float(settings[2])
            except (TypeError, ValueError, IndexError):
                pass
    return float(fallback)


def _fur_shading_from_texture_slot(
    slot_data,
    fallback: tuple[float, float, float] = (1.0, 1.0, 0.0),
) -> tuple[float, float, float]:
    """Read authored gloss, specular, and transmittance scales."""
    if slot_data and len(slot_data) > 4 and isinstance(slot_data[4], dict):
        settings = slot_data[4].get('fur_settings')
        if settings:
            try:
                return tuple(max(float(settings[index]), 0.0) for index in (3, 4, 5))
            except (TypeError, ValueError, IndexError):
                pass
    return tuple(float(value) for value in fallback)


def _fur_wind_turbulence_from_texture_slot(
    slot_data, fallback: float = 0.0,
) -> float:
    """Read the authored ModelFur wind-turbulence scalar."""
    if slot_data and len(slot_data) > 4 and isinstance(slot_data[4], dict):
        settings = slot_data[4].get('fur_settings')
        if settings:
            try:
                return max(float(settings[6]), 0.0)
            except (TypeError, ValueError, IndexError):
                pass
    return max(float(fallback), 0.0)


def _fur_header_from_texture_slot(slot_data) -> tuple[int, float]:
    """Read the authored Fur_LayerCount and Fur_LoDReduction settings."""
    if slot_data and len(slot_data) > 4 and isinstance(slot_data[4], dict):
        metadata = slot_data[4]
        try:
            return (
                max(int(metadata.get('fur_layer_count', 0)), 0),
                max(float(metadata.get('fur_lod_reduction', 0.0)), 0.0),
            )
        except (TypeError, ValueError):
            pass
    return 0, 0.0


def _fur_root_lod_factor(projected_length_pixels: float) -> float:
    """Keep full roots up close and stably thin them below six pixels."""
    x = min(max((float(projected_length_pixels) - 1.0) / 5.0, 0.0), 1.0)
    smooth = x * x * (3.0 - 2.0 * x)
    return 0.25 + 0.75 * smooth


def _fur_tip_width_factors(along: float) -> tuple[float, float]:
    """Return physical taper and pixel-width floor, both zero at the tip."""
    remaining = 1.0 - min(max(float(along), 0.0), 1.0)
    return remaining ** 1.35, 0.65 * remaining ** 0.70


def _merge_material_textures(current: dict, incoming: dict) -> dict:
    """Merge progressive per-role texture batches without dropping prior slots."""
    merged = dict(current or {})
    for mat_idx, slots in (incoming or {}).items():
        if isinstance(slots, dict) and isinstance(merged.get(mat_idx), dict):
            combined = dict(merged[mat_idx])
            combined.update(slots)
            merged[mat_idx] = combined
        else:
            merged[mat_idx] = slots
    return merged


def _is_srgb_texture_role(role: str) -> bool:
    """Base colors are authored in sRGB; data/effect maps stay linear."""
    return role == 'base'


# ── GLSL Shaders ──────────────────────────────────────────────────────────────

VERT_SRC = """
#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNormal;
layout(location=2) in vec2 aUV;
layout(location=3) in vec4 aTangent;
layout(location=5) in vec3 aPreviousPos;

uniform mat4 uMVP;
uniform mat4 uPreviousMVP;
uniform mat4 uModel;
uniform mat3 uNormal;

out vec3 vNormal;
out vec3 vWorldPos;
out vec2 vUV;
out vec4 vPreviousClip;

void main() {
    vec4 worldPos = uModel * vec4(aPos, 1.0);
    vWorldPos  = worldPos.xyz;
    vNormal    = normalize(uNormal * aNormal);
    vUV        = aUV;
    vPreviousClip = uPreviousMVP * vec4(aPreviousPos, 1.0);
    gl_Position = uMVP * vec4(aPos, 1.0);
}
"""

FRAG_SRC = """
#version 330 core
#extension GL_ARB_gpu_shader5 : enable
in vec3 vNormal;
in vec3 vWorldPos;
in vec2 vUV;
in vec4 vPreviousClip;

uniform vec3      uLightDir;
uniform vec3      uFillDir;
uniform vec3      uBaseColor;
uniform bool      uWireframe;
uniform bool      uHasTexture;
uniform bool      uHasNormal;
uniform bool      uHasEmissive;
uniform bool      uHasEffectMask;
uniform bool      uHasNoise;
uniform bool      uIsLava;
uniform bool      uIsLavaRock;
uniform bool      uIsLavaFall;
uniform bool      uIsRetailBlizarLava;
uniform bool      uIsFur;
uniform bool      uHasFurControl;
uniform bool      uAlphaCutout;
uniform float     uTime;
uniform sampler2D uAlbedo;
uniform sampler2D uNormalMap;
uniform sampler2D uEmissiveMap;
uniform sampler2D uEffectMaskMap;
uniform sampler2D uNoiseMap;
uniform sampler2D uRetailLavaColorA;
uniform sampler2D uRetailLavaColorB;
uniform sampler2D uRetailLavaNormalA;
uniform sampler2D uRetailLavaNormalB;
uniform sampler2D uRetailLavaNoise;
uniform sampler2D uRetailLavaMaskA;
uniform sampler2D uRetailLavaMaskB;
uniform sampler2D uFurControlMap;
uniform vec2      uLavaFlowA;
uniform vec2      uLavaFlowB;
uniform vec2      uViewportSize;
uniform float     uMotionNearPlane;

layout(location = 0) out vec4 FragColor;
layout(location = 1) out vec4 BrightColor;
layout(location = 2) out vec4 SceneLinearDepth;
layout(location = 3) out vec2 SceneVelocity;
layout(location = 4) out uint SceneStencil;

// Simple normal perturbation — offsets vertex normal by normal map XY.
// More stable than full cotangent TBN at large world scales.
vec3 perturb_normal(vec3 N, vec2 uv, sampler2D nmap) {
    vec3 nm = texture(nmap, uv).rgb * 2.0 - 1.0;
    // BC5 RG normal map — reconstruct Z
    nm.z = sqrt(max(0.001, 1.0 - dot(nm.xy, nm.xy)));
    // Build a simple local frame from vertex normal
    vec3 up    = abs(N.z) < 0.999 ? vec3(0,0,1) : vec3(1,0,0);
    vec3 T     = normalize(cross(up, N));
    vec3 B     = cross(N, T);
    // Blend: use nm.xy to perturb N, keep Z influence from vertex normal
    vec3 perturbed = normalize(T * nm.x + B * nm.y + N * (nm.z + 0.5));
    return perturbed;
}

vec3 perturb_normal_xy(vec3 N, vec2 normalXY) {
    float normalZ = sqrt(max(0.001, 1.0 - dot(normalXY, normalXY)));
    vec3 up = abs(N.z) < 0.999 ? vec3(0,0,1) : vec3(1,0,0);
    vec3 T = normalize(cross(up, N));
    vec3 B = cross(N, T);
    return normalize(T * normalXY.x + B * normalXY.y + N * normalZ);
}

void main() {
    vec2 nativePixel = gl_FragCoord.xy;
#ifndef RCRA_NATIVE_UPPER_LEFT
    nativePixel.y = uViewportSize.y - nativePixel.y;
#endif
    float inversePrevious = 1.0 / max(vPreviousClip.w, uMotionNearPlane);
#ifdef GL_ARB_gpu_shader5
    precise vec2 currentUV = nativePixel / max(uViewportSize, vec2(1.0));
    precise vec2 currentCentered = currentUV - 0.5;
    precise vec2 previousHalf = vPreviousClip.xy * 0.5;
    precise vec2 opaqueMotion = fma(
        vec2(-1.0, 1.0) * previousHalf,
        vec2(inversePrevious), currentCentered
    );
    SceneVelocity = opaqueMotion * uViewportSize;
#else
    vec2 currentCentered = nativePixel / max(uViewportSize, vec2(1.0)) - 0.5;
    SceneVelocity = (
        currentCentered
        + vec2(-1.0, 1.0) * (vPreviousClip.xy * 0.5) * inversePrevious
    ) * uViewportSize;
#endif
    SceneStencil = 0u;
    if (uWireframe) {
        FragColor = vec4(0.2, 0.8, 1.0, 1.0);
        BrightColor = vec4(0.0);
        SceneLinearDepth = vec4(0.0, 0.0, 0.0, 1.0 / gl_FragCoord.w);
        return;
    }

    vec2 effectUV = length(vUV) > 0.0001 ? vUV : vWorldPos.xz * 0.08;
    vec3 n = normalize(vNormal);
    vec4 albedoSample = uHasTexture ? texture(uAlbedo, vUV) : vec4(1.0);
    vec4 furControl = uHasFurControl ? texture(uFurControlMap, vUV) : vec4(1.0);
    if (uAlphaCutout && uHasTexture && albedoSample.a < 0.45) {
        discard;
    }

    if (uHasNormal && !uIsRetailBlizarLava) {
        vec2 normalUV = uIsLava
            ? effectUV * 1.35 + vec2(uTime * 0.018, -uTime * 0.011)
            : vUV;
        n = perturb_normal(n, normalUV, uNormalMap);
    }

    // Two-sided lighting
    float NdL  = abs(dot(n, normalize(uLightDir)));
    float NdL2 = abs(dot(n, normalize(uFillDir)));
    float light = NdL * 0.8 + NdL2 * 0.3 + 0.35;

    vec3 col;
    vec3 dedicatedBloom = vec3(0.0);
    if (uIsRetailBlizarLava) {
        // Direct translation of the shipped blz_gbl_lava_01_flow GBuffer
        // permutation and its material-instance overrides.  The graph uses
        // world XZ projection, two phase-shifted flow samples, and the two
        // retained default CMA bindings; it does not sample a sibling _c map.
        const float shaderSpeed = 0.25;
        const float flowStrength = 0.20;
        const float textureTiling = 0.60;
        vec2 baseUV = vWorldPos.xz * 0.075;
        float noiseValue = texture(uRetailLavaNoise, baseUV).r;
        float timer = uTime * shaderSpeed;
        float phaseB = fract(noiseValue * 0.10 + timer);
        float phaseA = fract(noiseValue * 0.10 + timer + 0.50);

        // These shipped models have no vertex-colour stream.  The retail
        // vertex shader supplies white, which its sRGB decode converts to the
        // (-1,-1) flow vector with full strength.
        vec2 flowVector = vec2(-1.0);
        vec2 mappedUV = baseUV * textureTiling;
        vec2 uvA = mappedUV
            + flowVector * (phaseA * flowStrength)
            - vec2((timer - phaseA) * 0.10);
        vec2 uvB = mappedUV
            + flowVector * (phaseB * flowStrength)
            + vec2((timer - phaseB) * 0.10);

        float weightA = 1.0 - abs(1.0 - phaseA * 2.0);
        float weightB = 1.0 - abs(1.0 - phaseB * 2.0);
        // DXBC component swizzles resolve both scalar reads to the BC4 source
        // red channel.  Read it directly instead of depending on upload-time
        // replication into G/A.
        float maskA = texture(uRetailLavaMaskA, uvA).r;
        float maskB = texture(uRetailLavaMaskB, uvB).r;
        float maskMix = maskA * weightA + maskB * weightB;
        vec3 layerA = texture(uRetailLavaColorA, uvA).rgb * weightA;
        vec3 layerB = texture(uRetailLavaColorB, uvB).rgb * weightB;
        vec3 layeredColor = layerA + layerB;

        vec3 curveColor = pow(
            max(vec3(1.0 - maskMix), vec3(0.000001)),
            vec3(0.5, 6.0, 32.0)
        );
        float materialMask = 2.0 - maskMix;
        float blend = smoothstep(0.50, 1.25, materialMask);
        vec3 materialColor = mix(layeredColor, curveColor, blend);

        // The retail permutation writes materialColor beside a normalized,
        // logarithmically encoded emission scalar in its G-buffer output.
        // Reproduce that render-target saturation before forward lighting;
        // retaining out-of-range BC6H values in our RGBA16F target makes the
        // isolated waterfall clip to featureless white.
        materialColor = clamp(materialColor, vec3(0.0), vec3(1.0));

        vec2 normalA = texture(uRetailLavaNormalA, uvA).rg * 2.0 - 1.0;
        vec2 normalB = texture(uRetailLavaNormalB, uvB).rg * 2.0 - 1.0;
        vec2 blendedNormal = normalA * weightA + normalB * weightB;
        float normalLength = max(length(blendedNormal), 1.0);
        n = perturb_normal_xy(n, blendedNormal / normalLength);
        NdL = abs(dot(n, normalize(uLightDir)));
        NdL2 = abs(dot(n, normalize(uFillDir)));
        light = NdL * 0.8 + NdL2 * 0.3 + 0.35;

        float emissionStrength =
            (curveColor.r + curveColor.g) * clamp(materialMask, 0.0, 1.0);
        vec3 materialEmission = materialColor * emissionStrength;
        // Retail's deferred lighting pass decodes o1.w and adds the material's
        // emission to the lit surface.  This forward preview applies that once;
        // the separate bright buffer contributes only the blurred halo.
        col = materialColor * light + materialEmission * 0.55;
        dedicatedBloom = max(materialEmission - vec3(0.60), vec3(0.0));
    } else if (uIsLava) {
        vec2 flowA = effectUV * 1.10 + uLavaFlowA * uTime;
        vec2 flowB = effectUV * 2.35 + uLavaFlowB * uTime;
        vec2 warp = uHasNormal
            ? texture(uNormalMap, flowB * 0.72).rg * 2.0 - 1.0
            : vec2(sin(flowB.y * 5.0), cos(flowB.x * 4.0)) * 0.18;
        float noiseA = uHasNoise
            ? texture(uNoiseMap, flowB + warp * 0.12).r
            : 0.5 + 0.5 * sin(flowB.x * 5.1 + sin(flowB.y * 3.7));
        float breakup = uHasEffectMask
            ? texture(uEffectMaskMap, flowA + warp * 0.09).r
            : 0.5 + 0.5 * sin(flowA.x * 7.0 - flowA.y * 4.0);
        float hdrPattern = uHasEmissive
            ? dot(texture(uEmissiveMap, flowA + warp * 0.08).rgb,
                  vec3(0.299, 0.587, 0.114))
            : noiseA;
        float movingBand = uIsLavaFall
            ? 0.5 + 0.5 * sin(
                effectUV.y * 18.0 + noiseA * 5.0 - uTime * 1.15
              )
            : 0.5 + 0.5 * sin(
                (effectUV.x + effectUV.y * 0.63) * 18.0
                + noiseA * 5.0 + uTime * 1.15
              );
        float worldBreak = uIsLavaFall
            ? 0.5 + 0.5 * sin(
                effectUV.y * 8.0 + noiseA * 2.0 - uTime * 0.65
              )
            : 0.5 + 0.5 * sin(
                vWorldPos.x * 0.31
                + sin(vWorldPos.z * 0.27 + uTime * 0.7) * 2.2
              );
        float heat = smoothstep(
            0.30, 0.76,
            noiseA * 0.25 + breakup * 0.30 + hdrPattern * 0.22
            + movingBand * 0.20 + worldBreak * 0.20
        );
        float hotCore = smoothstep(0.70, 0.98, heat + hdrPattern * 0.22);
        vec3 crust = mix(vec3(0.012, 0.009, 0.008), vec3(0.13, 0.025, 0.006), breakup);
        vec3 molten = mix(vec3(1.10, 0.075, 0.006), vec3(1.65, 0.72, 0.075), heat);
        molten = mix(molten, vec3(2.5, 1.55, 0.42), hotCore);
        col = mix(crust * (0.45 + light * 0.30), molten, heat);
        col += molten * heat * (1.35 + hotCore * 1.8);
    } else if (uHasTexture) {
        col = albedoSample.rgb * light;
    } else {
        col = uBaseColor * light;
    }
    if (uIsFur && uHasFurControl) {
        // Soft fiber scattering keeps the surviving cards readable without
        // turning them emissive or feeding them into bloom.
        float fiber = smoothstep(0.05, 0.85, furControl.g);
        float grazing = pow(1.0 - abs(dot(n, normalize(uLightDir))), 3.0);
        col += albedoSample.rgb * grazing * mix(0.04, 0.16, fiber);
    }
    if (!uIsLava && !uIsRetailBlizarLava && uHasEmissive) {
        vec3 emission = texture(uEmissiveMap, vUV).rgb;
        float mask = uHasEffectMask ? texture(uEffectMaskMap, vUV).r : 1.0;
        if (uIsLavaRock) {
            // The lava-rock FX input is red across most of the texture and its
            // CMA map is surface detail, not a literal binary glow mask.  Use
            // their high-value features to isolate hot fissures while keeping
            // the recovered volcanic-stone albedo visible.
            float heat = max(emission.r, max(emission.g, emission.b));
            float fissure = smoothstep(0.42, 0.82, heat);
            float surfaceDetail = smoothstep(0.32, 0.78, mask);
            float glow = fissure * mix(0.28, 0.82, surfaceDetail);
            vec3 hotColor = mix(
                vec3(0.72, 0.025, 0.002),
                vec3(1.45, 0.34, 0.025),
                smoothstep(0.68, 0.98, heat)
            );
            vec3 rockEmission = hotColor * glow;
            col += rockEmission;
            dedicatedBloom = rockEmission * 1.15;
        } else {
            col += emission * mask * 2.4;
        }
    }
    FragColor = vec4(col, 1.0);
    float luminance = dot(max(col, vec3(0.0)), vec3(0.2126, 0.7152, 0.0722));
    if (uIsRetailBlizarLava) {
        float emissiveLuminance = dot(
            dedicatedBloom, vec3(0.2126, 0.7152, 0.0722)
        );
        float bloomWeight = smoothstep(0.18, 0.85, emissiveLuminance);
        BrightColor = vec4(dedicatedBloom * bloomWeight, 1.0);
    } else if (uIsLavaRock) {
        float emissiveLuminance = dot(
            dedicatedBloom, vec3(0.2126, 0.7152, 0.0722)
        );
        float bloomWeight = smoothstep(0.07, 0.42, emissiveLuminance);
        BrightColor = vec4(dedicatedBloom * bloomWeight, 1.0);
    } else {
        float bloomWeight = smoothstep(0.82, 1.45, luminance);
        BrightColor = vec4(col * bloomWeight, 1.0);
    }
    SceneLinearDepth = vec4(0.0, 0.0, 0.0, 1.0 / gl_FragCoord.w);
}
"""


# Rejected geometric-ribbon experiment retained here only as a comparison
# shader. The active viewport compiles FUR_SHELL_* below. Recovered semantics
# establish that control B participates in the retail depth output; this legacy
# shader does not implement that G-buffer channel.
FUR_VERT_SRC = """
#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNormal;
layout(location=2) in vec2 aUV;
layout(location=3) in vec4 aTangent;

out FurVertex {
    vec3 position;
    vec3 normal;
    vec2 uv;
} furVertex;

void main() {
    furVertex.position = aPos;
    furVertex.normal = aNormal;
    furVertex.uv = aUV;
    gl_Position = vec4(aPos, 1.0);
}
"""

FUR_GEOM_SRC = """
#version 330 core
layout(triangles) in;
layout(triangle_strip, max_vertices=48) out;

in FurVertex {
    vec3 position;
    vec3 normal;
    vec2 uv;
} furVertex[];

uniform mat4 uMVP;
uniform mat4 uModel;
uniform mat3 uNormal;
uniform vec3 uEye;
uniform vec3 uLightDir;
uniform vec3 uFillDir;
uniform sampler2D uFurAlbedo;
uniform sampler2D uFurControl;
uniform float uFurLength;
uniform float uFurDensity;
uniform float uFurOffsetScale;
uniform vec2 uViewportSize;

out vec3 gColor;
out float gAlong;
out float gAcross;
out float gLighting;
out vec3 gTangent;
out vec3 gViewDirection;
out float gEnvelopeLength;
out vec2 gLightScreenDirection;

float hash31(vec3 value) {
    return fract(sin(dot(value, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
}

vec3 bary3(vec3 a, vec3 b, vec3 c, vec3 weights) {
    return a * weights.x + b * weights.y + c * weights.z;
}

vec2 bary2(vec2 a, vec2 b, vec2 c, vec3 weights) {
    return a * weights.x + b * weights.y + c * weights.z;
}

vec3 uniformTriangleWeights(vec3 triangleCenter, float seed) {
    float u = hash31(triangleCenter * 127.0 + vec3(seed, 0.31, 0.73));
    float v = hash31(triangleCenter * 193.0 + vec3(0.59, seed, 1.17));
    float rootU = sqrt(u);
    return vec3(1.0 - rootU, rootU * (1.0 - v), rootU * v);
}

void emitFiber(vec3 weights, float seed, vec3 tangent, vec3 bitangent) {
    vec3 localRoot = bary3(
        furVertex[0].position, furVertex[1].position, furVertex[2].position,
        weights
    );
    vec3 root = (uModel * vec4(localRoot, 1.0)).xyz;
    vec3 normal = normalize(uNormal * bary3(
        furVertex[0].normal, furVertex[1].normal, furVertex[2].normal,
        weights
    ));
    vec2 uv = bary2(furVertex[0].uv, furVertex[1].uv, furVertex[2].uv, weights);
    vec4 control = textureLod(uFurControl, uv, 0.0);
    // The live shipped vertex shader samples control blue for extrusion.
    if (control.b <= (1.0 / 255.0)) {
        return;
    }

    // The retail fur pixel shader always decodes control RG as comb direction.
    vec2 flow = control.rg * 2.0 - 1.0;
    float randomValue = hash31(root * 173.0 + vec3(seed));
    // The measured particle-volume slice mean falls approximately linearly
    // from root to tip, so its survival function corresponds to a uniform
    // distribution of fiber endpoints inside the authored maximum envelope.
    float strandLength = uFurLength * control.b * randomValue;
    float rootWidth = 0.00050;
    vec3 baseColor = textureLod(uFurAlbedo, uv, 0.0).rgb;
    float primary = abs(dot(normal, normalize(uLightDir)));
    float fill = abs(dot(normal, normalize(uFillDir)));
    float lighting = primary * 0.68 + fill * 0.32 + 0.38;

    vec2 comb = flow * uFurOffsetScale;
    float combLengthSquared = min(dot(comb, comb), 0.99);
    float combNormal = sqrt(1.0 - combLengthSquared);
    // Match the recovered shader's tangent-space reconstruction instead of
    // adding an arbitrary comb vector to the geometric normal.
    vec3 direction = normalize(
        tangent * comb.x + bitangent * comb.y + normal * combNormal
    );
    for (int segment = 0; segment <= 3; ++segment) {
        float along = float(segment) / 3.0;
        vec3 center = root + normal * 0.00020
            + direction * strandLength * along;
        vec3 viewDirection = normalize(uEye - center);
        vec3 side = cross(direction, viewDirection);
        if (dot(side, side) < 0.00001) {
            side = cross(direction, tangent);
        }
        side = normalize(side);
        float widthTaper = pow(1.0 - along, 1.35);
        float halfWidth = rootWidth * widthTaper;
        vec4 centerClip = uMVP * vec4(center, 1.0);
        vec4 sideClip = uMVP * vec4(center + side * halfWidth, 1.0);
        vec2 centerNdc = centerClip.xy / centerClip.w;
        vec2 sideNdc = sideClip.xy / sideClip.w;
        vec2 pixelOffset = (sideNdc - centerNdc) * uViewportSize * 0.5;
        float pixelHalfWidth = length(pixelOffset);
        vec2 pixelDirection = pixelHalfWidth > 0.0001
            ? pixelOffset / pixelHalfWidth : vec2(1.0, 0.0);
        // Preserve the authored world-space width up close, but prevent the
        // ribbon from collapsing into unstable sub-pixel stipple at distance.
        float pixelWidthFloor = 0.65 * pow(1.0 - along, 0.70);
        pixelHalfWidth = max(pixelHalfWidth, pixelWidthFloor);
        vec2 clipOffset = pixelDirection * pixelHalfWidth
            * (2.0 / uViewportSize) * centerClip.w;
        gColor = baseColor;
        gAlong = along;
        gLighting = lighting;
        gTangent = direction;
        gViewDirection = viewDirection;
        gEnvelopeLength = control.b;
        vec4 lightClip = uMVP * vec4(
            center + normalize(uLightDir) * max(uFurLength, 0.01), 1.0
        );
        vec2 lightPixelOffset = (
            lightClip.xy / lightClip.w - centerNdc
        ) * uViewportSize * 0.5;
        gLightScreenDirection = dot(lightPixelOffset, lightPixelOffset) > 0.0001
            ? normalize(lightPixelOffset) : vec2(0.0, 1.0);
        gAcross = -1.0;
        gl_Position = centerClip;
        gl_Position.xy -= clipOffset;
        EmitVertex();
        gAcross = 1.0;
        gl_Position = centerClip;
        gl_Position.xy += clipOffset;
        EmitVertex();
    }
    EndPrimitive();
}

void main() {
    vec3 world0 = (uModel * vec4(furVertex[0].position, 1.0)).xyz;
    vec3 world1 = (uModel * vec4(furVertex[1].position, 1.0)).xyz;
    vec3 world2 = (uModel * vec4(furVertex[2].position, 1.0)).xyz;
    vec2 edgeUV1 = furVertex[1].uv - furVertex[0].uv;
    vec2 edgeUV2 = furVertex[2].uv - furVertex[0].uv;
    vec3 averageNormal = normalize(uNormal * (
        furVertex[0].normal + furVertex[1].normal + furVertex[2].normal
    ));
    float determinant = edgeUV1.x * edgeUV2.y - edgeUV1.y * edgeUV2.x;
    vec3 tangent;
    if (abs(determinant) > 0.000001) {
        tangent = normalize(
            ((world1 - world0) * edgeUV2.y - (world2 - world0) * edgeUV1.y)
            / determinant
        );
    } else {
        vec3 axis = abs(averageNormal.y) < 0.95 ? vec3(0.0, 1.0, 0.0)
                                                 : vec3(1.0, 0.0, 0.0);
        tangent = normalize(cross(axis, averageNormal));
    }
    tangent = normalize(tangent - averageNormal * dot(tangent, averageNormal));
    vec3 bitangent = normalize(cross(averageNormal, tangent));
    float worldArea = length(cross(world1 - world0, world2 - world0)) * 0.5;
    float rootBudget = clamp(worldArea * uFurDensity * 10000.0, 0.0, 6.0);
    vec3 triangleCenter = (world0 + world1 + world2) / 3.0;
    vec4 rootClip = uMVP * vec4(triangleCenter, 1.0);
    vec4 envelopeClip = uMVP * vec4(
        triangleCenter + averageNormal * uFurLength, 1.0
    );
    float projectedLengthPixels = length(
        (envelopeClip.xy / envelopeClip.w - rootClip.xy / rootClip.w)
        * uViewportSize * 0.5
    );
    // Deterministic thresholds below make roots disappear in a stable order
    // as the authored envelope becomes sub-pixel, with a conservative floor
    // so distant silhouettes never lose the fur pass completely.
    float rootLod = mix(
        0.25, 1.0, smoothstep(1.0, 6.0, projectedLengthPixels)
    );
    rootBudget *= rootLod;
    if (rootBudget > hash31(triangleCenter * 71.0 + vec3(0.17))) {
        emitFiber(uniformTriangleWeights(triangleCenter, 0.17), 0.17, tangent, bitangent);
    }
    if (rootBudget > 1.0 + hash31(triangleCenter * 83.0 + vec3(0.53))) {
        emitFiber(uniformTriangleWeights(triangleCenter, 0.53), 0.53, tangent, bitangent);
    }
    if (rootBudget > 2.0 + hash31(triangleCenter * 97.0 + vec3(0.89))) {
        emitFiber(uniformTriangleWeights(triangleCenter, 0.89), 0.89, tangent, bitangent);
    }
    if (rootBudget > 3.0 + hash31(triangleCenter * 101.0 + vec3(1.31))) {
        emitFiber(uniformTriangleWeights(triangleCenter, 1.31), 1.31, tangent, bitangent);
    }
    if (rootBudget > 4.0 + hash31(triangleCenter * 107.0 + vec3(1.73))) {
        emitFiber(uniformTriangleWeights(triangleCenter, 1.73), 1.73, tangent, bitangent);
    }
    if (rootBudget > 5.0 + hash31(triangleCenter * 109.0 + vec3(2.11))) {
        emitFiber(uniformTriangleWeights(triangleCenter, 2.11), 2.11, tangent, bitangent);
    }
}
"""

FUR_FRAG_SRC = """
#version 330 core
in vec3 gColor;
in float gAlong;
in float gAcross;
in float gLighting;
in vec3 gTangent;
in vec3 gViewDirection;
in float gEnvelopeLength;
in vec2 gLightScreenDirection;
uniform bool uWeightedOIT;
uniform bool uScreenSpaceShadow;
uniform sampler2D uSceneDepth;
uniform vec2 uViewportSize;
uniform vec3 uLightDir;

layout(location = 0) out vec4 FurColor;
layout(location = 1) out vec4 FurReveal;

void main() {
    float rootFade = smoothstep(0.0, 0.12, gAlong);
    float tipFade = 1.0 - smoothstep(0.68, 1.0, gAlong);
    float acrossDerivative = max(fwidth(gAcross), 0.0001);
    float edgeCoverage = clamp(
        (1.0 - abs(gAcross)) / acrossDerivative, 0.0, 1.0
    );
    float alpha = mix(0.72, 0.92, rootFade) * tipFade * edgeCoverage;
    if (alpha < 0.025) {
        discard;
    }
    vec3 tangent = normalize(gTangent);
    vec3 viewDirection = normalize(gViewDirection);
    vec3 lightDirection = normalize(uLightDir);
    vec3 halfDirection = normalize(viewDirection + lightDirection);
    // Hair reflects in a lobe around the strand tangent rather than around a
    // polygon normal. This compact Kajiya-Kay-style term gives the ribbons a
    // strand response while the retail lobe parameters remain unknown.
    float tangentDotHalf = clamp(dot(tangent, halfDirection), -1.0, 1.0);
    float anisotropic = pow(max(0.0, 1.0 - tangentDotHalf * tangentDotHalf), 24.0);
    float rim = pow(1.0 - max(dot(viewDirection, lightDirection), 0.0), 4.0);
    vec3 color = gColor * gLighting;
    color += mix(vec3(0.12), gColor, 0.30) * anisotropic * 0.32;
    color += gColor * rim * 0.08;
    // Control blue is the shipped vertex shader's shell-extrusion multiplier.
    // Use that same envelope scale for the restrained base contact term.
    float contactFalloff = 1.0 - smoothstep(0.04, 0.52, gAlong);
    float contactStrength = mix(0.10, 0.28, clamp(gEnvelopeLength, 0.0, 1.0));
    color *= 1.0 - contactStrength * contactFalloff;
    if (uScreenSpaceShadow) {
        vec2 screenUV = gl_FragCoord.xy / uViewportSize;
        vec2 texelStep = normalize(gLightScreenDirection) / uViewportSize;
        float depthBias = max(fwidth(gl_FragCoord.z) * 2.0, 0.00002);
        float occlusion = 0.0;
        float sampleDepth = texture(uSceneDepth, screenUV + texelStep * 1.5).r;
#ifdef RCRA_NATIVE_UPPER_LEFT
        occlusion += sampleDepth > 0.0001
            && sampleDepth - depthBias > gl_FragCoord.z ? 0.50 : 0.0;
        sampleDepth = texture(uSceneDepth, screenUV + texelStep * 3.0).r;
        occlusion += sampleDepth > 0.0001
            && sampleDepth - depthBias > gl_FragCoord.z ? 0.30 : 0.0;
        sampleDepth = texture(uSceneDepth, screenUV + texelStep * 5.0).r;
        occlusion += sampleDepth > 0.0001
            && sampleDepth - depthBias > gl_FragCoord.z ? 0.20 : 0.0;
#else
        occlusion += sampleDepth < 0.9999
            && sampleDepth + depthBias < gl_FragCoord.z ? 0.50 : 0.0;
        sampleDepth = texture(uSceneDepth, screenUV + texelStep * 3.0).r;
        occlusion += sampleDepth < 0.9999
            && sampleDepth + depthBias < gl_FragCoord.z ? 0.30 : 0.0;
        sampleDepth = texture(uSceneDepth, screenUV + texelStep * 5.0).r;
        occlusion += sampleDepth < 0.9999
            && sampleDepth + depthBias < gl_FragCoord.z ? 0.20 : 0.0;
#endif
        float strandContact = 1.0 - smoothstep(0.12, 0.82, gAlong);
        color *= 1.0 - occlusion * strandContact * 0.18;
    }
    if (uWeightedOIT) {
#ifdef RCRA_NATIVE_UPPER_LEFT
        float depthWeight = pow(0.1 + gl_FragCoord.z * 0.90, 3.0);
#else
        float depthWeight = pow(1.0 - gl_FragCoord.z * 0.90, 3.0);
#endif
        float weight = clamp(alpha * 8.0 * depthWeight, 0.01, 3.0);
        FurColor = vec4(color * alpha, alpha) * weight;
        FurReveal = vec4(alpha);
    } else {
        FurColor = vec4(color, alpha);
        FurReveal = vec4(0.0);
    }
}
"""

GRID_VERT = """
#version 330 core
layout(location=0) in vec3 aPos;

uniform mat4 uInvVP;

out vec3 vNear;
out vec3 vFar;

vec3 unproject(float x, float y, float z, mat4 invVP) {
    vec4 v = invVP * vec4(x, y, z, 1.0);
    return v.xyz / v.w;
}

void main() {
    gl_Position = vec4(aPos, 1.0);
#ifdef RCRA_NATIVE_UPPER_LEFT
    vNear = unproject(aPos.x, aPos.y, 1.0, uInvVP);
    vFar  = unproject(aPos.x, aPos.y, 0.0, uInvVP);
#else
    vNear = unproject(aPos.x, aPos.y, -1.0, uInvVP);
    vFar  = unproject(aPos.x, aPos.y,  1.0, uInvVP);
#endif
}
"""

GRID_FRAG = """
#version 330 core
in vec3 vNear;
in vec3 vFar;

uniform float uGridY;
uniform bool  uOrtho;
uniform vec3  uEye;       // camera world-space eye position

layout(location = 0) out vec4 FragColor;
layout(location = 1) out vec4 BrightColor;

float gridLine(vec2 uv, float scale) {
    vec2 g = abs(fract(uv / scale - 0.5) - 0.5) / fwidth(uv / scale);
    return min(g.x, g.y);
}

void main() {
    vec3 rayOrigin, rayDir;

    if (uOrtho) {
        // In ortho all rays are parallel. The direction is the same for every
        // fragment: from near to far (both already in world space).
        // The origin per-fragment is vNear — it lies on the near plane in
        // world space at the correct XZ for this screen pixel.
        rayDir    = normalize(vFar - vNear);
        rayOrigin = vNear;
    } else {
        // Perspective: rays diverge from the eye point.
        rayOrigin = uEye;
        rayDir    = normalize(vFar - uEye);
    }

    float dY = rayDir.y;
    if (abs(dY) < 1e-5) discard;

    float t = (uGridY - rayOrigin.y) / dY;
    if (t < 0.0) discard;

    vec3  pos     = rayOrigin + t * rayDir;
    float dist    = length(pos.xz - uEye.xz);

    float g1   = gridLine(pos.xz, 1.0);
    float g2   = gridLine(pos.xz, 0.1);
    float line = min(g1, g2);

    float fadeRange = uOrtho ? 200.0 : 80.0;
    float alpha = (1.0 - min(line, 1.0)) * (1.0 - smoothstep(0.0, fadeRange, dist));
    if (alpha < 0.01) discard;

    vec3 col = (g2 > g1) ? vec3(0.20, 0.23, 0.29) : vec3(0.10, 0.12, 0.16);
    FragColor = vec4(col, alpha * 0.68);
    BrightColor = vec4(0.0);
}
"""

# Instanced shell reconstruction. Geometry, varyings, control-channel semantics,
# view-dependent shell culling, and stochastic coverage follow the installed
# ModelFur/MaterialFur DXBC. The layer-volume texels and mip chain are
# reconstructed from the installed executable's TextureDefaultsInit routine.
FUR_SHELL_VERT_SRC = """
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aUV;
layout(location = 3) in vec4 aTangent;
layout(location = 4) in float aDecodeCorrection;
layout(location = 5) in vec3 aPreviousPos;

uniform mat4 uMVP;
uniform mat4 uPreviousMVP;
uniform mat4 uModel;
uniform mat3 uNormal;
uniform sampler2D uFurControl;
uniform float uFurLength;
uniform float uFurOffsetScale;
uniform float uFurWindStrength;
uniform vec3 uFurWindVector;
uniform float uFurWindTime;
uniform float uPreviousFurWindTime;
uniform float uFurWindObjectPhase;
uniform float uFurWindRadius;
uniform float uFurWindTurbulence;
uniform int uLayerCount;
uniform int uReverseLayer;
uniform vec3 uEye;

out vec2 vsUV;
out vec3 vsWorldPosition;
out vec3 vsWorldNormal;
out float vsLayerDepth;
out float vsLayerSlice;
out float vsCurvedOffset;
flat out int vsBaseShell;
flat out int vsShellVisible;
out vec4 vsWorldTangent;
out vec4 vsPreviousClip;

// Exact g_RandomVecs.v table embedded by the captured retail wind VS.
const vec4 RETAIL_WIND_RANDOM[64] = vec4[64](
    vec4(0.840796, 0.813891, 0.312036, 0.409705),
    vec4(0.892850, 0.503802, 0.809281, 0.377742),
    vec4(0.311328, 0.108150, 0.746691, 0.444973),
    vec4(0.306975, 0.958722, 0.451885, 0.082242),
    vec4(0.399972, 0.081290, 0.245685, 0.433091),
    vec4(0.091177, 0.787678, 0.489735, 0.575681),
    vec4(0.429327, 0.479088, 0.994538, 0.673963),
    vec4(0.423418, 0.977108, 0.628466, 0.842047),
    vec4(0.191882, 0.228921, 0.785621, 0.256387),
    vec4(0.879887, 0.622279, 0.801219, 0.172460),
    vec4(0.840796, 0.813891, 0.312036, 0.776001),
    vec4(0.602731, 0.012805, 0.545680, 0.576612),
    vec4(0.258923, 0.129449, 0.733609, 0.776765),
    vec4(0.308455, 0.294581, 0.913658, 0.844449),
    vec4(0.375183, 0.978853, 0.428443, 0.131553),
    vec4(0.414992, 0.015655, 0.590460, 0.330335),
    vec4(0.995044, 0.506598, 0.569916, 0.261539),
    vec4(0.526623, 0.186814, 0.888852, 0.953245),
    vec4(0.429767, 0.974934, 0.639661, 0.743165),
    vec4(0.669612, 0.764758, 0.111239, 0.424083),
    vec4(0.435360, 0.183351, 0.118483, 0.560506),
    vec4(0.196027, 0.505871, 0.896946, 0.270710),
    vec4(0.182654, 0.489446, 0.113762, 0.984206),
    vec4(0.489892, 0.974144, 0.658383, 0.071101),
    vec4(0.975564, 0.380410, 0.597662, 0.466624),
    vec4(0.044131, 0.318927, 0.403063, 0.344429),
    vec4(0.025007, 0.491437, 0.344088, 0.018572),
    vec4(0.832404, 0.177144, 0.687808, 0.543193),
    vec4(0.908834, 0.254218, 0.350178, 0.350695),
    vec4(0.300320, 0.904002, 0.716587, 0.397697),
    vec4(0.242521, 0.411378, 0.080654, 0.406470),
    vec4(0.924259, 0.488238, 0.764322, 0.586954),
    vec4(0.342563, 0.971971, 0.549566, 0.963398),
    vec4(0.315562, 0.963127, 0.461316, 0.909517),
    vec4(0.191886, 0.889296, 0.440722, 0.951838),
    vec4(0.469036, 0.029332, 0.665869, 0.444422),
    vec4(0.741022, 0.652844, 0.910545, 0.553683),
    vec4(0.266224, 0.790136, 0.833421, 0.834226),
    vec4(0.908181, 0.284288, 0.691980, 0.483448),
    vec4(0.417763, 0.790482, 0.101431, 0.153960),
    vec4(0.150757, 0.629250, 0.166348, 0.359245),
    vec4(0.039506, 0.353832, 0.371235, 0.939238),
    vec4(0.097391, 0.254725, 0.666572, 0.570285),
    vec4(0.773237, 0.323679, 0.120194, 0.974246),
    vec4(0.285994, 0.857065, 0.223042, 0.100589),
    vec4(0.272433, 0.072084, 0.377112, 0.402916),
    vec4(0.533814, 0.314517, 0.963091, 0.028274),
    vec4(0.153012, 0.361124, 0.167866, 0.748453),
    vec4(0.983539, 0.469407, 0.623505, 0.656017),
    vec4(0.477317, 0.528396, 0.001323, 0.923924),
    vec4(0.066620, 0.506131, 0.749287, 0.050451),
    vec4(0.848485, 0.249520, 0.243450, 0.405907),
    vec4(0.036950, 0.685308, 0.464709, 0.272810),
    vec4(0.380287, 0.014672, 0.511236, 0.595491),
    vec4(0.668458, 0.053124, 0.351933, 0.780319),
    vec4(0.672278, 0.031136, 0.522069, 0.921864),
    vec4(0.842112, 0.351749, 0.833138, 0.100663),
    vec4(0.233485, 0.077054, 0.490699, 0.067748),
    vec4(0.641836, 0.961169, 0.368828, 0.755992),
    vec4(0.582643, 0.627093, 0.023537, 0.813861),
    vec4(0.660399, 0.630621, 0.044796, 0.882384),
    vec4(0.840796, 0.813891, 0.312036, 0.409705),
    vec4(0.892850, 0.503802, 0.809281, 0.377742),
    vec4(0.311328, 0.108150, 0.746691, 0.444973)
);

vec3 retailWindOffset(vec2 uv, vec3 localWind, float windTime) {
    float lowFrequency = uFurWindTurbulence * 20.0 + 10.0;
    float highFrequency = uFurWindTurbulence * 100.0 + 50.0;
    float spatial = sin(lowFrequency * uv.x) + sin(lowFrequency * uv.y)
        + 0.5 * (sin(highFrequency * uv.x) + sin(highFrequency * uv.y));
    float envelope = uFurWindObjectPhase * 0.9 + 0.05 + spatial * 0.05;
    float denominator = 1.925 - envelope * 0.875;
    float ramp = denominator <= 0.0 ? 0.0 : clamp(
        (0.6625 - envelope * 0.4375) / denominator, 0.0, 1.0
    );
    float smoothRamp = ramp * ramp * (3.0 - 2.0 * ramp);
    float wave = (
        (1.0 - smoothRamp) * envelope + smoothRamp + 1.0
    ) * sin((envelope + fract(windTime * 0.15915493667125702))
            * 6.2831854820251465) - 1.0;
    float directionalCap = min(
        smoothRamp * (envelope * 0.0125 + 0.0375),
        uFurWindRadius * 0.1
    );

    float speed = uFurWindTurbulence * 10.0 + 5.0;
    float noiseTime = (windTime + 0.125 + spatial * 0.125) * speed;
    float f = fract(noiseTime);
    float f2 = f * f;
    float f3 = f2 * f;
    vec4 weights = vec4(
        -f + 2.0 * f2 - f3,
        1.0 - 2.0 * f2 + f3,
        f + f2 - f3,
        -f2 + f3
    );
    int tableIndex = int(fract(noiseTime * 0.016393441706895828) * 61.0);
    vec3 randomVector = RETAIL_WIND_RANDOM[tableIndex].xyz * weights.x
        + RETAIL_WIND_RANDOM[tableIndex + 1].xyz * weights.y
        + RETAIL_WIND_RANDOM[tableIndex + 2].xyz * weights.z
        + RETAIL_WIND_RANDOM[tableIndex + 3].xyz * weights.w;
    vec3 baseWind = vec3(wave, -1.0, wave) * uFurWindStrength
        + localWind * directionalCap;
    return (randomVector * uFurWindStrength + baseWind) * (1.0 / 30.0);
}

float pointWrappedControlLength(vec2 uv) {
    ivec2 dimensions = textureSize(uFurControl, 0);
    ivec2 texel = ivec2(floor(fract(uv) * vec2(dimensions)));
    texel = clamp(texel, ivec2(0), dimensions - ivec2(1));
    // Live VS_ModelFurShellGBufferDeferredWind event 32398 extracts component
    // 2 here. Blue is the authored strand-length/groom envelope; alpha is a
    // separate tangent-shift control consumed by the fur GBuffer pixel shader.
    return texelFetch(uFurControl, texel, 0).b;
}

void main() {
    int reverseLayer = uReverseLayer;
    float rawDepth = float(reverseLayer) / float(max(uLayerCount, 1));
    vec3 localNormal = normalize(aNormal);
    vec3 localTangent = normalize(aTangent.xyz);
    vec3 worldNormal = normalize(uNormal * localNormal);
    vec3 worldTangent = normalize(uNormal * localTangent);
    vec3 basePosition = (uModel * vec4(aPos, 1.0)).xyz;
    vec3 viewDirection = normalize(uEye - basePosition);
    float front = clamp(
        dot(viewDirection, worldNormal)
            - aDecodeCorrection * 0.0065 - 0.025,
        0.0, 1.0
    );
    float available = min(
        2.0 * (1.0 - front) * (1.0 - front) + 0.1, 1.0
    );
    float unboundedDepth = rawDepth / available;
    float layerDepth = clamp(unboundedDepth, 0.0, 1.0);
    float controlLength = pointWrappedControlLength(aUV);
    vec3 shellLocalNormal = localNormal;
    vec3 previousShellLocalNormal = localNormal;
    if (uFurWindStrength > 0.0 && uFurLength > 0.0) {
        vec3 localWind = inverse(mat3(uModel)) * uFurWindVector;
        vec3 windOffset = retailWindOffset(aUV, localWind, uFurWindTime);
        vec3 previousWindOffset = retailWindOffset(
            aUV, localWind, uPreviousFurWindTime
        );
        // The retail shader projects the procedural displacement onto its
        // tangent/bitangent plane before curving the shell frame.
        vec3 localBitangent = normalize(cross(localTangent, localNormal))
            * aTangent.w;
        vec3 frameOffset = localTangent * dot(localTangent, windOffset)
            + localBitangent * dot(localBitangent, windOffset);
        float windGate = clamp(
            (controlLength * uFurLength - 0.0075) * 50.0, 0.0, 1.0
        );
        float bendCurve = layerDepth * layerDepth + 0.4 * layerDepth;
        vec3 bend = frameOffset * windGate * bendCurve
            / max(uFurLength, 0.000001);
        vec3 previousFrameOffset = localTangent
            * dot(localTangent, previousWindOffset)
            + localBitangent * dot(localBitangent, previousWindOffset);
        vec3 previousBend = previousFrameOffset * windGate * bendCurve
            / max(uFurLength, 0.000001);
        shellLocalNormal = normalize(localNormal + bend);
        previousShellLocalNormal = normalize(localNormal + previousBend);
        // The captured VS preserves the bent tangent's magnitude. Normalize
        // after raster interpolation in the material pass.
        worldTangent = uNormal * (localTangent + bend);
    }
    vec3 localPosition = aPos + shellLocalNormal
        * (uFurLength * controlLength * layerDepth);
    vec3 previousLocalPosition = aPreviousPos + previousShellLocalNormal
        * (uFurLength * controlLength * layerDepth);
    vec3 worldPosition = (uModel * vec4(localPosition, 1.0)).xyz;
    vsUV = aUV;
    vsWorldPosition = worldPosition;
    vsWorldNormal = worldNormal;
    vsLayerDepth = layerDepth;
    vsLayerSlice = layerDepth * 32.0;
    vsCurvedOffset = (layerDepth * layerDepth + 0.4 * layerDepth)
        * uFurLength * uFurOffsetScale;
    vsBaseShell = reverseLayer == 0 ? 1 : 0;
    vsShellVisible = unboundedDepth <= 1.0 ? 1 : 0;
    vsWorldTangent = vec4(worldTangent, aTangent.w * uFurOffsetScale);
    vsPreviousClip = uPreviousMVP * vec4(previousLocalPosition, 1.0);
    gl_Position = uMVP * vec4(localPosition, 1.0);
}
"""

# D3D's recovered vertex shader rejects a shell triangle when any vertex writes
# its +INF clip sentinel.  Passing +INF to OpenGL is undefined and produced
# stretched radial primitives on some drivers, so aggregate the same per-vertex
# decision explicitly before rasterization.
FUR_SHELL_GEOM_SRC = """
#version 330 core
layout(triangles) in;
layout(triangle_strip, max_vertices = 3) out;

in vec2 vsUV[];
in vec3 vsWorldPosition[];
in vec3 vsWorldNormal[];
in float vsLayerDepth[];
in float vsLayerSlice[];
in float vsCurvedOffset[];
flat in int vsBaseShell[];
flat in int vsShellVisible[];
in vec4 vsWorldTangent[];
in vec4 vsPreviousClip[];

out vec2 vUV;
out vec3 vWorldPosition;
out vec3 vWorldNormal;
out float vLayerDepth;
out float vLayerSlice;
out float vCurvedOffset;
flat out int vBaseShell;
out vec4 vWorldTangent;
out vec4 vPreviousClip;

void main() {
    if (vsShellVisible[0] == 0
            || vsShellVisible[1] == 0
            || vsShellVisible[2] == 0) {
        return;
    }
    for (int index = 0; index < 3; ++index) {
        vUV = vsUV[index];
        vWorldPosition = vsWorldPosition[index];
        vWorldNormal = vsWorldNormal[index];
        vLayerDepth = vsLayerDepth[index];
        vLayerSlice = vsLayerSlice[index];
        vCurvedOffset = vsCurvedOffset[index];
        vBaseShell = vsBaseShell[index];
        vWorldTangent = vsWorldTangent[index];
        vPreviousClip = vsPreviousClip[index];
        gl_Position = gl_in[index].gl_Position;
        EmitVertex();
    }
    EndPrimitive();
}
"""

FUR_SHELL_MATERIAL_COMMON = """
#version 330 core
#extension GL_ARB_gpu_shader5 : enable
in vec2 vUV;
in vec3 vWorldPosition;
in vec3 vWorldNormal;
in float vLayerDepth;
in float vLayerSlice;
in float vCurvedOffset;
flat in int vBaseShell;
in vec4 vWorldTangent;
in vec4 vPreviousClip;

uniform sampler2D uFurAlbedo;
uniform sampler2D uFurControl;
uniform sampler2D uFurSpecular;
uniform sampler2DArray uFurLayers;
uniform samplerCube uFurEnvironment;
uniform sampler2D uFurBrdfLut;
uniform float uFurDensity;
uniform float uFurOffsetScale;
uniform float uFurGlossScale;
uniform float uFurSpecularScale;
uniform float uFurTransmittanceScale;
uniform float uFurWetness;
uniform uint uFurRenderFlags;
uniform bool uHasFurSpecular;
uniform bool uHasFurEnvironment;
uniform vec3 uEye;
uniform vec3 uLightDir;
uniform vec3 uFillDir;
uniform float uTemporalIndex;
uniform float uTemporalPlusCycle;
uniform vec2 uViewportSize;
uniform float uMotionNearPlane;

uniform float uFurLength;

/* HAIR_LIGHTING_NOISE */
/* FUR_MATERIAL */
/* FUR_GBUFFER */


vec2 furNativePixel(vec2 fragmentPixel) {
#ifdef RCRA_NATIVE_UPPER_LEFT
    return fragmentPixel;
#else
    return vec2(fragmentPixel.x, uViewportSize.y - fragmentPixel.y);
#endif
}

float screenLayerRandom(vec2 pixel, float slice) {
    // Captured SV_Position is a pixel center with a top-left origin.
    vec2 nativePixel = furNativePixel(pixel);
    return hairCoveragePhase(nativePixel, slice, 1.0 / max(uViewportSize, vec2(1.0)),
                             uTemporalIndex, uTemporalPlusCycle);
}

float layerUvDivisor(vec2 pixel, float wetness) {
    vec2 nativePixel = furNativePixel(pixel);
    float phase = hairScreenPhase(nativePixel, 1.0 / max(uViewportSize, vec2(1.0)),
                                 uTemporalIndex, uTemporalPlusCycle);
    // Round_ni is floor. Dry fur always has divisor 1; wetness adds eight steps.
    return hairWetnessStep(wetness, phase) * 3.0 + 1.0;
}

vec3 fallbackTangent(vec3 normal) {
    vec3 axis = abs(normal.z) < 0.999
        ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 1.0, 0.0);
    return normalize(cross(axis, normal));
}

vec3 surfaceTangent(vec3 normal) {
    vec3 dpdx = dFdx(vWorldPosition);
    vec3 dpdy = dFdy(vWorldPosition);
    vec2 duvdx = dFdx(vUV);
    vec2 duvdy = dFdy(vUV);
    vec3 candidate = dpdx * duvdy.y - dpdy * duvdx.y;
    candidate -= normal * dot(normal, candidate);
    return dot(candidate, candidate) > 1e-10
        ? normalize(candidate) : fallbackTangent(normal);
}

struct FurShellMaterial {
    uvec4 material;
    uint strand;
    vec4 albedo;
    float depth;
};

FurShellMaterial evaluateFurShellMaterial() {
    vec4 control = texture(uFurControl, vUV);
    float wetness = clamp(uFurWetness, 0.0, 1.0);
    vec3 groom = furGroom(control.rg, vWorldTangent.w);
    vec2 layerUV = furLayerUV(
        vUV, uFurDensity, groom, vCurvedOffset,
        layerUvDivisor(gl_FragCoord.xy, wetness)
    );

    vec3 viewDirection = normalize(uEye - vWorldPosition);
    // The DXBC applies SV_IsFrontFace before the layer MIP bias and before
    // transforming the groom vector into the packed shading normal.
    float faceSign = gl_FrontFacing ? 1.0 : -1.0;
    vec3 normal = normalize(vWorldNormal) * faceSign;
    float facing = clamp(dot(normal, viewDirection), 0.0, 1.0);
    float mipBias = -2.0 * (1.0 - facing) * (1.0 - facing);
    // The captured sample clamps array coordinate 32 to the final slice.
    float layerValue = texture(
        uFurLayers, vec3(layerUV, vLayerSlice), mipBias
    ).r;
    // MaterialFur rounds out the recovered shell field as strands clump wet.
    layerValue = furWetLayerValue(layerValue, wetness);
    vec4 albedo = texture(uFurAlbedo, vUV);
    albedo = furWetAlbedo(albedo, wetness, vLayerSlice / 32.0);
    float coverage = clamp(
        layerValue * albedo.a + float(vBaseShell), 0.0, 1.0
    ) * clamp(1.0 - vLayerSlice / 64.0, 0.0, 1.0);
    vec3 strandTangent = furStrandDirection(
        normal, vWorldTangent, groom, (uFurRenderFlags & 65536u) != 0u);
    // Contact depth uses authored fur length and the unshifted material phase.
    vec2 materialPixel = furNativePixel(gl_FragCoord.xy);
    float materialPhase = hairScreenPhase(
        materialPixel, 1.0 / max(uViewportSize, vec2(1.0)),
        uTemporalIndex, uTemporalPlusCycle
    );
    float customViewDepth = furContactDepth(
        1.0 / gl_FragCoord.w, control.b, layerValue, materialPhase,
        vLayerSlice / 32.0, uFurLength
    );
    vec2 materialResponse = uHasFurSpecular
        ? furGlossSpecular(texture(uFurSpecular, vUV).rg,
                           uFurGlossScale, uFurSpecularScale,
                           wetness, vLayerSlice / 32.0)
        : vec2(0.0);
    uvec4 packedMaterial = furPackGBuffer(
        normal, materialResponse.x, materialResponse.y, uFurRenderFlags
    );
    uint packedStrand = furPackExtra(strandTangent, uFurTransmittanceScale);
    if (coverage < screenLayerRandom(gl_FragCoord.xy, vLayerSlice)) discard;
    // Native target alpha carries material occlusion, independently of coverage.
    float occlusion = clamp(vLayerSlice * 0.015625, 0.0, 1.0)
        * (1.0 - control.a) + control.a;
    return FurShellMaterial(packedMaterial, packedStrand, vec4(albedo.rgb, occlusion), customViewDepth);
}
"""
for _marker, _filename in (
    ('/* HAIR_LIGHTING_NOISE */', 'hair_lighting_noise.glsl'),
    ('/* FUR_MATERIAL */', 'fur_material.glsl'),
    ('/* FUR_GBUFFER */', 'fur_gbuffer.glsl'),
):
    FUR_SHELL_MATERIAL_COMMON = FUR_SHELL_MATERIAL_COMMON.replace(
        _marker, (Path(__file__).resolve().parents[1] / 'core' / _filename).read_text(encoding='utf-8'),
    )

_HAIR_PREVIEW_LIGHTING = '\n'.join(
    (Path(__file__).resolve().parents[1] / 'core' / filename).read_text(encoding='utf-8')
    for filename in ('hair_frame.glsl', 'hair_lobes.glsl', 'hair_response.glsl',
                     'hair_environment_frame.glsl')
)
_HAIR_PREVIEW_LIGHTING += '\n#ifdef HAIR_SCENE_LIGHTING\n' + '\n'.join(
    (Path(__file__).resolve().parents[1] / 'core' / filename).read_text(encoding='utf-8')
    for filename in ('hair_light_grid.glsl', 'hair_probe_lighting.glsl', 'hair_key_shadow.glsl', 'hair_history.glsl', 'hair_scene.glsl', 'hair_key_modulation.glsl', 'hair_local_lights.glsl')
) + '\n#endif\n' + (Path(__file__).resolve().parents[1] / 'core' / 'hair_preview_lighting.glsl').read_text(encoding='utf-8')

# Native deferred material targets, including the previous-frame motion written
# by PS_FurShellGBufferDeferred. The current lighting stages consume the first
# four; temporal reconstruction will consume Motion in a later parity slice.
FUR_MATERIAL_FRAG_SRC = FUR_SHELL_MATERIAL_COMMON + """
layout(location = 0) out uvec4 Material;
layout(location = 1) out vec4 AlbedoOcclusion;
layout(location = 2) out float LinearDepth;
layout(location = 3) out uint Strand;
layout(location = 4) out vec2 Motion;
layout(location = 5) out uint Stencil;
void main() {
    FurShellMaterial surface = evaluateFurShellMaterial();
    Material = surface.material;
    AlbedoOcclusion = surface.albedo;
    LinearDepth = surface.depth;
    Strand = surface.strand;
    vec2 pixel = furNativePixel(gl_FragCoord.xy);
    Motion = furMotionVector(
        pixel, 1.0 / max(uViewportSize, vec2(1.0)), vPreviousClip,
        uMotionNearPlane, uViewportSize
    );
    Stencil = 128u;
}
"""


# Discrete ModelStrand accents use the same packed material targets as shell
# fur.  The vertex inputs are generated from the captured guide buffers using
# the retail live-sample layout and profile curves; the shader performs the
# captured child-clump, thickness-mask, and camera-facing ribbon expansion.
MODEL_STRAND_VERT_SRC = """
#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aRootNormal;
layout(location=2) in vec3 aCurveTangent;
layout(location=3) in vec3 aFrameY;
layout(location=4) in vec2 aRootUV;
layout(location=5) in vec4 aCurve; // thickness, clump x/y, along
layout(location=6) in vec4 aIds;   // child, guide, side, width scale

uniform mat4 uMVP;
uniform mat4 uPreviousMVP;
uniform mat4 uModel;
uniform mat3 uNormal;
uniform vec3 uEye;
uniform sampler2D uThickness;
uniform float uChildCount;
uniform float uStrayBase;
uniform float uStrayStrength;
uniform float uStrayPower;

out vec2 vStrandUV;
out vec3 vStrandWorldPosition;
out vec3 vStrandNormal;
out vec3 vStrandTangent;
out float vStrandAlong;
out vec4 vStrandPreviousClip;

void main() {
    float child = aIds.x;
    float along = clamp(aCurve.w, 0.0, 1.0);
    vec3 normal = normalize(uNormal * aRootNormal);
    vec3 tangent = normalize(uNormal * aCurveTangent);
    vec3 frameY = normalize(uNormal * aFrameY);
    vec4 mask = textureLod(uThickness, aRootUV, 0.0);
    float angle = child * 2.39996;
    float radius = sqrt((child + 1.0) / uChildCount);
    float radialCos = cos(angle) * radius;
    float radialSin = sin(angle) * radius;
    float maskAlong = mix(mask.g, mask.b, along);
    vec3 clumpOffset = normal * (radialCos * 2.0 * maskAlong * aCurve.y)
        + frameY * (radialSin * 2.0 * maskAlong * aCurve.z);
    float hashBase = fract((aIds.y + child) * 0.318310 + 0.1);
    float strayRandom = fract((hashBase * hashBase * 83521.0)
        * hashBase * (hashBase * 3.0));
    float stray = uStrayBase * along * uStrayStrength
        * pow(strayRandom, uStrayPower);
    clumpOffset += (normal * radialCos + frameY * radialSin) * stray;

    vec3 center = (uModel * vec4(aPos + clumpOffset, 1.0)).xyz;
    vec3 viewDirection = normalize(uEye - center);
    vec3 facing = cross(tangent, viewDirection);
    if (dot(facing, facing) < 1e-12) facing = cross(tangent, normal);
    facing = normalize(facing);
    float ribbonWidth = 2.0 * mask.r * aCurve.x * aIds.w;
    vec3 worldPosition = center + facing * ((aIds.z - 0.5) * ribbonWidth);

    vStrandUV = aRootUV;
    vStrandWorldPosition = worldPosition;
    vStrandNormal = normal;
    vStrandTangent = tangent;
    vStrandAlong = along;
    vec4 sideClip = uMVP * vec4(aPos + clumpOffset
        + facing * ((aIds.z - 0.5) * ribbonWidth), 1.0);
    vStrandPreviousClip = uPreviousMVP * vec4(aPos + clumpOffset
        + facing * ((aIds.z - 0.5) * ribbonWidth), 1.0);
    gl_Position = sideClip;
}
"""

MODEL_STRAND_MATERIAL_FRAG_SRC = """
#version 330 core
#extension GL_ARB_gpu_shader5 : enable
in vec2 vStrandUV;
in vec3 vStrandWorldPosition;
in vec3 vStrandNormal;
in vec3 vStrandTangent;
in float vStrandAlong;
in vec4 vStrandPreviousClip;
uniform sampler2D uDiffuse;
uniform float uReflectance;
uniform float uFurWetness;
uniform float uTransmittance;
uniform vec2 uViewportSize;
uniform float uMotionNearPlane;
uniform uint uFurRenderFlags;
layout(location = 0) out uvec4 Material;
layout(location = 1) out vec4 AlbedoOcclusion;
layout(location = 2) out float LinearDepth;
layout(location = 3) out uint Strand;
layout(location = 4) out vec2 Motion;
layout(location = 5) out uint Stencil;
/* FUR_MATERIAL */
/* FUR_GBUFFER */

vec2 nativePixel(vec2 fragmentPixel) {
#ifdef RCRA_NATIVE_UPPER_LEFT
    return fragmentPixel;
#else
    return vec2(fragmentPixel.x, uViewportSize.y - fragmentPixel.y);
#endif
}

void main() {
    vec3 textureColor = texture(uDiffuse, vStrandUV).rgb;
    vec3 authoredGamma = pow(vec3(clamp(uReflectance, 0.0, 1.0)), vec3(0.447761));
    vec3 textureGamma = pow(clamp(textureColor, vec3(0.0), vec3(1.0)), vec3(0.447761));
    vec3 multiplyBranch = authoredGamma * (2.0 * textureGamma);
    vec3 screenBranch = 1.0 - (1.0 - textureGamma)
        * (1.0 - (authoredGamma - 0.5) * 2.0);
    vec3 gammaCombined = mix(screenBranch, multiplyBranch, step(vec3(0.5), textureGamma));
    vec4 albedo = furWetAlbedo(
        vec4(pow(clamp(gammaCombined, vec3(0.0), vec3(1.0)), vec3(2.23333)), 1.0),
        clamp(uFurWetness, 0.0, 1.0), clamp(vStrandAlong, 0.0, 1.0));
    vec2 response = furGlossSpecular(
        vec2(0.2, 0.0395462364), 1.0, 1.0,
        clamp(uFurWetness, 0.0, 1.0), clamp(vStrandAlong, 0.0, 1.0));
    vec3 normal = normalize(vStrandNormal) * (gl_FrontFacing ? 1.0 : -1.0);
    vec3 tangent = normalize(vStrandTangent);
    Material = furPackGBuffer(normal, response.x, response.y, uFurRenderFlags);
    Strand = furPackExtra(tangent, uTransmittance);
    AlbedoOcclusion = albedo;
    LinearDepth = 1.0 / gl_FragCoord.w;
    Motion = furMotionVector(nativePixel(gl_FragCoord.xy),
        1.0 / max(uViewportSize, vec2(1.0)), vStrandPreviousClip,
        uMotionNearPlane, uViewportSize);
    Stencil = 128u;
}
"""
for _marker, _filename in (
    ('/* FUR_MATERIAL */', 'fur_material.glsl'),
    ('/* FUR_GBUFFER */', 'fur_gbuffer.glsl'),
):
    MODEL_STRAND_MATERIAL_FRAG_SRC = MODEL_STRAND_MATERIAL_FRAG_SRC.replace(
        _marker,
        (Path(__file__).resolve().parents[1] / 'core' / _filename).read_text(encoding='utf-8'),
    )

FUR_SHELL_FRAG_SRC = FUR_SHELL_MATERIAL_COMMON + _HAIR_PREVIEW_LIGHTING + """
layout(location = 0) out vec4 FragColor;
layout(location = 1) out vec4 BrightColor;
layout(location = 2) out vec4 FurGBuffer;
layout(location = 3) out vec4 FurNormalMask;
layout(location = 4) out vec4 FurKeyLight;
void main() {
    FurShellMaterial surface = evaluateFurShellMaterial();
    vec3 normal = furUnpackNormal(surface.material);
    vec3 strandTangent = furUnpackStrand(surface.strand);
    vec2 pixel = floor(furNativePixel(gl_FragCoord.xy));
    vec3 directColor, indirectColor;
    evaluatePreviewHairLighting(surface.material, surface.strand, normal, strandTangent,
        surface.albedo, surface.depth, normalize(uEye - vWorldPosition), pixel, vWorldPosition, 1.0,
        directColor, indirectColor);
    FragColor = vec4(indirectColor + directColor, 1.0);
    BrightColor = vec4(0.0);
    FurGBuffer = vec4(strandTangent, surface.depth);
    FurNormalMask = vec4(normal, 1.0);
    FurKeyLight = vec4(directColor, float((surface.strand >> 19u) & 127u));
}
"""

# A separate vector pass prevents precise lighting expressions from changing the
# native packed-vector decode. Every pixel is written, including opaque depth.
FUR_DECODE_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : enable
uniform usampler2D uMaterial;
uniform usampler2D uStrand;
uniform sampler2D uLinearDepth;
uniform sampler2D uOpaqueDepth;
layout(location = 0) out vec4 FurGBuffer;
layout(location = 1) out vec4 FurNormalMask;
/* FUR_GBUFFER */
void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    uvec4 material = texelFetch(uMaterial, pixel, 0);
    bool hair = ((material.x >> 13u) & 7u) == 3u && (material.x & 4096u) == 0u;
    if (!hair) {
        FurGBuffer = vec4(0.0, 0.0, 0.0, texelFetch(uOpaqueDepth, pixel, 0).a);
        FurNormalMask = vec4(0.0);
        return;
    }
    uint strand = texelFetch(uStrand, pixel, 0).r;
    FurGBuffer = vec4(furUnpackStrand(strand), texelFetch(uLinearDepth, pixel, 0).r);
    FurNormalMask = vec4(furUnpackNormal(material), 1.0);
}
""".replace('/* FUR_GBUFFER */',
    (Path(__file__).resolve().parents[1] / 'core/fur_gbuffer.glsl').read_text(encoding='utf-8'))

FUR_LIGHTING_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : enable
uniform usampler2D uMaterial;
uniform usampler2D uStrand;
uniform sampler2D uAlbedoOcclusion;
uniform sampler2D uFurGBuffer;
uniform sampler2D uFurNormalMask;
uniform samplerCube uFurEnvironment;
uniform sampler2D uFurBrdfLut;
uniform bool uHasFurEnvironment;
uniform vec3 uLightDir;
uniform vec2 uViewportSize;
uniform vec4 uScreenToView;
uniform mat3 uViewToWorld;
uniform vec3 uCameraPosition;
uniform float uTemporalIndex;
uniform float uTemporalPlusCycle;
layout(location = 0) out vec4 IndirectColor;
layout(location = 1) out vec4 KeyLight;
/* HAIR_LIGHTING_NOISE */
/* HAIR_SURFACE */
/* HAIR_PREVIEW_LIGHTING */
#ifdef HAIR_SCENE_LIGHTING
/* HAIR_CONTACT */
float hairHistoryDepth(ivec2 pixel) {
    ivec2 dimensions = textureSize(uFurGBuffer, 0);
    if (any(lessThan(pixel, ivec2(0))) || any(greaterThanEqual(pixel, dimensions))) return 0.0;
#ifndef RCRA_NATIVE_UPPER_LEFT
    return texelFetch(uFurGBuffer, ivec2(pixel.x, dimensions.y - 1 - pixel.y), 0).a;
#else
    return texelFetch(uFurGBuffer, pixel, 0).a;
#endif
}
float hairContactLoadDepth(ivec2 pixel) { return hairHistoryDepth(pixel); }
#endif
void main() {
    ivec2 center = ivec2(gl_FragCoord.xy);
    vec4 normalMask = texelFetch(uFurNormalMask, center, 0);
    if (normalMask.a <= 0.0) discard;
    vec4 fur = texelFetch(uFurGBuffer, center, 0);
    uvec4 material = texelFetch(uMaterial, center, 0);
    uint strand = texelFetch(uStrand, center, 0).r;
    vec4 albedo = texelFetch(uAlbedoOcclusion, center, 0);
#ifdef RCRA_NATIVE_UPPER_LEFT
    vec2 pixel = vec2(center);
#else
    vec2 pixel = vec2(center.x, int(uViewportSize.y) - 1 - center.y);
#endif
    vec3 position = hairViewPosition(pixel, fur.a, 1.0 / uViewportSize,
                                     uScreenToView, vec2(1.0, 0.0));
    vec3 relative = hairRelativeWorldPosition(position, uViewToWorld);
    float keyVisibility = 1.0;
#ifdef HAIR_SCENE_LIGHTING
    vec3 noise = hairLightingNoise(pixel, 1.0 / uViewportSize, uTemporalIndex, uTemporalPlusCycle);
    keyVisibility = hairSceneKeyVisibility(relative, strand, noise.xz);
    if (keyVisibility <= 0.0001) keyVisibility = 0.0;
    else if (uFurContactEnabled && (uHairSceneFlags & 2u) != 0u) {
        vec3 viewLight = vec3(dot(uViewToWorld[0], uLightDir),
            dot(uViewToWorld[1], uLightDir), dot(uViewToWorld[2], uLightDir));
        float radius = fma(float((strand >> 19u) & 127u), uintBitsToFloat(0x39041aa4u), uintBitsToFloat(0x3b03126fu));
        float contact = hairContactVisibility(pixel, fur.a, normalMask.xyz, uLightDir, viewLight,
            1.0 / uViewportSize, uScreenToView, vec2(1.0, 0.0), uHairViewToScreen,
            uViewportSize, noise.xz, radius);
        keyVisibility = min(keyVisibility, contact);
    }
#endif
    vec3 directColor, indirectColor;
    evaluatePreviewHairLighting(material, strand, normalMask.xyz, fur.xyz,
        albedo, fur.a, hairViewDirection(relative), pixel, relative + uCameraPosition, keyVisibility,
        directColor, indirectColor);
    // Scene lighting already combines visibility and history before material resolve.
    IndirectColor = vec4(indirectColor, 1.0);
    KeyLight = vec4(directColor, float((strand >> 19u) & 127u));
}
"""
for _marker, _code in (
    ('/* HAIR_LIGHTING_NOISE */', (Path(__file__).resolve().parents[1] / 'core/hair_lighting_noise.glsl').read_text(encoding='utf-8')),
    ('/* HAIR_SURFACE */', (Path(__file__).resolve().parents[1] / 'core/hair_surface.glsl').read_text(encoding='utf-8')),
    ('/* HAIR_CONTACT */', (Path(__file__).resolve().parents[1] / 'core/hair_contact_shadow.glsl').read_text(encoding='utf-8')),
    ('/* HAIR_PREVIEW_LIGHTING */', _HAIR_PREVIEW_LIGHTING),
):
    FUR_LIGHTING_FRAG = FUR_LIGHTING_FRAG.replace(_marker, _code)

FUR_SCENE_LIGHTING_FRAG = FUR_LIGHTING_FRAG.replace(
    '#version 330 core', '#version 430 core\n#define HAIR_SCENE_LIGHTING', 1,
)


POST_VERT = """
#version 330 core
layout(location=0) in vec3 aPos;
out vec2 vTexCoord;
void main() {
#ifdef RCRA_NATIVE_UPPER_LEFT
    vTexCoord = vec2(aPos.x * 0.5 + 0.5, 0.5 - aPos.y * 0.5);
#else
    vTexCoord = aPos.xy * 0.5 + 0.5;
#endif
    gl_Position = vec4(aPos, 1.0);
}
"""

BLUR_FRAG = """
#version 330 core
in vec2 vTexCoord;
uniform sampler2D uImage;
uniform bool uHorizontal;
out vec4 FragColor;
void main() {
    vec2 texel = 1.0 / vec2(textureSize(uImage, 0));
    float weights[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
    vec3 result = texture(uImage, vTexCoord).rgb * weights[0];
    for (int i = 1; i < 5; ++i) {
        vec2 offset = uHorizontal ? vec2(texel.x * i, 0.0) : vec2(0.0, texel.y * i);
        result += texture(uImage, vTexCoord + offset).rgb * weights[i];
        result += texture(uImage, vTexCoord - offset).rgb * weights[i];
    }
    FragColor = vec4(result, 1.0);
}
"""

COMPOSITE_FRAG = """
#version 330 core
in vec2 vTexCoord;
uniform sampler2D uScene;
uniform sampler2D uBloom;
uniform bool uBloomEnabled;
uniform float uBloomStrength;
uniform float uExposure;
out vec4 FragColor;

vec3 acesToneMap(vec3 x) {
    const float a = 2.51;
    const float b = 0.03;
    const float c = 2.43;
    const float d = 0.59;
    const float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void main() {
    vec3 hdr = texture(uScene, vTexCoord).rgb;
    if (uBloomEnabled) {
        hdr += texture(uBloom, vTexCoord).rgb * uBloomStrength;
    }
    vec3 mapped = acesToneMap(hdr * uExposure);
    FragColor = vec4(mapped, 1.0);
}
"""

MOTION_BLUR_DOWNSAMPLE_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : require
uniform sampler2D uMotion;
uniform sampler2D uOpaqueMotion;
uniform sampler2D uFurMask;
uniform sampler2D uFurDepth;
uniform sampler2D uSceneDepth;
uniform vec2 uOutputInvSize;
uniform float uShutterScale;
layout(location = 0) out vec2 DepthVelocity;
layout(location = 1) out vec2 HalfVelocity;

void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec2 uv = (vec2(pixel) + 0.5) * uOutputInvSize;
    vec4 furMask = textureGather(uFurMask, uv, 3);
    vec4 furDepth = textureGather(uFurDepth, uv, 0);
    vec4 sceneDepth = textureGather(uSceneDepth, uv, 3);
    vec4 depth = mix(sceneDepth, furDepth, greaterThan(furMask, vec4(0.0)));
    vec4 velocityX = mix(
        textureGather(uOpaqueMotion, uv, 0),
        textureGather(uMotion, uv, 0),
        greaterThan(furMask, vec4(0.0))
    );
    vec4 velocityY = -mix(
        textureGather(uOpaqueMotion, uv, 1),
        textureGather(uMotion, uv, 1),
        greaterThan(furMask, vec4(0.0))
    );
    float minimumDepth = min(min(depth.x, depth.y), min(depth.z, depth.w));
    vec2 selected = vec2(velocityX.x, velocityY.x);
    if (depth.y == minimumDepth) selected = vec2(velocityX.y, velocityY.y);
    if (depth.z == minimumDepth) selected = vec2(velocityX.z, velocityY.z);
    if (depth.w == minimumDepth) selected = vec2(velocityX.w, velocityY.w);
    HalfVelocity = selected;

    vec2 adjusted = selected * uShutterScale;
    float maximumComponent = max(abs(adjusted.x), abs(adjusted.y));
    float ramp = clamp(0.25 * maximumComponent - 0.6000000238418579, 0.0, 1.0);
    // Captured m_RampConsts.z is exactly zero, so the native smooth-ramp
    // multiplier is the identity for this frame configuration.
    adjusted *= 20.0 / max(max(abs(adjusted.x), abs(adjusted.y)), 20.0);
    DepthVelocity = vec2(minimumDepth, length(adjusted));
}
"""

MOTION_BLUR_NEIGHBORHOOD_HALF_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : require
uniform sampler2D uVelocity;
uniform vec2 uOutputInvSize;
uniform float uVelocityScale;
out vec2 NeighborhoodVelocity;
void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec2 uv = (vec2(pixel) + 0.5) * uOutputInvSize;
    vec4 velocityX = textureGather(uVelocity, uv, 0);
    vec4 velocityY = textureGather(uVelocity, uv, 1);
    vec2 velocity[4] = vec2[4](
        vec2(velocityX.x, velocityY.x), vec2(velocityX.y, velocityY.y),
        vec2(velocityX.z, velocityY.z), vec2(velocityX.w, velocityY.w)
    );
    float maximumMagnitude = max(
        max(dot(velocity[0], velocity[0]), dot(velocity[1], velocity[1])),
        max(dot(velocity[2], velocity[2]), dot(velocity[3], velocity[3]))
    );
    vec2 selected = velocity[0];
    if (dot(velocity[1], velocity[1]) == maximumMagnitude) selected = velocity[1];
    if (dot(velocity[2], velocity[2]) == maximumMagnitude) selected = velocity[2];
    if (dot(velocity[3], velocity[3]) == maximumMagnitude) selected = velocity[3];
    NeighborhoodVelocity = selected * uVelocityScale;
}
"""

MOTION_BLUR_NEIGHBORHOOD_QUARTER_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : require
uniform sampler2D uVelocity;
uniform vec2 uOutputInvSize;
out vec2 NeighborhoodVelocity;

void appendGather(inout vec2 velocity[16], int base, vec2 uv, ivec2 offset) {
    vec4 x = textureGatherOffset(uVelocity, uv, offset, 0);
    vec4 y = textureGatherOffset(uVelocity, uv, offset, 1);
    velocity[base + 0] = vec2(x.x, y.x);
    velocity[base + 1] = vec2(x.y, y.y);
    velocity[base + 2] = vec2(x.z, y.z);
    velocity[base + 3] = vec2(x.w, y.w);
}

void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec2 uv = (vec2(pixel) + 0.5) * uOutputInvSize;
    vec2 velocity[16];
    appendGather(velocity, 0, uv, ivec2(-1, -1));
    appendGather(velocity, 4, uv, ivec2(1, -1));
    appendGather(velocity, 8, uv, ivec2(-1, 1));
    appendGather(velocity, 12, uv, ivec2(1, 1));
    float maximumMagnitude = 0.0;
    for (int index = 0; index < 16; ++index) {
        maximumMagnitude = max(maximumMagnitude, dot(velocity[index], velocity[index]));
    }
    vec2 selected = velocity[0];
    for (int index = 1; index < 16; ++index) {
        if (dot(velocity[index], velocity[index]) == maximumMagnitude) selected = velocity[index];
    }
    NeighborhoodVelocity = selected;
}
"""

MOTION_BLUR_GATHER_NEIGHBORHOOD_FRAG = """
#version 330 core
uniform sampler2D uVelocity;
out vec2 GatheredVelocity;
vec2 loadClamped(ivec2 pixel) {
    ivec2 dimensions = textureSize(uVelocity, 0);
    return texelFetch(uVelocity, clamp(pixel, ivec2(0), dimensions - 1), 0).xy;
}
void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec2 velocity[25];
    float magnitude[25];
    int index = 0;
    float maximumMagnitude = 0.0;
    vec2 reference = vec2(0.0);
    for (int y = -2; y <= 2; ++y) {
        for (int x = -2; x <= 2; ++x) {
            velocity[index] = loadClamped(pixel + ivec2(x, y));
            magnitude[index] = dot(velocity[index], velocity[index]);
            if (magnitude[index] > 0.0 && magnitude[index] >= maximumMagnitude) {
                maximumMagnitude = magnitude[index];
                reference = velocity[index];
            }
            ++index;
        }
    }
    vec2 weightedVelocity = vec2(0.0);
    float totalMagnitude = 0.0;
    for (index = 0; index < 25; ++index) {
        vec2 aligned = dot(velocity[index], reference) >= 0.0
            ? velocity[index] : -velocity[index];
        float alignedMagnitude = dot(aligned, aligned);
        weightedVelocity += aligned * alignedMagnitude;
        totalMagnitude += alignedMagnitude;
    }
    vec2 result = weightedVelocity / max(totalMagnitude, 0.0010000000474974513);
    float ramp = clamp(0.25 * length(result) - 0.6000000238418579, 0.0, 1.0);
    GatheredVelocity = result;
}
"""

MOTION_BLUR_SCATTER_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : require
uniform sampler2D uDepthVelocity;
uniform sampler2D uNeighborhoodVelocity;
uniform vec2 uOutputInvSize;
out float Scatter;

vec2 alignVelocity(vec2 reference, vec2 candidate) {
    return dot(reference, candidate) >= 0.0 ? candidate : -candidate;
}

vec2 gatherNeighborhoodVelocity(ivec2 pixel) {
    vec2 velocityUv = (vec2(pixel) + 0.5) * uOutputInvSize;
    vec4 velocityX = textureGather(uNeighborhoodVelocity, velocityUv, 0);
    vec4 velocityY = textureGather(uNeighborhoodVelocity, velocityUv, 1);
    vec2 dither = vec2((pixel + ivec2(4)) & ivec2(7)) * 0.125;
    vec2 lowWeight = vec2(0.9375) - dither;
    vec2 highWeight = dither + vec2(0.0625);
    float weights[4] = float[4](
        highWeight.y * lowWeight.x, highWeight.y * highWeight.x,
        lowWeight.y * highWeight.x, lowWeight.y * lowWeight.x
    );
    vec2 velocity[4] = vec2[4](
        vec2(velocityX.x, velocityY.x) * weights[0],
        vec2(velocityX.y, velocityY.y) * weights[1],
        vec2(velocityX.z, velocityY.z) * weights[2],
        vec2(velocityX.w, velocityY.w) * weights[3]
    );
    vec2 reference = velocity[3];
    vec2 result = reference;
    result += alignVelocity(reference, velocity[2]);
    result += alignVelocity(reference, velocity[1]);
    result += alignVelocity(reference, velocity[0]);
    return result;
}

vec2 directionalCrossings(
    vec2 centerUv, vec2 uvDirection, float pathLength,
    float centerInverseDepth, float tapFraction
) {
    vec2 offset = uvDirection * tapFraction;
    vec2 positive = textureLod(uDepthVelocity, centerUv + offset, 0.0).xy;
    vec2 negative = textureLod(uDepthVelocity, centerUv - offset, 0.0).xy;
    float ramp = pathLength * tapFraction - 0.5;
    float centerDepthScale = 16.0 * centerInverseDepth;
    float positiveHit = clamp(positive.y - ramp, 0.0, 1.0)
        * clamp(16.5 - centerDepthScale * positive.x, 0.0, 1.0)
        / max(positive.y, 1.0);
    float negativeHit = clamp(negative.y - ramp, 0.0, 1.0)
        * clamp(16.5 - centerDepthScale * negative.x, 0.0, 1.0)
        / max(negative.y, 1.0);
    float crossingScale = 4.0 * centerInverseDepth;
    return vec2(
        clamp(crossingScale * (negative.x - positive.x), 0.0, 1.0) * positiveHit,
        clamp(crossingScale * (positive.x - negative.x), 0.0, 1.0) * negativeHit
    );
}

void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec2 velocity = gatherNeighborhoodVelocity(pixel);
    float velocityMagnitude = length(velocity);
    if (velocityMagnitude < 0.800000011920929) {
        Scatter = 0.0;
        return;
    }
    float sampleScale = 20.0 / max(abs(velocity.x), abs(velocity.y));
    vec2 centerUv = (vec2(pixel) + 0.5) * uOutputInvSize;
    vec2 uvDirection = velocity * sampleScale * uOutputInvSize;
    float pathLength = sampleScale * velocityMagnitude;
    float centerInverseDepth = 1.0 / texelFetch(uDepthVelocity, pixel, 0).x;
    vec2 crossing[20];
    crossing[0] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.05000000074505806);
    crossing[1] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.10000000149011612);
    crossing[2] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.15000000596046448);
    crossing[3] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.20000000298023224);
    crossing[4] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.25);
    crossing[5] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.30000001192092896);
    crossing[6] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.3499999940395355);
    crossing[7] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.4000000059604645);
    crossing[8] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.44999998807907104);
    crossing[9] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.5);
    crossing[10] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.550000011920929);
    crossing[11] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.6000000238418579);
    crossing[12] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.6499999761581421);
    crossing[13] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.699999988079071);
    crossing[14] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.75);
    crossing[15] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.800000011920929);
    crossing[16] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.8500000238418579);
    crossing[17] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.8999999761581421);
    crossing[18] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 0.949999988079071);
    crossing[19] = directionalCrossings(centerUv, uvDirection, pathLength, centerInverseDepth, 1.0);
    float orderedSum = crossing[0].y + crossing[0].x;
    for (int index = 1; index < 20; ++index) {
        orderedSum += crossing[index].x;
        orderedSum += crossing[index].y;
    }
    Scatter = clamp(orderedSum * 2.5, 0.0, 1.0);
}
"""

TEMPORAL_LINEAR_DEPTH_FRAG = """
#version 330 core
uniform sampler2D uFurMask;
uniform sampler2D uFurDepth;
uniform sampler2D uSceneDepth;
uniform bool uHasFurDepth;
layout(location = 0) out float OpaqueDepth;
layout(location = 1) out float ComposedDepth;

void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    float opaqueDepth = texelFetch(uSceneDepth, pixel, 0).a;
    float furDepth = uHasFurDepth ? texelFetch(uFurDepth, pixel, 0).r : 0.0;
    bool hasFur = uHasFurDepth
        && texelFetch(uFurMask, pixel, 0).a > 0.0
        && furDepth > 0.0;
    OpaqueDepth = opaqueDepth;
    ComposedDepth = hasFur ? furDepth : opaqueDepth;
}
"""

TEMPORAL_HALF_BASE_FRAG = """
#version 330 core
uniform sampler2D uFullDisocclusion;
uniform sampler2D uOpaqueDepth;
uniform vec2 uFullDimensions;
layout(location = 0) out float HalfDisocclusion;
layout(location = 1) out vec2 HalfVelocity;
layout(location = 2) out float MaximumDepth;
layout(location = 3) out float MinimumDepth;

ivec2 clampFullPixel(ivec2 pixel) {
    return clamp(pixel, ivec2(0), ivec2(uFullDimensions) - ivec2(1));
}

void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    ivec2 base = pixel * 2;
    float depth00 = texelFetch(uOpaqueDepth, clampFullPixel(base), 0).r;
    float depth10 = texelFetch(
        uOpaqueDepth, clampFullPixel(base + ivec2(1, 0)), 0
    ).r;
    float depth01 = texelFetch(
        uOpaqueDepth, clampFullPixel(base + ivec2(0, 1)), 0
    ).r;
    float depth11 = texelFetch(
        uOpaqueDepth, clampFullPixel(base + ivec2(1, 1)), 0
    ).r;
    vec2 uv = (vec2(base) + 1.0) / uFullDimensions;
    HalfDisocclusion = textureLod(uFullDisocclusion, uv, 0.0).r;
    HalfVelocity = vec2(0.0);
    MaximumDepth = max(max(depth00, depth10), max(depth01, depth11));
    MinimumDepth = min(min(depth00, depth10), min(depth01, depth11));
}
"""

TEMPORAL_ALPHA_MASK_FRAG = """
#version 330 core
uniform sampler2D uComposedDepth;
uniform sampler2D uOpaqueMinimumDepth;
uniform vec2 uFullDimensions;
layout(location = 0) out float AlphaMask;

void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec2 uv = (vec2(pixel * 2) + 1.0) / uFullDimensions;
    float fullDepth = textureLod(uComposedDepth, uv, 0.0).r;
    float halfDepth = texelFetch(uOpaqueMinimumDepth, pixel, 0).r;
    AlphaMask = float(fullDepth < halfDepth * 0.9980000257492065);
}
"""

TEMPORAL_ALPHA_HALF_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : require
uniform sampler2D uFullDisocclusion;
uniform sampler2D uComposedDepth;
uniform sampler2D uFurVelocity;
uniform sampler2D uOpaqueVelocity;
uniform sampler2D uFurMask;
uniform sampler2D uAlphaMask;
uniform vec2 uFullDimensions;
layout(location = 0) out float HalfDisocclusion;
layout(location = 1) out vec2 HalfVelocity;
layout(location = 2) out float MaximumDepth;
layout(location = 3) out float MinimumDepth;

void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    if (texelFetch(uAlphaMask, pixel, 0).r == 0.0) {
        discard;
    }
    vec2 uv = (vec2(pixel * 2) + 1.0) / uFullDimensions;
    vec4 depths = textureGather(uComposedDepth, uv, 0);
    float maximumDepth = max(max(depths.x, depths.y), depths.z);
    float minimumDepth = min(min(depths.x, depths.y), depths.z);
    vec4 furMask = textureGather(uFurMask, uv, 3);
    vec4 velocityX = mix(
        textureGather(uOpaqueVelocity, uv, 0),
        textureGather(uFurVelocity, uv, 0),
        greaterThan(furMask, vec4(0.0))
    );
    vec4 velocityY = mix(
        textureGather(uOpaqueVelocity, uv, 1),
        textureGather(uFurVelocity, uv, 1),
        greaterThan(furMask, vec4(0.0))
    );
    vec2 selectedVelocity = vec2(velocityX.x, velocityY.x);
    if (depths.y == maximumDepth) {
        selectedVelocity = vec2(velocityX.y, velocityY.y);
    }
    if (depths.z == maximumDepth) {
        selectedVelocity = vec2(velocityX.z, velocityY.z);
    }
    if (depths.w == maximumDepth) {
        selectedVelocity = vec2(velocityX.w, velocityY.w);
    }
    HalfDisocclusion = textureLod(uFullDisocclusion, uv, 0.0).r;
    HalfVelocity = selectedVelocity;
    MaximumDepth = maximumDepth;
    MinimumDepth = minimumDepth;
}
"""

TEMPORAL_DISOCCLUSION_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : require
uniform sampler2D uMotion;
uniform sampler2D uOpaqueMotion;
uniform sampler2D uFurMask;
uniform sampler2D uLinearDepth;
uniform sampler2D uHistoryDepthMotion;
uniform sampler2D uMotionBlurScatter;
uniform sampler2D uAccAlphaFlags;
uniform mat4 uCurrentToPreviousView;
uniform mat3 uCurrentToPreviousRotation;
uniform mat4 uPreviousProjection;
uniform vec4 uCurrentProjection;
uniform vec2 uDimensions;
uniform float uDepthBase;
uniform float uDepthSlope;
uniform float uMotionThreshold;
uniform float uCameraMotionScale;
uniform bool uHasFurMotion;
uniform bool uHasOpaqueMotion;
uniform bool uHasHistory;
uniform bool uRequireAccAlphaFlag;
layout(location = 0) out vec2 FullDisocclusion;
layout(location = 1) out vec2 DepthMotion;

ivec2 clampPixel(ivec2 pixel, ivec2 dimensions) {
    return clamp(pixel, ivec2(0), dimensions - ivec2(1));
}

float loadDepth(ivec2 pixel, ivec2 dimensions) {
    pixel = clampPixel(pixel, dimensions);
    return texelFetch(uLinearDepth, pixel, 0).r;
}

vec2 loadVelocity(ivec2 pixel, ivec2 dimensions) {
    pixel = clampPixel(pixel, dimensions);
    bool useFurMotion = uHasFurMotion
        && texelFetch(uFurMask, pixel, 0).a > 0.0;
    if (!useFurMotion && !uHasOpaqueMotion) {
        return vec2(0.0);
    }
    vec2 nativeVelocity = useFurMotion
        ? texelFetch(uMotion, pixel, 0).xy
        : texelFetch(uOpaqueMotion, pixel, 0).xy;
#ifdef RCRA_NATIVE_UPPER_LEFT
    return nativeVelocity;
#else
    return vec2(nativeVelocity.x, -nativeVelocity.y);
#endif
}

vec3 reconstructViewPosition(vec2 uv, float depth) {
    vec2 ndc = uv * 2.0 - 1.0;
#ifdef RCRA_NATIVE_UPPER_LEFT
    ndc.y = -ndc.y;
#endif
    vec2 viewXY = (ndc + uCurrentProjection.zw) * depth
        / uCurrentProjection.xy;
    return vec3(viewXY, -depth);
}

vec2 projectedCenteredUv(mat4 projection, vec3 viewPosition) {
    vec4 clip = projection * vec4(viewPosition, 1.0);
    vec2 centered = clip.xy / max(clip.w, 0.000001) * 0.5;
#ifdef RCRA_NATIVE_UPPER_LEFT
    centered.y = -centered.y;
#endif
    return centered;
}

void main() {
    ivec2 dimensions = ivec2(uDimensions);
    ivec2 pixel = clampPixel(ivec2(gl_FragCoord.xy), dimensions);
    if (uRequireAccAlphaFlag
            && texelFetch(uAccAlphaFlags, pixel >> 1, 0).r == 0.0) {
        discard;
    }
    vec2 pixelCenter = vec2(pixel) + 0.5;
    vec2 inverseDimensions = 1.0 / uDimensions;

    float centerDepth = loadDepth(pixel, dimensions);
    float depth00 = loadDepth(pixel + ivec2(-1, -1), dimensions);
    float depth20 = loadDepth(pixel + ivec2(1, -1), dimensions);
    float depth02 = loadDepth(pixel + ivec2(-1, 1), dimensions);
    float depth22 = loadDepth(pixel + ivec2(1, 1), dimensions);
    float diagonalDepth = min(min(depth00, depth20), min(depth02, depth22));
    bool centerWins = centerDepth <= 1.025 * diagonalDepth;
    float selectedDepth = centerWins ? centerDepth : diagonalDepth;
    ivec2 selectedOffset = ivec2(0);
    if (!centerWins) {
        selectedOffset.x = min(depth00, depth02) == selectedDepth ? -1 : 1;
        selectedOffset.y = min(depth00, depth20) == selectedDepth ? -1 : 1;
    }

    // The isolated preview clears uncovered linear depth to zero, whereas the
    // retail frame supplies a valid sky/background depth. Keep those pixels
    // inert instead of projecting the zero-depth sentinel through the camera.
    if (selectedDepth <= 0.0) {
        FullDisocclusion = vec2(0.0);
        DepthMotion = vec2(0.0);
        return;
    }

    vec2 selectedUv = (pixelCenter + vec2(selectedOffset)) * inverseDimensions;
    vec2 velocity = loadVelocity(pixel + selectedOffset, dimensions);
    vec2 historyPixel = pixelCenter - velocity;
    vec2 historyUv = historyPixel * inverseDimensions;
    float outsideHistory = float(
        max(abs(0.5 - historyUv.x), abs(0.5 - historyUv.y)) > 0.5
    );

    if (!uHasHistory) {
        FullDisocclusion = vec2(1.0, 0.0);
        DepthMotion = vec2(selectedDepth, 0.0);
        return;
    }

    float historyConfidence = textureLod(
        uMotionBlurScatter, historyUv, 0.0
    ).r * clamp(2.0 - 0.125 * max(abs(velocity.x), abs(velocity.y)), 0.0, 1.0);
    float relativeDepth = ((selectedDepth - uDepthBase) * uDepthSlope)
        / max(selectedDepth, 0.000001);
    float localDepthReject = clamp(relativeDepth * 0.25 - 1.0, 0.0, 1.0);
    historyConfidence = max(historyConfidence, localDepthReject);

    vec3 viewPosition = reconstructViewPosition(selectedUv, selectedDepth);
    vec3 previousViewPosition = (uCurrentToPreviousView
        * vec4(viewPosition, 1.0)).xyz;
    float previousViewDepth = max(-previousViewPosition.z, 0.1);
    vec2 historyProjectionBase = (
        historyPixel + vec2(selectedOffset)
    ) * inverseDimensions - 0.5;
    vec2 previousProjection = projectedCenteredUv(
        uPreviousProjection, previousViewPosition
    );
    vec2 translationDiscrepancy = (
        historyProjectionBase - previousProjection
    ) * uDimensions;
    float translationOutside = clamp(
        max(abs(translationDiscrepancy.x), abs(translationDiscrepancy.y)) - 1.0,
        0.0, 1.0
    );

    vec3 rotatedViewPosition = uCurrentToPreviousRotation * viewPosition;
    vec2 rotatedProjection = projectedCenteredUv(
        uPreviousProjection, rotatedViewPosition
    );
    vec2 cameraDiscrepancy = (
        historyProjectionBase - rotatedProjection
    ) * uDimensions;
    float cameraMotion = uCameraMotionScale * length(cameraDiscrepancy);
    DepthMotion = vec2(selectedDepth, cameraMotion);

    vec2 scatterDelta = 1.5 * inverseDimensions;
    vec2 scatterTopLeft = textureLod(
        uHistoryDepthMotion, historyUv - scatterDelta, 0.0
    ).xy;
    vec2 scatterTopRight = textureLod(
        uHistoryDepthMotion,
        historyUv + vec2(scatterDelta.x, -scatterDelta.y), 0.0
    ).xy;
    vec2 scatterBottom = textureLod(
        uHistoryDepthMotion, historyUv + vec2(0.0, scatterDelta.y), 0.0
    ).xy;
    float scatterDepth = min(
        min(scatterTopLeft.x, scatterTopRight.x), scatterBottom.x
    );
    float scatterMotion = scatterTopLeft.x == scatterDepth
        ? scatterTopLeft.y
        : (scatterTopRight.x == scatterDepth
            ? scatterTopRight.y : scatterBottom.y);

    float rejectionRate = translationOutside != 0.0 ? 24.0 : 120.0;
    float translatedDepthAdjustment = (
        min(previousViewDepth, selectedDepth) - previousViewDepth
    ) * translationOutside;
    float depthEdgeLimit = centerDepth * 0.075;
    float depthEdge = 0.0;
    float edgeDelta = abs(centerDepth - depth00);
    depthEdge = max(depthEdge, edgeDelta < depthEdgeLimit ? edgeDelta : 0.0);
    edgeDelta = abs(centerDepth - depth20);
    depthEdge = max(depthEdge, edgeDelta < depthEdgeLimit ? edgeDelta : 0.0);
    edgeDelta = abs(centerDepth - depth02);
    depthEdge = max(depthEdge, edgeDelta < depthEdgeLimit ? edgeDelta : 0.0);
    edgeDelta = abs(centerDepth - depth22);
    depthEdge = max(depthEdge, edgeDelta < depthEdgeLimit ? edgeDelta : 0.0);

    float relativeHistoryDepth = (
        previousViewDepth - scatterDepth + translatedDepthAdjustment
    ) / max(scatterDepth, 0.000001);
    float depthReject = clamp(
        (relativeHistoryDepth - depthEdge) * rejectionRate - 1.0,
        0.0, 1.0
    );
    float motionConfidence = clamp(
        max(scatterMotion, cameraMotion) - uMotionThreshold, 0.0, 1.0
    );
    float smallCameraReject = clamp(
        cameraMotion * 0.125 - 0.5, 0.0, 1.0
    ) * 0.125;
    float baseReject = max(outsideHistory, smallCameraReject);
    float disocclusion = clamp(
        depthReject * motionConfidence + baseReject, 0.0, 1.0
    );
    FullDisocclusion = vec2(disocclusion, historyConfidence);
}
"""

TEMPORAL_ACCUM_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : require
#extension GL_ARB_shading_language_packing : require
/* HAIR_TEMPORAL */
in vec2 vTexCoord;
uniform sampler2D uCurrent;
uniform sampler2D uHistory;
uniform sampler2D uMotion;
uniform sampler2D uOpaqueMotion;
uniform sampler2D uFurMask;
uniform sampler2D uLinearDepth;
uniform sampler2D uAlphaMask;
uniform sampler2D uDisocclusion;
uniform usampler2D uStencil;
uniform float uHistoryWarmup;
uniform float uTemporalMinimumRejection;
uniform vec2 uHistoryJitterOffset;
uniform vec2 uTemporalFilterOffsetPixels;
uniform bool uHasFurMotion;
uniform bool uHasOpaqueMotion;
uniform bool uHasStencil;
uniform bool uHasTemporalHistory;
uniform bool uHasAlphaMask;
uniform bool uHasDisocclusion;
uniform float uNonopaqueStencilRejection;
uniform float uTemporalHdrScale;
uniform vec4 uTemporalDither;
layout(location = 0) out vec4 FragColor;

ivec2 clampTemporalPixel(ivec2 pixel, ivec2 dimensions) {
    return clamp(pixel, ivec2(0), dimensions - ivec2(1));
}

vec3 sampleCurrentColor(ivec2 pixel, ivec2 dimensions) {
    return texelFetch(uCurrent, clampTemporalPixel(pixel, dimensions), 0).rgb;
}

void main() {
    ivec2 dimensions = textureSize(uCurrent, 0);
    vec2 texel = 1.0 / vec2(dimensions);
    ivec2 currentPixel = clampTemporalPixel(
        ivec2(floor(vTexCoord * vec2(dimensions))), dimensions
    );
    vec2 currentUV = (vec2(currentPixel) + 0.5) * texel;
    vec4 current = vec4(
        sampleCurrentColor(currentPixel, dimensions),
        texelFetch(uCurrent, currentPixel, 0).a
    );
    vec2 historyPixel = vec2(currentPixel) + 0.5;
    vec2 motionPixels = vec2(0.0);
    float centerDepth = texelFetch(uLinearDepth, currentPixel, 0).r;
    float depth00 = texelFetch(
        uLinearDepth, clampTemporalPixel(currentPixel + ivec2(-1, -1), dimensions), 0
    ).r;
    float depth20 = texelFetch(
        uLinearDepth, clampTemporalPixel(currentPixel + ivec2(1, -1), dimensions), 0
    ).r;
    float depth02 = texelFetch(
        uLinearDepth, clampTemporalPixel(currentPixel + ivec2(-1, 1), dimensions), 0
    ).r;
    float depth22 = texelFetch(
        uLinearDepth, clampTemporalPixel(currentPixel + ivec2(1, 1), dimensions), 0
    ).r;
    float diagonalDepth = min(min(depth00, depth20), min(depth02, depth22));
    bool centerWins = centerDepth <= 1.025 * diagonalDepth;
    ivec2 velocityOffset = ivec2(0);
    if (!centerWins) {
        velocityOffset.x = min(depth00, depth02) == diagonalDepth ? -1 : 1;
        velocityOffset.y = min(depth00, depth20) == diagonalDepth ? -1 : 1;
    }
    ivec2 velocityPixel = clampTemporalPixel(
        currentPixel + velocityOffset, dimensions
    );
    bool useFurMotion = uHasFurMotion
        && texelFetch(uFurMask, velocityPixel, 0).a > 0.0;
    if (useFurMotion || uHasOpaqueMotion) {
        // Native velocity is current-minus-previous in top-left pixel space.
        // Convert its Y component to this lower-left texture convention.  The
        // preview resolves jitter onto a stable grid, so remove the previous
        // frame's raster offset as well.
        motionPixels = useFurMotion
            ? texelFetch(uMotion, velocityPixel, 0).xy
            : texelFetch(uOpaqueMotion, velocityPixel, 0).xy;
#ifdef RCRA_NATIVE_UPPER_LEFT
        vec2 motionToPreviousPixels = -motionPixels;
#else
        vec2 motionToPreviousPixels = vec2(-motionPixels.x, motionPixels.y);
#endif
        historyPixel += motionToPreviousPixels;
    }
    vec2 historyUV = historyPixel * texel + uHistoryJitterOffset;
    historyUV = clamp(historyUV, texel * 0.5, vec2(1.0) - texel * 0.5);
    // Native apply keeps its measured/history rejection separate from the
    // global response floor. The floor affects only the final history blend.
    float rejection = uHistoryWarmup;
    if (uHasDisocclusion) {
        vec2 disocclusion = texelFetch(uDisocclusion, currentPixel, 0).rg;
        rejection = max(rejection, disocclusion.r);
        rejection = max(rejection, 0.5 * disocclusion.g);
    }
    if (uHasAlphaMask) {
        float alphaMask = textureLod(uAlphaMask, currentUV, 0.0).r;
        rejection = max(rejection, 0.5 * alphaMask);
    }
    if (uHasStencil) {
        uint category = texelFetch(uStencil, velocityPixel, 0).r & 128u;
        rejection = max(
            rejection, float(category) * uNonopaqueStencilRejection
        );
    }
    float blendFactor = max(rejection, uTemporalMinimumRejection);
    vec3 historyRgb;
    if (!uHasTemporalHistory) {
        // D3D null-history reads are defined as zero. The OpenGL texture's
        // initial contents are undefined, so use an inert finite input while
        // rejection is one on a new or reset history.
        historyRgb = current.rgb;
    } else if (rejection <= 0.125
            && dot(motionPixels, motionPixels) >= 0.015625) {
        historyRgb = hairTemporalHistoryCatmullRom(
            uHistory, historyUV / texel, texel
        );
    } else {
        historyRgb = textureLod(uHistory, historyUV, 0.0).rgb;
    }

    vec3 samples[9];
    int sampleIndex = 0;
    for (int y = -1; y <= 1; ++y) {
        for (int x = -1; x <= 1; ++x) {
            vec3 sampleColor = sampleCurrentColor(
                currentPixel + ivec2(x, y), dimensions
            );
            samples[sampleIndex++] = hairTemporalRoundCurrentChroma(
                hairTemporalEncode(sampleColor, uTemporalHdrScale)
            );
        }
    }

    // The executable's cbuffer builder normalizes a Gaussian and separable
    // Catmull kernel, then mixes 80 percent toward Catmull. Rejection broadens
    // those weights toward the shader's fixed 3x3 limit.
    float broadening = clamp(rejection * 4.0 - 1.0, 0.0, 1.0);
    float weights[9];
    hairTemporalFilterWeights(uTemporalFilterOffsetPixels, weights);
    weights[0] = (0.05 - weights[0]) * broadening + weights[0];
    weights[1] = (0.10 - weights[1]) * broadening + weights[1];
    weights[2] = (0.05 - weights[2]) * broadening + weights[2];
    weights[3] = (0.10 - weights[3]) * broadening + weights[3];
    weights[4] = (0.40 - weights[4]) * broadening + weights[4];
    weights[5] = (0.10 - weights[5]) * broadening + weights[5];
    weights[6] = (0.05 - weights[6]) * broadening + weights[6];
    weights[7] = (0.10 - weights[7]) * broadening + weights[7];
    weights[8] = (0.05 - weights[8]) * broadening + weights[8];
    const int accumulationOrder[9] = int[9](1, 3, 4, 5, 7, 0, 2, 6, 8);
    int firstIndex = accumulationOrder[0];
    vec3 filteredCurrent = hairTemporalPremultiply(samples[firstIndex])
        * weights[firstIndex];
    for (int i = 1; i < 9; ++i) {
        int index = accumulationOrder[i];
        filteredCurrent += hairTemporalPremultiply(samples[index]) * weights[index];
    }
    filteredCurrent.x = max(filteredCurrent.x, HAIR_TEMPORAL_MIN_LUMA);
    vec3 currentRgb = hairTemporalDecodePremultiplied(filteredCurrent);

    vec3 neighborhoodMin = min(
        min(samples[1], samples[3]), min(samples[5], samples[7])
    );
    neighborhoodMin = min(neighborhoodMin, samples[4]);
    vec3 neighborhoodMax = max(
        max(samples[1], samples[3]), max(samples[5], samples[7])
    );
    neighborhoodMax = max(neighborhoodMax, samples[4]);
    vec3 fullMin = min(
        neighborhoodMin, min(min(samples[0], samples[2]), min(samples[6], samples[8]))
    );
    vec3 fullMax = max(
        neighborhoodMax, max(max(samples[0], samples[2]), max(samples[6], samples[8]))
    );
    float diagonalConfidence = clamp(1.0 - rejection * 20.0, 0.0, 1.0);
    neighborhoodMin = (fullMin - neighborhoodMin) * diagonalConfidence
        + neighborhoodMin;
    neighborhoodMax = (fullMax - neighborhoodMax) * diagonalConfidence
        + neighborhoodMax;

    vec3 history = hairTemporalEncode(historyRgb, uTemporalHdrScale);
    history = clamp(history, neighborhoodMin, neighborhoodMax);
    vec3 constrainedHistory = hairTemporalDecode(history);
    vec3 compressedResult = (currentRgb - constrainedHistory) * blendFactor
        + constrainedHistory;
    vec3 outputRgb = hairTemporalUndoHdrCompression(
        compressedResult, uTemporalHdrScale
    );
    ivec2 ditherPixel = currentPixel;
#ifndef RCRA_NATIVE_UPPER_LEFT
    ditherPixel.y = dimensions.y - 1 - ditherPixel.y;
#endif
    float noise = fract(
        (float(ditherPixel.x + 2 * ditherPixel.y) + uTemporalDither.z) * 0.2
    );
    noise += uTemporalDither.w * 0.2;
    outputRgb.rg *= 1.0 + noise * uTemporalDither.x;
    outputRgb.b *= 1.0 + noise * uTemporalDither.y;
    FragColor = vec4(outputRgb, current.a);
}
"""
TEMPORAL_ACCUM_FRAG = TEMPORAL_ACCUM_FRAG.replace(
    '/* HAIR_TEMPORAL */',
    (Path(__file__).resolve().parents[1] / 'core/hair_temporal.glsl')
    .read_text(encoding='utf-8'),
)

# Contact visibility is evaluated on the key-light contribution before denoise.
FUR_CONTACT_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : enable
uniform sampler2D uScene;
uniform sampler2D uFurKeyLight;
uniform sampler2D uFurGBuffer;
uniform sampler2D uFurNormalMask;
uniform vec2 uViewportSize;
uniform vec2 uProjectionScale;
uniform vec2 uProjectionOffset;
uniform mat3 uViewRotation;
uniform vec3 uWorldLightDir;
uniform float uTemporalIndex;
uniform float uTemporalPlusCycle;
uniform bool uFurContactEnabled;
layout(location = 0) out vec4 FragColor;
layout(location = 1) out vec4 BrightColor;
/* HAIR_LIGHTING_NOISE */
/* HAIR_SURFACE */
/* HAIR_CONTACT */
/* HAIR_COLOR_STORE */
float hairContactLoadDepth(ivec2 pixel) {
    ivec2 dimensions = textureSize(uFurGBuffer, 0);
    if (any(lessThan(pixel, ivec2(0))) || any(greaterThanEqual(pixel, dimensions))) return 0.0;
#ifndef RCRA_NATIVE_UPPER_LEFT
    pixel.y = dimensions.y - 1 - pixel.y;
#endif
    return texelFetch(uFurGBuffer, pixel, 0).a;
}
void main() {
    ivec2 center = ivec2(gl_FragCoord.xy);
    vec4 normalMask = texelFetch(uFurNormalMask, center, 0);
    if (normalMask.a <= 0.0) discard;
    vec4 indirect = texelFetch(uScene, center, 0);
    vec4 key = texelFetch(uFurKeyLight, center, 0);
    float visibility = indirect.a;
    if (visibility <= 0.0001) visibility = 0.0;
    if (uFurContactEnabled) {
        float depth = texelFetch(uFurGBuffer, center, 0).a;
#ifdef RCRA_NATIVE_UPPER_LEFT
        vec2 pixel = vec2(center);
#else
        vec2 pixel = vec2(center.x, int(uViewportSize.y) - 1 - center.y);
#endif
        vec2 inverseDimensions = 1.0 / uViewportSize;
        vec3 noise = hairLightingNoise(pixel, inverseDimensions, uTemporalIndex, uTemporalPlusCycle);
        vec3 light = normalize(uWorldLightDir);
        vec3 viewLight = (uViewRotation * light) * vec3(1.0, -1.0, -1.0);
#ifdef GL_ARB_gpu_shader5
        float radius = fma(key.a, uintBitsToFloat(0x39041aa4u), uintBitsToFloat(0x3b03126fu));
#else
        float radius = key.a * uintBitsToFloat(0x39041aa4u) + uintBitsToFloat(0x3b03126fu);
#endif
        float contact = hairContactVisibility(pixel, depth, normalMask.xyz, light, viewLight,
            inverseDimensions, vec4(2.0 / uProjectionScale, (uProjectionOffset - 1.0) / uProjectionScale),
            vec2(1.0, 0.0), vec4(uProjectionScale * 0.5, (1.0 - uProjectionOffset) * 0.5),
            uViewportSize, noise.xz, radius);
        visibility = min(visibility, contact);
    }
    FragColor = vec4(hairStoreColor(indirect.rgb + key.rgb * visibility), 1.0);
    BrightColor = vec4(0.0);
}
"""
for _marker, _filename in (
    ('/* HAIR_LIGHTING_NOISE */', 'hair_lighting_noise.glsl'),
    ('/* HAIR_SURFACE */', 'hair_surface.glsl'),
    ('/* HAIR_CONTACT */', 'hair_contact_shadow.glsl'),
    ('/* HAIR_COLOR_STORE */', 'hair_color_store.glsl'),
):
    FUR_CONTACT_FRAG = FUR_CONTACT_FRAG.replace(
        _marker, (Path(__file__).resolve().parents[1] / 'core' / _filename).read_text(encoding='utf-8'),
    )

# Shared captured HairDenoise geometry and gather kernel. The preview derives
# Hair tile occupancy from its fur buffer; its lighting mask remains the
# isolated renderer's input until full deferred Hair lighting is connected.
FUR_DENOISE_FRAG = """
#version 330 core
#extension GL_ARB_gpu_shader5 : enable
in vec2 vTexCoord;
uniform sampler2D uScene;
uniform sampler2D uFurGBuffer;
uniform sampler2D uFurNormalMask;
uniform sampler2D uSceneDenoiseMask;
uniform usampler2D uGatherAddress;
uniform bool uHasGatherAddress;
uniform bool uHasSceneDenoiseMask;
uniform bool uHasSceneProjection;
uniform vec4 uSceneScreenToView;
uniform vec4 uSceneViewToScreen;
uniform mat3 uViewRotation;
uniform vec2 uProjectionScale;
uniform vec2 uProjectionOffset;
uniform vec2 uViewportSize;
uniform float uTemporalIndex;
uniform float uTemporalPlusCycle;
out vec4 FragColor;

/* HAIR_LIGHTING_NOISE */
/* HAIR_SURFACE */
/* HAIR_DENOISE */
/* HAIR_COLOR_STORE */

vec4 previewDenoiseGather(sampler2D source, vec2 d3dUV, int component) {
#ifdef GL_ARB_gpu_shader5
    if (uHasGatherAddress) {
        // Let the sampler choose addresses in native top-left coordinates.
        // Flipping UV before the gather changes subtexel boundary rounding.
        uvec4 addresses = textureGather(uGatherAddress, d3dUV, 0);
        ivec2 dimensions = textureSize(source, 0);
        vec4 values;
        for (int i = 0; i < 4; ++i) {
            ivec2 pixel = ivec2(addresses[i] % uint(dimensions.x),
                                addresses[i] / uint(dimensions.x));
#ifndef RCRA_NATIVE_UPPER_LEFT
            values[i] = texelFetch(source,
                ivec2(pixel.x, dimensions.y - 1 - pixel.y), 0)[component];
#else
            values[i] = texelFetch(source, pixel, 0)[component];
#endif
        }
        return values;
    }
#ifdef RCRA_NATIVE_UPPER_LEFT
    // Use explicit native addresses here. This avoids depending on OpenGL's
    // implementation-facing textureGather component order during migration.
    ivec2 dimensions = textureSize(source, 0);
    ivec2 base = ivec2(floor(d3dUV * vec2(dimensions) - 0.5));
    ivec2 offsets[4] = ivec2[](ivec2(0, 1), ivec2(1, 1), ivec2(1, 0), ivec2(0, 0));
    vec4 values;
    for (int i = 0; i < 4; ++i) {
        ivec2 pixel = clamp(base + offsets[i], ivec2(0), dimensions - 1);
        values[i] = texelFetch(source, pixel, 0)[component];
    }
    return values;
#else
    vec2 uv = vec2(d3dUV.x, 1.0 - d3dUV.y);
    // Vertical texture orientation reverses the native gather component order.
    if (component == 0) return textureGather(source, uv, 0).wzyx;
    if (component == 1) return textureGather(source, uv, 1).wzyx;
    if (component == 2) return textureGather(source, uv, 2).wzyx;
    return textureGather(source, uv, 3).wzyx;
#endif
#else
    ivec2 dimensions = textureSize(source, 0);
    ivec2 base = ivec2(floor(d3dUV * vec2(dimensions) - 0.5));
    ivec2 offsets[4] = ivec2[](ivec2(0, 1), ivec2(1, 1), ivec2(1, 0), ivec2(0, 0));
    vec4 values;
    for (int i = 0; i < 4; ++i) {
        ivec2 pixel = clamp(base + offsets[i], ivec2(0), dimensions - 1);
#ifndef RCRA_NATIVE_UPPER_LEFT
        pixel.y = dimensions.y - 1 - pixel.y;
#endif
        values[i] = texelFetch(source, pixel, 0)[component];
    }
    return values;
#endif
}

vec4 hairDenoiseGatherDepth(vec2 uv) {
    vec4 depth = previewDenoiseGather(uFurGBuffer, uv, 3);
    return vec4(hairDenoiseHalfDepth(depth.x), hairDenoiseHalfDepth(depth.y),
                hairDenoiseHalfDepth(depth.z), hairDenoiseHalfDepth(depth.w));
}

vec4 hairDenoiseGatherMask(vec2 uv) {
    vec4 hair = previewDenoiseGather(uFurNormalMask, uv, 3);
    return uHasSceneDenoiseMask
        ? max(hair, previewDenoiseGather(uSceneDenoiseMask, uv, 0)) : hair;
}

vec4 hairDenoiseGatherColor(vec2 uv, int component) {
    return previewDenoiseGather(uScene, uv, component);
}

bool hairDenoiseTileActive(vec2 uv) {
    ivec2 dimensions = textureSize(uFurGBuffer, 0);
    ivec2 tile = ivec2(uv * uViewportSize) >> 3;
    if (any(lessThan(tile, ivec2(0)))) return false;
    ivec2 origin = tile * 8;
    if (any(greaterThanEqual(origin, dimensions))) return false;
    // Equivalent to the Hair bit for this preview's isolated material buffer.
    // Return early for occupied tiles; masked gather weights handle boundaries.
    for (int y = 0; y < 8; ++y) {
        for (int x = 0; x < 8; ++x) {
            ivec2 pixel = origin + ivec2(x, y);
            if (any(greaterThanEqual(pixel, dimensions))) continue;
#ifndef RCRA_NATIVE_UPPER_LEFT
            pixel.y = dimensions.y - 1 - pixel.y;
#endif
            if (texelFetch(uFurNormalMask, pixel, 0).a > 0.0) return true;
        }
    }
    return false;
}

void main() {
    ivec2 centerPixel = ivec2(gl_FragCoord.xy);
    vec4 fur = texelFetch(uFurGBuffer, centerPixel, 0);
    vec4 normalMask = texelFetch(uFurNormalMask, centerPixel, 0);
    if (normalMask.a <= 0.0) discard;
    vec4 centerColor = texelFetch(uScene, centerPixel, 0);
    vec3 normal = normalMask.xyz;
    vec3 strand = fur.xyz;
    float depth = hairDenoiseHalfDepth(fur.a);
#ifdef RCRA_NATIVE_UPPER_LEFT
    vec2 pixel = vec2(centerPixel);
#else
    vec2 pixel = vec2(centerPixel.x, int(uViewportSize.y) - 1 - centerPixel.y);
#endif
    vec2 inverseDimensions = 1.0 / uViewportSize;
    float phase = hairScreenPhase(pixel, inverseDimensions, uTemporalIndex, uTemporalPlusCycle);
    vec3 viewTangent = (uViewRotation * strand) * vec3(1.0, -1.0, -1.0);
    vec4 screenToView = vec4(2.0 / uProjectionScale, (uProjectionOffset - 1.0) / uProjectionScale);
    vec4 viewToScreen = vec4(uProjectionScale * 0.5, (1.0 - uProjectionOffset) * 0.5);
    if (uHasSceneProjection) {
        screenToView = uSceneScreenToView;
        viewToScreen = uSceneViewToScreen;
    }
    HairDenoiseRay ray = hairDenoiseBuildRay(
        pixel, depth, normal, strand, viewTangent, inverseDimensions,
        screenToView, vec2(1.0, 0.0), viewToScreen, phase
    );
    FragColor = vec4(hairStoreColor(hairDenoiseFilter(ray, centerColor.rgb, depth)), centerColor.a);
}
"""

for _marker, _filename in (
    ('/* HAIR_LIGHTING_NOISE */', 'hair_lighting_noise.glsl'),
    ('/* HAIR_SURFACE */', 'hair_surface.glsl'),
    ('/* HAIR_DENOISE */', 'hair_denoise.glsl'),
    ('/* HAIR_COLOR_STORE */', 'hair_color_store.glsl'),
):
    FUR_DENOISE_FRAG = FUR_DENOISE_FRAG.replace(
        _marker,
        (Path(__file__).resolve().parents[1] / 'core' / _filename)
        .read_text(encoding='utf-8'),
    )

FUR_OIT_COMPOSITE_FRAG = """
#version 330 core
in vec2 vTexCoord;
uniform sampler2D uFurAccum;
uniform sampler2D uFurReveal;
out vec4 FragColor;

void main() {
    vec4 accumulation = texture(uFurAccum, vTexCoord);
    float alpha = 1.0 - texture(uFurReveal, vTexCoord).r;
    if (alpha <= 0.0001) {
        discard;
    }
    vec3 averageColor = accumulation.rgb / max(accumulation.a, 0.00001);
    FragColor = vec4(averageColor * alpha, alpha);
}
"""


# ── Arcball Camera ─────────────────────────────────────────────────────────────

class ArcballCamera:
    def __init__(self):
        self.yaw:    float  = 30.0
        self.pitch:  float  = 25.0
        self.dist:   float  = 5.0
        self.target: np.ndarray = np.zeros(3, dtype=np.float32)

    def view_matrix(self) -> np.ndarray:
        y = math.radians(self.yaw)
        p = math.radians(self.pitch)
        cx, cy, cz = math.cos(y), math.sin(p), math.sin(y)
        eye = self.target + np.array([
            cx * math.cos(p),
            cy,
            cz * math.cos(p),
        ], dtype=np.float32) * self.dist
        return _look_at(eye, self.target, np.array([0, 1, 0], np.float32))

    def eye_position(self) -> np.ndarray:
        y = math.radians(self.yaw)
        p = math.radians(self.pitch)
        return self.target + np.array([
            math.cos(y) * math.cos(p),
            math.sin(p),
            math.sin(y) * math.cos(p),
        ], dtype=np.float32) * self.dist

    def view_direction(self) -> np.ndarray:
        """Normalized direction from the camera eye toward the orbit pivot."""
        direction = self.target - self.eye_position()
        length = float(np.linalg.norm(direction))
        if length < 1e-8:
            return np.array([0.0, 0.0, -1.0], dtype=np.float32)
        return direction / length

    def view_basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return Maya-style camera right, up, and forward vectors."""
        forward = self.view_direction()
        world_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        right = np.cross(forward, world_up)
        right_length = float(np.linalg.norm(right))
        if right_length < 1e-8:
            right = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        else:
            right /= right_length
        up = np.cross(right, forward)
        up /= max(float(np.linalg.norm(up)), 1e-8)
        return right, up, forward

    def orbit(self, dx: float, dy: float):
        # Autodesk/Maya-style turntable tumble around a stable target pivot.
        self.yaw += dx * 0.32
        self.pitch = max(-89.0, min(89.0, self.pitch - dy * 0.32))

    def pan(self, dx: float, dy: float):
        right, up, _ = self.view_basis()
        speed = self.dist * 0.001
        self.target += (-right * dx + up * dy) * speed

    def dolly(self, pixels: float):
        """Maya-style drag dolly: positive motion moves toward the pivot."""
        self.dist = max(0.0001, self.dist * math.exp(-pixels * 0.01))

    def zoom(self, delta: float):
        # Exponential scaling stays stable for both tiny and enormous models.
        self.dist = max(0.0001, self.dist * math.exp(-delta * 0.15))

    def frame_aabb(self, mn: np.ndarray, mx: np.ndarray):
        self.target = (mn + mx) * 0.5
        diag = np.linalg.norm(mx - mn)
        self.dist = float(diag) * 1.2 if diag > 0 else 5.0


def _perspective_clip_planes(camera: ArcballCamera,
                             minimum: np.ndarray,
                             maximum: np.ndarray) -> tuple[float, float]:
    """Fit perspective clip planes to the model AABB with depth padding."""
    eye = camera.eye_position()
    forward = camera.view_direction()
    corners = np.array([
        [x, y, z]
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    ], dtype=np.float32)
    depths = (corners - eye) @ forward
    diagonal = float(np.linalg.norm(maximum - minimum))
    padding = max(diagonal * 0.08, 0.01)
    minimum_near = max(diagonal * 1e-5, 0.0001)
    near = max(minimum_near, float(depths.min()) - padding)
    far = max(float(depths.max()) + padding, near + max(diagonal, 1.0))
    return near, far


def _halton(index: int, base: int) -> float:
    """Return one deterministic low-discrepancy sample in [0, 1)."""
    value = 0.0
    fraction = 1.0
    index = max(0, int(index))
    while index:
        fraction /= base
        value += fraction * (index % base)
        index //= base
    return value


def _temporal_current_sample_offset(
    jitter_pixels: tuple[float, float],
    framebuffer_size: tuple[int, int],
    *, upper_left: bool = False,
) -> tuple[float, float]:
    """Undo projection jitter when sampling the current temporal-AA frame.

    Adding ``2*jitter/size`` to this OpenGL projection's [0, 2]/[1, 2]
    entries moves rasterized geometry by ``-jitter`` pixels because visible
    view-space Z is negative and clip W is ``-Z``. Sampling the current frame
    at that same negative pixel offset maps it onto history's stable grid.
    """
    width = max(int(framebuffer_size[0]), 1)
    height = max(int(framebuffer_size[1]), 1)
    y_sign = 1.0 if upper_left else -1.0
    return (
        -float(jitter_pixels[0]) / float(width),
        y_sign * float(jitter_pixels[1]) / float(height),
    )


def _temporal_history_jitter_offset(
    current_jitter_pixels: tuple[float, float],
    previous_jitter_pixels: tuple[float, float],
    framebuffer_size: tuple[int, int],
    *, upper_left: bool = False,
) -> tuple[float, float]:
    """Map native jittered velocity onto the preview's stable history grid."""
    current = _temporal_current_sample_offset(
        current_jitter_pixels, framebuffer_size, upper_left=upper_left,
    )
    previous = _temporal_current_sample_offset(
        previous_jitter_pixels, framebuffer_size, upper_left=upper_left,
    )
    return current[0] - previous[0], current[1] - previous[1]


def _temporal_filter_offset_pixels(
    jitter_pixels: tuple[float, float], *, upper_left: bool = False,
) -> tuple[float, float]:
    """Map projection jitter to the recovered 3x3 filter's pixel frame."""
    return (
        float(jitter_pixels[0]),
        -float(jitter_pixels[1]) if upper_left else float(jitter_pixels[1]),
    )


# ── GPU Mesh ──────────────────────────────────────────────────────────────────

class GpuSubMesh:
    def __init__(self):
        self.vao: int = 0
        self.vbo: int = 0
        self.ebo: int = 0
        self._pose_vertices = None
        self._pose_history_dirty = False
        self.index_count: int = 0
        self.index_type: int = 0   # GL_UNSIGNED_SHORT or GL_UNSIGNED_INT
        self.color: tuple = (0.75, 0.75, 0.75)
        self.texture_id:    int = 0   # OpenGL texture object, 0 = no texture
        self.normal_tex_id: int = 0   # OpenGL normal map texture, 0 = none
        self.specular_tex_id: int = 0
        self.fur_control_tex_id: int = 0
        self.fur_length: float = 0.03
        self.fur_density: float = 16.0
        self.fur_offset_scale: float = 0.0
        self.fur_layer_count: int = 0
        self.fur_lod_reduction: float = 0.0
        self.fur_gloss_scale: float = 1.0
        self.fur_specular_scale: float = 1.0
        self.fur_transmittance_scale: float = 0.0
        self.fur_wind_turbulence: float = 0.0
        self.fur_wind_radius: float = 0.0
        self.emissive_tex_id: int = 0
        self.effect_mask_tex_id: int = 0
        self.noise_tex_id: int = 0
        self.retail_lava_color_a_tex_id: int = 0
        self.retail_lava_color_b_tex_id: int = 0
        self.retail_lava_normal_a_tex_id: int = 0
        self.retail_lava_normal_b_tex_id: int = 0
        self.retail_lava_noise_tex_id: int = 0
        self.retail_lava_mask_a_tex_id: int = 0
        self.retail_lava_mask_b_tex_id: int = 0
        self.material_index: int = -1  # model material index for texture lookup
        self.material_name: str = ''
        self.is_lava: bool = False
        self.is_lava_rock: bool = False
        self.is_lavafall: bool = False
        self.is_retail_blizar_lava: bool = False
        self.lava_flow_a: tuple[float, float] = (0.024, 0.011)
        self.lava_flow_b: tuple[float, float] = (-0.017, 0.029)
        self.is_alpha_cutout: bool = False
        self.is_fur: bool = False     # fur/composite shell mesh — can be toggled
        self.is_fur_surface: bool = False
        self.is_composite_shell: bool = False

    def upload(self, positions: np.ndarray, normals: np.ndarray,
               uvs: np.ndarray, indices: np.ndarray,
               authored_tangents: np.ndarray | None = None,
               decode_corrections: np.ndarray | None = None):
        """Upload pre-extracted numpy arrays to the GPU."""
        n = len(positions)
        if n == 0 or indices is None or len(indices) == 0:
            return

        nrm = normals if normals is not None and len(normals) == n \
              else np.zeros((n, 3), np.float32)
        uv  = uvs if uvs is not None and len(uvs) == n \
              else np.zeros((n, 2), np.float32)

        if (authored_tangents is not None
                and authored_tangents.shape == (n, 4)
                and np.isfinite(authored_tangents).all()):
            tangents = authored_tangents.astype(np.float32)
        else:
            tangents = _mesh_tangents(positions, nrm, uv, indices)
        corrections = decode_corrections \
            if (decode_corrections is not None
                and decode_corrections.shape == (n, 1)
                and np.isfinite(decode_corrections).all()) \
            else np.zeros((n, 1), dtype=np.float32)
        interleaved = np.concatenate([
            positions.astype(np.float32),
            nrm.astype(np.float32),
            uv.astype(np.float32),
            tangents,
            corrections.astype(np.float32),
            positions.astype(np.float32),
        ], axis=1).astype(np.float32)
        self._pose_vertices = interleaved.copy()

        self.vao = glGenVertexArrays(1)
        self.vbo = glGenBuffers(1)
        self.ebo = glGenBuffers(1)

        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, interleaved.nbytes, interleaved, GL_STATIC_DRAW)

        stride = 16 * 4
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(24))
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(3, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(32))
        glEnableVertexAttribArray(3)
        glVertexAttribPointer(4, 1, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(48))
        glEnableVertexAttribArray(4)
        glVertexAttribPointer(5, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(52))
        glEnableVertexAttribArray(5)

        if indices.max() < 65536:
            idx = indices.astype(np.uint16)
            self.index_type = GL_UNSIGNED_SHORT
        else:
            idx = indices.astype(np.uint32)
            self.index_type = GL_UNSIGNED_INT

        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, idx.nbytes, idx, GL_STATIC_DRAW)
        self.index_count = len(idx)
        glBindVertexArray(0)

    def draw(self):
        if self.vao and self.index_count:
            glBindVertexArray(self.vao)
            glDrawElements(GL_TRIANGLES, self.index_count, self.index_type, None)
            glBindVertexArray(0)

    def draw_instanced(self, instance_count: int):
        if self.vao and self.index_count and instance_count > 0:
            glBindVertexArray(self.vao)
            glDrawElementsInstanced(
                GL_TRIANGLES, self.index_count, self.index_type, None,
                int(instance_count),
            )
            glBindVertexArray(0)

    def update_pose(self, positions, normals, tangents, *, previous_positions=None):
        """Update a deformed mesh on the current GL context, preserving its topology.

        Inputs use this submesh's existing vertex order. The producer supplies
        current deformed normals/tangents; previous positions default to the
        last rendered pose. This does not decode animation clips or skin weights.
        """
        if self._pose_vertices is None:
            raise ValueError('Upload the mesh before setting a pose')
        n = len(self._pose_vertices)
        arrays = [np.asarray(x, dtype=np.float32) for x in (positions, normals, tangents)]
        previous = (self._pose_vertices[:, :3].copy() if previous_positions is None
                    else np.asarray(previous_positions, dtype=np.float32))
        for array, shape in zip([*arrays, previous], [(n, 3), (n, 3), (n, 4), (n, 3)]):
            if array.shape != shape or not np.isfinite(array).all():
                raise ValueError('Pose streams must be finite and preserve vertex count')
        updated = self._pose_vertices.copy()
        updated[:, :3], updated[:, 3:6], updated[:, 8:12] = arrays
        updated[:, 13:16] = previous
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, updated.nbytes, updated)
        self._pose_vertices = updated
        self._pose_history_dirty = True

    def settle_pose_history(self):
        """After a rendered frame, stationary repaint motion must return to zero."""
        if self._pose_history_dirty:
            self._pose_vertices[:, 13:16] = self._pose_vertices[:, :3]
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
            glBufferSubData(GL_ARRAY_BUFFER, 0, self._pose_vertices.nbytes, self._pose_vertices)
            self._pose_history_dirty = False

    def free(self):
        if self.vao:
            glDeleteVertexArrays(1, [self.vao])
            glDeleteBuffers(1, [self.vbo])
            glDeleteBuffers(1, [self.ebo])
            self.vao = 0
        self._pose_vertices = None
        self._pose_history_dirty = False
        if self.texture_id:
            glDeleteTextures(1, [self.texture_id])
            self.texture_id = 0
        if self.normal_tex_id:
            glDeleteTextures(1, [self.normal_tex_id])
            self.normal_tex_id = 0
        for attr in (
            'emissive_tex_id', 'effect_mask_tex_id', 'noise_tex_id',
            'retail_lava_color_a_tex_id', 'retail_lava_color_b_tex_id',
            'retail_lava_normal_a_tex_id', 'retail_lava_normal_b_tex_id',
            'retail_lava_noise_tex_id',
            'retail_lava_mask_a_tex_id', 'retail_lava_mask_b_tex_id',
            'fur_control_tex_id', 'specular_tex_id',
        ):
            tex_id = getattr(self, attr, 0)
            if tex_id:
                glDeleteTextures(1, [tex_id])
                setattr(self, attr, 0)


class GpuModelStrandGroup:
    """One capture-derived ModelStrand group resident on the GPU."""

    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        self.profile = MODEL_STRAND_PROFILES[profile_name]
        self.vao = 0
        self.vbo = 0
        self.ebo = 0
        self.index_count = 0
        self.diffuse_texture = 0
        self.thickness_texture = 0
        self.summary = {}

    @staticmethod
    def _upload_png(path: Path, *, srgb: bool) -> int:
        image = QImage(str(path))
        if image.isNull():
            raise RuntimeError(f"Could not read ModelStrand texture {path}")
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        width, height = image.width(), image.height()
        bits = image.bits()
        bits.setsize(image.sizeInBytes())
        rgba = bytes(bits)
        texture = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_SRGB8_ALPHA8 if srgb else GL_RGBA8,
            width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba,
        )
        glGenerateMipmap(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, 0)
        return texture

    def upload(self, *, captured_wind: bool = False):
        vertices, indices, self.summary = build_model_strand_group(
            self.profile_name, captured_wind=captured_wind,
        )
        self.vao = int(glGenVertexArrays(1))
        self.vbo = int(glGenBuffers(1))
        self.ebo = int(glGenBuffers(1))
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        stride = 22 * 4
        for location, size, offset in (
            (0, 3, 0), (1, 3, 12), (2, 3, 24), (3, 3, 36),
            (4, 2, 48), (5, 4, 56), (6, 4, 72),
        ):
            glVertexAttribPointer(
                location, size, GL_FLOAT, GL_FALSE, stride,
                ctypes.c_void_p(offset),
            )
            glEnableVertexAttribArray(location)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)
        self.index_count = int(len(indices))
        glBindVertexArray(0)
        fixture_root = model_strand_fixture_directory()
        if self.profile_name == 'tail':
            diffuse = fixture_root / 'tail-DiffuseTexture.png'
            thickness = fixture_root / 'tail-StrandThicknessTexture.png'
        else:
            diffuse = fixture_root / 'DiffuseTexture.png'
            thickness = fixture_root / 'StrandThicknessTexture.png'
        self.diffuse_texture = self._upload_png(diffuse, srgb=True)
        self.thickness_texture = self._upload_png(thickness, srgb=False)

    def draw(self):
        if self.vao and self.index_count:
            glBindVertexArray(self.vao)
            glEnable(GL_PRIMITIVE_RESTART_FIXED_INDEX)
            glDrawElements(GL_TRIANGLE_STRIP, self.index_count, GL_UNSIGNED_INT, None)
            glDisable(GL_PRIMITIVE_RESTART_FIXED_INDEX)

    def free(self):
        if self.vao:
            glDeleteVertexArrays(1, [self.vao])
            glDeleteBuffers(1, [self.vbo])
            glDeleteBuffers(1, [self.ebo])
            self.vao = self.vbo = self.ebo = 0
        textures = [value for value in (self.diffuse_texture, self.thickness_texture) if value]
        if textures:
            glDeleteTextures(len(textures), textures)
        self.diffuse_texture = self.thickness_texture = 0


# ── Viewport Widget ───────────────────────────────────────────────────────────

import ctypes

class Viewport3D(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera     = ArcballCamera()
        self._gpu_meshes: list[GpuSubMesh] = []
        self._shader_prog: int = 0
        self._native_raster_active = False
        self._fur_shader_prog: int = 0
        self._fur_material_prog: int = 0
        self._model_strand_material_prog: int = 0
        self._gpu_model_strands: list[GpuModelStrandGroup] = []
        self._fur_decode_prog: int = 0
        self._fur_lighting_prog: int = 0
        self._fur_layer_texture: int = 0
        self._fur_environment_texture: int = 0
        self._fur_brdf_texture: int = 0
        self._pending_fur_environment = None
        self._pending_fur_scene = None
        self._fur_scene_gpu = None
        self._fur_scene_program = 0
        self._fur_scene_view = None
        self._grid_prog:   int = 0
        self._blur_prog:   int = 0
        self._composite_prog: int = 0
        self._temporal_accum_prog: int = 0
        self._temporal_disocclusion_prog: int = 0
        self._temporal_linear_depth_prog: int = 0
        self._temporal_half_base_prog: int = 0
        self._temporal_alpha_mask_prog: int = 0
        self._temporal_alpha_half_prog: int = 0
        self._motion_blur_downsample_prog: int = 0
        self._motion_blur_neighborhood_half_prog: int = 0
        self._motion_blur_neighborhood_quarter_prog: int = 0
        self._motion_blur_gather_neighborhood_prog: int = 0
        self._motion_blur_scatter_prog: int = 0
        self._fur_denoise_prog: int = 0
        self._fur_contact_prog: int = 0
        self._fur_deferred_active = False
        self._fur_oit_composite_prog: int = 0
        self._fur_oit_supported: bool = False
        self._grid_vao:    int = 0
        self._grid_vbo:    int = 0
        self._grid_count:  int = 0
        self._last_pos:    Optional[QPoint] = None
        self._mouse_mode:  Optional[str] = None
        self._drag_button = Qt.MouseButton.NoButton
        self._dragging:    bool = False
        self._wireframe:   bool = False
        self._show_fur:    bool = True    # toggle fur/composite shell meshes
        self._pending_model  = None
        self._pending_poses = {}
        self._reset_pose_history = False
        self._redraw_pending = False
        self._grid_y         = 0.0
        self._grid_fade_r    = 2.0
        self._cached_material_textures: dict = {}   # persists across LOD switches
        self._uploaded_texture_signatures: dict = {}
        self._max_texture_anisotropy = 1.0
        self._animated_materials = False
        self._bloom_enabled = True
        self._bloom_supported = True
        self._hdr_fbo = 0
        self._hdr_color_buffers: list[int] = []
        self._fur_material_fbo = 0
        self._fur_material_textures = []
        self._fur_decode_fbo = 0
        self._fur_lighting_fbo = 0
        self._fur_indirect_texture = 0
        self._scene_linear_depth_texture = 0
        self._scene_velocity_texture = 0
        self._scene_stencil_texture = 0
        self._fur_gbuffer_texture = 0
        self._fur_normal_texture = 0
        self._fur_denoise_fbo = 0
        self._fur_key_texture = 0
        self._fur_contact_fbo = 0
        self._fur_contact_texture = 0
        self._fur_denoise_texture = 0
        self._fur_gather_address_texture = 0
        # Native contact marches reciprocal ray depth against linear scene depth.
        self._fur_contact_enabled = True
        self._fur_denoise_enabled = True
        # MaterialFur wetness and ModelFur wind strength are runtime state in
        # retail, not constants in the static material payload.
        self._fur_wetness = 0.0
        self._preview_light_direction = (0.6, 1.0, 0.8)
        self._fur_wind_strength = 0.0
        self._fur_wind_vector = np.asarray((1.0, 0.0, 0.0), dtype=np.float32)
        self._fur_wind_object_phase = 0.0
        self._fur_wind_time_override: Optional[float] = None
        self._fur_wind_epoch = time.monotonic()
        self._fur_debug_reverse_layer: Optional[int] = None
        self._fur_oit_textures: list[int] = []
        self._fur_scene_depth_texture = 0
        self._fur_depth_snapshot_ready = False
        self._hdr_depth_rbo = 0
        self._pingpong_fbos: list[int] = []
        self._pingpong_textures: list[int] = []
        self._temporal_fbos: list[int] = []
        self._temporal_textures: list[int] = []
        self._temporal_depth_textures: list[int] = []
        self._temporal_disocclusion_fbos: list[int] = []
        self._temporal_disocclusion_textures: list[int] = []
        self._temporal_disocclusion_valid = [False, False]
        self._temporal_linear_depth_fbo = 0
        self._temporal_linear_depth_textures: list[int] = []
        self._temporal_half_fbo = 0
        self._temporal_half_textures: list[int] = []
        self._temporal_alpha_mask_fbo = 0
        self._temporal_alpha_mask_texture = 0
        self._temporal_alpha_valid = False
        self._motion_blur_downsample_fbo = 0
        self._motion_blur_depth_velocity_texture = 0
        self._motion_blur_half_velocity_texture = 0
        self._motion_blur_neighborhood_fbos: list[int] = []
        self._motion_blur_neighborhood_textures: list[int] = []
        self._motion_blur_scatter_fbos: list[int] = []
        self._motion_blur_scatter_textures: list[int] = []
        self._motion_blur_scatter_valid = [False, False]
        self._motion_blur_sizes = ((0, 0), (0, 0), (0, 0))
        self._temporal_sample_count = 0
        self._temporal_signature = None
        # These are the three dynamic producers for native TAA m_Misc.xyz.
        # None selects the recovered executable fallback for response/HDR.
        self._temporal_nonopaque_response: Optional[float] = None
        self._temporal_conditional_floor = False
        self._temporal_hdr_reference: Optional[float] = None
        self._current_temporal_jitter = (0.0, 0.0)
        self._previous_fur_mvp: Optional[np.ndarray] = None
        self._previous_fur_projection: Optional[np.ndarray] = None
        self._previous_fur_view: Optional[np.ndarray] = None
        self._previous_fur_wind_time: Optional[float] = None
        self._previous_fur_jitter: Optional[tuple[float, float]] = None
        self._fur_motion_signature = None
        self._display_scene_texture = 0
        self._current_scene_texture = 0
        self._current_scene_fbo = 0
        self._bloom_size = (0, 0)
        # Load persisted control settings
        self._controls: dict = load_controls()

        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.WheelFocus)
        self.setToolTip(AUTODESK_CONTROL_TOOLTIP)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)

    def _framebuffer_size(self) -> tuple[int, int]:
        """Return the QOpenGLWidget backing framebuffer size in physical pixels."""
        return _scaled_framebuffer_size(
            self.width(), self.height(), self.devicePixelRatioF(),
        )

    def _redraw(self):
        """Request a repaint through Qt's paint system."""
        self.update()

    def _start_render_loop(self):
        if not hasattr(self, '_render_timer'):
            from PyQt6.QtCore import QTimer
            self._render_timer = QTimer(self)
            self._render_timer.timeout.connect(self.update)
        if not self._render_timer.isActive():
            self._render_timer.start(16)  # 60fps

    def _stop_render_loop(self):
        if self._animated_materials or self._fur_wind_strength > 0.0:
            return
        if hasattr(self, '_render_timer') and self._render_timer.isActive():
            self._render_timer.stop()

    # ── Mesh Loading ──────────────────────────────────────────────────────────

    def load_mesh(self, model: ModelAsset):
        """Queue a model for GPU upload — actual upload happens in paintGL."""
        self._fur_scene_view = None
        self._pending_model  = model
        self._pending_poses = {}
        self._active_lod     = 0   # reset to LOD0 on new model load
        self._cached_material_textures = {}   # clear texture cache for new model
        self._pending_textures = {}
        self._uploaded_texture_signatures = {}
        if hasattr(self, '_cam_logged'):
            del self._cam_logged
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(10, self._trigger_repaint)

    def set_deformed_pose(self, poses: dict):
        """Queue per-GPU-submesh (positions, normals, tangents) on the UI thread.

        Arrays must use the uploaded submesh vertex order. Multiple queued
        updates coalesce; history refers to the last rendered pose, not an
        intermediate queued pose. Native animation decoding is a separate producer.
        """
        if self._pending_model is not None:
            raise ValueError('Wait for the pending model upload before setting a pose')
        pending = {}
        for index, streams in poses.items():
            if not isinstance(index, int) or not 0 <= index < len(self._gpu_meshes):
                raise ValueError('Invalid uploaded submesh index')
            n = len(self._gpu_meshes[index]._pose_vertices)
            if len(streams) != 3:
                raise ValueError('A pose requires positions, normals and tangents')
            arrays = tuple(np.array(x, dtype=np.float32, copy=True) for x in streams)
            for array, shape in zip(arrays, [(n, 3), (n, 3), (n, 4)]):
                if array.shape != shape or not np.isfinite(array).all():
                    raise ValueError('Pose streams must be finite and preserve vertex count')
            pending[index] = arrays
        self._pending_poses.update(pending)
        self._fur_scene_view = None
        self._trigger_repaint()

    def load_textures(self, material_textures: dict):
        """
        Queue albedo textures for GPU upload on the next paintGL call.
        Always defers to paintGL so OpenGL calls happen on the main thread
        with the GL context guaranteed active.
        """
        if not material_textures:
            return

        # Texture decoding arrives progressively from the archive worker. Keep
        # every previously decoded role and queue the complete affected
        # material so largest-resolution selection remains stable.
        self._cached_material_textures = _merge_material_textures(
            self._cached_material_textures, material_textures,
        )
        pending = getattr(self, '_pending_textures', {}) or {}
        affected = {
            mat_idx: self._cached_material_textures[mat_idx]
            for mat_idx in material_textures
        }
        self._pending_textures = _merge_material_textures(pending, affected)
        self._trigger_repaint()

    def _upload_textures(self, material_textures: dict):
        """Upload decoded PBR/effect inputs and assign them to GPU sub-meshes."""
        uploaded = {
            'texture_id': {},
            'normal_tex_id': {},
            'specular_tex_id': {},
            'fur_control_tex_id': {},
            'emissive_tex_id': {},
            'effect_mask_tex_id': {},
            'noise_tex_id': {},
            'retail_lava_color_a_tex_id': {},
            'retail_lava_color_b_tex_id': {},
            'retail_lava_normal_a_tex_id': {},
            'retail_lava_normal_b_tex_id': {},
            'retail_lava_noise_tex_id': {},
            'retail_lava_mask_a_tex_id': {},
            'retail_lava_mask_b_tex_id': {},
        }
        fur_lengths = {}
        fur_densities = {}
        fur_offset_scales = {}
        fur_headers = {}
        fur_shading = {}
        fur_wind_turbulence = {}

        def upload_slot(mat_idx, slot_data, role, anisotropy=1.0):
            if not slot_data or not slot_data[0]:
                return None
            rgba_bytes, width, height = slot_data[0], slot_data[1], slot_data[2]
            metadata = slot_data[4] if len(slot_data) > 4 \
                and isinstance(slot_data[4], dict) else {}
            anisotropy = min(anisotropy, self._max_texture_anisotropy)
            dxgi_format = metadata.get('dxgi_format')
            signature = (role, id(rgba_bytes), width, height, anisotropy, dxgi_format)
            if self._uploaded_texture_signatures.get((mat_idx, role)) == signature:
                return None
            try:
                tex_id = int(glGenTextures(1))
                glBindTexture(GL_TEXTURE_2D, tex_id)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
                if self._max_texture_anisotropy > 1.0:
                    glTexParameterf(GL_TEXTURE_2D, 0x84FE, anisotropy)
                compressed_mips = metadata.get('compressed_mips')
                compressed_mip0 = metadata.get('compressed_mip0')
                compressed_format = _compressed_gl_format(
                    dxgi_format, _is_srgb_texture_role(role),
                )
                used_authored_mips = bool(
                    compressed_mips and compressed_format is not None
                )
                if used_authored_mips:
                    for level, (mip_width, mip_height, blocks) in enumerate(
                            compressed_mips):
                        glCompressedTexImage2D(
                            GL_TEXTURE_2D, level, compressed_format,
                            mip_width, mip_height, 0, blocks,
                        )
                    glTexParameteri(
                        GL_TEXTURE_2D, GL_TEXTURE_MAX_LEVEL,
                        len(compressed_mips) - 1,
                    )
                    if dxgi_format in (0x4F, 0x50, 0x51) \
                            and role.startswith('retail_lava_'):
                        # The lava graph binds one BC4 map to RGB, G, and A
                        # consumers, so its SRVs replicate the red component.
                        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_R, GL_RED)
                        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_G, GL_RED)
                        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_B, GL_RED)
                        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_A, GL_RED)
                elif compressed_mip0 and compressed_format is not None:
                    glCompressedTexImage2D(
                        GL_TEXTURE_2D, 0, compressed_format, width, height, 0,
                        compressed_mip0,
                    )
                    if dxgi_format in (0x4F, 0x50, 0x51) \
                            and role.startswith('retail_lava_'):
                        # The lava graph binds one BC4 map to RGB, G, and A
                        # consumers, so its SRVs replicate the red component.
                        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_R, GL_RED)
                        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_G, GL_RED)
                        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_B, GL_RED)
                        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_A, GL_RED)
                elif dxgi_format in (0x4F, 0x50, 0x51) \
                        and role.startswith('retail_lava_'):
                    red = np.frombuffer(rgba_bytes, dtype=np.uint8) \
                        .reshape((-1, 4))[:, 0].copy()
                    glTexImage2D(
                        GL_TEXTURE_2D, 0, GL_R8, width, height, 0,
                        GL_RED, GL_UNSIGNED_BYTE, red,
                    )
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_R, GL_RED)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_G, GL_RED)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_B, GL_RED)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_A, GL_RED)
                else:
                    internal_format = GL_SRGB8_ALPHA8 \
                        if (_is_srgb_texture_role(role) or dxgi_format in (29, 72, 75, 78, 91, 93, 99)) else GL_RGBA8
                    glTexImage2D(
                        GL_TEXTURE_2D, 0, internal_format, width, height, 0,
                        GL_RGBA, GL_UNSIGNED_BYTE, rgba_bytes,
                    )
                if not used_authored_mips:
                    glGenerateMipmap(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, 0)
                self._uploaded_texture_signatures[(mat_idx, role)] = signature
                print(f"[viewport] uploaded {role} mat={mat_idx} {width}×{height}")
                return tex_id
            except Exception as ex:
                print(f"[viewport] {role} upload failed mat={mat_idx}: {ex}")
                return None

        for mat_idx, data in material_textures.items():
            if isinstance(data, dict):
                slots_by_attr = {
                    'texture_id': _best_texture_slot(data, BASE_COLOR_ROLES),
                    'normal_tex_id': _best_texture_slot(data, NORMAL_ROLES),
                    'specular_tex_id': _best_texture_slot(
                        data, SPECULAR_COLOR_ROLES,
                    ),
                    'fur_control_tex_id': _best_texture_slot(data, FUR_CONTROL_ROLES),
                    'emissive_tex_id': _best_texture_slot(data, EMISSIVE_ROLES),
                    'effect_mask_tex_id': _best_texture_slot(data, EFFECT_MASK_ROLES),
                    'noise_tex_id': _best_texture_slot(data, NOISE_ROLES),
                    'retail_lava_color_a_tex_id': _best_texture_slot(
                        data, RETAIL_LAVA_COLOR_A_ROLES,
                    ),
                    'retail_lava_color_b_tex_id': _best_texture_slot(
                        data, RETAIL_LAVA_COLOR_B_ROLES,
                    ),
                    'retail_lava_normal_a_tex_id': _best_texture_slot(
                        data, RETAIL_LAVA_NORMAL_A_ROLES,
                    ),
                    'retail_lava_normal_b_tex_id': _best_texture_slot(
                        data, RETAIL_LAVA_NORMAL_B_ROLES,
                    ),
                    'retail_lava_noise_tex_id': _best_texture_slot(
                        data, RETAIL_LAVA_NOISE_ROLES,
                    ),
                    'retail_lava_mask_a_tex_id': _best_texture_slot(
                        data, RETAIL_LAVA_MASK_A_ROLES,
                    ),
                    'retail_lava_mask_b_tex_id': _best_texture_slot(
                        data, RETAIL_LAVA_MASK_B_ROLES,
                    ),
                }
                fur_lengths[mat_idx] = _fur_length_from_texture_slot(
                    slots_by_attr['fur_control_tex_id'],
                )
                fur_densities[mat_idx] = _fur_density_from_texture_slot(
                    slots_by_attr['fur_control_tex_id'],
                )
                fur_offset_scales[mat_idx] = _fur_offset_scale_from_texture_slot(
                    slots_by_attr['fur_control_tex_id'],
                )
                fur_headers[mat_idx] = _fur_header_from_texture_slot(
                    slots_by_attr['fur_control_tex_id'],
                )
                fur_shading[mat_idx] = _fur_shading_from_texture_slot(
                    slots_by_attr['fur_control_tex_id'],
                )
                fur_wind_turbulence[mat_idx] = \
                    _fur_wind_turbulence_from_texture_slot(
                        slots_by_attr['fur_control_tex_id'],
                    )
            else:
                slots_by_attr = {
                    'texture_id': data,
                    'normal_tex_id': None,
                    'specular_tex_id': None,
                    'fur_control_tex_id': None,
                    'emissive_tex_id': None,
                    'effect_mask_tex_id': None,
                    'noise_tex_id': None,
                    'retail_lava_color_a_tex_id': None,
                    'retail_lava_color_b_tex_id': None,
                    'retail_lava_normal_a_tex_id': None,
                    'retail_lava_normal_b_tex_id': None,
                    'retail_lava_noise_tex_id': None,
                    'retail_lava_mask_a_tex_id': None,
                    'retail_lava_mask_b_tex_id': None,
                }

            role_by_attr = {
                'texture_id': 'base',
                'normal_tex_id': 'normal',
                'specular_tex_id': 'specular_color',
                'fur_control_tex_id': 'fur_control',
                'emissive_tex_id': 'emissive',
                'effect_mask_tex_id': 'effect_mask',
                'noise_tex_id': 'noise',
                'retail_lava_color_a_tex_id': 'retail_lava_color_a',
                'retail_lava_color_b_tex_id': 'retail_lava_color_b',
                'retail_lava_normal_a_tex_id': 'retail_lava_normal_a',
                'retail_lava_normal_b_tex_id': 'retail_lava_normal_b',
                'retail_lava_noise_tex_id': 'retail_lava_noise',
                'retail_lava_mask_a_tex_id': 'retail_lava_mask_a',
                'retail_lava_mask_b_tex_id': 'retail_lava_mask_b',
            }
            for attr, slot_data in slots_by_attr.items():
                # Captured fur samplers: albedo 16x, gloss/control 8x. Keep
                # the procedural layer volume on its separate linear sampler.
                anisotropy = 1.0
                if slots_by_attr['fur_control_tex_id']:
                    anisotropy = {
                        'texture_id': 16.0, 'specular_tex_id': 8.0,
                        'fur_control_tex_id': 8.0,
                    }.get(attr, 1.0)
                tex_id = upload_slot(
                    mat_idx, slot_data, role_by_attr[attr], anisotropy,
                )
                if tex_id:
                    uploaded[attr][mat_idx] = tex_id

        # Only update meshes whose material_index appears in the new batch.
        replaced_ids = set()
        for gm in self._gpu_meshes:
            if gm.material_index in fur_lengths:
                gm.fur_length = fur_lengths[gm.material_index]
                gm.fur_density = fur_densities[gm.material_index]
                gm.fur_offset_scale = fur_offset_scales[gm.material_index]
                gm.fur_layer_count, gm.fur_lod_reduction = \
                    fur_headers[gm.material_index]
                (
                    gm.fur_gloss_scale,
                    gm.fur_specular_scale,
                    gm.fur_transmittance_scale,
                ) = fur_shading[gm.material_index]
                gm.fur_wind_turbulence = \
                    fur_wind_turbulence[gm.material_index]
            for attr, by_material in uploaded.items():
                new_id = by_material.get(gm.material_index)
                if not new_id:
                    continue
                old_id = getattr(gm, attr)
                if old_id and old_id != new_id:
                    replaced_ids.add(int(old_id))
                setattr(gm, attr, new_id)
                if attr == 'fur_control_tex_id':
                    # Some shipped fur materials (Ratchet's limbs and tail)
                    # do not contain the word "fur" in their path.  The
                    # dedicated control binding is the authoritative signal.
                    gm.is_fur_surface = True
                    gm.is_fur = True
        for tex_id in replaced_ids:
            glDeleteTextures(1, [tex_id])

    def set_lod(self, lod_idx: int):
        """Switch the viewport to show a different LOD level."""
        if self._pending_model is None and not self._gpu_meshes:
            return
        model = getattr(self, '_current_model', None)
        if model is None:
            return
        self._active_lod = lod_idx
        self._fur_scene_view = None
        self._pending_model = model   # re-upload with new LOD filter
        # Re-apply cached textures after model re-upload
        if self._cached_material_textures:
            self._pending_textures = self._cached_material_textures
            # _upload_pending_model frees the prior LOD's GL texture objects,
            # so cached signatures must not suppress their replacement.
            self._uploaded_texture_signatures = {}
        self._trigger_repaint()

    def _trigger_repaint(self):
        self._redraw()

    def _upload_pending_model(self):
        """Called from paintGL — upload pending model with GL context active."""
        model = self._pending_model
        self._pending_model  = None
        self._current_model  = model   # keep reference for LOD switching

        active_lod = getattr(self, '_active_lod', 0)
        primary_meshes = [mesh for mesh in model.meshes if mesh.look_index == 0]
        if not primary_meshes:
            primary_meshes = list(model.meshes)
        available_lods = sorted({mesh.lod_level for mesh in primary_meshes})
        if available_lods and active_lod not in available_lods:
            # Some cooked Look tables reuse a mesh across several LOD slots.
            # The parser then retains only the last referenced LOD number, so a
            # hard-coded LOD0 filter produces an empty viewport despite valid
            # geometry.  Fall back to the highest-detail LOD that survived.
            active_lod = available_lods[0]

        self._free_gpu_meshes()
        all_positions = []
        skipped = 0

        for i, mesh in enumerate(primary_meshes):
            # Filter by look 0 + LOD level — avoids bundled props from other looks
            if mesh.lod_level != active_lod:
                continue

            positions, normals, uvs, indices = mesh_to_numpy(model, mesh)
            if positions is None or indices is None or len(positions) == 0:
                skipped += 1
                continue

            gpu = GpuSubMesh()
            gpu.material_index = mesh.material_index
            mesh_min = positions.min(axis=0)
            mesh_max = positions.max(axis=0)
            mesh_center = (mesh_min + mesh_max) * 0.5
            gpu.fur_wind_radius = float(np.max(np.linalg.norm(
                positions - mesh_center, axis=1,
            )))

            # Tag fur/shell meshes — they stay in GPU list but can be skipped at draw time
            mat_name = ''
            if model.material_names and mesh.material_index < len(model.material_names):
                mat_name = model.material_names[mesh.material_index].lower()
            gpu.material_name = mat_name
            gpu.is_lava = _uses_molten_shader(
                mat_name, getattr(model, 'source_path', ''),
            )
            gpu.is_lava_rock = _is_lava_rock_model(
                getattr(model, 'source_path', ''),
            )
            gpu.is_lavafall = _is_lavafall_model(
                getattr(model, 'source_path', ''),
            )
            gpu.is_retail_blizar_lava = _is_retail_blizar_lava_material(
                mat_name,
            )
            gpu.lava_flow_a, gpu.lava_flow_b = _lava_flow_sample_offsets(
                getattr(model, 'source_path', ''),
            )
            gpu.is_alpha_cutout = _is_alpha_cutout_material(mat_name)
            gpu.is_fur_surface = _is_fur_material(mat_name)
            gpu.is_composite_shell = _is_composite_shell_material(mat_name)
            gpu.is_fur = gpu.is_fur_surface or gpu.is_composite_shell

            try:
                resolved_uvs, generated_uvs = _resolved_mesh_uvs(
                    positions, normals, uvs,
                )
                if generated_uvs:
                    print(
                        f"[viewport] generated box UVs for mat={mesh.material_index} "
                        f"({len(positions):,} vertices)"
                    )
                authored_tangents = mesh_tangents_to_numpy(model, mesh)
                decode_corrections = mesh_decode_corrections_to_numpy(
                    model, mesh,
                )
                gpu.upload(
                    positions, normals, resolved_uvs, indices,
                    authored_tangents, decode_corrections,
                )
                if gpu.vao == 0:
                    skipped += 1
                    continue
            except Exception as e:
                print(f"[viewport] mesh {i} upload failed: {e}")
                skipped += 1
                continue
            hue = (i * 0.618033) % 1.0
            r, g, b = _hsv_to_rgb(hue, 0.4, 0.85)
            gpu.color = (r, g, b)
            self._gpu_meshes.append(gpu)
            all_positions.append(positions)

        print(f"[viewport] LOD{active_lod}: {len(self._gpu_meshes)} GPU meshes, {skipped} skipped")

        self._animated_materials = any(
            gpu.is_lava or gpu.is_retail_blizar_lava
            for gpu in self._gpu_meshes
        )
        if self._animated_materials:
            self._start_render_loop()
        else:
            self._stop_render_loop()

        if all_positions:
            pts = np.concatenate(all_positions)
            mn, mx = pts.min(axis=0), pts.max(axis=0)
            self._aabb_min = mn
            self._aabb_max = mx
            self._grid_y   = 0.0  # always at world origin
            self.camera.frame_aabb(mn, mx)
        self._upload_model_strands(model)

    def _upload_model_strands(self, model):
        source_path = getattr(model, 'source_path', '')
        if not ratchet_strand_fixtures_available(source_path):
            return
        summaries = []
        captured_wind = bool(
            abs(self._fur_wind_strength - MODEL_STRAND_CAPTURED_WIND_STRENGTH) < 1e-7
            and self._fur_wind_time_override is not None
            and abs(self._fur_wind_time_override - MODEL_STRAND_CAPTURED_WIND_TIME) < 1e-4
        )
        for profile_name in ('tail', 'head-sparse', 'ears'):
            group = GpuModelStrandGroup(profile_name)
            try:
                group.upload(captured_wind=captured_wind)
            except Exception as ex:
                group.free()
                print(f"[model-strand] {profile_name} upload failed: {ex}", flush=True)
                continue
            self._gpu_model_strands.append(group)
            summaries.append(group.summary)
        if summaries:
            print(f"[model-strand] capture-derived groups ready: {summaries}", flush=True)

    def frame_model(self):
        """Reset camera to frame the loaded model."""
        if self._gpu_meshes:
            # Re-frame from stored AABB
            if hasattr(self, '_aabb_min') and hasattr(self, '_aabb_max'):
                self.camera.frame_aabb(self._aabb_min, self._aabb_max)
                self._redraw()
        else:
            self.camera.target = np.zeros(3, dtype=np.float32)
            self.camera.dist   = 5.0
            self._redraw()

    def set_view_preset(self, preset: str):
        """Set camera to a named preset view."""
        presets = {
            'main':   ( 45,  25),
            'front':  ( 90,   0),
            'back':   (270,   0),
            'right':  (180,   0),
            'left':   (  0,   0),
            'top':    (  0,  89),
            'bottom': (  0, -89),
        }
        if preset in presets:
            self.camera.yaw, self.camera.pitch = presets[preset]
            self._redraw()

    def clear_mesh(self):
        self._animated_materials = False
        self._stop_render_loop()
        self.makeCurrent()
        self._free_gpu_meshes()
        self.doneCurrent()
        self._redraw()

    def set_wireframe(self, enabled: bool):
        self._wireframe = enabled
        self._redraw()

    def set_bloom_enabled(self, enabled: bool):
        """Enable HDR bloom for emissive/effect materials."""
        self._bloom_enabled = bool(enabled)
        self._redraw()

    def set_show_fur(self, enabled: bool):
        """Toggle visibility of fur/composite shell meshes."""
        self._show_fur = enabled
        self.update()
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

    def _reset_temporal_history(self) -> None:
        self._reset_pose_history = True
        self._temporal_signature = None
        self._temporal_sample_count = 0
        self._motion_blur_scatter_valid = [False, False]
        self._temporal_disocclusion_valid = [False, False]
        self._temporal_alpha_valid = False
        self._previous_fur_mvp = None
        self._previous_fur_projection = None
        self._previous_fur_view = None
        self._previous_fur_wind_time = None
        self._previous_fur_jitter = None
        self._fur_motion_signature = None

    def set_temporal_aa_state(
        self, *, nonopaque_response: float | None = None,
        conditional_floor: bool = False,
        hdr_reference: float | None = None,
    ) -> None:
        """Set the per-frame producers consumed by native TAA ``m_Misc.xyz``."""
        response = (
            None if nonopaque_response is None else float(nonopaque_response)
        )
        reference = None if hdr_reference is None else float(hdr_reference)
        state = (response, bool(conditional_floor), reference)
        previous = (
            self._temporal_nonopaque_response,
            self._temporal_conditional_floor,
            self._temporal_hdr_reference,
        )
        if state == previous:
            return
        self._temporal_nonopaque_response = response
        self._temporal_conditional_floor = bool(conditional_floor)
        self._temporal_hdr_reference = reference
        self._reset_temporal_history()
        self._redraw()

    def temporal_aa_misc(
        self, history_age: int | None = None,
    ) -> tuple[float, float, float, float]:
        """Return the live native TAA scalar register for inspection/upload."""
        return temporal_apply_misc(
            nonopaque_response=self._temporal_nonopaque_response,
            conditional_floor=self._temporal_conditional_floor,
            runtime_hdr_reference=self._temporal_hdr_reference,
            history_age=(
                self._temporal_sample_count
                if history_age is None else history_age
            ),
        )

    def set_preview_light_direction(self, direction) -> None:
        """Set an isolated-view key light; a valid scene retains its own key."""
        values = np.asarray(direction, dtype=np.float64)
        if values.shape != (3,) or not np.isfinite(values).all():
            raise ValueError('Light direction requires three finite values')
        magnitude = np.linalg.norm(values)
        if not np.isfinite(magnitude) or magnitude < 1e-12:
            raise ValueError('Light direction must be nonzero')
        result = tuple(float(v) for v in values / magnitude)
        if result == self._preview_light_direction:
            return
        self._preview_light_direction = result
        self._reset_temporal_history()
        self._redraw()

    def set_fur_weather(
        self, *, wetness: float | None = None,
        wind_strength: float | None = None,
        wind_vector=None,
        wind_object_phase: float | None = None,
        wind_time: float | None = None,
    ) -> None:
        """Set the runtime weather inputs consumed by the retail fur shaders."""
        if wetness is not None:
            self._fur_wetness = float(np.clip(wetness, 0.0, 1.0))
        if wind_strength is not None:
            self._fur_wind_strength = max(float(wind_strength), 0.0)
        if wind_vector is not None:
            # The runtime vector's magnitude contributes to shell displacement.
            self._fur_wind_vector = np.asarray(
                wind_vector, dtype=np.float32,
            ).reshape(3).copy()
        if wind_object_phase is not None:
            self._fur_wind_object_phase = float(wind_object_phase)
        self._fur_wind_time_override = (
            None if wind_time is None else float(wind_time)
        )
        if self._fur_wind_strength > 0.0:
            self._start_render_loop()
        else:
            self._stop_render_loop()
        self._reset_temporal_history()
        self._redraw()

    def set_fur_environment(
        self, cube_mips, brdf_half_rgba: bytes,
        brdf_size: tuple[int, int] = (64, 64),
    ) -> None:
        """Queue a native BC6U/decoded RGB16F cube and captured RG16F BRDF LUT."""
        validate_cube_mips(cube_mips)
        self._pending_fur_environment = (
            cube_mips, bytes(brdf_half_rgba), tuple(brdf_size),
        )
        if self._fur_shader_prog:
            self.makeCurrent()
            try:
                self._upload_fur_environment()
            finally:
                self.doneCurrent()
        self._reset_temporal_history()
        self._redraw()

    def _fur_scene_view_key(self):
        """Lookup masks belong to one camera/view and cannot follow an orbit."""
        return (self.camera.view_matrix().tobytes(), self._framebuffer_size(),
                bool(getattr(self, '_ortho', False)), id(self._gpu_meshes))

    def set_fur_scene_lighting(self, bundle) -> None:
        """Attach explicit resources for the current view, or clear with None.

        The scene loader must supply matching world placement and a current
        per-tile lookup. Camera, viewport and model changes invalidate that
        lookup until a new bundle is supplied.
        """
        from core.hair_scene import validate_hair_scene
        pending = None if bundle is None else validate_hair_scene(bundle)
        if pending is not None and pending[1]['viewport_size'] != self._framebuffer_size():
            raise ValueError('Scene lighting lookup dimensions must match the current framebuffer')
        self._pending_fur_scene = (pending, self._fur_scene_view_key()) if pending is not None else None
        if self._fur_shader_prog:
            self.makeCurrent()
            try:
                self._upload_fur_scene()
            finally:
                self.doneCurrent()
        self._reset_temporal_history()
        self._redraw()

    def _upload_fur_scene(self):
        from core.hair_scene import HairSceneGpu
        pending = self._pending_fur_scene
        self._pending_fur_scene = None
        replacement = None
        if pending is not None:
            if not self._fur_scene_program:
                self._fur_scene_program = compileProgram(
                    self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
                    self._compile_viewport_shader(
                        FUR_SCENE_LIGHTING_FRAG, GL_FRAGMENT_SHADER,
                    ), validate=False,
                )
            replacement = HairSceneGpu(*pending[0])
        if self._fur_scene_gpu is not None:
            self._fur_scene_gpu.close()
        self._fur_scene_gpu = replacement
        self._fur_scene_view = pending[1] if pending is not None else None

    def _fur_scene_is_current(self):
        return self._fur_scene_gpu is not None and self._fur_scene_view == self._fur_scene_view_key()

    def _set_fur_temporal_uniforms(self, program):
        if self._fur_scene_is_current():
            params = self._fur_scene_gpu.params
            index, cycle = params['temporal_index'], params['temporal_plus_cycle']
        else:
            index = _halton((self._temporal_sample_count % 32) + 1, 2)
            cycle = self._temporal_sample_count
        _set_uniform_1f(program, 'uTemporalIndex', float(index))
        _set_uniform_1f(program, 'uTemporalPlusCycle', float(cycle))

    # ── OpenGL Lifecycle ──────────────────────────────────────────────────────

    def _compile_viewport_shader(self, source: str, shader_type: int):
        return compileShader(
            _shader_with_raster_mode(source, self._native_raster_active),
            shader_type,
        )

    def _apply_raster_convention(self) -> None:
        """Apply one coherent origin, clip-depth, and depth-test convention."""
        if self._native_raster_active:
            glClipControl(GL_UPPER_LEFT, GL_ZERO_TO_ONE)
            glClearDepth(0.0)
            glDepthFunc(GL_GEQUAL)
        else:
            glClearDepth(1.0)
            glDepthFunc(GL_LESS)

    def initializeGL(self):
        if not _HAS_OPENGL:
            return

        extensions = {
            glGetStringi(GL_EXTENSIONS, index)
            for index in range(int(glGetIntegerv(GL_NUM_EXTENSIONS)))
        }
        version = (
            int(glGetIntegerv(GL_MAJOR_VERSION)),
            int(glGetIntegerv(GL_MINOR_VERSION)),
        )
        self._native_raster_active = bool(
            callable(globals().get('glClipControl'))
            and _supports_native_raster(version, extensions)
        )
        self._apply_raster_convention()
        if extensions.intersection({
            b'GL_EXT_texture_filter_anisotropic',
            b'GL_ARB_texture_filter_anisotropic',
        }):
            self._max_texture_anisotropy = float(glGetFloatv(0x84FF))

        glClearColor(0.102, 0.110, 0.133, 1.0)  # matches BG_BASE #1a1c22
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        vert = self._compile_viewport_shader(VERT_SRC, GL_VERTEX_SHADER)
        frag = self._compile_viewport_shader(FRAG_SRC, GL_FRAGMENT_SHADER)
        self._shader_prog = compileProgram(vert, frag)

        self._fur_shader_prog = compileProgram(
            self._compile_viewport_shader(FUR_SHELL_VERT_SRC, GL_VERTEX_SHADER),
            self._compile_viewport_shader(FUR_SHELL_GEOM_SRC, GL_GEOMETRY_SHADER),
            self._compile_viewport_shader(FUR_SHELL_FRAG_SRC, GL_FRAGMENT_SHADER),
        )
        self._fur_material_prog = compileProgram(
            self._compile_viewport_shader(FUR_SHELL_VERT_SRC, GL_VERTEX_SHADER),
            self._compile_viewport_shader(FUR_SHELL_GEOM_SRC, GL_GEOMETRY_SHADER),
            self._compile_viewport_shader(FUR_MATERIAL_FRAG_SRC, GL_FRAGMENT_SHADER),
        )
        self._model_strand_material_prog = compileProgram(
            self._compile_viewport_shader(MODEL_STRAND_VERT_SRC, GL_VERTEX_SHADER),
            self._compile_viewport_shader(
                MODEL_STRAND_MATERIAL_FRAG_SRC, GL_FRAGMENT_SHADER,
            ),
        )
        for attribute, source in (('_fur_decode_prog', FUR_DECODE_FRAG),
                                  ('_fur_lighting_prog', FUR_LIGHTING_FRAG)):
            setattr(self, attribute, compileProgram(
                self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
                self._compile_viewport_shader(source, GL_FRAGMENT_SHADER),
            ))
        self._upload_fur_layer_volume()
        try:
            self._upload_fur_environment()
        except Exception as ex:
            print(f"[viewport] fur environment upload failed: {ex}", flush=True)
            raise

        gv = self._compile_viewport_shader(GRID_VERT, GL_VERTEX_SHADER)
        gf = self._compile_viewport_shader(GRID_FRAG, GL_FRAGMENT_SHADER)
        self._grid_prog = compileProgram(gv, gf)

        pv = self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER)
        bf = self._compile_viewport_shader(BLUR_FRAG, GL_FRAGMENT_SHADER)
        cf = self._compile_viewport_shader(COMPOSITE_FRAG, GL_FRAGMENT_SHADER)
        self._blur_prog = compileProgram(pv, bf)
        # A shader object cannot be linked into a second program after
        # compileProgram has deleted it, so compile a fresh fullscreen vertex.
        self._composite_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER), cf,
        )
        self._temporal_accum_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(TEMPORAL_ACCUM_FRAG, GL_FRAGMENT_SHADER),
        )
        self._temporal_disocclusion_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(TEMPORAL_DISOCCLUSION_FRAG, GL_FRAGMENT_SHADER),
        )
        self._temporal_linear_depth_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(TEMPORAL_LINEAR_DEPTH_FRAG, GL_FRAGMENT_SHADER),
        )
        self._temporal_half_base_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(TEMPORAL_HALF_BASE_FRAG, GL_FRAGMENT_SHADER),
        )
        self._temporal_alpha_mask_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(TEMPORAL_ALPHA_MASK_FRAG, GL_FRAGMENT_SHADER),
        )
        self._temporal_alpha_half_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(TEMPORAL_ALPHA_HALF_FRAG, GL_FRAGMENT_SHADER),
        )
        self._motion_blur_downsample_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(MOTION_BLUR_DOWNSAMPLE_FRAG, GL_FRAGMENT_SHADER),
        )
        self._motion_blur_neighborhood_half_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(MOTION_BLUR_NEIGHBORHOOD_HALF_FRAG, GL_FRAGMENT_SHADER),
        )
        self._motion_blur_neighborhood_quarter_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(MOTION_BLUR_NEIGHBORHOOD_QUARTER_FRAG, GL_FRAGMENT_SHADER),
        )
        self._motion_blur_gather_neighborhood_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(MOTION_BLUR_GATHER_NEIGHBORHOOD_FRAG, GL_FRAGMENT_SHADER),
        )
        self._motion_blur_scatter_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(MOTION_BLUR_SCATTER_FRAG, GL_FRAGMENT_SHADER),
        )
        self._fur_contact_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(FUR_CONTACT_FRAG, GL_FRAGMENT_SHADER),
        )
        self._fur_denoise_prog = compileProgram(
            self._compile_viewport_shader(POST_VERT, GL_VERTEX_SHADER),
            self._compile_viewport_shader(FUR_DENOISE_FRAG, GL_FRAGMENT_SHADER),
        )
        # The recovered fur pass does not use the old weighted-OIT ribbon
        # attachments. Its no-TAA viewport resolve composites expected shell
        # coverage root-to-tip into the scene target.
        self._fur_oit_composite_prog = 0
        self._fur_oit_supported = False

        self._build_grid(20, 0.2)
        self._resize_bloom_targets(*self._framebuffer_size())

    def resizeGL(self, w: int, h: int):
        framebuffer_size = _scaled_framebuffer_size(
            w, h, self.devicePixelRatioF(),
        )
        glViewport(0, 0, *framebuffer_size)
        self._resize_bloom_targets(*framebuffer_size)

    @staticmethod
    def _generated_ids(values) -> list[int]:
        return [int(value) for value in np.atleast_1d(values).tolist()]

    def _upload_fur_layer_volume(self):
        """Upload the recovered procedural Default Fur Shells volume."""
        mip_chain = _build_fur_layer_mips()
        self._fur_layer_texture = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D_ARRAY, self._fur_layer_texture)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        for level, volume in enumerate(mip_chain):
            glTexImage3D(
                GL_TEXTURE_2D_ARRAY, level, GL_R8,
                volume.shape[2], volume.shape[1], volume.shape[0], 0,
                GL_RED, GL_UNSIGNED_BYTE, volume,
            )
        glTexParameteri(
            GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MIN_FILTER,
            GL_LINEAR_MIPMAP_LINEAR,
        )
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_BASE_LEVEL, 0)
        # TextureDefaultsInit allocates base + three downsampled levels.
        glTexParameteri(
            GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAX_LEVEL, len(mip_chain) - 1,
        )
        glBindTexture(GL_TEXTURE_2D_ARRAY, 0)

    def _upload_fur_environment(self):
        """Upload the original BC6U blocks or a decoded diagnostic cube."""
        pending = self._pending_fur_environment
        if pending is None:
            return
        cube_mips, brdf_half_rgba, brdf_size = pending
        encoding = validate_cube_mips(cube_mips)
        if self._fur_environment_texture:
            glDeleteTextures(1, [self._fur_environment_texture])
        if self._fur_brdf_texture:
            glDeleteTextures(1, [self._fur_brdf_texture])
        self._fur_environment_texture = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_CUBE_MAP, self._fur_environment_texture)
        level_count = len(cube_mips[0])
        for face, levels in enumerate(cube_mips):
            for level, (width, height, pixels) in enumerate(levels):
                target = GL_TEXTURE_CUBE_MAP_POSITIVE_X + face
                if encoding == 'bc6u':
                    blocks = np.frombuffer(pixels, dtype=np.uint8)
                    # Bypass PyOpenGL's compressed-array converter, which
                    # rejects these otherwise valid original blocks.
                    _raw_compressed_tex_image_2d(
                        target, level, GL_COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT,
                        width, height, 0, blocks.nbytes,
                        ctypes.c_void_p(blocks.ctypes.data),
                    )
                else:
                    decoded = np.frombuffer(pixels, dtype=np.float16)
                    glTexImage2D(target, level, GL_RGB16F, width, height, 0,
                                 GL_RGB, GL_HALF_FLOAT, decoded)
                error = glGetError()
                if error != GL_NO_ERROR:
                    raise RuntimeError(f'Hair cube upload failed: GL error {error}')
        glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        for axis in (GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_TEXTURE_WRAP_R):
            glTexParameteri(GL_TEXTURE_CUBE_MAP, axis, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_BASE_LEVEL, 0)
        glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MAX_LEVEL, level_count - 1)
        glEnable(GL_TEXTURE_CUBE_MAP_SEAMLESS)

        brdf_width, brdf_height = brdf_size
        expected_bytes = brdf_width * brdf_height * 2 * 2
        if len(brdf_half_rgba) != expected_bytes:
            raise ValueError(
                f"Hair BRDF LUT needs {expected_bytes} bytes, "
                f"got {len(brdf_half_rgba)}"
            )
        self._fur_brdf_texture = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, self._fur_brdf_texture)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RG16F,
            brdf_width, brdf_height, 0,
            GL_RG, GL_HALF_FLOAT, brdf_half_rgba,
        )
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glBindTexture(GL_TEXTURE_2D, 0)
        glBindTexture(GL_TEXTURE_CUBE_MAP, 0)
        self._pending_fur_environment = None

    def _delete_bloom_targets(self):
        for texture in self._fur_material_textures + [
            self._fur_indirect_texture,
            self._scene_linear_depth_texture,
            self._scene_velocity_texture,
            self._scene_stencil_texture,
        ]:
            if texture:
                glDeleteTextures(1, [texture])
        for fbo in (self._fur_material_fbo, self._fur_decode_fbo, self._fur_lighting_fbo):
            if fbo:
                glDeleteFramebuffers(1, [fbo])
        if self._hdr_color_buffers:
            glDeleteTextures(len(self._hdr_color_buffers), self._hdr_color_buffers)
        if self._fur_gbuffer_texture:
            glDeleteTextures(1, [self._fur_gbuffer_texture])
        if self._fur_normal_texture:
            glDeleteTextures(1, [self._fur_normal_texture])
        if self._fur_denoise_texture:
            glDeleteTextures(1, [self._fur_denoise_texture])
        if self._fur_gather_address_texture:
            glDeleteTextures(1, [self._fur_gather_address_texture])
        if self._fur_key_texture:
            glDeleteTextures(1, [self._fur_key_texture])
        if self._fur_contact_texture:
            glDeleteTextures(1, [self._fur_contact_texture])
        if self._fur_oit_textures:
            glDeleteTextures(len(self._fur_oit_textures), self._fur_oit_textures)
        if self._fur_scene_depth_texture:
            glDeleteTextures(1, [self._fur_scene_depth_texture])
        if self._pingpong_textures:
            glDeleteTextures(len(self._pingpong_textures), self._pingpong_textures)
        if self._temporal_textures:
            glDeleteTextures(len(self._temporal_textures), self._temporal_textures)
        if self._temporal_depth_textures:
            glDeleteTextures(
                len(self._temporal_depth_textures), self._temporal_depth_textures,
            )
        if self._temporal_disocclusion_textures:
            glDeleteTextures(
                len(self._temporal_disocclusion_textures),
                self._temporal_disocclusion_textures,
            )
        temporal_alpha_textures = [
            *self._temporal_linear_depth_textures,
            *self._temporal_half_textures,
            self._temporal_alpha_mask_texture,
        ]
        temporal_alpha_textures = [
            texture for texture in temporal_alpha_textures if texture
        ]
        if temporal_alpha_textures:
            glDeleteTextures(len(temporal_alpha_textures), temporal_alpha_textures)
        motion_blur_textures = [
            self._motion_blur_depth_velocity_texture,
            self._motion_blur_half_velocity_texture,
            *self._motion_blur_neighborhood_textures,
            *self._motion_blur_scatter_textures,
        ]
        motion_blur_textures = [texture for texture in motion_blur_textures if texture]
        if motion_blur_textures:
            glDeleteTextures(len(motion_blur_textures), motion_blur_textures)
        if self._hdr_depth_rbo:
            glDeleteRenderbuffers(1, [self._hdr_depth_rbo])
        if self._hdr_fbo:
            glDeleteFramebuffers(1, [self._hdr_fbo])
        if self._fur_denoise_fbo:
            glDeleteFramebuffers(1, [self._fur_denoise_fbo])
        if self._fur_contact_fbo:
            glDeleteFramebuffers(1, [self._fur_contact_fbo])
        if self._pingpong_fbos:
            glDeleteFramebuffers(len(self._pingpong_fbos), self._pingpong_fbos)
        if self._temporal_fbos:
            glDeleteFramebuffers(len(self._temporal_fbos), self._temporal_fbos)
        if self._temporal_disocclusion_fbos:
            glDeleteFramebuffers(
                len(self._temporal_disocclusion_fbos),
                self._temporal_disocclusion_fbos,
            )
        temporal_alpha_fbos = [
            self._temporal_linear_depth_fbo,
            self._temporal_half_fbo,
            self._temporal_alpha_mask_fbo,
        ]
        temporal_alpha_fbos = [fbo for fbo in temporal_alpha_fbos if fbo]
        if temporal_alpha_fbos:
            glDeleteFramebuffers(len(temporal_alpha_fbos), temporal_alpha_fbos)
        motion_blur_fbos = [
            self._motion_blur_downsample_fbo,
            *self._motion_blur_neighborhood_fbos,
            *self._motion_blur_scatter_fbos,
        ]
        motion_blur_fbos = [fbo for fbo in motion_blur_fbos if fbo]
        if motion_blur_fbos:
            glDeleteFramebuffers(len(motion_blur_fbos), motion_blur_fbos)
        self._hdr_fbo = 0
        self._hdr_color_buffers = []
        self._fur_material_fbo = 0
        self._fur_material_textures = []
        self._fur_decode_fbo = 0
        self._fur_lighting_fbo = 0
        self._fur_indirect_texture = 0
        self._scene_linear_depth_texture = 0
        self._scene_velocity_texture = 0
        self._scene_stencil_texture = 0
        self._fur_gbuffer_texture = 0
        self._fur_normal_texture = 0
        self._fur_denoise_fbo = 0
        self._fur_key_texture = 0
        self._fur_contact_fbo = 0
        self._fur_contact_texture = 0
        self._fur_denoise_texture = 0
        self._fur_gather_address_texture = 0
        self._fur_oit_textures = []
        self._fur_scene_depth_texture = 0
        self._fur_depth_snapshot_ready = False
        self._hdr_depth_rbo = 0
        self._pingpong_fbos = []
        self._pingpong_textures = []
        self._temporal_fbos = []
        self._temporal_textures = []
        self._temporal_depth_textures = []
        self._temporal_disocclusion_fbos = []
        self._temporal_disocclusion_textures = []
        self._temporal_disocclusion_valid = [False, False]
        self._temporal_linear_depth_fbo = 0
        self._temporal_linear_depth_textures = []
        self._temporal_half_fbo = 0
        self._temporal_half_textures = []
        self._temporal_alpha_mask_fbo = 0
        self._temporal_alpha_mask_texture = 0
        self._temporal_alpha_valid = False
        self._motion_blur_downsample_fbo = 0
        self._motion_blur_depth_velocity_texture = 0
        self._motion_blur_half_velocity_texture = 0
        self._motion_blur_neighborhood_fbos = []
        self._motion_blur_neighborhood_textures = []
        self._motion_blur_scatter_fbos = []
        self._motion_blur_scatter_textures = []
        self._motion_blur_scatter_valid = [False, False]
        self._motion_blur_sizes = ((0, 0), (0, 0), (0, 0))
        self._temporal_sample_count = 0
        self._temporal_signature = None
        self._previous_fur_mvp = None
        self._previous_fur_projection = None
        self._previous_fur_view = None
        self._previous_fur_wind_time = None
        self._previous_fur_jitter = None
        self._fur_motion_signature = None
        self._display_scene_texture = 0
        self._current_scene_texture = 0
        self._current_scene_fbo = 0
        self._bloom_size = (0, 0)

    @staticmethod
    def _create_fur_gather_addresses(width, height):
        """Pixel indices sampled with the native texture-coordinate convention."""
        texture = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, texture)
        addresses = np.arange(width * height, dtype=np.uint32).reshape(height, width)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_R32UI, width, height, 0,
                     GL_RED_INTEGER, GL_UNSIGNED_INT, addresses)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        return texture

    @staticmethod
    def _make_fur_target(width, height, internal, fmt, dtype, attachment):
        texture = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, texture)
        glTexImage2D(GL_TEXTURE_2D, 0, internal, width, height, 0, fmt, dtype, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0 + attachment, GL_TEXTURE_2D, texture, 0)
        return texture

    def _resize_bloom_targets(self, width: int, height: int):
        """Create floating-point scene/bright buffers and blur ping-pong targets."""
        if not self._bloom_supported or self._bloom_size == (width, height):
            return
        try:
            self._delete_bloom_targets()
            self._fur_gather_address_texture = self._create_fur_gather_addresses(width, height)
            self._hdr_fbo = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._hdr_fbo)
            self._hdr_color_buffers = self._generated_ids(glGenTextures(2))
            for index, tex_id in enumerate(self._hdr_color_buffers):
                glBindTexture(GL_TEXTURE_2D, tex_id)
                glTexImage2D(
                    GL_TEXTURE_2D, 0, GL_RGBA16F, width, height, 0,
                    GL_RGBA, GL_FLOAT, None,
                )
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                glFramebufferTexture2D(
                    GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0 + index,
                    GL_TEXTURE_2D, tex_id, 0,
                )
            glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
            self._scene_linear_depth_texture = self._make_fur_target(
                width, height, GL_RGBA32F, GL_RGBA, GL_FLOAT, 2)
            self._scene_velocity_texture = self._make_fur_target(
                width, height, GL_RG16F, GL_RG, GL_HALF_FLOAT, 3,
            )
            self._scene_stencil_texture = self._make_fur_target(
                width, height, GL_R8UI, GL_RED_INTEGER, GL_UNSIGNED_BYTE, 4,
            )
            if self._fur_oit_supported:
                self._fur_oit_textures = self._generated_ids(glGenTextures(2))
                for index, tex_id in enumerate(self._fur_oit_textures):
                    glBindTexture(GL_TEXTURE_2D, tex_id)
                    glTexImage2D(
                        GL_TEXTURE_2D, 0, GL_RGBA16F, width, height, 0,
                        GL_RGBA, GL_FLOAT, None,
                    )
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                    glFramebufferTexture2D(
                        GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT2 + index,
                        GL_TEXTURE_2D, tex_id, 0,
                    )
            self._hdr_depth_rbo = int(glGenRenderbuffers(1))
            glBindRenderbuffer(GL_RENDERBUFFER, self._hdr_depth_rbo)
            glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, width, height)
            glFramebufferRenderbuffer(
                GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, self._hdr_depth_rbo,
            )
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("HDR framebuffer is incomplete")

            self._fur_material_fbo = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._fur_material_fbo)
            self._fur_material_textures = [
                self._make_fur_target(width, height, internal, fmt, dtype, attachment)
                for attachment, (internal, fmt, dtype) in enumerate((
                    (GL_RGBA16UI, GL_RGBA_INTEGER, GL_UNSIGNED_SHORT),
                    (GL_SRGB8_ALPHA8, GL_RGBA, GL_UNSIGNED_BYTE),
                    (GL_R32F, GL_RED, GL_FLOAT),
                    (GL_R32UI, GL_RED_INTEGER, GL_UNSIGNED_INT),
                    (GL_RG16F, GL_RG, GL_HALF_FLOAT),
                ))
            ]
            # Both material passes depth-test against the same opaque geometry.
            glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, self._hdr_depth_rbo)
            # The native temporal apply loads category bit 128 from the same
            # per-pixel target for opaque and accumulated-alpha geometry.
            glFramebufferTexture2D(
                GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT5, GL_TEXTURE_2D,
                self._scene_stencil_texture, 0,
            )
            glDrawBuffers(6, [GL_COLOR_ATTACHMENT0 + i for i in range(6)])
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError('Fur material framebuffer is incomplete')
            self._fur_decode_fbo = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._fur_decode_fbo)
            self._fur_gbuffer_texture = self._make_fur_target(width, height, GL_RGBA32F, GL_RGBA, GL_FLOAT, 0)
            self._fur_normal_texture = self._make_fur_target(width, height, GL_RGBA32F, GL_RGBA, GL_FLOAT, 1)
            glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError('Fur vector framebuffer is incomplete')
            self._fur_lighting_fbo = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._fur_lighting_fbo)
            self._fur_indirect_texture = self._make_fur_target(width, height, GL_RGBA32F, GL_RGBA, GL_FLOAT, 0)
            self._fur_key_texture = self._make_fur_target(width, height, GL_RGBA32F, GL_RGBA, GL_FLOAT, 1)
            glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError('Fur illumination framebuffer is incomplete')

            for prefix in ('_fur_contact', '_fur_denoise'):
                fbo = int(glGenFramebuffers(1))
                texture = int(glGenTextures(1))
                setattr(self, prefix + '_fbo', fbo)
                setattr(self, prefix + '_texture', texture)
                glBindFramebuffer(GL_FRAMEBUFFER, fbo)
                glBindTexture(GL_TEXTURE_2D, texture)
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA16F, width, height, 0, GL_RGBA, GL_FLOAT, None)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0)
                if prefix == '_fur_contact':
                    # Fur replaces covered opaque emission in the bloom buffer.
                    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT1,
                                           GL_TEXTURE_2D, self._hdr_color_buffers[1], 0)
                    glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
                if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                    raise RuntimeError('Fur lighting framebuffer is incomplete: ' + prefix)

            # Keep a detached depth texture for the fur pass. Sampling the
            # attached depth image while it is also used for depth testing is
            # an OpenGL feedback loop, so opaque depth is copied here instead.
            try:
                self._fur_scene_depth_texture = int(glGenTextures(1))
                glBindTexture(GL_TEXTURE_2D, self._fur_scene_depth_texture)
                glTexImage2D(
                    GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT24, width, height, 0,
                    GL_DEPTH_COMPONENT, GL_FLOAT, None,
                )
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                glBindTexture(GL_TEXTURE_2D, 0)
            except Exception as depth_ex:
                print(f"[viewport] fur screen-space shadow disabled: {depth_ex}")
                if self._fur_scene_depth_texture:
                    glDeleteTextures(1, [self._fur_scene_depth_texture])
                self._fur_scene_depth_texture = 0

            self._pingpong_fbos = self._generated_ids(glGenFramebuffers(2))
            self._pingpong_textures = self._generated_ids(glGenTextures(2))
            for fbo, tex_id in zip(self._pingpong_fbos, self._pingpong_textures):
                glBindFramebuffer(GL_FRAMEBUFFER, fbo)
                glBindTexture(GL_TEXTURE_2D, tex_id)
                glTexImage2D(
                    GL_TEXTURE_2D, 0, GL_RGBA16F, width, height, 0,
                    GL_RGBA, GL_FLOAT, None,
                )
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                glFramebufferTexture2D(
                    GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex_id, 0,
                )
                if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                    raise RuntimeError("Bloom blur framebuffer is incomplete")

            self._temporal_fbos = self._generated_ids(glGenFramebuffers(2))
            self._temporal_textures = self._generated_ids(glGenTextures(2))
            self._temporal_depth_textures = self._generated_ids(glGenTextures(2))
            for fbo, tex_id, depth_id in zip(
                self._temporal_fbos,
                self._temporal_textures,
                self._temporal_depth_textures,
            ):
                glBindFramebuffer(GL_FRAMEBUFFER, fbo)
                glBindTexture(GL_TEXTURE_2D, tex_id)
                _raw_tex_image_2d(
                    GL_TEXTURE_2D, 0, GL_R11F_G11F_B10F, width, height, 0,
                    GL_RGB, GL_UNSIGNED_INT_10F_11F_11F_REV,
                    ctypes.c_void_p(0),
                )
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                glFramebufferTexture2D(
                    GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                    GL_TEXTURE_2D, tex_id, 0,
                )
                glDrawBuffer(GL_COLOR_ATTACHMENT0)
                if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                    raise RuntimeError("Temporal framebuffer is incomplete")
                glBindTexture(GL_TEXTURE_2D, depth_id)
                glTexImage2D(
                    GL_TEXTURE_2D, 0, GL_RG16F, width, height, 0,
                    GL_RG, GL_HALF_FLOAT, None,
                )
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

            self._temporal_disocclusion_fbos = self._generated_ids(
                glGenFramebuffers(2),
            )
            self._temporal_disocclusion_textures = self._generated_ids(
                glGenTextures(2),
            )
            for fbo, disocclusion_id, depth_id in zip(
                self._temporal_disocclusion_fbos,
                self._temporal_disocclusion_textures,
                self._temporal_depth_textures,
            ):
                glBindFramebuffer(GL_FRAMEBUFFER, fbo)
                glBindTexture(GL_TEXTURE_2D, disocclusion_id)
                glTexImage2D(
                    GL_TEXTURE_2D, 0, GL_RG8, width, height, 0,
                    GL_RG, GL_UNSIGNED_BYTE, None,
                )
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                glFramebufferTexture2D(
                    GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                    GL_TEXTURE_2D, disocclusion_id, 0,
                )
                glFramebufferTexture2D(
                    GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT1,
                    GL_TEXTURE_2D, depth_id, 0,
                )
                glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
                if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                    raise RuntimeError("Temporal disocclusion framebuffer is incomplete")
            self._temporal_disocclusion_valid = [False, False]

            half_size = (max(1, (width + 1) // 2), max(1, (height + 1) // 2))
            quarter_size = (
                max(1, (half_size[0] + 1) // 2),
                max(1, (half_size[1] + 1) // 2),
            )
            sixteenth_size = (
                max(1, (quarter_size[0] + 3) // 4),
                max(1, (quarter_size[1] + 3) // 4),
            )
            self._motion_blur_sizes = (half_size, quarter_size, sixteenth_size)

            self._temporal_linear_depth_fbo = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._temporal_linear_depth_fbo)
            self._temporal_linear_depth_textures = [
                self._make_fur_target(
                    width, height, GL_R16F, GL_RED, GL_HALF_FLOAT, attachment,
                )
                for attachment in range(2)
            ]
            glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("Temporal linear-depth framebuffer is incomplete")

            self._temporal_half_fbo = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._temporal_half_fbo)
            self._temporal_half_textures = [
                self._make_fur_target(
                    *half_size, internal, fmt, dtype, attachment,
                )
                for attachment, (internal, fmt, dtype) in enumerate((
                    (GL_R8, GL_RED, GL_UNSIGNED_BYTE),
                    (GL_RG16F, GL_RG, GL_HALF_FLOAT),
                    (GL_R16F, GL_RED, GL_HALF_FLOAT),
                    (GL_R16F, GL_RED, GL_HALF_FLOAT),
                ))
            ]
            glBindTexture(GL_TEXTURE_2D, self._temporal_half_textures[0])
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glDrawBuffers(4, [GL_COLOR_ATTACHMENT0 + index for index in range(4)])
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("Temporal half-resolution framebuffer is incomplete")

            self._temporal_alpha_mask_fbo = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._temporal_alpha_mask_fbo)
            self._temporal_alpha_mask_texture = self._make_fur_target(
                *half_size, GL_R8, GL_RED, GL_UNSIGNED_BYTE, 0,
            )
            glBindTexture(GL_TEXTURE_2D, self._temporal_alpha_mask_texture)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glDrawBuffer(GL_COLOR_ATTACHMENT0)
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("Temporal accumulated-alpha mask framebuffer is incomplete")
            self._temporal_alpha_valid = False

            self._motion_blur_downsample_fbo = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._motion_blur_downsample_fbo)
            self._motion_blur_depth_velocity_texture = self._make_fur_target(
                *half_size, GL_RG16F, GL_RG, GL_HALF_FLOAT, 0,
            )
            glBindTexture(GL_TEXTURE_2D, self._motion_blur_depth_velocity_texture)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            self._motion_blur_half_velocity_texture = self._make_fur_target(
                *half_size, GL_RG16F, GL_RG, GL_HALF_FLOAT, 1,
            )
            glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("Motion-blur downsample framebuffer is incomplete")

            self._motion_blur_neighborhood_fbos = self._generated_ids(
                glGenFramebuffers(3),
            )
            self._motion_blur_neighborhood_textures = self._generated_ids(
                glGenTextures(3),
            )
            neighborhood_sizes = (quarter_size, sixteenth_size, sixteenth_size)
            for fbo, texture, target_size in zip(
                self._motion_blur_neighborhood_fbos,
                self._motion_blur_neighborhood_textures,
                neighborhood_sizes,
            ):
                glBindFramebuffer(GL_FRAMEBUFFER, fbo)
                glBindTexture(GL_TEXTURE_2D, texture)
                glTexImage2D(
                    GL_TEXTURE_2D, 0, GL_RG16F, *target_size, 0,
                    GL_RG, GL_HALF_FLOAT, None,
                )
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                glFramebufferTexture2D(
                    GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                    GL_TEXTURE_2D, texture, 0,
                )
                if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                    raise RuntimeError("Motion-blur neighborhood framebuffer is incomplete")

            self._motion_blur_scatter_fbos = self._generated_ids(glGenFramebuffers(2))
            self._motion_blur_scatter_textures = self._generated_ids(glGenTextures(2))
            for fbo, texture in zip(
                self._motion_blur_scatter_fbos, self._motion_blur_scatter_textures,
            ):
                glBindFramebuffer(GL_FRAMEBUFFER, fbo)
                glBindTexture(GL_TEXTURE_2D, texture)
                glTexImage2D(
                    GL_TEXTURE_2D, 0, GL_R8, *half_size, 0,
                    GL_RED, GL_UNSIGNED_BYTE, None,
                )
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                glFramebufferTexture2D(
                    GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                    GL_TEXTURE_2D, texture, 0,
                )
                if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                    raise RuntimeError("Motion-blur scatter framebuffer is incomplete")
            self._motion_blur_scatter_valid = [False, False]
            self._bloom_size = (width, height)
            glBindFramebuffer(GL_FRAMEBUFFER, self.defaultFramebufferObject())
        except Exception as ex:
            print(f"[viewport] bloom disabled: {ex}")
            self._bloom_supported = False
            try:
                self._delete_bloom_targets()
                glBindFramebuffer(GL_FRAMEBUFFER, self.defaultFramebufferObject())
            except Exception:
                pass

    def _build_motion_blur_scatter(self, target_index: int) -> None:
        """Build the retail motion/depth scatter signal for the next frame."""
        programs = (
            self._motion_blur_downsample_prog,
            self._motion_blur_neighborhood_half_prog,
            self._motion_blur_neighborhood_quarter_prog,
            self._motion_blur_gather_neighborhood_prog,
            self._motion_blur_scatter_prog,
        )
        if (
            not all(programs)
            or len(self._fur_material_textures) < 5
            or not self._fur_normal_texture
            or not self._scene_linear_depth_texture
            or not self._scene_velocity_texture
            or len(self._motion_blur_neighborhood_fbos) != 3
            or len(self._motion_blur_neighborhood_textures) != 3
            or len(self._motion_blur_scatter_fbos) != 2
            or len(self._motion_blur_scatter_textures) != 2
            or target_index not in (0, 1)
        ):
            return

        half_size, quarter_size, sixteenth_size = self._motion_blur_sizes
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)

        glBindFramebuffer(GL_FRAMEBUFFER, self._motion_blur_downsample_fbo)
        glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
        glViewport(0, 0, *half_size)
        glUseProgram(self._motion_blur_downsample_prog)
        for sampler, unit in (
            ('uMotion', 0), ('uOpaqueMotion', 1), ('uFurMask', 2),
            ('uFurDepth', 3), ('uSceneDepth', 4),
        ):
            location = glGetUniformLocation(self._motion_blur_downsample_prog, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        _set_uniform_2f(
            self._motion_blur_downsample_prog, 'uOutputInvSize',
            1.0 / half_size[0], 1.0 / half_size[1],
        )
        _set_uniform_1f(
            self._motion_blur_downsample_prog, 'uShutterScale',
            0.14122892916202545,
        )
        for unit, texture in enumerate((
            self._fur_material_textures[4], self._scene_velocity_texture,
            self._fur_normal_texture, self._fur_material_textures[2],
            self._scene_linear_depth_texture,
        )):
            glActiveTexture(GL_TEXTURE0 + unit)
            glBindTexture(GL_TEXTURE_2D, texture)
        glBindVertexArray(self._grid_vao)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)

        neighborhood_stages = (
            (
                self._motion_blur_neighborhood_half_prog,
                self._motion_blur_neighborhood_fbos[0], quarter_size,
                self._motion_blur_half_velocity_texture, 0.14122892916202545,
            ),
            (
                self._motion_blur_neighborhood_quarter_prog,
                self._motion_blur_neighborhood_fbos[1], sixteenth_size,
                self._motion_blur_neighborhood_textures[0], None,
            ),
            (
                self._motion_blur_gather_neighborhood_prog,
                self._motion_blur_neighborhood_fbos[2], sixteenth_size,
                self._motion_blur_neighborhood_textures[1], None,
            ),
        )
        for program, fbo, target_size, source, velocity_scale in neighborhood_stages:
            glBindFramebuffer(GL_FRAMEBUFFER, fbo)
            glDrawBuffer(GL_COLOR_ATTACHMENT0)
            glViewport(0, 0, *target_size)
            glUseProgram(program)
            location = glGetUniformLocation(program, 'uVelocity')
            if location >= 0:
                glUniform1i(location, 0)
            _set_uniform_2f(
                program, 'uOutputInvSize',
                1.0 / target_size[0], 1.0 / target_size[1],
            )
            if velocity_scale is not None:
                _set_uniform_1f(program, 'uVelocityScale', velocity_scale)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, source)
            glDrawArrays(GL_TRIANGLES, 0, self._grid_count)

        glBindFramebuffer(GL_FRAMEBUFFER, self._motion_blur_scatter_fbos[target_index])
        glDrawBuffer(GL_COLOR_ATTACHMENT0)
        glViewport(0, 0, *half_size)
        glUseProgram(self._motion_blur_scatter_prog)
        for sampler, unit in (('uDepthVelocity', 0), ('uNeighborhoodVelocity', 1)):
            location = glGetUniformLocation(self._motion_blur_scatter_prog, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        _set_uniform_2f(
            self._motion_blur_scatter_prog, 'uOutputInvSize',
            1.0 / half_size[0], 1.0 / half_size[1],
        )
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._motion_blur_depth_velocity_texture)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self._motion_blur_neighborhood_textures[2])
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
        self._motion_blur_scatter_valid[target_index] = True

        glBindVertexArray(0)
        for unit in range(4, -1, -1):
            glActiveTexture(GL_TEXTURE0 + unit)
            glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glEnable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

    def _temporal_frame_signature(self):
        return (
            self._bloom_size,
            bool(self._show_fur),
            int(getattr(self, '_active_lod', 0)),
            len(self._gpu_meshes),
        )

    def _sync_temporal_signature(self) -> None:
        signature = self._temporal_frame_signature()
        if signature != self._temporal_signature:
            self._temporal_signature = signature
            self._temporal_sample_count = 0
            self._motion_blur_scatter_valid = [False, False]
            self._temporal_disocclusion_valid = [False, False]
            self._temporal_alpha_valid = False

    def _build_temporal_disocclusion(
        self, target_index: int, projection, view,
        previous_projection, previous_view,
    ) -> None:
        """Build base and accumulated-alpha disocclusion plus half outputs."""
        programs = (
            self._temporal_linear_depth_prog,
            self._temporal_half_base_prog,
            self._temporal_alpha_mask_prog,
            self._temporal_alpha_half_prog,
            self._temporal_disocclusion_prog,
        )
        if (
            not all(programs)
            or len(self._temporal_disocclusion_fbos) != 2
            or len(self._temporal_disocclusion_textures) != 2
            or len(self._temporal_depth_textures) != 2
            or len(self._motion_blur_scatter_textures) != 2
            or len(self._temporal_linear_depth_textures) != 2
            or len(self._temporal_half_textures) != 4
            or not self._temporal_linear_depth_fbo
            or not self._temporal_half_fbo
            or not self._temporal_alpha_mask_fbo
            or not self._temporal_alpha_mask_texture
            or target_index not in (0, 1)
            or not self._scene_linear_depth_texture
            or not self._scene_velocity_texture
        ):
            self._temporal_alpha_valid = False
            return

        previous_index = 1 - target_index
        has_fur_motion = bool(
            self._fur_deferred_active
            and len(self._fur_material_textures) >= 5
            and self._fur_material_textures[2]
            and self._fur_material_textures[4]
            and self._fur_normal_texture
        )
        has_history = bool(
            self._temporal_sample_count > 0
            and self._temporal_disocclusion_valid[previous_index]
            and self._motion_blur_scatter_valid[target_index]
        )
        projection = np.asarray(projection, dtype=np.float32)
        view = np.asarray(view, dtype=np.float32)
        previous_projection = np.asarray(
            projection if previous_projection is None else previous_projection,
            dtype=np.float32,
        )
        previous_view = np.asarray(
            view if previous_view is None else previous_view,
            dtype=np.float32,
        )
        current_to_previous = (
            previous_view.astype(np.float64)
            @ np.linalg.inv(view.astype(np.float64))
        ).astype(np.float32)
        current_to_previous_rotation = current_to_previous[:3, :3].copy()

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glBindVertexArray(self._grid_vao)

        glBindFramebuffer(GL_FRAMEBUFFER, self._temporal_linear_depth_fbo)
        glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
        glViewport(0, 0, *self._bloom_size)
        glUseProgram(self._temporal_linear_depth_prog)
        for sampler, unit in (
            ('uFurMask', 0), ('uFurDepth', 1), ('uSceneDepth', 2),
        ):
            location = glGetUniformLocation(self._temporal_linear_depth_prog, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        _set_uniform_bool(
            self._temporal_linear_depth_prog, 'uHasFurDepth', has_fur_motion,
        )
        for unit, texture in enumerate((
            self._fur_normal_texture if has_fur_motion else 0,
            self._fur_material_textures[2] if has_fur_motion else 0,
            self._scene_linear_depth_texture,
        )):
            glActiveTexture(GL_TEXTURE0 + unit)
            glBindTexture(GL_TEXTURE_2D, texture)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)

        def draw_full_disocclusion(
            linear_depth: int, use_fur_motion: bool,
            motion_threshold: float, require_alpha_flag: bool,
        ) -> None:
            glBindFramebuffer(
                GL_FRAMEBUFFER, self._temporal_disocclusion_fbos[target_index],
            )
            glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
            glViewport(0, 0, *self._bloom_size)
            glUseProgram(self._temporal_disocclusion_prog)
            for sampler, unit in (
                ('uMotion', 0), ('uFurMask', 1), ('uLinearDepth', 2),
                ('uHistoryDepthMotion', 3), ('uMotionBlurScatter', 4),
                ('uAccAlphaFlags', 5), ('uOpaqueMotion', 6),
            ):
                location = glGetUniformLocation(
                    self._temporal_disocclusion_prog, sampler,
                )
                if location >= 0:
                    glUniform1i(location, unit)
            _set_uniform_mat4(
                self._temporal_disocclusion_prog,
                'uCurrentToPreviousView', current_to_previous,
            )
            _set_uniform_mat3(
                self._temporal_disocclusion_prog,
                'uCurrentToPreviousRotation', current_to_previous_rotation,
            )
            _set_uniform_mat4(
                self._temporal_disocclusion_prog,
                'uPreviousProjection', previous_projection,
            )
            _set_uniform_4f(
                self._temporal_disocclusion_prog,
                'uCurrentProjection',
                projection[0, 0], projection[1, 1],
                projection[0, 2], projection[1, 2],
            )
            _set_uniform_2f(
                self._temporal_disocclusion_prog,
                'uDimensions', *self._bloom_size,
            )
            _set_uniform_1f(
                self._temporal_disocclusion_prog, 'uDepthBase',
                TEMPORAL_DISOCCLUSION_CAPTURE_DEPTH_BASE,
            )
            _set_uniform_1f(
                self._temporal_disocclusion_prog, 'uDepthSlope',
                TEMPORAL_DISOCCLUSION_CAPTURE_DEPTH_SLOPE,
            )
            _set_uniform_1f(
                self._temporal_disocclusion_prog,
                'uMotionThreshold', motion_threshold,
            )
            _set_uniform_1f(
                self._temporal_disocclusion_prog, 'uCameraMotionScale',
                temporal_disocclusion_camera_scale(self._bloom_size[0]),
            )
            _set_uniform_bool(
                self._temporal_disocclusion_prog,
                'uHasFurMotion', use_fur_motion,
            )
            _set_uniform_bool(
                self._temporal_disocclusion_prog,
                'uHasOpaqueMotion', bool(self._scene_velocity_texture),
            )
            _set_uniform_bool(
                self._temporal_disocclusion_prog, 'uHasHistory', has_history,
            )
            _set_uniform_bool(
                self._temporal_disocclusion_prog,
                'uRequireAccAlphaFlag', require_alpha_flag,
            )
            textures = (
                self._fur_material_textures[4] if use_fur_motion else 0,
                self._fur_normal_texture if use_fur_motion else 0,
                linear_depth,
                self._temporal_depth_textures[previous_index] if has_history else 0,
                self._motion_blur_scatter_textures[target_index]
                if self._motion_blur_scatter_valid[target_index] else 0,
                self._temporal_alpha_mask_texture if require_alpha_flag else 0,
                self._scene_velocity_texture,
            )
            for unit, texture in enumerate(textures):
                glActiveTexture(GL_TEXTURE0 + unit)
                glBindTexture(GL_TEXTURE_2D, texture)
            glDrawArrays(GL_TRIANGLES, 0, self._grid_count)

        # Event 16262 is the opaque/base pass. The captured base half-depth
        # inputs are the exact four-texel extrema of this pre-alpha depth.
        draw_full_disocclusion(
            self._temporal_linear_depth_textures[0], False,
            TEMPORAL_DISOCCLUSION_CAPTURE_MOTION_THRESHOLD, False,
        )

        half_size = self._motion_blur_sizes[0]
        glBindFramebuffer(GL_FRAMEBUFFER, self._temporal_half_fbo)
        glDrawBuffers(4, [GL_COLOR_ATTACHMENT0 + index for index in range(4)])
        glViewport(0, 0, *half_size)
        glUseProgram(self._temporal_half_base_prog)
        for sampler, unit in (('uFullDisocclusion', 0), ('uOpaqueDepth', 1)):
            location = glGetUniformLocation(self._temporal_half_base_prog, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        _set_uniform_2f(
            self._temporal_half_base_prog, 'uFullDimensions', *self._bloom_size,
        )
        for unit, texture in enumerate((
            self._temporal_disocclusion_textures[target_index],
            self._temporal_linear_depth_textures[0],
        )):
            glActiveTexture(GL_TEXTURE0 + unit)
            glBindTexture(GL_TEXTURE_2D, texture)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)

        # Event 18687 compares the current post-alpha R16F depth against the
        # pre-alpha four-texel minimum. This R8 target is the exact t10 family
        # consumed by the final TAA apply.
        glBindFramebuffer(GL_FRAMEBUFFER, self._temporal_alpha_mask_fbo)
        glDrawBuffer(GL_COLOR_ATTACHMENT0)
        glViewport(0, 0, *half_size)
        glUseProgram(self._temporal_alpha_mask_prog)
        for sampler, unit in (('uComposedDepth', 0), ('uOpaqueMinimumDepth', 1)):
            location = glGetUniformLocation(self._temporal_alpha_mask_prog, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        _set_uniform_2f(
            self._temporal_alpha_mask_prog, 'uFullDimensions', *self._bloom_size,
        )
        for unit, texture in enumerate((
            self._temporal_linear_depth_textures[1],
            self._temporal_half_textures[3],
        )):
            glActiveTexture(GL_TEXTURE0 + unit)
            glBindTexture(GL_TEXTURE_2D, texture)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
        self._temporal_alpha_valid = True

        if has_fur_motion:
            # Events 18695/18704 use a packed tile queue. A full-screen draw
            # with a fragment discard on the same mask is output-equivalent:
            # unflagged pixels retain the base targets and flagged pixels use
            # the captured accumulated-alpha threshold.
            draw_full_disocclusion(
                self._temporal_linear_depth_textures[1], True,
                TEMPORAL_ACC_ALPHA_MOTION_THRESHOLD, True,
            )

            glBindFramebuffer(GL_FRAMEBUFFER, self._temporal_half_fbo)
            glDrawBuffers(4, [GL_COLOR_ATTACHMENT0 + index for index in range(4)])
            glViewport(0, 0, *half_size)
            glUseProgram(self._temporal_alpha_half_prog)
            for sampler, unit in (
                ('uFullDisocclusion', 0), ('uComposedDepth', 1),
                ('uFurVelocity', 2), ('uOpaqueVelocity', 3),
                ('uFurMask', 4), ('uAlphaMask', 5),
            ):
                location = glGetUniformLocation(
                    self._temporal_alpha_half_prog, sampler,
                )
                if location >= 0:
                    glUniform1i(location, unit)
            _set_uniform_2f(
                self._temporal_alpha_half_prog,
                'uFullDimensions', *self._bloom_size,
            )
            for unit, texture in enumerate((
                self._temporal_disocclusion_textures[target_index],
                self._temporal_linear_depth_textures[1],
                self._fur_material_textures[4],
                self._scene_velocity_texture,
                self._fur_normal_texture,
                self._temporal_alpha_mask_texture,
            )):
                glActiveTexture(GL_TEXTURE0 + unit)
                glBindTexture(GL_TEXTURE_2D, texture)
            glDrawArrays(GL_TRIANGLES, 0, self._grid_count)

        glBindVertexArray(0)
        for unit in range(6, -1, -1):
            glActiveTexture(GL_TEXTURE0 + unit)
            glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        self._temporal_disocclusion_valid[target_index] = True
        glEnable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

    def _accumulate_temporal_scene(self, previous_jitter=(0.0, 0.0)):
        """Accumulate stochastic fur, reprojecting its proven motion target."""
        if (
            not self._temporal_accum_prog
            or len(self._temporal_fbos) != 2
            or len(self._temporal_depth_textures) != 2
        ):
            self._display_scene_texture = self._current_scene_texture or self._hdr_color_buffers[0]
            return
        self._sync_temporal_signature()

        target_index = self._temporal_sample_count % 2
        previous_index = 1 - target_index
        temporal_misc = self.temporal_aa_misc()
        glBindFramebuffer(GL_FRAMEBUFFER, self._temporal_fbos[target_index])
        glDrawBuffer(GL_COLOR_ATTACHMENT0)
        glViewport(0, 0, *self._bloom_size)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glUseProgram(self._temporal_accum_prog)
        for sampler, unit in (
            ('uCurrent', 0), ('uHistory', 1), ('uMotion', 2),
            ('uFurMask', 3), ('uLinearDepth', 4),
            ('uAlphaMask', 5), ('uDisocclusion', 6),
            ('uOpaqueMotion', 7), ('uStencil', 8),
        ):
            location = glGetUniformLocation(self._temporal_accum_prog, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        _set_uniform_1f(
            self._temporal_accum_prog, 'uHistoryWarmup', temporal_misc[3],
        )
        _set_uniform_1f(
            self._temporal_accum_prog, 'uTemporalMinimumRejection',
            temporal_misc[0],
        )
        _set_uniform_1f(
            self._temporal_accum_prog, 'uNonopaqueStencilRejection',
            temporal_misc[1],
        )
        _set_uniform_1f(
            self._temporal_accum_prog, 'uTemporalHdrScale', temporal_misc[2],
        )
        _set_uniform_4f(
            self._temporal_accum_prog, 'uTemporalDither',
            *temporal_dither_constants(self._temporal_sample_count),
        )
        _set_uniform_2f(
            self._temporal_accum_prog, 'uTemporalFilterOffsetPixels',
            *_temporal_filter_offset_pixels(
                self._current_temporal_jitter,
                upper_left=self._native_raster_active,
            ),
        )
        _set_uniform_2f(
            self._temporal_accum_prog, 'uHistoryJitterOffset',
            *_temporal_history_jitter_offset(
                self._current_temporal_jitter, previous_jitter,
                self._bloom_size,
                upper_left=self._native_raster_active,
            ),
        )
        has_fur_motion = bool(
            self._fur_deferred_active
            and len(self._fur_material_textures) >= 5
            and self._fur_material_textures[2]
            and self._fur_material_textures[4]
            and self._fur_normal_texture
        )
        _set_uniform_bool(
            self._temporal_accum_prog, 'uHasFurMotion', has_fur_motion,
        )
        has_opaque_motion = bool(self._scene_velocity_texture)
        has_stencil = bool(self._scene_stencil_texture)
        _set_uniform_bool(
            self._temporal_accum_prog, 'uHasOpaqueMotion', has_opaque_motion,
        )
        _set_uniform_bool(
            self._temporal_accum_prog, 'uHasStencil', has_stencil,
        )
        _set_uniform_bool(
            self._temporal_accum_prog, 'uHasTemporalHistory',
            self._temporal_sample_count > 0,
        )
        _set_uniform_bool(
            self._temporal_accum_prog, 'uHasAlphaMask',
            self._temporal_alpha_valid,
        )
        has_disocclusion = bool(
            len(self._temporal_disocclusion_textures) == 2
            and self._temporal_disocclusion_valid[target_index]
        )
        _set_uniform_bool(
            self._temporal_accum_prog,
            'uHasDisocclusion', has_disocclusion,
        )
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(
            GL_TEXTURE_2D,
            self._current_scene_texture or self._hdr_color_buffers[0],
        )
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self._temporal_textures[previous_index])
        glActiveTexture(GL_TEXTURE2)
        glBindTexture(
            GL_TEXTURE_2D,
            self._fur_material_textures[4] if has_fur_motion else 0,
        )
        glActiveTexture(GL_TEXTURE3)
        glBindTexture(
            GL_TEXTURE_2D, self._fur_normal_texture if has_fur_motion else 0,
        )
        glActiveTexture(GL_TEXTURE4)
        glBindTexture(
            GL_TEXTURE_2D,
            self._temporal_linear_depth_textures[1]
            if len(self._temporal_linear_depth_textures) == 2 else 0,
        )
        glActiveTexture(GL_TEXTURE5)
        glBindTexture(
            GL_TEXTURE_2D,
            self._temporal_alpha_mask_texture if self._temporal_alpha_valid else 0,
        )
        glActiveTexture(GL_TEXTURE6)
        glBindTexture(
            GL_TEXTURE_2D,
            self._temporal_disocclusion_textures[target_index]
            if has_disocclusion else 0,
        )
        glActiveTexture(GL_TEXTURE7)
        glBindTexture(
            GL_TEXTURE_2D,
            self._scene_velocity_texture if has_opaque_motion else 0,
        )
        glActiveTexture(GL_TEXTURE8)
        glBindTexture(
            GL_TEXTURE_2D,
            self._scene_stencil_texture if has_stencil else 0,
        )
        glBindVertexArray(self._grid_vao)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
        glBindVertexArray(0)
        for unit in range(8, 0, -1):
            glActiveTexture(GL_TEXTURE0 + unit)
            glBindTexture(GL_TEXTURE_2D, 0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, 0)
        self._display_scene_texture = self._temporal_textures[target_index]
        self._temporal_sample_count += 1
        glEnable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

    def _prepare_fur_lighting(self, projection, view, light_dir):
        """Decode stored native values, then evaluate the asset-preview lights."""
        material, albedo, depth, strand, _motion = self._fur_material_textures
        scene = self._fur_scene_gpu if self._fur_scene_is_current() else None
        lighting_program = self._fur_scene_program if scene is not None else self._fur_lighting_prog
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glViewport(0, 0, *self._bloom_size)
        stages = (
            (self._fur_decode_fbo, self._fur_decode_prog, (
                ('uMaterial', material), ('uStrand', strand), ('uLinearDepth', depth),
                ('uOpaqueDepth', self._scene_linear_depth_texture))),
            (self._fur_lighting_fbo, lighting_program, (
                ('uMaterial', material), ('uStrand', strand), ('uAlbedoOcclusion', albedo),
                ('uFurGBuffer', self._fur_gbuffer_texture), ('uFurNormalMask', self._fur_normal_texture))),
        )
        for fbo, program, textures in stages:
            glBindFramebuffer(GL_FRAMEBUFFER, fbo)
            glUseProgram(program)
            for unit, (sampler, texture) in enumerate(textures):
                glUniform1i(glGetUniformLocation(program, sampler), unit)
                glActiveTexture(GL_TEXTURE0 + unit)
                glBindTexture(GL_TEXTURE_2D, texture)
            if program == lighting_program:
                # Native view axes are right/down/forward; GL uses right/up/back.
                native_to_world = view[:3, :3].T @ np.diag([1.0, -1.0, -1.0])
                _set_uniform_mat3(program, 'uViewToWorld', native_to_world.astype(np.float32))
                scale = np.array([projection[0, 0], projection[1, 1]], dtype=np.float32)
                offset = np.array([projection[0, 2], -projection[1, 2]], dtype=np.float32)
                screen = np.concatenate((2.0 / scale, (offset - 1.0) / scale))
                glUniform4f(glGetUniformLocation(program, 'uScreenToView'), *screen)
                _set_uniform_2f(program, 'uViewportSize', *self._bloom_size)
                _set_uniform_3f(program, 'uLightDir', *light_dir)
                _set_uniform_3f(program, 'uCameraPosition', *self.camera.eye_position())
                _set_uniform_bool(program, 'uFurContactEnabled', self._fur_contact_enabled)
                self._set_fur_temporal_uniforms(program)
                _set_uniform_bool(program, 'uHasFurEnvironment', bool((scene is not None or self._fur_environment_texture) and self._fur_brdf_texture))
                for unit, sampler, target, texture in (
                    (5, 'uFurEnvironment', GL_TEXTURE_CUBE_MAP, self._fur_environment_texture),
                    (6, 'uFurBrdfLut', GL_TEXTURE_2D, self._fur_brdf_texture),
                ):
                    glUniform1i(glGetUniformLocation(program, sampler), unit)
                    glActiveTexture(GL_TEXTURE0 + unit)
                    glBindTexture(target, texture)
                if scene is not None:
                    scene.bind(program)
            glBindVertexArray(self._grid_vao)
            glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
        glBindVertexArray(0)
        if scene is not None:
            scene.unbind()
        for unit in range(6, -1, -1):
            glActiveTexture(GL_TEXTURE0 + unit)
            glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE5)
        glBindTexture(GL_TEXTURE_CUBE_MAP, 0)
        glActiveTexture(GL_TEXTURE0)

    def _resolve_fur_lighting(self, projection, view, light_dir):
        """Resolve key contact visibility before HairDenoise and temporal history."""
        self._current_scene_fbo = self._hdr_fbo
        self._current_scene_texture = self._hdr_color_buffers[0]
        if not self._fur_deferred_active:
            return
        self._prepare_fur_lighting(projection, view, light_dir)
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self._hdr_fbo)
        glReadBuffer(GL_COLOR_ATTACHMENT0)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self._fur_contact_fbo)
        glDrawBuffer(GL_COLOR_ATTACHMENT0)
        glBlitFramebuffer(0, 0, *self._bloom_size, 0, 0, *self._bloom_size,
                          GL_COLOR_BUFFER_BIT, GL_NEAREST)
        glBindFramebuffer(GL_FRAMEBUFFER, self._fur_contact_fbo)
        glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
        glViewport(0, 0, *self._bloom_size)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        program = self._fur_contact_prog
        glUseProgram(program)
        for sampler, unit in (('uScene', 0), ('uFurKeyLight', 1),
                              ('uFurGBuffer', 2), ('uFurNormalMask', 3)):
            location = glGetUniformLocation(program, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        _set_uniform_mat3(program, 'uViewRotation', view[:3, :3])
        _set_uniform_2f(program, 'uProjectionScale', projection[0, 0], projection[1, 1])
        _set_uniform_2f(program, 'uProjectionOffset', projection[0, 2], -projection[1, 2])
        _set_uniform_2f(program, 'uViewportSize', *self._bloom_size)
        _set_uniform_3f(program, 'uWorldLightDir', *light_dir)
        self._set_fur_temporal_uniforms(program)
        # Scene lighting includes contact before the combined material resolve.
        _set_uniform_bool(program, 'uFurContactEnabled', self._fur_contact_enabled
                          and not self._fur_scene_is_current() and not getattr(self, '_ortho', False))
        for unit, texture in enumerate((self._fur_indirect_texture, self._fur_key_texture,
                                        self._fur_gbuffer_texture, self._fur_normal_texture)):
            glActiveTexture(GL_TEXTURE0 + unit)
            glBindTexture(GL_TEXTURE_2D, texture)
        glBindVertexArray(self._grid_vao)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
        glBindVertexArray(0)
        for unit in (GL_TEXTURE3, GL_TEXTURE2, GL_TEXTURE1, GL_TEXTURE0):
            glActiveTexture(unit)
            glBindTexture(GL_TEXTURE_2D, 0)
        self._current_scene_fbo = self._fur_contact_fbo
        self._current_scene_texture = self._fur_contact_texture
        glEnable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

    def _denoise_fur_scene(self, projection, view):
        """Apply the captured tangent/depth/mask-gated HairDenoise gather."""
        if not (
            self._fur_denoise_prog and self._fur_denoise_fbo
            and self._fur_denoise_texture and self._fur_gbuffer_texture
            and self._fur_normal_texture and self._show_fur
            and self._fur_denoise_enabled and self._fur_deferred_active
        ):
            return
        # Retail's destination already contains the other shading models;
        # CS_HairDenoise writes only worklisted hair pixels. Preserve that
        # behavior so non-fur scene color does not take an extra FP16 roundtrip.
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self._current_scene_fbo)
        glReadBuffer(GL_COLOR_ATTACHMENT0)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self._fur_denoise_fbo)
        glDrawBuffer(GL_COLOR_ATTACHMENT0)
        glBlitFramebuffer(
            0, 0, self._bloom_size[0], self._bloom_size[1],
            0, 0, self._bloom_size[0], self._bloom_size[1],
            GL_COLOR_BUFFER_BIT, GL_NEAREST,
        )
        glBindFramebuffer(GL_FRAMEBUFFER, self._fur_denoise_fbo)
        glViewport(0, 0, *self._bloom_size)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glUseProgram(self._fur_denoise_prog)
        for sampler, unit in (
            ('uScene', 0), ('uFurGBuffer', 1), ('uFurNormalMask', 2),
            ('uGatherAddress', 4),
        ):
            location = glGetUniformLocation(self._fur_denoise_prog, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        _set_uniform_mat3(
            self._fur_denoise_prog, 'uViewRotation', view[:3, :3],
        )
        _set_uniform_2f(
            self._fur_denoise_prog, 'uProjectionScale',
            projection[0, 0], projection[1, 1],
        )
        _set_uniform_2f(
            self._fur_denoise_prog, 'uProjectionOffset',
            projection[0, 2], -projection[1, 2],
        )
        _set_uniform_2f(
            self._fur_denoise_prog, 'uViewportSize', *self._bloom_size,
        )
        self._set_fur_temporal_uniforms(self._fur_denoise_prog)
        _set_uniform_bool(self._fur_denoise_prog, 'uHasSceneProjection', False)
        _set_uniform_bool(self._fur_denoise_prog, 'uHasSceneDenoiseMask', False)
        _set_uniform_bool(self._fur_denoise_prog, 'uHasGatherAddress', bool(self._fur_gather_address_texture))
        if self._fur_scene_is_current():
            self._fur_scene_gpu.bind_denoise(self._fur_denoise_prog)
        for unit, texture_id in (
            (GL_TEXTURE0, self._current_scene_texture),
            (GL_TEXTURE1, self._fur_gbuffer_texture),
            (GL_TEXTURE2, self._fur_normal_texture),
            (GL_TEXTURE4, self._fur_gather_address_texture),
        ):
            glActiveTexture(unit)
            glBindTexture(GL_TEXTURE_2D, texture_id)
        glBindVertexArray(self._grid_vao)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
        glBindVertexArray(0)
        for unit in (GL_TEXTURE4, GL_TEXTURE3, GL_TEXTURE2, GL_TEXTURE1, GL_TEXTURE0):
            glActiveTexture(unit)
            glBindTexture(GL_TEXTURE_2D, 0)
        self._current_scene_texture = self._fur_denoise_texture
        self._current_scene_fbo = self._fur_denoise_fbo
        glEnable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

    def _composite_bloom(self):
        """Blur the bright buffer, tone-map HDR, and composite to the Qt framebuffer."""
        glViewport(0, 0, *self._bloom_size)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glUseProgram(self._blur_prog)
        loc = glGetUniformLocation(self._blur_prog, 'uImage')
        if loc >= 0:
            glUniform1i(loc, 0)
        horizontal = True
        first_pass = True
        for _ in range(8):
            target_index = 1 if horizontal else 0
            glBindFramebuffer(GL_FRAMEBUFFER, self._pingpong_fbos[target_index])
            _set_uniform_bool(self._blur_prog, 'uHorizontal', horizontal)
            glActiveTexture(GL_TEXTURE0)
            source = self._hdr_color_buffers[1] if first_pass \
                else self._pingpong_textures[0 if horizontal else 1]
            glBindTexture(GL_TEXTURE_2D, source)
            glBindVertexArray(self._grid_vao)
            glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
            horizontal = not horizontal
            first_pass = False

        glBindFramebuffer(GL_FRAMEBUFFER, self.defaultFramebufferObject())
        if self._native_raster_active:
            # QOpenGLWidget presents its backing FBO with Qt's conventional
            # lower-left GL row ownership. Keep native offscreen targets
            # upper-left, then write this one boundary in Qt's convention.
            glClipControl(GL_LOWER_LEFT, GL_ZERO_TO_ONE)
        glViewport(0, 0, *self._bloom_size)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glUseProgram(self._composite_prog)
        for sampler, unit in (('uScene', 0), ('uBloom', 1)):
            loc = glGetUniformLocation(self._composite_prog, sampler)
            if loc >= 0:
                glUniform1i(loc, unit)
        _set_uniform_bool(self._composite_prog, 'uBloomEnabled', self._bloom_enabled)
        exposure, bloom_strength = _postprocess_settings(any(
            gpu.is_retail_blizar_lava for gpu in self._gpu_meshes
        ))
        _set_uniform_1f(self._composite_prog, 'uBloomStrength', bloom_strength)
        _set_uniform_1f(self._composite_prog, 'uExposure', exposure)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(
            GL_TEXTURE_2D,
            self._display_scene_texture or self._hdr_color_buffers[0],
        )
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self._pingpong_textures[0 if horizontal else 1])
        glBindVertexArray(self._grid_vao)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
        glBindVertexArray(0)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glEnable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        self._apply_raster_convention()

    def _composite_fur_oit(self):
        """Composite order-independent fur accumulation into HDR scene color."""
        glDrawBuffer(GL_COLOR_ATTACHMENT0)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        glUseProgram(self._fur_oit_composite_prog)
        for sampler, unit in (('uFurAccum', 0), ('uFurReveal', 1)):
            location = glGetUniformLocation(self._fur_oit_composite_prog, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        for unit, tex_id in zip((GL_TEXTURE0, GL_TEXTURE1), self._fur_oit_textures):
            glActiveTexture(unit)
            glBindTexture(GL_TEXTURE_2D, tex_id)
        glBindVertexArray(self._grid_vao)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
        glBindVertexArray(0)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
        glEnable(GL_DEPTH_TEST)

    def _snapshot_opaque_depth_for_fur(self, framebuffer_size) -> int:
        """Copy opaque depth to a detached texture safe for shader sampling."""
        self._fur_depth_snapshot_ready = False
        texture_id = self._fur_scene_depth_texture
        if not texture_id or self._bloom_size != tuple(framebuffer_size):
            return 0
        try:
            glActiveTexture(GL_TEXTURE2)
            glBindTexture(GL_TEXTURE_2D, texture_id)
            glCopyTexSubImage2D(
                GL_TEXTURE_2D, 0, 0, 0, 0, 0,
                int(framebuffer_size[0]), int(framebuffer_size[1]),
            )
            glBindTexture(GL_TEXTURE_2D, 0)
            glActiveTexture(GL_TEXTURE0)
            self._fur_depth_snapshot_ready = True
            return texture_id
        except Exception as ex:
            print(f"[viewport] fur depth snapshot failed: {ex}")
            try:
                glBindTexture(GL_TEXTURE_2D, 0)
                glActiveTexture(GL_TEXTURE0)
            except Exception:
                pass
            return 0

    def _draw_fur_strands(self, mvp, previous_mvp, model, normal_mat, eye,
                          light_dir, fill_dir, wind_time,
                          previous_wind_time, near_plane):
        """Render one stochastic opaque sample of the recovered shell pass."""
        if not self._fur_shader_prog or not self._fur_layer_texture:
            return
        fur_meshes = [
            mesh for mesh in self._gpu_meshes
            if _can_draw_fur_strands(
                show_fur=self._show_fur,
                wireframe=self._wireframe,
                is_composite_shell=mesh.is_composite_shell,
                albedo_tex_id=mesh.texture_id,
                control_tex_id=mesh.fur_control_tex_id,
            )
            and mesh.fur_length > 0.0
        ]
        if not fur_meshes:
            return

        program = self._fur_material_prog if self._fur_deferred_active else self._fur_shader_prog
        glUseProgram(program)
        _set_uniform_mat4(program, 'uMVP', mvp)
        _set_uniform_mat4(program, 'uPreviousMVP', previous_mvp)
        _set_uniform_mat4(program, 'uModel', model)
        _set_uniform_mat3(program, 'uNormal', normal_mat)
        _set_uniform_3f(program, 'uEye', *eye)
        _set_uniform_3f(program, 'uLightDir', *light_dir)
        _set_uniform_3f(program, 'uFillDir', *fill_dir)
        _set_uniform_1f(
            program, 'uFurWindStrength', self._fur_wind_strength,
        )
        _set_uniform_3f(
            program, 'uFurWindVector', *self._fur_wind_vector,
        )
        _set_uniform_1f(
            program, 'uFurWindTime', wind_time,
        )
        _set_uniform_1f(
            program, 'uPreviousFurWindTime', previous_wind_time,
        )
        _set_uniform_1f(program, 'uMotionNearPlane', near_plane)
        _set_uniform_1f(
            program, 'uFurWindObjectPhase',
            self._fur_wind_object_phase,
        )
        _set_uniform_2f(
            program, 'uViewportSize',
            *self._framebuffer_size(),
        )
        self._set_fur_temporal_uniforms(program)
        for sampler, unit in (
            ('uFurAlbedo', 0), ('uFurControl', 1), ('uFurLayers', 2),
            ('uFurSpecular', 3),
            ('uFurEnvironment', 4), ('uFurBrdfLut', 5),
        ):
            location = glGetUniformLocation(program, sampler)
            if location >= 0:
                glUniform1i(location, unit)

        glDisable(GL_BLEND)
        glDepthMask(GL_TRUE)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glActiveTexture(GL_TEXTURE2)
        glBindTexture(GL_TEXTURE_2D_ARRAY, self._fur_layer_texture)
        has_fur_environment = (
            self._fur_environment_texture > 0 and self._fur_brdf_texture > 0
        )
        _set_uniform_bool(
            program, 'uHasFurEnvironment', has_fur_environment,
        )
        glActiveTexture(GL_TEXTURE4)
        glBindTexture(
            GL_TEXTURE_CUBE_MAP,
            self._fur_environment_texture if has_fur_environment else 0,
        )
        glActiveTexture(GL_TEXTURE5)
        glBindTexture(
            GL_TEXTURE_2D,
            self._fur_brdf_texture if has_fur_environment else 0,
        )
        for mesh in fur_meshes:
            _set_uniform_1f(program, 'uFurLength', mesh.fur_length)
            _set_uniform_1f(
                program, 'uFurWindRadius', mesh.fur_wind_radius,
            )
            _set_uniform_1f(
                program, 'uFurWindTurbulence',
                mesh.fur_wind_turbulence,
            )
            _set_uniform_1f(program, 'uFurDensity', mesh.fur_density)
            _set_uniform_1f(
                program, 'uFurOffsetScale',
                mesh.fur_offset_scale,
            )
            _set_uniform_1f(
                program, 'uFurGlossScale', mesh.fur_gloss_scale,
            )
            _set_uniform_1f(
                program, 'uFurSpecularScale',
                mesh.fur_specular_scale,
            )
            _set_uniform_1f(
                program, 'uFurTransmittanceScale',
                mesh.fur_transmittance_scale,
            )
            _set_uniform_1f(
                program, 'uFurWetness', self._fur_wetness,
            )
            _set_uniform_bool(
                program, 'uHasFurSpecular',
                mesh.specular_tex_id > 0,
            )
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, mesh.texture_id)
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, mesh.fur_control_tex_id)
            glActiveTexture(GL_TEXTURE3)
            glBindTexture(GL_TEXTURE_2D, mesh.specular_tex_id)
            glBindVertexArray(mesh.vao)
            layer_count = max(1, int(mesh.fur_layer_count or 32))
            location = glGetUniformLocation(program, 'uLayerCount')
            if location >= 0:
                glUniform1i(location, layer_count)
            layer_location = glGetUniformLocation(
                program, 'uReverseLayer',
            )
            debug_layer = self._fur_debug_reverse_layer
            reverse_layers = (
                [max(0, min(int(debug_layer), layer_count - 1))]
                if debug_layer is not None
                else range(layer_count - 1, -1, -1)
            )
            for reverse_layer in reverse_layers:
                if layer_location >= 0:
                    glUniform1i(layer_location, reverse_layer)
                glDrawElements(
                    GL_TRIANGLES, mesh.index_count, mesh.index_type, None,
                )
        glBindVertexArray(0)
        glActiveTexture(GL_TEXTURE5)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE4)
        glBindTexture(GL_TEXTURE_CUBE_MAP, 0)
        glActiveTexture(GL_TEXTURE2)
        glBindTexture(GL_TEXTURE_2D_ARRAY, 0)
        glActiveTexture(GL_TEXTURE3)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glDepthMask(GL_TRUE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def _draw_model_strands(self, mvp, previous_mvp, model, normal_mat, eye,
                            near_plane):
        """Write captured discrete Ratchet ribbons into the native Hair G-buffer."""
        if (not self._fur_deferred_active or not self._model_strand_material_prog
                or not self._gpu_model_strands or not self._show_fur):
            return
        program = self._model_strand_material_prog
        glUseProgram(program)
        _set_uniform_mat4(program, 'uMVP', mvp)
        _set_uniform_mat4(program, 'uPreviousMVP', previous_mvp)
        _set_uniform_mat4(program, 'uModel', model)
        _set_uniform_mat3(program, 'uNormal', normal_mat)
        _set_uniform_3f(program, 'uEye', *eye)
        _set_uniform_2f(program, 'uViewportSize', *self._framebuffer_size())
        _set_uniform_1f(program, 'uMotionNearPlane', near_plane)
        _set_uniform_1f(program, 'uFurWetness', self._fur_wetness)
        _set_uniform_1f(program, 'uTransmittance', 0.1)
        flags = glGetUniformLocation(program, 'uFurRenderFlags')
        if flags >= 0:
            glUniform1ui(flags, 0)
        for sampler, unit in (('uDiffuse', 0), ('uThickness', 1)):
            location = glGetUniformLocation(program, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        glDisable(GL_BLEND)
        glDepthMask(GL_TRUE)
        glDisable(GL_CULL_FACE)
        for group in self._gpu_model_strands:
            profile = group.profile
            _set_uniform_1f(program, 'uChildCount', float(profile.children))
            _set_uniform_1f(program, 'uReflectance', profile.reflectance)
            _set_uniform_1f(
                program, 'uStrayBase',
                max(profile.clump_x[0][1], profile.clump_y[0][1]),
            )
            _set_uniform_1f(program, 'uStrayStrength', profile.stray_strength)
            _set_uniform_1f(program, 'uStrayPower', profile.stray_power)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, group.diffuse_texture)
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, group.thickness_texture)
            group.draw()
        glBindVertexArray(0)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def paintGL(self):
        if not _HAS_OPENGL:
            return

        # Qt preserves context state between paints, but applying the complete
        # convention here also guards against state changed by external GL use.
        self._apply_raster_convention()
        glDisable(GL_CULL_FACE)

        # Upload any pending model now that GL context is active
        if self._pending_model is not None:
            self._upload_pending_model()

        if self._pending_fur_scene is not None:
            self._upload_fur_scene()

        pending_poses = self._pending_poses
        self._pending_poses = {}
        for index, streams in pending_poses.items():
            self._gpu_meshes[index].update_pose(*streams)
        if self._reset_pose_history or self._previous_fur_mvp is None:
            for mesh in self._gpu_meshes:
                mesh.settle_pose_history()
            self._reset_pose_history = False

        # Upload any pending textures
        pending_tex = getattr(self, '_pending_textures', None)
        if pending_tex is not None:
            self._pending_textures = None
            self._upload_textures(pending_tex)

        w, h = self.width(), self.height()
        framebuffer_size = self._framebuffer_size()
        if self._bloom_supported and self._bloom_size != framebuffer_size:
            self._resize_bloom_targets(*framebuffer_size)
        use_hdr = bool(
            self._bloom_supported and self._hdr_fbo
            and len(self._hdr_color_buffers) == 2
            and len(self._pingpong_fbos) == 2
        )
        self._fur_deferred_active = bool(use_hdr and self._fur_contact_prog
            and self._fur_contact_fbo and self._fur_key_texture and self._show_fur
            and self._fur_material_prog and self._fur_decode_prog and self._fur_lighting_prog
            and self._fur_material_fbo and not getattr(self, '_ortho', False))
        glBindFramebuffer(
            GL_FRAMEBUFFER,
            self._hdr_fbo if use_hdr else self.defaultFramebufferObject(),
        )
        glViewport(0, 0, *framebuffer_size)
        if use_hdr:
            if self._scene_velocity_texture and self._scene_stencil_texture:
                glDrawBuffers(5, [GL_COLOR_ATTACHMENT0 + index for index in range(5)])
            glClearBufferfv(
                GL_COLOR, 0, np.array([0.102, 0.110, 0.133, 1.0], dtype=np.float32),
            )
            glClearBufferfv(
                GL_COLOR, 1, np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            )
            if self._scene_velocity_texture and self._scene_stencil_texture:
                glClearBufferfv(
                    GL_COLOR, 2,
                    np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
                )
                glClearBufferfv(
                    GL_COLOR, 3,
                    np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
                )
                glClearBufferuiv(
                    GL_COLOR, 4, np.zeros(4, dtype=np.uint32),
                )
                glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
            glClear(GL_DEPTH_BUFFER_BIT)
        else:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        aspect = w / max(h, 1)
        near = 0.0001
        self._current_temporal_jitter = (0.0, 0.0)
        if getattr(self, '_ortho', False):
            # Orthographic: scale half-height by camera distance.
            # near/far are expressed in view space; we push near well behind
            # the eye (negative) so the infinite grid is never clipped, while
            # keeping far large enough for big scenes.
            half_h = self.camera.dist * 0.5
            extent = max(self.camera.dist * 10.0, 500.0)
            projection_builder = (
                _ortho_reverse_z_zero_to_one
                if self._native_raster_active else _ortho
            )
            proj = projection_builder(
                -half_h * aspect, half_h * aspect,
                -half_h, half_h, -extent, extent,
            )
        else:
            if hasattr(self, '_aabb_min') and hasattr(self, '_aabb_max'):
                near, far = _perspective_clip_planes(
                    self.camera, self._aabb_min, self._aabb_max,
                )
            else:
                near = max(self.camera.dist * 1e-4, 0.0001)
                far = max(self.camera.dist * 10.0, 100.0)
            projection_builder = (
                _perspective_reverse_z_zero_to_one
                if self._native_raster_active else _perspective
            )
            proj = projection_builder(60.0, aspect, near, far)
            if use_hdr and self._show_fur and self._gpu_meshes:
                # The retail stochastic coverage is consumed by a jittered
                # temporal pipeline.  Jitter is required to reconstruct the
                # sub-pixel shell field instead of merely averaging opacity.
                jitter_index = (self._temporal_sample_count % 32) + 1
                jitter_x = _halton(jitter_index, 2) - 0.5
                jitter_y = _halton(jitter_index, 3) - 0.5
                self._current_temporal_jitter = (jitter_x, jitter_y)
                proj[0, 2] += 2.0 * jitter_x / max(framebuffer_size[0], 1)
                proj[1, 2] += 2.0 * jitter_y / max(framebuffer_size[1], 1)
        view   = self.camera.view_matrix()
        vp     = proj @ view
        model  = np.eye(4, dtype=np.float32)
        mvp    = proj @ view @ model
        normal_mat = np.linalg.inv(model[:3, :3]).T
        wind_time = self._fur_wind_time_override
        if wind_time is None:
            wind_time = time.monotonic() - self._fur_wind_epoch
        motion_signature = (framebuffer_size, id(getattr(self, '_current_model', None)))
        if self._fur_motion_signature != motion_signature:
            self._previous_fur_mvp = None
            self._previous_fur_wind_time = None
            self._previous_fur_jitter = None
        previous_mvp = self._previous_fur_mvp
        if previous_mvp is None:
            previous_mvp = mvp
            # A camera/resource reset must reset pose motion in the same frame.
            for mesh in self._gpu_meshes:
                mesh.settle_pose_history()
        previous_projection = self._previous_fur_projection
        if previous_projection is None:
            previous_projection = proj
        previous_view = self._previous_fur_view
        if previous_view is None:
            previous_view = view
        previous_wind_time = self._previous_fur_wind_time
        if previous_wind_time is None:
            previous_wind_time = wind_time
        previous_fur_jitter = self._previous_fur_jitter
        if previous_fur_jitter is None:
            previous_fur_jitter = self._current_temporal_jitter

        light_dir = np.array(self._preview_light_direction, np.float32)
        if self._fur_deferred_active and self._fur_scene_is_current():
            light_dir = np.array(self._fur_scene_gpu.params['key_direction'], np.float32)
        light_dir /= np.linalg.norm(light_dir)
        fill_dir  = np.array([0.0, 0.3, 1.0], np.float32)   # soft front fill
        fill_dir  /= np.linalg.norm(fill_dir)

        # Draw infinite grid using full-screen quad + fragment shader.
        glDisable(GL_DEPTH_TEST)
        glUseProgram(self._grid_prog)
        inv_vp = np.linalg.inv(vp).astype(np.float32)
        _set_uniform_mat4(self._grid_prog, 'uInvVP', inv_vp)
        _set_uniform_bool(self._grid_prog, 'uOrtho', getattr(self, '_ortho', False))
        eye = self.camera.eye_position()
        _set_uniform_3f(self._grid_prog, 'uEye', float(eye[0]), float(eye[1]), float(eye[2]))
        grid_y = getattr(self, '_grid_y', 0.0)
        loc = glGetUniformLocation(self._grid_prog, 'uGridY')
        if loc >= 0: glUniform1f(loc, grid_y)
        if self._grid_vao:
            glBindVertexArray(self._grid_vao)
            glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
            glBindVertexArray(0)
        glEnable(GL_DEPTH_TEST)

        # Draw meshes
        if self._gpu_meshes:
            if use_hdr and self._scene_velocity_texture and self._scene_stencil_texture:
                glDrawBuffers(5, [GL_COLOR_ATTACHMENT0 + index for index in range(5)])
                # Linear depth is data; alpha blending would square the depth
                # or mix it with previously drawn geometry.
                glDisablei(GL_BLEND, 2)
                glDisablei(GL_BLEND, 3)
                glDisablei(GL_BLEND, 4)
            glUseProgram(self._shader_prog)
            _set_uniform_mat4(self._shader_prog, 'uMVP', mvp)
            _set_uniform_mat4(self._shader_prog, 'uPreviousMVP', previous_mvp)
            _set_uniform_mat4(self._shader_prog, 'uModel', model)
            _set_uniform_mat3(self._shader_prog, 'uNormal', normal_mat)
            _set_uniform_2f(
                self._shader_prog, 'uViewportSize', *framebuffer_size,
            )
            _set_uniform_1f(self._shader_prog, 'uMotionNearPlane', near)
            _set_uniform_3f(self._shader_prog, 'uLightDir', *light_dir)
            _set_uniform_3f(self._shader_prog, 'uFillDir',  *fill_dir)
            _set_uniform_bool(self._shader_prog, 'uWireframe', self._wireframe)
            _set_uniform_1f(self._shader_prog, 'uTime', time.monotonic())

            # Bind texture samplers
            for sampler, unit in (
                ('uAlbedo', 0), ('uNormalMap', 1), ('uEmissiveMap', 2),
                ('uEffectMaskMap', 3), ('uNoiseMap', 4),
                ('uRetailLavaColorA', 5), ('uRetailLavaColorB', 6),
                ('uRetailLavaNormalA', 7), ('uRetailLavaNormalB', 8),
                ('uRetailLavaNoise', 9),
                ('uRetailLavaMaskA', 10), ('uRetailLavaMaskB', 11),
                ('uFurControlMap', 12),
            ):
                loc = glGetUniformLocation(self._shader_prog, sampler)
                if loc >= 0:
                    glUniform1i(loc, unit)

            if self._wireframe:
                glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            else:
                glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

            for gm in self._gpu_meshes:
                if gm.is_fur and not self._show_fur:
                    continue
                # Composite-shell meshes are engine-side fur/RT helpers with
                # no albedo of their own. Drawing them as ordinary textured
                # surfaces creates the large flat pink/white patches that
                # obscure the authored head-fur geometry. Keep them available
                # in wireframe, but never include them in the shaded pass.
                if gm.is_composite_shell and not self._wireframe:
                    continue
                if (
                    gm.is_fur_surface
                    and gm.fur_length > 0.0
                    and _can_draw_fur_strands(
                        show_fur=self._show_fur,
                        wireframe=self._wireframe,
                        is_composite_shell=gm.is_composite_shell,
                        albedo_tex_id=gm.texture_id,
                        control_tex_id=gm.fur_control_tex_id,
                    )
                ):
                    # The recovered pass draws its own opaque base shell.  A
                    # generic shaded copy underneath creates a material seam
                    # wherever stochastic outer-shell coverage changes.
                    continue
                has_tex = gm.texture_id > 0 and not self._wireframe
                has_nrm = gm.normal_tex_id > 0 and not self._wireframe
                has_emissive = gm.emissive_tex_id > 0 and not self._wireframe
                has_effect_mask = gm.effect_mask_tex_id > 0 and not self._wireframe
                has_noise = gm.noise_tex_id > 0 and not self._wireframe
                has_fur_control = gm.fur_control_tex_id > 0 and not self._wireframe
                retail_lava_ids = (
                    gm.retail_lava_color_a_tex_id,
                    gm.retail_lava_color_b_tex_id,
                    gm.retail_lava_normal_a_tex_id,
                    gm.retail_lava_normal_b_tex_id,
                    gm.retail_lava_noise_tex_id,
                    gm.retail_lava_mask_a_tex_id,
                    gm.retail_lava_mask_b_tex_id,
                )
                has_retail_lava = (
                    gm.is_retail_blizar_lava
                    and not self._wireframe
                    and all(texture_id > 0 for texture_id in retail_lava_ids)
                )
                _set_uniform_bool(self._shader_prog, 'uHasTexture', has_tex)
                _set_uniform_bool(self._shader_prog, 'uHasNormal', has_nrm)
                _set_uniform_bool(self._shader_prog, 'uHasEmissive', has_emissive)
                _set_uniform_bool(self._shader_prog, 'uHasEffectMask', has_effect_mask)
                _set_uniform_bool(self._shader_prog, 'uHasNoise', has_noise)
                is_fur_surface = gm.is_fur_surface or has_fur_control
                _set_uniform_bool(self._shader_prog, 'uIsFur', is_fur_surface)
                _set_uniform_bool(
                    self._shader_prog, 'uHasFurControl', has_fur_control,
                )
                _set_uniform_bool(self._shader_prog, 'uIsLava', gm.is_lava)
                _set_uniform_bool(self._shader_prog, 'uIsLavaRock', gm.is_lava_rock)
                _set_uniform_bool(self._shader_prog, 'uIsLavaFall', gm.is_lavafall)
                _set_uniform_bool(
                    self._shader_prog, 'uIsRetailBlizarLava', has_retail_lava,
                )
                _set_uniform_2f(self._shader_prog, 'uLavaFlowA', *gm.lava_flow_a)
                _set_uniform_2f(self._shader_prog, 'uLavaFlowB', *gm.lava_flow_b)
                _set_uniform_bool(self._shader_prog, 'uAlphaCutout', gm.is_alpha_cutout)
                _set_uniform_3f(self._shader_prog, 'uBaseColor', *gm.color)
                texture_bindings = (
                    (has_tex, GL_TEXTURE0, gm.texture_id),
                    (has_nrm, GL_TEXTURE1, gm.normal_tex_id),
                    (has_emissive, GL_TEXTURE2, gm.emissive_tex_id),
                    (has_effect_mask, GL_TEXTURE3, gm.effect_mask_tex_id),
                    (has_noise, GL_TEXTURE4, gm.noise_tex_id),
                    (has_retail_lava, GL_TEXTURE5, gm.retail_lava_color_a_tex_id),
                    (has_retail_lava, GL_TEXTURE6, gm.retail_lava_color_b_tex_id),
                    (has_retail_lava, GL_TEXTURE7, gm.retail_lava_normal_a_tex_id),
                    (has_retail_lava, GL_TEXTURE8, gm.retail_lava_normal_b_tex_id),
                    (has_retail_lava, GL_TEXTURE9, gm.retail_lava_noise_tex_id),
                    (has_retail_lava, GL_TEXTURE10, gm.retail_lava_mask_a_tex_id),
                    (has_retail_lava, GL_TEXTURE11, gm.retail_lava_mask_b_tex_id),
                    (has_fur_control, GL_TEXTURE12, gm.fur_control_tex_id),
                )
                for enabled, unit, tex_id in texture_bindings:
                    if enabled:
                        glActiveTexture(unit)
                        glBindTexture(GL_TEXTURE_2D, tex_id)
                gm.draw()
                for enabled, unit, _tex_id in texture_bindings:
                    if enabled:
                        glActiveTexture(unit)
                        glBindTexture(GL_TEXTURE_2D, 0)

            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

            if use_hdr and self._scene_velocity_texture and self._scene_stencil_texture:
                glDrawBuffers(5, [GL_COLOR_ATTACHMENT0 + index for index in range(5)])
            srgb_enabled = bool(glIsEnabled(GL_FRAMEBUFFER_SRGB))
            if self._fur_deferred_active:
                glBindFramebuffer(GL_FRAMEBUFFER, self._fur_material_fbo)
                glClearBufferuiv(GL_COLOR, 0, np.zeros(4, dtype=np.uint32))
                glClearBufferfv(GL_COLOR, 1, np.zeros(4, dtype=np.float32))
                glClearBufferfv(GL_COLOR, 2, np.zeros(4, dtype=np.float32))
                glClearBufferuiv(GL_COLOR, 3, np.zeros(4, dtype=np.uint32))
                glClearBufferfv(GL_COLOR, 4, np.zeros(4, dtype=np.float32))
                glEnable(GL_FRAMEBUFFER_SRGB)
            if self._native_raster_active:
                # The captured state proves CCW/back-face culling for the fur
                # material draw. Other editor materials can be authored
                # two-sided, so keep this state scoped to the recovered pass.
                glFrontFace(GL_CCW)
                glCullFace(GL_BACK)
                glEnable(GL_CULL_FACE)
            self._draw_fur_strands(
                mvp, previous_mvp, model, normal_mat, eye, light_dir, fill_dir,
                wind_time, previous_wind_time, near,
            )
            if self._native_raster_active:
                glDisable(GL_CULL_FACE)
            self._draw_model_strands(
                mvp, previous_mvp, model, normal_mat, eye, near,
            )
            self._previous_fur_mvp = mvp.copy()
            self._previous_fur_projection = proj.copy()
            self._previous_fur_view = view.copy()
            self._previous_fur_wind_time = float(wind_time)
            self._previous_fur_jitter = tuple(self._current_temporal_jitter)
            self._fur_motion_signature = motion_signature
            if self._fur_deferred_active:
                if not srgb_enabled:
                    glDisable(GL_FRAMEBUFFER_SRGB)
                glBindFramebuffer(GL_FRAMEBUFFER, self._hdr_fbo)
            if use_hdr:
                glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])

        if use_hdr:
            if self._fur_deferred_active and not self._gpu_meshes:
                glBindFramebuffer(GL_FRAMEBUFFER, self._fur_material_fbo)
                glClearBufferuiv(GL_COLOR, 0, np.zeros(4, dtype=np.uint32))
            self._resolve_fur_lighting(proj, view, light_dir)
            self._denoise_fur_scene(proj, view)
            self._sync_temporal_signature()
            temporal_target_index = self._temporal_sample_count % 2
            self._build_motion_blur_scatter(temporal_target_index)
            self._build_temporal_disocclusion(
                temporal_target_index, proj, view,
                previous_projection, previous_view,
            )
            self._accumulate_temporal_scene(previous_fur_jitter)
            self._composite_bloom()
            if self._temporal_sample_count < 32:
                self.update()

    # ── Control settings ──────────────────────────────────────────────────────

    def reload_controls(self):
        """Re-read persisted control settings (call after the dialog closes)."""
        self._controls = load_controls()

    # ── Mouse Input  (Autodesk Maya-style) ────────────────────────────────────
    #
    #   LMB drag            → Tumble around the model pivot
    #   MMB drag            → Track in the camera view plane
    #   RMB drag            → Dolly horizontally
    #   Scroll wheel        → Dolly
    #   F / A               → Frame model
    #

    def mousePressEvent(self, e: QMouseEvent):
        mode = autodesk_mouse_mode(e.button(), e.modifiers())
        if mode is None:
            self._dragging = False
            self._last_pos = None
            self._mouse_mode = None
            self._drag_button = Qt.MouseButton.NoButton
            super().mousePressEvent(e)
            return

        self.setFocus()
        self._last_pos = e.pos()
        self._dragging = True
        self._mouse_mode = mode
        self._drag_button = e.button()
        self._start_render_loop()
        e.accept()

    def mouseMoveEvent(self, e: QMouseEvent):
        if not self._dragging or self._last_pos is None:
            return

        if not e.buttons() & self._drag_button:
            self._dragging = False
            self._last_pos = None
            return

        raw_dx = e.pos().x() - self._last_pos.x()
        raw_dy = e.pos().y() - self._last_pos.y()

        if self._mouse_mode == 'tumble':
            inv_x = self._controls.get("invert_orbit_x", False)
            inv_y = self._controls.get("invert_orbit_y", False)
            dx = -raw_dx if inv_x else raw_dx
            dy = -raw_dy if inv_y else raw_dy
            self.camera.orbit(dx, dy)

        elif self._mouse_mode == 'track':
            self.camera.pan(raw_dx, raw_dy)

        elif self._mouse_mode == 'dolly':
            speed = float(self._controls.get("zoom_speed", 1.0))
            self.camera.dolly(raw_dx * speed)

        self._last_pos = e.pos()
        try:
            win = self.window()
            if hasattr(win, '_status_lbl'):
                win._status_lbl.setText(
                    f"Camera yaw={self.camera.yaw:.0f}°  pitch={self.camera.pitch:.0f}°"
                )
        except Exception:
            pass
        e.accept()

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() != self._drag_button:
            super().mouseReleaseEvent(e)
            return
        self._dragging = False
        self._last_pos = None
        self._mouse_mode = None
        self._drag_button = Qt.MouseButton.NoButton
        self._stop_render_loop()
        self.update()
        e.accept()

    def wheelEvent(self, e: QWheelEvent):
        raw_delta = e.angleDelta().y() / 120.0   # +1 = scroll up = zoom in
        speed     = float(self._controls.get("zoom_speed", 1.0))
        invert    = self._controls.get("invert_zoom", False)
        signed    = raw_delta if not invert else -raw_delta
        self.camera.zoom(signed * speed)
        self._redraw()

    # ── Keyboard Input (Autodesk Maya-style framing) ──────────────────────────

    def keyPressEvent(self, e):
        key = e.key()
        if key in (Qt.Key.Key_F, Qt.Key.Key_A):
            self.frame_model()
            e.accept()
        else:
            super().keyPressEvent(e)

    def _toggle_ortho(self):
        """Toggle between perspective and orthographic projection."""
        self._ortho = not getattr(self, '_ortho', False)
        self._reset_temporal_history()
        self._redraw()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _free_gpu_meshes(self):
        self._pending_poses = {}
        # Collect unique texture IDs before freeing (multiple meshes may share a texture)
        unique_tex_ids = set()
        for gm in self._gpu_meshes:
            if gm.texture_id:
                unique_tex_ids.add(int(gm.texture_id))
            if gm.normal_tex_id:
                unique_tex_ids.add(int(gm.normal_tex_id))
            if gm.emissive_tex_id:
                unique_tex_ids.add(int(gm.emissive_tex_id))
            if gm.effect_mask_tex_id:
                unique_tex_ids.add(int(gm.effect_mask_tex_id))
            if gm.noise_tex_id:
                unique_tex_ids.add(int(gm.noise_tex_id))
            retail_attrs = (
                'retail_lava_color_a_tex_id', 'retail_lava_color_b_tex_id',
                'retail_lava_normal_a_tex_id', 'retail_lava_normal_b_tex_id',
                'retail_lava_noise_tex_id',
                'retail_lava_mask_a_tex_id', 'retail_lava_mask_b_tex_id',
            )
            for attr in retail_attrs:
                texture_id = getattr(gm, attr, 0)
                if texture_id:
                    unique_tex_ids.add(int(texture_id))
            gm.texture_id = 0  # prevent gm.free() from deleting it
            gm.normal_tex_id = 0
            gm.emissive_tex_id = 0
            gm.effect_mask_tex_id = 0
            gm.noise_tex_id = 0
            for attr in retail_attrs:
                setattr(gm, attr, 0)

        for gm in self._gpu_meshes:
            gm.free()
        self._gpu_meshes.clear()
        for group in self._gpu_model_strands:
            group.free()
        self._gpu_model_strands.clear()
        self._reset_temporal_history()
        if self._fur_scene_gpu is not None:
            self._fur_scene_gpu.close()
            self._fur_scene_gpu = None
        self._fur_scene_view = None

        # Now delete unique textures once each
        if unique_tex_ids:
            try:
                glDeleteTextures(len(unique_tex_ids), list(unique_tex_ids))
            except Exception:
                pass

    def _build_grid(self, half_size: int = 10, spacing: float = 0.1):
        """Build a full-screen quad for the infinite grid fragment shader."""
        verts = np.array([
            -1, -1, 0,   1, -1, 0,   1,  1, 0,
            -1, -1, 0,   1,  1, 0,  -1,  1, 0,
        ], dtype=np.float32)

        self._grid_vao = glGenVertexArrays(1)
        self._grid_vbo = glGenBuffers(1)
        glBindVertexArray(self._grid_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._grid_vbo)
        glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 12, None)
        glEnableVertexAttribArray(0)
        glBindVertexArray(0)
        self._grid_count = 6


# ── Math helpers ──────────────────────────────────────────────────────────────

def _perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    return np.array([
        [f/aspect, 0,  0,                        0                       ],
        [0,        f,  0,                        0                       ],
        [0,        0,  (far+near)/(near-far),    (2*far*near)/(near-far) ],
        [0,        0, -1,                        0                       ]
    ], dtype=np.float32)


def _perspective_reverse_z_zero_to_one(
    fov_deg: float, aspect: float, near: float, far: float,
) -> np.ndarray:
    """Build the native right-handed finite reverse-Z projection.

    This is kept separate from ``_perspective`` until clip origin, shared
    depth, fullscreen passes, and screen-space addressing can migrate as one
    operation.  With visible view-space Z negative, near maps to 1 and far to
    0 under ``GL_ZERO_TO_ONE``.
    """
    if not 0.0 < near < far:
        raise ValueError("reverse-Z perspective requires 0 < near < far")
    f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    inverse_range = 1.0 / (far - near)
    return np.array([
        [f/aspect, 0,  0,                         0                        ],
        [0,        f,  0,                         0                        ],
        [0,        0,  near * inverse_range,      near * far * inverse_range],
        [0,        0, -1,                         0                        ],
    ], dtype=np.float32)

def _ortho(left: float, right: float, bottom: float, top: float,
           near: float, far: float) -> np.ndarray:
    return np.array([
        [2/(right-left), 0,              0,             -(right+left)/(right-left)],
        [0,              2/(top-bottom), 0,             -(top+bottom)/(top-bottom)],
        [0,              0,             -2/(far-near),  -(far+near)/(far-near)    ],
        [0,              0,              0,              1                        ],
    ], dtype=np.float32)


def _ortho_reverse_z_zero_to_one(
    left: float, right: float, bottom: float, top: float,
    near: float, far: float,
) -> np.ndarray:
    """Map right-handed view planes ``-near``/``-far`` to one/zero."""
    if right == left or top == bottom or far == near:
        raise ValueError("orthographic bounds must have non-zero extent")
    return np.array([
        [2/(right-left), 0,              0,            -(right+left)/(right-left)],
        [0,              2/(top-bottom), 0,            -(top+bottom)/(top-bottom)],
        [0,              0,              1/(far-near),  far/(far-near)            ],
        [0,              0,              0,             1                         ],
    ], dtype=np.float32)

def _look_at(eye: np.ndarray, center: np.ndarray, up: np.ndarray) -> np.ndarray:
    f = center - eye;  f /= np.linalg.norm(f)
    r = np.cross(f, up); r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return np.array([
        [ r[0],  r[1],  r[2], -np.dot(r, eye)],
        [ u[0],  u[1],  u[2], -np.dot(u, eye)],
        [-f[0], -f[1], -f[2],  np.dot(f, eye)],
        [ 0,     0,     0,     1             ]
    ], dtype=np.float32)

def _set_uniform_mat4(prog, name, mat):
    loc = glGetUniformLocation(prog, name)
    if loc >= 0:
        # OpenGL expects column-major; numpy matrices are row-major.
        # GL_TRUE means transpose on upload, so pass as-is with GL_TRUE.
        glUniformMatrix4fv(loc, 1, GL_TRUE, mat.astype(np.float32))

def _set_uniform_mat3(prog, name, mat):
    loc = glGetUniformLocation(prog, name)
    if loc >= 0:
        glUniformMatrix3fv(loc, 1, GL_TRUE, mat.astype(np.float32))

def _set_uniform_3f(prog, name, x, y, z):
    loc = glGetUniformLocation(prog, name)
    if loc >= 0:
        glUniform3f(loc, x, y, z)

def _set_uniform_bool(prog, name, val):
    loc = glGetUniformLocation(prog, name)
    if loc >= 0:
        glUniform1i(loc, int(val))


def _set_uniform_1f(prog, name, value):
    loc = glGetUniformLocation(prog, name)
    if loc >= 0:
        glUniform1f(loc, float(value))


def _set_uniform_2f(prog, name, x, y):
    loc = glGetUniformLocation(prog, name)
    if loc >= 0:
        glUniform2f(loc, float(x), float(y))


def _set_uniform_4f(prog, name, x, y, z, w):
    loc = glGetUniformLocation(prog, name)
    if loc >= 0:
        glUniform4f(loc, float(x), float(y), float(z), float(w))

def _hsv_to_rgb(h, s, v):
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s);  q = v * (1 - f * s);  t = v * (1 - (1 - f) * s)
    i %= 6
    return [(v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q)][i]
