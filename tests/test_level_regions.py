"""Level topology must retain catalogue indices and runtime replacement lists."""
import struct
from dataclasses import replace

import pytest

from core.level import LevelParser


def _level(mutate=None):
    strings = ['tile.region', 'world.region', 'one.zone', 'two.zone', 'checkpoint']
    pool, offsets = b'', []
    for text in strings:
        offsets.append(16 + 9*12 + len(pool))
        pool += text.encode() + b'\0'
    header = struct.pack('<3I6I', 0, 0, 0, 2, 4, 1, 2, 1, 0)
    root = struct.pack('<Q14h', 10, 4, 1, -1, -1, 1, 1, 0, 2, -1, 0, -1, 0, -1, 0)
    tile = struct.pack('<Q14h', 11, 6, 0, 0, 0, -1, 0, 2, 1, 3, 1, 0, 1, -1, 0)
    checkpoint = struct.pack('<3QI4h3f', 20, 0, 0, 0, 0, 1, -1, 0, 1, 2, 3)
    sections = {
        0x7CA7267D: header,
        0x4E023760: struct.pack('<QhHQhH', 1, 0, 0, 2, 1, 0),
        0x2BA33702: struct.pack('<2I', *offsets[2:4]),
        0x396F9418: root + tile,
        0x4130D903: struct.pack('<2I', *offsets[:2]),
        0xC30D92B6: struct.pack('<3f3I', 10, 0, 30, 4, 5, 6),
        0x95F91E24: struct.pack('<4h', 1, 0, 0, -1),
        0x3395AEC1: checkpoint,
        0x2236C47A: struct.pack('<I', offsets[4]),
    }
    if mutate: mutate(sections)
    cursor = 16 + 9*12
    directory, body = bytearray(), bytearray(pool)
    for tag, raw in sections.items():
        directory.extend(struct.pack('<III', tag, cursor+len(body), len(raw)))
        body.extend(raw)
    return bytes(36) + struct.pack('<IIIHH', 0x44415431, 0x587B60A6, cursor+len(body), 9, 0) + directory + body


def test_level_regions_keep_topology_names_bounds_and_replacements():
    level = LevelParser(_level()).parse_info()
    root, tile = level.regions
    assert (root.name, tile.name) == ('world.region', 'tile.region')
    assert root.child_indices == (1,) and tile.parent_index == 0
    assert root.zone_indices == (1, 0) and tile.zone_indices == (0,)
    assert root.replacement_zone_indices == () and tile.replacement_zone_indices == (-1,)
    assert struct.unpack('<3f3I', tile.bounds_data) == (10, 0, 30, 4, 5, 6)
    assert tile.checkpoint_indices == (0,)
    checkpoint = level.checkpoints[0]
    assert (checkpoint.name, checkpoint.region_index, checkpoint.position) == ('checkpoint', 1, (1, 2, 3))
    assert level.region_zone_candidates([1]) == (0, 1)
    assert level.region_zone_candidates([1], include_parents=False) == (0,)
    assert level.region_zone_candidates([0, 1]) == (1, 0)
    # The retail kind-4 selector iterates the root's child range and consumes
    # child primary lists; the root's own (1, 0) list is a different input.
    assert level.streaming_region_zone_candidates(0) == (0,)
    with pytest.raises(ValueError, match='not kind 4'):
        level.streaming_region_zone_candidates(1)
    level.regions[1] = replace(tile, kind=3)
    assert level.dependency_region_zone_candidates(1) == (1, 0)
    with pytest.raises(ValueError, match='not kind 3 or 5'):
        level.dependency_region_zone_candidates(0)


@pytest.mark.parametrize('tag,offset,value', [
    (0x396F9418, 0x0E, 5),  # Parent beyond the catalogue.
    (0x396F9418, 0x0C, 1),  # Bounds beyond the table.
    (0x396F9418, 0x12, 9),  # Child range overrun.
    (0x396F9418, 0x16, 5),  # Zone-index range overrun.
    (0x95F91E24, 0, -1),    # Sentinel valid only in replacement slots.
    (0x95F91E24, 0, 2),     # Invalid primary zone catalogue index.
    (0x95F91E24, 6, -2),    # Invalid replacement sentinel.
    (0x3395AEC1, 0x1E, 2),  # Checkpoint points outside the region catalogue.
])
def test_invalid_level_topology_is_rejected(tag, offset, value):
    def mutate(sections):
        raw = bytearray(sections[tag])
        struct.pack_into('<h', raw, offset, value)
        sections[tag] = raw
    with pytest.raises(ValueError):
        LevelParser(_level(mutate)).parse_info()


def test_region_dependency_query_rejects_cycles_and_missing_regions():
    level = LevelParser(_level()).parse_info()
    with pytest.raises(ValueError, match='region index'):
        level.region_zone_candidates([2])
    level.regions[0] = replace(level.regions[0], parent_index=1)
    with pytest.raises(ValueError, match='Cycle'):
        level.region_zone_candidates([1])
