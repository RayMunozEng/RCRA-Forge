"""Verify integer lookup operations recovered from the retail DXIL."""
import hashlib

import numpy as np
import pytest

from core.local_lights import LIGHT_GPU_DTYPE, LightShellPlacement
from core.probe_lookup import (
    LIGHT_SHELL_BOX_VERTICES,
    LIGHT_SHELL_CYLINDER_VERTICES,
    build_local_light_frame_lookup,
    build_probe_frame_lookup,
    build_screen_lookup_bitfields,
    compact_selected_probe_records,
    conservative_probe_depth_overlap,
    compute_probe_z_bin_limits,
    generate_probe_z_bin_lookup,
    orthographic_back_rejection,
    perspective_back_rejection,
    project_probe_box_shell,
    project_probe_cylinder_shell,
    rasterize_probe_box_screen_lookup,
    rasterize_local_light_screen_lookup,
    rasterize_probe_screen_lookup,
    populate_probe_z_bin_limits,
    probe_lookup_word_count,
    reduce_linear_depth_bounds,
    light_shell_vertex_push_scale,
)


def records_with_limits(limits, capacity=None):
    capacity = len(limits) if capacity is None else capacity
    records = np.zeros((capacity, 128), np.uint8)
    words = records[:, 124:128].view('<u4').reshape(-1)
    for index, (minimum, maximum) in enumerate(limits):
        words[index] = minimum | (maximum << 16)
    return records


def unit_box_record(*, flags=0):
    record = np.zeros((1, 128), np.uint8)
    values = record.view('<f4').reshape(32)
    values[0:3] = [1, 0, 0]
    values[4:7] = [0, 1, 0]
    values[7] = 1
    values[12:15] = 1
    record[0, 44:48] = np.asarray([flags], '<u4').view(np.uint8)
    return record


def test_retail_box_shell_stream_is_twelve_outward_triangles():
    triangles = np.asarray(LIGHT_SHELL_BOX_VERTICES, np.float32).reshape(12, 3, 3)
    assert triangles.shape == (12, 3, 3)
    np.testing.assert_array_equal(np.unique(triangles.reshape(-1, 3), axis=0), [
        [-1, -1, -1], [-1, -1, 1], [-1, 1, -1], [-1, 1, 1],
        [1, -1, -1], [1, -1, 1], [1, 1, -1], [1, 1, 1],
    ])
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    centroids = triangles.mean(axis=1)
    assert np.all(np.sum(normals * centroids, axis=1) > 0)


def test_retail_cylinder_shell_stream_is_exact_and_outward_wound():
    triangles = np.asarray(LIGHT_SHELL_CYLINDER_VERTICES, '<f4').reshape(64, 3, 3)
    assert triangles.shape == (64, 3, 3)
    assert np.unique(triangles.reshape(-1, 3), axis=0).shape == (34, 3)
    assert hashlib.sha256(triangles.tobytes()).hexdigest() == (
        '8fe24507143963629632edf3c199c15a0bc0911d9af08280adf985f777d7cd46'
    )
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    centroids = triangles.mean(axis=1)
    assert np.all(np.sum(normals * centroids, axis=1) > 0)


def test_lookup_shell_push_uses_quarter_resolution_raster_width():
    value = light_shell_vertex_push_scale(np.float32(1.4530850648880005), 480)
    assert value.view(np.uint32) == np.float32(0.006054521072655916).view(np.uint32)
    with pytest.raises(ValueError, match='Raster width'):
        light_shell_vertex_push_scale(1, 0)
    with pytest.raises(ValueError, match='nonnegative'):
        light_shell_vertex_push_scale(1, 480, -1)


def test_box_shell_projection_executes_vertex_push_in_retail_stream_order():
    record = unit_box_record()
    view = np.eye(4, dtype=np.float32)
    projection = np.eye(4, dtype=np.float32)
    clip = project_probe_box_shell(
        record, view, projection, vert_push_scale=np.float32(.3), near_clip=np.float32(.1),
    )
    source = np.asarray(LIGHT_SHELL_BOX_VERTICES, np.float32).reshape(12, 3, 3)
    expected = source + source / np.sqrt(np.float32(3)) * np.float32(.3)
    np.testing.assert_allclose(clip[:, :, :3], expected, rtol=0, atol=2e-7)
    np.testing.assert_array_equal(clip[:, :, 3], np.ones((12, 3), np.float32))


def test_box_shell_projection_rejects_round_probe_records():
    with pytest.raises(ValueError, match='box shell'):
        project_probe_box_shell(
            unit_box_record(flags=1), np.eye(4, dtype=np.float32), np.eye(4, dtype=np.float32),
            vert_push_scale=0, near_clip=.1,
        )


def test_cylinder_shell_projection_preserves_retail_stream_order_without_push():
    record = unit_box_record(flags=1)
    identity = np.eye(4, dtype=np.float32)
    clip = project_probe_cylinder_shell(
        record, identity, identity, vert_push_scale=0, near_clip=.1,
    )
    source = np.asarray(LIGHT_SHELL_CYLINDER_VERTICES, np.float32).reshape(64, 3, 3)
    np.testing.assert_array_equal(clip[:, :, :3], source)
    np.testing.assert_array_equal(clip[:, :, 3], np.ones((64, 3), np.float32))

    with pytest.raises(ValueError, match='round shell'):
        project_probe_cylinder_shell(
            unit_box_record(), identity, identity, vert_push_scale=0, near_clip=.1,
        )


def test_saved_depth_lookup_preserves_empty_shape_and_accepts_round_shell():
    view = np.eye(4, dtype=np.float32)
    depth = np.ones((8, 8), np.float32)
    full, opaque = rasterize_probe_box_screen_lookup(
        np.zeros((0, 128), np.uint8), view, view, depth,
        screen_to_view_x=1, near_clip=.1,
    )
    assert full.shape == opaque.shape == (0, 1, 1)
    full, opaque = rasterize_probe_screen_lookup(
        unit_box_record(flags=1), view, view, np.ones((64, 64), np.float32),
        screen_to_view_x=1, near_clip=.1,
    )
    assert full.shape == opaque.shape == (1, 8, 8)
    assert np.count_nonzero(full) == np.count_nonzero(opaque) > 0


def test_explicit_local_light_shell_producer_matches_equivalent_probe_box():
    identity = np.eye(4, dtype=np.float32)
    record = unit_box_record()
    record.view('<f4').reshape(32)[8:11] = [0, 0, .5]
    record.view('<f4').reshape(32)[12:15] = 4
    depth = np.ones((64, 64), np.float32)
    expected = rasterize_probe_screen_lookup(
        record, identity, identity, depth,
        screen_to_view_x=1, near_clip=.1,
    )
    object_to_world = identity.copy()
    object_to_world[3, 2] = .5
    placement = LightShellPlacement(
        vertices=np.asarray(LIGHT_SHELL_BOX_VERTICES, np.float32) * np.float32(.25),
        object_to_world=object_to_world,
        local_aabb_minimum=np.asarray([-.25, -.25, -.25], np.float32),
        local_aabb_maximum=np.asarray([.25, .25, .25], np.float32),
    )
    actual = rasterize_local_light_screen_lookup(
        [placement], identity, identity, depth,
        screen_to_view_x=1, near_clip=.1,
    )
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])
    assert np.count_nonzero(actual[0]) == np.count_nonzero(actual[1]) == 4


def test_local_light_frame_builder_uses_one_shared_submitted_prefix():
    identity = np.eye(4, dtype=np.float32)
    records = np.zeros(2, dtype=LIGHT_GPU_DTYPE)
    records[0]['z_bin_min_max'] = np.uint32((4 << 16) | 2)
    records[1]['z_bin_min_max'] = np.uint32((7 << 16) | 6)
    object_to_world = identity.copy()
    object_to_world[3, 2] = .5
    placement = LightShellPlacement(
        vertices=np.asarray(LIGHT_SHELL_BOX_VERTICES, np.float32) * np.float32(.25),
        object_to_world=object_to_world,
        local_aabb_minimum=np.asarray([-.25, -.25, -.25], np.float32),
        local_aabb_maximum=np.asarray([.25, .25, .25], np.float32),
    )
    frame = build_local_light_frame_lookup(
        records, [placement], identity, identity, np.ones((64, 64), np.float32),
        screen_to_view_x=1, near_clip=.1, record_count=1, z_bin_count=8,
    )
    assert int(frame['light_record_count']) == 1
    assert frame['light_records'].shape == (1,)
    np.testing.assert_array_equal(
        frame['light_z_bin_lookup'], [[0, 0, 1, 1, 1, 0, 0, 0]],
    )
    assert frame['light_lookup_full'].shape == frame['light_lookup'].shape == (1, 8, 8)
    assert np.count_nonzero(frame['light_lookup_full']) == 4
    np.testing.assert_array_equal(frame['light_lookup_full'], frame['light_lookup'])

    empty = build_local_light_frame_lookup(
        records, [], identity, identity, np.ones((8, 8), np.float32),
        screen_to_view_x=1, near_clip=.1, record_count=0, z_bin_count=3,
    )
    assert empty['light_records'].shape == (0,)
    assert empty['light_z_bin_lookup'].shape == (0, 3)
    assert empty['light_lookup'].shape == empty['light_lookup_full'].shape == (0, 1, 1)


def test_probe_frame_builder_preserves_empty_resource_shapes():
    view = np.eye(4, dtype=np.float32)
    frame = build_probe_frame_lookup(
        [], np.zeros(0, np.uint8), view, view, np.ones((8, 8), np.float32),
        screen_to_view_x=1, near_clip=.1, z_bin_count=17,
    )
    assert frame['probe_records'].shape == (0, 128)
    assert frame['probe_record_count'] == 0
    assert frame['probe_placement_indices'].shape == (0,)
    assert frame['probe_z_bin_lookup'].shape == (0, 17)
    assert frame['probe_lookup'].shape == frame['probe_lookup_full'].shape == (0, 1, 1)


def test_probe_frame_builder_can_derive_empty_selection_from_matrices_or_frustum():
    view = np.eye(4, dtype=np.float32)
    frame = build_probe_frame_lookup(
        [], None, view, view, np.ones((8, 8), np.float32),
        screen_to_view_x=1, near_clip=.1, z_bin_count=17,
        frustum_planes=np.asarray([
            [1, 0, 0, 1], [-1, 0, 0, 1],
            [0, 1, 0, 1], [0, -1, 0, 1],
            [0, 0, 1, 1], [0, 0, -1, 1],
        ], np.float32),
    )
    assert frame['probe_record_count'] == 0
    assert frame['probe_selection_mask'].shape == (0,)
    derived = build_probe_frame_lookup(
        [], None, view, view, np.ones((8, 8), np.float32),
        screen_to_view_x=1, near_clip=.1,
    )
    assert derived['probe_record_count'] == 0


@pytest.mark.parametrize(('count', 'words'), [(0, 0), (1, 1), (31, 1), (32, 1), (33, 2), (64, 2)])
def test_lookup_word_count_rounds_up_in_groups_of_32(count, words):
    assert probe_lookup_word_count(count) == words


def test_submit_selection_compacts_in_sorted_manager_order():
    records = np.zeros((4, 128), np.uint8)
    records[:, 0] = [10, 20, 30, 40]
    compacted, source_indices = compact_selected_probe_records(
        records, np.array([3, 0, 2, 1], np.uint32), np.array([0, 4, 0, 1], np.uint8),
    )
    np.testing.assert_array_equal(source_indices, [0, 3])
    np.testing.assert_array_equal(compacted[:, 0], [10, 40])


def test_submit_selection_rejects_missing_or_out_of_range_indices():
    records = np.zeros((2, 128), np.uint8)
    with pytest.raises(ValueError, match='one integer'):
        compact_selected_probe_records(records, [0], [1])
    with pytest.raises(ValueError, match='exceeds'):
        compact_selected_probe_records(records, [0, 2], [1, 0])
    with pytest.raises(ValueError, match='one-dimensional'):
        compact_selected_probe_records(records, [0, 1], np.zeros((1, 2), np.uint8))


def test_z_bin_generation_uses_inclusive_unsigned_limits_and_active_count():
    records = records_with_limits([(0, 0), (1, 3), (3, 2), (65535, 65535)], capacity=8)
    lookup = generate_probe_z_bin_lookup(records, 65536, record_count=4)
    assert lookup.shape == (1, 65536)
    assert lookup[0, 0] == 0b0001
    assert lookup[0, 1] == 0b0010
    assert lookup[0, 2] == 0b0010
    assert lookup[0, 3] == 0b0010
    assert lookup[0, 4] == 0
    assert lookup[0, 65535] == 0b1000


def test_z_bin_generation_flushes_full_and_partial_words():
    records = records_with_limits([(2, 2)] * 33)
    lookup = generate_probe_z_bin_lookup(records, 4)
    np.testing.assert_array_equal(lookup[:, 2], [0xFFFFFFFF, 1])
    assert np.count_nonzero(lookup[:, [0, 1, 3]]) == 0


def test_z_bin_generation_rejects_invalid_capacity_and_preserves_empty_shapes():
    records = np.zeros((2, 128), np.uint8)
    assert generate_probe_z_bin_lookup(records, 0).shape == (1, 0)
    assert generate_probe_z_bin_lookup(records[:0], 17).shape == (0, 17)
    with pytest.raises(ValueError, match='exceeds'):
        generate_probe_z_bin_lookup(records, 4, record_count=3)
    with pytest.raises(ValueError, match='shape'):
        generate_probe_z_bin_lookup(np.zeros((2, 127), np.uint8), 4)


def test_z_bin_limit_producer_clamps_scales_floors_and_expands_maximum():
    packed, scale = compute_probe_z_bin_limits(
        np.array([-5, 10, 1500], np.float32),
        np.array([2, 2, 500], np.float32),
    )
    assert scale == np.float32(1024 / 2000)
    np.testing.assert_array_equal(packed & 0xFFFF, [0, 4, 512])
    np.testing.assert_array_equal(packed >> 16, [1, 7, 1025])


def test_record_z_bin_producer_uses_view_basis_camera_and_stable_extent_length():
    records = np.zeros((2, 128), np.uint8)
    floats = records.view('<f4').reshape(-1, 32)
    floats[:, 8:11] = [[3, 4, 22], [3, 4, -5]]
    floats[:, 12:15] = np.float32(1) / [[3, 4, 12], [3, 4, 12]]
    view_to_world = np.eye(4, dtype=np.float32)
    view_to_world[3, :3] = [3, 4, 7]

    produced, scale = populate_probe_z_bin_limits(records, view_to_world)
    packed = produced[:, 124:128].copy().view('<u4').reshape(-1)
    assert scale == 1
    # Centers are 15 and -12; stable length([3, 4, 12]) is exactly 13.
    np.testing.assert_array_equal(packed & 0xFFFF, [2, 0])
    np.testing.assert_array_equal(packed >> 16, [29, 2])


def test_record_z_bin_producer_accepts_manager_radius_and_active_prefix():
    records = np.zeros((2, 128), np.uint8)
    floats = records.view('<f4').reshape(-1, 32)
    floats[0, 8:11] = [0, 0, 10]
    original_tail = records[1].copy()
    produced, _ = populate_probe_z_bin_limits(
        records, np.eye(4, dtype=np.float32), record_count=1,
        bounding_radii=np.array([2], np.float32),
    )
    packed = int(produced[0, 124:128].copy().view('<u4')[0])
    assert (packed & 0xFFFF, packed >> 16) == (8, 13)
    np.testing.assert_array_equal(produced[1], original_tail)


def test_z_bin_limit_producer_rejects_invalid_bounds_and_view_inputs():
    with pytest.raises(ValueError, match='matching'):
        compute_probe_z_bin_limits([1, 2], [1])
    with pytest.raises(ValueError, match='nonnegative'):
        compute_probe_z_bin_limits([1], [-1])
    records = np.zeros((1, 128), np.uint8)
    with pytest.raises(ValueError, match='reciprocal'):
        populate_probe_z_bin_limits(records, np.eye(4, dtype=np.float32))
    bad_view = np.eye(4, dtype=np.float32)
    bad_view[0, 3] = 1
    with pytest.raises(ValueError, match='affine'):
        populate_probe_z_bin_limits(records, bad_view, bounding_radii=[1])


def test_screen_lookup_front_or_and_back_clear_match_shader_layers():
    front = np.zeros((33, 2, 3), bool)
    rejected = np.zeros_like(front)
    front[0, 0, 0] = front[31, 0, 0] = front[32, 1, 2] = True
    rejected[31, 0, 0] = rejected[32, 1, 2] = True
    full, opaque = build_screen_lookup_bitfields(front, rejected)
    np.testing.assert_array_equal(full[:, 0, 0], [0x80000001, 0])
    np.testing.assert_array_equal(opaque[:, 0, 0], [1, 0])
    np.testing.assert_array_equal(full[:, 1, 2], [0, 1])
    assert not opaque[:, 1, 2].any()


def test_screen_lookup_rejects_non_boolean_or_mismatched_coverage():
    with pytest.raises(ValueError, match='boolean'):
        build_screen_lookup_bitfields(np.zeros((1, 2, 2), np.uint8), np.zeros((1, 2, 2), bool))
    with pytest.raises(ValueError, match='matching'):
        build_screen_lookup_bitfields(np.zeros((1, 2, 2), bool), np.zeros((2, 2, 2), bool))


def test_depth_bounds_reduce_tiles_conservatively_and_round_through_r16f():
    depth = np.array([
        [1.0001, 2, 7],
        [3, 4, 8],
        [5, 6, 9],
    ], np.float32)
    nearest, farthest = reduce_linear_depth_bounds(depth, 2)
    expected_near = np.array([[1.0001, 7], [5, 9]], np.float16).astype(np.float32)
    expected_far = np.array([[4, 8], [6, 9]], np.float16).astype(np.float32)
    np.testing.assert_array_equal(nearest, expected_near)
    np.testing.assert_array_equal(farthest, expected_far)


def test_depth_bounds_reject_invalid_inputs_and_storage():
    with pytest.raises(ValueError, match='2D'):
        reduce_linear_depth_bounds([1, 2], 2)
    with pytest.raises(ValueError, match='positive'):
        reduce_linear_depth_bounds(np.ones((2, 2), np.float32), 0)
    with pytest.raises(ValueError, match='floating'):
        reduce_linear_depth_bounds(np.ones((2, 2), np.float32), 2, storage_dtype=np.uint16)


def test_conservative_depth_overlap_uses_farthest_front_and_nearest_back():
    selected = conservative_probe_depth_overlap(
        [5, 5, 10, 10], [10, 10, 20, 20],
        [1, 11, 1, 21], [4, 20, 15, 30],
    )
    np.testing.assert_array_equal(selected, [False, False, True, False])


def test_conservative_depth_overlap_rejects_nonfinite_values():
    with pytest.raises(ValueError, match='finite'):
        conservative_probe_depth_overlap(0, np.inf, 0, 1)


def test_perspective_back_depth_uses_half_coarse_derivative_envelope():
    selected = perspective_back_rejection([1, 2], [.2, -.4], [-.2, .4], [1.21, 2.39])
    np.testing.assert_array_equal(selected, [True, False])


def test_orthographic_back_depth_maps_clip_z_before_derivative_envelope():
    selected = orthographic_back_rejection([0, 1], [.2, -.2], [-.2, .2],
                                            [10.21, 1.19], 1, 10)
    np.testing.assert_array_equal(selected, [True, False])
