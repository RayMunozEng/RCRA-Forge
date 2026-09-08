"""Local-probe records, sampling, and blending recovered from retail Hair.

This module does not infer zone placements, runtime cube indices, or residency.
Supply those explicitly, or read the captured 128-byte GPU records. Given the
retail six view-frustum planes and active resource mask, it can reproduce the
manager's per-view probe selection. See docs/ENVIRONMENT_PROBES.md for evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct

import numpy as np

from core.environment_probes import ZoneEnvironmentProbe


@dataclass(frozen=True)
class ProbeShaderRecord:
    axis_x: tuple[float, ...]
    fade: float
    axis_y: tuple[float, ...]
    z_sign: float
    position: tuple[float, ...]
    flags: int
    reciprocal_extents: tuple[float, ...]
    cube_index: float
    reciprocal_falloff_positive: tuple[float, ...]
    reciprocal_falloff_negative: tuple[float, ...]
    proxy_negative: tuple[float, ...]
    proxy_positive: tuple[float, ...]
    capture_position: tuple[float, ...]
    z_bin_min_max: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> ProbeShaderRecord:
        if len(data) != 128:
            raise ValueError('An EnvProbeEnv record must contain exactly 128 bytes')
        f = struct.unpack('<32f', data)
        return cls(
            f[0:3], f[3], f[4:7], f[7], f[8:11],
            struct.unpack_from('<I', data, 44)[0], f[12:15], f[15],
            f[16:19], f[20:23], (f[19], f[23], f[27]), f[24:27],
            f[28:31], struct.unpack_from('<I', data, 124)[0],
        )

    def to_bytes(self) -> bytes:
        data = bytearray(128)
        for offset, values in (
            (0, self.axis_x), (16, self.axis_y), (32, self.position),
            (48, self.reciprocal_extents),
            (64, self.reciprocal_falloff_positive),
            (80, self.reciprocal_falloff_negative),
            (96, self.proxy_positive), (112, self.capture_position),
        ):
            struct.pack_into('<3f', data, offset, *values)
        for offset, value in (
            (12, self.fade), (28, self.z_sign), (60, self.cube_index),
            (76, self.proxy_negative[0]), (92, self.proxy_negative[1]),
            (108, self.proxy_negative[2]),
        ):
            struct.pack_into('<f', data, offset, value)
        struct.pack_into('<I', data, 44, self.flags)
        struct.pack_into('<I', data, 124, self.z_bin_min_max)
        return bytes(data)


@dataclass(frozen=True)
class ProbePlacement:
    """One manager entry with caller-resolved placement and cube residency.

    ``resource_index`` addresses the separate per-view selection mask used by
    retail's FillEnvProbeLookup job. Keeping it distinct from ``cube_index``
    prevents a resident atlas slot or asset ID from being mistaken for the gate.
    """
    probe: ZoneEnvironmentProbe
    zone_to_world: object
    resource_index: int
    cube_index: int
    fade: float


def parse_probe_shader_buffer(data: bytes) -> list[ProbeShaderRecord]:
    if len(data) % 128:
        raise ValueError('EnvProbeEnv buffer size must be a multiple of 128 bytes')
    return [ProbeShaderRecord.from_bytes(data[i:i + 128])
            for i in range(0, len(data), 128)]


def probe_sort_key(probe: ZoneEnvironmentProbe) -> float:
    """Descending retail key: authored priority, size, then deterministic ID."""
    f = np.float32
    id_term = f(f(probe.instance_id & 0xFFFFFF) * f(3.725290742551124e-09))
    extent = max(f(1.0625), *map(f, probe.half_extents))
    tie_break = f(f(id_term + f(1.0)) / extent)
    return float(f(f(max(probe.priority, 0.0)) + tie_break))


def probe_fade_from_byte(value: int) -> float:
    """Retail residency fade remap; per-view selection is a separate gate."""
    if not 0 <= value <= 255:
        raise ValueError('Probe fade byte must be in 0..255')
    f = np.float32
    t = np.clip(f(value) * f(0.003929273225367069), f(0), f(1))
    return float(f(f(f(3) - f(t + t)) * f(t * t)))


def build_probe_shader_record(
    probe: ZoneEnvironmentProbe, zone_to_world, *, cube_index: int, fade: float,
) -> ProbeShaderRecord:
    """Apply an explicit row-vector zone matrix and build a resident GPU record.

    Matrix rows 0..2 are basis vectors, row 3 is translation. As in the retail
    zone loader, only position and axes are transformed. The record builder
    adds the authored capture offset directly to the resulting position.
    Callers must resolve the actual cube slot and residency before using this
    for rendering; supplying a texture asset ID as cube_index is invalid.
    """
    matrix = np.asarray(zone_to_world, dtype=np.float32)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('zone_to_world must be a finite 4x4 row-vector matrix')
    if not np.array_equal(matrix[:, 3], (0, 0, 0, 1)):
        raise ValueError('zone_to_world must be affine with translation in row 3')
    if not 0 <= cube_index <= 32767 or not np.isfinite(fade) or not 0 <= fade <= 1:
        raise ValueError('A resident cube slot and fade in 0..1 are required')
    extents = np.asarray(probe.half_extents, dtype=np.float32)
    if not np.isfinite(extents).all() or np.any(extents <= 0):
        raise ValueError('Probe half extents must be finite and positive')
    axes = np.asarray(probe.axes, dtype=np.float32) @ matrix[:3, :3]
    position = np.asarray(probe.position, dtype=np.float32) @ matrix[:3, :3] + matrix[3, :3]
    sign = 1.0 if np.dot(np.cross(axes[0], axes[1]), axes[2]) > 0 else -1.0
    negative = np.maximum(np.asarray(probe.falloff_negative, dtype=np.float32), np.float32(.01))
    positive = np.maximum(np.asarray(probe.falloff_positive, dtype=np.float32), np.float32(.01))
    flags = int(probe.volume_shape != 1) | ((probe.diffuse_flags & 1) << 1)
    return ProbeShaderRecord(
        tuple(axes[0]), fade, tuple(axes[1]), sign, tuple(position), flags,
        tuple(np.float32(1) / extents), float(cube_index),
        tuple(extents / positive), tuple(extents / negative),
        probe.proxy_negative, probe.proxy_positive,
        tuple(position + np.asarray(probe.capture_offset, dtype=np.float32)),
    )


def build_probe_frustum_selection_mask(
    placements: list[ProbePlacement], frustum_planes, *, active_mask=None,
    excluded_resource_indices=(),
) -> np.ndarray:
    """Build retail's resource-indexed per-view probe selection bytes.

    ``0x14108BE90`` first gates resource indices through the manager active
    bitset, then applies the six inward-facing frustum planes to each probe's
    oriented bounding box. Two manager-owned transition indices are suppressed
    after the plane test; callers provide those indices explicitly because they
    are runtime lifecycle state. A missing ``active_mask`` treats each supplied
    placement as active while leaving sparse resource slots clear.
    """
    planes = np.asarray(frustum_planes, dtype=np.float32)
    if planes.shape != (6, 4) or not np.isfinite(planes).all():
        raise ValueError('Probe selection requires six finite float4 frustum planes')

    resource_indices = [int(placement.resource_index) for placement in placements]
    if any(index < 0 for index in resource_indices):
        raise ValueError('Probe resource indices must be nonnegative')
    if len(set(resource_indices)) != len(resource_indices):
        raise ValueError('Probe resource indices must be unique')

    if active_mask is None:
        capacity = max(resource_indices, default=-1) + 1
        active = np.zeros(capacity, dtype=bool)
        if resource_indices:
            active[resource_indices] = True
    else:
        supplied = np.asarray(active_mask)
        if supplied.ndim != 1 or supplied.dtype.kind not in 'uib':
            raise ValueError('Probe active mask must be a one-dimensional integer array')
        active = supplied.astype(bool, copy=False)
        capacity = len(active)
        if any(index >= capacity for index in resource_indices):
            raise ValueError('Probe resource index exceeds the active mask')

    try:
        excluded = {int(index) for index in excluded_resource_indices}
    except (TypeError, ValueError) as exc:
        raise ValueError('Excluded probe resource indices must be integers') from exc
    if any(index < 0 or index >= capacity for index in excluded):
        raise ValueError('Excluded probe resource index exceeds the selection mask')

    result = np.zeros(capacity, dtype=np.uint8)
    f = np.float32
    normals = planes[:, :3]
    for placement, resource_index in zip(placements, resource_indices):
        if not active[resource_index] or resource_index in excluded:
            continue
        record = build_probe_shader_record(
            placement.probe, placement.zone_to_world,
            cube_index=placement.cube_index, fade=placement.fade,
        )
        axis_x = np.asarray(record.axis_x, dtype=np.float32)
        axis_y = np.asarray(record.axis_y, dtype=np.float32)
        axis_z = np.cross(axis_x, axis_y) * f(record.z_sign)
        half_extents = f(1) / np.asarray(record.reciprocal_extents, dtype=np.float32)
        half_axes = np.stack((axis_x, axis_y, axis_z)) * half_extents[:, None]
        center = np.asarray(record.position, dtype=np.float32)

        # Match the packed x86 ordering: x*nx + w, then y*ny, then z*nz.
        distances = f(f(f(center[0] * normals[:, 0]) + planes[:, 3])
                      + f(center[1] * normals[:, 1]))
        distances = f(distances + f(center[2] * normals[:, 2]))
        radii = np.zeros(6, dtype=np.float32)
        for half_axis in half_axes:
            projection = f(f(half_axis[0] * normals[:, 0])
                           + f(half_axis[1] * normals[:, 1]))
            projection = f(projection + f(half_axis[2] * normals[:, 2]))
            radii = f(radii + np.abs(projection))
        # Retail uses movmskps, so signed negative zero is outside too.
        if not np.signbit(f(distances + radii)).any():
            result[resource_index] = 1
    return result


def camera_relative_frustum_planes(view_to_world, cam_world_to_clip) -> np.ndarray:
    """Extract six inward D3D zero-to-one planes in world coordinates.

    Shell projection uses ``(world - camera) @ cam_world_to_clip``. The clip
    inequalities are ``-w <= x,y <= w`` and ``0 <= z <= w``; converting their
    column combinations back to world coordinates only changes each plane's
    constant by the camera translation. Plane normalization is unnecessary for
    the oriented-box test because distance and projected radius scale together.
    """
    view = np.asarray(view_to_world, dtype=np.float32)
    clip = np.asarray(cam_world_to_clip, dtype=np.float32)
    if (view.shape != (4, 4) or clip.shape != (4, 4)
            or not np.isfinite(view).all() or not np.isfinite(clip).all()):
        raise ValueError('Frustum extraction requires two finite 4x4 matrices')
    if not np.array_equal(view[:, 3], np.array((0, 0, 0, 1), np.float32)):
        raise ValueError('view_to_world must be affine with translation in row 3')
    columns = clip.T
    relative = np.stack((
        columns[3] + columns[0], columns[3] - columns[0],
        columns[3] + columns[1], columns[3] - columns[1],
        columns[2], columns[3] - columns[2],
    )).astype(np.float32)
    planes = relative.copy()
    camera = view[3, :3]
    planes[:, 3] = np.float32(relative[:, 3] - relative[:, :3] @ camera)
    return planes


def build_selected_probe_shader_records(
    placements: list[ProbePlacement], selection_mask,
) -> tuple[np.ndarray, np.ndarray]:
    """Sort manager entries, apply per-view resource selection, and build records.

    Retail keeps manager order while compacting entries whose resource-indexed
    selection byte is nonzero. Authored sort keys are descending; equal keys
    preserve the caller's registration order. The returned indices address the
    original ``placements`` sequence.
    """
    mask = np.asarray(selection_mask)
    if mask.ndim != 1 or mask.dtype.kind not in 'uib':
        raise ValueError('Probe selection mask must be a one-dimensional integer array')
    order = sorted(
        range(len(placements)), key=lambda index: probe_sort_key(placements[index].probe),
        reverse=True,
    )
    selected = []
    rows = []
    for index in order:
        placement = placements[index]
        resource_index = int(placement.resource_index)
        if resource_index < 0 or resource_index >= len(mask):
            raise ValueError('Probe resource index exceeds the selection mask')
        if not mask[resource_index]:
            continue
        rows.append(build_probe_shader_record(
            placement.probe, placement.zone_to_world,
            cube_index=placement.cube_index, fade=placement.fade,
        ).to_bytes())
        selected.append(index)
    records = np.frombuffer(b''.join(rows), dtype=np.uint8).reshape(-1, 128).copy()
    return records, np.asarray(selected, dtype=np.int64)


def _saturate(value):
    # D3D _sat maps NaN to zero, including the cylinder's center singularity.
    return np.clip(np.nan_to_num(value, nan=0.0, posinf=1.0, neginf=0.0), 0, 1)


def _mad(a, b, c):
    # Round once to float32, avoiding cancellation from a separately rounded
    # product in the shipped probes' narrow (clamped 0.01 m) falloff bands.
    return np.asarray(np.asarray(a, dtype=np.float64) * np.asarray(b, dtype=np.float64)
                      + np.asarray(c, dtype=np.float64), dtype=np.float32)


def probe_spatial_weight(record: ProbeShaderRecord, world_points):
    """Evaluate Hair's geometric weight for one point or an (..., 3) array.

    The returned float32 weights exclude residency fade and ordered blending.
    """
    points = np.asarray(world_points, dtype=np.float32)
    if points.ndim < 1 or points.shape[-1] != 3 or not np.isfinite(points).all():
        raise ValueError('Expected finite world points with final dimension 3')
    x = np.asarray(record.axis_x, dtype=np.float32)
    y = np.asarray(record.axis_y, dtype=np.float32)
    z = np.cross(x, y) * np.float32(record.z_sign)
    local = (points - np.asarray(record.position, dtype=np.float32)) @ np.stack((x, y, z)).T
    inverse_extent = np.asarray(record.reciprocal_extents, dtype=np.float32)
    q = local * inverse_extent
    positive = np.asarray(record.reciprocal_falloff_positive, dtype=np.float32)
    negative = np.asarray(record.reciprocal_falloff_negative, dtype=np.float32)
    edge = np.maximum(_saturate(_mad(_mad(local, inverse_extent, -1), positive, 1)),
                      _saturate(_mad(_mad(-local, inverse_extent, -1), negative, 1)))
    if record.flags & 1:
        with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
            fall_pos = np.float32(1) / positive[[0, 2]]
            fall_neg = np.float32(1) / negative[[0, 2]]
            inner = _mad(-fall_neg, .5, _mad(-fall_pos, .5, 1))
            center = fall_neg + inner - 1
            radial = _mad(local[..., [0, 2]], inverse_extent[[0, 2]], -center) / inner
            radius = np.sqrt(np.sum(radial * radial, axis=-1, keepdims=True))
            direction = radial / radius
            falloff = np.where(q[..., [0, 2]] > center, fall_pos, fall_neg)
            distance = (radius - 1) / np.sum(falloff * direction * direction, axis=-1, keepdims=True)
            radial_edge = _saturate(distance * (np.abs(direction) * inner))
        edge = np.stack((radial_edge[..., 0], edge[..., 1], radial_edge[..., 1]), axis=-1)
    weight = np.maximum(1 - np.sum(edge * edge, axis=-1), 0)
    return np.asarray(weight * weight, dtype=np.float32)


def blend_probe_weights(records: list[ProbeShaderRecord], world_point, lookup_mask: int) -> dict:
    """Recover Hair's specular and diffuse sample weights in buffer/bit order.

    Remaining coverage subtracts each faded spatial weight; it is not a
    multiplicative alpha-transmittance chain. Samples first accumulate with
    remaining * weight, then normalize before the final default-cube blend.
    Diffuse-enabled samples retain their own accumulated coverage, independent
    of the final specular/default blend. Their remainder uses the light grid.
    """
    if lookup_mask < 0 or lookup_mask >> len(records):
        raise ValueError('Lookup mask references a missing probe record')
    if np.asarray(world_point).shape != (3,):
        raise ValueError('Blending requires one world point')
    f = np.float32
    remaining, total, diffuse_total = f(1), f(0), f(0)
    samples = []
    mask = lookup_mask
    while mask and remaining > 0:
        bit = mask & -mask
        index = bit.bit_length() - 1
        mask ^= bit
        record = records[index]
        geometric = f(probe_spatial_weight(record, world_point))
        alpha = f(geometric * f(record.fade))
        if alpha > 0:
            if record.cube_index < 0:
                raise ValueError(f'Probe {index} has weight but no resident cube')
            contribution = f(remaining * alpha)
            total = f(total + contribution)
            if record.flags & 2:
                diffuse_total = f(diffuse_total + contribution)
            remaining = f(remaining - alpha)
            samples.append({
                'record_index': index, 'cube_index': record.cube_index,
                'spatial_weight': float(geometric), 'faded_weight': float(alpha),
                'accumulated_weight': float(contribution),
                'diffuse_enabled': bool(record.flags & 2),
            })
    default = max(float(remaining), 0.0)
    denominator = max(total, f(.00001))
    for sample in samples:
        sample['sample_weight'] = float(f(f(sample['accumulated_weight']) / denominator) * f(1 - default))
        sample['diffuse_sample_weight'] = (
            float(f(f(sample['accumulated_weight']) / diffuse_total) * _saturate(diffuse_total))
            if sample['diffuse_enabled'] and diffuse_total > 0 else 0.0
        )
    return {'samples': samples, 'default_weight': default,
            'diffuse_base_weight': float(f(1) - _saturate(diffuse_total)),
            'remaining_before_default_clamp': float(remaining)}


def hair_probe_sampling_parameters(average_gloss):
    """Return specular mip and capture-offset scale from mean Hair gloss.

    The shader clamps gloss only at zero. Texture sampling handles mip bounds.
    Diffuse always uses mip 5 and the full capture offset (scale 1).
    """
    gloss = np.asarray(average_gloss, dtype=np.float32)
    if not np.isfinite(gloss).all():
        raise ValueError('Expected finite average gloss')
    gloss = np.maximum(gloss, np.float32(0))
    t = np.minimum(gloss * np.float32(1.5), np.float32(1))
    return _mad(gloss, -5, 5), _mad(-t, 2, 3) * (t * t)


def probe_parallax_direction(
    record: ProbeShaderRecord, world_points, world_directions, *, capture_offset_scale=1.0,
):
    """Intersect the signed proxy planes and return unnormalized cube vectors.

    Points and directions broadcast as (..., 3). The proxy is a box even for
    cylindrical influence volumes. Intersection uses the original direction;
    only (world_point - capture_position) receives the specular gloss scale.
    Parallel axes preserve the shader's infinities and minimum/NaN behavior.
    """
    points = np.asarray(world_points, dtype=np.float32)
    directions = np.asarray(world_directions, dtype=np.float32)
    for name, values in [('world points', points), ('world directions', directions)]:
        if values.ndim < 1 or values.shape[-1] != 3 or not np.isfinite(values).all():
            raise ValueError(f'Expected finite {name} with final dimension 3')
    if np.any(np.all(directions == 0, axis=-1)):
        raise ValueError('World directions must be nonzero')
    scale = np.asarray(capture_offset_scale, dtype=np.float32)
    if not np.isfinite(scale).all():
        raise ValueError('Expected finite capture offset scale')
    x = np.asarray(record.axis_x, dtype=np.float32)
    y = np.asarray(record.axis_y, dtype=np.float32)
    z = np.cross(x, y) * np.float32(record.z_sign)
    basis = np.stack((x, y, z))
    def dot_basis(vectors):
        # An initial +0 accumulator in matmul loses an all-negative-zero dot,
        # which changes the sign of division by zero for exactly axial rays.
        products = vectors[..., None, :] * basis
        return (products[..., 0] + products[..., 1]) + products[..., 2]
    local = dot_basis(points - np.asarray(record.position, dtype=np.float32))
    ray = dot_basis(directions)
    planes = np.where(ray < 0, np.asarray(record.proxy_negative, dtype=np.float32),
                      np.asarray(record.proxy_positive, dtype=np.float32))
    with np.errstate(divide='ignore', invalid='ignore'):
        distances = (planes - local) / ray
        distance = np.fmin(distances[..., 2], np.fmin(distances[..., 1], distances[..., 0]))
        capture_delta = (points - np.asarray(record.capture_position, dtype=np.float32)) * scale[..., None]
        return _mad(directions, distance[..., None], capture_delta)


def hair_probe_specular_visibility(average_gloss, light_grid_reflection, coarse_luminance):
    """Hair's light-grid visibility multiplier, before environment intensity.

    coarse_luminance is the blended mip-5 reflection sample dotted with
    (0.25, 0.5, 0.25), without parallax. light_grid_reflection is the separate
    scalar reconstructed by the light-grid branch, not its diffuse RGB.
    """
    values = [np.asarray(v, dtype=np.float32) for v in
              (average_gloss, light_grid_reflection, coarse_luminance)]
    if not all(np.isfinite(v).all() for v in values):
        raise ValueError('Expected finite probe visibility inputs')
    gloss, grid, luminance = values
    strength = np.minimum(np.float32(1.5) - np.maximum(gloss, np.float32(0)), np.float32(1))
    ratio = _saturate((grid * np.float32(.5)) / np.maximum(luminance, np.float32(.000001)))
    return _mad(strength * strength, _mad(ratio, 2, -1), 1)


def probe_sampling_plan(
    records: list[ProbeShaderRecord], world_point, lookup_mask: int, *,
    reflection_direction, shading_normal, average_gloss: float,
) -> dict:
    """Describe every environment fetch and blend without inventing resources.

    reflection_direction and shading_normal are Hair's already reconstructed
    world-space vectors, including its anisotropic/frame-dependent normal.
    This does not evaluate the BRDF, sample cubes, or reconstruct the light grid.
    Undefined direction components are JSON nulls with a false finite flag;
    the lower-level parallax helper preserves the actual NaNs/infinities.
    """
    for direction in (reflection_direction, shading_normal):
        vector = np.asarray(direction, dtype=np.float32)
        if vector.shape != (3,) or not np.isfinite(vector).all() or not np.any(vector):
            raise ValueError('Sampling requires finite nonzero world-space vectors of size 3')
    if np.asarray(average_gloss).shape != ():
        raise ValueError('Sampling requires one average gloss value')
    mip, offset_scale = hair_probe_sampling_parameters(average_gloss)
    result = blend_probe_weights(records, world_point, lookup_mask)
    for sample in result['samples']:
        record = records[sample['record_index']]
        specular = probe_parallax_direction(
            record, world_point, reflection_direction, capture_offset_scale=offset_scale,
        )
        diffuse = (probe_parallax_direction(
            record, world_point, shading_normal,
        ) if sample['diffuse_enabled'] else None)
        for channel, vector in [('specular', specular), ('diffuse', diffuse)]:
            sample[f'{channel}_direction'] = (
                [float(v) if np.isfinite(v) else None for v in vector] if vector is not None else None
            )
            sample[f'{channel}_direction_finite'] = (
                bool(np.isfinite(vector).all()) if vector is not None else None
            )
    return {
        **result, 'specular_mip': float(mip), 'specular_capture_offset_scale': float(offset_scale),
        'diffuse_mip': 5.0, 'coarse_luminance_mip': 5.0,
        'coarse_luminance_rgb_weights': [.25, .5, .25],
        'coarse_luminance_direction': list(map(float, reflection_direction)),
        'default_specular_direction': list(map(float, reflection_direction)),
    }
