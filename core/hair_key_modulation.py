"""Recovered Hair key-light cloud-shadow coordinate boundary."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class CloudShadowCoordinates:
    """One native cloud-shadow lookup before texture filtering."""

    uv: np.ndarray
    minimum_visibility: float


@dataclass(frozen=True)
class KeyGoboCoordinates:
    """One native key-light gobo lookup before texture filtering."""

    uv: np.ndarray


@dataclass(frozen=True)
class KeyShadowVolumeRange:
    """Cascade-selected first/count pair for key-light shadow volumes."""

    cascade: int
    first: int
    count: int


def cloud_shadow_coordinates(
        world_point, camera_position, key_world_to_light,
        cloud_constants) -> CloudShadowCoordinates | None:
    """Return the retail cloud-shadow UV, or ``None`` when disabled.

    ``key_world_to_light`` contains world-cbuffer rows 19..21. The shader uses
    camera-relative X/Z with absolute world Y for this periodic projection.
    ``cloud_constants`` is world-cbuffer row 41.
    """
    point = np.asarray(world_point, dtype=np.float32)
    camera = np.asarray(camera_position, dtype=np.float32)
    transform = np.asarray(key_world_to_light, dtype=np.float32)
    constants = np.asarray(cloud_constants, dtype=np.float32)
    if point.shape != (3,) or camera.shape != (3,):
        raise ValueError('Cloud-shadow world point and camera must be float3')
    if transform.shape != (3, 4) or constants.shape != (4,):
        raise ValueError('Cloud-shadow transform must be 3x4 and constants float4')
    if not all(np.isfinite(value).all() for value in (
            point, camera, transform, constants)):
        raise ValueError('Cloud-shadow inputs must be finite')
    if constants[0] <= 0:
        return None
    if constants[1] < 0 or constants[1] > 1 or constants[2] < 0:
        raise ValueError('Cloud-shadow visibility and scale are out of range')

    relative = np.asarray((
        point[0] - camera[0], point[1], point[2] - camera[2]),
        dtype=np.float32)
    projected = np.asarray((
        np.dot(transform[:, 0], relative),
        np.dot(transform[:, 1], relative)), dtype=np.float32)
    projected = np.asarray(projected * constants[2], dtype=np.float32)
    denominator = np.float32(
        (abs(projected[0] + projected[1])
         + abs(projected[1] - projected[0])) * np.float32(.5)
        + np.float32(1))
    uv = np.asarray(projected / denominator * np.float32(.5)
                    + np.float32(.5), dtype=np.float32)
    return CloudShadowCoordinates(uv, float(constants[1]))


def resolve_cloud_shadow_sample(
        coordinates: CloudShadowCoordinates | None, sample: float) -> float:
    """Apply the sampled red channel and the native minimum-visibility fade."""
    if coordinates is None:
        return 1.0
    value = float(sample)
    if not np.isfinite(value) or value < 0 or value > 1:
        raise ValueError('Cloud-shadow sample must be finite and in 0..1')
    minimum = np.float32(coordinates.minimum_visibility)
    result = np.float32((np.float32(1) - minimum) * np.float32(value) + minimum)
    return float(np.clip(result, np.float32(0), np.float32(1)))


def key_gobo_coordinates(
        world_point, key_world_to_light,
        gobo_constants) -> KeyGoboCoordinates | None:
    """Return the repeating key-gobo atlas UV, or ``None`` when disabled."""
    point = np.asarray(world_point, dtype=np.float32)
    transform = np.asarray(key_world_to_light, dtype=np.float32)
    constants = np.asarray(gobo_constants, dtype=np.float32)
    if point.shape != (3,):
        raise ValueError('Key-gobo world point must be float3')
    if transform.shape != (3, 4) or constants.shape != (4,):
        raise ValueError('Key-gobo transform must be 3x4 and constants float4')
    if not all(np.isfinite(value).all() for value in (
            point, transform, constants)):
        raise ValueError('Key-gobo inputs must be finite')
    if constants[3] <= 0:
        return None
    if constants[2] < 0:
        raise ValueError('Key-gobo atlas scale must be nonnegative')
    projected = np.asarray((
        np.dot(transform[:, 0], point),
        np.dot(transform[:, 1], point)), dtype=np.float32)
    tiled = np.asarray(
        np.modf(projected * constants[3] + np.float32(.5))[0],
        dtype=np.float32)
    tiled = np.where(tiled < 0, tiled + np.float32(1), tiled)
    uv = np.asarray((
        constants[0] + constants[2] * tiled[0],
        constants[1] + np.float32(2) * constants[2] * tiled[1]),
        dtype=np.float32)
    return KeyGoboCoordinates(uv)


def resolve_key_gobo_sample(coordinates: KeyGoboCoordinates | None,
                            color, sample) -> np.ndarray:
    """Multiply key radiance by the filtered RGB gobo sample."""
    radiance = np.asarray(color, dtype=np.float32)
    if radiance.shape != (3,) or not np.isfinite(radiance).all():
        raise ValueError('Key-gobo radiance must be finite float3')
    if coordinates is None:
        return radiance.copy()
    texture = np.asarray(sample, dtype=np.float32)
    if (texture.shape != (3,) or not np.isfinite(texture).all()
            or np.any(texture < 0)):
        raise ValueError('Key-gobo sample must be finite nonnegative RGB')
    return np.asarray(radiance * texture, dtype=np.float32)


def key_shadow_volume_range(relative_point, world_constants,
                            *, enabled: bool = True) -> KeyShadowVolumeRange | None:
    """Decode the key shadow-volume range selected by native cascade level."""
    if not enabled:
        return None
    relative = np.asarray(relative_point, dtype=np.float32)
    constants = np.asarray(world_constants, dtype=np.float32)
    if relative.shape != (3,) or constants.shape != (56, 4):
        raise ValueError(
            'Key shadow-volume point/constants must be float3 and 56x4')
    if not np.isfinite(relative).all() or not np.isfinite(constants[14:28]).all():
        raise ValueError('Key shadow-volume selector inputs must be finite')
    parameters = constants[14]
    maximum_cascade = int(parameters[2])
    if (maximum_cascade < 0 or maximum_cascade > 5
            or parameters[2] != maximum_cascade):
        raise ValueError('Key shadow-volume cascade count must be 0..5')
    bounds = np.asarray(
        relative[0] * constants[15]
        + relative[1] * constants[16], dtype=np.float32)
    bounds = np.asarray(
        relative[2] * constants[17] + bounds, dtype=np.float32)
    bounds = np.asarray(bounds + constants[18], dtype=np.float32)
    maximum = np.max(bounds)
    if maximum <= 0:
        raise ValueError('Key shadow-volume cascade extent must be positive')
    level = np.float32(
        np.log2(maximum) * parameters[0] + parameters[1])
    level = np.minimum(np.maximum(level, np.float32(0)), parameters[2])
    cascade = int(level)
    encoded = np.float32(constants[22 + cascade, 3])
    count = int(np.float32(
        (encoded - np.floor(encoded)) * np.float32(64)))
    if not count:
        return None
    first = int(np.rint(encoded))
    if first < 0:
        raise ValueError('Key shadow-volume first index must be nonnegative')
    return KeyShadowVolumeRange(cascade, first, count)
