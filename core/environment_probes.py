"""Cooked zone probe resources recovered from the retail zone loader.

See docs/ENVIRONMENT_PROBES.md for executable anchors. Positions and axes are
zone-local; applying the owning zone transform is a separate runtime step.
This inventories resource dependencies, not rendered or blended probe cubes.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct

from core.archive import DAT1


TAG_PROBES = 0x557013E9
TAG_PROBE_TEXTURES = 0x027795C5
TAG_PROBE_DRAW_LISTS = 0x2D1E19C6
PROBE_RECORD_SIZE = 128


@dataclass(frozen=True)
class ProbeTexture:
    asset_id: int
    path: str | None
    condition_id: int | None


@dataclass(frozen=True)
class ProbeDrawList:
    # Face order is deliberately left numeric until the consumer is traced.
    faces: tuple[tuple[int, ...], ...]
    reserved: bytes


@dataclass(frozen=True)
class ZoneEnvironmentProbe:
    index: int
    instance_id: int
    position: tuple[float, ...]
    axes: tuple[tuple[float, ...], ...]
    texture_index: int
    draw_list_index: int
    textures: tuple[ProbeTexture, ...]
    draw_lists: tuple[ProbeDrawList, ...]
    half_extents: tuple[float, ...]
    capture_offset: tuple[float, ...]
    falloff_negative: tuple[float, ...]
    falloff_positive: tuple[float, ...]
    proxy_negative: tuple[float, ...]
    proxy_positive: tuple[float, ...]
    volume_shape: int
    diffuse_flags: int
    priority: float

    @property
    def source(self) -> str:
        if self.texture_index >= 0 and self.draw_list_index >= 0:
            return 'texture_and_draw_lists'
        if self.texture_index >= 0:
            return 'texture'
        if self.draw_list_index >= 0:
            return 'runtime_draw_lists'
        return 'unbound'


def _require(data, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f'Truncated {label} at byte {offset}: need {size} bytes')


def _texture_slots(dat1: DAT1) -> list[tuple[ProbeTexture, ...]]:
    data = dat1.get_section(TAG_PROBE_TEXTURES)
    if data is None:
        return []
    _require(data, 0, 8, 'probe texture table')
    static_count, conditioned_count = struct.unpack_from('<II', data)
    cursor = 8

    def read_ref(condition_id):
        nonlocal cursor
        _require(data, cursor, 16, 'probe texture reference')
        asset_id, path_offset, _type_id = struct.unpack_from('<QII', data, cursor)
        cursor += 16
        return ProbeTexture(asset_id, dat1.get_string(path_offset), condition_id)

    _require(data, cursor, static_count * 16, 'static probe textures')
    slots = [(read_ref(None),) for _ in range(static_count)]
    _require(data, cursor, 4, 'probe lighting condition count')
    condition_count = struct.unpack_from('<I', data, cursor)[0]
    cursor += 4
    # The retail loader accepts an unconditioned block or five lighting states.
    if condition_count not in (0, 5):
        raise ValueError(f'Unsupported probe lighting condition count: {condition_count}')
    _require(data, cursor, condition_count * 4, 'probe lighting conditions')
    conditions = struct.unpack_from(f'<{condition_count}I', data, cursor)
    cursor = (cursor + condition_count * 4 + 7) & ~7
    _require(data, cursor, max(1, condition_count) * conditioned_count * 16,
             'conditioned probe textures')
    variants: list[list[ProbeTexture]] = [[] for _ in range(conditioned_count)]
    for condition_id in conditions or (None,):
        for variant in variants:
            variant.append(read_ref(condition_id))
    slots.extend(tuple(variant) for variant in variants)
    return slots


def _draw_list_pairs(dat1: DAT1) -> list[tuple[ProbeDrawList, ...]]:
    data = dat1.get_section(TAG_PROBE_DRAW_LISTS)
    if data is None:
        return []
    _require(data, 0, 2, 'probe draw-list count')
    pair_count = struct.unpack_from('<H', data)[0]
    cursor = 2
    pairs = []
    for _ in range(pair_count):
        pair = []
        # Each probe has two consecutive six-face lists (models / impostors).
        for _ in range(2):
            _require(data, cursor, 16, 'probe draw-list header')
            counts = struct.unpack_from('<6H', data, cursor)
            reserved = bytes(data[cursor + 12:cursor + 16])
            cursor += 16
            _require(data, cursor, sum(counts) * 8, 'probe draw-list IDs')
            faces = []
            for count in counts:
                faces.append(struct.unpack_from(f'<{count}Q', data, cursor))
                cursor += count * 8
            pair.append(ProbeDrawList(tuple(faces), reserved))
        pairs.append(tuple(pair))
    return pairs


def parse_zone_environment_probes(data: bytes) -> list[ZoneEnvironmentProbe]:
    """Decode verified record fields and resolve texture/draw-list indices.

    IDs in draw lists identify scene instances, not model asset hashes. Do not
    look them up in the TOC as if they were directly loadable cubemap resources.
    """
    dat1 = DAT1(data)
    records = dat1.get_section(TAG_PROBES)
    if records is None:
        return []
    if len(records) % PROBE_RECORD_SIZE:
        raise ValueError('Probe section size is not a multiple of 128 bytes')
    textures = _texture_slots(dat1)
    draw_lists = _draw_list_pairs(dat1)
    probes = []
    for index in range(len(records) // PROBE_RECORD_SIZE):
        offset = index * PROBE_RECORD_SIZE
        position = struct.unpack_from('<3f', records, offset)
        axes = tuple(struct.unpack_from('<3f', records, offset + 12 + axis * 12)
                     for axis in range(3))
        texture_index, draw_index = struct.unpack_from('<hh', records, offset + 0x74)
        instance_id = struct.unpack_from('<Q', records, offset + 0x78)[0]
        for name, value, slots in [('texture', texture_index, textures),
                                   ('draw list', draw_index, draw_lists)]:
            if value < -1 or value >= len(slots):
                raise ValueError(f'Probe {index}: invalid {name} index {value}')
        probes.append(ZoneEnvironmentProbe(
            index, instance_id, position, axes, texture_index, draw_index,
            textures[texture_index] if texture_index >= 0 else (),
            draw_lists[draw_index] if draw_index >= 0 else (),
            struct.unpack_from('<3f', records, offset + 0x30),
            struct.unpack_from('<3f', records, offset + 0x3C),
            struct.unpack_from('<3f', records, offset + 0x48),
            struct.unpack_from('<3f', records, offset + 0x54),
            struct.unpack_from('<3e', records, offset + 0x60),
            struct.unpack_from('<3e', records, offset + 0x66),
            records[offset + 0x6C], records[offset + 0x6D],
            struct.unpack_from('<f', records, offset + 0x70)[0],
        ))
    return probes
