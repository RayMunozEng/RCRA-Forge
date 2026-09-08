import hashlib
import inspect
import struct

import numpy as np
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from ui.camera_controls import autodesk_mouse_mode
from ui.model_preview import SoftwareModelPreview
from ui.viewport import (
    ArcballCamera,
    BASE_COLOR_ROLES,
    FUR_CONTROL_ROLES,
    NORMAL_ROLES,
    FRAG_SRC,
    VERT_SRC,
    _best_texture_slot,
    _can_draw_fur_strands,
    _fur_density_from_texture_slot,
    FUR_SHELL_FRAG_SRC,
    FUR_FRAG_SRC,
    FUR_SHELL_GEOM_SRC,
    FUR_MATERIAL_FRAG_SRC,
    FUR_SHELL_VERT_SRC,
    FUR_DENOISE_FRAG,
    FUR_CONTACT_FRAG,
    FUR_SCENE_LIGHTING_FRAG,
    MOTION_BLUR_DOWNSAMPLE_FRAG,
    TEMPORAL_ACCUM_FRAG,
    TEMPORAL_ALPHA_HALF_FRAG,
    TEMPORAL_ALPHA_MASK_FRAG,
    TEMPORAL_DISOCCLUSION_FRAG,
    TEMPORAL_HALF_BASE_FRAG,
    TEMPORAL_LINEAR_DEPTH_FRAG,
    _fur_header_from_texture_slot,
    _fur_offset_scale_from_texture_slot,
    _fur_shading_from_texture_slot,
    _fur_wind_turbulence_from_texture_slot,
    _build_fur_layer_volume,
    _build_fur_layer_mips,
    _fur_adjusted_shell_depth,
    _fur_shell_availability,
    _fur_length_from_texture_slot,
    _fur_root_lod_factor,
    _fur_tip_width_factors,
    _is_alpha_cutout_material,
    _is_authored_wool,
    _is_composite_shell_material,
    _is_fur_material,
    _is_lava_material,
    _is_retail_blizar_lava_material,
    _is_lava_rock_model,
    _is_lavafall_model,
    _is_srgb_texture_role,
    _temporal_current_sample_offset,
    _temporal_filter_offset_pixels,
    _temporal_history_jitter_offset,
    _lava_flow_sample_offsets,
    _merge_material_textures,
    _mesh_tangents,
    _postprocess_settings,
    _perspective_reverse_z_zero_to_one,
    _perspective_clip_planes,
    _ortho_reverse_z_zero_to_one,
    _resolved_mesh_uvs,
    _scaled_framebuffer_size,
    _shader_with_raster_mode,
    _supports_native_raster,
    _uses_molten_shader,
    Viewport3D,
)
from core.texture import TextureAsset
from core.fur_resources import default_hair_brdf_rg_half
from core.hair_temporal import (
    DITHER_TABLE_SHA256,
    TEMPORAL_CONDITIONAL_REJECTION_FLOOR,
    TEMPORAL_DITHER_TABLE,
    TEMPORAL_MINIMUM_REJECTION_FLOOR,
    TEMPORAL_NONOPAQUE_RESPONSE_FALLBACK,
    temporal_dither_constants,
    temporal_history_warmup,
    temporal_minimum_rejection,
)


def _slot(width: int, height: int, name: str):
    return (b"rgba", width, height, name)


def test_recovered_hair_brdf_lookup_is_exact_and_complete():
    lookup = default_hair_brdf_rg_half()

    assert len(lookup) == 64 * 64 * 2 * 2
    assert hashlib.sha256(lookup).hexdigest() == (
        "4fa9755a296ec4c8c11d19e62598217eedd8625814bb75128c947ca325038672"
    )


def test_bc6h_render_payload_preserves_original_top_mip_blocks():
    top_mip = bytes(range(64))
    lower_mips = b"lower mip data"
    texture = TextureAsset(
        sd_len=len(top_mip) + len(lower_mips),
        sd_width=8,
        sd_height=8,
        sd_mips=2,
        hd_len=0,
        hd_width=0,
        hd_height=0,
        hd_mips=0,
        fmt=0x5F,
        array_size=1,
        planes=1,
        pixel_data=top_mip + lower_mips,
    )

    assert texture.compressed_mip0() == top_mip


def test_block_compressed_render_payload_preserves_authored_mips():
    mip0 = bytes(range(64))
    mip1 = bytes(range(16))
    texture = TextureAsset(
        sd_len=len(mip0) + len(mip1),
        sd_width=8,
        sd_height=8,
        sd_mips=2,
        hd_len=0,
        hd_width=0,
        hd_height=0,
        hd_mips=0,
        fmt=0x62,
        array_size=1,
        planes=1,
        pixel_data=mip0 + mip1,
    )

    assert texture.compressed_mips() == [
        (8, 8, mip0),
        (4, 4, mip1),
    ]


def test_block_compressed_render_payload_joins_hd_and_sd_mip_tail():
    hd_8 = bytes(range(32))
    hd_4 = bytes(range(8))
    sd_2 = bytes(range(8, 16))
    sd_1 = bytes(range(16, 24))
    texture = TextureAsset(
        sd_len=len(sd_2) + len(sd_1),
        sd_width=2,
        sd_height=2,
        sd_mips=2,
        hd_len=len(hd_8) + len(hd_4),
        hd_width=8,
        hd_height=8,
        hd_mips=2,
        fmt=0x48,
        array_size=1,
        planes=1,
        pixel_data=sd_2 + sd_1,
        hd_pixel_data=hd_8 + hd_4,
    )

    assert texture.compressed_mips() == [
        (8, 8, hd_8),
        (4, 4, hd_4),
        (2, 2, sd_2),
        (1, 1, sd_1),
    ]


def test_bc6_cube_payload_splits_six_face_major_mip_chains():
    faces = []
    payload = bytearray()
    for face in range(6):
        mip0 = bytes([face]) * 64
        mip1 = bytes([face + 16]) * 16
        faces.append([(8, 8, mip0), (4, 4, mip1)])
        payload.extend(mip0)
        payload.extend(mip1)
    texture = TextureAsset(
        sd_len=len(payload),
        sd_width=8,
        sd_height=8,
        sd_mips=2,
        hd_len=0,
        hd_width=0,
        hd_height=0,
        hd_mips=0,
        fmt=0x5F,
        array_size=1,
        planes=4,
        pixel_data=bytes(payload),
    )

    assert texture.compressed_cube_mips() == faces


def test_retail_lava_uses_restrained_isolated_preview_postprocess():
    lava_exposure, lava_bloom = _postprocess_settings(True)
    default_exposure, default_bloom = _postprocess_settings(False)

    assert lava_exposure < default_exposure
    assert lava_bloom < default_bloom


def test_best_texture_slot_uses_largest_base_color_variant():
    palette = _slot(64, 1, "armor_palette")
    diffuse = _slot(2048, 2048, "hero_rivet_body_c")
    slots = {
        "base_color": diffuse,
        "base_color_4": palette,
        "normal": _slot(2048, 2048, "hero_rivet_body_n"),
    }

    assert _best_texture_slot(slots, BASE_COLOR_ROLES) is diffuse


def test_best_texture_slot_uses_largest_indexed_normal_map():
    detail = _slot(128, 128, "denim_detail_n")
    primary = _slot(2048, 2048, "hero_ratchet_harness_n")
    slots = {"normal": detail, "normal_5": primary}

    assert _best_texture_slot(slots, NORMAL_ROLES) is primary


def test_fur_material_classification_excludes_helpers_and_nofur_variants():
    assert _is_fur_material(
        "material/characters/hero/hero_ratchet_head/hero_ratchet_head_fur.material"
    )
    assert _is_fur_material("material/characters/hero/hero_rivet_head_fur.material")
    assert not _is_fur_material("material/characters/cat/cat_nofur.material")
    assert not _is_fur_material("hero_ratchet_compositeshell.material")
    assert _is_composite_shell_material("hero_ratchet_compositeshell.material")


def test_fur_control_selects_largest_matching_map():
    small = _slot(64, 64, "preview_fur_control")
    authored = _slot(256, 256, "hero_ratchet_head_fur_control")
    assert _best_texture_slot(
        {"fur_control": authored, "fur_control_4": small},
        FUR_CONTROL_ROLES,
    ) is authored


def test_fur_length_uses_authored_material_setting():
    slot = (*_slot(256, 256, "hero_rivet_head_fur_control"), {
        "fur_settings": (0.012, 16.0, 0.9, 1.0, 1.0, 0.1, 0.0),
        "fur_layer_count": 32,
        "fur_lod_reduction": 0.25,
    })
    assert _fur_length_from_texture_slot(slot) == 0.012
    assert _fur_density_from_texture_slot(slot) == 16.0
    assert _fur_offset_scale_from_texture_slot(slot) == 0.9
    assert _fur_shading_from_texture_slot(slot) == (1.0, 1.0, 0.1)
    assert _fur_wind_turbulence_from_texture_slot(slot) == 0.0
    assert _fur_header_from_texture_slot(slot) == (32, 0.25)
    assert _fur_length_from_texture_slot(None) == 0.03
    assert _fur_density_from_texture_slot(None) == 16.0
    assert _fur_offset_scale_from_texture_slot(None) == 0.0
    assert _fur_header_from_texture_slot(None) == (0, 0.0)


def test_fur_root_lod_is_stable_and_preserves_a_distant_floor():
    assert _fur_root_lod_factor(0.0) == 0.25
    assert _fur_root_lod_factor(1.0) == 0.25
    assert 0.25 < _fur_root_lod_factor(3.5) < 1.0
    assert _fur_root_lod_factor(6.0) == 1.0
    assert _fur_root_lod_factor(100.0) == 1.0


def test_fur_ribbon_tapers_to_a_true_zero_width_tip():
    root_width, root_floor = _fur_tip_width_factors(0.0)
    middle_width, middle_floor = _fur_tip_width_factors(0.5)
    tip_width, tip_floor = _fur_tip_width_factors(1.0)

    assert root_width == 1.0
    assert root_floor == 0.65
    assert 0.0 < middle_width < root_width
    assert 0.0 < middle_floor < root_floor
    assert tip_width == tip_floor == 0.0


def test_mesh_tangents_follow_indexed_uv_orientation_and_handedness():
    positions = np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
    ], dtype=np.float32)
    normals = np.tile([0.0, 0.0, 1.0], (4, 1)).astype(np.float32)
    uvs = positions[:, :2].copy()
    indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint16)

    tangents = _mesh_tangents(positions, normals, uvs, indices)

    np.testing.assert_allclose(tangents[:, :3], [[1.0, 0.0, 0.0]] * 4)
    np.testing.assert_allclose(tangents[:, 3], [1.0] * 4)


def test_recovered_fur_shell_budget_culls_front_facing_outer_layers():
    assert _fur_shell_availability(0.0) == 1.0
    assert 0.10 <= _fur_shell_availability(1.0) < 0.102
    assert 0.65 <= _fur_shell_availability(0.5) <= 0.652
    assert _fur_adjusted_shell_depth(0.05, 1.0) is not None
    assert _fur_adjusted_shell_depth(0.25, 1.0) is None
    assert _fur_adjusted_shell_depth(0.75, 0.0) == 0.75


def test_recovered_fur_shader_keeps_exact_cull_face_and_hash_terms():
    assert "aDecodeCorrection * 0.0065" in FUR_SHELL_VERT_SRC
    assert "2.0 * (1.0 - front) * (1.0 - front)" in FUR_SHELL_VERT_SRC
    assert "return texelFetch(uFurControl, texel, 0).b;" in FUR_SHELL_VERT_SRC
    assert "controlLength * uFurLength - 0.0075" in FUR_SHELL_VERT_SRC
    assert "* 50.0, 0.0, 1.0" in FUR_SHELL_VERT_SRC
    assert "layerDepth * layerDepth + 0.4 * layerDepth" in FUR_SHELL_VERT_SRC
    assert "const vec4 RETAIL_WIND_RANDOM[64]" in FUR_SHELL_VERT_SRC
    assert "uFurWindTurbulence * 20.0 + 10.0" in FUR_SHELL_VERT_SRC
    assert "uFurWindTurbulence * 100.0 + 50.0" in FUR_SHELL_VERT_SRC
    assert "fract(noiseTime * 0.016393441706895828) * 61.0" in FUR_SHELL_VERT_SRC
    assert "uFurWindRadius * 0.1" in FUR_SHELL_VERT_SRC
    assert "inverse(mat3(uModel)) * uFurWindVector" in FUR_SHELL_VERT_SRC
    assert "cross(localTangent, localNormal)" in FUR_SHELL_VERT_SRC
    assert "uPreviousMVP * vec4(previousLocalPosition, 1.0)" in FUR_SHELL_VERT_SRC
    assert "vPreviousClip = vsPreviousClip[index]" in FUR_SHELL_GEOM_SRC
    assert "vsShellVisible[0] == 0" in FUR_SHELL_GEOM_SRC
    assert "vsShellVisible[1] == 0" in FUR_SHELL_GEOM_SRC
    assert "vsShellVisible[2] == 0" in FUR_SHELL_GEOM_SRC
    assert "gl_FrontFacing ? 1.0 : -1.0" in FUR_SHELL_FRAG_SRC
    assert "vec2 nativePixel = furNativePixel(pixel)" in FUR_SHELL_FRAG_SRC
    assert "return vec2(fragmentPixel.x, uViewportSize.y - fragmentPixel.y)" in FUR_SHELL_FRAG_SRC
    assert "#ifdef RCRA_NATIVE_UPPER_LEFT" in FUR_SHELL_FRAG_SRC
    assert "sampleDepth - depthBias > gl_FragCoord.z" in FUR_FRAG_SRC
    assert "0.1 + gl_FragCoord.z * 0.90" in FUR_FRAG_SRC
    assert "vec2 cell = floor(pixel)" in FUR_SHELL_FRAG_SRC
    assert "floor((phase * 0.1 + 0.45) + wetBase)" in FUR_SHELL_FRAG_SRC
    assert "vec2 layerUV = furLayerUV(" in FUR_SHELL_FRAG_SRC
    assert "layerUvDivisor(gl_FragCoord.xy, wetness)" in FUR_SHELL_FRAG_SRC
    assert "0.95 * controlLength + 0.05" in FUR_SHELL_FRAG_SRC
    assert "furLength + 0.005" in FUR_SHELL_FRAG_SRC
    assert "FurGBuffer = vec4(strandTangent" in FUR_SHELL_FRAG_SRC
    assert "void recoveredHairBasis(" in FUR_SHELL_FRAG_SRC
    assert "hairLobeFrame(strandTangent, geometricNormal, viewDirection)" in FUR_SHELL_FRAG_SRC
    assert "HairMaterialResponse material = hairMaterialResponse(" in FUR_SHELL_FRAG_SRC
    assert "material.primaryAlpha.x, material.primaryAlpha.y" in FUR_SHELL_FRAG_SRC
    assert "hairSecondaryStrand(strandTangent, normal, packedStrand >> 26u)" in FUR_SHELL_FRAG_SRC
    assert "sqrt(max(sampledResponse.r, 0.0)) * glossScale" in FUR_SHELL_FRAG_SRC
    assert "sampledResponse.g * specularScale" in FUR_SHELL_FRAG_SRC
    assert "primaryFresnel * primaryDistribution" in FUR_SHELL_FRAG_SRC
    assert "hairTransmissionResponse(" in FUR_SHELL_FRAG_SRC
    assert "hairDiffuseResponse(normalLight, material.transmission)" in FUR_SHELL_FRAG_SRC
    assert "hairResolveWeights(material.transmission, normalView, material.occlusion, 1.0)" in FUR_SHELL_FRAG_SRC
    assert "hairResolveLighting(albedo.rgb, material.occlusion" in FUR_SHELL_FRAG_SRC
    assert "vec3 sampleD3DCube" in FUR_SHELL_FRAG_SRC
    assert "5.0 - clamp(environment.averageGloss" in FUR_SHELL_FRAG_SRC
    assert "environmentBrdf.x * material.primaryF0 + environmentBrdf.y" in FUR_SHELL_FRAG_SRC
    assert "0.35 + key * 0.80 + fill * 0.30" not in FUR_SHELL_FRAG_SRC
    assert "uFurTransmittanceScale * 0.20" not in FUR_SHELL_FRAG_SRC
    assert "FurNormalMask = vec4(normal, 1.0)" in FUR_SHELL_FRAG_SRC
    assert "for (int i = 0; i < 3; ++i)" in FUR_DENOISE_FRAG
    assert "200.0 / centerDepth" in FUR_DENOISE_FRAG
    assert "sqrt(1.0 - abs(dot(normal, strand))) * 0.05" in FUR_DENOISE_FRAG
    assert "rayLength = min(" in FUR_DENOISE_FRAG
    assert "0.0025" in FUR_DENOISE_FRAG
    assert "hairContactVisibility" in FUR_CONTACT_FRAG
    assert "indirect.rgb + key.rgb * visibility" in FUR_CONTACT_FRAG
    assert "pixel, viewDepth, normal, geometry.direction, viewLight" in FUR_SCENE_LIGHTING_FRAG
    assert "uHairViewToScreen, uViewportSize, noiseAnglePhase, 0.0" in FUR_SCENE_LIGHTING_FRAG
    assert "hairSceneCloudVisibility(worldPoint)" in FUR_SCENE_LIGHTING_FRAG
    assert "uHairSceneConstants[41]" in FUR_SCENE_LIGHTING_FRAG
    assert "hairSceneKeyGobo(worldPoint, radiance)" in FUR_SCENE_LIGHTING_FRAG
    assert "uHairSceneConstants[40]" in FUR_SCENE_LIGHTING_FRAG
    assert "hairSceneKeyShadowVolumes(" in FUR_SCENE_LIGHTING_FRAG
    assert "uint(fract(encoded) * 64.0)" in FUR_SCENE_LIGHTING_FRAG
    assert "hairContactVisibility" not in TEMPORAL_ACCUM_FRAG
    assert "layout(location = 4) out vec2 Motion" in FUR_MATERIAL_FRAG_SRC
    assert "layout(location = 5) out uint Stencil" in FUR_MATERIAL_FRAG_SRC
    assert "Stencil = 128u" in FUR_MATERIAL_FRAG_SRC
    assert "Motion = furMotionVector(" in FUR_MATERIAL_FRAG_SRC
    assert "uMotionNearPlane, uViewportSize" in FUR_MATERIAL_FRAG_SRC
    assert "vPreviousClip = uPreviousMVP * vec4(aPreviousPos, 1.0)" in VERT_SRC
    assert "layout(location = 3) out vec2 SceneVelocity" in FRAG_SRC
    assert "layout(location = 4) out uint SceneStencil" in FRAG_SRC
    assert "SceneStencil = 0u" in FRAG_SRC
    assert "textureGather(uOpaqueMotion, uv, 0)" in MOTION_BLUR_DOWNSAMPLE_FRAG
    assert "uLinearDepth, currentPixel" in TEMPORAL_ACCUM_FRAG
    assert "texelFetch(uOpaqueMotion, velocityPixel, 0).xy" in TEMPORAL_ACCUM_FRAG
    assert "texelFetch(uStencil, velocityPixel, 0).r & 128u" in TEMPORAL_ACCUM_FRAG
    assert "float(category) * uNonopaqueStencilRejection" in TEMPORAL_ACCUM_FRAG
    assert "centerDepth <= 1.025 * diagonalDepth" in TEMPORAL_ACCUM_FRAG
    assert "vec2 motionToPreviousPixels = vec2(-motionPixels.x, motionPixels.y)" in TEMPORAL_ACCUM_FRAG
    assert "vec2 historyUV = historyPixel * texel + uHistoryJitterOffset" in TEMPORAL_ACCUM_FRAG
    assert "uCurrentUvOffset" not in TEMPORAL_ACCUM_FRAG
    assert "float rejection = uHistoryWarmup" in TEMPORAL_ACCUM_FRAG
    assert "vec2 disocclusion = texelFetch(uDisocclusion" in TEMPORAL_ACCUM_FRAG
    assert "rejection = max(rejection, 0.5 * disocclusion.g)" in TEMPORAL_ACCUM_FRAG
    assert "uNonopaqueStencilRejection" in TEMPORAL_ACCUM_FRAG
    assert "layout(location = 1) out float TemporalDepth" not in TEMPORAL_ACCUM_FRAG
    assert "float alphaMask = textureLod(uAlphaMask, currentUV, 0.0).r" in TEMPORAL_ACCUM_FRAG
    assert "rejection = max(rejection, 0.5 * alphaMask)" in TEMPORAL_ACCUM_FRAG
    assert "float blendFactor = max(rejection, uTemporalMinimumRejection)" in TEMPORAL_ACCUM_FRAG
    assert "(currentRgb - constrainedHistory) * blendFactor" in TEMPORAL_ACCUM_FRAG
    assert "max(uHistoryWarmup, uTemporalMinimumRejection)" not in TEMPORAL_ACCUM_FRAG
    assert "hairTemporalFilterWeights(uTemporalFilterOffsetPixels, weights)" in TEMPORAL_ACCUM_FRAG
    assert "exp(-2.29 * (dx * dx + dy * dy))" in TEMPORAL_ACCUM_FRAG
    assert "mix(normalizedGaussian, normalizedCatmull, 0.8)" in TEMPORAL_ACCUM_FRAG
    assert "hairTemporalHistoryCatmullRom(" in TEMPORAL_ACCUM_FRAG
    assert "vec2 base = floor(centered) + 0.5" in TEMPORAL_ACCUM_FRAG
    assert "dot(motionPixels, motionPixels) >= 0.015625" in TEMPORAL_ACCUM_FRAG
    assert "float broadening = clamp(rejection * 4.0 - 1.0" in TEMPORAL_ACCUM_FRAG
    assert "float diagonalConfidence = clamp(1.0 - rejection * 20.0" in TEMPORAL_ACCUM_FRAG
    assert "int[9](1, 3, 4, 5, 7, 0, 2, 6, 8)" in TEMPORAL_ACCUM_FRAG
    assert "hairTemporalUndoHdrCompression(" in TEMPORAL_ACCUM_FRAG
    assert "ditherPixel.y = dimensions.y - 1 - ditherPixel.y" in TEMPORAL_ACCUM_FRAG
    assert "ditherPixel.x + 2 * ditherPixel.y" in TEMPORAL_ACCUM_FRAG
    assert "outputRgb.rg *= 1.0 + noise * uTemporalDither.x" in TEMPORAL_ACCUM_FRAG
    assert "layout(location = 0) out vec2 FullDisocclusion" in TEMPORAL_DISOCCLUSION_FRAG
    assert "layout(location = 1) out vec2 DepthMotion" in TEMPORAL_DISOCCLUSION_FRAG
    assert "texelFetch(uOpaqueMotion, pixel, 0).xy" in TEMPORAL_DISOCCLUSION_FRAG
    assert "centerDepth <= 1.025 * diagonalDepth" in TEMPORAL_DISOCCLUSION_FRAG
    assert "(selectedDepth - uDepthBase) * uDepthSlope" in TEMPORAL_DISOCCLUSION_FRAG
    assert "translationOutside != 0.0 ? 24.0 : 120.0" in TEMPORAL_DISOCCLUSION_FRAG
    assert "cameraMotion * 0.125 - 0.5" in TEMPORAL_DISOCCLUSION_FRAG
    assert "FullDisocclusion = vec2(disocclusion, historyConfidence)" in TEMPORAL_DISOCCLUSION_FRAG
    assert "ndc.y = -ndc.y" in TEMPORAL_DISOCCLUSION_FRAG
    assert "centered.y = -centered.y" in TEMPORAL_DISOCCLUSION_FRAG


def test_native_raster_support_accepts_core_or_arb_clip_control():
    assert _supports_native_raster((4, 5), ())
    assert _supports_native_raster((4, 6), ())
    assert _supports_native_raster((3, 3), (b'GL_ARB_clip_control',))
    assert _supports_native_raster((3, 3), ('GL_ARB_clip_control',))
    assert not _supports_native_raster((4, 4), ())


def test_native_raster_define_is_injected_after_version_only_when_enabled():
    source = "\n#version 330 core\n#extension GL_ARB_gpu_shader5 : enable\nvoid main() {}\n"
    native = _shader_with_raster_mode(source, True)

    assert native.startswith("\n#version 330 core\n#define RCRA_NATIVE_UPPER_LEFT 1\n")
    assert native.count("#define RCRA_NATIVE_UPPER_LEFT") == 1
    assert _shader_with_raster_mode(source, False) == source


def test_native_raster_final_qt_boundary_restores_lower_left_origin():
    source = inspect.getsource(Viewport3D._composite_bloom)

    assert "glClipControl(GL_LOWER_LEFT, GL_ZERO_TO_ONE)" in source
    assert source.index("glClipControl(GL_LOWER_LEFT, GL_ZERO_TO_ONE)") \
        < source.index("glUseProgram(self._composite_prog)")
    assert source.rstrip().endswith("self._apply_raster_convention()")


def test_native_raster_culling_is_scoped_to_recovered_fur_draw():
    source = inspect.getsource(Viewport3D.paintGL)
    opaque_draw = source.index("gm.draw()")
    enable_cull = source.index("glEnable(GL_CULL_FACE)", opaque_draw)
    fur_draw = source.index("self._draw_fur_strands(", enable_cull)
    disable_cull = source.index("glDisable(GL_CULL_FACE)", fur_draw)

    assert opaque_draw < enable_cull < fur_draw < disable_cull
    assert "OpaqueDepth = opaqueDepth" in TEMPORAL_LINEAR_DEPTH_FRAG
    assert "ComposedDepth = hasFur ? furDepth : opaqueDepth" in TEMPORAL_LINEAR_DEPTH_FRAG
    assert "MaximumDepth = max(max(depth00, depth10), max(depth01, depth11))" in TEMPORAL_HALF_BASE_FRAG
    assert "MinimumDepth = min(min(depth00, depth10), min(depth01, depth11))" in TEMPORAL_HALF_BASE_FRAG
    assert "fullDepth < halfDepth * 0.9980000257492065" in TEMPORAL_ALPHA_MASK_FRAG
    assert "max(max(depths.x, depths.y), depths.z)" in TEMPORAL_ALPHA_HALF_FRAG
    assert "min(min(depths.x, depths.y), depths.z)" in TEMPORAL_ALPHA_HALF_FRAG
    assert "if (depths.w == maximumDepth)" in TEMPORAL_ALPHA_HALF_FRAG


def test_temporal_dither_table_and_sequence_match_the_executable_builder():
    raw = struct.pack("<256f", *TEMPORAL_DITHER_TABLE)
    assert hashlib.sha256(raw).hexdigest() == DITHER_TABLE_SHA256
    assert [temporal_dither_constants(age)[2] for age in range(5)] == [
        0.0, 2.0, 4.0, 1.0, 3.0,
    ]
    first = temporal_dither_constants(0)
    wrapped = temporal_dither_constants(256)
    assert first[0] == struct.unpack("<f", bytes.fromhex("610b363c"))[0]
    assert first[1] == np.float32(first[0] + first[0])
    assert first[3] == wrapped[3]
    assert temporal_dither_constants(7, enabled=False)[:2] == (0.0, 0.0)


def test_temporal_history_warmup_matches_the_cbuffer_builder_division():
    assert temporal_history_warmup(0) == 1.0
    assert temporal_history_warmup(1) == 0.5
    assert temporal_history_warmup(15) == 0.0625
    assert temporal_history_warmup(31) == 0.03125
    assert temporal_history_warmup(-20) == 1.0
    assert temporal_history_warmup(9, has_history=False) == 1.0


def test_temporal_minimum_rejection_uses_the_executable_fallback():
    assert struct.pack("<f", TEMPORAL_NONOPAQUE_RESPONSE_FALLBACK).hex() == "0ad7233d"
    assert TEMPORAL_NONOPAQUE_RESPONSE_FALLBACK == np.float32(0.04)
    assert TEMPORAL_MINIMUM_REJECTION_FLOOR == 0.0625
    assert TEMPORAL_CONDITIONAL_REJECTION_FLOOR == np.float32(0.1)
    assert temporal_minimum_rejection() == 0.0625
    assert temporal_minimum_rejection(conditional_floor=True) == np.float32(0.1)


def test_viewport_temporal_runtime_state_builds_exact_captured_misc():
    class State:
        _temporal_nonopaque_response = None
        _temporal_conditional_floor = False
        _temporal_hdr_reference = None
        _temporal_sample_count = 0
        reset_count = 0
        redraw_count = 0

        def _reset_temporal_history(self):
            self._temporal_sample_count = 0
            self.reset_count += 1

        def _redraw(self):
            self.redraw_count += 1

    state = State()
    captured_state = {
        "nonopaque_response": 0.04,
        "conditional_floor": False,
        "hdr_reference": 0.006569501478328294,
    }
    Viewport3D.set_temporal_aa_state(state, **captured_state)
    assert state.reset_count == 1
    assert state.redraw_count == 1
    assert Viewport3D.temporal_aa_misc(state, 3645) == (
        0.0625,
        0.0022656249348074198,
        76.1092758178711,
        0.00027427318855188787,
    )

    Viewport3D.set_temporal_aa_state(state, **captured_state)
    assert state.reset_count == 1
    assert state.redraw_count == 1

    Viewport3D.set_temporal_aa_state(
        state,
        nonopaque_response=0.08,
        conditional_floor=True,
        hdr_reference=2.0,
    )
    changed = Viewport3D.temporal_aa_misc(state, 0)
    assert state.reset_count == 2
    assert state.redraw_count == 2
    assert changed[0] == np.float32(0.1)
    assert changed[2:] == (np.float32(0.25), 1.0)


def test_temporal_histories_use_native_color_and_depth_storage():
    allocation_source = inspect.getsource(Viewport3D._resize_bloom_targets)
    allocation = allocation_source.split(
        'self._temporal_fbos', 1,
    )[1]
    assert 'GL_R11F_G11F_B10F' in allocation
    assert 'GL_UNSIGNED_INT_10F_11F_11F_REV' in allocation
    assert '_raw_tex_image_2d' in allocation
    assert 'ctypes.c_void_p(0)' in allocation
    assert 'self._temporal_depth_textures' in allocation
    assert 'GL_RG16F' in allocation
    assert 'self._temporal_disocclusion_textures' in allocation
    assert 'GL_RG8' in allocation
    assert 'GL_COLOR_ATTACHMENT1' in allocation
    assert 'self._temporal_linear_depth_textures' in allocation
    assert 'self._temporal_half_textures' in allocation
    assert 'self._temporal_alpha_mask_texture' in allocation
    assert 'GL_R16F' in allocation
    assert 'self._scene_velocity_texture' in allocation_source
    assert 'GL_R8UI' in allocation_source
    assert 'self._scene_stencil_texture' in allocation_source
    assert 'GL_COLOR_ATTACHMENT5' in allocation_source


def test_recovered_fur_volume_matches_procedural_shape_and_profile():
    volume = _build_fur_layer_volume(size=128, slices=32)
    repeated = _build_fur_layer_volume(size=128, slices=32)

    assert volume.shape == (32, 128, 128)
    assert volume.dtype == np.uint8
    assert np.array_equal(volume, repeated)
    assert 217.0 <= float(volume[0].mean()) <= 219.0
    assert np.all(np.diff(volume.mean(axis=(1, 2))) <= 1e-6)
    assert np.count_nonzero(volume[-1]) == 271
    assert 0.85 < np.corrcoef(
        volume[0].ravel(), volume[1].ravel(),
    )[0, 1] < 0.88


def test_fur_mips_match_captured_gpu_texture_hashes():
    # Ratchet draw 24715, t7, Rift Apart 3.630.1.0: all 32 slices per mip.
    # These independent capture hashes catch float32 reciprocal/profile errors.
    captured = (
        'fe7ceb598779b2796595be8e373fedd3af8ab1385013c2a06748974374c73780',
        '77807d40bff0d87521b8b33823b7a7e46c31fe7e826e51d2b4a67df152fa208c',
        '72a0bf5d62f903c9ee7161a5a2f037587d483a484049da666780092a2ebe8f9a',
        '3d9cf0bb6279ce79c90a76ea7d0b11c17974e290a382a8c808ce1444d916e1b8',
    )
    assert tuple(hashlib.sha256(mip.tobytes()).hexdigest()
                 for mip in _build_fur_layer_mips()) == captured


def test_recovered_fur_mips_use_exact_integer_2x2_averages():
    volume = np.array([[[0, 1, 2, 3],
                        [4, 5, 6, 7],
                        [8, 9, 10, 11],
                        [12, 13, 14, 15]]], dtype=np.uint8)

    mips = _build_fur_layer_mips(volume, levels=3)

    assert [level.shape for level in mips] == [
        (1, 4, 4), (1, 2, 2), (1, 1, 1),
    ]
    np.testing.assert_array_equal(mips[1], [[[2, 4], [10, 12]]])
    np.testing.assert_array_equal(mips[2], [[[7]]])


def test_recovered_retail_fur_mip_chain_has_stored_dimensions():
    mips = _build_fur_layer_mips()

    assert [level.shape for level in mips] == [
        (32, 128, 128), (32, 64, 64), (32, 32, 32), (32, 16, 16),
    ]


def test_geometric_fur_requires_surface_and_control_textures():
    assert _can_draw_fur_strands(
        show_fur=True,
        wireframe=False,
        is_composite_shell=False,
        albedo_tex_id=7,
        control_tex_id=9,
    )
    assert not _can_draw_fur_strands(
        show_fur=True,
        wireframe=False,
        is_composite_shell=True,
        albedo_tex_id=7,
        control_tex_id=9,
    )
    assert not _can_draw_fur_strands(
        show_fur=True,
        wireframe=True,
        is_composite_shell=False,
        albedo_tex_id=7,
        control_tex_id=9,
    )
    assert not _can_draw_fur_strands(
        show_fur=False,
        wireframe=False,
        is_composite_shell=False,
        albedo_tex_id=7,
        control_tex_id=9,
    )

def test_progressive_texture_batches_merge_without_losing_roles():
    base = _slot(2048, 2048, "hero_ratchet_boots_c")
    normal = _slot(2048, 2048, "hero_ratchet_boots_n")

    merged = _merge_material_textures({}, {3: {"base_color": base}})
    merged = _merge_material_textures(merged, {3: {"normal": normal}})

    assert merged == {3: {"base_color": base, "normal": normal}}


def test_software_preview_accepts_texture_payload_metadata():
    app = QApplication.instance() or QApplication([])
    preview = SoftwareModelPreview()
    payload = (
        bytes([80, 100, 120, 255]) * 16,
        4,
        4,
        "obsidian_c",
        {"dxgi_format": 0x48},
    )

    preview.load_textures({0: {"base_color": payload}})

    assert 0 in preview._material_colors
    preview.deleteLater()
    app.processEvents()


def test_only_color_textures_use_srgb_gpu_decoding():
    assert _is_srgb_texture_role("base")
    assert not _is_srgb_texture_role("normal")
    assert not _is_srgb_texture_role("effect_mask")
    assert not _is_srgb_texture_role("noise")
    assert not _is_srgb_texture_role("emissive")


def test_temporal_current_sample_offset_undoes_projection_jitter():
    assert np.allclose(
        _temporal_current_sample_offset((0.25, -0.5), (1000, 500)),
        (-0.00025, 0.001),
    )


def test_temporal_history_jitter_offset_removes_both_raster_offsets():
    size = (1000, 500)
    current = (0.25, -0.5)
    previous = (-0.25, 0.25)

    current_offset = np.asarray(_temporal_current_sample_offset(current, size))
    previous_offset = np.asarray(_temporal_current_sample_offset(previous, size))
    history_offset = np.asarray(
        _temporal_history_jitter_offset(current, previous, size)
    )

    np.testing.assert_allclose(
        history_offset, current_offset - previous_offset,
    )
    np.testing.assert_allclose(
        _temporal_history_jitter_offset(current, current, size), (0.0, 0.0),
    )


def test_temporal_filter_offset_uses_the_shader_texture_coordinate_frame():
    jitter = (0.25, -0.5)
    assert _temporal_filter_offset_pixels(jitter) == (0.25, -0.5)
    assert _temporal_filter_offset_pixels(jitter, upper_left=True) == (0.25, 0.5)


def test_native_motion_reprojects_to_stable_previous_gl_pixel():
    size = np.asarray((1000.0, 500.0), dtype=np.float64)
    current_jitter = np.asarray((0.25, -0.5), dtype=np.float64)
    previous_jitter = np.asarray((-0.25, 0.25), dtype=np.float64)
    current_stable = np.asarray((640.25, 320.75), dtype=np.float64)
    previous_stable = np.asarray((638.5, 321.25), dtype=np.float64)

    # The projection moves GL raster positions by negative jitter. Native Y is
    # top-left, so its current-minus-previous motion has the opposite GL Y sign.
    current_raster = current_stable - current_jitter
    previous_raster = previous_stable - previous_jitter
    native_motion = np.asarray((
        current_raster[0] - previous_raster[0],
        -(current_raster[1] - previous_raster[1]),
    ))
    jitter_offset = np.asarray(_temporal_history_jitter_offset(
        tuple(current_jitter), tuple(previous_jitter), tuple(size.astype(int)),
    ))
    history_uv = current_stable / size + jitter_offset + np.asarray((
        -native_motion[0] / size[0], native_motion[1] / size[1],
    ))

    np.testing.assert_allclose(history_uv, previous_stable / size)


def test_upper_left_motion_reprojects_to_stable_previous_pixel():
    size = np.asarray((1000.0, 500.0), dtype=np.float64)
    current_jitter = np.asarray((0.25, -0.5), dtype=np.float64)
    previous_jitter = np.asarray((-0.25, 0.25), dtype=np.float64)
    current_stable = np.asarray((640.25, 320.75), dtype=np.float64)
    previous_stable = np.asarray((638.5, 321.25), dtype=np.float64)

    # With upper-left clip control, the existing projection coefficients move
    # top-left raster X by -jitter.x and Y by +jitter.y.
    current_raster = current_stable + np.asarray((-current_jitter[0], current_jitter[1]))
    previous_raster = previous_stable + np.asarray((-previous_jitter[0], previous_jitter[1]))
    native_motion = current_raster - previous_raster
    jitter_offset = np.asarray(_temporal_history_jitter_offset(
        tuple(current_jitter), tuple(previous_jitter), tuple(size.astype(int)),
        upper_left=True,
    ))
    history_uv = current_stable / size + jitter_offset - native_motion / size

    np.testing.assert_allclose(history_uv, previous_stable / size)


def test_blizar_lava_material_uses_animated_effect_path():
    assert _is_lava_material("sal_gnd_lava_flow_001")
    assert _is_lava_material("material/environment/blizar/magma_surface")
    assert not _is_lava_material("blz_gnd_rubber_mat_01")
    assert not _is_lava_material("material/environment/vendor/ground/blz_gnd_lava_rock_01")
    assert not _is_lava_material("material/environment/prop/prop_std_lava_rock_02")
    assert not _uses_molten_shader(
        "material/environment/blizar_prime/ground/blz_gbl_lava_01_flow.material",
        "environment/blizar_prime/rock/blz_lava_rock/blz_lava_rock_01.model",
    )
    assert _uses_molten_shader(
        "material/environment/blizar_prime/ground/blz_gbl_lava_01_flow.material",
        "environment/blizar_prime/ground/blz_ground_lava_plane_flow.model",
    )
    assert _is_lava_rock_model(
        "environment/blizar_prime/rock/blz_lava_rock/blz_lava_rock_01.model",
    )
    assert not _is_lava_rock_model(
        "environment/blizar_prime/ground/blz_ground_lava_plane_flow.model",
    )
    assert _is_retail_blizar_lava_material("blz_gbl_lava_01_flow")
    assert _is_retail_blizar_lava_material(
        "material/environment/blizar_prime/ground/blz_gbl_lava_01_flow.material"
    )


def test_lavafall_texture_motion_goes_down_its_increasing_v_axis():
    lavafall_path = "environment/blizar_prime/lava/blz_lava_lavafall_01.model"
    flow_a, flow_b = _lava_flow_sample_offsets(lavafall_path)

    # Texture features move opposite the sampling direction. Both layers must
    # therefore sample toward -V so their visible features travel toward +V,
    # which the shipped lavafall mesh maps from top to bottom.
    assert flow_a[1] < 0.0
    assert flow_b[1] < 0.0
    assert flow_a[0] == 0.0
    assert flow_b[0] == 0.0
    assert -flow_a[1] > abs(flow_a[0])
    assert _is_lavafall_model(lavafall_path)
    assert not _is_lavafall_model(
        "environment/blizar_prime/ground/blz_ground_lava_plane_flow.model",
    )

    ground_a, ground_b = _lava_flow_sample_offsets(
        "environment/blizar_prime/ground/blz_ground_lava_plane_flow.model",
    )
    assert ground_a == (0.024, 0.011)
    assert ground_b == (-0.017, 0.029)


def test_world_mapped_mesh_with_zero_uvs_gets_box_projection():
    positions = np.array([
        [-2.0, 0.0, -2.0],
        [2.0, 0.0, -2.0],
        [2.0, 0.0, 2.0],
        [-2.0, 0.0, 2.0],
    ], dtype=np.float32)
    normals = np.tile(np.array([[0.0, 1.0, 0.0]], dtype=np.float32), (4, 1))
    authored = np.zeros((4, 2), dtype=np.float32)

    resolved, generated = _resolved_mesh_uvs(positions, normals, authored)

    assert generated
    assert np.allclose(np.ptp(resolved, axis=0), [2.2, 2.2])
    assert not np.allclose(resolved, 0.0)


def test_authored_uvs_are_preserved():
    positions = np.zeros((3, 3), dtype=np.float32)
    normals = np.tile(np.array([[0.0, 1.0, 0.0]], dtype=np.float32), (3, 1))
    authored = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    resolved, generated = _resolved_mesh_uvs(positions, normals, authored)

    assert not generated
    assert resolved is authored


def test_foliage_card_materials_use_alpha_cutout_rendering():
    assert _is_alpha_cutout_material("amb_sargassso_platformdino_grass_1")
    assert _is_alpha_cutout_material("sar_plant_tree_large_leaves_01")
    assert _is_alpha_cutout_material("amb_sargasso_platformdino_vines")
    assert not _is_alpha_cutout_material("amb_sargasso_platformdino_body")


def test_authored_wool_is_distinct_from_groomed_hero_fur():
    assert _is_authored_wool(density=3.0, offset_scale=0.0)
    assert not _is_authored_wool(density=16.0, offset_scale=1.0)
    assert not _is_authored_wool(density=8.985, offset_scale=2.769)


def test_adaptive_clip_planes_contain_a_giant_framed_model():
    camera = ArcballCamera()
    minimum = np.array([-2400.0, -800.0, -3100.0], dtype=np.float32)
    maximum = np.array([2600.0, 1400.0, 2900.0], dtype=np.float32)
    camera.frame_aabb(minimum, maximum)

    near, far = _perspective_clip_planes(camera, minimum, maximum)
    eye = camera.eye_position()
    forward = camera.view_direction()
    corners = np.array([
        [x, y, z]
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    ], dtype=np.float32)
    depths = (corners - eye) @ forward

    assert 0.0 < near < float(depths.min())
    assert far > float(depths.max())
    assert far > 1000.0


def test_autodesk_style_pan_stays_in_the_camera_view_plane():
    camera = ArcballCamera()
    camera.yaw = 35.0
    camera.pitch = 48.0
    forward = camera.view_direction().copy()
    before = camera.target.copy()

    camera.pan(35.0, -22.0)

    movement = camera.target - before
    assert np.linalg.norm(movement) > 0.0
    assert abs(float(np.dot(movement, forward))) < 1e-6


def test_scaled_display_uses_the_full_physical_opengl_framebuffer():
    assert _scaled_framebuffer_size(800, 600, 1.25) == (1000, 750)
    assert _scaled_framebuffer_size(801, 601, 1.25) == (1001, 751)


def test_native_reverse_z_perspective_maps_near_to_one_and_far_to_zero():
    near, far = 0.1, 1000.0
    projection = _perspective_reverse_z_zero_to_one(60.0, 16.0 / 9.0, near, far)

    near_clip = projection @ np.array([0.0, 0.0, -near, 1.0], dtype=np.float32)
    far_clip = projection @ np.array([0.0, 0.0, -far, 1.0], dtype=np.float32)

    assert np.isclose(near_clip[2] / near_clip[3], 1.0, atol=1e-7)
    assert np.isclose(far_clip[2] / far_clip[3], 0.0, atol=1e-7)
    assert projection[2, 2] == np.float32(near / (far - near))
    assert projection[2, 3] == np.float32(near * far / (far - near))
    assert projection[3, 2] == -1.0


def test_native_reverse_z_orthographic_maps_requested_bounds_to_one_and_zero():
    near, far = -500.0, 500.0
    projection = _ortho_reverse_z_zero_to_one(-8.0, 8.0, -4.0, 4.0, near, far)

    near_clip = projection @ np.array([0.0, 0.0, -near, 1.0], dtype=np.float32)
    far_clip = projection @ np.array([0.0, 0.0, -far, 1.0], dtype=np.float32)

    assert np.isclose(near_clip[2], 1.0, atol=1e-7)
    assert np.isclose(far_clip[2], 0.0, atol=1e-7)
    assert projection[2, 2] == np.float32(1.0 / (far - near))


def test_direct_mouse_bindings_match_maya_motion_tools_without_requiring_alt():
    alt = Qt.KeyboardModifier.AltModifier
    direct = Qt.KeyboardModifier.NoModifier

    assert autodesk_mouse_mode(Qt.MouseButton.LeftButton, direct) == "tumble"
    assert autodesk_mouse_mode(Qt.MouseButton.MiddleButton, direct) == "track"
    assert autodesk_mouse_mode(Qt.MouseButton.RightButton, direct) == "dolly"
    assert autodesk_mouse_mode(Qt.MouseButton.LeftButton, alt) == "tumble"


def _mouse_event(event_type, x, modifiers, *, pressed):
    return QMouseEvent(
        event_type,
        QPointF(x, 10.0),
        Qt.MouseButton.LeftButton if event_type != QEvent.Type.MouseMove
        else Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton if pressed else Qt.MouseButton.NoButton,
        modifiers,
    )


def test_both_previews_tumble_directly_in_the_mouse_drag_direction():
    app = QApplication.instance() or QApplication([])
    previews = (SoftwareModelPreview(), Viewport3D())

    for preview in previews:
        yaw = lambda: preview._yaw if isinstance(preview, SoftwareModelPreview) \
            else preview.camera.yaw
        initial_yaw = yaw()

        preview.mousePressEvent(_mouse_event(
            QEvent.Type.MouseButtonPress, 10.0,
            Qt.KeyboardModifier.NoModifier, pressed=True,
        ))
        preview.mouseMoveEvent(_mouse_event(
            QEvent.Type.MouseMove, 40.0,
            Qt.KeyboardModifier.NoModifier, pressed=True,
        ))
        preview.mouseReleaseEvent(_mouse_event(
            QEvent.Type.MouseButtonRelease, 40.0,
            Qt.KeyboardModifier.NoModifier, pressed=False,
        ))
        assert yaw() > initial_yaw

    assert app is not None


def test_maya_motion_directions_track_and_dolly_intuitively():
    camera = ArcballCamera()
    before_target = camera.target.copy()
    right, up, _ = camera.view_basis()

    camera.pan(25.0, 18.0)
    movement = camera.target - before_target
    assert float(np.dot(movement, right)) < 0.0
    assert float(np.dot(movement, up)) > 0.0

    before_distance = camera.dist
    camera.dolly(30.0)
    assert camera.dist < before_distance
