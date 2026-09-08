"""Cooked light-grid index and first-stage brick decoder.

The executable's 0x1410A06A0 decodes authored records and marks missing cells.
The wrapper 0x14109DA40 can interpolate those cells afterward. This module
preserves that distinction: its output is not automatically a resident grid.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import struct

import numpy as np

from core.archive import DAT1


@dataclass(frozen=True)
class LightGridAssetIndex:
    positions: np.ndarray
    stream_offsets: np.ndarray | None
    header_words: tuple[int, int]


def _stream_offsets(data: bytes | memoryview, count: int) -> np.ndarray:
    if len(data) != (count + 1) * 4:
        raise ValueError('The light-grid stream index needs one more offset than positions')
    offsets = np.frombuffer(data, dtype='<u4')
    if offsets[0] != 0 or np.any(offsets[1:] < offsets[:-1]):
        raise ValueError('Light-grid stream offsets must start at zero and increase')
    return offsets


def parse_light_grid_asset_index(data: bytes) -> LightGridAssetIndex:
    if data[:4] == b'1TAD':
        origin = 0
    elif len(data) >= 52 and data[36:40] == b'1TAD':
        origin = 36
    else:
        raise ValueError('Expected light-grid DAT1 metadata, optionally after its 36-byte header')
    if len(data) < origin + 16:
        raise ValueError('Truncated light-grid metadata header')
    metadata_size = struct.unpack_from('<I', data, origin + 8)[0]
    asset = _checked_dat1(data[origin:origin + metadata_size])
    if asset.unk1 != 0xFA8D90B3:
        raise ValueError('Expected a retail zonelightbin asset (FA8D90B3)')
    header = asset.get_section(0x101A2196)
    positions = asset.get_section(0x27204B67)
    if header is None or len(header) != 8 or positions is None or len(positions) % 12:
        raise ValueError('Invalid light-grid header or 12-byte position table')
    coordinates = np.frombuffer(positions, dtype='<f4').reshape(-1, 3)
    if len(coordinates) > 65535 or not np.isfinite(coordinates).all():
        raise ValueError('Invalid light-grid position count or coordinates')
    offset_data = asset.get_section(0xC72A514C)
    offsets = None
    if offset_data is not None:
        offsets = _stream_offsets(offset_data, len(coordinates))
    return LightGridAssetIndex(coordinates, offsets, struct.unpack('<2I', header))


def _decompress_grid_data(data: bytes, max_size: int) -> bytes:
    """Strict, bounded LZ block used by the retail inline-grid worker.

    Unlike the archive preview decoder, truncated literals/matches and invalid
    back references must fail rather than leave zero-filled output samples.
    """
    output = bytearray()
    cursor = 0

    def length(value: int) -> int:
        nonlocal cursor
        if value == 15:
            while True:
                if cursor >= len(data):
                    raise ValueError('Truncated light-grid compressed length')
                extension = data[cursor]
                cursor += 1
                value += extension
                if value > max_size:
                    raise ValueError('Light-grid decompression exceeds its brick-size bound')
                if extension != 255:
                    break
        return value

    while cursor < len(data):
        token = data[cursor]
        cursor += 1
        literal_count = length(token >> 4)
        if cursor + literal_count > len(data):
            raise ValueError('Truncated light-grid compressed literals')
        if len(output) + literal_count > max_size:
            raise ValueError('Light-grid decompression exceeds its brick-size bound')
        output.extend(data[cursor:cursor + literal_count])
        cursor += literal_count
        if cursor == len(data):
            break
        if cursor + 2 > len(data):
            raise ValueError('Truncated light-grid match offset')
        distance = struct.unpack_from('<H', data, cursor)[0]
        cursor += 2
        if not 0 < distance <= len(output):
            raise ValueError('Invalid light-grid compressed back reference')
        match_count = length(token & 15) + 4
        if len(output) + match_count > max_size:
            raise ValueError('Light-grid decompression exceeds its brick-size bound')
        # Repetition also handles matches overlapping their source range.
        pattern = output[-distance:]
        repeats, remainder = divmod(match_count, distance)
        output.extend(pattern * repeats + pattern[:remainder])
    return bytes(output)


def _checked_dat1(data: bytes) -> DAT1:
    if len(data) < 16 or struct.unpack_from('<I', data)[0] != 0x44415431:
        raise ValueError('Invalid light-grid DAT1 header')
    _, _, total, count, unknown = struct.unpack_from('<IIIHH', data)
    end = 16 + count * 12 + unknown * 8
    if total != len(data) or end > total:
        raise ValueError('Truncated or oversized light-grid DAT1')
    seen = set()
    for i in range(count):
        tag, offset, size = struct.unpack_from('<3I', data, 16 + i * 12)
        if tag in seen or offset < end or offset + size > total:
            raise ValueError('Invalid light-grid DAT1 section range or duplicate tag')
        seen.add(tag)
    return DAT1(data)


@dataclass(frozen=True)
class CookedLightGridAsset:
    index: LightGridAssetIndex
    stream: bytes
    storage: str


def load_light_grid_asset(data: bytes, stream: bytes | None = None) -> CookedLightGridAsset:
    """Resolve a separate streamed span or the compressed inline DAT1 payload.

    Inline assets retain their 36-byte outer header: metadata length at +4,
    compressed length at +8. The worker at 0x1410A77A0 decompresses a second
    DAT1 containing C72A514C offsets and the 13F4AF3B brick stream.
    """
    index = parse_light_grid_asset_index(data)
    if index.stream_offsets is not None:
        if stream is None:
            raise ValueError('This light-grid asset requires its separate streamed span')
        result = CookedLightGridAsset(index, stream, 'separate_stream')
    else:
        if stream is not None:
            raise ValueError('An inline light-grid asset must not use a separate stream')
        if len(data) < 52 or struct.unpack_from('<I', data)[0] != 0xFA8D90B3:
            raise ValueError('Inline light-grid data requires the original 36-byte outer header')
        metadata_size, compressed_size = struct.unpack_from('<2I', data, 4)
        payload_offset = 36 + metadata_size
        if metadata_size < 16 or payload_offset + compressed_size != len(data):
            raise ValueError('Inline light-grid sizes do not match the asset length')
        _checked_dat1(data[36:payload_offset])
        # 4096 fully custom cells are the largest encoded brick. Allow a
        # bounded directory/padding overhead in the enclosing data container.
        max_size = len(index.positions) * (1024 + 16 * 4096 + 4) + 65536
        expanded = _decompress_grid_data(data[payload_offset:], max_size)
        inner = _checked_dat1(expanded)
        if inner.unk1 != 0xFA8D90B3:
            raise ValueError('Unexpected inline light-grid data type')
        offsets = inner.get_section(0xC72A514C)
        bricks = inner.get_section(0x13F4AF3B)
        if offsets is None or bricks is None:
            raise ValueError('Inline light-grid data is missing offsets or brick bytes')
        index = replace(index, stream_offsets=_stream_offsets(offsets, len(index.positions)))
        result = CookedLightGridAsset(index, bytes(bricks), 'inline_compressed')
    if int(result.index.stream_offsets[-1]) != len(result.stream):
        raise ValueError('The final light-grid offset does not match the stream size')
    return result


@dataclass(frozen=True)
class DecodedLightGridBrick:
    records: np.ndarray
    cell_kinds: np.ndarray
    unresolved_indices: np.ndarray
    authored_count: int
    average_scale_exponent_code: float


def decode_light_grid_brick(data: bytes) -> DecodedLightGridBrick:
    """Decode exactly one indexed brick before optional missing-cell filling.

    Cell kinds 0/1 retain retail sentinel words; they are not black samples.
    Each brick expands to 4096 uint4 records in x-fastest order.
    """
    if len(data) < 1024:
        raise ValueError('A light-grid brick needs its 1024-byte cell-kind map')
    packets = np.frombuffer(data, dtype='<u8', count=128)
    shifts = np.arange(62, -1, -2, dtype=np.uint64)
    kinds = ((packets[:, None] >> shifts) & 3).astype(np.uint8).reshape(-1)
    authored = np.flatnonzero(kinds >= 2)
    custom = np.flatnonzero(kinds == 3)
    count = len(authored)
    expected = 1024 + 13 * count + 3 * len(custom)
    if len(data) != expected:
        raise ValueError(f'Light-grid brick has {len(data)} bytes; its cell map requires {expected}')
    records = np.zeros((4096, 4), dtype=np.uint32)
    records[kinds == 0, 3] = 0x83F80000
    records[kinds == 1, 3] = 0x8008003F
    lanes = np.frombuffer(data, dtype='<u2', count=count * 6, offset=1024).reshape(6, count).astype(np.uint32)
    records[authored, :3] = (lanes[::2] | (lanes[1::2] << 16)).T
    records[kinds == 2, 3] = 0x83F8003F
    scales = np.frombuffer(data, dtype=np.uint8, count=count, offset=1024 + count * 12)
    packed_planes = np.frombuffer(data, dtype=np.uint8, count=len(custom) * 3,
                                  offset=1024 + count * 13).reshape(-1, 3).astype(np.uint32)
    records[custom, 3] = ((packed_planes[:, 0] << 24) | (packed_planes[:, 1] << 16)
                          | (packed_planes[:, 2] << 8) | packed_planes[:, 2]) & 0xFFFFC03F
    records[authored, 3] |= scales.astype(np.uint32) << 6
    mean_code = float(np.float32(np.sum(scales >> 4, dtype=np.uint32)) / np.float32(max(count, 1)))
    return DecodedLightGridBrick(records, kinds, np.flatnonzero(kinds < 2), count, mean_code)
