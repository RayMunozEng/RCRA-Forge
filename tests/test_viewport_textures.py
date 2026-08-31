import numpy as np
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from ui.camera_controls import autodesk_mouse_mode
from ui.model_preview import SoftwareModelPreview
from ui.viewport import (
    ArcballCamera,
    BASE_COLOR_ROLES,
    NORMAL_ROLES,
    _best_texture_slot,
    _is_alpha_cutout_material,
    _is_lava_material,
    _is_retail_blizar_lava_material,
    _is_lava_rock_model,
    _is_lavafall_model,
    _is_srgb_texture_role,
    _lava_flow_sample_offsets,
    _merge_material_textures,
    _postprocess_settings,
    _perspective_clip_planes,
    _resolved_mesh_uvs,
    _scaled_framebuffer_size,
    _uses_molten_shader,
    Viewport3D,
)
from core.texture import TextureAsset


def _slot(width: int, height: int, name: str):
    return (b"rgba", width, height, name)


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
