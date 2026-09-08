"""Native type-1 scene-light record boundaries."""

import struct

import pytest

from core.scene_lights import (
    SCENE_LIGHT_ATTENUATION_RADIUS_FLOOR,
    SCENE_LIGHT_AUTO_RADIUS_COLOR_WEIGHTS,
    SCENE_LIGHT_CONE_INNER_LIMIT,
    SCENE_LIGHT_SCALAR_OFFSETS,
    SCENE_LIGHT_TYPE1_SCALAR_FIELDS,
    build_scene_light_local_basis_transform,
    compose_scene_light_owner_transform,
    build_scene_light_type_1_derived_runtime,
    build_scene_light_resolved_transform,
    build_scene_light_type_1_runtime_transfer,
    parse_scene_light_definition,
    select_scene_light_owner_transform,
)
from core.zone import SceneNodeEntry


def light_bytes(*, size=0xF0, node_type=1, light_type=2, string_offset=0,
                option_bits=0xA55A):
    raw = bytearray(max(size, 0xF0))
    matrix = [float(index) for index in range(16)]
    struct.pack_into('<16f', raw, 0, *matrix)
    struct.pack_into('<I', raw, 0x5C, 0x010203 | (node_type << 24))
    struct.pack_into('<3f', raw, 0x70, 2.0, 3.0, 4.0)
    struct.pack_into('<I', raw, 0x7C, size)
    struct.pack_into('<QQH4B H II 3f 2H f II 13f', raw, 0x80,
                     0x1122334455667788, 0x8877665544332211, option_bits,
                     light_type, 3, 4, 5, string_offset, 0x12345678, 0x9ABCDEF0,
                     0.25, 0.5, 0.75, 100, 200, 1.25,
                     0x0BADF00D, 0xC001D00D,
                     *[float(index) for index in range(13)])
    return raw


def unterminated_light_bytes():
    raw = light_bytes(size=0xF4, string_offset=0xF0)
    raw[0xF0:0xF4] = b'abcd'
    return raw


def test_parse_exact_scene_light_layout():
    light = parse_scene_light_definition(light_bytes())

    assert light.position == (12.0, 13.0, 14.0)
    assert light.node_flags == 0x01010203
    assert light.scale == (2.0, 3.0, 4.0)
    assert light.serialized_size == 0xF0
    assert light.field_80 == 0x1122334455667788
    assert light.toggle_bits == 0x8877665544332211
    assert light.option_bits == 0xA55A
    assert light.light_type == 2
    assert (light.field_93, light.field_94, light.field_95) == (3, 4, 5)
    assert light.trailing_string is None
    assert light.color == (0.25, 0.5, 0.75)
    assert light.packed_pair_ac == (100, 200)
    assert light.field_b0 == 1.25
    assert light.field_b4 == 0x0BADF00D
    assert light.field_b8 == 0xC001D00D
    assert light.scalar_at(0xBC) == 0.0
    assert light.scalar_at(0xEC) == 12.0
    assert SCENE_LIGHT_SCALAR_OFFSETS == tuple(range(0xBC, 0xF0, 4))


def test_parse_scene_light_trailing_string():
    raw = light_bytes(size=0xF8, string_offset=0xF0)
    raw[0xF0:0xF8] = b'point\0\0\0'
    assert parse_scene_light_definition(raw).trailing_string == 'point'


def test_scene_entry_exposes_type_1_light_only():
    raw = bytes(light_bytes())
    entry = SceneNodeEntry(0, 0, 0, 'light', 12, 13, 14, (), 0,
                           raw=raw, node_type=1)
    assert entry.scene_light.light_type == 2
    entry.node_type = 2
    assert entry.scene_light is None


@pytest.mark.parametrize('raw, message', [
    (b'\0' * 0x70, 'shorter than its header'),
    (light_bytes(node_type=2), 'Expected scene node type 1'),
    (light_bytes(size=0xE0), 'shorter than 0xF0'),
    (light_bytes() + b'\0', 'exactly one serialized definition'),
    (unterminated_light_bytes(), 'not null terminated'),
])
def test_parse_scene_light_rejects_invalid_boundaries(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_scene_light_definition(raw)


def test_scalar_offsets_remain_explicit():
    light = parse_scene_light_definition(light_bytes())
    with pytest.raises(ValueError, match='0xBC..0xEC'):
        light.scalar_at(0xB8)


def test_type_1_runtime_transfer_maps_verified_fields():
    light = parse_scene_light_definition(light_bytes(light_type=1))
    transfer = light.type_1_runtime_transfer()

    assert transfer.color == (0.25, 0.5, 0.75)
    assert transfer.volumetric_fog_intensity == 1.25
    assert transfer.intensity == 0.0
    assert transfer.attenuation_radius_override == 1.0
    assert transfer.cutoff_radius == 2.0
    assert transfer.cut_on_distance == 3.0
    assert transfer.specular_intensity == 4.0
    assert transfer.specular_fade_out_distance == 5.0
    assert transfer.fade_out_distance == 6.0
    assert transfer.inner_cone == 7.0
    assert transfer.outer_cone == 8.0
    assert transfer.bulb_radius == 9.0
    assert transfer.bulb_length == 10.0
    assert transfer.shadow_cut_on_distance == 11.0
    assert transfer.bulb_push_forward == 12.0
    assert dict(transfer.runtime_float_fields()) == {
        0xA0: 0.0, 0xA8: 0.25, 0xAC: 0.5, 0xB0: 0.75, 0xB4: 1.25,
        0xC4: 6.0, 0xC8: 4.0, 0xCC: 5.0, 0x120: 1.0,
        0x124: 7.0, 0x128: 8.0, 0x12C: 2.0, 0x130: 3.0,
        0x134: 11.0, 0x138: 9.0, 0x13C: 10.0, 0x140: 12.0,
    }
    assert SCENE_LIGHT_TYPE1_SCALAR_FIELDS == (
        (0xBC, 'intensity', 0xA0),
        (0xC0, 'attenuation_radius', 0x120),
        (0xC4, 'cutoff_radius', 0x12C),
        (0xC8, 'cut_on_distance', 0x130),
        (0xCC, 'specular_intensity', 0xC8),
        (0xD0, 'specular_fade_out_distance', 0xCC),
        (0xD4, 'fade_out_distance', 0xC4),
        (0xD8, 'inner_cone', 0x124),
        (0xDC, 'outer_cone', 0x128),
        (0xE0, 'bulb_radius', 0x138),
        (0xE4, 'bulb_length', 0x13C),
        (0xE8, 'shadow_cut_on_distance', 0x134),
        (0xEC, 'bulb_push_forward', 0x140),
    )


def test_type_1_runtime_transfer_reproduces_native_clamp_and_flags():
    raw = light_bytes(light_type=1, option_bits=0)
    struct.pack_into('<13f', raw, 0xBC,
                     2.0, 0.001, 4.0, 5.0, 6.0, 7.0, 8.0,
                     9.0, 10.0, 11.0, 12.0, 13.0, 14.0)
    transfer = build_scene_light_type_1_runtime_transfer(
        parse_scene_light_definition(raw))

    assert transfer.attenuation_radius_override == \
        SCENE_LIGHT_ATTENUATION_RADIUS_FLOOR
    assert transfer.runtime_flags == 0x740000


def test_type_1_runtime_transfer_preserves_initializer_radius_when_not_positive():
    raw = light_bytes(light_type=1, option_bits=0)
    struct.pack_into('<f', raw, 0xC0, 0.0)
    transfer = build_scene_light_type_1_runtime_transfer(
        parse_scene_light_definition(raw))

    assert transfer.attenuation_radius_override is None
    assert 0x120 not in dict(transfer.runtime_float_fields())
    assert not transfer.runtime_flags & (1 << 22)


def test_type_1_derived_runtime_reproduces_native_cone_and_culling_values():
    raw = light_bytes(light_type=1, option_bits=0)
    struct.pack_into(
        '<3f', raw, 0xA0, 5.5363874435424805, 1.1506770849227905, 0.0)
    struct.pack_into(
        '<13f', raw, 0xBC,
        1, 25, 0, 0, 1, 0, 0,
        0.6108652353286743, 1.1344640254974365,
        0, 0, 4, 0)
    derived = parse_scene_light_definition(
        raw).type_1_runtime_transfer().derived_runtime()

    assert derived.attenuation_radius == 4.0
    assert derived.cone_scale == 2.521852970123291
    assert derived.cone_bias == -1.0657811164855957
    assert derived.cone_culling_length == 4.0
    assert derived.cut_on_distance == 0.0
    assert derived.shadow_cut_on_distance == 3.990000009536743
    assert derived.culling_half_extents == (
        3.6252312660217285, 3.6252312660217285, 2.0)
    assert derived.culling_center_and_radius == (
        0.0, 0.0, 2.0, 3.638421058654785)
    assert dict(derived.runtime_float_fields()) == {
        0x120: 4.0,
        0x130: 0.0,
        0x134: 3.990000009536743,
        0x144: 2.521852970123291,
        0x148: -1.0657811164855957,
        0x14C: 4.0,
    }
    assert SCENE_LIGHT_AUTO_RADIUS_COLOR_WEIGHTS == (
        1.7007999420166016, 5.72160005569458, 0.5776000022888184)
    assert SCENE_LIGHT_CONE_INNER_LIMIT == 0.9900000095367432


def test_type_1_derived_runtime_handles_cutoff_inside_cone_axis():
    raw = light_bytes(light_type=1, option_bits=0)
    struct.pack_into(
        '<3f', raw, 0xA0, 5.5363874435424805, 1.1506770849227905, 0.0)
    struct.pack_into(
        '<13f', raw, 0xBC,
        1, 25, 1, .25, 1, 0, 0,
        0.6108652353286743, 1.1344640254974365,
        0, 0, .5, 0)
    derived = build_scene_light_type_1_derived_runtime(
        parse_scene_light_definition(raw).type_1_runtime_transfer())

    assert derived.cone_culling_length == 2.366201639175415
    assert derived.cut_on_distance == .25
    assert derived.shadow_cut_on_distance == .5
    assert derived.culling_half_extents == (
        2.1445069313049316, 2.1445069313049316, .375)
    assert derived.culling_center_and_radius == (
        0.0, 0.0, .625, 2.1770472526550293)


def test_type_1_derived_runtime_zero_cone_preserves_ramp_fields():
    raw = light_bytes(light_type=1, option_bits=0)
    struct.pack_into('<3f', raw, 0xA0, 0.0, 0.0, 0.0)
    struct.pack_into('<13f', raw, 0xBC, *([0.0] * 13))
    derived = parse_scene_light_definition(
        raw).type_1_runtime_transfer().derived_runtime()

    assert derived.cone_scale is None
    assert derived.cone_bias is None
    assert derived.attenuation_radius == 0.0
    assert derived.culling_half_extents == (0.0, 0.0, 0.0)
    assert derived.culling_center_and_radius == (0.0, 0.0, 0.0, 0.0)
    assert derived.shadow_cut_on_distance == \
        SCENE_LIGHT_ATTENUATION_RADIUS_FLOOR


def test_resolved_transform_commit_preserves_affine_identity():
    result = build_scene_light_resolved_transform((
        (1, 0, 0, 0),
        (0, 1, 0, 0),
        (0, 0, 1, 0),
        (10, 20, 30, 1),
    ), existing_transform_flags=0xA5A500E0)

    assert result.matrix == (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (10.0, 20.0, 30.0, 1.0),
    )
    assert result.axis_scales == (1.0, 1.0, 1.0)
    assert result.transform_flags == 0xA5A500E0


def test_resolved_transform_classifies_mirror_nonuniform_and_median_axis():
    result = build_scene_light_resolved_transform((
        (2, 0, 0, 0),
        (0, 4, 0, 0),
        (0, 0, -8, 0),
        (10, 20, 30, 1),
    ), existing_transform_flags=0xFFFF0000)

    assert result.axis_scales == (2.0, 4.0, 8.0)
    assert result.transform_flags == 0xFFFF0015


def test_local_basis_transform_strips_scale_and_preserves_translation():
    result = build_scene_light_local_basis_transform((
        (2, 0, 0, 8),
        (0, 4, 0, 9),
        (0, 0, 8, 10),
        (11, 12, 13, 14),
    ))

    assert result == (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (11.0, 12.0, 13.0, 1.0),
    )


def test_owner_transform_composes_record_local_then_owner_row_vector():
    result = compose_scene_light_owner_transform((
        (1, 0, 0, 0),
        (0, 1, 0, 0),
        (0, 0, 1, 0),
        (10, 20, 30, 1),
    ), (
        (0, 1, 0, 0),
        (-1, 0, 0, 0),
        (0, 0, 1, 0),
        (100, 200, 300, 1),
    ))

    assert result == (
        (0.0, 1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (80.0, 210.0, 330.0, 1.0),
    )


def test_owner_transform_bypass_keeps_raw_record_matrix():
    record = (
        (2, 3, 4, 5),
        (6, 7, 8, 9),
        (10, 11, 12, 13),
        (14, 15, 16, 17),
    )

    selected = compose_scene_light_owner_transform(
        record, already_world=True)
    assert selected == tuple(tuple(float(value) for value in row)
                             for row in record)
    assert build_scene_light_resolved_transform(selected).matrix == (
        (2.0, 3.0, 4.0, 0.0),
        (6.0, 7.0, 8.0, 0.0),
        (10.0, 11.0, 12.0, 0.0),
        (14.0, 15.0, 16.0, 1.0),
    )


def test_owner_transform_requires_external_matrix_for_composition():
    with pytest.raises(ValueError, match='owner transform'):
        compose_scene_light_owner_transform(((1, 0, 0, 0),) * 4)


def test_owner_transform_selector_matches_native_source_priority():
    embedded = ((1, 2, 3, 4),) * 4
    holder = ((5, 6, 7, 8),) * 4
    fallback = ((9, 10, 11, 12),) * 4

    assert select_scene_light_owner_transform(
        holder, fallback, already_world=True, embedded_transform=embedded,
        use_embedded_override=True) == tuple(
            tuple(float(value) for value in row) for row in embedded)
    assert select_scene_light_owner_transform(
        holder, fallback, already_world=True) == tuple(
            tuple(float(value) for value in row) for row in fallback)
    assert select_scene_light_owner_transform(holder, fallback) == tuple(
        tuple(float(value) for value in row) for row in holder)
    assert select_scene_light_owner_transform(None, fallback) == tuple(
        tuple(float(value) for value in row) for row in fallback)


def test_owner_transform_selector_requires_the_selected_source():
    with pytest.raises(ValueError, match='Embedded scene-light'):
        select_scene_light_owner_transform(
            use_embedded_override=True)
    with pytest.raises(ValueError, match='Runtime fallback'):
        select_scene_light_owner_transform(already_world=True)
    with pytest.raises(ValueError, match='Runtime fallback'):
        select_scene_light_owner_transform()


def test_scene_light_definition_resolves_flat_serialized_matrix():
    raw = light_bytes(light_type=1)
    struct.pack_into('<16f', raw, 0,
                     2, 0, 0, 0,
                     0, 4, 0, 0,
                     0, 0, 8, 0,
                     11, 12, 13, 1)

    assert parse_scene_light_definition(raw).local_basis_transform() == (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (11.0, 12.0, 13.0, 1.0),
    )


def test_local_basis_transform_preserves_mirrored_axis_orientation():
    result = build_scene_light_local_basis_transform((
        (-2, 0, 0, 0),
        (0, 4, 0, 0),
        (0, 0, 8, 0),
        (0, 0, 0, 1),
    ))

    assert result[:3] == (
        (-1.0, -0.0, -0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
    )


def test_local_basis_transform_uses_identity_axes_for_degenerate_source():
    assert build_scene_light_local_basis_transform((
        (0, 0, 0, 0),
        (0, 0, 0, 0),
        (0, 0, 0, 0),
        (3, 4, 5, 0),
    )) == (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (3.0, 4.0, 5.0, 1.0),
    )


def test_local_basis_transform_matches_nontrivial_float32_oracle():
    result = build_scene_light_local_basis_transform((
        (1.25, -2.5, .75, 7),
        (3.5, 4.25, -1.5, 8),
        (-2.25, .5, 5.75, 9),
        (123.125, -456.5, .03125, 99),
    ))
    bits = struct.unpack(
        '<16I', struct.pack('<16f', *(value for row in result for value in row)))

    assert bits == (
        0x3F47A956, 0xBF04C701, 0x3EB35938, 0,
        0x3F1D0495, 0x3F3EAA22, 0xBE869636, 0,
        0xBDFF1557, 0x3ED6F8B6, 0x3F6624CA, 0,
        0x42F64000, 0xC3E44000, 0x3D000000, 0x3F800000,
    )


@pytest.mark.parametrize('matrix', [
    ((1, 0, 0, 0),) * 3,
    ((1, 0, 0, 0, 0),) * 4,
    ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, float('nan'), 0),
     (0, 0, 0, 1)),
])
def test_local_basis_transform_rejects_invalid_matrices(matrix):
    with pytest.raises(ValueError, match='transform'):
        build_scene_light_local_basis_transform(matrix)


def test_resolved_transform_classifies_before_normalizing_homogeneous_values():
    result = build_scene_light_resolved_transform((
        (1, 0, 0, 3),
        (0, 1, 0, 0),
        (0, 0, 1, 0),
        (10, 20, 30, 9),
    ))

    assert result.axis_scales == (3.1622776985168457, 1.0, 1.0)
    assert result.transform_flags == 0x11
    assert tuple(row[3] for row in result.matrix) == (0.0, 0.0, 0.0, 1.0)


def test_type_1_runtime_transfer_rejects_other_native_subtypes():
    light = parse_scene_light_definition(light_bytes(light_type=2))
    with pytest.raises(ValueError, match='native light type 1'):
        build_scene_light_type_1_runtime_transfer(light)
