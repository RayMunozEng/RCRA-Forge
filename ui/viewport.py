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

from core.mesh import ModelAsset, MeshDefinition, mesh_to_numpy


BASE_COLOR_ROLES = ('base_color', 'color_id', 'albedo', 'diffuse')
NORMAL_ROLES = ('normal',)
FUR_CONTROL_ROLES = ('fur_control',)
FUR_SHELL_LAYERS = 16
FUR_SHELL_LENGTH = 0.03
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


def _compressed_gl_format(dxgi_format: int):
    """Map supported DXGI block formats to their identical OpenGL formats."""
    return {
        0x4F: GL_COMPRESSED_RED_RGTC1,
        0x50: GL_COMPRESSED_RED_RGTC1,
        0x51: GL_COMPRESSED_SIGNED_RED_RGTC1,
        0x5F: GL_COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT,
        0x60: GL_COMPRESSED_RGB_BPTC_SIGNED_FLOAT,
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

uniform mat4 uMVP;
uniform mat4 uModel;
uniform mat3 uNormal;
uniform float uFurLayer;
uniform float uFurLength;

out vec3 vNormal;
out vec3 vWorldPos;
out vec2 vUV;

void main() {
    vec3 displacedPos = aPos + normalize(aNormal) * uFurLength * uFurLayer;
    vec4 worldPos = uModel * vec4(displacedPos, 1.0);
    vWorldPos  = worldPos.xyz;
    vNormal    = normalize(uNormal * aNormal);
    vUV        = aUV;
    gl_Position = uMVP * vec4(displacedPos, 1.0);
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
uniform float     uFurLayer;
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
        return;
    }

    vec2 effectUV = length(vUV) > 0.0001 ? vUV : vWorldPos.xz * 0.08;
    vec3 n = normalize(vNormal);
    vec4 albedoSample = uHasTexture ? texture(uAlbedo, vUV) : vec4(1.0);
    vec4 furControl = uHasFurControl ? texture(uFurControlMap, vUV) : vec4(1.0);
    if (uIsFur && uHasFurControl) {
        // B controls local fiber length and A controls density.  Cull shells
        // past the authored length, then progressively thin the remaining
        // layers toward their tips.  Without this pass the fur mesh becomes
        // an opaque shell that hides the textured skin below it.
        float localLength = clamp(furControl.b * 1.25, 0.02, 1.0);
        if (uFurLayer > localLength) {
            discard;
        }
        float dither = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233)))
                             * 43758.5453);
        float densityCutoff = mix(0.06, 0.78, uFurLayer) + dither * 0.16;
        if (furControl.a < densityCutoff) {
            discard;
        }
    }
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
        self.fur_control_tex_id: int = 0
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
               uvs: np.ndarray, indices: np.ndarray):
        """Upload pre-extracted numpy arrays to the GPU."""
        n = len(positions)
        if n == 0 or indices is None or len(indices) == 0:
            return

        nrm = normals if normals is not None and len(normals) == n \
              else np.zeros((n, 3), np.float32)
        uv  = uvs if uvs is not None and len(uvs) == n \
              else np.zeros((n, 2), np.float32)

        interleaved = np.concatenate([
            positions.astype(np.float32),
            nrm.astype(np.float32),
            uv.astype(np.float32),
        ], axis=1).astype(np.float32)

        self.vao = glGenVertexArrays(1)
        self.vbo = glGenBuffers(1)
        self.ebo = glGenBuffers(1)

        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, interleaved.nbytes, interleaved, GL_STATIC_DRAW)

        stride = 8 * 4
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(24))
        glEnableVertexAttribArray(2)

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
            'fur_control_tex_id',
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
        self._grid_prog:   int = 0
        self._blur_prog:   int = 0
        self._composite_prog: int = 0
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
        self._hdr_depth_rbo = 0
        self._pingpong_fbos: list[int] = []
        self._pingpong_textures: list[int] = []
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
        if self._animated_materials:
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
                compressed_mip0 = metadata.get('compressed_mip0')
                dxgi_format = metadata.get('dxgi_format')
                compressed_format = _compressed_gl_format(dxgi_format)
                if compressed_mip0 and compressed_format is not None:
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
            else:
                slots_by_attr = {
                    'texture_id': data,
                    'normal_tex_id': None,
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
                gpu.upload(positions, normals, resolved_uvs, indices)
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

    def _delete_bloom_targets(self):
        if self._hdr_color_buffers:
            glDeleteTextures(len(self._hdr_color_buffers), self._hdr_color_buffers)
        if self._pingpong_textures:
            glDeleteTextures(len(self._pingpong_textures), self._pingpong_textures)
        if self._hdr_depth_rbo:
            glDeleteRenderbuffers(1, [self._hdr_depth_rbo])
        if self._hdr_fbo:
            glDeleteFramebuffers(1, [self._hdr_fbo])
        if self._pingpong_fbos:
            glDeleteFramebuffers(len(self._pingpong_fbos), self._pingpong_fbos)
        self._hdr_fbo = 0
        self._hdr_color_buffers = []
        self._hdr_depth_rbo = 0
        self._pingpong_fbos = []
        self._pingpong_textures = []
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
            self._hdr_depth_rbo = int(glGenRenderbuffers(1))
            glBindRenderbuffer(GL_RENDERBUFFER, self._hdr_depth_rbo)
            glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, width, height)
            glFramebufferRenderbuffer(
                GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, self._hdr_depth_rbo,
            )
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("HDR framebuffer is incomplete")

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
        glBindTexture(GL_TEXTURE_2D, self._hdr_color_buffers[0])
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
            glClearBufferfv(
                GL_COLOR, 0, np.array([0.102, 0.110, 0.133, 1.0], dtype=np.float32),
            )
            glClearBufferfv(
                GL_COLOR, 1, np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            )
            glClear(GL_DEPTH_BUFFER_BIT)
        else:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        aspect = w / max(h, 1)
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
            glUseProgram(self._shader_prog)
            _set_uniform_mat4(self._shader_prog, 'uMVP', mvp)
            _set_uniform_mat4(self._shader_prog, 'uModel', model)
            _set_uniform_mat3(self._shader_prog, 'uNormal', normal_mat)
            _set_uniform_3f(self._shader_prog, 'uLightDir', *light_dir)
            _set_uniform_3f(self._shader_prog, 'uFillDir',  *fill_dir)
            _set_uniform_bool(self._shader_prog, 'uWireframe', self._wireframe)
            _set_uniform_1f(self._shader_prog, 'uTime', time.monotonic())
            _set_uniform_1f(self._shader_prog, 'uFurLayer', 0.0)
            _set_uniform_1f(self._shader_prog, 'uFurLength', 0.0)

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
                shell_count = FUR_SHELL_LAYERS if has_fur_control else 1
                for shell_index in range(shell_count):
                    fur_layer = shell_index / max(shell_count - 1, 1)
                    _set_uniform_1f(self._shader_prog, 'uFurLayer', fur_layer)
                    _set_uniform_1f(
                        self._shader_prog, 'uFurLength',
                        FUR_SHELL_LENGTH if has_fur_control else 0.0,
                    )
                    gm.draw()
                for enabled, unit, _tex_id in texture_bindings:
                    if enabled:
                        glActiveTexture(unit)
                        glBindTexture(GL_TEXTURE_2D, 0)

            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        if use_hdr:
            self._composite_bloom()

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
