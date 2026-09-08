"""Reject stale-sized or out-of-range scene resources before GPU upload."""
import struct
import numpy as np
import pytest

from core.hair_scene import build_hair_scene_local_lookup, validate_hair_scene
from core.local_lights import (
    LIGHT_GPU_DTYPE, LIGHT_VOLUME_GPU_DTYPE, LightShellPlacement,
)


def scene_bundle():
    view, world = bytearray(480), bytearray(896)
    struct.pack_into('<2f', view, 400, 64, 32)
    struct.pack_into('<3f', world, 192, 2, 3, 4)
    struct.pack_into('<3f', world, 208, 0, 1, 0)
    struct.pack_into('<I', world, 748, 2)
    value = dict(viewport_cbuffer=np.frombuffer(view, np.uint8),
                 world_cbuffer=np.frombuffer(world, np.uint8),
                 probe_lookup=np.zeros((2, 4, 8), np.uint32),
                 probe_records=np.zeros((34, 128), np.uint8),
                 grid_lookup=np.zeros(64**3, np.uint32),
                 grid_data=np.zeros((4096, 4), np.uint32))
    value['probe_lookup'][1, 3, 7] = 2
    for prefix, leading in (('default', (6,)), ('local', (1, 6))):
        for mip in range(6):
            size = 32 >> mip
            value[f'{prefix}_mip{mip}'] = np.zeros((*leading, size, size, 3), np.float32)
    return value


def local_scene_bundle(record_count=2):
    scene = scene_bundle()
    struct.pack_into('<I', scene['world_cbuffer'], 44, 1)
    scene['light_lookup'] = np.zeros((1, 4, 8), np.uint32)
    scene['light_lookup'][0, 0, 0] = 1 << (record_count - 1)
    records = np.zeros(record_count, LIGHT_GPU_DTYPE)
    records['world_axis_z'][:, 2] = 1
    records['inverse_attenuation_radius'] = 1
    records['linear_color'] = 1
    records['mod_id_and_gobo_id'] = 0xffff0000
    scene['light_records'] = records.view(np.uint8).reshape(-1, 128)
    return scene


def test_full_view_masks_preserve_late_tile_and_second_word():
    scene = scene_bundle()
    arrays, params = validate_hair_scene(scene)
    assert np.array_equal(arrays['probe_lookup'], scene['probe_lookup'])
    assert params['viewport_size'] == (64, 32)
    assert params['key_color'] == (2, 3, 4)
    assert params['key_direction'] == (0, 1, 0)
    assert params['record_count'] == 34
    assert params['record_capacity'] == 34


def test_scene_derives_effective_probe_prefix_from_all_view_tiles():
    scene = scene_bundle()
    scene['probe_lookup'].fill(0)
    scene['probe_lookup'][0, 0, 0] = 1 << 10
    _, params = validate_hair_scene(scene)
    assert params['record_count'] == 11
    assert params['record_capacity'] == 34
    scene['probe_lookup'].fill(0)
    _, params = validate_hair_scene(scene)
    assert params['record_count'] == 0


def test_scene_accepts_optional_local_light_lookup_and_derives_prefix():
    scene = local_scene_bundle()
    arrays, params = validate_hair_scene(scene)
    assert params['has_local_resources'] and params['has_local_lights']
    assert params['local_light_word_count'] == 1
    assert params['local_light_record_count'] == 2
    assert params['local_light_record_capacity'] == 2
    np.testing.assert_array_equal(arrays['light_lookup'], scene['light_lookup'])
    np.testing.assert_array_equal(arrays['light_records'], scene['light_records'])


def test_scene_builder_generates_current_local_lookup_from_manager_placements():
    from core.probe_lookup import LIGHT_SHELL_BOX_VERTICES

    scene = local_scene_bundle(1)
    scene.pop('light_lookup')
    records = scene['light_records'].view(LIGHT_GPU_DTYPE).reshape(-1)
    records[0]['z_bin_min_max'] = np.uint32((4 << 16) | 2)
    identity = np.eye(4, dtype=np.float32)
    object_to_world = identity.copy()
    object_to_world[3, 2] = .5
    placement = LightShellPlacement(
        np.asarray(LIGHT_SHELL_BOX_VERTICES, np.float32) * np.float32(.25),
        object_to_world,
        np.asarray([-.25, -.25, -.25], np.float32),
        np.asarray([.25, .25, .25], np.float32),
    )
    generated = build_hair_scene_local_lookup(
        scene, [placement], np.ones((32, 64), np.float32),
        view_to_world=identity, cam_world_to_clip=identity,
        screen_to_view_x=1, near_clip=.1, z_bin_count=8,
    )
    assert struct.unpack_from('<I', generated['world_cbuffer'], 44)[0] == 1
    assert generated['light_lookup'].shape == (1, 4, 8)
    assert np.count_nonzero(generated['light_lookup']) > 0
    np.testing.assert_array_equal(
        generated['light_z_bin_lookup'], [[0, 0, 1, 1, 1, 0, 0, 0]],
    )
    arrays, params = validate_hair_scene(generated)
    assert params['has_local_lights'] and params['local_light_record_count'] == 1
    np.testing.assert_array_equal(arrays['light_lookup'], generated['light_lookup'])


def test_scene_without_local_resources_keeps_local_stage_disabled():
    _, params = validate_hair_scene(scene_bundle())
    assert not params['has_local_resources']
    assert not params['has_local_lights']
    assert params['local_light_word_count'] == 0
    assert not params['has_cloud_shadow']


def test_scene_accepts_optional_cloud_shadow_storage():
    scene = scene_bundle()
    struct.pack_into('<4f', scene['world_cbuffer'], 656, 1, .25, .1, 0)
    scene['cloud_shadow'] = np.full((4, 8, 4), 255, np.uint8)
    arrays, params = validate_hair_scene(scene)
    assert params['has_cloud_shadow'] and params['cloud_shadow_enabled']
    assert params['cloud_shadow_storage'] == 'rgba8'
    np.testing.assert_array_equal(arrays['cloud_shadow'], scene['cloud_shadow'])


def test_scene_requires_enabled_cloud_shadow_resource():
    scene = scene_bundle()
    struct.pack_into('<4f', scene['world_cbuffer'], 656, 1, .25, .1, 0)
    with pytest.raises(ValueError, match='require cloud_shadow'):
        validate_hair_scene(scene)


def test_scene_requires_enabled_key_gobo_atlas():
    scene = scene_bundle()
    struct.pack_into('<4f', scene['world_cbuffer'], 640, 0, 0, .25, 1)
    with pytest.raises(ValueError, match='shared gobo_atlas'):
        validate_hair_scene(scene)


def test_scene_rejects_bad_key_gobo_constants_and_atlas_shape():
    scene = scene_bundle()
    struct.pack_into('<4f', scene['world_cbuffer'], 640, 0, 0, -1, 0)
    with pytest.raises(ValueError, match='Key-gobo constants'):
        validate_hair_scene(scene)
    scene = scene_bundle()
    scene['gobo_atlas'] = np.zeros((4, 4), np.uint32)
    with pytest.raises(ValueError, match='2048x4096'):
        validate_hair_scene(scene)


def test_scene_requires_key_shadow_volume_resources_and_checks_range():
    scene = scene_bundle()
    struct.pack_into('<I', scene['world_cbuffer'], 892, 64)
    struct.pack_into('<f', scene['world_cbuffer'], 22 * 16 + 12, 1 / 64)
    with pytest.raises(ValueError, match='require light_volumes'):
        validate_hair_scene(scene)
    scene['light_volumes'] = np.zeros(
        1, LIGHT_VOLUME_GPU_DTYPE).view(np.uint8).reshape(-1, 128)
    with pytest.raises(ValueError, match='shared gobo_atlas'):
        validate_hair_scene(scene)

    scene = scene_bundle()
    struct.pack_into('<I', scene['world_cbuffer'], 892, 64)
    struct.pack_into('<f', scene['world_cbuffer'], 22 * 16 + 12, 2 + 1 / 64)
    scene['light_volumes'] = np.zeros(
        1, LIGHT_VOLUME_GPU_DTYPE).view(np.uint8).reshape(-1, 128)
    with pytest.raises(ValueError, match='range exceeds'):
        validate_hair_scene(scene)


@pytest.mark.parametrize('image,message', [
    (np.zeros((4, 8, 3), np.uint8), 'RGBA8'),
    (np.full((4, 8, 3), np.inf, np.float32), 'finite'),
    (np.full((4, 8), 31 << 6, np.uint32), 'finite R11'),
])
def test_scene_rejects_invalid_cloud_shadow_storage(image, message):
    scene = scene_bundle()
    scene['cloud_shadow'] = image
    with pytest.raises(ValueError, match=message):
        validate_hair_scene(scene)


@pytest.mark.parametrize('change,message', [
    (lambda b: b.pop('light_records'), 'both light_lookup and light_records'),
    (lambda b: b.update(light_lookup=b['light_lookup'].astype(np.float32)),
     'uint32'),
    (lambda b: b.update(light_records=b['light_records'][:, :-1]),
     r'\(count, 128\)'),
    (lambda b: b.update(light_record_count=np.array(1, np.uint32)),
     'missing light record'),
])
def test_scene_rejects_incomplete_local_light_resources(change, message):
    scene = local_scene_bundle()
    change(scene)
    with pytest.raises(ValueError, match=message):
        validate_hair_scene(scene)


def test_scene_rejects_unbound_local_modifiers():
    scene = local_scene_bundle(1)
    records = scene['light_records'].view(LIGHT_GPU_DTYPE).reshape(-1)
    records['shadow_map_info'][0] = 1 << 16
    with pytest.raises(ValueError, match='light_volumes'):
        validate_hair_scene(scene)

    scene = local_scene_bundle(1)
    records = scene['light_records'].view(LIGHT_GPU_DTYPE).reshape(-1)
    records['mod_id_and_gobo_id'][0] = 0
    with pytest.raises(ValueError, match='light_volumes'):
        validate_hair_scene(scene)

    scene['light_volumes'] = np.zeros(
        1, LIGHT_VOLUME_GPU_DTYPE).view(np.uint8).reshape(-1, 128)
    with pytest.raises(ValueError, match='gobo_atlas'):
        validate_hair_scene(scene)


@pytest.mark.parametrize('change,message', [
    (lambda b: b.update(probe_lookup=b['probe_lookup'][:, :-1]), 'cover'),
    (lambda b: b.update(probe_lookup=b['probe_lookup'][:1]), 'word count'),
    (lambda b: b.update(probe_lookup=b['probe_lookup'].astype(np.float32)), 'uint32'),
    (lambda b: b.update(probe_records=b['probe_records'][:33]), 'missing record'),
    (lambda b: b['world_cbuffer'].__setitem__(slice(208, 220), 0), 'nonzero direction'),
    (lambda b: b['viewport_cbuffer'].__setitem__(slice(400, 408), 0), 'dimensions'),
    (lambda b: b.update(key_shadow_depth=np.zeros((16, 16), np.uint16)), '8192x8192'),
])
def test_scene_contract_rejects_incompatible_bindings(change, message):
    scene = scene_bundle()
    change(scene)
    with pytest.raises(ValueError, match=message):
        validate_hair_scene(scene)


def test_view_changes_invalidate_a_supplied_lookup():
    from types import SimpleNamespace
    from ui.viewport import ArcballCamera, Viewport3D
    view = SimpleNamespace(camera=ArcballCamera(), _gpu_meshes=[], _ortho=False,
                           _fur_scene_gpu=object(), size=(64, 32))
    view._framebuffer_size = lambda: view.size
    view._fur_scene_view_key = lambda: Viewport3D._fur_scene_view_key(view)
    view._fur_scene_view = view._fur_scene_view_key()
    assert Viewport3D._fur_scene_is_current(view)
    view.camera.yaw += 1
    assert not Viewport3D._fur_scene_is_current(view)
    view._fur_scene_view = view._fur_scene_view_key()
    view.size = (128, 64)
    assert not Viewport3D._fur_scene_is_current(view)


def test_failed_upload_does_not_relabel_old_gpu_lookup(monkeypatch):
    from types import SimpleNamespace
    from ui.viewport import Viewport3D
    old = object()
    view = SimpleNamespace(_pending_fur_scene=(({}, {}), 'new-view'),
                           _fur_scene_view='old-view', _fur_scene_gpu=old,
                           _fur_scene_program=1)
    def fail(*args):
        raise RuntimeError('GPU allocation failed')
    monkeypatch.setattr('core.hair_scene.HairSceneGpu', fail)
    with pytest.raises(RuntimeError, match='allocation'):
        Viewport3D._upload_fur_scene(view)
    assert view._fur_scene_gpu is old
    assert view._fur_scene_view == 'old-view'


def test_scene_history_mask_and_native_timing():
    scene = scene_bundle()
    struct.pack_into('<f', scene['viewport_cbuffer'], 21 * 16 + 8, 0.25)
    struct.pack_into('<f', scene['viewport_cbuffer'], 25 * 16 + 12, 19)
    scene['reflection_history'] = np.zeros((16, 32), np.uint32)
    scene['reflection_velocity'] = np.zeros((16, 32, 2), np.float16)
    scene['denoise_mask'] = np.arange(64 * 32, dtype=np.uint8).reshape(32, 64)
    arrays, params = validate_hair_scene(scene)
    assert params['has_history'] and params['has_denoise_mask']
    assert params['temporal_index'] == 0.25 and params['temporal_plus_cycle'] == 19
    np.testing.assert_array_equal(arrays['denoise_mask'], scene['denoise_mask'])


@pytest.mark.parametrize('inputs,message', [
    ({'reflection_history': np.zeros((16, 32), np.uint32)}, 'both color and velocity'),
    ({'reflection_history': np.zeros((16, 32), np.float32),
      'reflection_velocity': np.zeros((16, 32, 2), np.float16)}, 'uint32'),
    ({'reflection_history': np.full((16, 32), 31 << 6, np.uint32),
      'reflection_velocity': np.zeros((16, 32, 2), np.float16)}, 'finite R11'),
    ({'reflection_history': np.zeros((16, 32), np.uint32),
      'reflection_velocity': np.full((16, 32, 2), np.inf, np.float16)}, 'finite half-resolution'),
    ({'denoise_mask': np.zeros((31, 64), np.uint8)}, 'full-resolution'),
    ({'denoise_mask': np.zeros((32, 64), np.float32)}, 'uint8'),
])
def test_scene_rejects_incomplete_or_incompatible_history(inputs, message):
    scene = scene_bundle()
    scene.update(inputs)
    with pytest.raises(ValueError, match=message):
        validate_hair_scene(scene)


def test_scene_clock_falls_back_after_view_invalidation(monkeypatch):
    from types import SimpleNamespace
    from ui.viewport import Viewport3D
    writes = {}
    monkeypatch.setattr('ui.viewport._set_uniform_1f', lambda p, name, value: writes.update({name: value}))
    view = SimpleNamespace(_fur_scene_gpu=SimpleNamespace(params={'temporal_index': 0.25, 'temporal_plus_cycle': 19}),
                           _temporal_sample_count=4, _fur_scene_is_current=lambda: True)
    Viewport3D._set_fur_temporal_uniforms(view, 1)
    assert writes == {'uTemporalIndex': 0.25, 'uTemporalPlusCycle': 19.0}
    view._fur_scene_is_current = lambda: False
    Viewport3D._set_fur_temporal_uniforms(view, 1)
    assert writes == {'uTemporalIndex': 0.625, 'uTemporalPlusCycle': 4.0}
