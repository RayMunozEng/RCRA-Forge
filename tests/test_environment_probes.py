import struct

import pytest

from core.environment_probes import (
    TAG_PROBES, TAG_PROBE_DRAW_LISTS, TAG_PROBE_TEXTURES,
    parse_zone_environment_probes,
)


def _zone(sections, pool=b''):
    start = 16 + len(sections) * 12
    payload = bytearray(pool)
    directory = bytearray()
    for tag, data in sections.items():
        while (start + len(payload)) % 16:
            payload.append(0)
        directory.extend(struct.pack('<III', tag, start + len(payload), len(data)))
        payload.extend(data)
    return (struct.pack('<IIIHH', 0x44415431, 0x1F390AA0,
                        start + len(payload), len(sections), 0)
            + directory + payload)


def _probe(texture=-1, draw=-1, instance=0xF123456789ABCDEF):
    result = bytearray(128)
    struct.pack_into('<12f', result, 0, -551, 76, 969,
                     1, 0, 0, 0, 1, 0, 0, 0, 1)
    struct.pack_into('<hhQ', result, 0x74, texture, draw, instance)
    return result


def _draw_pair():
    # First list: three scene instances distributed across faces 0 and 2.
    # Second list: one scene instance on face 1. IDs must remain 64-bit.
    return (struct.pack('<6H4s3Q', 2, 0, 1, 0, 0, 0, b'ABCD',
                        0x8000000000000011, 0x8000000000000012, 0x9000000000000013)
            + struct.pack('<6H4sQ', 0, 1, 0, 0, 0, 0, b'EFGH', 0xA000000000000014))


def test_probe_resources_preserve_condition_major_slots_and_scene_draw_lists():
    # Three sections place the string pool at absolute DAT1 byte 52.
    textures = bytearray(struct.pack('<IIQII', 1, 2, 42, 52, 0))
    textures.extend(struct.pack('<6I', 5, 10, 20, 30, 40, 50))
    for condition in range(1, 6):
        for slot in range(2):
            textures.extend(struct.pack('<QII', condition * 100 + slot, 52, 0))
    raw = _zone({
        TAG_PROBES: _probe(texture=0) + _probe(texture=2) + _probe(draw=0),
        TAG_PROBE_TEXTURES: textures,
        TAG_PROBE_DRAW_LISTS: struct.pack('<H', 1) + _draw_pair(),
    }, b'probe.texture\0')

    static, conditional, runtime = parse_zone_environment_probes(raw)

    assert static.position == (-551, 76, 969)
    assert static.axes == ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    assert static.instance_id == 0xF123456789ABCDEF
    assert static.source == 'texture'
    assert [(t.asset_id, t.path, t.condition_id) for t in static.textures] == [
        (42, 'probe.texture', None),
    ]
    assert [t.asset_id for t in conditional.textures] == [101, 201, 301, 401, 501]
    assert [t.condition_id for t in conditional.textures] == [10, 20, 30, 40, 50]
    assert runtime.source == 'runtime_draw_lists'
    assert runtime.textures == ()
    assert runtime.draw_lists[0].faces == (
        (0x8000000000000011, 0x8000000000000012), (), (0x9000000000000013,), (), (), (),
    )
    assert runtime.draw_lists[1].faces == ((), (0xA000000000000014,), (), (), (), ())
    assert runtime.draw_lists[1].reserved == b'EFGH'


def test_unconditioned_probe_texture_block_uses_aligned_reference():
    textures = struct.pack('<4IQII', 0, 1, 0, 0, 123, 0, 0)
    probe, = parse_zone_environment_probes(_zone({
        TAG_PROBES: _probe(texture=0), TAG_PROBE_TEXTURES: textures,
    }))
    assert probe.textures[0].asset_id == 123
    assert probe.textures[0].condition_id is None


def test_zone_without_probes_is_empty():
    assert parse_zone_environment_probes(_zone({0x3D8DBDB8: bytes(4)})) == []


def test_probe_spatial_fields_keep_directional_float_and_half_float_layouts():
    raw = _probe()
    struct.pack_into('<12f', raw, 0x30,
                     10, 20, 30, 1, 2, 3, 4, 5, 6, 7, 8, 9)
    struct.pack_into('<6eBBHf', raw, 0x60,
                     -10.5, -20.5, -30.5, 40.5, 50.5, 60.5, 2, 0x81, 0, 3.5)
    probe, = parse_zone_environment_probes(_zone({TAG_PROBES: raw}))
    assert probe.half_extents == (10, 20, 30)
    assert probe.capture_offset == (1, 2, 3)
    assert probe.falloff_negative == (4, 5, 6)
    assert probe.falloff_positive == (7, 8, 9)
    assert probe.proxy_negative == (-10.5, -20.5, -30.5)
    assert probe.proxy_positive == (40.5, 50.5, 60.5)
    assert (probe.volume_shape, probe.diffuse_flags, probe.priority) == (2, 0x81, 3.5)


@pytest.mark.parametrize('sections, message', [
    ({TAG_PROBES: bytes(127)}, 'multiple of 128'),
    ({TAG_PROBES: _probe(texture=-2)}, 'invalid texture index'),
    ({TAG_PROBES: _probe(draw=0)}, 'invalid draw list index'),
    ({TAG_PROBES: _probe(draw=0), TAG_PROBE_DRAW_LISTS: b'\x01'}, 'Truncated'),
    ({TAG_PROBES: _probe(draw=0),
      TAG_PROBE_DRAW_LISTS: struct.pack('<H', 1) + _draw_pair()[:-1]}, 'Truncated'),
    ({TAG_PROBES: _probe(texture=0), TAG_PROBE_TEXTURES: struct.pack('<3I', 0, 1, 4)},
     'Unsupported probe lighting condition'),
])
def test_malformed_probe_resources_do_not_produce_partial_success(sections, message):
    with pytest.raises(ValueError, match=message):
        parse_zone_environment_probes(_zone(sections))
