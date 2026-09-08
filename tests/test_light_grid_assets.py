import struct

import numpy as np
import pytest

from core.light_grid_assets import (
    _decompress_grid_data, decode_light_grid_brick, load_light_grid_asset,
    parse_light_grid_asset_index,
)


def _dat1(sections):
    start = 16 + len(sections) * 12
    directory, body = bytearray(), bytearray()
    for tag, data in sections.items():
        directory.extend(struct.pack('<3I', tag, start + len(body), len(data)))
        body.extend(data)
    return struct.pack('<IIIHH', 0x44415431, 0xFA8D90B3, start + len(body), len(sections), 0) + directory + body


def _inline_asset(payload=None):
    metadata = _dat1({0x101A2196: bytes(8), 0x27204B67: struct.pack('<3f', -232, 8, 664)})
    if payload is None:
        payload = _dat1({0xC72A514C: struct.pack('<2I', 0, 1024), 0x13F4AF3B: bytes(1024)})
    # A single literal sequence; real game blocks additionally use back references.
    repeats, tail = divmod(len(payload) - 15, 255)
    compressed = bytes([0xF0]) + bytes([255]) * repeats + bytes([tail]) + payload
    return struct.pack('<9I', 0xFA8D90B3, len(metadata), len(compressed), 0, 0, 0, 0, 0, 0) + metadata + compressed


def test_inline_and_separate_storage_resolve_the_same_brick():
    inline = load_light_grid_asset(_inline_asset())
    assert inline.storage == 'inline_compressed'
    np.testing.assert_array_equal(inline.index.positions, [[-232, 8, 664]])
    np.testing.assert_array_equal(inline.index.stream_offsets, [0, 1024])
    separate = _dat1({0x101A2196: bytes(8), 0x27204B67: struct.pack('<3f', -232, 8, 664),
                      0xC72A514C: struct.pack('<2I', 0, 1024)})
    assert load_light_grid_asset(separate, bytes(1024)).stream == inline.stream
    assert decode_light_grid_brick(inline.stream).authored_count == 0
    with pytest.raises(ValueError, match='separate streamed span'):
        load_light_grid_asset(separate)
    with pytest.raises(ValueError, match='must not use a separate stream'):
        load_light_grid_asset(_inline_asset(), bytes(1024))
    with pytest.raises(ValueError, match='final light-grid offset'):
        load_light_grid_asset(separate, bytes(1023))


def test_compressed_grid_match_may_overlap_its_source():
    assert _decompress_grid_data(b'\x32abc\x03\x00\x10d', 10) == b'abcabcabcd'


@pytest.mark.parametrize('compressed', [b'\xf0', b'\x20a', b'\x00\x00\x00', b'\x10a\x02\x00',
                                         b'\x10a\x01', b'\x1fa\x01\x00', b'\xf0\xff'])
def test_compressed_grid_rejects_truncation_and_invalid_distances(compressed):
    with pytest.raises(ValueError):
        _decompress_grid_data(compressed, 4096)


def test_inline_grid_rejects_outer_and_inner_size_mismatches():
    with pytest.raises(ValueError, match='asset length'):
        load_light_grid_asset(_inline_asset()[:-1])
    broken = bytearray(_dat1({0xC72A514C: struct.pack('<2I', 0, 1024), 0x13F4AF3B: bytes(1024)}))
    struct.pack_into('<I', broken, 8, len(broken) + 1)
    with pytest.raises(ValueError, match='DAT1'):
        load_light_grid_asset(_inline_asset(broken))
    with pytest.raises(ValueError, match='brick-size bound'):
        _decompress_grid_data(b'\x1fa\x01\x00\xff\x00', 32)


def test_cell_map_is_msb_first_inside_little_endian_64_bit_packets():
    # First packet starts 0,1,2,3; the other 4092 entries are zero.
    kinds = struct.pack('<Q', (1 << 60) | (2 << 58) | (3 << 56)) + bytes(1016)
    # Two authored cells, six independent halfword planes, then two scale bytes.
    planes = struct.pack('<12H', 1, 11, 2, 12, 3, 13, 4, 14, 5, 15, 6, 16)
    brick = decode_light_grid_brick(kinds + planes + bytes([0xA4, 0xB5, 0x12, 0x34, 0x56]))
    np.testing.assert_array_equal(brick.cell_kinds[:5], [0, 1, 2, 3, 0])
    np.testing.assert_array_equal(brick.records[:2, 3], [0x83F80000, 0x8008003F])
    np.testing.assert_array_equal(brick.records[2, :3], [0x00020001, 0x00040003, 0x00060005])
    np.testing.assert_array_equal(brick.records[3, :3], [0x000C000B, 0x000E000D, 0x0010000F])
    assert brick.records[2, 3] == 0x83F8293F
    assert brick.records[3, 3] == 0x12346D56
    assert brick.authored_count == 2
    assert len(brick.unresolved_indices) == 4094
    assert brick.average_scale_exponent_code == 10.5


@pytest.mark.parametrize('raw', [bytes(1023), bytes(1025), b'\xff' * 1024])
def test_brick_rejects_incomplete_or_unexpected_payload(raw):
    with pytest.raises(ValueError):
        decode_light_grid_brick(raw)


def test_index_positions_and_stream_ranges():
    sections = {
        0x101A2196: struct.pack('<2I', 0, 1),
        0x27204B67: struct.pack('<6f', 8, 8, 8, 24, 8, 8),
        0xC72A514C: struct.pack('<3I', 0, 1024, 2048),
    }
    directory, body = bytearray(), bytearray()
    for tag, data in sections.items():
        directory.extend(struct.pack('<3I', tag, 52 + len(body), len(data)))
        body.extend(data)
    raw = struct.pack('<IIIHH', 0x44415431, 0xFA8D90B3, 52 + len(body), 3, 0) + directory + body
    index = parse_light_grid_asset_index(raw)
    np.testing.assert_array_equal(index.positions, [[8, 8, 8], [24, 8, 8]])
    np.testing.assert_array_equal(index.stream_offsets, [0, 1024, 2048])
    assert index.header_words == (0, 1)
    damaged = bytearray(raw)
    struct.pack_into('<I', damaged, 8, len(raw) - 1)
    with pytest.raises(ValueError, match='section range'):
        parse_light_grid_asset_index(damaged)
