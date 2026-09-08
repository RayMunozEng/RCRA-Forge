from dataclasses import replace
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
import pytest

from core.environment_probes import ZoneEnvironmentProbe
from core.probe_lighting import (
    ProbePlacement, ProbeShaderRecord, blend_probe_weights,
    build_probe_frustum_selection_mask, build_probe_shader_record,
    build_selected_probe_shader_records,
    camera_relative_frustum_planes,
    parse_probe_shader_buffer, probe_fade_from_byte, probe_sort_key,
    probe_spatial_weight,
    hair_probe_sampling_parameters, hair_probe_specular_visibility,
    probe_parallax_direction, probe_sampling_plan,
)


@pytest.fixture
def probe():
    return ZoneEnvironmentProbe(
        index=0, instance_id=0x1234000000000000,
        position=(0, 0, 0), axes=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        texture_index=-1, draw_list_index=-1, textures=(), draw_lists=(),
        half_extents=(10, 10, 10), capture_offset=(0, 0, 0),
        falloff_negative=(2, 2, 2), falloff_positive=(2, 2, 2),
        proxy_negative=(-10, -20, -30), proxy_positive=(40, 50, 60),
        volume_shape=1, diffuse_flags=0, priority=0,
    )


def record(probe, **changes):
    return build_probe_shader_record(replace(probe, **changes), np.eye(4), cube_index=14, fade=1)


def test_manager_build_sorts_then_applies_resource_selection(probe):
    placements = [
        ProbePlacement(replace(probe, priority=1), np.eye(4), 1, 3, 1),
        ProbePlacement(replace(probe, priority=3), np.eye(4), 0, 4, .5),
        ProbePlacement(replace(probe, priority=2), np.eye(4), 2, 5, 1),
    ]
    records, source_indices = build_selected_probe_shader_records(
        placements, np.array([1, 1, 0], np.uint8),
    )
    np.testing.assert_array_equal(source_indices, [1, 0])
    values = records.view('<f4').reshape(-1, 32)
    np.testing.assert_array_equal(values[:, 15], [4, 3])
    np.testing.assert_array_equal(values[:, 3], [.5, 1])


def test_manager_build_requires_resource_indexed_integer_mask(probe):
    placement = ProbePlacement(probe, np.eye(4), 1, 0, 1)
    with pytest.raises(ValueError, match='one-dimensional integer'):
        build_selected_probe_shader_records([placement], np.ones((1, 2), np.uint8))
    with pytest.raises(ValueError, match='exceeds'):
        build_selected_probe_shader_records([placement], np.ones(1, np.uint8))


def test_frustum_selection_is_resource_indexed_and_uses_oriented_extents(probe):
    planes = np.asarray([
        [1, 0, 0, 1], [-1, 0, 0, 1],
        [0, 1, 0, 1], [0, -1, 0, 1],
        [0, 0, 1, 1], [0, 0, -1, 1],
    ], np.float32)
    inside = replace(probe, half_extents=(.25, .25, .25))
    tangent = replace(inside, position=(1.25, 0, 0))
    outside = replace(inside, position=(1.251, 0, 0))
    placements = [
        ProbePlacement(outside, np.eye(4), 0, 0, 1),
        ProbePlacement(inside, np.eye(4), 2, 1, 1),
        ProbePlacement(tangent, np.eye(4), 4, 2, 1),
    ]
    mask = build_probe_frustum_selection_mask(
        placements, planes, active_mask=np.array([1, 0, 1, 0, 1], np.uint8),
    )
    np.testing.assert_array_equal(mask, [0, 0, 1, 0, 1])


def test_frustum_selection_applies_active_and_transition_gates(probe):
    planes = np.asarray([
        [1, 0, 0, 100], [-1, 0, 0, 100],
        [0, 1, 0, 100], [0, -1, 0, 100],
        [0, 0, 1, 100], [0, 0, -1, 100],
    ], np.float32)
    placements = [
        ProbePlacement(probe, np.eye(4), 1, 0, 1),
        ProbePlacement(probe, np.eye(4), 3, 1, 1),
    ]
    mask = build_probe_frustum_selection_mask(
        placements, planes, active_mask=np.array([0, 1, 0, 1], np.uint8),
        excluded_resource_indices=(3,),
    )
    np.testing.assert_array_equal(mask, [0, 1, 0, 0])
    with pytest.raises(ValueError, match='unique'):
        build_probe_frustum_selection_mask(placements + [placements[0]], planes)
    with pytest.raises(ValueError, match='six finite'):
        build_probe_frustum_selection_mask(placements, np.eye(4))


def test_camera_relative_frustum_plane_extraction_uses_d3d_zero_to_one_clip():
    view = np.eye(4, dtype=np.float32)
    view[3, :3] = [10, 20, 30]
    planes = camera_relative_frustum_planes(view, np.eye(4, dtype=np.float32))
    np.testing.assert_array_equal(planes, [
        [1, 0, 0, -9], [-1, 0, 0, 11],
        [0, 1, 0, -19], [0, -1, 0, 21],
        [0, 0, 1, -30], [0, 0, -1, 31],
    ])


def test_gpu_record_layout_matches_reflected_offsets():
    raw = bytearray(struct.pack('<32f', *range(32)))
    struct.pack_into('<I', raw, 44, 0x81)
    struct.pack_into('<I', raw, 124, 0xCAFE0012)
    parsed, = parse_probe_shader_buffer(raw)
    assert parsed.axis_x == (0, 1, 2) and parsed.fade == 3
    assert parsed.axis_y == (4, 5, 6) and parsed.z_sign == 7
    assert parsed.position == (8, 9, 10) and parsed.flags == 0x81
    assert parsed.reciprocal_extents == (12, 13, 14) and parsed.cube_index == 15
    assert parsed.reciprocal_falloff_positive == (16, 17, 18)
    assert parsed.reciprocal_falloff_negative == (20, 21, 22)
    assert parsed.proxy_negative == (19, 23, 27)
    assert parsed.proxy_positive == (24, 25, 26)
    assert parsed.capture_position == (28, 29, 30)
    assert parsed.z_bin_min_max == 0xCAFE0012
    assert parsed.to_bytes() == raw


@pytest.mark.parametrize('size', [1, 127, 129, 255])
def test_truncated_gpu_record_buffer_fails(size):
    with pytest.raises(ValueError, match='multiple of 128'):
        parse_probe_shader_buffer(bytes(size))


def test_cooked_record_uses_zone_row_matrix_and_retail_field_mapping(probe):
    probe = replace(probe, position=(2, 3, 4), half_extents=(10, 20, 30),
                    capture_offset=(1, 2, 3), falloff_negative=(0, -2, .25),
                    falloff_positive=(2, 4, 6), diffuse_flags=0x81)
    matrix = ((0, 0, 1, 0), (0, 1, 0, 0), (-1, 0, 0, 0), (10, 20, 30, 1))
    result = build_probe_shader_record(probe, matrix, cube_index=7, fade=.5)
    assert result.position == (6, 23, 32)
    assert result.axis_x == (0, 0, 1) and result.axis_y == (0, 1, 0)
    assert result.z_sign == 1
    assert result.capture_position == (7, 25, 35)
    assert result.flags == 2 and result.cube_index == 7 and result.fade == .5
    np.testing.assert_allclose(result.reciprocal_extents, [0.1, 0.05, 1 / 30])
    np.testing.assert_allclose(result.reciprocal_falloff_negative, [1000, 2000, 120])
    assert result.reciprocal_falloff_positive == (5, 5, 5)
    assert result.proxy_negative == (-10, -20, -30)


def test_mirrored_probe_reconstructs_third_axis_handedness(probe):
    matrix = np.diag((-1, 1, 1, 1))
    probe = replace(probe, falloff_negative=(2, 2, 4))
    result = build_probe_shader_record(probe, matrix, cube_index=7, fade=1)
    assert result.z_sign == -1
    np.testing.assert_allclose(probe_spatial_weight(result, [[0, 0, 8], [0, 0, -8]]),
                               [1, .5625], atol=2e-6)


@pytest.mark.parametrize('matrix', [np.eye(3), np.full((4, 4), np.nan), np.eye(4).T + .1])
def test_invalid_zone_matrices_are_not_silently_inferred(probe, matrix):
    with pytest.raises(ValueError, match='zone_to_world'):
        build_probe_shader_record(probe, matrix, cube_index=0, fade=1)


def test_box_directional_falloff_and_corner_distance(probe):
    box = record(probe, falloff_negative=(4, 2, 2))
    points = [[0, 0, 0], [8, 0, 0], [-6, 0, 0], [9, 0, 0], [-8, 0, 0],
              [9, 9, 0], [9, 9, 9], [10, 0, 0], [20, 0, 0]]
    np.testing.assert_allclose(probe_spatial_weight(box, points),
                               [1, 1, 1, .5625, .5625, .25, .0625, 0, 0], atol=2e-6)


def test_cylinder_round_falloff_and_center_singularity(probe):
    cylinder = record(probe, volume_shape=2)
    diagonal = 9 / np.sqrt(2)
    points = [[0, 0, 0], [8, 0, 0], [9, 0, 0], [diagonal, 0, diagonal],
              [9, 9, 0], [10, 0, 0], [10, 10, 10]]
    np.testing.assert_allclose(probe_spatial_weight(cylinder, points),
                               [1, 1, .5625, .5625, .25, 0, 0], atol=2e-6)


def test_asymmetric_cylinder_shifts_inner_center(probe):
    cylinder = record(probe, volume_shape=2, falloff_positive=(4, 2, 4))
    np.testing.assert_allclose(probe_spatial_weight(cylinder, [[-1, 0, -1], [8, 0, -1], [-9, 0, -1]]),
                               [1, .5625, .5625], atol=2e-6)


def test_sort_key_orders_priority_then_size_with_deterministic_id_tie(probe):
    small = replace(probe, half_extents=(5, 5, 5))
    tie = replace(probe, instance_id=probe.instance_id | 0xFFFFFF)
    authored = replace(probe, priority=1, half_extents=(400, 400, 400))
    assert sorted([probe, small, tie, authored], key=probe_sort_key, reverse=True) == [authored, small, tie, probe]
    assert probe_sort_key(replace(probe, priority=-1)) == probe_sort_key(probe)


def test_residency_fade_is_clamped_smoothstep(probe):
    assert probe_fade_from_byte(0) == 0
    assert probe_fade_from_byte(255) == 1
    assert .498 < probe_fade_from_byte(127) < .499
    assert .504 < probe_fade_from_byte(128) < .505
    with pytest.raises(ValueError):
        probe_fade_from_byte(256)


def test_full_weight_probe_ends_mask_processing_before_broader_record(probe):
    empty = replace(record(probe), fade=0, cube_index=-1)
    records = [empty] * 19
    records[10] = record(probe)
    records[18] = replace(record(probe), cube_index=22)
    result = blend_probe_weights(records, (0, 0, 0), 0x40400)
    assert [(s['record_index'], s['cube_index'], s['sample_weight']) for s in result['samples']] == [(10, 14, 1)]
    assert result['default_weight'] == 0


def test_blending_subtracts_coverage_then_normalizes_sample_accumulation(probe):
    records = [replace(record(probe), fade=.4), replace(record(probe), fade=.3, cube_index=15)]
    result = blend_probe_weights(records, (0, 0, 0), 3)
    np.testing.assert_allclose([s['accumulated_weight'] for s in result['samples']], [.4, .18], atol=1e-7)
    np.testing.assert_allclose([s['sample_weight'] for s in result['samples']], [.7 * .4 / .58, .7 * .18 / .58], atol=1e-7)
    assert result['default_weight'] == pytest.approx(.3)


def test_blending_exhaustion_and_high_lookup_words(probe):
    entries = [replace(record(probe), fade=.75)] * 35
    result = blend_probe_weights(entries, (0, 0, 0), (1 << 31) | (1 << 32) | (1 << 34))
    assert [s['record_index'] for s in result['samples']] == [31, 32]
    np.testing.assert_allclose([s['sample_weight'] for s in result['samples']], [.8, .2])
    assert result['default_weight'] == 0
    assert result['remaining_before_default_clamp'] == -.5


def test_empty_and_unavailable_probes_leave_the_default_weight(probe):
    empty = replace(record(probe), fade=0, cube_index=-1)
    assert blend_probe_weights([empty], (0, 0, 0), 1)['default_weight'] == 1
    assert blend_probe_weights([], (0, 0, 0), 0)['default_weight'] == 1
    with pytest.raises(ValueError, match='missing probe'):
        blend_probe_weights([empty], (0, 0, 0), 2)
    with pytest.raises(ValueError, match='resident cube'):
        blend_probe_weights([replace(empty, fade=1)], (0, 0, 0), 1)


def test_probe_buffer_cli_preserves_high_lookup_words_and_writes_json(probe, tmp_path):
    empty = replace(record(probe), fade=0, cube_index=-1).to_bytes()
    data = empty * 31 + record(probe).to_bytes() + empty
    buffer_path = tmp_path / 'synthetic-probe-buffer.bin'
    output_path = tmp_path / 'result.json'
    buffer_path.write_bytes(data)
    run = subprocess.run([
        sys.executable, str(Path(__file__).resolve().parents[1] / 'tools/analyze_probe_buffer.py'),
        '--buffer', str(buffer_path), '--world-point', '0', '0', '0',
        '--lookup-mask', '0x180000000', '--output', str(output_path),
    ], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    output = json.loads(output_path.read_text())
    assert output['record_count'] == 33
    assert set(output['masked_records']) == {'31', '32'}
    assert output['samples'][0]['record_index'] == 31
    assert output['samples'][0]['cube_index'] == 14
    assert output['samples'][0]['sample_weight'] == 1
    assert output['default_weight'] == 0


def test_diffuse_coverage_uses_only_enabled_raw_contributions(probe):
    first = replace(record(probe), fade=.4)
    second = replace(record(probe, diffuse_flags=1), fade=.3)
    result = blend_probe_weights([first, second], (0, 0, 0), 3)
    np.testing.assert_allclose([s['diffuse_sample_weight'] for s in result['samples']], [0, .18])
    assert result['diffuse_base_weight'] == pytest.approx(.82)
    both = blend_probe_weights([replace(first, flags=2), second], (0, 0, 0), 3)
    np.testing.assert_allclose([s['diffuse_sample_weight'] for s in both['samples']], [.4, .18])
    assert both['diffuse_base_weight'] == pytest.approx(.42)
    assert both['default_weight'] == pytest.approx(.3)


def test_full_specular_coverage_can_leave_diffuse_on_light_grid(probe):
    result = blend_probe_weights([record(probe), record(probe, diffuse_flags=1)], (0, 0, 0), 3)
    assert result['default_weight'] == 0
    assert result['diffuse_base_weight'] == 1
    assert result['samples'][0]['diffuse_sample_weight'] == 0


def test_gloss_controls_mip_and_smoothstep_capture_offset():
    mip, scale = hair_probe_sampling_parameters([-.2, 0, 1 / 3, 2 / 3, 1, 1.2])
    np.testing.assert_allclose(mip, [5, 5, 10 / 3, 5 / 3, 0, -1], atol=3e-7)
    np.testing.assert_allclose(scale, [0, 0, .5, 1, 1, 1])


def test_parallax_uses_signed_proxy_bounds_and_scales_only_capture_delta(probe):
    env = record(probe, capture_offset=(1, 2, 3))
    directions = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, 0, -1]]
    expected = [[39, 1, 1], [-11, 1, 1], [1, 48, 1], [1, 1, -33]]
    np.testing.assert_allclose(probe_parallax_direction(env, [2, 3, 4], directions), expected)
    np.testing.assert_allclose(probe_parallax_direction(env, [2, 3, 4], [1, 0, 0],
                                                      capture_offset_scale=.5), [38.5, .5, .5])
    np.testing.assert_allclose(probe_parallax_direction(env, [2, 3, 4], [1, 0, 0],
                                                      capture_offset_scale=0), [38, 0, 0])


def test_parallel_ray_at_proxy_boundary_uses_d3d_minimum_behavior(probe):
    env = record(probe)
    np.testing.assert_allclose(probe_parallax_direction(env, [40, 3, 4], [0, 1, 0]), [40, 50, 4])


def test_signed_zero_parallel_ray_preserves_shader_degeneracy(probe):
    projected = probe_parallax_direction(record(probe), [2, 3, 4], [-1.0, -0.0, -0.0])
    assert np.isposinf(projected[0])
    assert np.isnan(projected[1:]).all()


def test_cylinder_influence_still_uses_box_proxy_intersection(probe):
    env = record(probe, volume_shape=2)
    np.testing.assert_allclose(probe_parallax_direction(env, [0, 0, 0], [1, 0, 1]), [40, 0, 40])


@pytest.mark.parametrize('rotation', [((0, 0, 1), (0, 1, 0), (-1, 0, 0)),
                                     ((-1, 0, 0), (0, 1, 0), (0, 0, 1))])
def test_parallax_rotates_with_zone_including_mirrors(probe, rotation):
    matrix = np.eye(4, dtype=np.float32)
    matrix[:3, :3] = rotation
    matrix[3, :3] = [100, 200, 300]
    env = build_probe_shader_record(probe, matrix, cube_index=14, fade=1)
    point = np.array([2, 3, 4]) @ rotation + matrix[3, :3]
    direction = np.array([1, 0, 0]) @ rotation
    np.testing.assert_allclose(probe_parallax_direction(env, point, direction),
                               np.array([40, 3, 4]) @ rotation)


@pytest.mark.parametrize('direction', [(0, 0, 0), (np.nan, 0, 1), (1, 2)])
def test_invalid_parallax_direction_fails(probe, direction):
    with pytest.raises(ValueError):
        probe_parallax_direction(record(probe), (0, 0, 0), direction)


def test_visibility_uses_coarse_luminance_and_separate_grid_scalar():
    np.testing.assert_allclose(hair_probe_specular_visibility([0, .5, 1], 0, 1), [0, 0, .75])
    np.testing.assert_allclose(hair_probe_specular_visibility([0, .5, 1], 1, 1), [1, 1, 1])
    np.testing.assert_allclose(hair_probe_specular_visibility([0, .5, 1], 2, 1), [2, 2, 1.25])
    assert hair_probe_specular_visibility(0, 0, 0) == 0
    assert hair_probe_specular_visibility(0, 1, 0) == 2


def test_sampling_plan_keeps_parallax_and_coarse_fetches_distinct(probe):
    plan = probe_sampling_plan([record(probe, diffuse_flags=1)], (2, 3, 4), 1,
                               reflection_direction=(1, 0, 0), shading_normal=(0, 1, 0),
                               average_gloss=1 / 3)
    sample, = plan['samples']
    np.testing.assert_allclose(sample['specular_direction'], [39, 1.5, 2])
    np.testing.assert_allclose(sample['diffuse_direction'], [2, 50, 4])
    assert plan['specular_mip'] == pytest.approx(10 / 3)
    assert plan['coarse_luminance_direction'] == [1, 0, 0]
    assert plan['coarse_luminance_rgb_weights'] == [.25, .5, .25]
    assert plan['diffuse_base_weight'] == 0


def test_degenerate_sampling_plan_is_valid_json_with_explicit_nulls(probe):
    plan = probe_sampling_plan([record(probe)], (2, 3, 4), 1,
                               reflection_direction=(-1.0, -0.0, -0.0), shading_normal=(0, 1, 0),
                               average_gloss=.5)
    assert plan['samples'][0]['specular_direction_finite'] is False
    assert plan['samples'][0]['specular_direction'] == [None, None, None]
    json.dumps(plan, allow_nan=False)


def test_cli_sampling_plan_requires_complete_inputs(probe, tmp_path):
    buffer_path = tmp_path / 'synthetic-probe-buffer.bin'
    buffer_path.write_bytes(record(probe, diffuse_flags=1).to_bytes())
    output_path = tmp_path / 'plan.json'
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'tools/analyze_probe_buffer.py'),
               '--buffer', str(buffer_path), '--world-point', '2', '3', '4',
               '--lookup-mask', '1', '--output', str(output_path),
               '--reflection-direction', '1', '0', '0']
    partial = subprocess.run(command, capture_output=True, text=True)
    assert partial.returncode == 2 and 'requires' in partial.stderr
    run = subprocess.run(command + ['--shading-normal', '0', '1', '0', '--average-gloss', '0'],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    report = json.loads(output_path.read_text())
    assert report['result_kind'] == 'hair_probe_sampling_plan_before_texture_fetch_and_shading'
    assert report['samples'][0]['specular_direction'] == [38, 0, 0]
    assert report['samples'][0]['diffuse_direction'] == [2, 50, 4]
