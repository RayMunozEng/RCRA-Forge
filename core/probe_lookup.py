"""CPU forms of the retail screen-volume and environment-probe lookup writes.

The active record count and runtime placement inputs remain caller-owned. Given
those inputs, these functions reproduce the shell projection/raster operations and
integer operations in
PS_InsertLightLookupFront, PS_InsertLightLookupBackPerspective,
PS_InsertLightLookupBackOrthographic and CS_EnvProbeLookupGenerateZBin.
"""
from __future__ import annotations

import numpy as np

from core.local_lights import (
    LIGHT_GPU_DTYPE, LIGHT_SHELL_BOX_VERTICES, LIGHT_SHELL_CBUFFER_DTYPE,
    LightShellPlacement,
    build_light_shell_constants, generate_light_z_bin_lookup,
    project_light_shell_vertices,
)


ENV_PROBE_Z_BIN_OFFSET = 124
PROBE_RECORD_SIZE = 128
PROBE_POSITION_OFFSET = 32
PROBE_RECIPROCAL_EXTENTS_OFFSET = 48
PROBE_Z_BIN_BASE_DEPTH = np.float32(1024.0)
# Retail VA 0x1432D3C60 stores a 16-segment circumscribed cylinder. These are
# the exact uint32 float bits for the ring's XZ pairs; tiny near-zero values are
# preserved because the executable's source stream contains them.
_LIGHT_SHELL_CYLINDER_RING_BITS = (
    (0x3F8281F6, 0x00000000), (0x3F71258E, 0x3EC7C5C2),
    (0x3F3890D2, 0x3F3890D2), (0x3EC7C5C1, 0x3F71258F),
    (0xB32BCC77, 0x3F8281F6), (0xBEC7C5C4, 0x3F71258E),
    (0xBF3890D2, 0x3F3890D2), (0xBF712590, 0x3EC7C5BC),
    (0xBF8281F6, 0xB3C14606), (0xBF71258E, 0xBEC7C5C2),
    (0xBF3890D0, 0xBF3890D4), (0xBEC7C5B7, 0xBF712591),
    (0x322BCC77, 0xBF8281F6), (0x3EC7C5C7, 0xBF71258D),
    (0x3F3890D6, 0xBF3890CE), (0x3F71258F, 0xBEC7C5C1),
)


def _cylinder_shell_vertices() -> tuple[tuple[float, float, float], ...]:
    ring = np.asarray(_LIGHT_SHELL_CYLINDER_RING_BITS, '<u4').view('<f4')
    vertices = []
    for index in range(len(ring)):
        x0, z0 = map(float, ring[index])
        x1, z1 = map(float, ring[(index + 1) % len(ring)])
        bottom0, top0 = (x0, -1.0, z0), (x0, 1.0, z0)
        bottom1, top1 = (x1, -1.0, z1), (x1, 1.0, z1)
        vertices.extend((
            bottom0, top0, top1, top1, bottom1, bottom0,
            top0, (0.0, 1.0, 0.0), top1,
            bottom1, (0.0, -1.0, 0.0), bottom0,
        ))
    return tuple(vertices)


LIGHT_SHELL_CYLINDER_VERTICES = _cylinder_shell_vertices()


def light_shell_vertex_push_scale(screen_to_view_x: float, raster_width: int,
                                  push_pixels: float = 2.0) -> np.float32:
    """Return the retail shell expansion constant for one raster stage.

    Helper ``0x1410ACEA0`` multiplies the mode table value by the renderer's
    horizontal screen-to-view factor and divides by the active stage width.
    Environment-probe submission uses table index 4, whose value is exactly
    2.0.  The captured 1920-wide view rasterizes the lookup depth at quarter
    resolution, so that stage width is 480 rather than the final 240-wide
    bitfield target.
    """
    scale = np.float32(screen_to_view_x)
    width = int(raster_width)
    pixels = np.float32(push_pixels)
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError('Screen-to-view scale must be finite and positive')
    if width <= 0:
        raise ValueError('Raster width must be positive')
    if not np.isfinite(pixels) or pixels < 0:
        raise ValueError('Shell push distance must be finite and nonnegative')
    return np.float32(np.float32(pixels * scale) / np.float32(width))


def _project_probe_shell(record, view_to_world, cam_world_to_clip, *,
                         vert_push_scale: float, near_clip: float,
                         vertices, round_shell: bool) -> np.ndarray:
    """Execute recovered ``VS_LightShell`` math for one probe topology.

    The result has shape ``(triangles, 3, 4)`` and contains homogeneous clip-space
    triangle vertices in the retail stream order. Homogeneous clipping,
    fixed-function depth/culling and pixel coverage remain raster-stage work.
    """
    raw = _record_bytes(record)
    if len(raw) != 1:
        raise ValueError('Shell projection requires exactly one probe record')
    values = raw.view('<f4').reshape(32)
    flags = int(raw[0, 44:48].copy().view('<u4')[0])
    if bool(flags & 1) != bool(round_shell):
        expected = 'round' if round_shell else 'box'
        raise ValueError(f'Probe record does not select the {expected} shell')
    inverse_extents = values[12:15]
    if not np.isfinite(inverse_extents).all() or np.any(inverse_extents <= 0):
        raise ValueError('Probe reciprocal extents must be finite and positive')
    view = np.asarray(view_to_world, dtype=np.float32)
    projection = np.asarray(cam_world_to_clip, dtype=np.float32)
    if (view.shape != (4, 4) or projection.shape != (4, 4)
            or not np.isfinite(view).all() or not np.isfinite(projection).all()):
        raise ValueError('Probe shell projection requires two finite 4x4 matrices')
    if not np.array_equal(view[:, 3], np.array((0, 0, 0, 1), np.float32)):
        raise ValueError('view_to_world must be affine with translation in row 3')
    push = np.float32(vert_push_scale)
    clip_near = np.float32(near_clip)
    if not np.isfinite([push, clip_near]).all() or push < 0 or clip_near < 0:
        raise ValueError('Shell push and near clip must be finite and nonnegative')

    axis_x = values[0:3]
    axis_y = values[4:7]
    axis_z = np.cross(axis_x, axis_y) * values[7]
    extents = np.float32(1) / inverse_extents
    basis = np.stack((axis_x, axis_y, axis_z)) * extents[:, None]
    vertices = np.asarray(vertices, np.float32).reshape(-1, 3, 3)
    center = values[8:11]
    object_to_world = np.eye(4, dtype=np.float32)
    object_to_world[:3, :3] = basis
    object_to_world[3, :3] = center
    constants = np.zeros(1, dtype=LIGHT_SHELL_CBUFFER_DTYPE)
    constants[0]['object_to_world'] = object_to_world
    constants[0]['aabb_center'] = center
    constants[0]['aabb_inverse_extents'] = inverse_extents
    constants[0]['vertex_push_scale'] = push
    return project_light_shell_vertices(
        vertices, constants[0], view, projection,
        near_clip=clip_near,
    ).clip_positions


def project_probe_box_shell(record, view_to_world, cam_world_to_clip, *,
                            vert_push_scale: float, near_clip: float) -> np.ndarray:
    """Project the retail 36-vertex box shell for one box probe."""
    return _project_probe_shell(
        record, view_to_world, cam_world_to_clip,
        vert_push_scale=vert_push_scale, near_clip=near_clip,
        vertices=LIGHT_SHELL_BOX_VERTICES, round_shell=False,
    )


def project_probe_cylinder_shell(record, view_to_world, cam_world_to_clip, *,
                                 vert_push_scale: float, near_clip: float) -> np.ndarray:
    """Project the retail 192-vertex shell for one cylindrical probe."""
    return _project_probe_shell(
        record, view_to_world, cam_world_to_clip,
        vert_push_scale=vert_push_scale, near_clip=near_clip,
        vertices=LIGHT_SHELL_CYLINDER_VERTICES, round_shell=True,
    )


def reduce_linear_depth_bounds(linear_depth, tile_size: int = 8, *,
                               storage_dtype=np.float16) -> tuple[np.ndarray, np.ndarray]:
    """Return conservative nearest/farthest linear depth for screen tiles.

    The captured lookup is 240x135 for a 1920x1080 source. Retail's
    ``CS_GenerateEighthResMinDepth`` performs a 4x4 minimum gather from its
    upstream low-resolution input. This direct block form is the equivalent
    conservative reduction when the complete source-depth footprint is
    available. Edge tiles clamp to the final source texel, as the captured
    point-clamp sampler does. Values round through the requested target
    storage type (R16F by default) before returning float32 shader values.
    """
    depth = np.asarray(linear_depth, dtype=np.float32)
    size = int(tile_size)
    if depth.ndim != 2 or not np.isfinite(depth).all() or np.any(depth < 0):
        raise ValueError('Linear depth must be a finite nonnegative 2D array')
    if size <= 0:
        raise ValueError('Depth tile size must be positive')
    if depth.size == 0:
        return (np.empty(((depth.shape[0] + size - 1) // size,
                          (depth.shape[1] + size - 1) // size), np.float32),) * 2
    pad_height = (-depth.shape[0]) % size
    pad_width = (-depth.shape[1]) % size
    if pad_height or pad_width:
        depth = np.pad(depth, ((0, pad_height), (0, pad_width)), mode='edge')
    tiles = depth.reshape(depth.shape[0] // size, size, depth.shape[1] // size, size)
    nearest = tiles.min(axis=(1, 3))
    farthest = tiles.max(axis=(1, 3))
    dtype = np.dtype(storage_dtype)
    if dtype.kind != 'f':
        raise ValueError('Depth storage type must be floating point')
    return (nearest.astype(dtype).astype(np.float32),
            farthest.astype(dtype).astype(np.float32))


def conservative_probe_depth_overlap(shell_near, shell_far, tile_near, tile_far):
    """Select pixels whose shell interval overlaps a conservative depth range.

    The saved opaque lookup is explained by the front pass accepting the
    farthest tile depth and the back pass rejecting against the nearest tile
    depth. This is the interval form of those two comparisons; raster
    coverage, shell expansion and the back shader's derivative envelope stay
    separate inputs.
    """
    near, far, depth_near, depth_far = np.broadcast_arrays(
        np.asarray(shell_near, np.float32), np.asarray(shell_far, np.float32),
        np.asarray(tile_near, np.float32), np.asarray(tile_far, np.float32),
    )
    if not all(np.isfinite(value).all() for value in (near, far, depth_near, depth_far)):
        raise ValueError('Shell and tile depth bounds must be finite')
    return (near <= depth_far) & (far >= depth_near)


def _record_bytes(records) -> np.ndarray:
    if isinstance(records, (bytes, bytearray, memoryview)):
        raw = np.frombuffer(records, np.uint8)
        if raw.size % PROBE_RECORD_SIZE:
            raise ValueError('Probe record bytes must be a multiple of 128')
        raw = raw.reshape(-1, PROBE_RECORD_SIZE)
    else:
        raw = np.asarray(records)
        if raw.ndim != 2 or raw.shape[1] != PROBE_RECORD_SIZE or raw.dtype != np.uint8:
            raise ValueError('Probe records must have shape (count, 128), dtype uint8')
    return np.ascontiguousarray(raw)


def _active_count(capacity: int, record_count: int | None) -> int:
    count = capacity if record_count is None else int(record_count)
    if count < 0 or count > capacity:
        raise ValueError('Active probe record count exceeds the supplied buffer')
    return count


def probe_lookup_word_count(record_count: int) -> int:
    """Return the number of 32-bit lookup words written for active records."""
    count = int(record_count)
    if count < 0:
        raise ValueError('Probe record count cannot be negative')
    return (count + 31) // 32


def compact_selected_probe_records(records, resource_indices, selection_mask) -> tuple[np.ndarray, np.ndarray]:
    """Compact sorted manager records using retail's submit-time byte mask.

    At ``0x14108D2B0`` the submit loop reads the resource index stored at
    manager offset ``0x80`` and keeps the record only when the corresponding
    byte in the supplied selection table is nonzero. The manager's existing
    order is preserved. Resource readiness and construction of this per-pass
    selection table remain caller-owned inputs.
    """
    raw = _record_bytes(records)
    indices = np.asarray(resource_indices)
    mask = np.asarray(selection_mask)
    if indices.ndim != 1 or len(indices) != len(raw) or not np.issubdtype(indices.dtype, np.integer):
        raise ValueError('Probe resource indices must be one integer per record')
    if mask.ndim != 1 or not (mask.dtype == np.bool_ or np.issubdtype(mask.dtype, np.integer)):
        raise ValueError('Probe selection mask must be a one-dimensional byte or boolean table')
    if np.any(indices < 0) or np.any(indices >= len(mask)):
        raise ValueError('Probe resource index exceeds the selection mask')
    selected = np.flatnonzero(mask[indices.astype(np.int64)] != 0)
    return raw[selected].copy(), selected.astype(np.int64, copy=False)


def _f32_add(left, right) -> np.float32:
    return np.float32(np.float32(left) + np.float32(right))


def _f32_mul(left, right) -> np.float32:
    return np.float32(np.float32(left) * np.float32(right))


def _stable_length3(vector) -> np.float32:
    """Match retail 0x1402985F0 without overflowing intermediate squares."""
    value = np.asarray(vector, dtype=np.float32)
    greatest = np.float32(np.max(np.abs(value)))
    if greatest == 0:
        return np.float32(0)
    scaled = np.asarray(value / greatest, dtype=np.float32)
    squared = _f32_add(
        _f32_add(_f32_mul(scaled[1], scaled[1]), _f32_mul(scaled[0], scaled[0])),
        _f32_mul(scaled[2], scaled[2]),
    )
    return _f32_mul(np.sqrt(squared), greatest)


def compute_probe_z_bin_limits(depth_centers, bounding_radii) -> tuple[np.ndarray, np.float32]:
    """Return packed record limits and the shared retail world-constant scale.

    The CPU submit path at ``0x14108D200`` clamps each sphere's view-depth
    bounds at zero, selects ``1024 / max(1024, farthest_bound)``, floors the
    scaled minimum, and stores ``floor(scaled_maximum) + 1`` in the high half.
    Centers and radii are kept explicit so transformed runtime bounds can be
    supplied without guessing placement state.
    """
    centers = np.asarray(depth_centers, dtype=np.float32)
    radii = np.asarray(bounding_radii, dtype=np.float32)
    if centers.ndim != 1 or radii.shape != centers.shape:
        raise ValueError('Probe depth centers and bounding radii must be matching vectors')
    if not np.isfinite(centers).all() or not np.isfinite(radii).all() or np.any(radii < 0):
        raise ValueError('Probe depth centers and nonnegative bounding radii must be finite')

    minimums = np.empty_like(centers)
    maximums = np.empty_like(centers)
    farthest = np.float32(0)
    for index, (center, radius) in enumerate(zip(centers, radii)):
        minimums[index] = max(_f32_add(center, -radius), np.float32(0))
        maximums[index] = max(_f32_add(center, radius), np.float32(0))
        farthest = max(farthest, maximums[index])
    scale = np.float32(PROBE_Z_BIN_BASE_DEPTH / max(PROBE_Z_BIN_BASE_DEPTH, farthest))

    packed = np.empty(len(centers), dtype=np.uint32)
    for index, (minimum, maximum) in enumerate(zip(minimums, maximums)):
        low = int(np.floor(_f32_mul(scale, minimum)))
        high = int(np.floor(_f32_mul(scale, maximum))) + 1
        packed[index] = np.uint32(low | (high << 16))
    return packed, scale


def populate_probe_z_bin_limits(records, view_to_world, *, record_count: int | None = None,
                                bounding_radii=None) -> tuple[np.ndarray, np.float32]:
    """Write retail Z-bin limits into a copy of resident probe GPU records.

    ``view_to_world`` is the affine row-vector matrix present at the start of
    the retail viewport cbuffer. Its third row is the forward basis and its
    fourth row is the camera position. When ``bounding_radii`` is omitted,
    radii are reconstructed from the reciprocal half extents in each record,
    matching the rigid-placement path at ``0x14108AA20``. Callers with scaled
    or otherwise updated runtime bounds should pass the manager radii.
    """
    raw = _record_bytes(records)
    count = _active_count(len(raw), record_count)
    matrix = np.asarray(view_to_world, dtype=np.float32)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('view_to_world must be a finite 4x4 row-vector matrix')
    if not np.array_equal(matrix[:, 3], np.array((0, 0, 0, 1), dtype=np.float32)):
        raise ValueError('view_to_world must be affine with translation in row 3')

    floats = raw[:count].copy().view('<f4').reshape(-1, PROBE_RECORD_SIZE // 4)
    positions = floats[:, PROBE_POSITION_OFFSET // 4:PROBE_POSITION_OFFSET // 4 + 3]
    basis = matrix[2, :3]
    camera = matrix[3, :3]
    camera_yx = _f32_add(_f32_mul(basis[1], camera[1]), _f32_mul(basis[0], camera[0]))
    translation = -_f32_add(camera_yx, _f32_mul(basis[2], camera[2]))
    centers = np.empty(count, dtype=np.float32)
    for index, position in enumerate(positions):
        yx = _f32_add(_f32_mul(basis[1], position[1]), _f32_mul(basis[0], position[0]))
        zt = _f32_add(_f32_mul(basis[2], position[2]), translation)
        centers[index] = _f32_add(yx, zt)

    if bounding_radii is None:
        reciprocal = floats[:, PROBE_RECIPROCAL_EXTENTS_OFFSET // 4:
                            PROBE_RECIPROCAL_EXTENTS_OFFSET // 4 + 3]
        if not np.isfinite(reciprocal).all() or np.any(reciprocal <= 0):
            raise ValueError('Active probe records need finite positive reciprocal extents')
        half_extents = np.asarray(np.float32(1) / reciprocal, dtype=np.float32)
        radii = np.asarray([_stable_length3(extents) for extents in half_extents], dtype=np.float32)
    else:
        radii = np.asarray(bounding_radii, dtype=np.float32)
        if radii.shape != (count,):
            raise ValueError('Explicit probe bounding radii must match the active record count')

    packed, scale = compute_probe_z_bin_limits(centers, radii)
    output = raw.copy()
    if count:
        output[:count, ENV_PROBE_Z_BIN_OFFSET:ENV_PROBE_Z_BIN_OFFSET + 4] = packed.view(np.uint8).reshape(-1, 4)
    return output, scale


def generate_probe_z_bin_lookup(records, bin_count: int, *, record_count: int | None = None) -> np.ndarray:
    """Pack inclusive per-record Z-bin ranges as ``(words, bins)`` uint32.

    ``EnvProbeEnv.m_ZBinMinMax`` stores the unsigned minimum in the low 16
    bits and the inclusive maximum in the high 16 bits. The retail compute
    shader launches one thread per requested bin, walks records in buffer
    order, and writes one bit per record. A separate active count is needed
    because allocated structured buffers may contain trailing rows.
    """
    raw = _record_bytes(records)
    count = _active_count(len(raw), record_count)
    bins = int(bin_count)
    if bins < 0:
        raise ValueError('Z-bin count cannot be negative')
    output = np.zeros((probe_lookup_word_count(count), bins), np.uint32)
    if not count or not bins:
        return output
    packed = raw[:count, ENV_PROBE_Z_BIN_OFFSET:ENV_PROBE_Z_BIN_OFFSET + 4].copy().view('<u4').reshape(-1)
    indices = np.arange(bins, dtype=np.uint32)
    for record_index, limits in enumerate(packed):
        minimum = np.uint32(limits & np.uint32(0xFFFF))
        maximum = np.uint32(limits >> np.uint32(16))
        selected = (indices >= minimum) & (indices <= maximum)
        output[record_index >> 5, selected] |= np.uint32(1 << (record_index & 31))
    return output


def build_screen_lookup_bitfields(front_coverage, opaque_back_rejections) -> tuple[np.ndarray, np.ndarray]:
    """Apply the lookup pixel shaders to already-rasterized boolean coverage.

    Inputs have shape ``(records, height, width)``. A front fragment ORs its
    record bit into both the full and opaque arrays. A qualifying back
    fragment clears that bit from the opaque array only. The returned arrays
    use the renderer's ``(words, height, width)`` texture-array ordering.
    """
    front = np.asarray(front_coverage)
    rejected = np.asarray(opaque_back_rejections)
    if front.ndim != 3 or front.shape != rejected.shape:
        raise ValueError('Coverage inputs must have matching (records, height, width) shapes')
    if front.dtype != np.bool_ or rejected.dtype != np.bool_:
        raise ValueError('Coverage inputs must have boolean dtype')
    count, height, width = front.shape
    full = np.zeros((probe_lookup_word_count(count), height, width), np.uint32)
    opaque = np.zeros_like(full)
    for record_index in range(count):
        bit = np.uint32(1 << (record_index & 31))
        word = record_index >> 5
        full[word, front[record_index]] |= bit
        opaque[word, front[record_index]] |= bit
        opaque[word, rejected[record_index]] &= ~bit
    return full, opaque


def _clip_d3d_polygon(vertices: np.ndarray) -> list[np.ndarray]:
    polygon = [vertex for vertex in vertices]
    planes = (
        lambda vertex: vertex[0] + vertex[3],
        lambda vertex: vertex[3] - vertex[0],
        lambda vertex: vertex[1] + vertex[3],
        lambda vertex: vertex[3] - vertex[1],
        lambda vertex: vertex[2],
        lambda vertex: vertex[3] - vertex[2],
    )
    for distance in planes:
        if not polygon:
            break
        output = []
        previous = polygon[-1]
        previous_distance = np.float32(distance(previous))
        previous_inside = previous_distance >= 0
        for current in polygon:
            current_distance = np.float32(distance(current))
            current_inside = current_distance >= 0
            if current_inside != previous_inside:
                amount = np.float32(
                    previous_distance / (previous_distance - current_distance)
                )
                output.append(np.asarray(
                    previous + amount * (current - previous), dtype=np.float32,
                ))
            if current_inside:
                output.append(current)
            previous = current
            previous_distance = current_distance
            previous_inside = current_inside
        polygon = output
    return polygon


def _screen_edge(first, second, x, y):
    return ((x - first[0]) * (second[1] - first[1])
            - (y - first[1]) * (second[0] - first[0]))


def _rasterize_shell_depth(clip_triangles: np.ndarray, width: int, height: int):
    """Rasterize pixel-center coverage and nearest/farthest perspective W."""
    nearest = np.full((height, width), np.inf, np.float32)
    farthest = np.full((height, width), -np.inf, np.float32)
    for source in clip_triangles:
        polygon = _clip_d3d_polygon(source)
        for fan_index in range(1, len(polygon) - 1):
            clip = np.asarray(
                (polygon[0], polygon[fan_index], polygon[fan_index + 1]),
                dtype=np.float32,
            )
            screen = np.empty((3, 2), np.float32)
            screen[:, 0] = (
                clip[:, 0] / clip[:, 3] * np.float32(.5) + np.float32(.5)
            ) * width
            screen[:, 1] = (
                np.float32(.5) - clip[:, 1] / clip[:, 3] * np.float32(.5)
            ) * height
            area = float(_screen_edge(
                screen[0], screen[1], screen[2, 0], screen[2, 1],
            ))
            if abs(area) < 1e-12:
                continue
            x0 = max(0, int(np.ceil(float(screen[:, 0].min()) - .5)))
            x1 = min(width - 1, int(np.floor(float(screen[:, 0].max()) - .5)))
            y0 = max(0, int(np.ceil(float(screen[:, 1].min()) - .5)))
            y1 = min(height - 1, int(np.floor(float(screen[:, 1].max()) - .5)))
            if x1 < x0 or y1 < y0:
                continue
            xx, yy = np.meshgrid(
                np.arange(x0, x1 + 1, dtype=np.float32) + np.float32(.5),
                np.arange(y0, y1 + 1, dtype=np.float32) + np.float32(.5),
            )
            edge0 = _screen_edge(screen[1], screen[2], xx, yy)
            edge1 = _screen_edge(screen[2], screen[0], xx, yy)
            edge2 = _screen_edge(screen[0], screen[1], xx, yy)
            if area > 0:
                inside = (edge0 >= 0) & (edge1 >= 0) & (edge2 >= 0)
            else:
                inside = (edge0 <= 0) & (edge1 <= 0) & (edge2 <= 0)
            if not inside.any():
                continue
            reciprocal_w = (
                (edge0 / area) / clip[0, 3]
                + (edge1 / area) / clip[1, 3]
                + (edge2 / area) / clip[2, 3]
            )
            shell_w = np.asarray(np.float32(1) / reciprocal_w, dtype=np.float32)
            target_near = nearest[y0:y1 + 1, x0:x1 + 1]
            target_far = farthest[y0:y1 + 1, x0:x1 + 1]
            np.minimum(target_near, np.where(inside, shell_w, np.inf), out=target_near)
            np.maximum(target_far, np.where(inside, shell_w, -np.inf), out=target_far)
    return np.isfinite(nearest), nearest, farthest


def _coarse_far_envelope(farthest: np.ndarray, coverage: np.ndarray) -> np.ndarray:
    """Apply the perspective back shader's 2x2 coarse derivative envelope."""
    safe = np.where(coverage, farthest, np.float32(0)).astype(np.float32)
    result = safe.copy()
    height, width = safe.shape
    for y in range(0, height, 2):
        y1 = min(y + 1, height - 1)
        for x in range(0, width, 2):
            x1 = min(x + 1, width - 1)
            dx = safe[y, x1] - safe[y, x]
            dy = safe[y1, x] - safe[y, x]
            result[y:y + 2, x:x + 2] += np.float32(.5) * (abs(dx) + abs(dy))
    return result


def rasterize_probe_screen_lookup(
    records, view_to_world, cam_world_to_clip, linear_depth, *,
    screen_to_view_x: float, near_clip: float, record_count: int | None = None,
    tile_size: int = 8, raster_width: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Build full and opaque probe bitfields from a saved linear depth view.

    This selects the retail box or cylindrical topology from each record, then
    executes the recovered shell vertex math, homogeneous clipping,
    pixel-center triangle coverage, front depth test, and perspective back
    derivative predicate. The software raster convention is capture-validated
    but fixed-function D3D edge ownership and depth quantization can differ at
    boundary pixels.
    """
    raw = _record_bytes(records)
    count = _active_count(len(raw), record_count)
    depth = np.asarray(linear_depth, dtype=np.float32)
    size = int(tile_size)
    if depth.ndim != 2 or not np.isfinite(depth).all() or np.any(depth < 0):
        raise ValueError('Linear depth must be a finite nonnegative 2D array')
    if size <= 0:
        raise ValueError('Depth tile size must be positive')
    tile_near, tile_far = reduce_linear_depth_bounds(depth, size)
    height, width = tile_near.shape
    if raster_width is None:
        if depth.shape[1] % 4:
            raise ValueError(
                'Quarter-resolution raster width requires a source width divisible by four'
            )
        raster_width = depth.shape[1] // 4
    push = light_shell_vertex_push_scale(screen_to_view_x, raster_width)
    view = np.asarray(view_to_world, dtype=np.float32)
    if view.shape != (4, 4) or not np.isfinite(view).all():
        raise ValueError('view_to_world must be a finite 4x4 row-vector matrix')
    camera = view[3, :3]
    front = np.zeros((count, height, width), dtype=bool)
    rejected = np.zeros_like(front)
    for index in range(count):
        row = raw[index].view('<f4').reshape(32)
        flags = int(raw[index, 44:48].copy().view('<u4')[0])
        project = project_probe_cylinder_shell if flags & 1 else project_probe_box_shell
        clip = project(
            raw[index:index + 1], view, cam_world_to_clip,
            vert_push_scale=push, near_clip=near_clip,
        )
        coverage, shell_near, shell_far = _rasterize_shell_depth(clip, width, height)
        axis_x, axis_y = row[0:3], row[4:7]
        axis_z = np.cross(axis_x, axis_y) * row[7]
        extents = np.float32(1) / row[12:15]
        local_camera = (
            (camera - row[8:11]) @ np.stack((axis_x, axis_y, axis_z)).T
        )
        camera_inside = bool(np.all(np.abs(local_camera) <= extents))
        front_accept = coverage if camera_inside else coverage & (shell_near <= tile_far)
        envelope = _coarse_far_envelope(shell_far, coverage)
        opaque = front_accept & coverage & (envelope >= tile_near)
        front[index] = front_accept
        rejected[index] = front_accept & ~opaque
    return build_screen_lookup_bitfields(front, rejected)


def rasterize_local_light_screen_lookup(
    placements, view_to_world, cam_world_to_clip, linear_depth, *,
    screen_to_view_x: float, near_clip: float, record_count: int | None = None,
    tile_size: int = 8, raster_width: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Build retail full/opaque light words from explicit manager shell streams.

    ``FillLightLookup`` uploads each submitted light's arbitrary float3 triangle
    stream; no shell topology is present in ``LightGpu``. Given those manager
    inputs, this executes helper ``0x1410B6070``'s cbuffer construction followed
    by the shared vertex shader, perspective front/back depth predicates and
    bitfield writes. The software raster edge caveat is the same as
    :func:`rasterize_probe_screen_lookup`.
    """
    items = tuple(placements)
    count = len(items) if record_count is None else int(record_count)
    if count < 0 or count > len(items):
        raise ValueError('Active light shell count exceeds supplied placements')
    if not all(isinstance(item, LightShellPlacement) for item in items[:count]):
        raise ValueError('placements must contain LightShellPlacement entries')
    depth = np.asarray(linear_depth, dtype=np.float32)
    size = int(tile_size)
    if depth.ndim != 2 or not np.isfinite(depth).all() or np.any(depth < 0):
        raise ValueError('Linear depth must be a finite nonnegative 2D array')
    if size <= 0:
        raise ValueError('Depth tile size must be positive')
    tile_near, tile_far = reduce_linear_depth_bounds(depth, size)
    height, width = tile_near.shape
    if raster_width is None:
        if depth.shape[1] % 4:
            raise ValueError(
                'Quarter-resolution raster width requires a source width divisible by four'
            )
        raster_width = depth.shape[1] // 4
    push = light_shell_vertex_push_scale(screen_to_view_x, raster_width)
    view = np.asarray(view_to_world, dtype=np.float32)
    projection = np.asarray(cam_world_to_clip, dtype=np.float32)
    if (view.shape != (4, 4) or projection.shape != (4, 4)
            or not np.isfinite(view).all() or not np.isfinite(projection).all()
            or not np.array_equal(view[:, 3], np.array((0, 0, 0, 1), np.float32))):
        raise ValueError('Light lookup requires finite affine view/projection matrices')
    camera = view[3, :3]
    front = np.zeros((count, height, width), dtype=bool)
    rejected = np.zeros_like(front)
    for index, placement in enumerate(items[:count]):
        constants = build_light_shell_constants(
            placement, index, vertex_push_scale=push,
        )
        vertices = np.asarray(placement.vertices, dtype=np.float32).reshape(-1, 3, 3)
        clip = project_light_shell_vertices(
            vertices, constants, view, projection, near_clip=near_clip,
        ).clip_positions
        coverage, shell_near, shell_far = _rasterize_shell_depth(clip, width, height)
        normalized_camera = np.asarray(
            (camera - constants['aabb_center'])
            * constants['aabb_inverse_extents'],
            dtype=np.float32,
        )
        camera_inside = bool(np.all(np.abs(normalized_camera) <= np.float32(1)))
        front_accept = coverage if camera_inside else coverage & (shell_near <= tile_far)
        envelope = _coarse_far_envelope(shell_far, coverage)
        opaque = front_accept & coverage & (envelope >= tile_near)
        front[index] = front_accept
        rejected[index] = front_accept & ~opaque
    return build_screen_lookup_bitfields(front, rejected)


def build_local_light_frame_lookup(
    records, placements, view_to_world, cam_world_to_clip, linear_depth, *,
    screen_to_view_x: float, near_clip: float, record_count: int | None = None,
    z_bin_count: int = 65536, tile_size: int = 8,
    raster_width: int | None = None,
) -> dict:
    """Build the recovered local-light lookup resources for one submitted prefix.

    The manager's submitted ``LightGpu`` prefix and prepared shell placements
    share record order. This operation creates the inclusive Z-bin words and
    both screen lookup variants without deriving geometry from shading records.
    Source-light selection and shell preparation remain caller-owned inputs.
    """
    source = np.asarray(records)
    if source.dtype != LIGHT_GPU_DTYPE or source.ndim != 1:
        raise ValueError('records must be a one-dimensional parsed LightGpu array')
    items = tuple(placements)
    count = len(source) if record_count is None else int(record_count)
    if count < 0 or count > len(source):
        raise ValueError('Active light count exceeds supplied LightGpu records')
    if count > len(items):
        raise ValueError('Active light count exceeds supplied shell placements')

    active_records = source[:count].copy()
    z_bin_lookup = generate_light_z_bin_lookup(
        active_records, z_bin_count, record_count=count,
    )
    full_lookup, opaque_lookup = rasterize_local_light_screen_lookup(
        items, view_to_world, cam_world_to_clip, linear_depth,
        screen_to_view_x=screen_to_view_x, near_clip=near_clip,
        record_count=count, tile_size=tile_size, raster_width=raster_width,
    )
    return {
        'light_records': active_records,
        'light_record_count': np.uint32(count),
        'light_z_bin_lookup': z_bin_lookup,
        'light_lookup_full': full_lookup,
        'light_lookup': opaque_lookup,
    }


def rasterize_probe_box_screen_lookup(
    records, view_to_world, cam_world_to_clip, linear_depth, *,
    screen_to_view_x: float, near_clip: float, record_count: int | None = None,
    tile_size: int = 8, raster_width: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Compatibility alias for :func:`rasterize_probe_screen_lookup`."""
    return rasterize_probe_screen_lookup(
        records, view_to_world, cam_world_to_clip, linear_depth,
        screen_to_view_x=screen_to_view_x, near_clip=near_clip,
        record_count=record_count, tile_size=tile_size,
        raster_width=raster_width,
    )


def build_probe_frame_lookup(
    placements, selection_mask, view_to_world, cam_world_to_clip, linear_depth, *,
    screen_to_view_x: float, near_clip: float, z_bin_count: int = 65536,
    tile_size: int = 8, raster_width: int | None = None, bounding_radii=None,
    frustum_planes=None, active_mask=None, excluded_resource_indices=(),
) -> dict:
    """Build the recovered per-view probe records and lookup resources.

    Placement, cube slots, fades, and the active-resource lifecycle remain
    explicit inputs because cooked zone data does not determine their current
    runtime state. ``selection_mask=None`` derives retail's per-view selection
    from the current matrices, or from explicit ``frustum_planes``, plus the
    optional active/excluded resource state.
    Given those inputs, this applies manager ordering and
    compaction, camera Z-bin packing/generation, and the saved-depth screen
    shell path as one frame operation.
    """
    from core.probe_lighting import (
        build_probe_frustum_selection_mask, build_selected_probe_shader_records,
        camera_relative_frustum_planes,
    )

    if selection_mask is None:
        if frustum_planes is None:
            frustum_planes = camera_relative_frustum_planes(
                view_to_world, cam_world_to_clip,
            )
        selection_mask = build_probe_frustum_selection_mask(
            placements, frustum_planes, active_mask=active_mask,
            excluded_resource_indices=excluded_resource_indices,
        )
    elif frustum_planes is not None or active_mask is not None or excluded_resource_indices:
        raise ValueError('Probe selection inputs cannot accompany an explicit selection mask')

    records, placement_indices = build_selected_probe_shader_records(
        placements, selection_mask,
    )
    records, z_bin_scale = populate_probe_z_bin_limits(
        records, view_to_world, bounding_radii=bounding_radii,
    )
    z_bin_lookup = generate_probe_z_bin_lookup(records, z_bin_count)
    full_lookup, opaque_lookup = rasterize_probe_screen_lookup(
        records, view_to_world, cam_world_to_clip, linear_depth,
        screen_to_view_x=screen_to_view_x, near_clip=near_clip,
        tile_size=tile_size, raster_width=raster_width,
    )
    return {
        'probe_records': records,
        'probe_record_count': np.uint32(len(records)),
        'probe_selection_mask': np.asarray(selection_mask, dtype=np.uint8).copy(),
        'probe_placement_indices': placement_indices,
        'probe_z_bin_scale': z_bin_scale,
        'probe_z_bin_lookup': z_bin_lookup,
        'probe_lookup_full': full_lookup,
        'probe_lookup': opaque_lookup,
    }


def perspective_back_rejection(shell_w, coarse_ddx_w, coarse_ddy_w, scene_depth):
    """Return the exact perspective back-fragment depth predicate."""
    w, dx, dy, depth = np.broadcast_arrays(
        np.asarray(shell_w, np.float32), np.asarray(coarse_ddx_w, np.float32),
        np.asarray(coarse_ddy_w, np.float32), np.asarray(scene_depth, np.float32),
    )
    return (w + (np.abs(dx) + np.abs(dy)) * np.float32(.5)) < depth


def orthographic_back_rejection(shell_z, coarse_ddx_depth, coarse_ddy_depth,
                                scene_depth, near_clip: float, far_clip: float):
    """Return the exact orthographic back-fragment depth predicate.

    The shader first maps clip-space Z with ``(near - far) * z + far``. The
    supplied derivatives are derivatives of that mapped value, matching the
    values produced by ``ddx_coarse`` and ``ddy_coarse`` in the pixel shader.
    """
    if not np.isfinite([near_clip, far_clip]).all():
        raise ValueError('Orthographic clip distances must be finite')
    z, dx, dy, depth = np.broadcast_arrays(
        np.asarray(shell_z, np.float32), np.asarray(coarse_ddx_depth, np.float32),
        np.asarray(coarse_ddy_depth, np.float32), np.asarray(scene_depth, np.float32),
    )
    mapped = (np.float32(near_clip) - np.float32(far_clip)) * z + np.float32(far_clip)
    return (mapped + (np.abs(dx) + np.abs(dy)) * np.float32(.5)) < depth
