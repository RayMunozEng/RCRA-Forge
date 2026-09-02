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
import numpy as np
from typing import Optional

from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QMouseEvent, QWheelEvent

from ui.camera_controls import AUTODESK_CONTROL_TOOLTIP, autodesk_mouse_mode
from ui.controls_dialog import load_controls

try:
    from OpenGL.GL import *
    from OpenGL.GL.shaders import compileShader, compileProgram
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


def _postprocess_settings(has_retail_lava: bool) -> tuple[float, float]:
    """Return isolated-view exposure and bloom strength."""
    if has_retail_lava:
        # Rift Apart adapts exposure from the full Blizar cavern.  This neutral
        # reference keeps authored BC6H lava detail visible in isolation while
        # giving the glow less weight than the surface itself.
        return 0.55, 0.20
    return 1.0, 0.55


def _compressed_gl_format(dxgi_format: int, srgb: bool = False):
    """Map supported DXGI block formats to their identical OpenGL formats."""
    if dxgi_format in (0x47, 0x48):
        return 0x8C4D if srgb else 0x83F1  # sRGB/RGBA S3TC DXT1
    if dxgi_format in (0x4A, 0x4B):
        return 0x8C4E if srgb else 0x83F2  # sRGB/RGBA S3TC DXT3
    if dxgi_format in (0x4D, 0x4E):
        return 0x8C4F if srgb else 0x83F3  # sRGB/RGBA S3TC DXT5
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


def _fur_round_nearest_even(value: float) -> float:
    """Match DXBC ``round_ni`` including half-way ties to even."""
    base = math.floor(float(value))
    fraction = float(value) - base
    if fraction < 0.5:
        return float(base)
    if fraction > 0.5:
        return float(base + 1)
    return float(base if base % 2 == 0 else base + 1)


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
    result = np.zeros((slices, size, size), dtype=np.uint8)
    for y in range(size):
        for x in range(size):
            random24 = np.float32(xorshift128() >> 8)
            height = int(np.float32(random24 * random24) * height_scale) + 1
            height = min(height, slices)
            for layer in range(height):
                profile = max(2.0 * (layer + 1) / height - 1.0, 0.0)
                value = min(max(1.0 - 0.8 * profile * profile, 0.0), 1.0)
                result[layer, x, y] = int(value * 255.0)
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

uniform mat4 uMVP;
uniform mat4 uModel;
uniform mat3 uNormal;

out vec3 vNormal;
out vec3 vWorldPos;
out vec2 vUV;

void main() {
    vec4 worldPos = uModel * vec4(aPos, 1.0);
    vWorldPos  = worldPos.xyz;
    vNormal    = normalize(uNormal * aNormal);
    vUV        = aUV;
    gl_Position = uMVP * vec4(aPos, 1.0);
}
"""

FRAG_SRC = """
#version 330 core
in vec3 vNormal;
in vec3 vWorldPos;
in vec2 vUV;

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

layout(location = 0) out vec4 FragColor;
layout(location = 1) out vec4 BrightColor;
layout(location = 2) out vec4 SceneReciprocalDepth;

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
    if (uWireframe) {
        FragColor = vec4(0.2, 0.8, 1.0, 1.0);
        BrightColor = vec4(0.0);
        SceneReciprocalDepth = vec4(gl_FragCoord.w);
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
    SceneReciprocalDepth = vec4(gl_FragCoord.w);
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
        occlusion += sampleDepth < 0.9999
            && sampleDepth + depthBias < gl_FragCoord.z ? 0.50 : 0.0;
        sampleDepth = texture(uSceneDepth, screenUV + texelStep * 3.0).r;
        occlusion += sampleDepth < 0.9999
            && sampleDepth + depthBias < gl_FragCoord.z ? 0.30 : 0.0;
        sampleDepth = texture(uSceneDepth, screenUV + texelStep * 5.0).r;
        occlusion += sampleDepth < 0.9999
            && sampleDepth + depthBias < gl_FragCoord.z ? 0.20 : 0.0;
        float strandContact = 1.0 - smoothstep(0.12, 0.82, gAlong);
        color *= 1.0 - occlusion * strandContact * 0.18;
    }
    if (uWeightedOIT) {
        float depthWeight = pow(1.0 - gl_FragCoord.z * 0.90, 3.0);
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
    vNear = unproject(aPos.x, aPos.y, -1.0, uInvVP);
    vFar  = unproject(aPos.x, aPos.y,  1.0, uInvVP);
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

uniform mat4 uMVP;
uniform mat4 uModel;
uniform mat3 uNormal;
uniform sampler2D uFurControl;
uniform float uFurLength;
uniform float uFurOffsetScale;
uniform float uFurWindStrength;
uniform vec3 uFurWindVector;
uniform float uFurWindTime;
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

vec3 retailWindOffset(vec2 uv, vec3 localWind) {
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
    ) * sin((envelope + fract(uFurWindTime * 0.159155)) * 6.28319) - 1.0;
    float directionalCap = min(
        smoothRamp * (envelope * 0.0125 + 0.0375),
        uFurWindRadius * 0.1
    );

    float speed = uFurWindTurbulence * 10.0 + 5.0;
    float noiseTime = (uFurWindTime + 0.125 + spatial * 0.125) * speed;
    float f = fract(noiseTime);
    float f2 = f * f;
    float f3 = f2 * f;
    vec4 weights = vec4(
        -f + 2.0 * f2 - f3,
        1.0 - 2.0 * f2 + f3,
        f + f2 - f3,
        -f2 + f3
    );
    int tableIndex = int(fract(noiseTime * 0.0163934) * 61.0);
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
    if (uFurWindStrength > 0.0 && uFurLength > 0.0) {
        float windLength = length(uFurWindVector);
        vec3 windDirection = windLength > 0.000001
            ? uFurWindVector / windLength : vec3(0.0);
        vec3 localWind = inverse(mat3(uModel)) * windDirection;
        vec3 windOffset = retailWindOffset(aUV, localWind);
        // The retail shader projects the procedural displacement onto its
        // normal/bitangent plane before curving the shell frame.
        vec3 localBitangent = normalize(cross(localTangent, localNormal))
            * aTangent.w;
        vec3 frameOffset = localNormal * dot(localNormal, windOffset)
            + localBitangent * dot(localBitangent, windOffset);
        float windGate = clamp(
            (controlLength * uFurLength - 0.0075) * 50.0, 0.0, 1.0
        );
        float bendCurve = layerDepth * layerDepth + 0.4 * layerDepth;
        vec3 bend = frameOffset * windGate * bendCurve
            / max(uFurLength, 0.000001);
        shellLocalNormal = normalize(localNormal + bend);
        worldTangent = normalize(uNormal * (localTangent + bend));
    }
    vec3 localPosition = aPos + shellLocalNormal
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
    vsWorldTangent = vec4(worldTangent, aTangent.w);
    gl_Position = uMVP * vec4(worldPosition, 1.0);
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

out vec2 vUV;
out vec3 vWorldPosition;
out vec3 vWorldNormal;
out float vLayerDepth;
out float vLayerSlice;
out float vCurvedOffset;
flat out int vBaseShell;
out vec4 vWorldTangent;

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
        gl_Position = gl_in[index].gl_Position;
        EmitVertex();
    }
    EndPrimitive();
}
"""

FUR_SHELL_FRAG_SRC = """
#version 330 core
in vec2 vUV;
in vec3 vWorldPosition;
in vec3 vWorldNormal;
in float vLayerDepth;
in float vLayerSlice;
in float vCurvedOffset;
flat in int vBaseShell;
in vec4 vWorldTangent;

uniform sampler2D uFurAlbedo;
uniform sampler2D uFurControl;
uniform sampler2D uFurSpecular;
uniform sampler2DArray uFurLayers;
uniform sampler2DArray uFurEnvironment;
uniform sampler2D uFurBrdfLut;
uniform float uFurDensity;
uniform float uFurOffsetScale;
uniform float uFurGlossScale;
uniform float uFurSpecularScale;
uniform float uFurTransmittanceScale;
uniform float uFurWetness;
uniform bool uHasFurSpecular;
uniform bool uHasFurEnvironment;
uniform vec3 uEye;
uniform vec3 uLightDir;
uniform vec3 uFillDir;
uniform int uFrameIndex;
uniform float uTemporalIndex;
uniform vec2 uViewportSize;

layout(location = 0) out vec4 FragColor;
layout(location = 1) out vec4 BrightColor;
layout(location = 2) out vec4 FurGBuffer;
layout(location = 3) out vec4 FurNormalMask;

float screenHash(vec2 normalizedPosition) {
    return fract(sin(dot(normalizedPosition, vec2(12.9898, 78.233002)))
        * 43758.546875 + uTemporalIndex);
}

float roundNearestEven(float value) {
    float base = floor(value);
    float fraction = value - base;
    if (fraction < 0.5) {
        return base;
    }
    if (fraction > 0.5) {
        return base + 1.0;
    }
    return mod(base, 2.0) == 0.0 ? base : base + 1.0;
}

vec2 roundNearestEven(vec2 value) {
    return vec2(roundNearestEven(value.x), roundNearestEven(value.y));
}

float screenLayerRandom(vec2 pixel, float slice) {
    vec2 shifted = pixel + vec2(-10.0 * slice, slice);
    vec2 cell = roundNearestEven(shifted);
    // Exact PS_FurShellGBufferDeferred sequence: the integer temporal phase
    // joins x + 2*y before the 0.2 scale, and the spatial hash is scaled by
    // the same factor.  This produces five stratified threshold bands.
    return fract(
        (cell.x + cell.y * 2.0 + float(uFrameIndex)
            + screenHash(shifted / max(uViewportSize, vec2(1.0)))) * 0.2
    );
}

float layerUvDivisor(vec2 pixel, float wetness) {
    // Exact MaterialFur wet-clumping divisor. At m_Wetness=0 this reduces to
    // round(0.45 + phase*0.1), producing the recovered dry 1/1.375 dither.
    vec2 roundedPixel = roundNearestEven(pixel);
    float phase = fract(
        (roundedPixel.x + roundedPixel.y * 2.0 + float(uFrameIndex)
            + screenHash(pixel / max(uViewportSize, vec2(1.0)))) * 0.2
    );
    float wetBase = (1.0 - (1.0 - wetness) * (1.0 - wetness)) * 8.0 + 0.45;
    return roundNearestEven(wetBase + phase * 0.1) * 0.375 + 1.0;
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

void recoveredHairBasis(
        vec3 strandTangent,
        vec3 geometricNormal,
        vec3 viewDirection,
        out vec3 lobeNormal,
        out vec3 lobeSide) {
    // CS_ApplyGBufferLighting_Hair instructions 95-129.  GBufExtra is a
    // strand tangent, not a replacement surface normal.  Retail constructs a
    // view-oriented frame around that tangent for each of its two lobes.
    float strandNormalDot = dot(strandTangent, geometricNormal);
    float strandNormalSine = length(cross(strandTangent, geometricNormal));
    vec3 frameSeed = viewDirection * strandNormalSine
        + geometricNormal * strandNormalDot;
    lobeSide = normalize(cross(frameSeed, strandTangent));
    lobeNormal = normalize(cross(lobeSide, strandTangent));
}

float recoveredHairDistribution(
        vec3 lobeNormal,
        vec3 strandTangent,
        vec3 lobeSide,
        vec3 lightDirection,
        vec3 viewDirection,
        vec3 halfVector,
        float alphaAlong,
        float alphaAcross) {
    // Direct scalar translation of instructions 1229-1258 / 1267-1299.
    float normalHalf = dot(lobeNormal, halfVector);
    float tangentHalf = dot(strandTangent, halfVector);
    float sideHalf = dot(lobeSide, halfVector);
    float ellipsoid = normalHalf * normalHalf
        + tangentHalf * tangentHalf / (alphaAlong * alphaAlong)
        + sideHalf * sideHalf / (alphaAcross * alphaAcross);
    float normalLight = clamp(dot(lobeNormal, lightDirection), 0.0, 1.0);
    float normalView = min(abs(dot(lobeNormal, viewDirection)) + 0.00001, 1.0);
    float averageAlpha = min(alphaAlong, alphaAcross) * 0.75
        + max(alphaAlong, alphaAcross) * 0.25;
    float maskingAlpha = averageAlpha * 0.353553 + 0.353553;
    float maskingAlphaSquared = maskingAlpha * maskingAlpha;
    float maskingRemainder = 1.0 - maskingAlphaSquared;
    float lightMask = normalLight * maskingRemainder + maskingAlphaSquared;
    float viewMask = normalView * maskingRemainder + maskingAlphaSquared;
    float denominator = ellipsoid * ellipsoid
        * alphaAlong * alphaAcross * lightMask * viewMask;
    return normalLight * 0.25 / max(denominator, 0.00001);
}

vec3 recoveredHairFresnel(vec3 f0, float viewHalf) {
    float grazing = pow(1.0 - clamp(viewHalf, 0.0, 1.0), 5.0);
    return f0 + grazing * (vec3(1.0) - f0);
}

vec3 sampleD3DCube(vec3 direction, float lod) {
    vec3 absoluteDirection = abs(direction);
    float face;
    vec2 coordinate;
    if (absoluteDirection.x >= absoluteDirection.y
            && absoluteDirection.x >= absoluteDirection.z) {
        if (direction.x >= 0.0) {
            face = 0.0;
            coordinate = vec2(-direction.z, -direction.y) / absoluteDirection.x;
        } else {
            face = 1.0;
            coordinate = vec2(direction.z, -direction.y) / absoluteDirection.x;
        }
    } else if (absoluteDirection.y >= absoluteDirection.z) {
        if (direction.y >= 0.0) {
            face = 2.0;
            coordinate = vec2(direction.x, direction.z) / absoluteDirection.y;
        } else {
            face = 3.0;
            coordinate = vec2(direction.x, -direction.z) / absoluteDirection.y;
        }
    } else {
        if (direction.z >= 0.0) {
            face = 4.0;
            coordinate = vec2(direction.x, -direction.y) / absoluteDirection.z;
        } else {
            face = 5.0;
            coordinate = vec2(-direction.x, -direction.y) / absoluteDirection.z;
        }
    }
    return textureLod(
        uFurEnvironment, vec3(coordinate * 0.5 + 0.5, face), lod
    ).rgb;
}

void main() {
    vec4 control = texture(uFurControl, vUV);
    float wetness = clamp(uFurWetness, 0.0, 1.0);
    vec2 comb = (control.rg * 2.0 - 1.0) * uFurOffsetScale;
    float combZ = sqrt(1.0 - min(dot(comb, comb), 0.99));
    vec3 groom = normalize(vec3(comb, combZ));
    vec2 layerUV = vUV * uFurDensity
        + groom.xy * vCurvedOffset / max(groom.z, 0.0001);
    layerUV /= layerUvDivisor(gl_FragCoord.xy, wetness);

    vec3 viewDirection = normalize(uEye - vWorldPosition);
    // The DXBC applies SV_IsFrontFace before the layer MIP bias and before
    // transforming the groom vector into the packed shading normal.
    float faceSign = gl_FrontFacing ? 1.0 : -1.0;
    vec3 normal = normalize(vWorldNormal) * faceSign;
    float mipBias = -2.0 * pow(
        1.0 - clamp(dot(normal, viewDirection), 0.0, 1.0), 2.0
    );
    // D3D returns zero for the outer coordinate 32 of the 32-slice array.
    float layerValue = vLayerSlice >= 32.0 ? 0.0 : texture(
        uFurLayers, vec3(layerUV, vLayerSlice), mipBias
    ).r;
    // MaterialFur rounds out the recovered shell field as strands clump wet.
    float expandedLayer = clamp(layerValue + 0.1, 0.0, 1.0);
    expandedLayer = pow(expandedLayer, 5.0) - layerValue;
    layerValue += wetness * expandedLayer;
    vec4 albedo = texture(uFurAlbedo, vUV);
    albedo *= 1.0 - 0.2 * wetness * sqrt(clamp(vLayerSlice / 32.0, 0.0, 1.0));
    float coverage = clamp(
        layerValue * albedo.a + float(vBaseShell), 0.0, 1.0
    ) * clamp(1.0 - vLayerSlice / 64.0, 0.0, 1.0);
    if (coverage <= (1.0 / 255.0)) {
        discard;
    }

    vec3 tangent = normalize(
        vWorldTangent.xyz - normal * dot(normal, vWorldTangent.xyz)
    );
    vec3 bitangent = normalize(cross(normal, tangent)) * vWorldTangent.w;
    vec3 strandTangent = normalize(
        -tangent * groom.x + bitangent * groom.y + normal * groom.z
    );
    // Unit-radiance direct-light evaluation from CS_ApplyGBufferLighting_Hair.
    // Environment probes and the scene light grid are unavailable in an asset
    // viewport, but the lobe, diffuse, and transmission equations below are
    // the retail equations rather than fitted display-light multipliers.
    vec3 lightDirection = normalize(uLightDir);
    float normalLight = clamp(dot(normal, lightDirection), 0.0, 1.0);
    float normalView = dot(normal, viewDirection);
    float transmittance = max(uFurTransmittanceScale, 0.0);
    float diffuseResponse = clamp(
        (normalLight + transmittance)
            / ((transmittance + 1.0) * (transmittance + 1.0)),
        0.0, 1.0
    );
    vec3 wrappedLight = lightDirection * 0.75 + normal * 0.25;
    float transmissionPhase = dot(-viewDirection, wrappedLight);
    float transmissionDenominator = (
        8.0 - transmissionPhase * 10.5
            + transmissionPhase * transmissionPhase * 3.17114
    ) * (clamp(normalLight * normalView, 0.0, 1.0) + 0.1);
    float transmissionResponse = 1.0 / max(
        transmissionDenominator, 0.00001
    );
    float grazing = clamp(1.0 - normalView * 2.0, 0.0, 1.0);
    float transmissionMix = transmittance
        * (0.5 + 0.5 * grazing * grazing);
    vec3 primarySpecular = vec3(0.0);
    vec3 secondarySpecular = vec3(0.0);
    vec3 indirectDiffuse = vec3(0.0);
    if (uHasFurSpecular) {
        float furResponse = max(texture(uFurSpecular, vUV).r, 0.0);
        // Exact PS_FurShellGBufferDeferred packing order: gloss receives
        // sqrt(texture) before its authored scale; specular receives its
        // authored scale before sqrt.
        float glossResponse = clamp(
            sqrt(furResponse) * uFurGlossScale, 0.0, 1.0
        );
        float specularResponse = sqrt(clamp(
            furResponse * uFurSpecularScale, 0.0, 1.0
        ));
        float shellGlossFade = 1.0 - clamp(
            vLayerSlice * 0.125 - 0.25, 0.0, 1.0
        ) * 0.333;
        float adjustedGloss = glossResponse * shellGlossFade;
        float primaryGloss = adjustedGloss * 0.6 + 0.1;
        float secondaryGloss = primaryGloss
            * (1.0 - adjustedGloss * 0.3 - 0.05);

        float primaryAlong = pow(
            0.9725 - 0.7514 * primaryGloss, 4.0
        );
        float primaryAcross = pow(
            0.9725 - 0.07514 * primaryGloss, 4.0
        );
        float secondaryAlong = pow(min(
            0.9725 - 0.7514 * secondaryGloss, 1.0
        ), 4.0);
        float secondaryAcross = pow(
            0.9725 - 0.07514 * secondaryGloss, 4.0
        );

        // The installed PS leaves GBufExtra bits 26-31 clear, making the
        // second retail tangent shift exactly 0.075 for this material path.
        vec3 secondaryTangent = normalize(
            strandTangent + 0.075 * (-normal - strandTangent)
        );
        vec3 primaryNormal;
        vec3 primarySide;
        vec3 secondaryNormal;
        vec3 secondarySide;
        recoveredHairBasis(
            strandTangent, normal, viewDirection,
            primaryNormal, primarySide
        );
        recoveredHairBasis(
            secondaryTangent, normal, viewDirection,
            secondaryNormal, secondarySide
        );
        vec3 halfVector = normalize(lightDirection + viewDirection);
        float primaryDistribution = recoveredHairDistribution(
            primaryNormal, strandTangent, primarySide,
            lightDirection, viewDirection, halfVector,
            primaryAlong, primaryAcross
        );
        float secondaryDistribution = recoveredHairDistribution(
            secondaryNormal, secondaryTangent, secondarySide,
            lightDirection, viewDirection, halfVector,
            secondaryAlong, secondaryAcross
        );
        vec3 primaryF0 = vec3(specularResponse * specularResponse);
        vec3 secondaryF0 = clamp(
            vec3(specularResponse * 5.0), 0.0, 1.0
        ) / (sqrt(max(albedo.rgb, vec3(0.0))) + vec3(0.75));
        vec3 primaryFresnel = recoveredHairFresnel(
            primaryF0, dot(viewDirection, halfVector)
        );
        vec3 secondaryFresnel = recoveredHairFresnel(
            secondaryF0, dot(viewDirection, halfVector)
        );
        primarySpecular = primaryFresnel * primaryDistribution;
        secondarySpecular = secondaryFresnel * secondaryDistribution;
        if (uHasFurEnvironment) {
            // Captured default-probe Hair path: construct the anisotropic
            // reflection frame, sample BC6 at 5-5*roughness, then apply slice
            // zero of Default Brdf Lookup. LightGridIntensity was 0.6.
            vec3 chosenAxis = primaryAcross >= secondaryAcross
                ? primarySide : strandTangent;
            vec3 viewPerpendicular = cross(
                cross(chosenAxis, viewDirection), chosenAxis
            );
            float environmentBlend = clamp(
                (1.0 - dot(normal, strandTangent)) * 1.5
                    * max(primaryAcross, secondaryAcross),
                0.0, 1.0
            );
            vec3 environmentBase = mix(
                normal, viewPerpendicular, environmentBlend
            );
            float environmentAngle = screenLayerRandom(
                gl_FragCoord.xy, vLayerSlice
            ) * 18.8496;
            float sine = sin(environmentAngle);
            float cosine = cos(environmentAngle);
            vec3 environmentTarget = primaryNormal
                + primaryAcross * strandTangent * sine * sine * sine
                + secondaryAcross * primarySide * cosine * cosine * cosine;
            float averageRoughness = (primaryGloss + secondaryGloss) * 0.5;
            vec3 environmentNormal = normalize(mix(
                environmentTarget, environmentBase,
                averageRoughness * 0.25 + 0.5
            ));
            vec3 reflectionDirection = reflect(-viewDirection, environmentNormal);
            vec3 environmentSpecular = sampleD3DCube(
                reflectionDirection,
                5.0 - clamp(averageRoughness, 0.0, 1.0) * 5.0
            ) * 0.6;
            vec2 environmentBrdf = textureLod(
                uFurBrdfLut,
                vec2(abs(dot(environmentNormal, viewDirection)), averageRoughness),
                0.0
            ).rg;
            primarySpecular += environmentSpecular
                * (environmentBrdf.x * primaryF0 + environmentBrdf.y);
            secondarySpecular += environmentSpecular * secondaryF0;
            indirectDiffuse = sampleD3DCube(normal, 5.0) * 0.6;
        }
    }
    vec3 diffuseAndSecondary = vec3(diffuseResponse)
        + indirectDiffuse + secondarySpecular;
    vec3 color = albedo.rgb * mix(
        diffuseAndSecondary, vec3(transmissionResponse), transmissionMix
    ) + primarySpecular;
    // Recovered retail behavior: opaque stochastic coverage. Temporal offsets
    // are accumulated by the viewport history pass below.
    if (coverage < screenLayerRandom(gl_FragCoord.xy, vLayerSlice)) {
        discard;
    }
    // PS_FurShellGBufferDeferred writes a control-blue, wetness, shell-field
    // offset from reciprocal view depth. Hair deferred lighting consumes this
    // value for the strand-scale contact-shadow ray.
    float customReciprocalDepth = gl_FragCoord.w
        - (0.95 * control.b + 0.05)
        * (wetness + 0.005)
        * layerValue
        * (1.0 - vLayerSlice / 32.0);
    FragColor = vec4(color, 1.0);
    BrightColor = vec4(0.0);
    FurGBuffer = vec4(strandTangent, max(customReciprocalDepth, 0.000001));
    FurNormalMask = vec4(normal, 1.0);
}
"""

POST_VERT = """
#version 330 core
layout(location=0) in vec3 aPos;
out vec2 vTexCoord;
void main() {
    vTexCoord = aPos.xy * 0.5 + 0.5;
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

TEMPORAL_ACCUM_FRAG = """
#version 330 core
in vec2 vTexCoord;
uniform sampler2D uCurrent;
uniform sampler2D uHistory;
uniform sampler2D uFurGBuffer;
uniform float uHistoryWeight;
uniform vec2 uCurrentUvOffset;
uniform vec2 uProjectionScale;
uniform float uScreenToViewScaleX;
uniform vec3 uWorldLightDir;
uniform vec3 uViewLightDir;
uniform bool uFurContactEnabled;
out vec4 FragColor;

// CS_TemporalAaApply stores neighborhood colors as normalized luma/chroma
// before it constrains reprojected history.  The production shader also
// applies a cbuffer-controlled HDR luma compression term; its runtime value is
// not present in the DXBC, so the isolated preview intentionally omits only
// that unproven scale while preserving the recovered color axes and clamp.
vec3 encodeTemporalColor(vec3 rgb) {
    float luma = max(dot(rgb, vec3(0.25, 0.5, 0.25)), 0.000001);
    float chromaGreen = (0.5 * rgb.g - 0.25 * rgb.r - 0.25 * rgb.b) / luma;
    float chromaOrange = 0.5 * (rgb.r - rgb.b) / luma;
    return vec3(luma, chromaGreen, chromaOrange);
}

vec3 decodeTemporalColor(vec3 encoded) {
    float luma = encoded.x;
    return vec3(
        luma * (1.0 - encoded.y + encoded.z),
        luma * (1.0 + encoded.y),
        luma * (1.0 - encoded.y - encoded.z)
    );
}

vec3 sampleCurrentWithFurContact(vec2 uv) {
    vec3 color = texture(uCurrent, uv).rgb;
    vec4 fur = texture(uFurGBuffer, uv);
    if (fur.a <= 0.0) {
        return color;
    }
    if (!uFurContactEnabled) {
        return color;
    }

    float viewDepth = 1.0 / max(fur.a, 0.000001);
    vec2 ndc = uv * 2.0 - 1.0;
    vec3 viewPosition = vec3(
        ndc.x * viewDepth / uProjectionScale.x,
        ndc.y * viewDepth / uProjectionScale.y,
        -viewDepth
    );
    float depthScale = max(
        viewDepth * uScreenToViewScaleX * 0.137644, 1.0
    );
    vec3 rayEnd = viewPosition
        + normalize(uViewLightDir) * (depthScale * 0.015);
    vec2 rayEndNdc = vec2(
        rayEnd.x * uProjectionScale.x,
        rayEnd.y * uProjectionScale.y
    ) / max(-rayEnd.z, 0.000001);
    vec2 rayUv = rayEndNdc * 0.5 + 0.5 - uv;

    float occlusion = 0.0;
    for (int tap = 1; tap <= 4; ++tap) {
        float rayFraction = float(tap) * 0.25;
        vec2 sampleUv = clamp(
            uv + rayUv * rayFraction,
            vec2(0.0), vec2(1.0)
        );
        float sampleReciprocalDepth = texture(uFurGBuffer, sampleUv).a;
        if (sampleReciprocalDepth <= 0.0) {
            continue;
        }
        // Recovered DXBC: rcp(ray depth) - g_ViewDepthBuffer.  Keeping this
        // in reciprocal-depth units is essential; converting to linear depth
        // turns tiny strand offsets into broad false occlusion bands.
        float rayDepth = mix(viewDepth, max(-rayEnd.z, 0.000001), rayFraction);
        float separation = 1.0 / rayDepth - sampleReciprocalDepth;
        float contactBegins = clamp(
            separation * (1000.0 / depthScale), 0.0, 1.0
        );
        float contactEnds = clamp(
            2.0 - separation * (100.0 / depthScale), 0.0, 1.0
        );
        occlusion += contactBegins * contactEnds * 0.25;
    }
    float grazing = 1.0 - clamp(
        dot(normalize(fur.xyz), normalize(uWorldLightDir)), 0.0, 1.0
    );
    return color * (1.0 - 0.75 * grazing * occlusion);
}

void main() {
    vec2 texel = 1.0 / vec2(textureSize(uCurrent, 0));
    vec2 currentUV = clamp(
        vTexCoord + uCurrentUvOffset, texel * 0.5, vec2(1.0) - texel * 0.5
    );
    vec4 current = vec4(
        sampleCurrentWithFurContact(currentUV),
        texture(uCurrent, currentUV).a
    );
    vec3 neighborhoodMin = vec3(1.0e30);
    vec3 neighborhoodMax = vec3(-1.0e30);
    for (int y = -1; y <= 1; ++y) {
        for (int x = -1; x <= 1; ++x) {
            vec3 sampleColor = sampleCurrentWithFurContact(
                currentUV + vec2(x, y) * texel
            );
            vec3 encoded = encodeTemporalColor(sampleColor);
            neighborhoodMin = min(neighborhoodMin, encoded);
            neighborhoodMax = max(neighborhoodMax, encoded);
        }
    }
    vec3 history = encodeTemporalColor(texture(uHistory, vTexCoord).rgb);
    history = clamp(history, neighborhoodMin, neighborhoodMax);
    vec3 constrainedHistory = max(decodeTemporalColor(history), vec3(0.0));
    FragColor = vec4(
        mix(current.rgb, constrainedHistory, uHistoryWeight), current.a
    );
}
"""

# Direct translation of the captured CS_HairDenoise sampling structure. The
# retail pass follows the projected groom tangent for three gathers, accepts
# only masked fur samples, and rejects depth discontinuities with 200/depth.
# The viewport stores decoded float vectors instead of retail's packed GBuffer,
# so only the packing/unpacking instructions are intentionally absent here.
FUR_DENOISE_FRAG = """
#version 330 core
in vec2 vTexCoord;
uniform sampler2D uScene;
uniform sampler2D uFurGBuffer;
uniform sampler2D uFurNormalMask;
uniform mat3 uViewRotation;
uniform vec2 uProjectionScale;
uniform vec2 uViewportSize;
uniform int uFrameIndex;
uniform float uTemporalIndex;
out vec4 FragColor;

float screenHash(vec2 normalizedPosition) {
    return fract(sin(dot(normalizedPosition, vec2(12.9898, 78.233002)))
        * 43758.546875 + uTemporalIndex);
}

float roundNearestEven(float value) {
    float base = floor(value);
    float fraction = value - base;
    if (fraction < 0.5) return base;
    if (fraction > 0.5) return base + 1.0;
    return mod(base, 2.0) == 0.0 ? base : base + 1.0;
}

float denoisePhase(vec2 pixel) {
    vec2 rounded = vec2(
        roundNearestEven(pixel.x), roundNearestEven(pixel.y)
    );
    return fract(
        (rounded.x + rounded.y * 2.0 + float(uFrameIndex)
            + screenHash(pixel / max(uViewportSize, vec2(1.0)))) * 0.2
    );
}

vec2 projectViewPosition(vec3 position) {
    float reciprocalDepth = 1.0 / max(-position.z, 0.000001);
    vec2 ndc = position.xy * uProjectionScale * reciprocalDepth;
    return ndc * 0.5 + 0.5;
}

void gatherFurSample(
        ivec2 pixel, float projectedDepth, float centerDepth,
        inout vec3 colorSum, inout float weightSum) {
    ivec2 dimensions = textureSize(uScene, 0);
    ivec2 clampedPixel = clamp(pixel, ivec2(0), dimensions - ivec2(1));
    vec4 fur = texelFetch(uFurGBuffer, clampedPixel, 0);
    float mask = fur.a > 0.0 ? 1.0 : 0.0;
    if (mask <= 0.0) return;
    float sampleDepth = 1.0 / max(fur.a, 0.000001);
    float depthWeight = clamp(
        (sampleDepth - projectedDepth) * (200.0 / centerDepth) + 1.0,
        0.0, 1.0
    );
    float weight = depthWeight * mask;
    colorSum += texelFetch(uScene, clampedPixel, 0).rgb * weight;
    weightSum += weight;
}

void main() {
    ivec2 centerPixel = ivec2(gl_FragCoord.xy);
    vec4 centerFur = texelFetch(uFurGBuffer, centerPixel, 0);
    if (centerFur.a <= 0.0) {
        discard;
    }
    vec4 centerColor = texelFetch(uScene, centerPixel, 0);

    vec3 geometricNormal = normalize(
        texelFetch(uFurNormalMask, centerPixel, 0).xyz
    );
    vec3 strandTangent = normalize(centerFur.xyz);
    float centerDepth = 1.0 / max(centerFur.a, 0.000001);
    float tangentAgreement = abs(dot(geometricNormal, strandTangent));
    float rayLength = min(
        0.0025,
        sqrt(max(1.0 - tangentAgreement, 0.0)) * 0.05
    );
    vec3 viewTangent = normalize(uViewRotation * strandTangent);
    vec2 ndc = vTexCoord * 2.0 - 1.0;
    vec3 viewPosition = vec3(
        ndc.x * centerDepth / uProjectionScale.x,
        ndc.y * centerDepth / uProjectionScale.y,
        -centerDepth
    );
    vec3 rayStart = viewPosition - viewTangent * (rayLength * 0.5);
    vec3 rayEnd = viewPosition + viewTangent * (rayLength * 0.5);
    vec2 startUv = projectViewPosition(rayStart);
    vec2 endUv = projectViewPosition(rayEnd);
    float startReciprocalDepth = 1.0 / max(-rayStart.z, 0.000001);
    float endReciprocalDepth = 1.0 / max(-rayEnd.z, 0.000001);
    float phase = denoisePhase(gl_FragCoord.xy);

    vec3 colorSum = centerColor.rgb;
    float weightSum = 1.0;
    ivec2 dimensions = textureSize(uScene, 0);
    for (int step = 0; step < 3; ++step) {
        float along = (phase + float(step)) / 3.0;
        vec2 sampleUv = mix(startUv, endUv, along);
        float sampleReciprocalDepth = mix(
            startReciprocalDepth, endReciprocalDepth, along
        );
        float projectedDepth = 1.0 / max(
            sampleReciprocalDepth, 0.000001
        );
        vec2 gatherPosition = sampleUv * vec2(dimensions) - 0.5;
        ivec2 basePixel = ivec2(floor(gatherPosition));
        gatherFurSample(
            basePixel, projectedDepth, centerDepth, colorSum, weightSum
        );
        gatherFurSample(
            basePixel + ivec2(1, 0), projectedDepth, centerDepth,
            colorSum, weightSum
        );
        gatherFurSample(
            basePixel + ivec2(0, 1), projectedDepth, centerDepth,
            colorSum, weightSum
        );
        gatherFurSample(
            basePixel + ivec2(1, 1), projectedDepth, centerDepth,
            colorSum, weightSum
        );
    }
    FragColor = vec4(colorSum / max(weightSum, 0.000001), centerColor.a);
}
"""

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
) -> tuple[float, float]:
    """Undo projection jitter when sampling the current temporal-AA frame.

    Adding ``2*jitter/size`` to this OpenGL projection's [0, 2]/[1, 2]
    entries moves rasterized geometry by ``-jitter`` pixels because visible
    view-space Z is negative and clip W is ``-Z``. Sampling the current frame
    at that same negative pixel offset maps it onto history's stable grid.
    """
    width = max(int(framebuffer_size[0]), 1)
    height = max(int(framebuffer_size[1]), 1)
    return (
        -float(jitter_pixels[0]) / float(width),
        -float(jitter_pixels[1]) / float(height),
    )


# ── GPU Mesh ──────────────────────────────────────────────────────────────────

class GpuSubMesh:
    def __init__(self):
        self.vao: int = 0
        self.vbo: int = 0
        self.ebo: int = 0
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
        ], axis=1).astype(np.float32)

        self.vao = glGenVertexArrays(1)
        self.vbo = glGenBuffers(1)
        self.ebo = glGenBuffers(1)

        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, interleaved.nbytes, interleaved, GL_STATIC_DRAW)

        stride = 13 * 4
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

    def free(self):
        if self.vao:
            glDeleteVertexArrays(1, [self.vao])
            glDeleteBuffers(1, [self.vbo])
            glDeleteBuffers(1, [self.ebo])
            self.vao = 0
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


# ── Viewport Widget ───────────────────────────────────────────────────────────

import ctypes

class Viewport3D(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera     = ArcballCamera()
        self._gpu_meshes: list[GpuSubMesh] = []
        self._shader_prog: int = 0
        self._fur_shader_prog: int = 0
        self._fur_layer_texture: int = 0
        self._fur_environment_texture: int = 0
        self._fur_brdf_texture: int = 0
        self._pending_fur_environment = None
        self._grid_prog:   int = 0
        self._blur_prog:   int = 0
        self._composite_prog: int = 0
        self._temporal_accum_prog: int = 0
        self._fur_denoise_prog: int = 0
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
        self._redraw_pending = False
        self._grid_y         = 0.0
        self._grid_fade_r    = 2.0
        self._cached_material_textures: dict = {}   # persists across LOD switches
        self._uploaded_texture_signatures: dict = {}
        self._animated_materials = False
        self._bloom_enabled = True
        self._bloom_supported = True
        self._hdr_fbo = 0
        self._hdr_color_buffers: list[int] = []
        self._fur_gbuffer_texture = 0
        self._fur_normal_texture = 0
        self._fur_denoise_fbo = 0
        self._fur_denoise_texture = 0
        # Recovered Hair contact uses the complete reciprocal-depth buffer and
        # compares each ray tap in reciprocal (not linear) depth units.
        self._fur_contact_enabled = True
        self._fur_denoise_enabled = True
        # MaterialFur wetness and ModelFur wind strength are runtime state in
        # retail, not constants in the static material payload.
        self._fur_wetness = 0.0
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
        self._temporal_sample_count = 0
        self._temporal_signature = None
        self._current_temporal_jitter = (0.0, 0.0)
        self._display_scene_texture = 0
        self._current_scene_texture = 0
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
        self._pending_model  = model
        self._active_lod     = 0   # reset to LOD0 on new model load
        self._cached_material_textures = {}   # clear texture cache for new model
        self._pending_textures = {}
        self._uploaded_texture_signatures = {}
        if hasattr(self, '_cam_logged'):
            del self._cam_logged
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(10, self._trigger_repaint)

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

        def upload_slot(mat_idx, slot_data, role):
            if not slot_data or not slot_data[0]:
                return None
            rgba_bytes, width, height = slot_data[0], slot_data[1], slot_data[2]
            metadata = slot_data[4] if len(slot_data) > 4 \
                and isinstance(slot_data[4], dict) else {}
            signature = (role, id(rgba_bytes), width, height)
            if self._uploaded_texture_signatures.get((mat_idx, role)) == signature:
                return None
            try:
                tex_id = int(glGenTextures(1))
                glBindTexture(GL_TEXTURE_2D, tex_id)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
                compressed_mips = metadata.get('compressed_mips')
                compressed_mip0 = metadata.get('compressed_mip0')
                dxgi_format = metadata.get('dxgi_format')
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
                        if _is_srgb_texture_role(role) else GL_RGBA8
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
                tex_id = upload_slot(mat_idx, slot_data, role_by_attr[attr])
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
        self._temporal_signature = None
        self._temporal_sample_count = 0

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
            value = np.asarray(wind_vector, dtype=np.float32).reshape(3)
            length = float(np.linalg.norm(value))
            self._fur_wind_vector = value / length if length > 1e-8 else value
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
        """Queue a decoded RGB16F Hair probe and captured RG16F BRDF LUT."""
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

    # ── OpenGL Lifecycle ──────────────────────────────────────────────────────

    def initializeGL(self):
        if not _HAS_OPENGL:
            return

        glClearColor(0.102, 0.110, 0.133, 1.0)  # matches BG_BASE #1a1c22
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        vert = compileShader(VERT_SRC, GL_VERTEX_SHADER)
        frag = compileShader(FRAG_SRC, GL_FRAGMENT_SHADER)
        self._shader_prog = compileProgram(vert, frag)

        self._fur_shader_prog = compileProgram(
            compileShader(FUR_SHELL_VERT_SRC, GL_VERTEX_SHADER),
            compileShader(FUR_SHELL_GEOM_SRC, GL_GEOMETRY_SHADER),
            compileShader(FUR_SHELL_FRAG_SRC, GL_FRAGMENT_SHADER),
        )
        self._upload_fur_layer_volume()
        try:
            self._upload_fur_environment()
        except Exception as ex:
            print(f"[viewport] fur environment upload failed: {ex}", flush=True)
            raise

        gv = compileShader(GRID_VERT, GL_VERTEX_SHADER)
        gf = compileShader(GRID_FRAG, GL_FRAGMENT_SHADER)
        self._grid_prog = compileProgram(gv, gf)

        pv = compileShader(POST_VERT, GL_VERTEX_SHADER)
        bf = compileShader(BLUR_FRAG, GL_FRAGMENT_SHADER)
        cf = compileShader(COMPOSITE_FRAG, GL_FRAGMENT_SHADER)
        self._blur_prog = compileProgram(pv, bf)
        # A shader object cannot be linked into a second program after
        # compileProgram has deleted it, so compile a fresh fullscreen vertex.
        self._composite_prog = compileProgram(
            compileShader(POST_VERT, GL_VERTEX_SHADER), cf,
        )
        self._temporal_accum_prog = compileProgram(
            compileShader(POST_VERT, GL_VERTEX_SHADER),
            compileShader(TEMPORAL_ACCUM_FRAG, GL_FRAGMENT_SHADER),
        )
        self._fur_denoise_prog = compileProgram(
            compileShader(POST_VERT, GL_VERTEX_SHADER),
            compileShader(FUR_DENOISE_FRAG, GL_FRAGMENT_SHADER),
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
        """Upload the verified face-major RGB16F probe and captured BRDF LUT."""
        pending = self._pending_fur_environment
        if pending is None:
            return
        cube_mips, brdf_half_rgba, brdf_size = pending
        if len(cube_mips) != 6 or not cube_mips[0]:
            raise ValueError("Hair environment requires six BC6 cube faces")
        if self._fur_environment_texture:
            glDeleteTextures(1, [self._fur_environment_texture])
        if self._fur_brdf_texture:
            glDeleteTextures(1, [self._fur_brdf_texture])
        self._fur_environment_texture = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D_ARRAY, self._fur_environment_texture)
        level_count = len(cube_mips[0])
        for face, levels in enumerate(cube_mips):
            if len(levels) != level_count:
                raise ValueError("Hair environment faces have unequal mip counts")
        # Upload a complete six-layer image per mip. The source BC6 blocks are
        # decoded to linear half-float samples before this point because
        # PyOpenGL 3.1.10 cannot marshal compressed 2D-array payloads.
        for level in range(level_count):
            width, height, _ = cube_mips[0][level]
            level_faces = []
            for face in range(6):
                face_width, face_height, pixels = cube_mips[face][level]
                if (face_width, face_height) != (width, height):
                    raise ValueError(
                        "Hair environment faces have unequal mip dimensions"
                    )
                expected_bytes = width * height * 3 * 2
                if len(pixels) != expected_bytes:
                    raise ValueError(
                        f"Hair environment face needs {expected_bytes} bytes, "
                        f"got {len(pixels)}"
                    )
                level_faces.append(pixels)
            packed = np.frombuffer(
                b"".join(level_faces), dtype=np.float16,
            ).reshape(6, height, width, 3)
            glTexImage3D(
                GL_TEXTURE_2D_ARRAY, level, GL_RGB16F,
                width, height, 6, 0,
                GL_RGB, GL_HALF_FLOAT, packed,
            )
        glTexParameteri(
            GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MIN_FILTER,
            GL_LINEAR_MIPMAP_LINEAR,
        )
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_BASE_LEVEL, 0)
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAX_LEVEL, level_count - 1)

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
        glBindTexture(GL_TEXTURE_2D_ARRAY, 0)
        self._pending_fur_environment = None

    def _delete_bloom_targets(self):
        if self._hdr_color_buffers:
            glDeleteTextures(len(self._hdr_color_buffers), self._hdr_color_buffers)
        if self._fur_gbuffer_texture:
            glDeleteTextures(1, [self._fur_gbuffer_texture])
        if self._fur_normal_texture:
            glDeleteTextures(1, [self._fur_normal_texture])
        if self._fur_denoise_texture:
            glDeleteTextures(1, [self._fur_denoise_texture])
        if self._fur_oit_textures:
            glDeleteTextures(len(self._fur_oit_textures), self._fur_oit_textures)
        if self._fur_scene_depth_texture:
            glDeleteTextures(1, [self._fur_scene_depth_texture])
        if self._pingpong_textures:
            glDeleteTextures(len(self._pingpong_textures), self._pingpong_textures)
        if self._temporal_textures:
            glDeleteTextures(len(self._temporal_textures), self._temporal_textures)
        if self._hdr_depth_rbo:
            glDeleteRenderbuffers(1, [self._hdr_depth_rbo])
        if self._hdr_fbo:
            glDeleteFramebuffers(1, [self._hdr_fbo])
        if self._fur_denoise_fbo:
            glDeleteFramebuffers(1, [self._fur_denoise_fbo])
        if self._pingpong_fbos:
            glDeleteFramebuffers(len(self._pingpong_fbos), self._pingpong_fbos)
        if self._temporal_fbos:
            glDeleteFramebuffers(len(self._temporal_fbos), self._temporal_fbos)
        self._hdr_fbo = 0
        self._hdr_color_buffers = []
        self._fur_gbuffer_texture = 0
        self._fur_normal_texture = 0
        self._fur_denoise_fbo = 0
        self._fur_denoise_texture = 0
        self._fur_oit_textures = []
        self._fur_scene_depth_texture = 0
        self._fur_depth_snapshot_ready = False
        self._hdr_depth_rbo = 0
        self._pingpong_fbos = []
        self._pingpong_textures = []
        self._temporal_fbos = []
        self._temporal_textures = []
        self._temporal_sample_count = 0
        self._temporal_signature = None
        self._display_scene_texture = 0
        self._current_scene_texture = 0
        self._bloom_size = (0, 0)

    def _resize_bloom_targets(self, width: int, height: int):
        """Create floating-point scene/bright buffers and blur ping-pong targets."""
        if not self._bloom_supported or self._bloom_size == (width, height):
            return
        try:
            self._delete_bloom_targets()
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
            self._fur_gbuffer_texture = int(glGenTextures(1))
            glBindTexture(GL_TEXTURE_2D, self._fur_gbuffer_texture)
            glTexImage2D(
                # Retail's custom fur reciprocal depth feeds the float
                # g_ViewDepthBuffer. Preserve its 0.00025-0.005 dry offsets
                # without reducing precision before the Hair contact pass.
                GL_TEXTURE_2D, 0, GL_RGBA32F, width, height, 0,
                GL_RGBA, GL_FLOAT, None,
            )
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glFramebufferTexture2D(
                GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT2,
                GL_TEXTURE_2D, self._fur_gbuffer_texture, 0,
            )
            self._fur_normal_texture = int(glGenTextures(1))
            glBindTexture(GL_TEXTURE_2D, self._fur_normal_texture)
            glTexImage2D(
                GL_TEXTURE_2D, 0, GL_RGBA16F, width, height, 0,
                GL_RGBA, GL_FLOAT, None,
            )
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glFramebufferTexture2D(
                GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT3,
                GL_TEXTURE_2D, self._fur_normal_texture, 0,
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

            self._fur_denoise_fbo = int(glGenFramebuffers(1))
            self._fur_denoise_texture = int(glGenTextures(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._fur_denoise_fbo)
            glBindTexture(GL_TEXTURE_2D, self._fur_denoise_texture)
            glTexImage2D(
                GL_TEXTURE_2D, 0, GL_RGBA16F, width, height, 0,
                GL_RGBA, GL_FLOAT, None,
            )
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glFramebufferTexture2D(
                GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                GL_TEXTURE_2D, self._fur_denoise_texture, 0,
            )
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("Fur denoise framebuffer is incomplete")

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
            for fbo, tex_id in zip(self._temporal_fbos, self._temporal_textures):
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
                    GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                    GL_TEXTURE_2D, tex_id, 0,
                )
                if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                    raise RuntimeError("Temporal framebuffer is incomplete")
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

    def _accumulate_temporal_scene(self, projection, view, light_dir):
        """Accumulate stochastic opaque fur samples for a stationary camera."""
        if not self._temporal_accum_prog or len(self._temporal_fbos) != 2:
            self._display_scene_texture = self._hdr_color_buffers[0]
            return
        signature = (
            self._bloom_size,
            round(float(self.camera.yaw), 6),
            round(float(self.camera.pitch), 6),
            round(float(self.camera.dist), 6),
            tuple(round(float(value), 6) for value in self.camera.target),
            bool(self._show_fur),
            int(getattr(self, '_active_lod', 0)),
            len(self._gpu_meshes),
        )
        if signature != self._temporal_signature:
            self._temporal_signature = signature
            self._temporal_sample_count = 0

        target_index = self._temporal_sample_count % 2
        previous_index = 1 - target_index
        previous_count = min(self._temporal_sample_count, 31)
        history_weight = previous_count / float(previous_count + 1)
        glBindFramebuffer(GL_FRAMEBUFFER, self._temporal_fbos[target_index])
        glViewport(0, 0, *self._bloom_size)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glUseProgram(self._temporal_accum_prog)
        for sampler, unit in (
            ('uCurrent', 0), ('uHistory', 1), ('uFurGBuffer', 2),
        ):
            location = glGetUniformLocation(self._temporal_accum_prog, sampler)
            if location >= 0:
                glUniform1i(location, unit)
        _set_uniform_1f(
            self._temporal_accum_prog, 'uHistoryWeight', history_weight,
        )
        _set_uniform_2f(
            self._temporal_accum_prog, 'uCurrentUvOffset',
            *_temporal_current_sample_offset(
                self._current_temporal_jitter, self._bloom_size,
            ),
        )
        _set_uniform_2f(
            self._temporal_accum_prog, 'uProjectionScale',
            projection[0, 0], projection[1, 1],
        )
        _set_uniform_1f(
            self._temporal_accum_prog, 'uScreenToViewScaleX',
            2.0 / max(abs(float(projection[0, 0])), 0.000001),
        )
        view_light_dir = view[:3, :3] @ np.asarray(light_dir, dtype=np.float32)
        _set_uniform_3f(
            self._temporal_accum_prog, 'uWorldLightDir', *light_dir,
        )
        _set_uniform_3f(
            self._temporal_accum_prog, 'uViewLightDir', *view_light_dir,
        )
        _set_uniform_bool(
            self._temporal_accum_prog, 'uFurContactEnabled',
            self._fur_contact_enabled and bool(self._fur_gbuffer_texture),
        )
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(
            GL_TEXTURE_2D,
            self._current_scene_texture or self._hdr_color_buffers[0],
        )
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self._temporal_textures[previous_index])
        glActiveTexture(GL_TEXTURE2)
        glBindTexture(GL_TEXTURE_2D, self._fur_gbuffer_texture)
        glBindVertexArray(self._grid_vao)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
        glBindVertexArray(0)
        glActiveTexture(GL_TEXTURE2)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, 0)
        self._display_scene_texture = self._temporal_textures[target_index]
        self._temporal_sample_count += 1
        glEnable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

    def _denoise_fur_scene(self, projection, view):
        """Apply the captured tangent/depth/mask-gated HairDenoise gather."""
        self._current_scene_texture = self._hdr_color_buffers[0]
        if not (
            self._fur_denoise_prog and self._fur_denoise_fbo
            and self._fur_denoise_texture and self._fur_gbuffer_texture
            and self._fur_normal_texture and self._show_fur
            and self._fur_denoise_enabled
        ):
            return
        # Retail's destination already contains the other shading models;
        # CS_HairDenoise writes only worklisted hair pixels. Preserve that
        # behavior so non-fur scene color does not take an extra FP16 roundtrip.
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self._hdr_fbo)
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
            self._fur_denoise_prog, 'uViewportSize', *self._bloom_size,
        )
        frame_location = glGetUniformLocation(
            self._fur_denoise_prog, 'uFrameIndex',
        )
        if frame_location >= 0:
            glUniform1i(frame_location, int(self._temporal_sample_count))
        temporal_location = glGetUniformLocation(
            self._fur_denoise_prog, 'uTemporalIndex',
        )
        if temporal_location >= 0:
            glUniform1f(
                temporal_location,
                float(_halton((self._temporal_sample_count % 32) + 1, 2)),
            )
        for unit, texture_id in (
            (GL_TEXTURE0, self._hdr_color_buffers[0]),
            (GL_TEXTURE1, self._fur_gbuffer_texture),
            (GL_TEXTURE2, self._fur_normal_texture),
        ):
            glActiveTexture(unit)
            glBindTexture(GL_TEXTURE_2D, texture_id)
        glBindVertexArray(self._grid_vao)
        glDrawArrays(GL_TRIANGLES, 0, self._grid_count)
        glBindVertexArray(0)
        for unit in (GL_TEXTURE2, GL_TEXTURE1, GL_TEXTURE0):
            glActiveTexture(unit)
            glBindTexture(GL_TEXTURE_2D, 0)
        self._current_scene_texture = self._fur_denoise_texture
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

    def _draw_fur_strands(self, mvp, model, normal_mat, eye,
                          light_dir, fill_dir):
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

        glUseProgram(self._fur_shader_prog)
        _set_uniform_mat4(self._fur_shader_prog, 'uMVP', mvp)
        _set_uniform_mat4(self._fur_shader_prog, 'uModel', model)
        _set_uniform_mat3(self._fur_shader_prog, 'uNormal', normal_mat)
        _set_uniform_3f(self._fur_shader_prog, 'uEye', *eye)
        _set_uniform_3f(self._fur_shader_prog, 'uLightDir', *light_dir)
        _set_uniform_3f(self._fur_shader_prog, 'uFillDir', *fill_dir)
        _set_uniform_1f(
            self._fur_shader_prog, 'uFurWindStrength', self._fur_wind_strength,
        )
        _set_uniform_3f(
            self._fur_shader_prog, 'uFurWindVector', *self._fur_wind_vector,
        )
        wind_time = self._fur_wind_time_override
        if wind_time is None:
            wind_time = time.monotonic() - self._fur_wind_epoch
        _set_uniform_1f(
            self._fur_shader_prog, 'uFurWindTime', wind_time,
        )
        _set_uniform_1f(
            self._fur_shader_prog, 'uFurWindObjectPhase',
            self._fur_wind_object_phase,
        )
        _set_uniform_2f(
            self._fur_shader_prog, 'uViewportSize',
            *self._framebuffer_size(),
        )
        frame_location = glGetUniformLocation(
            self._fur_shader_prog, 'uFrameIndex',
        )
        if frame_location >= 0:
            glUniform1i(frame_location, int(self._temporal_sample_count))
        temporal_location = glGetUniformLocation(
            self._fur_shader_prog, 'uTemporalIndex',
        )
        if temporal_location >= 0:
            temporal_index = _halton(
                (self._temporal_sample_count % 32) + 1, 2,
            )
            glUniform1f(temporal_location, float(temporal_index))
        for sampler, unit in (
            ('uFurAlbedo', 0), ('uFurControl', 1), ('uFurLayers', 2),
            ('uFurSpecular', 3),
            ('uFurEnvironment', 4), ('uFurBrdfLut', 5),
        ):
            location = glGetUniformLocation(self._fur_shader_prog, sampler)
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
            self._fur_shader_prog, 'uHasFurEnvironment', has_fur_environment,
        )
        glActiveTexture(GL_TEXTURE4)
        glBindTexture(
            GL_TEXTURE_2D_ARRAY,
            self._fur_environment_texture if has_fur_environment else 0,
        )
        glActiveTexture(GL_TEXTURE5)
        glBindTexture(
            GL_TEXTURE_2D,
            self._fur_brdf_texture if has_fur_environment else 0,
        )
        for mesh in fur_meshes:
            _set_uniform_1f(self._fur_shader_prog, 'uFurLength', mesh.fur_length)
            _set_uniform_1f(
                self._fur_shader_prog, 'uFurWindRadius', mesh.fur_wind_radius,
            )
            _set_uniform_1f(
                self._fur_shader_prog, 'uFurWindTurbulence',
                mesh.fur_wind_turbulence,
            )
            _set_uniform_1f(self._fur_shader_prog, 'uFurDensity', mesh.fur_density)
            _set_uniform_1f(
                self._fur_shader_prog, 'uFurOffsetScale',
                mesh.fur_offset_scale,
            )
            _set_uniform_1f(
                self._fur_shader_prog, 'uFurGlossScale', mesh.fur_gloss_scale,
            )
            _set_uniform_1f(
                self._fur_shader_prog, 'uFurSpecularScale',
                mesh.fur_specular_scale,
            )
            _set_uniform_1f(
                self._fur_shader_prog, 'uFurTransmittanceScale',
                mesh.fur_transmittance_scale,
            )
            _set_uniform_1f(
                self._fur_shader_prog, 'uFurWetness', self._fur_wetness,
            )
            _set_uniform_bool(
                self._fur_shader_prog, 'uHasFurSpecular',
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
            location = glGetUniformLocation(self._fur_shader_prog, 'uLayerCount')
            if location >= 0:
                glUniform1i(location, layer_count)
            layer_location = glGetUniformLocation(
                self._fur_shader_prog, 'uReverseLayer',
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
        glBindTexture(GL_TEXTURE_2D_ARRAY, 0)
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

    def paintGL(self):
        if not _HAS_OPENGL:
            return

        # Upload any pending model now that GL context is active
        if self._pending_model is not None:
            self._upload_pending_model()

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
        glBindFramebuffer(
            GL_FRAMEBUFFER,
            self._hdr_fbo if use_hdr else self.defaultFramebufferObject(),
        )
        glViewport(0, 0, *framebuffer_size)
        if use_hdr:
            if self._fur_gbuffer_texture:
                glDrawBuffers(4, [
                    GL_COLOR_ATTACHMENT0,
                    GL_COLOR_ATTACHMENT1,
                    GL_COLOR_ATTACHMENT2,
                    GL_COLOR_ATTACHMENT3,
                ])
            glClearBufferfv(
                GL_COLOR, 0, np.array([0.102, 0.110, 0.133, 1.0], dtype=np.float32),
            )
            glClearBufferfv(
                GL_COLOR, 1, np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            )
            if self._fur_gbuffer_texture:
                glClearBufferfv(
                    GL_COLOR, 2,
                    np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
                )
                glClearBufferfv(
                    GL_COLOR, 3,
                    np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
                )
                glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])
            glClear(GL_DEPTH_BUFFER_BIT)
        else:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        aspect = w / max(h, 1)
        self._current_temporal_jitter = (0.0, 0.0)
        if getattr(self, '_ortho', False):
            # Orthographic: scale half-height by camera distance.
            # near/far are expressed in view space; we push near well behind
            # the eye (negative) so the infinite grid is never clipped, while
            # keeping far large enough for big scenes.
            half_h = self.camera.dist * 0.5
            extent = max(self.camera.dist * 10.0, 500.0)
            proj   = _ortho(-half_h * aspect, half_h * aspect,
                            -half_h, half_h, -extent, extent)
        else:
            if hasattr(self, '_aabb_min') and hasattr(self, '_aabb_max'):
                near, far = _perspective_clip_planes(
                    self.camera, self._aabb_min, self._aabb_max,
                )
            else:
                near = max(self.camera.dist * 1e-4, 0.0001)
                far = max(self.camera.dist * 10.0, 100.0)
            proj = _perspective(60.0, aspect, near, far)
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

        light_dir = np.array([0.6, 1.0, 0.8], np.float32)
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
            if use_hdr and self._fur_gbuffer_texture:
                glDrawBuffers(4, [
                    GL_COLOR_ATTACHMENT0,
                    GL_COLOR_ATTACHMENT1,
                    GL_COLOR_ATTACHMENT2,
                    GL_COLOR_ATTACHMENT3,
                ])
            glUseProgram(self._shader_prog)
            _set_uniform_mat4(self._shader_prog, 'uMVP', mvp)
            _set_uniform_mat4(self._shader_prog, 'uModel', model)
            _set_uniform_mat3(self._shader_prog, 'uNormal', normal_mat)
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

            if use_hdr and self._fur_gbuffer_texture:
                glDrawBuffers(4, [
                    GL_COLOR_ATTACHMENT0,
                    GL_COLOR_ATTACHMENT1,
                    GL_COLOR_ATTACHMENT2,
                    GL_COLOR_ATTACHMENT3,
                ])
            self._draw_fur_strands(
                mvp, model, normal_mat, eye, light_dir, fill_dir,
            )
            if use_hdr:
                glDrawBuffers(2, [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1])

        if use_hdr:
            self._denoise_fur_scene(proj, view)
            self._accumulate_temporal_scene(proj, view, light_dir)
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
        self._redraw()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _free_gpu_meshes(self):
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

def _ortho(left: float, right: float, bottom: float, top: float,
           near: float, far: float) -> np.ndarray:
    return np.array([
        [2/(right-left), 0,              0,             -(right+left)/(right-left)],
        [0,              2/(top-bottom), 0,             -(top+bottom)/(top-bottom)],
        [0,              0,             -2/(far-near),  -(far+near)/(far-near)    ],
        [0,              0,              0,              1                        ],
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

def _hsv_to_rgb(h, s, v):
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s);  q = v * (1 - f * s);  t = v * (1 - (1 - f) * s)
    i %= 6
    return [(v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q)][i]
