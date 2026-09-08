"""Captured resource dimensions and indices must agree before GPU upload."""
import struct

import numpy as np
import pytest

from core.hair_lighting_replay import validate_replay_bundle


def bundle():
    view, world = bytearray(480), bytearray(896)
    struct.pack_into('<3f', view, 48, 1, 2, 3)
    struct.pack_into('<4f', world, 720, .1, .2, .3, .6)
    struct.pack_into('<I', world, 748, 2)
    value = dict(world_points=np.zeros((1, 3), np.float32),
                 shading_normals=np.array([[1, 0, 0]], np.float32),
                 environment_normals=np.array([[0, 1, 0]], np.float32),
                 reflection_directions=np.array([[0, 0, 1]], np.float32),
                 average_gloss=np.array([.4], np.float32),
                 viewport_cbuffer=np.frombuffer(view, np.uint8),
                 world_cbuffer=np.frombuffer(world, np.uint8),
                 probe_records=np.zeros((34, 128), np.uint8),
                 lookup_words=np.array([[0, 2]], np.uint32),
                 grid_lookup=np.zeros(64**3, np.uint32),
                 grid_data=np.zeros((4096, 4), np.uint32))
    for mip in range(6):
        size = 32 >> mip
        value[f'default_mip{mip}'] = np.zeros((6, size, size, 3), np.float16)
        value[f'local_mip{mip}'] = np.zeros((1, 6, size, size, 3), np.float16)
    return value


def test_lookup_second_word_and_captured_constant_offsets():
    arrays, params = validate_replay_bundle(bundle())
    assert params['word_count'] == 2 and params['record_count'] == 34
    assert params['camera_position'] == (1, 2, 3)
    assert params['intensity'] == pytest.approx(.6)
    assert arrays['default_mip0'].dtype == np.float32
    assert not np.array_equal(arrays['shading_normals'], arrays['environment_normals'])


def test_explicit_active_probe_count_excludes_buffer_capacity():
    value = bundle()
    value['probe_record_count'] = np.array(33, np.uint32)
    value['lookup_words'][0, 1] = 1
    _, params = validate_replay_bundle(value)
    assert params['record_count'] == 33
    value['lookup_words'][0, 1] = 2
    with pytest.raises(ValueError, match='missing record'):
        validate_replay_bundle(value)


@pytest.mark.parametrize('active', [np.array([33], np.uint32), np.array(35, np.uint32), np.array(-1)])
def test_invalid_active_probe_count_is_rejected(active):
    value = bundle()
    value['probe_record_count'] = active
    with pytest.raises(ValueError, match='probe_record_count'):
        validate_replay_bundle(value)


@pytest.mark.parametrize('change,message', [
    (lambda v: v.update(probe_records=v['probe_records'][:33]), 'missing record'),
    (lambda v: v['probe_records'][33].__setitem__(slice(60, 64), np.frombuffer(struct.pack('<f', 1), np.uint8)), 'missing cube'),
    (lambda v: v['grid_lookup'].__setitem__(0, 4096), 'missing brick'),
    (lambda v: v.update(local_mip5=np.zeros((2, 6, 1, 1, 3), np.float32)), 'cube count'),
    (lambda v: v.update(lookup_words=v['lookup_words'].astype(np.int32)), 'dtype'),
    (lambda v: v.pop('environment_normals'), 'environment_normals'),
    (lambda v: v['world_cbuffer'].__setitem__(slice(672, 676), np.frombuffer(struct.pack('<f', .1), np.uint8)), 'distant_height'),
    (lambda v: v['world_points'].__setitem__((0, 0), 2**31), 'addressing'),
])
def test_incompatible_capture_bindings_fail_before_gpu_upload(change, message):
    value = bundle()
    change(value)
    with pytest.raises(ValueError, match=message):
        validate_replay_bundle(value)


def compressed_bundle():
    value = bundle()
    for prefix, leading in (('default', (6,)), ('local', (1, 6))):
        for mip in range(6):
            del value[f'{prefix}_mip{mip}']
            blocks = max(1, (32 >> mip) // 4)
            value[f'{prefix}_bc6_mip{mip}'] = np.zeros((*leading, blocks, blocks, 16), np.uint8)
    return value


def test_captured_bc6_blocks_keep_bytes_and_small_mip_extents():
    value = compressed_bundle()
    value['default_bc6_mip5'][0, 0, 0] = np.arange(16, dtype=np.uint8)
    arrays, params = validate_replay_bundle(value)
    assert params['cube_formats'] == {'default': 'bc6u', 'local': 'bc6u'}
    assert np.array_equal(arrays['default_bc6_mip5'], value['default_bc6_mip5'])
    assert arrays['local_bc6_mip5'].shape == (1, 6, 1, 1, 16)


@pytest.mark.parametrize('change,message', [
    (lambda v: v.pop('local_bc6_mip3'), 'Missing replay input'),
    (lambda v: v.update(default_bc6_mip0=v['default_bc6_mip0'][:, :-1]), 'complete blocks'),
    (lambda v: v.update(local_bc6_mip2=np.zeros((2, 6, 2, 2, 16), np.uint8)), 'cube count'),
    (lambda v: v.update(default_mip0=np.zeros((6, 32, 32, 3), np.float32)), 'not both'),
])
def test_invalid_compressed_subresources_fail_before_upload(change, message):
    value = compressed_bundle()
    change(value)
    with pytest.raises(ValueError, match=message):
        validate_replay_bundle(value)
