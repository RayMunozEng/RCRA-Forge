"""Retail local-light record and lookup boundaries."""

from dataclasses import replace
import hashlib
import struct
import zlib

import numpy as np
import pytest

from core.local_lights import (
    LIGHT_GPU_DTYPE,
    LIGHT_SHELL_CBUFFER_DTYPE,
    LIGHT_VOLUME_GPU_DTYPE,
    LightAtlasAllocationWords,
    LightAtlasHandleTable,
    LightColorVolumeSource,
    LightGoboVolumeSource,
    LightGpuSubtype1AuxiliarySources,
    LightGpuSubtype3AuxiliarySources,
    LightGpuSubtype4AuxiliarySources,
    LightManagerCandidateSource,
    LightManagerClipResource,
    LightManagerFramePartition,
    LightManagerFrameSourceOrder,
    LightManagerHierarchicalDepthSnapshot,
    LightManagerOcclusionQuery,
    LightManagerPartitionInputs,
    LightManagerPrimaryQueryDescriptor,
    LightManagerPrimaryQueryAlternateDescriptor,
    LightManagerPrimaryQueryOverride,
    LightManagerPrimaryQueryOverrideInputs,
    LightManagerObjectVisibilityNode,
    LightManagerResourceReadinessNode,
    LightManagerResourceShapeInputs,
    LightManagerSecondaryMerge,
    LightManagerSecondaryQueryDescriptor,
    LightManagerSpatialAabb,
    LightManagerSpatialCell,
    LightManagerSpatialEntry,
    LightManagerSpatialPackedBound,
    LightManagerSpatialTreeLookup,
    LightManagerSpatialTreeNode,
    LightManagerSpatialTreeSubdivision,
    LightManagerSpatialTreeChildCell,
    LightManagerSpatialTreeRedistribution,
    LightManagerSpatialPage,
    LightManagerSpatialPageQueryResolution,
    LightManagerSpatialWorkerFlush,
    LightManagerSpatialOptionalQueryBuckets,
    LightManagerSpatialPrimaryQueryBuckets,
    LightManagerTypeResourceEntry,
    LightManagerTypeResourceTable,
    LightPointShadowMapSource,
    LightProjectedShadowMapSource,
    LightShadowVolumeSource,
    LightSubtype3ClipVolumeSource,
    LightVolumeGpuSource,
    LightGpuBaseSource,
    LightShellPlacement,
    build_light_gpu_base_record,
    build_color_light_volume_record,
    build_light_gpu_subtype_1_record,
    build_light_gpu_subtype_3_record,
    build_light_gpu_subtype_4_record,
    build_light_manager_selection_batches,
    classify_light_manager_spatial_aabb,
    classify_light_manager_spatial_packed_sphere,
    classify_light_manager_spatial_optional_packed_sphere,
    classify_light_manager_spatial_optional_page_chain,
    classify_light_manager_spatial_primary_page_chain,
    decode_light_manager_spatial_page,
    resolve_light_manager_spatial_primary_page_query_indices,
    resolve_light_manager_spatial_primary_query_indices,
    resolve_light_manager_spatial_optional_query_indices,
    resolve_light_manager_spatial_optional_page_query_indices,
    classify_light_manager_spatial_query_obb,
    build_light_manager_box_shell_vertices,
    build_light_manager_occlusion_query,
    evaluate_light_manager_hierarchical_depth,
    build_light_manager_primary_query_base_descriptor,
    build_light_manager_primary_query_alternate_descriptor,
    apply_light_manager_primary_query_override,
    build_light_manager_resource_clip_planes,
    build_light_manager_resource_shell_output,
    build_light_manager_resource_shell_vertices,
    build_light_manager_resource_refresh_dispatch,
    build_light_manager_round_shell_vertices,
    build_light_manager_type_1_shell_vertices,
    build_light_manager_type_2_shell_vertices,
    build_light_manager_frame_source_order,
    build_light_manager_frame_partition,
    build_light_manager_secondary_merge,
    build_light_manager_secondary_query_descriptor,
    build_light_manager_secondary_query_sphere,
    build_light_volume_gpu_record,
    build_gobo_light_volume_record,
    build_primary_clip_light_volume_record,
    build_point_shadow_map_light_volume_record,
    build_projected_shadow_map_light_volume_record,
    build_shadow_volume_light_volume_record,
    build_subtype_3_clip_light_volume_record,
    build_light_shell_constants,
    build_light_shell_near_clip_plane,
    evaluate_hair_area_light,
    evaluate_point_light,
    evaluate_light_volume_multiplier,
    filter_light_manager_optional_query_sources,
    filter_light_manager_primary_query_sources,
    finalize_light_manager_resource_shell_output,
    generate_light_z_bin_lookup,
    light_clip_rejected,
    light_lookup_indices,
    light_lookup_indices_at_pixel,
    resolve_light_atlas_handle,
    select_light_manager_spatial_aabb_indices,
    light_lookup_word_count,
    light_lookup_words_at_pixels,
    light_manager_bounding_sphere_distance,
    light_manager_frame_priority,
    light_manager_runtime_flag_21_defer,
    light_manager_resource_chain_ready,
    light_manager_optional_query_source_visible,
    light_manager_primary_query_source_visible,
    light_manager_spatial_query_obb_intersects,
    light_manager_spatial_bound_admissible,
    decode_light_manager_spatial_entry,
    rebuild_light_manager_spatial_cell_bound,
    light_manager_resource_stream_allocation_bytes,
    light_manager_resource_version,
    light_manager_object_visibility,
    light_manager_type_resource_available,
    light_manager_auxiliary_volume_visible,
    light_manager_secondary_distance_squared,
    light_gobo_coordinates,
    light_shadow_map_coordinates,
    light_shadow_map_sample_plan,
    light_shadow_volume_coordinates,
    pack_light_manager_spatial_bound,
    lookup_light_manager_spatial_tree,
    begin_light_manager_spatial_tree_subdivision,
    redistribute_light_manager_spatial_tree_cell,
    collapse_light_manager_spatial_tree_cell,
    append_light_manager_spatial_page,
    allocate_light_manager_spatial_cell,
    allocate_light_manager_spatial_tree_node,
    insert_light_manager_spatial_owner,
    release_light_manager_spatial_cell,
    parse_light_gpu_records,
    parse_light_lookup_constants,
    parse_light_shell_constants,
    parse_light_volume_gpu_records,
    prepare_light_shell_vertices,
    prepare_light_shell_vertices_for_planes,
    project_light_shell_vertices,
    apply_light_gobo_sample,
    apply_light_shadow_volume_samples,
    resolve_light_shadow_map_sample,
    evaluate_light_manager_candidate,
    evaluate_light_manager_frame_partition,
)


def captured_light_zero_source(**changes):
    fields = {
        'world_axis_x': (-0.9024642109870911, 0.18937210738658905,
                         0.38690629601478577),
        'world_axis_y': (-0.39403626322746277, 5.778719724958137e-10,
                         -0.9190949201583862),
        'world_axis_z': (-0.1740509420633316, -0.9819053411483765,
                         0.07461947947740555),
        'world_position': (-322.5193176269531, 13.806163787841797,
                           721.2901000976562),
        'attenuation_radius': 2.0948801040649414,
        'linear_color': (9.100889205932617, 2.662903308868408,
                         0.008304795250296593),
        'specular_intensity': 1.0,
        'cone_parameters': (3.4213290214538574, -2.4192450046539307),
        'cut_on_depth': 0.0,
        'cut_off_depth': 16777216.0,
        'z_bin_min_depth': 27.0,
        'z_bin_max_depth': 30.0,
        'reciprocal_cone_sine': -1.4142135381698608,
        'bulb_radius': 0.041157566010951996,
        'bulb_length': 0.8231512904167175,
        'volumetric_fog': 2.0,
    }
    fields.update(changes)
    return LightGpuBaseSource(**fields)


def auxiliary_volume_source(seed=0.0):
    values = np.arange(16, dtype=np.float32).reshape(4, 4) + np.float32(seed)
    return LightVolumeGpuSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in values),
        atlas_coordinates=(seed + 16, seed + 17, seed + 18, seed + 19),
        extents=(seed + 20, seed + 21, seed + 22),
        fade=seed + 23,
        falloff_negative=(seed + 24, seed + 25, seed + 26),
        shadow_texel_scale=seed + 27,
        falloff_positive=(seed + 28, seed + 29, seed + 30),
        misc=seed + 31,
    )


def test_light_gpu_layout_matches_shader_reflection():
    assert LIGHT_GPU_DTYPE.itemsize == 128
    assert LIGHT_GPU_DTYPE.fields['world_position'][1] == 48
    assert LIGHT_GPU_DTYPE.fields['linear_color'][1] == 64
    assert LIGHT_GPU_DTYPE.fields['z_bin_min_max'][1] == 96
    assert LIGHT_GPU_DTYPE.fields['mod_id_and_gobo_id'][1] == 104
    assert LIGHT_GPU_DTYPE.fields['reciprocal_cone_sine'][1] == 120

    raw = bytearray(128)
    struct.pack_into('<3f', raw, 48, 1.25, -2.5, 3.75)
    struct.pack_into('<3f', raw, 64, 4.0, 5.0, 6.0)
    struct.pack_into('<I', raw, 96, 0x12345678)
    struct.pack_into('<I', raw, 104, 0x89ABCDEF)
    record = parse_light_gpu_records(raw)[0]
    np.testing.assert_array_equal(record['world_position'], [1.25, -2.5, 3.75])
    np.testing.assert_array_equal(record['linear_color'], [4, 5, 6])
    assert int(record['z_bin_min_max']) == 0x12345678
    assert int(record['mod_id_and_gobo_id']) == 0x89ABCDEF


def test_light_gpu_base_packer_rebuilds_captured_record_zero_exactly():
    expected = bytes.fromhex(
        'e50767bfc3ea413e9518c63ed694283d1fbfc9be20d81e30ce496bbf0bba523f'
        '693a32be265e7bbf19d2983d000000007942a1c30ce65c4191523444c867f43e'
        '3e9d1141026d2a40d610083c0000803f0ef75a40e9d41ac0000000000000804b'
        '1b001f0000000040ffffffff000000000000000000000000f304b5bf00000000'
    )
    actual = build_light_gpu_base_record(
        captured_light_zero_source(), z_bin_scale=1.0)
    assert actual.tobytes() == expected


def test_light_gpu_base_packer_applies_native_modes_flags_and_radius_floor():
    mode_one = build_light_gpu_base_record(
        captured_light_zero_source(
            attenuation_radius=0,
            radiance_mode=1,
            volumetric_fog=0.5,
            base_bit_flags=0x80,
            flag_103_bit0=True,
            flag_104=True,
            flag_105=True,
        ),
        z_bin_scale=1,
    )
    assert mode_one['inverse_attenuation_radius'] == np.float32(100000)
    assert mode_one['specular_intensity'] == 0
    assert int(mode_one['bit_flags_vfog']) == 0x380000d4

    mode_two = build_light_gpu_base_record(
        captured_light_zero_source(radiance_mode=2), z_bin_scale=1)
    np.testing.assert_array_equal(
        mode_two['linear_color'],
        np.asarray(captured_light_zero_source().linear_color, np.float32)
        * np.float32(1 / 1024),
    )
    assert mode_two['specular_intensity'] == np.float32(1024)


def test_light_gpu_base_packer_preserves_short_negative_radius_encoding():
    actual = build_light_gpu_base_record(
        captured_light_zero_source(bulb_radius=-.1, bulb_length=1),
        z_bin_scale=1,
    )
    np.testing.assert_array_equal(
        actual['world_axis_x'], captured_light_zero_source().world_axis_x)
    np.testing.assert_array_equal(
        actual['world_axis_y'], captured_light_zero_source().world_axis_y)
    assert actual['bulb_radius'] == np.float32(-.1)
    assert actual['bulb_length'] == np.float32(1)


def test_light_gpu_base_packer_remaps_long_negative_radius_encoding():
    source = captured_light_zero_source(bulb_radius=-.75, bulb_length=1)
    actual = build_light_gpu_base_record(source, z_bin_scale=1)
    np.testing.assert_array_equal(actual['world_axis_x'], source.world_axis_y)
    np.testing.assert_array_equal(
        actual['world_axis_y'], -np.asarray(source.world_axis_x, np.float32))
    np.testing.assert_array_equal(actual['world_axis_z'], source.world_axis_z)
    assert actual['bulb_radius'] == np.float32(-.5)
    assert actual['bulb_length'] == np.float32(1.5)


def test_light_volume_gpu_explicit_packer_preserves_all_128_bytes():
    record = build_light_volume_gpu_record(auxiliary_volume_source())

    assert record.dtype == LIGHT_VOLUME_GPU_DTYPE
    np.testing.assert_array_equal(
        record['transform_matrix'], np.arange(16, dtype=np.float32).reshape(4, 4))
    np.testing.assert_array_equal(
        record['atlas_coordinates'], np.arange(16, 20, dtype=np.float32))
    np.testing.assert_array_equal(record['extents'], (20, 21, 22))
    assert record['fade'] == np.float32(23)
    np.testing.assert_array_equal(record['falloff_negative'], (24, 25, 26))
    assert record['shadow_texel_scale'] == np.float32(27)
    np.testing.assert_array_equal(record['falloff_positive'], (28, 29, 30))
    assert record['misc'] == np.float32(31)


def test_primary_clip_volume_transposes_native_persistent_columns():
    columns = np.arange(12, dtype=np.float32).reshape(3, 4)
    record = build_primary_clip_light_volume_record(columns)
    expected = np.zeros((4, 4), dtype=np.float32)
    expected[:, :3] = columns.T

    np.testing.assert_array_equal(record['transform_matrix'], expected)
    assert not np.any(np.frombuffer(record.tobytes()[64:], np.uint8))


def test_shadow_volume_constructor_matches_native_atlas_and_field_mapping():
    matrix = np.arange(16, dtype=np.float32).reshape(4, 4)
    source = LightShadowVolumeSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        falloff_negative=(20, 21, 22),
        shadow_texel_scale=23,
        atlas_origin_texels=(-7, 11),
        atlas_size_words=(0x8005, 0xffff),
        misc=24,
        fade=25,
    )
    record = build_shadow_volume_light_volume_record(source)

    np.testing.assert_array_equal(record['transform_matrix'], matrix)
    np.testing.assert_array_equal(record['atlas_coordinates'], (
        -13 / 8192, 23 / 4096, 4 / 4096, 32766 / 2048))
    np.testing.assert_array_equal(record['extents'], (0, 0, 0))
    assert record['fade'] == np.float32(25)
    np.testing.assert_array_equal(record['falloff_negative'], (20, 21, 22))
    assert record['shadow_texel_scale'] == np.float32(23)
    np.testing.assert_array_equal(record['falloff_positive'], (0, 0, 0))
    assert record['misc'] == np.float32(24)


def test_gobo_constructor_matches_standard_native_atlas_mapping():
    matrix = np.arange(16, dtype=np.float32).reshape(4, 4)
    source = LightGoboVolumeSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        atlas_origin_texels=(-7, 11),
        atlas_size_words=(5, 9),
    )
    record = build_gobo_light_volume_record(source)

    np.testing.assert_array_equal(record['transform_matrix'], matrix)
    np.testing.assert_array_equal(record['atlas_coordinates'], (
        -13 / 8192, 23 / 4096, 4 / 4096, 8 / 2048))
    assert not np.any(np.frombuffer(record.tobytes()[80:], np.uint8))


def test_gobo_constructor_matches_native_dual_sign_y_flip():
    source = LightGoboVolumeSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in np.eye(4, dtype=np.float32)),
        atlas_origin_texels=(12, 20),
        atlas_size_words=(0x8005, 0x8009),
    )
    record = build_gobo_light_volume_record(source)

    np.testing.assert_array_equal(record['atlas_coordinates'], (
        25 / 8192, 28.5 / 2048, 4 / 4096, -8 / 2048))


def test_gobo_native_source_flows_through_subtype_1_allocator():
    source = LightGoboVolumeSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in np.eye(4, dtype=np.float32)),
        atlas_origin_texels=(2, 4), atlas_size_words=(8, 0x8010))
    result = build_light_gpu_subtype_1_record(
        captured_light_zero_source(), z_bin_scale=1,
        auxiliary=LightGpuSubtype1AuxiliarySources(gobo_volume=source),
        first_volume_index=3, volume_capacity=4)

    assert int(result.light['mod_id_and_gobo_id']) == 0x0003ffff
    assert int(result.light['bit_flags_vfog']) & 0xffff == 1 << 5
    np.testing.assert_array_equal(
        result.appended_volumes[0], build_gobo_light_volume_record(source))


def test_gobo_constructor_rejects_disabled_zero_width():
    with pytest.raises(ValueError, match='X size must be nonzero'):
        build_gobo_light_volume_record(LightGoboVolumeSource(
            transform_matrix=tuple(tuple(float(value) for value in row)
                                   for row in np.eye(4, dtype=np.float32)),
            atlas_origin_texels=(0, 0), atlas_size_words=(0x8000, 1)))


def test_color_volume_constructor_matches_direct_dimension_mode():
    record = build_color_light_volume_record(LightColorVolumeSource(
        dimensions=(2, 4, 8),
        negative_falloff_distances=(1, 2, 4),
        positive_falloff_distances=(4, 8, 16),
        fade=.75,
    ))

    assert not np.any(np.frombuffer(record.tobytes()[:80], np.uint8))
    np.testing.assert_array_equal(record['extents'], (2, 4, 8))
    assert record['fade'] == np.float32(.75)
    np.testing.assert_array_equal(record['falloff_negative'], (1, .5, .25))
    assert record['shadow_texel_scale'] == np.float32(0)
    np.testing.assert_array_equal(record['falloff_positive'], (.25, .125, .0625))
    assert record['misc'] == np.float32(0)


def test_color_volume_constructor_matches_reciprocal_dimension_mode():
    record = build_color_light_volume_record(LightColorVolumeSource(
        dimensions=(2, 4, 8),
        negative_falloff_distances=(1, 2, 4),
        positive_falloff_distances=(4, 8, 16),
        fade=.75,
        reciprocal_dimensions=True,
    ))

    np.testing.assert_array_equal(record['extents'], (.5, .25, .125))
    np.testing.assert_array_equal(record['falloff_negative'], (-2, -2, -2))
    np.testing.assert_array_equal(record['falloff_positive'], (.5, .5, .5))


def test_color_volume_constructor_rejects_nonfinite_division():
    with pytest.raises(ValueError, match='divisors'):
        build_color_light_volume_record(LightColorVolumeSource(
            dimensions=(2, 4, 8),
            negative_falloff_distances=(1, 0, 4),
            positive_falloff_distances=(4, 8, 16)))


def test_subtype_3_clip_constructor_matches_scaled_affine_inverse():
    matrix = np.asarray([
        [2, 0, 0, 0],
        [0, 4, 0, 0],
        [0, 0, 8, 0],
        [10, 20, 40, 1],
    ], dtype=np.float32)
    record = build_subtype_3_clip_light_volume_record(
        LightSubtype3ClipVolumeSource(
            transform_matrix=tuple(tuple(float(value) for value in row)
                                   for row in matrix),
            axis_scale=(.5, .25, .125)))
    expected = np.eye(4, dtype=np.float32)
    expected[3, :3] = (-10, -20, -40)

    np.testing.assert_array_equal(record['transform_matrix'], expected)
    assert record['fade'] == np.float32(1)
    assert not np.any(record['atlas_coordinates'])


def test_subtype_3_clip_constructor_matches_optional_unit_space_remap():
    matrix = np.asarray([
        [2, 0, 0, 0],
        [0, 4, 0, 0],
        [0, 0, 8, 0],
        [10, 20, 40, 1],
    ], dtype=np.float32)
    record = build_subtype_3_clip_light_volume_record(
        LightSubtype3ClipVolumeSource(
            transform_matrix=tuple(tuple(float(value) for value in row)
                                   for row in matrix),
            axis_scale=(.5, .25, .125), map_to_unit_space=True))
    expected = np.eye(4, dtype=np.float32)
    expected[:3, :3] *= np.float32(.5)
    expected[3, :3] = (-4.5, -9.5, -19.5)

    np.testing.assert_array_equal(record['transform_matrix'], expected)


def test_subtype_3_clip_constructor_reproduces_singular_zero_basis():
    matrix = np.zeros((4, 4), dtype=np.float32)
    matrix[3] = (2, 3, 4, 1)
    record = build_subtype_3_clip_light_volume_record(
        LightSubtype3ClipVolumeSource(
            transform_matrix=tuple(tuple(float(value) for value in row)
                                   for row in matrix),
            axis_scale=(1, 1, 1)))
    expected = np.zeros((4, 4), dtype=np.float32)
    expected[3, 3] = 1

    np.testing.assert_array_equal(record['transform_matrix'], expected)


def test_atlas_handle_resolver_uses_valid_bit_generation_byte_and_index():
    allocations = (
        LightAtlasAllocationWords(1, 2, 3, 4),
        LightAtlasAllocationWords(8, 16, 32, 64),
    )
    table = LightAtlasHandleTable(
        generation_word=0x12345A, allocations=allocations)

    assert resolve_light_atlas_handle(table, 0xD35A0001) == allocations[1]


@pytest.mark.parametrize('handle', [0x005A0001, 0x805B0001])
def test_atlas_handle_resolver_returns_zero_words_for_invalid_handles(handle):
    table = LightAtlasHandleTable(
        generation_word=0x5A,
        allocations=(LightAtlasAllocationWords(1, 2, 3, 4),) * 2)

    assert resolve_light_atlas_handle(table, handle) == \
        LightAtlasAllocationWords(0, 0, 0, 0)


def test_atlas_handle_resolver_rejects_valid_index_outside_snapshot():
    table = LightAtlasHandleTable(
        generation_word=0x5A,
        allocations=(LightAtlasAllocationWords(1, 2, 3, 4),))

    with pytest.raises(ValueError, match='outside the supplied table'):
        resolve_light_atlas_handle(table, 0x805A0001)


def manager_candidate(**changes):
    matrix = np.eye(4, dtype=np.float32)
    fields = {
        'transform_matrix': tuple(tuple(float(value) for value in row)
                                  for row in matrix),
        'local_bound_center': (0, 0, 0),
        'bound_radius_scale': 1,
        'bound_extents': (1, 2, 3),
        'runtime_flags': (1 << 2),
        'light_type': 1,
        'distance_fade_offset': 1,
        'distance_fade_scale': 0,
        'maximum_camera_distance': 100,
        'linear_color': (1, 2, 3),
    }
    fields.update(changes)
    return LightManagerCandidateSource(**fields)


def test_light_manager_bounding_sphere_distance_uses_transformed_center_and_radius():
    matrix = np.asarray([
        [2, 0, 0, 9], [0, 3, 0, 8], [0, 0, 4, 7], [10, 20, 30, 6],
    ], np.float32)
    source = manager_candidate(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        local_bound_center=(1, 2, 3), bound_radius_scale=.5,
        bound_extents=(2, 4, 6))
    distance = light_manager_bounding_sphere_distance(source, (12, 26, 46))
    assert distance.view('<u4') == np.float32(1).view('<u4')


def test_light_manager_secondary_query_sphere_matches_native_float4_builder():
    actual = build_light_manager_secondary_query_sphere(
        (-.25, .5, 1.25), (3.5, -4.25, 8), -2.75)
    assert actual.view('<u4').tolist() == [
        0x40860000, 0xc0b40000, 0x40920000, 0x42400000]
    assert hashlib.sha256(actual.astype('<f4').tobytes()).hexdigest() == (
        '429fe65f630a909b13392296108c45105e0263a24501497c9692d1c6965fac4c')
    assert build_light_manager_secondary_query_sphere(
        None, None, 123).view('<u4').tolist() == [0, 0, 0, 0]
    with pytest.raises(ValueError, match='both be present'):
        build_light_manager_secondary_query_sphere(None, (0, 0, 0), 0)


@pytest.mark.parametrize(('center', 'offset', 'expected_sha256'), (
    ((0, 0, 0), 48,
     '96181173751a49af3908013ab834a1287960d0a7ccd8c2ed6ab40aed67d4894f'),
    ((10, -20, 30), 48,
     '560c65b5047eaf86ed78ef7afe987acf8cd26616109d99b5708f7f5ee925ef0e'),
    ((3.5, -4.25, 8), 48,
     'da9042bcf0a51975e233e644c345cbe93d5a047414ca220e6b1e0c652127b081'),
    ((-1.25, 2.5, -5.75), -.5,
     '9a5017112b232c90b6409b755bb3ac5ad07470f29987670cc409255707a7b388'),
))
def test_light_manager_secondary_query_descriptor_matches_native_oracle(
        center, offset, expected_sha256):
    sphere = np.asarray((*center, offset), dtype=np.float32)
    result = build_light_manager_secondary_query_descriptor(sphere)
    assert isinstance(result, LightManagerSecondaryQueryDescriptor)
    assert result.logical_planes.shape == (16, 4)
    assert result.packed_planes.shape == (4, 4, 4)
    assert result.packed_planes.dtype == np.dtype('<f4')
    assert result.packed_planes.nbytes == 0x100
    unpacked = result.packed_planes.transpose(0, 2, 1).reshape(16, 4)
    assert np.array_equal(unpacked.view('<u4'), result.logical_planes.view('<u4'))
    assert hashlib.sha256(result.packed_planes.tobytes()).hexdigest() == (
        expected_sha256)


@pytest.mark.parametrize(('base_planes', 'edge_points', 'expected_sha256'), (
    (
        ((1, 0, 0, -2), (-1, 0, 0, -3), (0, 1, 0, -4),
         (0, -1, 0, -5), (0, 0, 1, -6), (0, 0, -1, -7)),
        ((.5, 1, -2), (2, -1, 3), (-3, .25, 1.5), (4, 2, -.5),
         (-2, 3, 1), (1, -4, 2.5), (3.5, 1, -3), (-1.5, -2, 4)),
        'cc9ad52ca74286dbda5df64df362f26bfa41334a36227b82040023d1ed99cc49',
    ),
    (
        ((.25, -.5, .75, 1), (-1.25, .125, .5, -2),
         (.5, .75, -.25, 3), (-.75, .5, 1.25, -4),
         (1.5, -1, .25, 5), (-.5, -1.5, .875, -6)),
        ((1.25, -2.5, 3.75), (-4.5, 5.25, -6.125),
         (7.5, -8.25, 9.125), (-10.5, 11.25, -12.125),
         (13.5, -14.25, 15.125), (-16.5, 17.25, -18.125),
         (19.5, -20.25, 21.125), (-22.5, 23.25, -24.125)),
        'e9752e64b97c01a5e8fda417d49e992b4b0fb9b243427d81c8ba7cc0a8452e59',
    ),
))
def test_light_manager_primary_query_base_descriptor_matches_native_oracle(
        base_planes, edge_points, expected_sha256):
    result = build_light_manager_primary_query_base_descriptor(
        base_planes, edge_points)
    assert isinstance(result, LightManagerPrimaryQueryDescriptor)
    assert result.logical_planes.shape == (16, 4)
    assert result.packed_planes.shape == (4, 4, 4)
    assert result.packed_planes.nbytes == 0x100
    assert np.array_equal(
        result.packed_planes.transpose(0, 2, 1).reshape(16, 4).view('<u4'),
        result.logical_planes.view('<u4'))
    assert hashlib.sha256(result.packed_planes.tobytes()).hexdigest() == (
        expected_sha256)



@pytest.mark.parametrize(
    ('axis_extents', 'translation', 'expected_sha256'),
    (
        (
            ((1, 0, 0, 2), (0, 1, 0, 3), (0, 0, 1, 4)),
            (10, 20, 30),
            'efd410498490ff902f9cf49714bf1e7c70b08d0ac50a67065bb3271923028d96',
        ),
        (
            ((0, 1, 0, 2.5), (-1, 0, 0, 3.5), (0, 0, 1, 4.5)),
            (1.25, -2.5, 3.75),
            '84bbbf374e73eb09f7ba53dcbcf284cc193d823b7e6de69ac67a5c056ace9294',
        ),
        (
            ((1, 2, 3, 4), (-2, 1, .5, 5), (.25, -.75, 2, 6)),
            (7, -8, 9),
            'f30ab43e527b4f5dcdf1ec251e8d57b0799a3be1edb0e7d331b6dc44d87b424b',
        ),
        (
            ((0, 0, 0, 2), (1, 0, 0, 3), (-1, 0, 0, 4)),
            (.5, -.25, 1),
            '27b16ea074900e566619ddfe65c8d5fa0e6be63389ee0961fd4a0b095fc73017',
        ),
    ),
)
def test_light_manager_primary_query_alternate_descriptor_matches_native_oracle(
        axis_extents, translation, expected_sha256):
    result = build_light_manager_primary_query_alternate_descriptor(
        axis_extents, translation)
    assert isinstance(result, LightManagerPrimaryQueryAlternateDescriptor)
    assert result.logical_planes.shape == (16, 4)
    assert result.packed_planes.shape == (4, 4, 4)
    assert result.packed_planes.nbytes == 0x100
    assert np.array_equal(
        result.packed_planes.transpose(0, 2, 1).reshape(16, 4).view('<u4'),
        result.logical_planes.view('<u4'))
    assert hashlib.sha256(result.packed_planes.tobytes()).hexdigest() == (
        expected_sha256)


@pytest.mark.parametrize(('enabled', 'tail_planes', 'expected_sha256'), (
    (False, (), '47152acd46478e4a00474eca08c87984780bfa01d2822432351c710976475238'),
    (True, (), '6f02861b345d9bad12a2904eebdc675adc032551e59da8ed4c3895b02318e5fe'),
    (True, ((1.25, -2.5, 3.75, -4.125),),
     '0f01a1065a7e4d7f4660d17c7054d6cdacdfa231b0cb782cb6ad559d4b22250a'),
    (True, ((1.25, -2.5, 3.75, -4.125),
            (-5.5, 6.25, -7.75, 8.5)),
     '525442071be7c55c9c352556f7ec29a5c51d2c969156c93585506747cf895824'),
))
def test_light_manager_primary_query_override_matches_native_oracle(
        enabled, tail_planes, expected_sha256):
    initial = (
        np.arange(64, dtype=np.float32).reshape(16, 4) / np.float32(7))
    inputs = LightManagerPrimaryQueryOverrideInputs(
        enabled=enabled,
        origin=(1, -2, 3),
        center=(10, -20, 30),
        axis_offset=(2, 3, 4),
        extents=(5, 6, 7),
        terminal_normal=(.25, -.5, .75),
        tail_planes=tail_planes,
    )
    result = apply_light_manager_primary_query_override(initial, inputs)
    assert isinstance(result, LightManagerPrimaryQueryOverride)
    assert result.logical_planes.shape == (16, 4)
    assert result.packed_planes.shape == (4, 4, 4)
    assert result.packed_planes.nbytes == 0x100
    assert hashlib.sha256(result.packed_planes.tobytes()).hexdigest() == (
        expected_sha256)
    if not enabled:
        assert np.array_equal(
            result.logical_planes.view('<u4'), initial.view('<u4'))


def test_light_manager_occlusion_query_matches_wrapper_obb_preprocessing():
    matrix = np.asarray([
        [2, 3, 5, 7], [11, 13, 17, 19],
        [23, 29, 31, 37], [41, 43, 47, 53],
    ], np.float32)
    source = manager_candidate(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        local_bound_center=(.5, -2, 3),
        occlusion_half_extents=(2, .25, 4))
    query = build_light_manager_occlusion_query(source)

    assert np.asarray(query.world_center, np.float32).view('<u4').tolist() == \
        np.asarray((89, 105.5, 108.5, 129.5), np.float32).view('<u4').tolist()
    assert np.asarray(query.half_axis_x, np.float32).view('<u4').tolist() == \
        np.asarray((4, 6, 10, 14), np.float32).view('<u4').tolist()
    assert np.asarray(query.half_axis_y, np.float32).view('<u4').tolist() == \
        np.asarray((2.75, 3.25, 4.25, 4.75), np.float32).view('<u4').tolist()
    assert np.asarray(query.half_axis_z, np.float32).view('<u4').tolist() == \
        np.asarray((92, 116, 124, 148), np.float32).view('<u4').tolist()
    assert np.float32(query.depth_bias).view('<u4') == \
        np.float32(.01).view('<u4')


def _manager_hierarchy_inputs(base_depth):
    base = np.asarray(base_depth, dtype='<i2')
    levels = [base]
    while levels[-1].shape != (1, 1):
        previous = levels[-1]
        levels.append(previous.reshape(
            previous.shape[0] // 2, 2,
            previous.shape[1] // 2, 2).max(axis=(1, 3)))
    query = LightManagerOcclusionQuery(
        world_center=(0, 0, 10, 0),
        half_axis_x=(1, 0, 0, 0),
        half_axis_y=(0, 1, 0, 0),
        half_axis_z=(0, 0, 1, 0),
        depth_bias=.01,
    )
    snapshot = LightManagerHierarchicalDepthSnapshot(
        base_width=16,
        camera_position=(0, 0, 0, 0),
        projection_rows=(
            (.1, 0, 0, 0),
            (0, .1, 0, 0),
            (0, 0, .1, 0),
            (0, 0, 1, 1),
        ),
        depth_cap=100,
        distance_scale=1,
        near_threshold=0,
        depth_scale=1000,
        screen_scale=(8, 8, 8, 8),
        screen_maximum=(15, 15, 15, 15),
        screen_bias=(8, 8, 8, 8),
        depth_levels=tuple(levels),
    )
    return query, snapshot


@pytest.mark.parametrize(('depth', 'visible', 'reason'), (
    (8000, False, 'coarse_corners'),
    (8990, True, 'base_corners'),
    (9000, True, 'base_corners'),
))
def test_light_manager_hierarchical_depth_matches_native_uniform_cases(
        depth, visible, reason):
    query, snapshot = _manager_hierarchy_inputs(
        np.full((16, 16), depth, dtype='<i2'))
    result = evaluate_light_manager_hierarchical_depth(query, snapshot)
    assert result.visible is visible
    assert result.reason == reason
    assert result.pixel_bounds == (7, 7, 8, 8)
    assert result.query_depth == 8990
    assert result.selected_mip_level == (0 if not visible else None)


def test_light_manager_hierarchical_depth_matches_fractional_native_case():
    query, snapshot = _manager_hierarchy_inputs(
        np.full((16, 16), 8000, dtype='<i2'))
    query = replace(
        query,
        world_center=(1.5, -.5, 10.25, 0),
        half_axis_x=(1.25, 0, 0, 0),
        half_axis_y=(0, .75, 0, 0),
        half_axis_z=(0, 0, 1.5, 0))
    result = evaluate_light_manager_hierarchical_depth(query, snapshot)
    assert result.visible is False
    assert result.reason == 'coarse_corners'
    assert result.pixel_bounds == (8, 7, 10, 8)
    assert result.query_depth == 8743
    assert result.initial_mip_level == 1
    assert result.selected_mip_level == 1

def test_light_manager_hierarchical_depth_scans_base_after_coarse_hit():
    base = np.full((16, 16), 1000, dtype='<i2')
    base[8, 8] = 9000
    query, snapshot = _manager_hierarchy_inputs(base)
    query = replace(
        query,
        half_axis_x=(6, 0, 0, 0),
        half_axis_y=(0, 6, 0, 0))
    result = evaluate_light_manager_hierarchical_depth(query, snapshot)
    assert result.visible is True
    assert result.reason == 'base_scan_visible'
    assert result.pixel_bounds == (3, 3, 12, 12)
    assert result.query_depth == 8990
    assert result.selected_mip_level == 3


def test_light_manager_hierarchical_depth_uses_supplied_coarse_levels():
    base = np.full((16, 16), 1000, dtype='<i2')
    base[8, 8] = 9000
    query, snapshot = _manager_hierarchy_inputs(base)
    query = replace(
        query,
        half_axis_x=(6, 0, 0, 0),
        half_axis_y=(0, 6, 0, 0))
    inconsistent = replace(
        snapshot,
        depth_levels=(
            base,
            np.full((8, 8), 1000, dtype='<i2'),
            np.full((4, 4), 1000, dtype='<i2'),
            np.full((2, 2), 1000, dtype='<i2'),
            np.full((1, 1), 1000, dtype='<i2'),
        ))
    result = evaluate_light_manager_hierarchical_depth(query, inconsistent)
    assert result.visible is False
    assert result.reason == 'coarse_corners'
    assert result.selected_mip_level == 3


def test_light_manager_hierarchical_depth_keeps_near_boundary_visible():
    query, snapshot = _manager_hierarchy_inputs(
        np.zeros((16, 16), dtype='<i2'))
    result = evaluate_light_manager_hierarchical_depth(
        query, replace(snapshot, near_threshold=10))
    assert result.visible is True
    assert result.reason == 'near_or_camera_boundary'
    assert result.pixel_bounds is None
    assert result.query_depth is None
    assert result.selected_mip_level is None

def test_light_manager_occlusion_query_requires_source_half_extents():
    with pytest.raises(ValueError, match='occlusion half extents'):
        build_light_manager_occlusion_query(manager_candidate())


def test_light_manager_primary_query_refinement_preserves_source_order():
    logical_planes = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
        (0, 0, 1, 1), (0, 0, -1, 1),
        *((0, 0, 0, 4),) * 10,
    ], dtype=np.float32)
    packed_planes = logical_planes.reshape(4, 4, 4).transpose(0, 2, 1).copy()

    def translated_source(x, extent):
        matrix = np.eye(4, dtype=np.float32)
        matrix[3, 0] = np.float32(x)
        return manager_candidate(
            transform_matrix=tuple(tuple(float(value) for value in row)
                                   for row in matrix),
            occlusion_half_extents=(extent, extent, extent))

    inside = translated_source(0, .25)
    outside = translated_source(1.5, .4)
    touching = translated_source(1.5, .5)
    assert light_manager_primary_query_source_visible(inside, packed_planes)
    assert not light_manager_primary_query_source_visible(outside, packed_planes)
    assert light_manager_primary_query_source_visible(touching, packed_planes)

    retained = filter_light_manager_primary_query_sources(
        (inside, outside, touching), packed_planes)
    assert len(retained) == 2
    assert retained[0] is inside
    assert retained[1] is touching


def test_light_manager_optional_query_refinement_excludes_strict_interior():
    logical_primary = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
        (0, 0, 1, 1), (0, 0, -1, 1),
        *((0, 0, 0, 4),) * 10,
    ], dtype=np.float32)
    packed_primary = logical_primary.reshape(4, 4, 4).transpose(0, 2, 1).copy()
    optional = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
    ], dtype=np.float32).T.copy()

    def translated_source(x, extent):
        matrix = np.eye(4, dtype=np.float32)
        matrix[3, 0] = np.float32(x)
        return manager_candidate(
            transform_matrix=tuple(tuple(float(value) for value in row)
                                   for row in matrix),
            occlusion_half_extents=(extent, extent, extent))

    interior = translated_source(0, .25)
    crosses_optional = translated_source(.9, .2)
    wide = translated_source(0, 1.25)
    outside_primary = translated_source(1.5, .1)
    assert not light_manager_optional_query_source_visible(
        interior, packed_primary, optional)
    assert light_manager_optional_query_source_visible(
        crosses_optional, packed_primary, optional)
    assert light_manager_optional_query_source_visible(
        wide, packed_primary, optional)
    assert not light_manager_optional_query_source_visible(
        outside_primary, packed_primary, optional)

    retained = filter_light_manager_optional_query_sources(
        (interior, crosses_optional, outside_primary, wide),
        packed_primary, optional)
    assert len(retained) == 2
    assert retained[0] is crosses_optional
    assert retained[1] is wide


def test_light_manager_spatial_bound_packing_and_admissibility():
    packed = pack_light_manager_spatial_bound((1, -1.5, .25, .5))
    assert packed.center == (2, -3, 1)
    assert packed.radius == 2

    limit = pack_light_manager_spatial_bound(
        (16384, -16384, 16383.5, 20000))
    assert limit.center == (-32768, -32768, 32767)
    assert limit.radius == 32767

    assert light_manager_spatial_bound_admissible(
        (16384, -16384, 0, 16383.9990234375))
    assert not light_manager_spatial_bound_admissible(
        (16384.001953125, 0, 0, 1))
    assert not light_manager_spatial_bound_admissible(
        (0, 0, 0, 16384))

    with pytest.raises(ValueError, match='center/radius float4'):
        pack_light_manager_spatial_bound((0, 0, 0))
    with pytest.raises(ValueError, match='center/radius float4'):
        light_manager_spatial_bound_admissible((0, 0, 0, np.nan))


def test_light_manager_spatial_entry_decode_and_cell_bound_rebuild():
    raw = struct.pack('<HHI4h', 0x00f0, 0, 9, -8, 12, 0, 5)
    decoded = decode_light_manager_spatial_entry(raw)
    assert decoded == LightManagerSpatialEntry(
        selection_mask=0x00f0,
        source_index=9,
        packed_bound=LightManagerSpatialPackedBound((-8, 12, 0), 5),
    )

    entries = (
        LightManagerSpatialEntry(
            0x0001, 3, LightManagerSpatialPackedBound((2, 4, 6), 2)),
        decoded,
    )
    rebuilt = rebuild_light_manager_spatial_cell_bound(
        entries, state_byte=0xc5)
    assert rebuilt.center == (-2.25, 4.75, .75)
    assert rebuilt.half_extents == (4.25, 3.75, 3.25)
    assert rebuilt.radius_weight == 11
    assert rebuilt.state_byte == 0x45

    logical = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
        (0, 0, 1, 1), (0, 0, -1, 1),
        *((0, 0, 0, 4),) * 10,
    ], dtype=np.float32)
    planes = logical.reshape(4, 4, 4).transpose(0, 2, 1).copy()
    direct = classify_light_manager_spatial_packed_sphere(
        LightManagerSpatialEntry(
            1, 4, LightManagerSpatialPackedBound((0, 0, 0), 1)),
        planes, query_mask=1, required_mask=1)
    assert direct.mask_matches and direct.intersects and direct.center_inside
    ambiguous = classify_light_manager_spatial_packed_sphere(
        LightManagerSpatialEntry(
            1, 4, LightManagerSpatialPackedBound((3, 0, 0), 1)),
        planes, query_mask=1, required_mask=1)
    assert ambiguous.mask_matches and ambiguous.intersects
    assert not ambiguous.center_inside
    rejected = classify_light_manager_spatial_packed_sphere(
        decoded, planes, query_mask=1, required_mask=1)
    assert not rejected.mask_matches and not rejected.intersects

    with pytest.raises(ValueError, match='exactly 16 bytes'):
        decode_light_manager_spatial_entry(raw[:-1])
    with pytest.raises(ValueError, match='state byte'):
        rebuild_light_manager_spatial_cell_bound(entries, state_byte=256)


def test_light_manager_spatial_optional_packed_sphere_states():
    primary_logical = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
        (0, 0, 1, 1), (0, 0, -1, 1),
        *((0, 0, 0, 4),) * 10,
    ], dtype=np.float32)
    primary = primary_logical.reshape(
        4, 4, 4).transpose(0, 2, 1).copy()
    entry = LightManagerSpatialEntry(
        1, 4, LightManagerSpatialPackedBound((0, 0, 0), 1))

    def optional(offset):
        logical = np.asarray([
            (1, 0, 0, offset),
            (0, 0, 0, 4),
            (0, 0, 0, 4),
            (0, 0, 0, 4),
        ], dtype=np.float32)
        return logical.transpose(1, 0).copy()

    direct = classify_light_manager_spatial_optional_packed_sphere(
        entry, primary, optional(-.25), query_mask=1, required_mask=1)
    assert direct.mask_matches and direct.survives_coarse and direct.direct
    ambiguous = classify_light_manager_spatial_optional_packed_sphere(
        entry, primary, optional(.25), query_mask=1, required_mask=1)
    assert ambiguous.mask_matches and ambiguous.survives_coarse
    assert not ambiguous.direct
    rejected = classify_light_manager_spatial_optional_packed_sphere(
        entry, primary, optional(1), query_mask=1, required_mask=1)
    assert rejected.mask_matches and not rejected.survives_coarse
    assert not rejected.direct


def test_light_manager_spatial_optional_page_and_resolution():
    primary_logical = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
        (0, 0, 1, 1), (0, 0, -1, 1),
        *((0, 0, 0, 4),) * 10,
    ], dtype=np.float32)
    primary = primary_logical.reshape(
        4, 4, 4).transpose(0, 2, 1).copy()
    optional_logical = np.asarray([
        (1, 0, 0, .25),
        (0, 0, 0, 4),
        (0, 0, 0, 4),
        (0, 0, 0, 4),
    ], dtype=np.float32)
    optional = optional_logical.transpose(1, 0).copy()

    entries = (
        LightManagerSpatialEntry(
            1, 10, LightManagerSpatialPackedBound((-2, 0, 0), 1)),
        LightManagerSpatialEntry(
            1, 11, LightManagerSpatialPackedBound((0, 0, 0), 1)),
        LightManagerSpatialEntry(
            1, 12, LightManagerSpatialPackedBound((2, 0, 0), 1)),
    )
    pages = (
        LightManagerSpatialPage(-1, -1, 4, 1, 0, entries),
    )
    buckets = classify_light_manager_spatial_optional_page_chain(
        pages, 0, primary, optional, query_mask=1, required_mask=1)
    assert buckets == LightManagerSpatialOptionalQueryBuckets(
        (10,), (11,), (0,))

    sources = {
        10: manager_candidate(),
        11: manager_candidate(occlusion_half_extents=(.5, .1, .1)),
    }
    assert resolve_light_manager_spatial_optional_query_indices(
        buckets, sources, primary, optional) == (10, 11)
    assert resolve_light_manager_spatial_optional_query_indices(
        buckets, sources, primary, optional, capacity=1) == (10,)


def test_light_manager_spatial_page_decode_and_primary_buckets():
    def entry(mask, source_index, packed):
        return struct.pack('<HHI4h', mask, 0, source_index, *packed)

    newest_raw = (
        struct.pack('<iihhhh', 1, -1, 4, 3, 1, 0)
        + entry(1, 10, (0, 0, 0, 1))
        + entry(1, 11, (3, 0, 0, 1))
        + entry(2, 12, (0, 0, 0, 1))
    ).ljust(0x100, b'\0')
    older_raw = (
        struct.pack('<iihhhh', -1, 0, 4, 1, 1, 0)
        + entry(1, 13, (2, 0, 0, 1))
    ).ljust(0x100, b'\0')
    pages = (
        decode_light_manager_spatial_page(newest_raw),
        decode_light_manager_spatial_page(older_raw),
    )
    assert pages[0].older_page == 1
    assert pages[1].newer_page == 0
    assert [item.source_index for item in pages[0].entries] == [10, 11, 12]

    logical = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
        (0, 0, 1, 1), (0, 0, -1, 1),
        *((0, 0, 0, 4),) * 10,
    ], dtype=np.float32)
    planes = logical.reshape(4, 4, 4).transpose(0, 2, 1).copy()
    buckets = classify_light_manager_spatial_primary_page_chain(
        pages, 0, planes, query_mask=1, required_mask=1)
    assert buckets.direct_source_indices == (10, 13)
    assert buckets.refinement_source_indices == (11,)
    assert buckets.visited_page_indices == (0, 1)

    contained = classify_light_manager_spatial_primary_page_chain(
        pages, 0, planes, cell_fully_inside=True,
        query_mask=1, required_mask=1)
    assert contained.direct_source_indices == (10, 11, 13)
    assert contained.refinement_source_indices == ()

    cyclic = (
        LightManagerSpatialPage(
            0, -1, 4, 1, 0, pages[0].entries[:1]),
    )
    with pytest.raises(ValueError, match='cycle'):
        classify_light_manager_spatial_primary_page_chain(
            cyclic, 0, planes, query_mask=1, required_mask=1)
    with pytest.raises(ValueError, match='exactly 256 bytes'):
        decode_light_manager_spatial_page(newest_raw[:-1])


def test_light_manager_spatial_primary_bucket_resolution():
    logical = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
        (0, 0, 1, 1), (0, 0, -1, 1),
        *((0, 0, 0, 4),) * 10,
    ], dtype=np.float32)
    planes = logical.reshape(4, 4, 4).transpose(0, 2, 1).copy()
    outside_matrix = np.eye(4, dtype=np.float32)
    outside_matrix[3, 0] = 10
    sources = {
        10: manager_candidate(),
        13: manager_candidate(),
        11: manager_candidate(occlusion_half_extents=(.1, .1, .1)),
        12: manager_candidate(
            transform_matrix=tuple(
                tuple(float(value) for value in row)
                for row in outside_matrix),
            occlusion_half_extents=(.1, .1, .1),
        ),
    }
    buckets = LightManagerSpatialPrimaryQueryBuckets(
        (10, 13), (11, 12), (0, 1))
    assert resolve_light_manager_spatial_primary_query_indices(
        buckets, sources, planes) == (10, 13, 11)
    assert resolve_light_manager_spatial_primary_query_indices(
        buckets, sources, planes, capacity=2) == (10, 13)

    with pytest.raises(ValueError, match='lacks index'):
        resolve_light_manager_spatial_primary_query_indices(
            LightManagerSpatialPrimaryQueryBuckets(
                (10,), (99,), (0,)),
            sources, planes)
    with pytest.raises(ValueError, match='intermediate worker flushes'):
        resolve_light_manager_spatial_primary_query_indices(
            LightManagerSpatialPrimaryQueryBuckets(
                tuple(range(1010)), (), (0,)),
            sources, planes)


def test_light_manager_spatial_primary_page_query_flush_order():
    logical = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
        (0, 0, 1, 1), (0, 0, -1, 1),
        *((0, 0, 0, 4),) * 10,
    ], dtype=np.float32)
    planes = logical.reshape(4, 4, 4).transpose(0, 2, 1).copy()
    pages = []
    source_by_index = {}
    ambiguous_indices = []
    direct_indices = []
    candidate = manager_candidate(occlusion_half_extents=(.1, .1, .1))

    for page_index in range(68):
        entries = []
        for slot in range(15):
            source_index = page_index * 15 + slot
            ambiguous_indices.append(source_index)
            source_by_index[source_index] = candidate
            entries.append(LightManagerSpatialEntry(
                1, source_index,
                LightManagerSpatialPackedBound((3, 0, 0), 1)))
        pages.append(LightManagerSpatialPage(
            page_index + 1, page_index - 1, 4, 1, 0, tuple(entries)))
    for local_page in range(68):
        page_index = 68 + local_page
        entries = []
        for slot in range(15):
            source_index = 10000 + local_page * 15 + slot
            direct_indices.append(source_index)
            source_by_index[source_index] = candidate
            entries.append(LightManagerSpatialEntry(
                1, source_index,
                LightManagerSpatialPackedBound((0, 0, 0), 1)))
        older_page = page_index + 1 if local_page < 67 else -1
        pages.append(LightManagerSpatialPage(
            older_page, page_index - 1, 4, 1, 0, tuple(entries)))

    result = resolve_light_manager_spatial_primary_page_query_indices(
        pages, 0, source_by_index, planes,
        query_mask=1, required_mask=1)
    assert isinstance(result, LightManagerSpatialPageQueryResolution)
    assert result.source_indices == (
        tuple(ambiguous_indices) + tuple(direct_indices))
    assert result.visited_page_indices == tuple(range(136))
    assert result.flushes == (
        LightManagerSpatialWorkerFlush(
            'primary_refinement', 1020, 1020, 1020, False),
        LightManagerSpatialWorkerFlush(
            'direct', 1020, 1020, 1020, False),
    )


def test_light_manager_spatial_optional_page_query_final_order_and_capacity():
    primary_logical = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
        (0, 0, 1, 1), (0, 0, -1, 1),
        *((0, 0, 0, 4),) * 10,
    ], dtype=np.float32)
    primary = primary_logical.reshape(
        4, 4, 4).transpose(0, 2, 1).copy()
    optional = np.asarray([
        (1, 0, 0, .25),
        (0, 0, 0, 4),
        (0, 0, 0, 4),
        (0, 0, 0, 4),
    ], dtype=np.float32).transpose(1, 0).copy()
    page = LightManagerSpatialPage(
        -1, -1, 4, 1, 0,
        (
            LightManagerSpatialEntry(
                1, 11, LightManagerSpatialPackedBound((0, 0, 0), 1)),
            LightManagerSpatialEntry(
                1, 10, LightManagerSpatialPackedBound((-2, 0, 0), 1)),
        ),
    )
    sources = {
        10: manager_candidate(),
        11: manager_candidate(occlusion_half_extents=(.5, .1, .1)),
    }
    result = resolve_light_manager_spatial_optional_page_query_indices(
        (page,), 0, sources, primary, optional,
        query_mask=1, required_mask=1, capacity=1)
    assert result.source_indices == (10,)
    assert result.visited_page_indices == (0,)
    assert result.flushes == (
        LightManagerSpatialWorkerFlush('direct', 1, 1, 1, True),
        LightManagerSpatialWorkerFlush(
            'optional_refinement', 1, 1, 0, True),
    )

def test_light_manager_spatial_cell_classification_and_batch_order():
    logical = np.asarray([
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
        (0, 0, 1, 1), (0, 0, -1, 1),
        *((0, 0, 0, 4),) * 10,
    ], dtype=np.float32)
    packed = logical.reshape(4, 4, 4).transpose(0, 2, 1).copy()
    inside = LightManagerSpatialAabb((0, 0, 0), (.25, .25, .25))
    crossing = LightManagerSpatialAabb((.9, 0, 0), (.2, .2, .2))
    outside = LightManagerSpatialAabb((1.5, 0, 0), (.4, .4, .4))

    assert classify_light_manager_spatial_aabb(
        inside, packed).intersects
    assert classify_light_manager_spatial_aabb(
        inside, packed).fully_inside
    assert classify_light_manager_spatial_aabb(
        crossing, packed).intersects
    assert not classify_light_manager_spatial_aabb(
        crossing, packed).fully_inside
    outside_result = classify_light_manager_spatial_aabb(outside, packed)
    assert not outside_result.intersects
    assert not outside_result.fully_inside
    assert select_light_manager_spatial_aabb_indices(
        (inside, outside, crossing), packed) == (0, 2)

    obb_logical = np.concatenate(
        (logical[:6], logical[:6], logical[:4]), axis=0)
    obb_packed = obb_logical.reshape(4, 4, 4).transpose(0, 2, 1).copy()

    axes = np.asarray([
        (1, 0, 0, .2), (0, 1, 0, .2), (0, 0, 1, .2),
    ], dtype=np.float32)
    crossing_obb = classify_light_manager_spatial_query_obb(
        axes, (.8, 0, 0), obb_packed)
    assert crossing_obb.intersects
    assert not crossing_obb.covers_query

    covering_axes = np.asarray([
        (1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1),
    ], dtype=np.float32)
    exact_cover = classify_light_manager_spatial_query_obb(
        covering_axes, (0, 0, 0), obb_packed)
    assert exact_cover.intersects
    assert exact_cover.covers_query

    threshold_axes = np.asarray([
        (1, 0, 0, 1.5), (0, 1, 0, 1.5), (0, 0, 1, 1.5),
    ], dtype=np.float32)
    assert classify_light_manager_spatial_query_obb(
        threshold_axes, (.5, 0, 0), obb_packed).covers_query
    assert not classify_light_manager_spatial_query_obb(
        threshold_axes, (.51, 0, 0), obb_packed).covers_query

    outside_obb = classify_light_manager_spatial_query_obb(
        axes, (1.5, 0, 0), obb_packed)
    assert not outside_obb.intersects
    assert not outside_obb.covers_query
    assert light_manager_spatial_query_obb_intersects(
        axes, (.8, 0, 0), obb_packed)
    assert not light_manager_spatial_query_obb_intersects(
        axes, (1.5, 0, 0), obb_packed)


def test_light_manager_spatial_cell_classification_validates_inputs():
    packed = np.zeros((4, 4, 4), dtype=np.float32)
    with pytest.raises(ValueError, match='LightManagerSpatialAabb'):
        classify_light_manager_spatial_aabb(object(), packed)
    with pytest.raises(ValueError, match='nonnegative'):
        classify_light_manager_spatial_aabb(
            LightManagerSpatialAabb((0, 0, 0), (-1, 1, 1)), packed)
    with pytest.raises(ValueError, match='cell values'):
        select_light_manager_spatial_aabb_indices((object(),), packed)
    with pytest.raises(ValueError, match='shape'):
        light_manager_spatial_query_obb_intersects(
            np.zeros((4, 4)), (0, 0, 0), packed)


def test_light_manager_primary_query_refinement_validates_inputs():
    source = manager_candidate(occlusion_half_extents=(1, 1, 1))
    packed_planes = np.zeros((4, 4, 4), dtype=np.float32)
    with pytest.raises(ValueError, match='shape'):
        light_manager_primary_query_source_visible(source, np.zeros((16, 4)))
    packed_planes[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match='finite'):
        light_manager_primary_query_source_visible(source, packed_planes)
    with pytest.raises(ValueError, match='candidate-source'):
        filter_light_manager_primary_query_sources((source, object()), packed_planes)
    with pytest.raises(ValueError, match='shape'):
        light_manager_optional_query_source_visible(
            source, np.zeros((4, 4, 4)), np.zeros((16, 4)))
    with pytest.raises(ValueError, match='candidate-source'):
        filter_light_manager_optional_query_sources(
            (object(),), np.zeros((4, 4, 4)), np.zeros((4, 4)))


def test_light_manager_resource_version_matches_raw_crc_and_cache_gate():
    matrix = np.arange(16, dtype=np.float32).reshape(4, 4)
    source = manager_candidate(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        light_type=1, bound_extents=(2, 4, 3), bound_radius_scale=.5,
        occlusion_half_extents=(7, 8, 9))
    shape = LightManagerResourceShapeInputs(
        parameter_0x120=10, parameter_0x124=11, parameter_0x128=12,
        parameter_0x12c=13, parameter_0x130=14, parameter_0x134=15,
        resolved_resource_version=0x12345678)

    def raw_crc(data, seed):
        return zlib.crc32(data, seed ^ 0xffffffff) ^ 0xffffffff

    expected = raw_crc(matrix.astype('<f4').tobytes(), 0xedb88320)
    expected = raw_crc(struct.pack('<I', 0x12345678), expected)
    for value in (13, 14, 15, 2, 12):
        expected = raw_crc(np.float32(value).tobytes(), expected)
    result = light_manager_resource_version(
        source, shape, global_epoch=7, cached_epoch=6,
        cached_version=0xaaaaaaaa)
    assert result.version == expected
    assert result.recomputed
    assert result.cached_epoch_after == 7
    assert result.cached_version_after == expected

    cached = light_manager_resource_version(
        source, shape, global_epoch=7, cached_epoch=7,
        cached_version=0x89abcdef)
    assert cached.version == 0x89abcdef
    assert not cached.recomputed


@pytest.mark.parametrize(
    ('light_type', 'expected_values'),
    [
        (0, (12,)),
        (2, (13, 14, 15, 2, 10)),
        (3, (7, 8, 9)),
        (4, (7, 8, 9)),
        (5, ()),
    ],
)
def test_light_manager_resource_version_type_payloads(light_type,
                                                       expected_values):
    source = manager_candidate(
        light_type=light_type, bound_extents=(2, 4, 3),
        bound_radius_scale=.5, occlusion_half_extents=(7, 8, 9))
    shape = LightManagerResourceShapeInputs(
        parameter_0x120=10, parameter_0x124=11, parameter_0x128=12,
        parameter_0x12c=13, parameter_0x130=14, parameter_0x134=15)
    expected = zlib.crc32(
        np.eye(4, dtype='<f4').tobytes(), 0xedb88320 ^ 0xffffffff)
    expected ^= 0xffffffff
    payload = (np.asarray(expected_values, dtype='<f4').tobytes()
               if expected_values else b'')
    if payload:
        expected = zlib.crc32(payload, expected ^ 0xffffffff) ^ 0xffffffff
    result = light_manager_resource_version(
        source, shape, global_epoch=2, cached_epoch=1, cached_version=0)
    assert result.version == expected


@pytest.mark.parametrize(
    ('light_type', 'flags', 'builder', 'vector', 'scalars'),
    [
        (0, 0, '0x1410B58B0', (12, 12, 12), None),
        (1, 0, '0x1410B5AE0', None, (10, 12)),
        (2, 0, '0x1410B59C0', None, (12, 10)),
        (3, 0, '0x1410B57F0', (7, 8, 9), None),
        (4, 0, '0x1410B57F0', (7, 8, 9), None),
        (4, 1 << 8, '0x1410B58B0', (7, 8, 9), None),
        (5, 0, None, None, None),
    ],
)
def test_light_manager_resource_refresh_dispatch(light_type, flags, builder,
                                                  vector, scalars):
    source = manager_candidate(
        light_type=light_type, runtime_flags=flags,
        occlusion_half_extents=(7, 8, 9))
    shape = LightManagerResourceShapeInputs(
        parameter_0x120=10, parameter_0x124=11, parameter_0x128=12,
        parameter_0x12c=13, parameter_0x130=14,
        resolved_resource_version=9)
    result = build_light_manager_resource_refresh_dispatch(
        source, shape, computed_version=8, built_version=7,
        generated_vertex_count=0 if builder is None else 5)
    assert result.refresh_required
    assert result.shape_builder == builder
    assert result.shape_vector == vector
    assert result.shape_scalars == scalars
    assert result.stream_allocation_bytes == (None if builder is None else 96)
    assert result.built_version_after == (7 if builder is None else 8)
    assert result.resolved_resource_present
    assert result.common_primary_parameter == (
        11 if light_type == 0 else 13 if light_type in (1, 2) else 0)
    assert result.common_secondary_parameter == (
        14 if light_type in (1, 2) else 0)


def test_light_manager_resource_refresh_zero_and_unchanged_outcomes():
    source = manager_candidate()
    shape = LightManagerResourceShapeInputs()
    zero = build_light_manager_resource_refresh_dispatch(
        source, shape, computed_version=8, built_version=7,
        generated_vertex_count=0)
    assert zero.refresh_required and zero.stream_allocation_bytes is None
    assert zero.built_version_after == 7
    unchanged = build_light_manager_resource_refresh_dispatch(
        source, shape, computed_version=7, built_version=7)
    assert not unchanged.refresh_required and unchanged.shape_builder is None
    assert light_manager_resource_stream_allocation_bytes(1) == 48
    assert light_manager_resource_stream_allocation_bytes(5) == 96


def test_light_manager_static_shape_sources_match_retail_xyz_hashes():
    def digest(vertices):
        return hashlib.sha256(
            np.asarray(vertices, dtype='<f4').tobytes()).hexdigest()

    box = build_light_manager_box_shell_vertices((1, 1, 1))
    rounded = build_light_manager_round_shell_vertices((1, 1, 1))
    assert box.shape == (36, 3)
    assert rounded.shape == (432, 3)
    assert digest(box) == (
        '370038ee81bfc19358e44c233c000edd9822922da18e044d9a8c3849a5f7491b')
    assert digest(rounded) == (
        '8a404348810afe9158aa224133d3b2bfe8d92447efafff96b937c4172df5a89f')
    assert np.array_equal(
        build_light_manager_box_shell_vertices((2, 3, 4)),
        box * np.asarray((2, 3, 4), np.float32))
    assert np.array_equal(
        build_light_manager_round_shell_vertices((2, 3, 4)),
        rounded * np.asarray((2, 3, 4), np.float32))


@pytest.mark.parametrize(
    ('builder', 'distance', 'angle', 'count', 'expected_sha256'),
    [
        (build_light_manager_type_1_shell_vertices, 1, 1, 216,
         '4c17cab574388cd227aa6490b763f3b917c2e3a899b4c341515443fa01b8f3ef'),
        (build_light_manager_type_1_shell_vertices, 2, 3, 216,
         '8d751f14b9961de3e17ef23c7422985cabf54c8952d79316d2828013e8d57d9c'),
        (build_light_manager_type_1_shell_vertices, .5, 5, 216,
         '4e1c478a2576ce4fd0d5e24547dd541bf8fc1495f7d54bd0985ac6f149a62532'),
        (build_light_manager_type_2_shell_vertices, 1, 1, 48,
         'f348e6ede9fd91bf3881f2579eda9848710a2bdde6bb0ec007494a9c910403b6'),
        (build_light_manager_type_2_shell_vertices, 2, 3, 48,
         '9b2a40961e5bf57bf1cc9af05d7898798cbd608a307dacba23090222aa885bea'),
        (build_light_manager_type_2_shell_vertices, .5, 5, 48,
         'a8602e1e4274e3e473d10c061d3c27f629b30fa4aa41bcc41d4f53202006f347'),
    ],
)
def test_light_manager_procedural_shape_sources_match_retail_oracle(
        builder, distance, angle, count, expected_sha256):
    vertices = builder(distance, angle)
    assert vertices.shape == (count, 3)
    assert hashlib.sha256(vertices.astype('<f4').tobytes()).hexdigest() == \
        expected_sha256


def test_light_manager_resource_shell_dispatch_generates_native_streams():
    shape = LightManagerResourceShapeInputs(
        parameter_0x120=1, parameter_0x128=2)
    cases = (
        (manager_candidate(light_type=0),
         build_light_manager_round_shell_vertices((2, 2, 2))),
        (manager_candidate(light_type=1),
         build_light_manager_type_1_shell_vertices(1, 2)),
        (manager_candidate(light_type=2),
         build_light_manager_type_2_shell_vertices(2, 1)),
        (manager_candidate(light_type=3, occlusion_half_extents=(3, 4, 5)),
         build_light_manager_box_shell_vertices((3, 4, 5))),
        (manager_candidate(light_type=4, occlusion_half_extents=(3, 4, 5)),
         build_light_manager_box_shell_vertices((3, 4, 5))),
        (manager_candidate(
            light_type=4, runtime_flags=1 << 8,
            occlusion_half_extents=(3, 4, 5)),
         build_light_manager_round_shell_vertices((3, 4, 5))),
    )
    for source, expected in cases:
        actual = build_light_manager_resource_shell_vertices(source, shape)
        assert np.array_equal(actual.view('<u4'), expected.view('<u4'))
        dispatch = build_light_manager_resource_refresh_dispatch(
            source, shape, computed_version=9, built_version=8,
            generated_vertex_count=len(actual))
        assert dispatch.generated_vertex_count == len(actual)
        assert dispatch.stream_allocation_bytes == \
            light_manager_resource_stream_allocation_bytes(len(actual))

    unsupported = build_light_manager_resource_shell_vertices(
        manager_candidate(light_type=5), shape)
    assert unsupported.shape == (0, 3)


def test_light_manager_resource_shell_applies_explicit_near_clip_plane():
    source = manager_candidate(
        light_type=3, occlusion_half_extents=(1, 2, 3))
    shape = LightManagerResourceShapeInputs()
    uncut = build_light_manager_resource_shell_vertices(source, shape)
    clipped = build_light_manager_resource_shell_vertices(
        source, shape, clip_plane=(0, 0, 1, 0))
    assert np.array_equal(
        clipped.view('<u4'),
        prepare_light_shell_vertices(uncut, (0, 0, 1, 0)).view('<u4'))
    assert len(clipped) > 0 and len(clipped) % 3 == 0


def test_light_manager_shape_sources_reject_invalid_dimensions():
    with pytest.raises(ValueError, match='nonnegative'):
        build_light_manager_box_shell_vertices((1, -1, 1))
    with pytest.raises(ValueError, match='nonnegative'):
        build_light_manager_round_shell_vertices((1, 1, -1))
    with pytest.raises(ValueError, match='nonnegative'):
        build_light_manager_type_1_shell_vertices(-1, 1)
    with pytest.raises(ValueError, match='nonnegative'):
        build_light_manager_type_2_shell_vertices(1, -1)


def test_light_manager_resource_clip_planes_match_retail_oracle():
    def matrix_tuple(value):
        return tuple(tuple(float(item) for item in row)
                     for row in np.asarray(value, np.float32))

    def digest(value):
        return hashlib.sha256(
            np.asarray(value, dtype='<f4').tobytes()).hexdigest()

    identity = np.eye(4, dtype=np.float32)
    source_matrix = np.asarray((
        (0, 1, 0, 0), (-1, 0, 0, 0),
        (0, 0, 1, 0), (10, 20, 30, 1),
    ), np.float32)
    resolved_matrix = np.asarray((
        (1, 0, 0, 0), (0, 0, 1, 0),
        (0, -1, 0, 0), (4, 5, 6, 1),
    ), np.float32)
    fractional_source = np.asarray((
        (.6, .8, 0, 0), (-.8, .6, 0, 0),
        (0, 0, 1, 0), (2.25, -4.5, 6.75, 1),
    ), np.float32)
    fractional_resolved = np.asarray((
        (.6, .8, 0, 0), (-.8, .6, 0, 0),
        (0, 0, 1, 0), (1.25, -2.5, 3.75, 1),
    ), np.float32)
    cases = (
        (manager_candidate(light_type=0),
         LightManagerResourceShapeInputs(parameter_0x124=2),
         '14929f8fc16fcfa1f63dcd208115af9dd3429befbb3b190bd33fd38938cacb81'),
        (manager_candidate(
            light_type=1, transform_matrix=matrix_tuple(source_matrix)),
         LightManagerResourceShapeInputs(
             parameter_0x12c=2, parameter_0x130=3),
         'd3417adccdf4f4f271bd1e410b2218a8eca01f874cea7cdc5c03196dfc4ed4c4'),
        (manager_candidate(light_type=0),
         LightManagerResourceShapeInputs(
             resolved_clip_resource=LightManagerClipResource(
                 matrix_tuple(identity), (2, 3, 4))),
         'd5c779720856d2127cab92345b73909e483cb1cf8f7b2bc5a8d46cb60b86ff67'),
        (manager_candidate(
            light_type=3, transform_matrix=matrix_tuple(source_matrix)),
         LightManagerResourceShapeInputs(
             resolved_clip_resource=LightManagerClipResource(
                 matrix_tuple(resolved_matrix), (2, 3, 4))),
         'bf8daf883d276a8c28ca2d81bd898a36dca8d15ec7ebe36d843a793c9791916b'),
        (manager_candidate(
            light_type=1, transform_matrix=matrix_tuple(fractional_source)),
         LightManagerResourceShapeInputs(
             parameter_0x12c=.35, parameter_0x130=1.25,
             resolved_clip_resource=LightManagerClipResource(
                 matrix_tuple(fractional_resolved), (.7, 1.1, 2.3))),
         'c1fe6c47d30ab5e8b15a4dfc99ab9e02f5ee684a4d732b58848aada62e4d49ec'),
    )
    for source, inputs, expected in cases:
        assert digest(build_light_manager_resource_clip_planes(
            source, inputs)) == expected


def test_light_manager_resource_shell_applies_generated_plane_sequence():
    source = manager_candidate(
        light_type=0, bound_extents=(2, 2, 2))
    inputs = LightManagerResourceShapeInputs(
        parameter_0x124=.5, parameter_0x128=2)
    base = build_light_manager_round_shell_vertices((2, 2, 2))
    actual = build_light_manager_resource_shell_vertices(source, inputs)
    expected = prepare_light_shell_vertices(base, (0, 0, -1, .5))
    assert np.array_equal(actual.view('<u4'), expected.view('<u4'))

    planes = np.asarray(((1, 0, 0, .75), (0, 1, 0, .5)), np.float32)
    explicit = prepare_light_shell_vertices_for_planes(base, planes)
    sequential = prepare_light_shell_vertices(
        prepare_light_shell_vertices(base, planes[0]), planes[1])
    assert np.array_equal(explicit.view('<u4'), sequential.view('<u4'))


def test_light_manager_resource_shell_output_matches_persistent_bounds_contract():
    source = manager_candidate(
        light_type=3, occlusion_half_extents=(2, 3, 4),
        local_bound_center=(5, 6, 7), bound_radius_scale=8,
        bound_extents=(2, 3, 4))
    output = build_light_manager_resource_shell_output(
        source, LightManagerResourceShapeInputs())
    assert output.vertices.shape == (36, 3)
    assert np.array_equal(
        output.local_aabb_minimum, np.asarray((-2, -3, -4), np.float32))
    assert np.array_equal(
        output.local_aabb_maximum, np.asarray((2, 3, 4), np.float32))
    assert np.array_equal(
        output.local_bounding_sphere.view('<u4'),
        np.asarray((0, 0, 0, np.sqrt(np.float32(29))), np.float32).view('<u4'))
    assert output.stream_allocation_bytes == 480
    unit = finalize_light_manager_resource_shell_output(
        source, build_light_manager_box_shell_vertices((1, 1, 1)))
    packed = b''.join(value.astype('<f4').tobytes() for value in (
        unit.vertices,
        np.concatenate((unit.local_aabb_minimum,
                        unit.local_aabb_maximum)),
        unit.local_bounding_sphere,
    ))
    assert hashlib.sha256(packed).hexdigest() == (
        '8bb4642dd793daf9b7688fc23370589dc0f1e5b97b51ea73237699c5833114b7')
    assert not output.source_bounds_update_required
    assert np.array_equal(
        output.source_bound_center_radius_after,
        np.asarray((5, 6, 7, 8), np.float32))

    shrinking = build_light_manager_resource_shell_output(
        manager_candidate(
            light_type=1, bound_extents=(100, 100, 100)),
        LightManagerResourceShapeInputs(
            parameter_0x120=1, parameter_0x128=1))
    assert shrinking.source_bounds_update_required
    assert np.array_equal(
        shrinking.source_bound_center_radius_after.view('<u4'),
        shrinking.local_bounding_sphere.view('<u4'))
    assert np.array_equal(
        shrinking.source_bound_extents_after,
        (shrinking.local_aabb_maximum - shrinking.local_aabb_minimum)
        * np.float32(.5))

    fractional_vertices = np.asarray((
        (-3.25, 2.5, .125), (4.75, -1.5, 2.25),
        (.5, 6.125, -4.5), (2.75, 3.5, 1.25),
        (-1.125, -2.75, 5.5), (3.875, .25, -3.125),
    ), np.float32)
    fractional = finalize_light_manager_resource_shell_output(
        source, fractional_vertices)
    packed = b''.join(value.astype('<f4').tobytes() for value in (
        fractional.vertices,
        np.concatenate((fractional.local_aabb_minimum,
                        fractional.local_aabb_maximum)),
        fractional.local_bounding_sphere,
    ))
    assert hashlib.sha256(packed).hexdigest() == (
        'c9fef54a184c8dec76b4594eb353c328521832d3a97a2a2e9228aea6cb4ffde0')


@pytest.mark.parametrize(
    ('changes', 'options', 'reason'),
    [
        ({'runtime_flags': 0}, {}, 'runtime_flag_2_clear'),
        ({}, {'singleton_restriction_enabled': True,
              'singleton_match': False}, 'singleton_mismatch'),
        ({'runtime_flags': (1 << 2) | (1 << 4)}, {},
         'runtime_flag_4_set'),
        ({'runtime_flags': (1 << 2) | (1 << 18),
          'maximum_camera_distance': 1}, {}, 'maximum_camera_distance'),
        ({'runtime_flags': (1 << 2) | (1 << 19),
          'distance_fade_offset': -1, 'distance_fade_scale': 0}, {},
         'distance_fade_zero'),
        ({'linear_color': (0, 0, 0), 'light_type': 1}, {},
         'nonemissive_non_type_4'),
        ({'light_type': 5}, {}, 'emissive_type_5'),
        ({}, {'view_filter_result': False}, 'view_filter'),
    ],
)
def test_light_manager_candidate_rejection_order(changes, options, reason):
    result = evaluate_light_manager_candidate(
        manager_candidate(**changes), (0, 0, 10), **options)
    assert not result.selected and result.rejection == reason


def test_light_manager_candidate_gates_and_normalizes_flags_exactly():
    flags = 0xe0000000 | (1 << 2) | (1 << 4) | (1 << 18) | (1 << 19)
    source = manager_candidate(
        runtime_flags=flags, maximum_camera_distance=20,
        distance_fade_offset=1, distance_fade_scale=-.05)
    result = evaluate_light_manager_candidate(
        source, (0, 0, 10), bypass_runtime_flag_4_rejection=True,
        view_filter_result=True)
    assert result.selected and result.rejection is None
    assert result.normalized_runtime_flags == flags & 0x1fffffff
    assert np.float32(result.bounding_sphere_distance).view('<u4') == \
        np.float32(7).view('<u4')
    assert np.float32(result.distance_fade).view('<u4') == \
        np.float32(.5).view('<u4')


def test_light_manager_nonemissive_type_4_and_singleton_override_are_selected():
    source = manager_candidate(
        runtime_flags=(1 << 2) | (1 << 4), linear_color=(0, 0, 0),
        light_type=4)
    result = evaluate_light_manager_candidate(
        source, (0, 0, 0), singleton_restriction_enabled=True,
        singleton_match=True, bypass_runtime_flag_4_rejection=True)
    assert result.selected


def test_light_manager_selection_batches_preserve_membership_per_16_sources():
    candidates = [manager_candidate() for _ in range(34)]
    filters = [True] * 34
    for index in (0, 15, 16, 31, 33):
        filters[index] = False
    assert build_light_manager_selection_batches(
        candidates, (0, 0, 0), view_filter_results=filters) == (
            tuple(range(1, 15)), tuple(range(17, 31)), (32,))


def test_light_manager_selection_batches_apply_atomic_completion_order():
    candidates = [manager_candidate() for _ in range(48)]
    filters = [False] * 48
    for index in (1, 3, 32, 47):
        filters[index] = True

    assert build_light_manager_selection_batches(
        candidates, (0, 0, 0), view_filter_results=filters,
        completed_chunk_order=(2, 1, 0)) == ((32, 47), (), (1, 3))


def test_light_manager_selection_batches_reject_invalid_completion_orders():
    candidates = [manager_candidate() for _ in range(17)]
    with pytest.raises(ValueError, match='include every claimed chunk'):
        build_light_manager_selection_batches(
            candidates, (0, 0, 0), completed_chunk_order=(0,))
    with pytest.raises(ValueError, match='must be unique'):
        build_light_manager_selection_batches(
            candidates, (0, 0, 0), completed_chunk_order=(0, 0))
    with pytest.raises(ValueError, match='must be in'):
        build_light_manager_selection_batches(
            candidates, (0, 0, 0), completed_chunk_order=(0, 2))

def test_light_manager_frame_priority_uses_bound_radius_and_one_unit_floor():
    matrix = np.asarray([
        [2, 0, 0, 9], [0, 3, 0, 8], [0, 0, 4, 7], [10, 20, 30, 6],
    ], np.float32)
    source = manager_candidate(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        local_bound_center=(1, 2, 3), bound_radius_scale=.5,
        bound_extents=(2, 4, 6))

    near = light_manager_frame_priority(source, (12, 26, 42))
    far = light_manager_frame_priority(source, (12, 26, 52))
    assert near.view('<u4') == np.float32(3).view('<u4')
    assert far.view('<u4') == np.float32(.3).view('<u4')


def test_light_manager_frame_source_order_ranks_priority_then_appends_deferred():
    def translated(distance, **changes):
        matrix = np.eye(4, dtype=np.float32)
        matrix[3, 0] = distance
        return manager_candidate(
            transform_matrix=tuple(tuple(float(value) for value in row)
                                   for row in matrix),
            **changes)

    candidates = (
        translated(10, bound_extents=(2, 1, 1)),
        translated(0, light_type=0, special_allocation_class=3),
        translated(100),
        translated(4, bound_extents=(2, 1, 1),
                   special_allocation_class=3),
    )
    result = build_light_manager_frame_source_order(
        candidates, (0, 0, 0), priority_indices=(0, 1, 3),
        deferred_indices=(2,))

    assert isinstance(result, LightManagerFrameSourceOrder)
    assert result.priority_indices == (1, 3, 0)
    assert result.deferred_indices == (2,)
    assert result.frame_indices == (1, 3, 0, 2)
    np.testing.assert_array_equal(
        np.asarray(result.priority_scores, np.float32),
        np.asarray((3, .5, .2), np.float32))
    assert result.weighted_allocation_count == 8
    assert result.special_allocation_count == 2
    assert result.equal_score_groups == ()


def test_light_manager_frame_source_order_surfaces_equal_score_groups():
    candidates = tuple(manager_candidate() for _ in range(3))
    result = build_light_manager_frame_source_order(
        candidates, (0, 0, 10), priority_indices=(2, 0, 1),
        deferred_indices=(), count_special_allocation_class_3=False)
    assert result.priority_indices == (2, 0, 1)
    assert result.equal_score_groups == ((2, 0, 1),)
    assert result.special_allocation_count == 0


@pytest.mark.parametrize(('scores', 'expected_indices'), (
    ([1] * 6, tuple(range(6))),
    ([1] * 7, (3, 1, 2, 0, 4, 5, 6)),
    ([1] * 8, (7, 1, 2, 3, 4, 5, 6, 0)),
    (
        [2, 1, 3, 2, 2, 1, 3, 3, 2, 1, 1, 3, 2, 3, 1, 2, 3],
        (6, 7, 16, 11, 2, 13, 8, 3, 4, 0, 12, 15, 1, 5, 14, 10, 9),
    ),
    (
        [2 if index % 2 else 1 for index in range(41)],
        (5, 11, 23, 3, 25, 13, 27, 7, 29, 15, 31, 1, 33, 17, 35, 9,
         37, 19, 39, 21, 0, 40, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20,
         22, 24, 26, 28, 30, 32, 34, 36, 38),
    ),
))
def test_light_manager_frame_source_order_matches_native_equal_score_permutations(
        scores, expected_indices):
    candidates = tuple(
        manager_candidate(bound_extents=(score, score, score))
        for score in scores)
    result = build_light_manager_frame_source_order(
        candidates, (0, 0, 0), priority_indices=range(len(candidates)),
        deferred_indices=())

    assert result.priority_indices == expected_indices
    assert result.frame_indices == expected_indices
    expected_groups = []
    start = 0
    while start < len(expected_indices):
        score = scores[expected_indices[start]]
        end = start + 1
        while end < len(expected_indices) and scores[expected_indices[end]] == score:
            end += 1
        if end - start > 1:
            expected_groups.append(expected_indices[start:end])
        start = end
    assert result.equal_score_groups == tuple(expected_groups)

def test_light_manager_frame_source_order_rejects_overlaps_and_native_overflow():
    candidates = tuple(manager_candidate() for _ in range(513))
    with pytest.raises(ValueError, match='must be disjoint'):
        build_light_manager_frame_source_order(
            candidates[:2], (0, 0, 0), priority_indices=(0,),
            deferred_indices=(0,))
    with pytest.raises(ValueError, match='native 512 cap'):
        build_light_manager_frame_source_order(
            candidates, (0, 0, 0), priority_indices=range(513),
            deferred_indices=())


def test_light_manager_secondary_distance_and_merge_reproduce_flags_and_order():
    def translated(distance, **changes):
        matrix = np.eye(4, dtype=np.float32)
        matrix[3, 0] = distance
        return manager_candidate(
            transform_matrix=tuple(tuple(float(value) for value in row)
                                   for row in matrix),
            **changes)

    candidates = (
        translated(0),
        translated(2),
        translated(1, runtime_flags=(1 << 2) | (1 << 4)),
        translated(3),
    )
    assert light_manager_secondary_distance_squared(
        candidates[3], (0, 0, 0)).view('<u4') == np.float32(9).view('<u4')

    result = build_light_manager_secondary_merge(
        candidates, (0, 0, 0), primary_indices=(0,),
        secondary_indices=(3, 0, 2, 1), secondary_layer_bit=1)
    assert isinstance(result, LightManagerSecondaryMerge)
    assert result.eligible_secondary_indices == (0, 1, 3)
    assert result.processed_secondary_indices == (0, 1, 3)
    assert result.merged_indices == (0, 1, 3)
    assert result.appended_secondary_indices == (1, 3)
    assert result.duplicate_secondary_indices == (0,)
    assert result.runtime_flag_updates == (
        (0, (1 << 2) | (1 << 29) | (1 << 31)),
        (1, (1 << 2) | (1 << 29) | (1 << 30)),
        (3, (1 << 2) | (1 << 29) | (1 << 30)),
    )
    assert result.equal_distance_groups == ()


def test_light_manager_secondary_merge_stops_before_mutation_at_512_cap():
    candidates = tuple(manager_candidate() for _ in range(513))
    result = build_light_manager_secondary_merge(
        candidates, (0, 0, 0), primary_indices=range(512),
        secondary_indices=(512,), secondary_layer_bit=1)
    assert len(result.merged_indices) == 512
    assert result.eligible_secondary_indices == (512,)
    assert result.processed_secondary_indices == ()
    assert result.runtime_flag_updates == ()


def test_light_manager_runtime_flag_21_distance_gate_is_strict_at_radius():
    matrix = np.eye(4, dtype=np.float32)
    matrix[3, :3] = (3, 4, 0)
    source = manager_candidate(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        runtime_flags=(1 << 2) | (1 << 21),
        bound_extents=(4, 2, 1), priority_distance_padding=4)

    assert not light_manager_runtime_flag_21_defer(source, (0, 0, 0))
    assert light_manager_runtime_flag_21_defer(
        replace(source, priority_distance_padding=np.float32(3.999)),
        (0, 0, 0))

    decision = evaluate_light_manager_frame_partition(
        replace(source, priority_distance_padding=np.float32(3.999)),
        frame_layer_bit=1, manager_reference_position=(0, 0, 0))
    assert decision.membership == 'deferred'
    assert decision.reason == 'runtime_flag_21_gate'


def test_light_manager_resource_readiness_walks_source_to_root_in_order():
    ready = (
        LightManagerResourceReadinessNode(0, 1),
        LightManagerResourceReadinessNode(0, 0),
        LightManagerResourceReadinessNode(0, 5),
    )
    assert light_manager_resource_chain_ready(ready)
    assert not light_manager_resource_chain_ready(
        ready + (LightManagerResourceReadinessNode(0x20, 1),))
    assert not light_manager_resource_chain_ready((
        LightManagerResourceReadinessNode(0, 0, 1),))
    assert not light_manager_resource_chain_ready((
        LightManagerResourceReadinessNode(0, 5, 1),))
    assert light_manager_resource_chain_ready((
        LightManagerResourceReadinessNode(0, 3, 1),))

    decision = evaluate_light_manager_frame_partition(
        manager_candidate(), frame_layer_bit=1,
        callback_inputs=LightManagerPartitionInputs(
            resource_ready_result=True,
            resource_readiness_chain=(
                LightManagerResourceReadinessNode(0x40, 1),)))
    assert decision.membership == 'skipped'
    assert decision.reason == 'resource_not_ready'


def test_light_manager_object_visibility_follows_resolved_handle_chain():
    node = LightManagerObjectVisibilityNode
    assert light_manager_object_visibility((node(0, 5, None),), 1)
    assert light_manager_object_visibility((
        node(1 << 11, 5, 1), node(0, 1)), 1)
    assert not light_manager_object_visibility((
        node(1 << 11, 5, 2), node(0, 1)), 1)
    assert light_manager_object_visibility((node(1 << 11, 1),), 1)

    decision = evaluate_light_manager_frame_partition(
        manager_candidate(resource_flags=1 << 11), frame_layer_bit=1,
        callback_inputs=LightManagerPartitionInputs(
            object_visibility_result=True, object_visibility_mask=1,
            object_visibility_chain=(node(1 << 11, 5, 2),)))
    assert decision.membership == 'skipped'
    assert decision.reason == 'object_visibility'


def test_light_manager_type_resource_requires_generation_and_type_2():
    entry = LightManagerTypeResourceEntry
    table = LightManagerTypeResourceTable((
        entry(0x12, 2), entry(0x34, 1), None))
    assert light_manager_type_resource_available(0x12000000, table)
    assert not light_manager_type_resource_available(0x13000000, table)
    assert not light_manager_type_resource_available(0x34000001, table)
    assert not light_manager_type_resource_available(0x12000002, table)
    assert not light_manager_type_resource_available(0, table)

    decision = evaluate_light_manager_frame_partition(
        manager_candidate(
            light_type=3, has_auxiliary_resource=True,
            auxiliary_resource_count=1),
        frame_layer_bit=1,
        callback_inputs=LightManagerPartitionInputs(
            type_resource_available=True,
            type_resource_handle=0x34000001,
            type_resource_table=table,
            auxiliary_volume_result=False))
    assert decision.membership == 'priority'


def test_light_manager_auxiliary_volume_ands_plane_signs_across_vertices():
    matrix = np.eye(4, dtype=np.float32)
    planes = np.zeros((16, 4), dtype=np.float32)
    planes[:, 3] = 1
    point = np.zeros((1, 3), dtype=np.float32)
    assert light_manager_auxiliary_volume_visible(planes, matrix, point)

    outside = planes.copy()
    outside[0, 3] = -1
    assert not light_manager_auxiliary_volume_visible(
        outside, matrix, point)

    straddling = planes.copy()
    straddling[0] = (1, 0, 0, 0)
    vertices = np.asarray(((-1, 0, 0), (1, 0, 0)), np.float32)
    assert light_manager_auxiliary_volume_visible(
        straddling, matrix, vertices)

    decision = evaluate_light_manager_frame_partition(
        manager_candidate(
            has_auxiliary_resource=True, auxiliary_resource_count=2),
        frame_layer_bit=1,
        callback_inputs=LightManagerPartitionInputs(
            auxiliary_volume_result=False,
            auxiliary_volume_plane_coefficients=straddling,
            auxiliary_volume_vertices=vertices))
    assert decision.membership == 'priority'


@pytest.mark.parametrize(
    ('changes', 'inputs', 'require_flag_16', 'membership', 'reason'),
    [
        ({'resource_flags': 1 << 11},
         {'object_visibility_result': False}, False,
         'skipped', 'object_visibility'),
        ({}, {'resource_ready_result': False}, False,
         'skipped', 'resource_not_ready'),
        ({'selection_layer_mask': 0}, {}, False,
         'skipped', 'selection_layer_mask'),
        ({'has_auxiliary_resource': True, 'auxiliary_resource_count': 1},
         {'auxiliary_volume_result': False}, False,
         'skipped', 'auxiliary_volume'),
        ({'runtime_flags': (1 << 2) | (1 << 31),
          'has_auxiliary_resource': True, 'auxiliary_resource_count': 1},
         {'auxiliary_volume_result': False}, False,
         'priority', None),
        ({'light_type': 3, 'has_auxiliary_resource': True,
          'auxiliary_resource_count': 1},
         {'type_resource_available': False,
          'auxiliary_volume_result': False}, False,
         'priority', None),
        ({'priority_class': 0}, {}, False,
         'deferred', 'priority_class_zero'),
        ({'priority_layer_mask': 0}, {}, False,
         'deferred', 'priority_layer_mask'),
        ({}, {}, True, 'deferred', 'runtime_flag_16_clear'),
        ({'runtime_flags': (1 << 2) | (1 << 16)}, {}, True,
         'priority', None),
        ({'runtime_flags': (1 << 2) | (1 << 21)},
         {'runtime_flag_21_defer_result': True}, False,
         'deferred', 'runtime_flag_21_gate'),
        ({}, {}, False, 'priority', None),
    ],
)
def test_light_manager_frame_partition_gate_order(
        changes, inputs, require_flag_16, membership, reason):
    decision = evaluate_light_manager_frame_partition(
        manager_candidate(**changes), frame_layer_bit=1,
        callback_inputs=LightManagerPartitionInputs(**inputs),
        require_runtime_flag_16_for_priority=require_flag_16)
    assert decision.membership == membership
    assert decision.reason == reason


def test_light_manager_frame_partition_preserves_each_membership_order():
    candidates = (
        manager_candidate(priority_class=0),
        manager_candidate(),
        manager_candidate(resource_flags=1 << 11),
        manager_candidate(priority_layer_mask=0),
    )
    inputs = (
        LightManagerPartitionInputs(),
        LightManagerPartitionInputs(),
        LightManagerPartitionInputs(object_visibility_result=False),
        LightManagerPartitionInputs(),
    )
    result = build_light_manager_frame_partition(
        candidates, (2, 0, 3, 1), frame_layer_bit=1,
        callback_inputs=(inputs[2], inputs[0], inputs[3], inputs[1]))
    assert isinstance(result, LightManagerFramePartition)
    assert result.priority_indices == (1,)
    assert result.deferred_indices == (0, 3)
    assert result.skipped_indices == (2,)
    assert tuple((index, decision.membership)
                 for index, decision in result.decisions) == (
                     (2, 'skipped'), (0, 'deferred'),
                     (3, 'deferred'), (1, 'priority'))


def test_projected_shadow_map_constructor_normalizes_atlas_and_texel_scale():
    matrix = np.arange(16, dtype=np.float32).reshape(4, 4)
    source = LightProjectedShadowMapSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        atlas_allocation=LightAtlasAllocationWords(8, 16, 32, 64),
        shadow_texel_numerator=128,
        fade=.75,
    )
    record = build_projected_shadow_map_light_volume_record(source)

    np.testing.assert_array_equal(record['transform_matrix'], matrix)
    np.testing.assert_array_equal(
        record['atlas_coordinates'], (8 / 8192, 16 / 8192, 32 / 8192, 32 / 8192))
    assert record['fade'] == np.float32(.75)
    assert record['shadow_texel_scale'] == np.float32(2)
    assert not np.any(np.frombuffer(record.tobytes()[80:92], np.uint8))
    assert not np.any(np.frombuffer(record.tobytes()[96:108], np.uint8))
    assert not np.any(np.frombuffer(record.tobytes()[112:], np.uint8))


def test_projected_shadow_map_constructor_zeroes_nonpositive_divisor():
    source = LightProjectedShadowMapSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in np.eye(4, dtype=np.float32)),
        atlas_allocation=LightAtlasAllocationWords(0, 0, 0, 0),
        shadow_texel_numerator=128,
    )
    record = build_projected_shadow_map_light_volume_record(source)
    assert record['shadow_texel_scale'] == np.float32(0)


def test_point_shadow_map_constructor_reproduces_face_fallback_and_average():
    allocations = (
        LightAtlasAllocationWords(0, 0, 0, 99),
        LightAtlasAllocationWords(1, 2, 8, 16),
        LightAtlasAllocationWords(3, 4, 16, 32),
        LightAtlasAllocationWords(5, 6, 24, 48),
        LightAtlasAllocationWords(7, 8, 32, 64),
        LightAtlasAllocationWords(9, 10, 40, 80),
    )
    source = LightPointShadowMapSource(
        face_atlas_allocations=allocations,
        projection_tail=(20, 21, 22, 23),
        shadow_texel_numerator=48,
        fade=.5,
    )
    record = build_point_shadow_map_light_volume_record(source)
    expected_pairs = [(1 / 8192, 1 / 8192)]
    expected_pairs.extend(
        (word_0 + size / 8192, word_2 + size / 8192)
        for word_0, word_2, size in (
            (1, 2, 8), (3, 4, 16), (5, 6, 24),
            (7, 8, 32), (9, 10, 40)))
    expected = np.empty(16, dtype=np.float32)
    expected[:12] = np.asarray(expected_pairs, np.float32).reshape(-1)
    expected[12:] = (20, 21, 22, 23)

    np.testing.assert_array_equal(
        record['transform_matrix'], expected.reshape(4, 4))
    assert not np.any(record['atlas_coordinates'])
    assert record['fade'] == np.float32(.5)
    assert record['shadow_texel_scale'] == np.float32(1)


def test_point_shadow_map_native_source_flows_through_subtype_1_allocator():
    source = LightPointShadowMapSource(
        face_atlas_allocations=(LightAtlasAllocationWords(1, 2, 8, 16),) * 6,
        projection_tail=(1, 2, 3, 4),
        shadow_texel_numerator=32,
    )
    result = build_light_gpu_subtype_1_record(
        captured_light_zero_source(), z_bin_scale=1,
        auxiliary=LightGpuSubtype1AuxiliarySources(
            shadow_map_volumes=(source,)),
        first_volume_index=9, volume_capacity=10)

    assert int(result.light['shadow_map_info']) == 0x00010009
    np.testing.assert_array_equal(
        result.appended_volumes[0],
        build_point_shadow_map_light_volume_record(source))


def test_shadow_map_constructors_reject_invalid_descriptor_shapes_and_words():
    with pytest.raises(ValueError, match='exactly six'):
        build_point_shadow_map_light_volume_record(LightPointShadowMapSource(
            face_atlas_allocations=(), projection_tail=(0, 0, 0, 0),
            shadow_texel_numerator=1))
    with pytest.raises(ValueError, match='word 4'):
        build_projected_shadow_map_light_volume_record(
            LightProjectedShadowMapSource(
                transform_matrix=tuple(tuple(float(value) for value in row)
                                       for row in np.eye(4, dtype=np.float32)),
                atlas_allocation=LightAtlasAllocationWords(0, 0, 0x10000, 1),
                shadow_texel_numerator=1))


def test_shadow_volume_native_source_flows_through_subtype_1_allocator():
    source = LightShadowVolumeSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in np.eye(4, dtype=np.float32)),
        falloff_negative=(1, 2, 3), shadow_texel_scale=4,
        atlas_origin_texels=(8, -4), atlas_size_words=(16, 32),
        misc=5, fade=6,
    )
    result = build_light_gpu_subtype_1_record(
        captured_light_zero_source(), z_bin_scale=1,
        auxiliary=LightGpuSubtype1AuxiliarySources(shadow_volumes=(source,)),
        first_volume_index=7, volume_capacity=8)

    assert int(result.light['shadow_volume_info']) == 0x00010007
    assert result.next_volume_index == 8
    assert result.skipped_volume_count == 0
    np.testing.assert_array_equal(
        result.appended_volumes[0],
        build_shadow_volume_light_volume_record(source))


@pytest.mark.parametrize(
    ('changes', 'message'),
    [
        ({'atlas_origin_texels': (-0x8001, 0)}, 'X origin'),
        ({'atlas_origin_texels': (0, 0x8000)}, 'Y origin'),
        ({'atlas_size_words': (-1, 1)}, 'X size word'),
        ({'atlas_size_words': (1, 0x10000)}, 'Y size word'),
        ({'atlas_size_words': (1.5, 2)}, 'integer'),
    ],
)
def test_shadow_volume_constructor_rejects_out_of_range_words(changes, message):
    fields = {
        'transform_matrix': tuple(tuple(float(value) for value in row)
                                  for row in np.eye(4, dtype=np.float32)),
        'falloff_negative': (1, 2, 3),
        'shadow_texel_scale': 4,
        'atlas_origin_texels': (0, 0),
        'atlas_size_words': (1, 1),
    }
    fields.update(changes)
    with pytest.raises(ValueError, match=message):
        build_shadow_volume_light_volume_record(LightShadowVolumeSource(**fields))


def test_subtype_1_auxiliary_allocator_preserves_native_order_and_ranges():
    auxiliary = LightGpuSubtype1AuxiliarySources(
        clip_volume=auxiliary_volume_source(100),
        gobo_volume=auxiliary_volume_source(200),
        shadow_map_volumes=(
            auxiliary_volume_source(300), auxiliary_volume_source(400)),
        shadow_volumes=(
            auxiliary_volume_source(500), auxiliary_volume_source(600)),
    )
    result = build_light_gpu_subtype_1_record(
        captured_light_zero_source(), z_bin_scale=1.0,
        auxiliary=auxiliary, first_volume_index=5, volume_capacity=20)

    assert result.next_volume_index == 11
    assert result.skipped_volume_count == 0
    assert len(result.appended_volumes) == 6
    assert int(result.light['clip_volume_info']) == 0x00010005
    assert int(result.light['mod_id_and_gobo_id']) == 0x0006FFFF
    assert int(result.light['shadow_map_info']) == 0x00020007
    assert int(result.light['shadow_volume_info']) == 0x00020009
    assert [float(record['fade']) for record in result.appended_volumes] == [
        123.0, 223.0, 323.0, 423.0, 523.0, 623.0]


def test_subtype_1_auxiliary_allocator_reproduces_capacity_skips():
    auxiliary = LightGpuSubtype1AuxiliarySources(
        clip_volume=auxiliary_volume_source(100),
        gobo_volume=auxiliary_volume_source(200),
        shadow_map_volumes=(auxiliary_volume_source(300),),
        shadow_volumes=(auxiliary_volume_source(400),),
    )
    result = build_light_gpu_subtype_1_record(
        captured_light_zero_source(), z_bin_scale=1.0,
        auxiliary=auxiliary, first_volume_index=3, volume_capacity=5)

    assert result.next_volume_index == 5
    assert result.skipped_volume_count == 2
    assert len(result.appended_volumes) == 2
    assert int(result.light['clip_volume_info']) == 0x00010003
    assert int(result.light['mod_id_and_gobo_id']) == 0x0004FFFF
    assert int(result.light['shadow_map_info']) == 0
    assert int(result.light['shadow_volume_info']) == 0


def test_subtype_1_auxiliary_allocator_rejects_invalid_boundaries():
    source = captured_light_zero_source()
    with pytest.raises(ValueError, match='at most three shadow maps'):
        build_light_gpu_subtype_1_record(
            source, z_bin_scale=1.0,
            auxiliary=LightGpuSubtype1AuxiliarySources(
                shadow_map_volumes=(auxiliary_volume_source(),) * 4))
    with pytest.raises(ValueError, match='0 <= first <= capacity'):
        build_light_gpu_subtype_1_record(
            source, z_bin_scale=1.0, first_volume_index=2,
            volume_capacity=1)


def test_subtype_3_packer_applies_native_position_marker_and_auxiliary_order():
    clip_source = LightSubtype3ClipVolumeSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in np.eye(4, dtype=np.float32)),
        axis_scale=(1, 1, 1))
    gobo_source = LightGoboVolumeSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in np.eye(4, dtype=np.float32)),
        atlas_origin_texels=(2, 4), atlas_size_words=(8, 0x8010))
    source = captured_light_zero_source(
        light_subtype=3, world_axis_z=(.25, -.5, 1),
        world_position=(100, 200, 300), cone_parameters=(9, 10))
    result = build_light_gpu_subtype_3_record(
        source, z_bin_scale=1,
        auxiliary=LightGpuSubtype3AuxiliarySources(
            clip_volume=auxiliary_volume_source(100),
            subtype_3_clip_volume=clip_source,
            gobo_volume=gobo_source,
            shadow_map_volumes=(auxiliary_volume_source(200),),
            shadow_volumes=(auxiliary_volume_source(300),)),
        first_volume_index=5, volume_capacity=20)

    np.testing.assert_array_equal(
        result.light['world_position'], (-7900, 16200, -31700))
    assert result.light['inverse_attenuation_radius'].view('<u4') == 3
    np.testing.assert_array_equal(result.light['cone_parameters'], (0, 1))
    assert int(result.light['clip_volume_info']) == 0x00020005
    assert int(result.light['mod_id_and_gobo_id']) == 0x0007ffff
    assert int(result.light['shadow_map_info']) == 0x00010008
    assert int(result.light['shadow_volume_info']) == 0x00010009
    assert int(result.light['bit_flags_vfog']) & 0xffff == (1 << 3) | (1 << 5)
    assert result.next_volume_index == 10
    assert result.skipped_volume_count == 0
    np.testing.assert_array_equal(
        result.appended_volumes[1],
        build_subtype_3_clip_light_volume_record(clip_source))


def test_subtype_3_packer_preserves_capacity_skips_and_clip_flag():
    clip_source = LightSubtype3ClipVolumeSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in np.eye(4, dtype=np.float32)),
        axis_scale=(1, 1, 1))
    result = build_light_gpu_subtype_3_record(
        captured_light_zero_source(light_subtype=3), z_bin_scale=1,
        auxiliary=LightGpuSubtype3AuxiliarySources(
            clip_volume=auxiliary_volume_source(),
            subtype_3_clip_volume=clip_source,
            gobo_volume=auxiliary_volume_source()),
        first_volume_index=4, volume_capacity=5)

    assert len(result.appended_volumes) == 1
    assert result.skipped_volume_count == 2
    assert int(result.light['clip_volume_info']) == 0x00010004
    assert not int(result.light['bit_flags_vfog']) & (1 << 3)
    assert int(result.light['mod_id_and_gobo_id']) == 0xffffffff


def test_subtype_3_packer_requires_native_subtype_and_extra_clip():
    clip_source = LightSubtype3ClipVolumeSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in np.eye(4, dtype=np.float32)),
        axis_scale=(1, 1, 1))
    with pytest.raises(ValueError, match='subtype 3'):
        build_light_gpu_subtype_3_record(
            captured_light_zero_source(), z_bin_scale=1,
            auxiliary=LightGpuSubtype3AuxiliarySources(
                subtype_3_clip_volume=clip_source))


def test_subtype_4_packer_rewrites_inverse_color_and_final_reference():
    source = LightGpuBaseSource(
        world_axis_x=(2, 0, 0), world_axis_y=(0, 4, 0),
        world_axis_z=(0, 0, 8), world_position=(10, 20, 40),
        attenuation_radius=10, linear_color=(2, 3, 4),
        specular_intensity=.5, cone_parameters=(9, 10),
        cut_on_depth=1, cut_off_depth=9,
        z_bin_min_depth=2, z_bin_max_depth=4,
        reciprocal_cone_sine=-1, bulb_radius=.2, bulb_length=.4,
        bulb_push_forward=.1, volumetric_fog=.5,
        radiance_mode=2, light_subtype=4)
    color = LightColorVolumeSource(
        dimensions=(2, 4, 8), negative_falloff_distances=(1, 2, 4),
        positive_falloff_distances=(4, 8, 16), fade=.75)
    result = build_light_gpu_subtype_4_record(
        source, z_bin_scale=1,
        auxiliary=LightGpuSubtype4AuxiliarySources(
            color_volume=color,
            clip_volume=auxiliary_volume_source(100),
            gobo_volume=auxiliary_volume_source(200),
            shadow_map_volumes=(auxiliary_volume_source(300),),
            shadow_volumes=(auxiliary_volume_source(400),)),
        first_volume_index=5, volume_capacity=20)

    np.testing.assert_array_equal(result.light['world_axis_x'], (.5, 0, 0))
    np.testing.assert_array_equal(result.light['world_axis_y'], (0, .25, 0))
    np.testing.assert_array_equal(result.light['world_axis_z'], (0, 0, .125))
    np.testing.assert_array_equal(result.light['world_position'], (-5, -5, -5))
    np.testing.assert_array_equal(result.light['linear_color'], (2, 3, 4))
    np.testing.assert_array_equal(result.light['cone_parameters'], (0, 1))
    assert int(result.light['clip_volume_info']) == 0x00010005
    assert int(result.light['mod_id_and_gobo_id']) == 0x00060009
    assert int(result.light['shadow_map_info']) == 0x00010007
    assert int(result.light['shadow_volume_info']) == 0x00010008
    assert int(result.light['bit_flags_vfog']) & 0xffff == 1 << 1
    assert result.next_volume_index == 10
    assert result.skipped_volume_count == 0
    np.testing.assert_array_equal(
        result.appended_volumes[-1], build_color_light_volume_record(color))


def test_subtype_4_packer_uses_flag_103_color_volume_mode():
    source = captured_light_zero_source(light_subtype=4, flag_103_bit0=True)
    color = LightColorVolumeSource(
        dimensions=(2, 4, 8), negative_falloff_distances=(1, 2, 4),
        positive_falloff_distances=(4, 8, 16), fade=.75)
    result = build_light_gpu_subtype_4_record(
        source, z_bin_scale=1,
        auxiliary=LightGpuSubtype4AuxiliarySources(color_volume=color))

    expected = build_color_light_volume_record(replace(
        color, reciprocal_dimensions=True))
    np.testing.assert_array_equal(result.appended_volumes[0], expected)
    assert int(result.light['bit_flags_vfog']) & 0xffff == (1 << 1) | (1 << 2)


def test_subtype_4_capacity_skip_preserves_common_record_without_rewrite():
    source = captured_light_zero_source(light_subtype=4, radiance_mode=2)
    color = LightColorVolumeSource(
        dimensions=(2, 4, 8), negative_falloff_distances=(1, 2, 4),
        positive_falloff_distances=(4, 8, 16))
    result = build_light_gpu_subtype_4_record(
        source, z_bin_scale=1,
        auxiliary=LightGpuSubtype4AuxiliarySources(
            color_volume=color, clip_volume=auxiliary_volume_source()),
        first_volume_index=4, volume_capacity=5)

    assert len(result.appended_volumes) == 1
    assert result.skipped_volume_count == 1
    assert int(result.light['clip_volume_info']) == 0x00010004
    assert int(result.light['mod_id_and_gobo_id']) == 0xffffffff
    assert not int(result.light['bit_flags_vfog']) & (1 << 1)
    np.testing.assert_array_equal(
        result.light['world_axis_x'], source.world_axis_x)
    np.testing.assert_array_equal(
        result.light['linear_color'],
        np.asarray(source.linear_color, np.float32) * np.float32(1 / 1024))


@pytest.mark.parametrize(
    ('changes', 'message'),
    [
        ({'light_subtype': 4}, 'captured subtype 1'),
        ({'base_bit_flags': 0x10000}, 'low 16 bits'),
        ({'z_bin_max_depth': 65535}, 'fit uint16'),
    ],
)
def test_light_gpu_base_packer_rejects_unimplemented_or_invalid_paths(
        changes, message):
    with pytest.raises(ValueError, match=message):
        build_light_gpu_base_record(
            captured_light_zero_source(**changes), z_bin_scale=1)


def test_light_volume_layout_matches_shader_reflection():
    assert LIGHT_VOLUME_GPU_DTYPE.itemsize == 128
    assert LIGHT_VOLUME_GPU_DTYPE.fields['transform_matrix'][1] == 0
    assert LIGHT_VOLUME_GPU_DTYPE.fields['atlas_coordinates'][1] == 64
    assert LIGHT_VOLUME_GPU_DTYPE.fields['extents'][1] == 80
    assert LIGHT_VOLUME_GPU_DTYPE.fields['falloff_negative'][1] == 96
    assert LIGHT_VOLUME_GPU_DTYPE.fields['falloff_positive'][1] == 112
    raw = np.arange(32, dtype='<f4').tobytes()
    record = parse_light_volume_gpu_records(raw)[0]
    np.testing.assert_array_equal(record['transform_matrix'], np.arange(16).reshape(4, 4))
    np.testing.assert_array_equal(record['falloff_positive'], [28, 29, 30])


def test_light_shell_cbuffer_layout_matches_shader_reflection():
    assert LIGHT_SHELL_CBUFFER_DTYPE.itemsize == 96
    assert LIGHT_SHELL_CBUFFER_DTYPE.fields['object_to_world'][1] == 0
    assert LIGHT_SHELL_CBUFFER_DTYPE.fields['aabb_center'][1] == 64
    assert LIGHT_SHELL_CBUFFER_DTYPE.fields['light_gpu_id'][1] == 76
    assert LIGHT_SHELL_CBUFFER_DTYPE.fields['aabb_inverse_extents'][1] == 80
    assert LIGHT_SHELL_CBUFFER_DTYPE.fields['vertex_push_scale'][1] == 92
    raw = bytearray(96)
    struct.pack_into('<16f', raw, 0, *np.eye(4, dtype=np.float32).ravel())
    struct.pack_into('<3fI3ff', raw, 64, 1, 2, 3, 17, 4, 5, 6, .25)
    record = parse_light_shell_constants(raw)
    np.testing.assert_array_equal(record['object_to_world'], np.eye(4))
    np.testing.assert_array_equal(record['aabb_center'], [1, 2, 3])
    assert int(record['light_gpu_id']) == 17
    assert float(record['vertex_push_scale']) == .25
    with pytest.raises(ValueError, match='exactly one'):
        parse_light_shell_constants(bytes(192))


def test_light_shell_manager_builder_matches_executable_field_order_and_clamp():
    matrix = np.eye(4, dtype=np.float32)
    matrix[0, 0], matrix[1, 1], matrix[2, 2] = 2, 3, 4
    matrix[3, :3] = [10, 20, 30]
    placement = LightShellPlacement(
        vertices=np.asarray([
            [-1, -1, 0], [1, -1, 0], [0, 1, 0],
        ], np.float32),
        object_to_world=matrix,
        local_aabb_minimum=np.asarray([-1, 2, 5], np.float32),
        local_aabb_maximum=np.asarray([3, 2.001, 9], np.float32),
    )
    constants = build_light_shell_constants(
        placement, 37, vertex_push_scale=np.float32(.006054521072655916),
    )
    assert constants.tobytes()[:64] == matrix.tobytes()
    midpoint = np.asarray([1, np.float32(2.001 + 2) * np.float32(.5), 7], np.float32)
    expected_center = midpoint @ matrix[:3, :3] + matrix[3, :3]
    np.testing.assert_allclose(constants['aabb_center'], expected_center, rtol=0, atol=2e-6)
    np.testing.assert_allclose(constants['aabb_inverse_extents'], [.5, 1000, .5], rtol=0, atol=.125)
    assert int(constants['light_gpu_id']) == 37
    assert constants['vertex_push_scale'].view('<u4') == np.float32(
        .006054521072655916).view('<u4')

    with pytest.raises(ValueError, match='triangles'):
        build_light_shell_constants(
            LightShellPlacement(np.zeros((4, 3)), matrix, [-1] * 3, [1] * 3),
            0, vertex_push_scale=0,
        )


def test_light_shell_preparation_clips_and_caps_one_closed_convex_stream():
    from core.probe_lookup import LIGHT_SHELL_BOX_VERTICES

    source = np.asarray(LIGHT_SHELL_BOX_VERTICES, np.float32)
    prepared = prepare_light_shell_vertices(source, [0, 0, 1, 0])
    assert prepared.shape == (60, 3)
    assert np.all(prepared[:, 2] >= 0)

    triangles = prepared.reshape(-1, 3, 3)
    cap = triangles[np.all(triangles[:, :, 2] == 0, axis=1)]
    assert len(cap) == 6
    assert np.all(np.cross(
        cap[:, 1] - cap[:, 0], cap[:, 2] - cap[:, 0],
    )[:, 2] < 0)

    # Every undirected edge is paired, including the generated cap.
    edges = {}
    for triangle in triangles:
        for first, second in ((0, 1), (1, 2), (2, 0)):
            edge = tuple(sorted((tuple(triangle[first]), tuple(triangle[second]))))
            edges[edge] = edges.get(edge, 0) + 1
    assert set(edges.values()) == {2}

    np.testing.assert_array_equal(
        prepare_light_shell_vertices(source, [0, 0, 1, -2]),
        np.empty((0, 3), np.float32),
    )
    np.testing.assert_array_equal(
        prepare_light_shell_vertices(source, [0, 0, 1, 2]), source,
    )


def test_light_shell_near_plane_reproduces_static_overlap_and_expansion_order():
    rows = np.eye(4, dtype=np.float32)[:3]
    plane = build_light_shell_near_clip_plane(
        [0, 0, .5], 1, [0, 0, 0], .1, rows,
    )
    assert plane is not None
    np.testing.assert_array_equal(
        plane.view('<u4'),
        np.asarray([0, 0, 0x3F800000, np.float32(-.101).view('<u4')], '<u4'),
    )
    assert build_light_shell_near_clip_plane(
        [0, 0, 2], 1, [0, 0, 0], .1, rows,
    ) is None

    transformed_rows = rows.copy()
    transformed_rows[:, 3] = [.5, -.25, 2]
    transformed = build_light_shell_near_clip_plane(
        [0, 0, .5], 1, [0, 0, 0], .1, transformed_rows,
    )
    expected_w = np.float32(-.101)
    np.testing.assert_array_equal(
        transformed,
        np.asarray([
            np.float32(expected_w * np.float32(.5)),
            np.float32(expected_w * np.float32(-.25)),
            np.float32(expected_w * np.float32(2) + np.float32(1)),
            expected_w,
        ], np.float32),
    )


def shell_constants(**fields):
    records = np.zeros(1, dtype=LIGHT_SHELL_CBUFFER_DTYPE)
    record = records[0]
    record['object_to_world'] = fields.pop(
        'object_to_world', np.eye(4, dtype=np.float32))
    record['aabb_center'] = fields.pop('aabb_center', (0, 0, 0))
    record['aabb_inverse_extents'] = fields.pop(
        'aabb_inverse_extents', (1, 1, 1))
    record['light_gpu_id'] = fields.pop('light_gpu_id', 7)
    record['vertex_push_scale'] = fields.pop('vertex_push_scale', .1)
    assert not fields
    return record


def test_light_shell_projection_push_near_fallback_and_clamp_variant():
    vertices = np.array(((1, 0, -1), (0, 1, 1)), np.float32)
    view = np.eye(4, dtype=np.float32)
    regular = project_light_shell_vertices(
        vertices, shell_constants(), view, view, near_clip=.5)
    np.testing.assert_allclose(
        regular.clip_positions,
        [[1 + .1 / np.sqrt(2), 0, -1 - .1 / np.sqrt(2), 1],
         [0, 1 + .1 / np.sqrt(2), 1 + .1 / np.sqrt(2), 1]],
        rtol=0, atol=1e-7)
    assert regular.encoded_light_id == 7.5

    fallback = project_light_shell_vertices(
        vertices[:1], shell_constants(), view, view, near_clip=2)
    np.testing.assert_array_equal(
        fallback.clip_positions, [[1, 0, -1, 1]])
    clamped = project_light_shell_vertices(
        vertices[:1], shell_constants(), view, view, near_clip=.5,
        clamp_clip_z_nonnegative=True)
    assert clamped.clip_positions[0, 2] == 0


def test_light_shell_projection_rejects_manager_boundary_errors():
    view = np.eye(4, dtype=np.float32)
    with pytest.raises(ValueError, match='AABB center'):
        project_light_shell_vertices(
            [[0, 0, 0]], shell_constants(), view, view, near_clip=0)
    with pytest.raises(ValueError, match='must be valid'):
        project_light_shell_vertices(
            [[1, 0, 0]], shell_constants(aabb_inverse_extents=(0, 1, 1)),
            view, view, near_clip=0)


@pytest.mark.parametrize('parser', [parse_light_gpu_records,
                                    parse_light_volume_gpu_records])
def test_record_parsers_reject_partial_records(parser):
    with pytest.raises(ValueError, match='whole 128-byte records'):
        parser(bytes(127))


def test_world_light_lookup_constants_use_exact_offsets():
    raw = bytearray(896)
    struct.pack_into('<3fI', raw, 32, 0.125, 0.25, 0.625, 3)
    result = parse_light_lookup_constants(raw)
    assert result.screen_to_lookup == (0.125, 0.25)
    assert result.z_bin_scale == 0.625
    assert result.word_count == 3
    with pytest.raises(ValueError, match='at least 48'):
        parse_light_lookup_constants(bytes(47))


def test_light_z_bin_word_count_and_inclusive_generation():
    records = np.zeros(35, dtype=LIGHT_GPU_DTYPE)
    records['z_bin_min_max'] = np.uint32(0x0000ffff)
    records[0]['z_bin_min_max'] = (2 << 16) | 1
    records[31]['z_bin_min_max'] = (3 << 16) | 3
    records[32]['z_bin_min_max'] = (4 << 16) | 2
    records[34]['z_bin_min_max'] = (1 << 16) | 0

    assert light_lookup_word_count(0) == 0
    assert light_lookup_word_count(32) == 1
    assert light_lookup_word_count(33) == 2
    lookup = generate_light_z_bin_lookup(records, 5)
    assert lookup.shape == (2, 5)
    np.testing.assert_array_equal(
        lookup[0], [0, 1, 1, np.uint32(1 << 31), 0])
    np.testing.assert_array_equal(lookup[1], [4, 4, 1, 1, 1])


def test_light_z_bin_generation_honors_active_prefix_and_empty_boundaries():
    records = np.zeros(33, dtype=LIGHT_GPU_DTYPE)
    records['z_bin_min_max'] = (3 << 16) | 1
    lookup = generate_light_z_bin_lookup(records, 5, record_count=2)
    np.testing.assert_array_equal(lookup, [[0, 3, 3, 3, 0]])
    assert generate_light_z_bin_lookup(
        records, 5, record_count=0).shape == (0, 5)
    assert generate_light_z_bin_lookup(records, 0).shape == (2, 0)


def test_light_z_bin_generation_rejects_invalid_inputs():
    records = np.zeros(1, dtype=LIGHT_GPU_DTYPE)
    with pytest.raises(ValueError, match='parsed LightGpu'):
        generate_light_z_bin_lookup(np.zeros(1, np.uint32), 1)
    with pytest.raises(ValueError, match='exceeds supplied'):
        generate_light_z_bin_lookup(records, 1, record_count=2)
    with pytest.raises(ValueError, match='cannot be negative'):
        generate_light_z_bin_lookup(records, -1)
    with pytest.raises(ValueError, match='cannot be negative'):
        light_lookup_word_count(-1)


def test_lookup_visits_words_and_low_bits_in_ascending_order():
    lookup = np.zeros((3, 2, 2), np.uint32)
    lookup[0, 1, 1] = (1 << 31) | (1 << 2) | 1
    lookup[1, 1, 1] = (1 << 5) | (1 << 1)
    lookup[2, 1, 1] = 1 << 7
    np.testing.assert_array_equal(
        light_lookup_indices(lookup, 1, 1), [0, 2, 31, 33, 37, 71])
    np.testing.assert_array_equal(
        light_lookup_indices(lookup, 1, 1, word_count=1), [0, 2, 31])


def test_lookup_pixel_mapping_and_bulk_word_gather():
    lookup = np.zeros((2, 2, 3), np.uint32)
    lookup[:, 0, 0] = [3, 4]
    lookup[:, 0, 1] = [8, 16]
    np.testing.assert_array_equal(
        light_lookup_indices_at_pixel(lookup, 7, 7), [0, 1, 34])
    np.testing.assert_array_equal(
        light_lookup_indices_at_pixel(lookup, 8, 7), [3, 36])
    pixels = np.array([[0, 0], [7, 7], [8, 7]], np.int32)
    np.testing.assert_array_equal(
        light_lookup_words_at_pixels(lookup, pixels), [[3, 4], [3, 4], [8, 16]])


def test_lookup_rejects_missing_records_and_invalid_boundaries():
    lookup = np.zeros((2, 1, 1), np.uint32)
    lookup[1, 0, 0] = 1 << 3
    with pytest.raises(ValueError, match='missing light record'):
        light_lookup_indices(lookup, 0, 0, record_count=35)
    with pytest.raises(ValueError, match='exceeds texture slices'):
        light_lookup_indices(lookup, 0, 0, word_count=3)
    with pytest.raises(ValueError, match='outside'):
        light_lookup_indices(lookup, 1, 0)
    with pytest.raises(ValueError, match='integer dtype'):
        light_lookup_words_at_pixels(lookup, np.zeros((1, 2), np.float32))


def point_record(**fields):
    records = np.zeros(1, dtype=LIGHT_GPU_DTYPE)
    record = records[0]
    record['world_axis_x'] = fields.pop('world_axis_x', (1, 0, 0))
    record['world_axis_y'] = fields.pop('world_axis_y', (0, 1, 0))
    record['world_axis_z'] = fields.pop('world_axis_z', (0, 0, 1))
    record['world_position'] = fields.pop('world_position', (0, 0, 0))
    record['linear_color'] = fields.pop('linear_color', (2, 4, 8))
    record['inverse_attenuation_radius'] = fields.pop(
        'inverse_attenuation_radius', 0.5)
    record['cone_parameters'] = fields.pop('cone_parameters', (0, 1))
    record['cut_on_depth'] = fields.pop('cut_on_depth', -100)
    record['cut_off_depth'] = fields.pop('cut_off_depth', 100)
    for name, value in fields.items():
        record[name] = value
    return record


def test_point_light_base_attenuation_and_radiance():
    result = evaluate_point_light(point_record(), (0, 0, -1))
    np.testing.assert_array_equal(result.direction, [0, 0, 1])
    assert result.distance_squared == 1
    assert result.cone_weight == 1
    assert result.radial_weight == 0.9375
    assert result.depth_weight == 1
    assert result.attenuation == 0.87890625
    assert result.distance_factor == 0.5
    np.testing.assert_array_equal(
        result.radiance, np.array([0.87890625, 1.7578125, 3.515625], np.float32))


def test_point_light_cone_and_cut_depth_multiply_before_square():
    record = point_record(cone_parameters=(1, 1), cut_on_depth=0.75,
                          cut_off_depth=2)
    # L points opposite the light's Z axis: cone saturates to one. Depth is
    # one, so the two-unit cut-on ramp contributes one half.
    result = evaluate_point_light(record, (0, 0, 1))
    assert result.cone_weight == 1
    assert result.depth_weight == 0.5
    assert result.attenuation == 0.439453125


def test_push_forward_changes_shading_ray_but_not_influence_attenuation():
    base = evaluate_point_light(point_record(), (1, 0, -2))
    pushed = evaluate_point_light(
        point_record(bulb_push_forward=1), (1, 0, -2))
    assert pushed.attenuation == base.attenuation
    assert pushed.distance_squared != base.distance_squared
    assert not np.array_equal(pushed.direction, base.direction)


def test_point_light_rejects_area_and_degenerate_inputs():
    with pytest.raises(ValueError, match='zero bulb radius'):
        evaluate_point_light(point_record(bulb_radius=0.1), (0, 0, -1))
    with pytest.raises(ValueError, match='must not equal'):
        evaluate_point_light(point_record(), (0, 0, 0))


def test_spherical_hair_area_light_adjusts_lobe_weights():
    record = point_record(
        bulb_radius=.5, bulb_length=0, inverse_attenuation_radius=.25)
    triad = np.eye(3, dtype=np.float32)[[2, 0, 1]]
    result = evaluate_hair_area_light(
        record, (0, 0, -2), triad, (0, 0, 1))
    np.testing.assert_array_equal(result.direction, [0, 0, 1])
    assert result.distance_squared == 4
    assert result.source_radius == .5
    assert result.source_length == 0
    assert result.area_metric == .25
    assert result.distance_factor == pytest.approx(.2, abs=1e-7)
    assert 0 < result.lobe_weights[1] < result.lobe_weights[0] < 1
    assert result.lobe_weights[1] == result.lobe_weights[2]
    np.testing.assert_allclose(
        result.radiance,
        np.asarray(record['linear_color'])
        * np.float32(result.attenuation * result.distance_factor),
        rtol=0, atol=1e-7)


def test_capsule_hair_area_light_uses_segment_direction_and_average():
    record = point_record(
        bulb_radius=.5, bulb_length=2, inverse_attenuation_radius=.125)
    triad = np.eye(3, dtype=np.float32)[[2, 0, 1]]
    result = evaluate_hair_area_light(
        record, (0, 0, -4), triad, (0, 0, 1))
    assert result.source_length == 2
    assert result.area_metric > 0
    assert result.distance_factor > 0
    assert not np.array_equal(result.direction, [0, 0, 1])
    assert np.linalg.norm(result.direction) == pytest.approx(1, abs=1e-6)
    assert np.isfinite(result.lobe_weights).all()
    assert np.all((result.lobe_weights >= 0) & (result.lobe_weights <= 1))


def test_negative_radius_area_path_converts_radius_and_shortens_segment():
    record = point_record(
        bulb_radius=-.25, bulb_length=1, inverse_attenuation_radius=.125)
    triad = np.eye(3, dtype=np.float32)[[2, 0, 1]]
    result = evaluate_hair_area_light(
        record, (0, 0, -4), triad, (0, 0, 1))
    assert result.source_radius == .25
    assert result.source_length == pytest.approx(
        1 - .25 * 1.7724499702453613, abs=1e-7)


def test_hair_area_light_rejects_point_and_invalid_surface_inputs():
    triad = np.eye(3, dtype=np.float32)
    with pytest.raises(ValueError, match='nonzero radius'):
        evaluate_hair_area_light(
            point_record(), (0, 0, -1), triad, (0, 0, 1))
    with pytest.raises(ValueError, match='finite Hair directions'):
        evaluate_hair_area_light(
            point_record(bulb_radius=.5), (0, 0, -1),
            np.eye(2, dtype=np.float32), (0, 0, 1))


def volume_record(*, translation=(0, 0, 0), fade=1,
                  extents=(1, 1, 1), negative=(1, 1, 1), positive=(1, 1, 1),
                  atlas=(0, 0, 1, 1)):
    records = np.zeros(1, dtype=LIGHT_VOLUME_GPU_DTYPE)
    records[0]['transform_matrix'] = np.eye(4, dtype=np.float32)
    records[0]['transform_matrix'][3, :3] = translation
    records[0]['atlas_coordinates'] = atlas
    records[0]['fade'] = fade
    records[0]['extents'] = extents
    records[0]['falloff_negative'] = negative
    records[0]['falloff_positive'] = positive
    return records


def test_clip_volume_single_and_ordered_boolean_chain():
    volumes = np.concatenate((
        volume_record(),
        volume_record(translation=(-3, 0, 0), fade=0),
        volume_record(translation=(-3, 0, 0), fade=1),
    ))
    record = point_record(clip_volume_info=(3 << 16))
    # First outside => true; second is a zero-fade intersection and is inside
    # at x=3 => false; third ORs another inside test and leaves false.
    assert not light_clip_rejected(record, volumes, (3, 0, 0))
    assert light_clip_rejected(
        point_record(clip_volume_info=(1 << 16)), volumes, (3, 0, 0))
    assert not light_clip_rejected(point_record(), volumes, (100, 0, 0))


def test_clip_volume_range_and_table_validation():
    volumes = volume_record()
    with pytest.raises(ValueError, match='range exceeds'):
        light_clip_rejected(
            point_record(clip_volume_info=(2 << 16)), volumes, (0, 0, 0))
    with pytest.raises(ValueError, match='parsed LightVolumeGpu'):
        light_clip_rejected(point_record(), np.zeros(1), (0, 0, 0))


def test_box_light_volume_multiplier():
    record = point_record(bit_flags_vfog=2, mod_id_and_gobo_id=0,
                          linear_color=(0, 0.5, 2))
    result = evaluate_light_volume_multiplier(
        record, volume_record(fade=.5), (0, 0, 0))
    np.testing.assert_array_equal(result.local_position, [0, 0, 0])
    assert result.influence == 0.5
    np.testing.assert_array_equal(result.multiplier, [0.5, 0.75, 1.5])
    outside = evaluate_light_volume_multiplier(
        record, volume_record(fade=.5), (2, 0, 0))
    assert outside.influence == 0
    np.testing.assert_array_equal(outside.multiplier, [1, 1, 1])


def test_radial_light_volume_multiplier():
    record = point_record(bit_flags_vfog=2 | 4, mod_id_and_gobo_id=0,
                          linear_color=(2, 2, 2))
    result = evaluate_light_volume_multiplier(
        record, volume_record(fade=.5), (.5, 0, 0))
    assert result.influence == 0.25
    np.testing.assert_array_equal(result.multiplier, [1.25, 1.25, 1.25])
    with pytest.raises(ValueError, match='degenerate'):
        evaluate_light_volume_multiplier(record, volume_record(), (0, 0, 0))


def test_light_volume_multiplier_rejects_wrong_branch_and_index():
    with pytest.raises(ValueError, match='does not select'):
        evaluate_light_volume_multiplier(point_record(), volume_record(), (0, 0, 0))
    with pytest.raises(ValueError, match='index exceeds'):
        evaluate_light_volume_multiplier(
            point_record(bit_flags_vfog=2, mod_id_and_gobo_id=1),
            volume_record(), (0, 0, 0))


def test_spherical_gobo_coordinates_and_rgb_or_monochrome_sampling():
    volumes = volume_record(atlas=(.1, .2, .5, .25))
    alternate = point_record(
        bit_flags_vfog=32, mod_id_and_gobo_id=(0 << 16))
    coords = light_gobo_coordinates(
        alternate, volumes, (0, 0, 0), (-1, 0, 0))
    assert coords.mode == 'alternate_spherical'
    assert coords.monochrome
    np.testing.assert_allclose(coords.unit_uv, [.5, .75], atol=2e-7)
    np.testing.assert_allclose(coords.atlas_uv, [.35, .3875], atol=2e-7)
    np.testing.assert_array_equal(
        apply_light_gobo_sample(alternate, coords, [.25]), [.5, 1, 2])

    spherical = point_record(
        bit_flags_vfog=1, mod_id_and_gobo_id=(0 << 16))
    coords = light_gobo_coordinates(
        spherical, volumes, (0, 0, 0), (-1, 0, 0))
    assert coords.mode == 'spherical'
    np.testing.assert_allclose(coords.unit_uv, [.5, .5], atol=2e-7)
    np.testing.assert_array_equal(
        apply_light_gobo_sample(spherical, coords, [.25, .5, .75]),
        [.5, 2, 6])


def test_projective_gobo_coordinates_and_edge_fade():
    record = point_record(mod_id_and_gobo_id=(0 << 16))
    volumes = volume_record(atlas=(.1, .2, .5, .25))
    coords = light_gobo_coordinates(
        record, volumes, (.25, .5, 0), (0, 0, 1))
    assert coords.mode == 'projective'
    np.testing.assert_array_equal(coords.unit_uv, [.75, .5])
    np.testing.assert_allclose(coords.atlas_uv, [.475, .325], atol=1e-7)
    assert coords.edge_weight == 1
    np.testing.assert_array_equal(
        apply_light_gobo_sample(record, coords, [.5, .25, .125]),
        [1, 1, 1])

    edge = light_gobo_coordinates(
        record, volumes, (0, .5, 0), (0, 0, 1))
    assert edge.edge_weight == 0


def test_gobo_boundary_rejects_absent_indices_and_bad_samples():
    volumes = volume_record()
    with pytest.raises(ValueError, match='does not select'):
        light_gobo_coordinates(
            point_record(mod_id_and_gobo_id=0xffff0000), volumes,
            (0, 0, 0), (1, 0, 0))
    with pytest.raises(ValueError, match='index exceeds'):
        light_gobo_coordinates(
            point_record(mod_id_and_gobo_id=1 << 16), volumes,
            (0, 0, 0), (1, 0, 0))
    coords = light_gobo_coordinates(
        point_record(mod_id_and_gobo_id=0), volumes,
        (.5, .5, 0), (1, 0, 0))
    with pytest.raises(ValueError, match='three-channel'):
        apply_light_gobo_sample(point_record(), coords, [.5])


def test_shadow_volume_coordinates_and_fade_to_white_sample_chain():
    volumes = volume_record(atlas=(.1, .2, .5, .25))
    matrix = np.array((
        (1, 0, 0, 1), (-1, 0, 0, 1),
        (0, 1, 0, 1), (0, -1, 0, 1),
    ), dtype=np.float32)
    volumes[0]['transform_matrix'] = matrix
    volumes[0]['falloff_negative'] = (0, 0, 1)
    volumes[0]['shadow_texel_scale'] = 1
    volumes[0]['fade'] = .1
    volumes[0]['misc'] = .5
    record = point_record(shadow_volume_info=(1 << 16))
    coords = light_shadow_volume_coordinates(record, volumes, (0, 0, 0))
    assert len(coords) == 1
    np.testing.assert_array_equal(coords[0].plane_distances, np.ones(5))
    np.testing.assert_allclose(coords[0].atlas_uv, [.35, .325], atol=1e-7)
    assert coords[0].fade_to_white == pytest.approx(.35, abs=1e-7)
    np.testing.assert_allclose(
        apply_light_shadow_volume_samples(
            (2, 4, 8), coords, [[.2, .4, .6]]),
        [.96, 2.44, 5.92], rtol=0, atol=2e-7)

    assert light_shadow_volume_coordinates(
        record, volumes, (2, 0, 0)) == ()
    assert light_shadow_volume_coordinates(
        record, volumes, (0, 0, 0), enabled=False) == ()


def test_shadow_volume_boundary_rejects_ranges_and_sample_shapes():
    record = point_record(shadow_volume_info=(2 << 16))
    with pytest.raises(ValueError, match='range exceeds'):
        light_shadow_volume_coordinates(record, volume_record(), (0, 0, 0))
    with pytest.raises(ValueError, match='shape'):
        apply_light_shadow_volume_samples((1, 1, 1), (), [[1, 1, 1]])


def test_projective_local_shadow_map_coordinates_and_filter_plan():
    volumes = volume_record(atlas=(.1, .2, .3, .4))
    record = point_record(shadow_map_info=(1 << 16))
    coordinates = light_shadow_map_coordinates(
        record, volumes, (.25, .5, .75))
    assert len(coordinates) == 1 and coordinates[0].mode == 'projective'
    np.testing.assert_allclose(coordinates[0].atlas_uv, [.175, .4], atol=1e-7)
    assert coordinates[0].compare_depth == .75
    assert coordinates[0].inverse_depth_scale == 1
    np.testing.assert_allclose(
        coordinates[0].clamp_minimum,
        [.10006103515625, .20006103515625], atol=1e-8)

    plan = light_shadow_map_sample_plan(coordinates[0], 17, (1, 0))
    assert not plan.direct_compare and plan.sample_uvs.shape == (4, 2)
    assert np.all(plan.sample_uvs >= coordinates[0].clamp_minimum)
    assert np.all(plan.sample_uvs <= coordinates[0].clamp_maximum)
    assert resolve_light_shadow_map_sample(plan, np.full(4, .75, np.float32)) == 1
    assert resolve_light_shadow_map_sample(plan, np.zeros(4, np.float32)) < 1e-6


def test_point_cube_local_shadow_map_face_mapping():
    volumes = volume_record()
    volumes[0]['transform_matrix'] = np.asarray((
        (1.25, 2.25, 3.25, 4.25),
        (5.25, 6.25, 7.25, 8.25),
        (9.25, 10.25, 11.25, 12.25),
        (.5, .1, 0, 1),
    ), np.float32)
    record = point_record(bit_flags_vfog=1, shadow_map_info=(1 << 16))
    coordinate = light_shadow_map_coordinates(
        record, volumes, (2, 1, .5))[0]
    assert coordinate.mode == 'point_cube_face'
    np.testing.assert_array_equal(coordinate.atlas_uv, [.53125, .5625])
    assert coordinate.compare_depth == pytest.approx(1.1, abs=1e-7)
    assert coordinate.inverse_depth_scale == 2

    direct_coordinate = light_shadow_map_coordinates(
        point_record(shadow_map_info=(1 << 16)), volume_record(),
        (.25, .5, 0))[0]
    plan = light_shadow_map_sample_plan(direct_coordinate, 0, (0, 1))
    assert plan.direct_compare
    np.testing.assert_array_equal(plan.sample_uvs, [[.25, .5]])
    assert resolve_light_shadow_map_sample(plan, .375) == .375


def test_local_shadow_map_boundary_rejects_invalid_inputs():
    with pytest.raises(ValueError, match='range exceeds'):
        light_shadow_map_coordinates(
            point_record(shadow_map_info=(2 << 16)), volume_record(),
            (0, 0, 1))
    coordinate = light_shadow_map_coordinates(
        point_record(shadow_map_info=(1 << 16)), volume_record(),
        (0, 0, 1))[0]
    with pytest.raises(ValueError, match='0..127'):
        light_shadow_map_sample_plan(coordinate, 128, (1, 0))
    plan = light_shadow_map_sample_plan(coordinate, 0, (1, 0))
    with pytest.raises(ValueError, match='four finite depths'):
        resolve_light_shadow_map_sample(plan, [1])

def test_light_manager_spatial_tree_lookup_axis_bits_and_leaf_encoding():
    empty = LightManagerSpatialTreeNode(
        (-0x8000, -0x8000, -0x8000), (0xffff,) * 8)
    for center, slot in (
            ((-0x8000, -0x8000, -0x8000), 0),
            ((0, -0x8000, -0x8000), 1),
            ((-0x8000, 0, -0x8000), 2),
            ((-0x8000, -0x8000, 0), 4),
            ((0x7fff, 0x7fff, 0x7fff), 7)):
        result = lookup_light_manager_spatial_tree(
            (empty,), LightManagerSpatialPackedBound(center, 0))
        assert result == LightManagerSpatialTreeLookup(0, slot, 0xffff, 0)

    leaf = LightManagerSpatialTreeNode(
        (-0x8000, -0x8000, -0x8000),
        (0x8003, 0xffff, 0xffff, 0xffff,
         0xffff, 0xffff, 0xffff, 0xffff))
    assert lookup_light_manager_spatial_tree(
        (leaf,), LightManagerSpatialPackedBound((-0x8000,) * 3, 0),
    ) == LightManagerSpatialTreeLookup(0, 0, 0x8003, 0)


def test_light_manager_spatial_tree_lookup_consumes_successive_coordinate_bits():
    nodes = (
        LightManagerSpatialTreeNode(
            (-0x8000, -0x8000, -0x8000),
            (1, 0xffff, 0xffff, 0xffff, 0xffff, 0xffff, 0xffff, 0xffff)),
        LightManagerSpatialTreeNode(
            (0, 0, 0),
            (0xffff, 2, 0xffff, 0xffff, 0xffff, 0xffff, 0xffff, 0xffff)),
        LightManagerSpatialTreeNode(
            (0, 0, 0),
            (0xffff, 0xffff, 0x8005, 0xffff,
             0xffff, 0xffff, 0xffff, 0xffff)),
    )
    result = lookup_light_manager_spatial_tree(
        nodes, LightManagerSpatialPackedBound((-0x4000, -0x6000, -0x8000), 0))
    assert result == LightManagerSpatialTreeLookup(2, 2, 0x8005, 2)


def test_light_manager_spatial_tree_lookup_validates_snapshot():
    bound = LightManagerSpatialPackedBound((0, 0, 0), 0)
    with pytest.raises(ValueError, match="must contain tree-node"):
        lookup_light_manager_spatial_tree((), bound)
    bad_child = LightManagerSpatialTreeNode((0, 0, 0), (1,) + (0xffff,) * 7)
    with pytest.raises(ValueError, match="child index"):
        lookup_light_manager_spatial_tree((bad_child,), bound)
    cycle = LightManagerSpatialTreeNode((0, 0, 0), (0,) * 8)
    with pytest.raises(ValueError, match="nonterminating"):
        lookup_light_manager_spatial_tree((cycle,), bound)

def test_light_manager_spatial_tree_subdivision_allocates_axis_children():
    for slot, expected_origin in (
            (0, (-0x8000, -0x8000, -0x8000)),
            (1, (0, -0x8000, -0x8000)),
            (2, (-0x8000, 0, -0x8000)),
            (4, (-0x8000, -0x8000, 0)),
            (7, (0, 0, 0))):
        nodes = (
            LightManagerSpatialTreeNode(
                (-0x8000, -0x8000, -0x8000), (0x8000,) * 8),
            LightManagerSpatialTreeNode((0, 0, 0), (0xffff,) * 8),
        )
        result = begin_light_manager_spatial_tree_subdivision(
            nodes, cell_parent_node_index=0, cell_parent_slot=slot,
            cell_depth=15, free_node_index=1, next_free_node_index=None,
            maximum_active_node_index=0)
        assert result is not None
        child = result.nodes[1]
        assert child.origin == expected_origin
        assert child.depth == 15
        assert child.parent_node_index == 0
        assert child.parent_slot == slot
        assert child.active_marker == 1
        assert child.slots == (0xffff,) * 8
        assert result.nodes[0].slots[slot] == 1
        assert result.maximum_active_node_index == 1


def test_light_manager_spatial_tree_subdivision_nonroot_and_free_list_state():
    nodes = (
        LightManagerSpatialTreeNode((0, 0, 0), (0xffff,) * 8),
        LightManagerSpatialTreeNode((0, 0, 0), (0xffff,) * 8),
        LightManagerSpatialTreeNode(
            (100, -200, 300), (0xffff,) * 5 + (0x8004,) + (0xffff,) * 2,
            depth=9),
        LightManagerSpatialTreeNode((0, 0, 0), (0xffff,) * 8),
    )
    result = begin_light_manager_spatial_tree_subdivision(
        nodes, cell_parent_node_index=2, cell_parent_slot=5,
        cell_depth=8, free_node_index=3, next_free_node_index=1,
        maximum_active_node_index=2)
    assert result is not None
    assert result.nodes[3] == LightManagerSpatialTreeNode(
        (356, -200, 556), (0xffff,) * 8, 8, 2, 5, 1)
    assert result.nodes[2].slots[5] == 3
    assert result.free_head_index == 1
    assert result.maximum_active_node_index == 3


def test_light_manager_spatial_tree_subdivision_gates_and_validates():
    nodes = (
        LightManagerSpatialTreeNode((0, 0, 0), (0x8000,) * 8),
        LightManagerSpatialTreeNode((0, 0, 0), (0xffff,) * 8),
    )
    base = dict(
        cell_parent_node_index=0, cell_parent_slot=0,
        next_free_node_index=None, maximum_active_node_index=0)
    assert begin_light_manager_spatial_tree_subdivision(
        nodes, cell_depth=4, free_node_index=1, **base) is None
    assert begin_light_manager_spatial_tree_subdivision(
        nodes, cell_depth=15, free_node_index=None, **base) is None
    with pytest.raises(ValueError, match="parent slot"):
        begin_light_manager_spatial_tree_subdivision(
            nodes, cell_parent_slot=8, cell_depth=15, free_node_index=1,
            cell_parent_node_index=0, next_free_node_index=None,
            maximum_active_node_index=0)

def _spatial_subdivision_root_nodes():
    return (
        LightManagerSpatialTreeNode(
            (-0x8000, -0x8000, -0x8000),
            (0x8008,) + (0xffff,) * 7),
        LightManagerSpatialTreeNode((0, 0, 0), (0xffff,) * 8),
    )


def test_light_manager_spatial_tree_redistribution_eight_octants():
    low, high = -0x6000, -0x2000
    entries = tuple(
        LightManagerSpatialEntry(
            1, slot,
            LightManagerSpatialPackedBound((
                high if slot & 1 else low,
                high if slot & 2 else low,
                high if slot & 4 else low,
            ), 2 + slot % 3))
        for slot in range(8))
    result = redistribute_light_manager_spatial_tree_cell(
        _spatial_subdivision_root_nodes(), entries,
        cell_parent_node_index=0, cell_parent_slot=0, cell_depth=15,
        old_cell_index=8, free_node_index=1, next_free_node_index=None,
        maximum_active_node_index=0, free_cell_indices=range(8),
        free_page_indices=range(8), cell_metadata=0x12345678)
    assert result is not None
    assert result.active_cell_delta == 7
    assert result.subdivision.nodes[1].slots == tuple(
        0x8000 | index for index in (8, 0, 1, 2, 3, 4, 5, 6))
    assert result.append_sequence == tuple(
        (slot, index) for slot, index in enumerate((8, 0, 1, 2, 3, 4, 5, 6)))
    assert [cell.slot_index for cell in result.child_cells] == list(range(8))
    assert all(cell.parent_node_index == 1 and cell.depth == 14
               for cell in result.child_cells)


def test_light_manager_spatial_tree_redistribution_unions_and_reuses():
    entries = (
        LightManagerSpatialEntry(
            1, 20, LightManagerSpatialPackedBound((-30000, -28000, -26000), 1)),
        LightManagerSpatialEntry(
            1, 21, LightManagerSpatialPackedBound((-25000, -27000, -29000), 3)),
        LightManagerSpatialEntry(
            1, 22, LightManagerSpatialPackedBound((-31000, -24000, -23000), 5)),
    )
    result = redistribute_light_manager_spatial_tree_cell(
        _spatial_subdivision_root_nodes(), entries,
        cell_parent_node_index=0, cell_parent_slot=0, cell_depth=15,
        old_cell_index=8, free_node_index=1, next_free_node_index=None,
        maximum_active_node_index=0, free_cell_indices=range(8),
        free_page_indices=range(8), cell_metadata=0x12345678)
    assert result is not None
    assert result.active_cell_delta == 0
    assert len(result.child_cells) == 1
    child = result.child_cells[0]
    assert child.slot_index == 0 and child.cell_index == 8 and child.page_index == 0
    assert tuple(entry.source_index for entry in child.entries) == (20, 21, 22)
    assert child.bound == rebuild_light_manager_spatial_cell_bound(entries)


def test_light_manager_spatial_tree_redistribution_requires_entries():
    with pytest.raises(ValueError, match="requires spatial-entry"):
        redistribute_light_manager_spatial_tree_cell(
            _spatial_subdivision_root_nodes(), (),
            cell_parent_node_index=0, cell_parent_slot=0, cell_depth=15,
            old_cell_index=8, free_node_index=1, next_free_node_index=None,
            maximum_active_node_index=0, free_cell_indices=range(8),
            free_page_indices=range(8))
def test_light_manager_spatial_tree_collapse_retains_sibling_cell():
    node = LightManagerSpatialTreeNode(
        (-0x8000,) * 3,
        (0xffff, 0xffff, 0x8005, 0xffff,
         0xffff, 0xffff, 0xffff, 0x8006),
        parent_node_index=-1)
    result = collapse_light_manager_spatial_tree_cell(
        (node,), cell_parent_node_index=0, cell_parent_slot=2,
        root_index=0, maximum_active_node_index=0)
    assert result.root_index == 0
    assert result.nodes[0].slots == (
        0xffff, 0xffff, 0xffff, 0xffff,
        0xffff, 0xffff, 0xffff, 0x8006)
    assert result.freed_node_indices == ()
    assert result.free_node_chain == ()
    assert result.maximum_active_node_index == 0


def test_light_manager_spatial_tree_collapse_frees_empty_ancestors():
    nodes = (
        LightManagerSpatialTreeNode(
            (-0x8000,) * 3,
            (0xffff, 0xffff, 1, 0xffff,
             0xffff, 0xffff, 0xffff, 0x8006),
            parent_node_index=-1),
        LightManagerSpatialTreeNode(
            (-0x8000,) * 3,
            (0xffff, 0xffff, 0xffff, 0xffff,
             0xffff, 2, 0xffff, 0xffff),
            depth=15, parent_node_index=0, parent_slot=2),
        LightManagerSpatialTreeNode(
            (-0x8000,) * 3,
            (0xffff, 0xffff, 0xffff, 0x8005,
             0xffff, 0xffff, 0xffff, 0xffff),
            depth=14, parent_node_index=1, parent_slot=5),
    )
    result = collapse_light_manager_spatial_tree_cell(
        nodes, cell_parent_node_index=2, cell_parent_slot=3,
        root_index=0, maximum_active_node_index=2)
    assert result.root_index == 0
    assert result.freed_node_indices == (2, 1)
    assert result.free_node_chain == (1, 2)
    assert result.free_head_index == 1
    assert result.maximum_active_node_index == 0
    assert result.nodes[0].slots == (
        0xffff, 0xffff, 0xffff, 0xffff,
        0xffff, 0xffff, 0xffff, 0x8006)
    assert result.nodes[1].active_marker == result.nodes[2].active_marker == 0


def test_light_manager_spatial_tree_collapse_clears_root_and_prepends_free_list():
    inactive = LightManagerSpatialTreeNode(
        (0, 0, 0), (0,) * 8, depth=0,
        parent_node_index=0, parent_slot=0, active_marker=0)
    nodes = (
        LightManagerSpatialTreeNode(
            (-0x8000,) * 3,
            (0xffff, 1, 0xffff, 0xffff,
             0xffff, 0xffff, 0xffff, 0xffff),
            parent_node_index=-1),
        LightManagerSpatialTreeNode(
            (-0x8000,) * 3,
            (0xffff, 0xffff, 0xffff, 0xffff,
             0xffff, 0xffff, 2, 0xffff),
            depth=15, parent_node_index=0, parent_slot=1),
        LightManagerSpatialTreeNode(
            (-0x8000,) * 3,
            (0xffff, 0xffff, 0xffff, 0xffff,
             0xffff, 0xffff, 0xffff, 0x8005),
            depth=14, parent_node_index=1, parent_slot=6),
        inactive,
    )
    result = collapse_light_manager_spatial_tree_cell(
        nodes, cell_parent_node_index=2, cell_parent_slot=7,
        root_index=0, free_node_chain=(3,), maximum_active_node_index=2)
    assert result.root_index is None
    assert result.freed_node_indices == (2, 1, 0)
    assert result.free_node_chain == (0, 1, 2, 3)
    assert result.free_head_index == 0
    assert result.maximum_active_node_index == -1
    assert all(node.active_marker == 0 for node in result.nodes)
def _spatial_page_append_entry(source_index=77):
    return LightManagerSpatialEntry(
        0x1234, source_index,
        LightManagerSpatialPackedBound((-30000, -20000, 10000), 31),
        reserved=0x2345)


def test_light_manager_spatial_page_append_uses_last_in_page_slot():
    entry = _spatial_page_append_entry()
    current = LightManagerSpatialPage(
        -1, -1, 3, 1, 0, tuple(entry for _ in range(14)))
    inactive = LightManagerSpatialPage(0, 0, 0, 0, 0, ())
    result = append_light_manager_spatial_page(
        (inactive, current, inactive), entry,
        cell_index=3, cell_latest_page_index=1, cell_entry_count=14,
        cell_state_byte=0x42, free_page_chain=(2,))
    assert result.success is True and result.source_handle == 0x1e
    assert result.appended_page_index == 1 and result.appended_slot == 14
    assert len(result.pages[1].entries) == 15
    assert result.cell_entry_count == 15 and result.cell_state_byte == 0x42
    assert result.free_page_chain == (2,)


def test_light_manager_spatial_page_append_reuses_page_zero_and_marks_dirty():
    entry = _spatial_page_append_entry(88)
    inactive = LightManagerSpatialPage(0, 0, 0, 0, 0, ())
    full = LightManagerSpatialPage(
        -1, -1, 2, 1, 0, tuple(entry for _ in range(15)))
    result = append_light_manager_spatial_page(
        (inactive, full, inactive), entry,
        cell_index=2, cell_latest_page_index=1, cell_entry_count=31,
        cell_state_byte=0x04, free_page_chain=(0, 2))
    assert result.success is True and result.source_handle == 0
    assert result.cell_latest_page_index == 0
    assert result.cell_entry_count == 32 and result.cell_state_byte == 0x84
    assert result.free_page_chain == (2,)
    assert result.pages[1].newer_page == 0
    assert result.pages[0] == LightManagerSpatialPage(
        1, -1, 2, 1, 0, (entry,))


def test_light_manager_spatial_page_append_exhaustion_is_atomic():
    entry = _spatial_page_append_entry(99)
    full = LightManagerSpatialPage(
        -1, -1, 0, 1, 0, tuple(entry for _ in range(15)))
    result = append_light_manager_spatial_page(
        (full,), entry,
        cell_index=0, cell_latest_page_index=0, cell_entry_count=15,
        cell_state_byte=0x45, source_handle_before=-1)
    assert result.success is False and result.source_handle == -1
    assert result.pages == (full,)
    assert result.cell_latest_page_index == 0
    assert result.cell_entry_count == 15 and result.cell_state_byte == 0x45
    assert result.appended_page_index is None and result.appended_slot is None

def _inactive_spatial_tree_node():
    return LightManagerSpatialTreeNode(
        (0, 0, 0), (0,) * 8, depth=0,
        parent_node_index=0, parent_slot=0, active_marker=0)


def _inactive_spatial_cell():
    return LightManagerSpatialCell(
        center=(0.0, 0.0, 0.0), radius_weight=0,
        half_extents=(0.0, 0.0, 0.0), reserved_1c=0,
        latest_page_index=0, entry_count=0, parent_node_index=0,
        parent_slot=0, state_byte=0, selection_mask=0)


def test_light_manager_spatial_node_allocator_initializes_and_extends_maximum():
    nodes = tuple(_inactive_spatial_tree_node() for _ in range(6))
    result = allocate_light_manager_spatial_tree_node(
        nodes, free_node_chain=(4, 2), maximum_active_node_index=1)
    assert result.allocated_node_index == 4
    assert result.free_head_index == 2 and result.free_node_chain == (2,)
    assert result.maximum_active_node_index == 4
    assert result.nodes[4] == LightManagerSpatialTreeNode(
        (0, 0, 0), (0xffff,) * 8, depth=0,
        parent_node_index=-1, parent_slot=0, active_marker=1)


def test_light_manager_spatial_node_allocator_exhaustion_is_atomic():
    nodes = tuple(_inactive_spatial_tree_node() for _ in range(4))
    result = allocate_light_manager_spatial_tree_node(
        nodes, maximum_active_node_index=3)
    assert result.allocated_node_index is None
    assert result.nodes == nodes and result.free_node_chain == ()
    assert result.free_head_index is None
    assert result.maximum_active_node_index == 3


def test_light_manager_spatial_cell_allocator_initializes_retail_sentinel():
    cells = tuple(_inactive_spatial_cell() for _ in range(6))
    result = allocate_light_manager_spatial_cell(
        cells, free_cell_chain=(4, 2), maximum_active_cell_index=1,
        active_cell_count=6)
    assert result.allocated_cell_index == 4
    assert result.free_head_index == 2 and result.free_cell_chain == (2,)
    assert result.maximum_active_cell_index == 4
    assert result.active_cell_count == 7
    assert result.cells[4] == LightManagerSpatialCell(
        center=(0.0, 0.0, 1048576.0), radius_weight=0,
        half_extents=(0.0, 0.0, 0.0), reserved_1c=0,
        latest_page_index=-1, entry_count=0, parent_node_index=-1,
        parent_slot=0, state_byte=0x40, selection_mask=0)


def test_light_manager_spatial_cell_allocator_preserves_maximum_and_exhaustion():
    cells = tuple(_inactive_spatial_cell() for _ in range(6))
    allocated = allocate_light_manager_spatial_cell(
        cells, free_cell_chain=(1,), maximum_active_cell_index=5,
        active_cell_count=2)
    assert allocated.allocated_cell_index == 1
    assert allocated.maximum_active_cell_index == 5
    assert allocated.active_cell_count == 3
    exhausted = allocate_light_manager_spatial_cell(
        cells, maximum_active_cell_index=3, active_cell_count=4)
    assert exhausted.allocated_cell_index is None
    assert exhausted.cells == cells and exhausted.free_cell_chain == ()
    assert exhausted.maximum_active_cell_index == 3
    assert exhausted.active_cell_count == 4
def _inactive_spatial_page():
    return LightManagerSpatialPage(0, 0, 0, 0, 0, ())


def test_light_manager_spatial_cell_release_repairs_maximum_over_gap():
    inactive = _inactive_spatial_cell()
    cells = (
        LightManagerSpatialCell(
            (0.0, 0.0, 0.0), 0, (1.0, 1.0, 1.0), 0,
            -1, 1, 0, 0, 0x40, 0),
        inactive,
        LightManagerSpatialCell(
            (2.0, 3.0, 4.0), 0, (1.0, 1.0, 1.0), 0,
            -1, 1, 0, 0, 0x4f, 7),
    )
    result = release_light_manager_spatial_cell(
        cells, cell_index=2, free_cell_chain=(1,),
        maximum_active_cell_index=2, active_cell_count=2)
    assert result.free_cell_chain == (2, 1)
    assert result.maximum_active_cell_index == 0
    assert result.active_cell_count == 1
    assert result.cells[2] == LightManagerSpatialCell(
        (0.0, 0.0, 1048576.0), 0, (0.0, 0.0, 0.0), 0,
        -1, 0, -1, 0, 0, 0)


def test_light_manager_spatial_owner_insert_builds_root_cell_and_page():
    nodes = tuple(_inactive_spatial_tree_node() for _ in range(8))
    cells = tuple(_inactive_spatial_cell() for _ in range(8))
    pages = tuple(_inactive_spatial_page() for _ in range(8))
    result = insert_light_manager_spatial_owner(
        nodes, cells, pages, source_byte_offset=12,
        selection_mask=0x1234, center_radius=(1.25, -2.5, 3.75, 2.0),
        free_node_chain=(1, 3), maximum_active_node_index=-1,
        free_cell_chain=(2, 4), maximum_active_cell_index=-1,
        free_page_chain=(3, 5), live_source_count=7)
    assert result.success is True and result.source_handle == 0x30
    assert result.root_index == 1 and result.live_source_count == 8
    assert result.active_cell_count == 1
    assert result.free_node_chain == (3,)
    assert result.free_cell_chain == (4,)
    assert result.free_page_chain == (5,)
    assert result.nodes[1].slots[5] == 0x8002
    assert result.cells[2] == LightManagerSpatialCell(
        (1.25, -2.5, 3.75), 0, (2.0, 2.0, 2.0), 0,
        3, 1, 1, 5, 0x4f, 0)
    assert result.pages[3].entries == (result.packed_entry,)
    assert result.helper_calls == (
        'bound_packer', 'node_allocator', 'tree_lookup',
        'cell_allocator', 'page_append')


def test_light_manager_spatial_owner_insert_releases_cell_without_page():
    root = LightManagerSpatialTreeNode(
        (-0x8000,) * 3, (0xffff,) * 8, parent_node_index=-1)
    nodes = (root,) + tuple(
        _inactive_spatial_tree_node() for _ in range(7))
    cells = tuple(_inactive_spatial_cell() for _ in range(8))
    pages = tuple(_inactive_spatial_page() for _ in range(8))
    result = insert_light_manager_spatial_owner(
        nodes, cells, pages, source_byte_offset=16,
        selection_mask=0x4321, center_radius=(13.0, 16.0, 35.0, 2.0),
        root_index=0, maximum_active_node_index=0,
        free_cell_chain=(2, 4), maximum_active_cell_index=-1)
    assert result.success is False and result.source_handle == -1
    assert result.active_cell_count == 0
    assert result.maximum_active_cell_index == -1
    assert result.free_cell_chain == (2, 4)
    assert result.nodes[0].slots == (0xffff,) * 8
    assert result.helper_calls == (
        'bound_packer', 'tree_lookup', 'cell_allocator', 'cell_release')


def test_light_manager_spatial_owner_insert_failed_append_keeps_expanded_bound():
    root = LightManagerSpatialTreeNode(
        (-0x8000,) * 3, (0x8001,) * 8, parent_node_index=-1)
    inactive = _inactive_spatial_cell()
    active = LightManagerSpatialCell(
        (10.0, 20.0, 30.0), 0, (1.0, 2.0, 3.0), 0,
        2, 15, 0, 5, 0x4f, 0x40)
    cells = (inactive, active) + tuple(inactive for _ in range(6))
    entry = _spatial_page_append_entry()
    empty_page = _inactive_spatial_page()
    full_page = LightManagerSpatialPage(
        -1, -1, 1, 1, 0, tuple(entry for _ in range(15)))
    pages = (
        empty_page, empty_page, full_page,
        empty_page, empty_page, empty_page, empty_page, empty_page)
    result = insert_light_manager_spatial_owner(
        (root,) + tuple(_inactive_spatial_tree_node() for _ in range(7)),
        cells, pages, source_byte_offset=24,
        selection_mask=0x00f3, center_radius=(13.0, 16.0, 35.0, 2.0),
        root_index=0, maximum_active_node_index=0,
        maximum_active_cell_index=1, active_cell_count=1,
        live_source_count=10)
    assert result.success is False and result.source_handle == -1
    assert result.live_source_count == 10
    assert result.cells[1].center == (12.0, 18.0, 32.0)
    assert result.cells[1].half_extents == (3.0, 4.0, 5.0)
    assert result.cells[1].entry_count == 15
    assert result.pages == pages
    assert result.helper_calls == (
        'bound_packer', 'tree_lookup', 'page_append')