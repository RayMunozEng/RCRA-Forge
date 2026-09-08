"""Hair's packed light grid, recovered from the matching retail DXBC.

The caller supplies the actual lookup/data buffers, global constants and
texture samplers. Cooked zone grids are not interchangeable with the resident
GPU buffers. See docs/ENVIRONMENT_PROBES.md for the evidence and limitations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


def _mad(a, b, c):
    return np.asarray(np.asarray(a, np.float64) * np.asarray(b, np.float64)
                      + np.asarray(c, np.float64), dtype=np.float32)


def _sat(value):
    return np.clip(np.nan_to_num(value, nan=0.0, posinf=1.0, neginf=0.0), 0, 1)


def _vector(value, name):
    result = np.asarray(value, dtype=np.float32)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError(f'{name} must be a finite three-component vector')
    return result


def parse_light_grid_data(data: bytes) -> np.ndarray:
    """Read captured g_LightGridData, uint3 radiance + uint occlusion/scale."""
    if len(data) % 16:
        raise ValueError('Light-grid data must contain whole 16-byte records')
    return np.frombuffer(data, dtype='<u4').reshape(-1, 4)


def light_grid_addresses(world_point) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return eight lookup addresses, in-brick offsets, and fractional position.

    Samples lie at half-integer world coordinates. A 64^3 ring of 16^3 bricks
    wraps signed coordinates, with x varying fastest in both address spaces.
    """
    point = _vector(world_point, 'world_point') - np.float32(.5)
    floored = np.floor(point)
    if np.any(floored.astype(np.float64) < -(2**31)) or np.any(floored.astype(np.float64) > 2**31 - 2):
        raise ValueError('Light-grid coordinates must fit signed 32-bit integers')
    corners = np.array([(i & 1, (i >> 1) & 1, i >> 2) for i in range(8)], np.int64)
    coordinates = floored.astype(np.int64) + corners
    brick = (coordinates >> 4) & 63
    local = coordinates & 15
    lookup = brick[:, 0] | (brick[:, 1] << 6) | (brick[:, 2] << 12)
    offsets = local[:, 0] | (local[:, 1] << 4) | (local[:, 2] << 8)
    return lookup, offsets, point - floored


def _radiance(records, normal, reflection):
    # Each axis word has a positive-direction low half and negative high half.
    # Zero selects the negative half in this branch (and contributes zero).
    shifts = np.where(normal > 0, 0, 16).astype(np.uint32)
    selected = records[:, :3] >> shifts
    channels = np.stack((selected & 63, selected & 1984, selected & 63488), axis=-1)
    squared = normal * normal
    directional = np.asarray(channels, np.float32)
    encoded = _mad(directional[:, 0], squared[0], directional[:, 1] * squared[1])
    encoded = _mad(directional[:, 2], squared[2], encoded)
    chroma = _mad(encoded[:, 1:], np.array([1 / 992, 1 / 31744], np.float32), -1)
    chroma *= np.abs(chroma)
    luma = encoded[:, 0]
    middle = _mad(-chroma[:, 0], luma, luma)
    rgb = np.stack((_mad(chroma[:, 1], luma, middle),
                    _mad(chroma[:, 0], luma, luma),
                    _mad(-chroma[:, 1], luma, middle)), axis=-1)
    selected = records[:, :3] >> np.where(reflection > 0, 0, 16).astype(np.uint32)
    lumas = np.asarray(selected & 63, np.float32)
    weights = reflection * reflection
    scalar = _mad(lumas[:, 2], weights[2], lumas[:, 0] * weights[0] + lumas[:, 1] * weights[1])
    return np.column_stack((rgb, scalar))


@dataclass(frozen=True)
class DistantGI:
    uv_scale_offset: tuple[float, float, float, float]
    irradiance_scale: float
    mid_height: float
    height_scale: float
    height_sample: Callable
    samples: Callable


def _distant_gi(point, normal, reflection, default, gi: DistantGI):
    transform = np.asarray(gi.uv_scale_offset, np.float32)
    uv = _mad(point[[0, 2]], transform[:2], transform[2:])
    height = np.float32(gi.height_sample(uv)) * np.float32(gi.height_scale)
    mid = np.float32(gi.mid_height)
    bias, start, end = (.5, mid, height) if point[1] > mid else (0, np.float32(1), mid)
    with np.errstate(divide='ignore', invalid='ignore'):
        h = _sat(_mad(np.divide(point[1] - start, end - start), .5, bias))
    zs = _mad(h, 2, np.array([.5, 3.5, 6.5, 9.5], np.float32)) * np.float32(1 / 12)
    a, b, c, d = [np.asarray(gi.samples(np.append(uv, z)), np.float32) for z in zs]
    direction_luma = np.where(normal >= 0, a[:3], b[:3])
    reflection_luma = np.where(reflection >= 0, a[:3], b[:3])
    x_chroma = c[:2] if normal[0] >= 0 else d[:2]
    z_chroma = c[2:] if normal[2] >= 0 else d[2:]
    y_chroma = (np.array([a[3], b[3]], np.float32) if normal[1] >= 0
                else ((c[:2] + d[:2]) + c[2:] + d[2:]) * np.float32(.25))
    n2, r2 = normal * normal, reflection * reflection
    luma = _mad(direction_luma[2], n2[2], direction_luma[0] * n2[0] + direction_luma[1] * n2[1])
    refl = _mad(reflection_luma[2], r2[2], reflection_luma[0] * r2[0] + reflection_luma[1] * r2[1])
    chroma = _mad(z_chroma, n2[2], _mad(y_chroma, n2[1], x_chroma * n2[0]))
    chroma = _mad(chroma, 2, -1)
    chroma *= np.abs(chroma)
    luma *= luma
    rgb = _mad(chroma[1], np.array([.621, -.6474, 1.7046], np.float32),
               _mad(luma, 4, chroma[0] * np.array([.9563, -.2721, -1.107], np.float32)))
    scaled = rgb * np.float32(gi.irradiance_scale)
    refl = refl * refl * np.float32(gi.irradiance_scale)
    blend = _sat((point[1] - height) * np.float32(1 / 16))
    output = np.empty(4, np.float32)
    output[:3] = _mad(blend, _mad(-rgb, np.float32(gi.irradiance_scale), default[:3]), scaled)
    output[3] = _mad(blend, _mad(-refl, 4, default[3]), refl * np.float32(4))
    return output


@dataclass(frozen=True)
class LightGridLighting:
    diffuse: np.ndarray
    reflection: float
    fallback_weight: float
    lookup_indices: np.ndarray
    data_indices: np.ndarray
    corner_weights: np.ndarray


def evaluate_light_grid(world_point, shading_normal, reflection, camera_position,
                        lookup, data, *, bleed_reduction: float, grid_intensity: float,
                        ambient_fill, default_sample: Callable,
                        distant_gi: DistantGI | None = None) -> LightGridLighting:
    """Sample the retail Hair light grid, including default/distant GI fallback.

    Directions are the shader's decoded normal and environment reflection;
    this function does not renormalize them. default_sample(direction, mip)
    returns linear RGB. The reflection scalar excludes grid intensity and
    ambient fill, exactly as required by probe specular visibility.
    """
    point = _vector(world_point, 'world_point')
    normal = _vector(shading_normal, 'shading_normal')
    ray = _vector(reflection, 'reflection')
    camera = _vector(camera_position, 'camera_position')
    ambient = _vector(ambient_fill, 'ambient_fill')
    if not np.isfinite([bleed_reduction, grid_intensity]).all():
        raise ValueError('Light-grid constants must be finite')
    lookups, offsets, fraction = light_grid_addresses(point)
    lookup = np.asarray(lookup)
    data = np.asarray(data)
    if lookup.shape != (64**3,) or lookup.dtype.kind != 'u' or lookup.dtype.itemsize != 4:
        raise ValueError('Light-grid lookup must contain 64^3 uint32 words')
    if data.ndim != 2 or data.shape[1] != 4 or data.dtype.kind != 'u' or data.dtype.itemsize != 4:
        raise ValueError('Light-grid data must have shape (record_count, 4), dtype uint32')
    words = lookup[lookups]
    indices = (words & np.uint32(0xFFFFF000)).astype(np.int64) + offsets
    if np.any(indices >= len(data)):
        raise ValueError('Light-grid lookup references a missing data record')
    records = data[indices]
    packed = records[:, 3]
    corners = np.array([(i & 1, (i >> 1) & 1, i >> 2) for i in range(8)], np.float32)
    delta = fraction - corners
    eased = _mad(fraction * fraction, _mad(-fraction, 2, 3), fraction)
    low, high = _mad(-eased, .5, 1), eased * np.float32(.5)
    axis_weights = np.where(corners != 0, high, low)
    trilinear = (axis_weights[:, 1] * axis_weights[:, 0]) * axis_weights[:, 2]
    plane = np.stack((packed >> 26, (packed >> 20) & 63, (packed >> 14) & 63), axis=-1)
    plane = _mad(plane.astype(np.float32), np.float32(8 / 63), -4)
    occlusion = _sat(_mad((packed & 63).astype(np.float32), np.float32(16 / 63),
                          np.sum(plane * delta, axis=-1, dtype=np.float32)) - np.float32(7))
    normal_weight = np.maximum(_sat(np.sum(normal * -delta, axis=-1, dtype=np.float32)),
                               np.float32(bleed_reduction))
    weights = np.maximum((occlusion * trilinear) * normal_weight, np.float32(2**-18))
    total = np.float32(weights[0] + weights[1])
    for value in weights[2:]:
        total = np.float32(total + value)
    inverse_total = np.float32(1) / total
    fallback_values = np.maximum(words & 1020, packed & 960).astype(np.float32)
    fallback = np.float32(weights[0] * fallback_values[0])
    for i in range(1, 8):
        fallback = _mad(weights[i], fallback_values[i], fallback)
    fallback = np.float32(fallback * inverse_total)
    scales = np.exp2(((packed >> 10) & 15).astype(np.float32) - np.float32(10))
    scaled_weights = (weights * scales) * inverse_total
    colors = _radiance(records, normal, ray)
    accumulated = _mad(colors[0], scaled_weights[0], colors[1] * scaled_weights[1])
    for i in range(2, 8):
        accumulated = _mad(colors[i], scaled_weights[i], accumulated)
    lighting = accumulated * np.float32(1 / 63)
    shifted = point - np.float32(.5)
    if np.max(np.abs(shifted[[0, 2]] - camera[[0, 2]])) > 512:
        fallback = max(fallback, np.float32(960))
    if fallback > 0:
        default = np.empty(4, np.float32)
        default[:3] = default_sample(normal, 5)
        default[3] = np.dot(np.asarray(default_sample(ray, 5), np.float32),
                            np.array([.25, .5, .25], np.float32))
        if distant_gi is not None and distant_gi.uv_scale_offset[0] != 0:
            default = _distant_gi(shifted, normal, ray, default, distant_gi)
        fallback = np.float32(fallback * np.float32(1 / 960))
        lighting = _mad(fallback, _mad(-accumulated, np.float32(1 / 63), default), lighting)
    return LightGridLighting(np.maximum(lighting[:3] * np.float32(grid_intensity), ambient),
                             float(lighting[3]), float(fallback), lookups, indices, weights)
