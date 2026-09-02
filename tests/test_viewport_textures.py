import hashlib

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
    _best_texture_slot,
    _can_draw_fur_strands,
    _fur_density_from_texture_slot,
    FUR_SHELL_FRAG_SRC,
    FUR_SHELL_GEOM_SRC,
    FUR_SHELL_VERT_SRC,
    FUR_DENOISE_FRAG,
    TEMPORAL_ACCUM_FRAG,
    _fur_header_from_texture_slot,
    _fur_offset_scale_from_texture_slot,
    _fur_shading_from_texture_slot,
    _fur_wind_turbulence_from_texture_slot,
    _build_fur_layer_volume,
    _build_fur_layer_mips,
    _fur_adjusted_shell_depth,
    _fur_round_nearest_even,
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
    _lava_flow_sample_offsets,
    _merge_material_textures,
    _mesh_tangents,
    _postprocess_settings,
    _perspective_clip_planes,
    _resolved_mesh_uvs,
    _scaled_framebuffer_size,
    _uses_molten_shader,
    Viewport3D,
)
from core.texture import TextureAsset
from core.fur_resources import default_hair_brdf_rg_half


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
    assert "fract(noiseTime * 0.0163934) * 61.0" in FUR_SHELL_VERT_SRC
    assert "uFurWindRadius * 0.1" in FUR_SHELL_VERT_SRC
    assert "inverse(mat3(uModel)) * windDirection" in FUR_SHELL_VERT_SRC
    assert "cross(localTangent, localNormal)" in FUR_SHELL_VERT_SRC
    assert "vsShellVisible[0] == 0" in FUR_SHELL_GEOM_SRC
    assert "vsShellVisible[1] == 0" in FUR_SHELL_GEOM_SRC
    assert "vsShellVisible[2] == 0" in FUR_SHELL_GEOM_SRC
    assert "gl_FrontFacing ? 1.0 : -1.0" in FUR_SHELL_FRAG_SRC
    assert "shifted / max(uViewportSize, vec2(1.0))" in FUR_SHELL_FRAG_SRC
    assert "vec2 cell = roundNearestEven(shifted)" in FUR_SHELL_FRAG_SRC
    assert "wetBase + phase * 0.1" in FUR_SHELL_FRAG_SRC
    assert "layerUV /= layerUvDivisor(gl_FragCoord.xy, wetness)" in FUR_SHELL_FRAG_SRC
    assert "0.95 * control.b + 0.05" in FUR_SHELL_FRAG_SRC
    assert "wetness + 0.005" in FUR_SHELL_FRAG_SRC
    assert "FurGBuffer = vec4(strandTangent" in FUR_SHELL_FRAG_SRC
    assert "void recoveredHairBasis(" in FUR_SHELL_FRAG_SRC
    assert "frameSeed = viewDirection * strandNormalSine" in FUR_SHELL_FRAG_SRC
    assert "0.9725 - 0.7514 * primaryGloss" in FUR_SHELL_FRAG_SRC
    assert "0.9725 - 0.07514 * secondaryGloss" in FUR_SHELL_FRAG_SRC
    assert "strandTangent + 0.075 * (-normal - strandTangent)" in FUR_SHELL_FRAG_SRC
    assert "sqrt(furResponse) * uFurGlossScale" in FUR_SHELL_FRAG_SRC
    assert "furResponse * uFurSpecularScale" in FUR_SHELL_FRAG_SRC
    assert "primaryFresnel * primaryDistribution" in FUR_SHELL_FRAG_SRC
    assert "8.0 - transmissionPhase * 10.5" in FUR_SHELL_FRAG_SRC
    assert "transmissionPhase * transmissionPhase * 3.17114" in FUR_SHELL_FRAG_SRC
    assert "(normalLight + transmittance)" in FUR_SHELL_FRAG_SRC
    assert "0.5 + 0.5 * grazing * grazing" in FUR_SHELL_FRAG_SRC
    assert "vec3 sampleD3DCube" in FUR_SHELL_FRAG_SRC
    assert "5.0 - clamp(averageRoughness" in FUR_SHELL_FRAG_SRC
    assert "environmentBrdf.x * primaryF0 + environmentBrdf.y" in FUR_SHELL_FRAG_SRC
    assert "0.35 + key * 0.80 + fill * 0.30" not in FUR_SHELL_FRAG_SRC
    assert "uFurTransmittanceScale * 0.20" not in FUR_SHELL_FRAG_SRC
    assert "FurNormalMask = vec4(normal, 1.0)" in FUR_SHELL_FRAG_SRC
    assert "for (int step = 0; step < 3; ++step)" in FUR_DENOISE_FRAG
    assert "200.0 / centerDepth" in FUR_DENOISE_FRAG
    assert "sqrt(max(1.0 - tangentAgreement, 0.0)) * 0.05" in FUR_DENOISE_FRAG
    assert "rayLength = min(" in FUR_DENOISE_FRAG
    assert "0.0025" in FUR_DENOISE_FRAG
    assert "depthScale * 0.015" in TEMPORAL_ACCUM_FRAG
    assert "1000.0 / depthScale" in TEMPORAL_ACCUM_FRAG
    assert "100.0 / depthScale" in TEMPORAL_ACCUM_FRAG
    assert "1.0 / rayDepth - sampleReciprocalDepth" in TEMPORAL_ACCUM_FRAG
    assert "0.75 * grazing * occlusion" in TEMPORAL_ACCUM_FRAG


def test_recovered_fur_rounding_matches_dxbc_round_nearest_even():
    assert _fur_round_nearest_even(0.49) == 0.0
    assert _fur_round_nearest_even(0.5) == 0.0
    assert _fur_round_nearest_even(1.5) == 2.0
    assert _fur_round_nearest_even(2.5) == 2.0
    assert _fur_round_nearest_even(-0.5) == 0.0
    assert _fur_round_nearest_even(-1.5) == -2.0
    assert _fur_round_nearest_even(-2.5) == -2.0


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
