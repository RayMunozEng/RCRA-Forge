"""Explicit light-grid resource construction from verified runtime operations.

Callers choose the bricks and fade bytes. This module does not infer active
levels, lighting conditions, priorities or streaming state. Slots are compacted
for replay; they are not asserted to equal slots from a captured frame.
"""
from __future__ import annotations

from dataclasses import dataclass
import operator

import numpy as np


def light_grid_lookup_address(position) -> int:
    """Retail 0x1410A1850: hash a brick position into the 64^3 lookup ring."""
    point = np.asarray(position, dtype=np.float32)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError('A light-grid position must be a finite float3')
    cell = np.floor(point * np.float32(1 / 16))
    if np.any(cell.astype(np.float64) < -(2**31)) or np.any(cell.astype(np.float64) >= 2**31):
        raise ValueError('Light-grid brick coordinates must fit signed 32-bit integers')
    x, y, z = cell.astype(np.int64) & 63
    return int(x | (y << 6) | (z << 12))


def pack_light_grid_lookup(slot: int, fade: int) -> int:
    """Retail 0x1410A1920: resident uint16 slot and uint8 fade to a GPU word.

    Fade 255 is fully present, 0 fully fallback. Hair subsequently masks the
    low word with 0x3FC; retain the original integer conversion here.
    """
    try:
        slot, fade = operator.index(slot), operator.index(fade)
    except TypeError as error:
        raise ValueError('Light-grid slot and fade must be integers') from error
    if not 0 <= slot <= 65535 or not 0 <= fade <= 255:
        raise ValueError('Light-grid slot/fade must fit uint16/uint8')
    return (slot << 12) | ((0xF00F - 0xF1 * fade) >> 6)


def should_replace_light_grid_brick(current_position, current_priority: int,
                                    candidate_position, candidate_priority: int,
                                    camera_position=None) -> bool:
    """Retail 0x1410A2160's decision for two valid entries sharing a ring cell.

    Existing bricks have a 512-unit Chebyshev retention radius; candidates
    have a 409.6-unit entry radius. Otherwise higher priority wins, with ties
    retaining the current entry. Empty/stale-slot handling is separate.
    """
    try:
        current_priority, candidate_priority = map(operator.index, (current_priority, candidate_priority))
    except TypeError as error:
        raise ValueError('Light-grid priorities must be integers') from error
    if not 0 <= current_priority <= 15 or not 0 <= candidate_priority <= 15:
        raise ValueError('Light-grid priorities must fit the resident four-bit field')
    if camera_position is not None:
        points = np.asarray([current_position, candidate_position, camera_position], dtype=np.float32)
        if points.shape != (3, 3) or not np.isfinite(points).all():
            raise ValueError('Light-grid positions and camera must be finite float3 values')
        distance = np.max(np.abs(points[:2] - points[2]), axis=1)
        current_near = distance[0] < np.float32(512)
        candidate_near = distance[1] < np.float32(409.6)
        if current_near != candidate_near:
            return bool(candidate_near)
    return candidate_priority > current_priority


@dataclass(frozen=True)
class LightGridResources:
    lookup: np.ndarray
    data: np.ndarray
    brick_lookup_addresses: np.ndarray
    fallback_slot: int


def build_light_grid_resources(positions, records, fades, fallback_record) -> LightGridResources:
    """Build t50/t51 from an explicit, already interpolated brick selection.

    Stored positions are used directly in the traced retail path. This helper
    requires 16-unit brick centers and rejects ring collisions instead of
    guessing priority/residency. The fallback record is supplied explicitly.
    """
    points = np.asarray(positions, dtype=np.float32)
    values = np.asarray(records)
    alpha = np.asarray(fades)
    fallback = np.asarray(fallback_record)
    if points.ndim != 2 or points.shape[1:] != (3,) or not np.isfinite(points).all():
        raise ValueError('Light-grid positions must have shape (B, 3) and be finite')
    count = len(points)
    if count > 65535:
        raise ValueError('Too many bricks for uint16 slots plus the fallback slot')
    if np.any(np.remainder(points - 8, 16) != 0):
        raise ValueError('Light-grid positions must be centers on the 16-unit lattice')
    if values.shape != (count, 4096, 4) or values.dtype.kind != 'u' or values.dtype.itemsize != 4:
        raise ValueError('Light-grid records must be uint32 with shape (B, 4096, 4)')
    if alpha.shape != (count,) or alpha.dtype.kind not in 'iu' or np.any(alpha < 0) or np.any(alpha > 255):
        raise ValueError('Supply one integer fade byte for each brick')
    if fallback.shape != (4,) or fallback.dtype.kind != 'u' or fallback.dtype.itemsize != 4:
        raise ValueError('Supply an explicit uint32 fallback record with shape (4,)')
    addresses = np.array([light_grid_lookup_address(p) for p in points], dtype=np.uint32)
    if len(np.unique(addresses)) != count:
        raise ValueError('Selected bricks collide in the lookup ring; resolve runtime selection first')
    lookup = np.full(64**3, pack_light_grid_lookup(count, 0), dtype=np.uint32)
    lookup[addresses] = [pack_light_grid_lookup(i, fade) for i, fade in enumerate(alpha)]
    data = np.empty(((count + 1) * 4096, 4), dtype=np.uint32)
    data[:count * 4096] = values.reshape(-1, 4)
    data[count * 4096:] = fallback
    return LightGridResources(lookup, data, addresses, count)
