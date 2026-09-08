"""Explicit per-view Hair scene resources, shared by the viewport and GPU checks.

The validator accepts native current-view lookups and resident resources. The
local-light adapter can generate its screen lookup from explicit manager
placements and linear depth. Asset placement, selection and residency remain
caller-owned.
"""
from __future__ import annotations

import ctypes
import struct
import numpy as np

from core.hair_lighting_replay import validate_replay_bundle
from core.local_lights import (
    parse_light_gpu_records,
    parse_light_volume_gpu_records,
)


_LOCAL_LIGHT_KEYS = ('light_lookup', 'light_records')


def _validate_light_volumes(bundle, arrays):
    if 'light_volumes' not in bundle:
        return None
    raw = np.asarray(bundle['light_volumes'])
    if (raw.ndim != 2 or raw.shape[1:] != (128,)
            or raw.dtype != np.uint8):
        raise ValueError(
            'light_volumes must be a (count, 128) uint8 array')
    volumes = parse_light_volume_gpu_records(
        np.ascontiguousarray(raw).tobytes())
    if not np.isfinite(volumes.view('<f4')).all():
        raise ValueError('Light-volume records must contain finite fields')
    arrays['light_volumes'] = np.ascontiguousarray(raw)
    return volumes


def _key_shadow_volume_ranges(world, scene_flags):
    constants = np.frombuffer(world.tobytes(), '<f4').reshape(56, 4)
    maximum_cascade = int(constants[14, 2])
    if (maximum_cascade < 0 or maximum_cascade > 5
            or constants[14, 2] != maximum_cascade
            or not np.isfinite(constants[14:28]).all()):
        raise ValueError(
            'Key shadow-volume selectors require finite rows and at most six cascades')
    ranges = []
    if scene_flags & 64:
        for cascade in range(maximum_cascade + 1):
            encoded = np.float32(constants[22 + cascade, 3])
            count = int(np.float32(
                (encoded - np.floor(encoded)) * np.float32(64)))
            if not count:
                continue
            first = int(np.rint(encoded))
            if first < 0:
                raise ValueError('Key shadow-volume first index must be nonnegative')
            ranges.append((cascade, first, count))
    return ranges


def _validate_key_shadow_volumes(world, scene_flags, volumes, params):
    ranges = _key_shadow_volume_ranges(world, scene_flags)
    if ranges and volumes is None:
        raise ValueError(
            'Enabled key shadow-volume ranges require light_volumes')
    if volumes is not None:
        for _, first, count in ranges:
            if first + count > len(volumes):
                raise ValueError(
                    'Key shadow-volume range exceeds supplied light_volumes')
    params.update(
        has_light_volumes=volumes is not None,
        key_shadow_volume_ranges=ranges,
        needs_key_shadow_gobo=bool(ranges))


def _validate_gobo_atlas(bundle, world, arrays, params):
    """Validate the atlas shared by key and local gobo/shadow-volume paths."""
    constants = np.frombuffer(world.tobytes(), '<f4', count=4, offset=640)
    if (not np.isfinite(constants).all() or constants[2] < 0
            or constants[3] < 0):
        raise ValueError('Key-gobo constants must be finite and nonnegative')
    key_enabled = bool(constants[3] > 0)
    required = (key_enabled or params['needs_local_gobo']
                or params['needs_key_shadow_gobo'])
    if 'gobo_atlas' not in bundle:
        if required:
            raise ValueError(
                'Enabled key/local gobo stages require the shared gobo_atlas')
        params.update(has_gobo_atlas=False, key_gobo_enabled=False)
        return
    atlas = np.asarray(bundle['gobo_atlas'])
    if (atlas.shape != (2048, 4096) or atlas.dtype.kind != 'u'
            or atlas.dtype.itemsize != 4):
        raise ValueError(
            'gobo_atlas must be the native 2048x4096 packed uint32 texture')
    if any(np.any(((atlas >> shift) & 31) == 31)
           for shift in (6, 17, 27)):
        raise ValueError('gobo_atlas must contain finite R11G11B10 colors')
    arrays['gobo_atlas'] = np.ascontiguousarray(atlas, np.uint32)
    params.update(has_gobo_atlas=True, key_gobo_enabled=key_enabled)


def _validate_cloud_shadow(bundle, world, arrays, params):
    """Validate the optional filtered cloud-shadow texture."""
    constants = np.frombuffer(world.tobytes(), '<f4', count=4, offset=656)
    if (not np.isfinite(constants).all() or constants[0] < 0
            or constants[1] < 0 or constants[1] > 1 or constants[2] < 0):
        raise ValueError('Cloud-shadow constants must be finite and in range')
    enabled = bool(constants[0] > 0)
    if 'cloud_shadow' not in bundle:
        if enabled:
            raise ValueError(
                'Enabled cloud-shadow constants require cloud_shadow')
        params.update(
            has_cloud_shadow=False, cloud_shadow_enabled=False,
            cloud_shadow_storage=None)
        return

    image = np.asarray(bundle['cloud_shadow'])
    if image.ndim == 3 and image.dtype == np.uint8 and image.shape[2] == 4:
        storage = 'rgba8'
    elif image.ndim == 2 and image.dtype.kind == 'u' and image.dtype.itemsize == 4:
        if any(np.any(((image >> shift) & 31) == 31) for shift in (6, 17, 27)):
            raise ValueError(
                'cloud_shadow must contain finite R11G11B10 colors')
        storage = 'r11g11b10'
    elif (image.ndim == 3 and image.dtype == np.float32
          and image.shape[2] in (3, 4)):
        if not np.isfinite(image).all():
            raise ValueError('cloud_shadow float pixels must be finite')
        storage = f'rgb{image.shape[2]}f'
    else:
        raise ValueError(
            'cloud_shadow must be RGBA8, packed R11G11B10, or RGB(A) float32')
    if (not image.shape[0] or not image.shape[1]
            or image.shape[0] > 16384 or image.shape[1] > 16384):
        raise ValueError('cloud_shadow dimensions must be in 1..16384')
    arrays['cloud_shadow'] = np.ascontiguousarray(image)
    params.update(
        has_cloud_shadow=True, cloud_shadow_enabled=enabled,
        cloud_shadow_storage=storage)


def _validate_local_lights(
        bundle, world, width, height, arrays, params, volumes):
    """Validate the optional native local-light resource block.

    The lookup itself determines the minimum live record prefix. A loader may
    provide ``light_record_count`` when the manager's submitted count is known;
    otherwise the highest referenced bit is the only defensible boundary.
    """
    supplied = [name for name in _LOCAL_LIGHT_KEYS if name in bundle]
    optional_supplied = 'light_record_count' in bundle
    if not supplied and not optional_supplied:
        params.update(
            has_local_resources=False, has_local_lights=False,
            local_light_word_count=0, local_light_record_count=0,
            local_light_record_capacity=0, needs_local_gobo=False,
        )
        return
    if len(supplied) != len(_LOCAL_LIGHT_KEYS):
        raise ValueError(
            'Local Hair lighting requires both light_lookup and light_records')

    lookup = np.asarray(bundle['light_lookup'])
    words = struct.unpack_from('<I', world.tobytes(), 44)[0]
    expected_size = ((height + 7) // 8, (width + 7) // 8)
    if (lookup.ndim != 3 or lookup.dtype.kind != 'u'
            or lookup.dtype.itemsize != 4):
        raise ValueError(
            'light_lookup must be a (words, height, width) uint32 array')
    if lookup.shape[0] < max(1, words) or lookup.shape[1:] != expected_size:
        raise ValueError(
            'light_lookup does not cover the current viewport and word count')

    raw_records = np.asarray(bundle['light_records'])
    if (raw_records.ndim != 2 or raw_records.shape[1:] != (128,)
            or raw_records.dtype != np.uint8):
        raise ValueError('light_records must be a (count, 128) uint8 array')
    records = parse_light_gpu_records(
        np.ascontiguousarray(raw_records).tobytes())
    active_masks = (
        np.bitwise_or.reduce(lookup[:words].reshape(words, -1), axis=1)
        if words else np.empty(0, np.uint32))
    referenced = [
        word * 32 + bit
        for word, mask in enumerate(active_masks)
        for bit in range(32) if int(mask) & (1 << bit)
    ]
    effective_count = referenced[-1] + 1 if referenced else 0
    if 'light_record_count' in bundle:
        value = np.asarray(bundle['light_record_count'])
        if value.shape != () or value.dtype.kind != 'u':
            raise ValueError('light_record_count must be an unsigned scalar')
        record_count = int(value)
    else:
        record_count = effective_count
    if (record_count < effective_count or record_count > len(records)
            or words > (record_count + 31) // 32):
        raise ValueError(
            'Local-light lookup or word count references a missing light record')

    active = records[referenced] if referenced else records[:0]
    float_fields = (
        'world_axis_x', 'bulb_radius', 'world_axis_y', 'bulb_length',
        'world_axis_z', 'bulb_push_forward', 'world_position',
        'inverse_attenuation_radius', 'linear_color', 'specular_intensity',
        'cone_parameters', 'cut_on_depth', 'cut_off_depth',
        'reciprocal_cone_sine',
    )
    if any(not np.isfinite(active[name]).all() for name in float_fields):
        raise ValueError('Active local-light records must contain finite fields')
    if (np.any(active['bulb_length'] < 0)
            or np.any(active['inverse_attenuation_radius'] < 0)
            or np.any(active['linear_color'] < 0)):
        raise ValueError(
            'Active local-light lengths, ranges and colors must be nonnegative')
    needs_volumes = bool(len(active) and (
        np.any(active['clip_volume_info'] >> 16)
        or np.any(active['bit_flags_vfog'] & 2)
        or np.any((active['mod_id_and_gobo_id'] >> 16) != 0xffff)
        or np.any(active['shadow_map_info'] >> 16)
        or np.any(active['shadow_volume_info'] >> 16)))
    if volumes is None and needs_volumes:
        raise ValueError(
            'Referenced local-light modifiers require light_volumes')

    if volumes is not None:
        capacity = len(volumes)
        for record in active:
            for field in ('clip_volume_info', 'shadow_volume_info'):
                info = int(record[field])
                first, count = info & 0xffff, info >> 16
                if first + count > capacity:
                    raise ValueError(
                        f'{field} range exceeds supplied light_volumes')
            flags = int(record['bit_flags_vfog'])
            packed_mod = int(record['mod_id_and_gobo_id'])
            if flags & 2 and (packed_mod & 0xffff) >= capacity:
                raise ValueError(
                    'Color-volume index exceeds supplied light_volumes')
            gobo = packed_mod >> 16
            if gobo != 0xffff and gobo >= capacity:
                raise ValueError('Gobo index exceeds supplied light_volumes')

    if len(active) and np.any(active['shadow_map_info'] >> 16):
        if 'key_shadow_depth' not in bundle:
            raise ValueError(
                'Local shadow-map records require the shared key_shadow_depth atlas')

    needs_gobo = bool(len(active) and (
        np.any((active['mod_id_and_gobo_id'] >> 16) != 0xffff)
        or np.any(active['shadow_volume_info'] >> 16)))
    arrays['light_lookup'] = np.ascontiguousarray(lookup, np.uint32)
    arrays['light_records'] = np.ascontiguousarray(raw_records)
    params.update(
        has_local_resources=True,
        has_local_lights=bool(words and record_count),
        local_light_word_count=words,
        local_light_record_count=record_count,
        local_light_record_capacity=len(records),
        needs_local_gobo=needs_gobo,
    )


def build_hair_scene_local_lookup(
        bundle, placements, linear_depth, *, view_to_world,
        cam_world_to_clip, screen_to_view_x: float, near_clip: float,
        record_count: int | None = None, z_bin_count: int = 65536,
        raster_width: int | None = None):
    """Attach generated local-light lookup resources to one explicit scene view.

    ``bundle`` supplies raw ``light_records`` and the ordinary Hair scene
    resources. The ordered manager placements and current full-resolution
    linear depth remain explicit live inputs. This helper runs the recovered
    frame producer, updates the world's active lookup-word count, and returns a
    new mapping accepted by :func:`validate_hair_scene`.

    The generated ``light_lookup`` is the opaque-depth-filtered variant consumed
    by Hair. ``light_lookup_full`` and ``light_z_bin_lookup`` are retained in the
    returned mapping for other recovered passes and diagnostics.
    """
    if 'light_records' not in bundle:
        raise ValueError('Generated local Hair lookup requires light_records')
    raw_records = np.asarray(bundle['light_records'])
    if (raw_records.ndim != 2 or raw_records.shape[1:] != (128,)
            or raw_records.dtype != np.uint8):
        raise ValueError('light_records must be a (count, 128) uint8 array')
    records = parse_light_gpu_records(
        np.ascontiguousarray(raw_records).tobytes())
    from core.probe_lookup import build_local_light_frame_lookup
    frame = build_local_light_frame_lookup(
        records, placements, view_to_world, cam_world_to_clip, linear_depth,
        screen_to_view_x=screen_to_view_x, near_clip=near_clip,
        record_count=record_count, z_bin_count=z_bin_count,
        raster_width=raster_width,
    )

    result = {name: bundle[name] for name in bundle.keys()}
    world = np.asarray(bundle['world_cbuffer'])
    if world.shape != (896,) or world.dtype != np.uint8:
        raise ValueError('Scene world constants must contain 896 uint8 bytes')
    world = np.ascontiguousarray(world).copy()
    view = np.asarray(bundle['viewport_cbuffer'])
    if view.shape != (480,) or view.dtype != np.uint8:
        raise ValueError('Scene viewport constants must contain 480 uint8 bytes')
    dimensions = np.frombuffer(view.tobytes(), '<f4', count=2, offset=400)
    depth = np.asarray(linear_depth)
    if (not np.isfinite(dimensions).all() or np.any(dimensions < 1)
            or tuple(map(int, dimensions[::-1])) != depth.shape):
        raise ValueError('Local-light linear depth must match the scene viewport')
    count = int(frame['light_record_count'])
    words = (count + 31) // 32
    struct.pack_into('<I', world, 44, words)
    opaque = frame['light_lookup']
    full = frame['light_lookup_full']
    if not words:
        # The upload contract retains one inert array slice when a present
        # local-light block has an empty active prefix.
        height, width = opaque.shape[1:]
        opaque = np.zeros((1, height, width), np.uint32)
        full = opaque.copy()
    result.update(
        world_cbuffer=world,
        light_records=np.ascontiguousarray(raw_records),
        light_record_count=np.asarray(count, np.uint32),
        light_lookup=np.ascontiguousarray(opaque),
        light_lookup_full=np.ascontiguousarray(full),
        light_z_bin_lookup=np.ascontiguousarray(frame['light_z_bin_lookup']),
    )
    return result


def validate_hair_scene(bundle):
    lookup = np.asarray(bundle['probe_lookup'])
    if lookup.ndim != 3 or lookup.dtype.kind != 'u' or lookup.dtype.itemsize != 4:
        raise ValueError('probe_lookup must be a (words, height, width) uint32 array')
    world = np.asarray(bundle['world_cbuffer'])
    view = np.asarray(bundle['viewport_cbuffer'])
    if world.shape != (896,) or world.dtype != np.uint8 or view.shape != (480,) or view.dtype != np.uint8:
        raise ValueError('Scene constants must contain 896 world and 480 viewport bytes')
    words = struct.unpack_from('<I', world.tobytes(), 748)[0]
    dimensions = np.frombuffer(view.tobytes(), '<f4', count=2, offset=400)
    if (not np.isfinite(dimensions).all() or np.any(dimensions < 1)
            or np.any(dimensions != np.floor(dimensions)) or np.any(dimensions > 16384)):
        raise ValueError('Scene viewport dimensions must be positive integral pixels')
    width, height = map(int, dimensions)
    if lookup.shape[0] < max(1, words) or lookup.shape[1:] != ((height + 7) // 8, (width + 7) // 8):
        raise ValueError('probe_lookup does not cover the current viewport and word count')
    # Reuse the validated resource schema, reducing the full-view lookup only
    # for bounds checking. The GPU receives the original per-tile words.
    probe_masks = np.bitwise_or.reduce(lookup[:words].reshape(words, -1), axis=1) if words else np.empty(0, np.uint32)
    check = dict(bundle)
    if 'probe_record_count' not in check:
        effective_count = 0
        for word, mask in enumerate(probe_masks):
            if mask:
                effective_count = word * 32 + int(mask).bit_length()
        check['probe_record_count'] = np.array(effective_count, np.uint32)
    check.update(world_points=np.zeros((1, 3), np.float32),
                 shading_normals=np.array([[0, 0, 1]], np.float32),
                 environment_normals=np.array([[0, 0, 1]], np.float32),
                 reflection_directions=np.array([[0, 0, 1]], np.float32),
                 average_gloss=np.array([0.5], np.float32),
                 lookup_words=probe_masks.reshape(1, words))
    arrays, params = validate_replay_bundle(check)
    arrays['probe_lookup'] = np.ascontiguousarray(lookup, dtype=np.uint32)
    params['viewport_size'] = (width, height)
    params['key_color'] = struct.unpack_from('<3f', world.tobytes(), 192)
    params['key_direction'] = struct.unpack_from('<3f', world.tobytes(), 208)
    params['scene_flags'] = struct.unpack_from('<I', world.tobytes(), 892)[0]
    if (not np.isfinite((*params['key_color'], *params['key_direction'])).all()
            or np.any(np.asarray(params['key_color']) < 0)
            or np.linalg.norm(params['key_direction']) == 0):
        raise ValueError('Scene key light must have finite radiance and a nonzero direction')
    params['has_key_shadow'] = 'key_shadow_depth' in bundle
    params['has_history'] = 'reflection_history' in bundle or 'reflection_velocity' in bundle
    viewport = np.frombuffer(view.tobytes(), '<f4').reshape(-1, 4)
    params['temporal_index'] = float(viewport[21, 2])
    params['temporal_plus_cycle'] = float(viewport[25, 3])
    params['history_world_to_clip'] = viewport[4:7, :2].tolist()
    params['view_to_screen'] = viewport[22].tolist()
    params['screen_to_view'] = viewport[23].tolist()
    params['view_rotation'] = (viewport[:3, :3] * np.array([[1], [-1], [-1]], np.float32)).tolist()
    params['has_denoise_mask'] = 'denoise_mask' in bundle
    if not np.isfinite([params['temporal_index'], params['temporal_plus_cycle'],
                        *viewport[4:7, :2].flat, *viewport[:3, :3].flat, *viewport[22:24].flat]).all():
        raise ValueError('Scene history projection and temporal constants must be finite')
    if params['has_history']:
        if not all(name in bundle for name in ('reflection_history', 'reflection_velocity')):
            raise ValueError('Reflection history requires both color and velocity')
        history, velocity = np.asarray(bundle['reflection_history']), np.asarray(bundle['reflection_velocity'])
        size = ((height + 1) // 2, (width + 1) // 2)
        if history.shape != size or history.dtype.kind != 'u' or history.dtype.itemsize != 4:
            raise ValueError('reflection_history must be half-resolution packed R11G11B10 uint32')
        if any(np.any(((history >> shift) & 31) == 31) for shift in (6, 17, 27)):
            raise ValueError('reflection_history must contain finite R11G11B10 colors')
        if velocity.shape != (*size, 2) or velocity.dtype.kind != 'f' or velocity.dtype.itemsize != 2 or not np.isfinite(velocity).all():
            raise ValueError('reflection_velocity must be finite half-resolution RG16F')
        arrays['reflection_history'] = np.ascontiguousarray(history, dtype=np.uint32)
        arrays['reflection_velocity'] = np.ascontiguousarray(velocity, dtype=np.float16)
    if params['has_denoise_mask']:
        mask = np.asarray(bundle['denoise_mask'])
        if mask.shape != (height, width) or mask.dtype != np.uint8:
            raise ValueError('denoise_mask must contain full-resolution R8_UNORM uint8 values')
        arrays['denoise_mask'] = np.ascontiguousarray(mask)
    if params['has_key_shadow']:
        depth = np.asarray(bundle['key_shadow_depth'])
        if depth.shape != (8192, 8192) or depth.dtype.kind != 'u' or depth.dtype.itemsize != 2:
            raise ValueError('key_shadow_depth must contain the native 8192x8192 uint16 atlas')
        constants = np.frombuffer(world.tobytes(), '<f4').reshape(-1, 4)
        if (not np.isfinite(constants[14:40]).all() or constants[14, 2] < 0
                or constants[14, 2] > 5 or constants[14, 2] != np.floor(constants[14, 2])):
            raise ValueError('Key shadow constants require finite rows and at most six cascades')
        arrays['key_shadow_depth'] = np.ascontiguousarray(depth, dtype=np.uint16)
    _validate_cloud_shadow(bundle, world, arrays, params)
    volumes = _validate_light_volumes(bundle, arrays)
    _validate_local_lights(
        bundle, world, width, height, arrays, params, volumes)
    _validate_key_shadow_volumes(
        world, params['scene_flags'], volumes, params)
    _validate_gobo_atlas(bundle, world, arrays, params)
    return arrays, params


class HairSceneGpu:
    """Own scene GPU resources in the caller's current GL 4.3 context."""

    def __init__(self, arrays, params):
        from OpenGL import GL
        from OpenGL.raw.GL.VERSION.GL_1_1 import glTexImage2D
        from OpenGL.raw.GL.VERSION.GL_1_2 import glTexImage3D
        from OpenGL.raw.GL.VERSION.GL_1_3 import glCompressedTexImage2D, glCompressedTexImage3D

        self.params = params
        self.buffers = []
        self.textures = []
        self.bindings = []
        self.samplers = []
        self.denoise_mask_texture = 0
        self.world_constants = np.frombuffer(arrays['world_cbuffer'], np.float32).reshape(56, 4)
        has_auxiliary = (params['has_local_resources']
                         or params['has_light_volumes']
                         or params['has_gobo_atlas'])
        required_units = 22 if has_auxiliary else 18
        if params['has_cloud_shadow']:
            required_units = max(
                required_units,
                23 if has_auxiliary else 19)
        if int(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_IMAGE_UNITS)) < required_units:
            raise RuntimeError(f'Scene Hair lighting requires {required_units} fragment texture units')
        if len(arrays['grid_data']) > int(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_BUFFER_SIZE)):
            raise ValueError('The resident light grid exceeds this GPU buffer-texture limit')
        try:
            def texture(unit, name, target):
                tex = int(GL.glGenTextures(1))
                self.textures.append(tex)
                self.bindings.append((unit, name, target, tex))
                GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
                GL.glBindTexture(target, tex)
                return tex

            def sampling(target, levels, integer=False):
                GL.glTexParameteri(target, GL.GL_TEXTURE_BASE_LEVEL, 0)
                GL.glTexParameteri(target, GL.GL_TEXTURE_MAX_LEVEL, levels - 1)
                GL.glTexParameteri(target, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST if integer else GL.GL_LINEAR_MIPMAP_LINEAR)
                GL.glTexParameteri(target, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST if integer else GL.GL_LINEAR)
                for axis in (GL.GL_TEXTURE_WRAP_S, GL.GL_TEXTURE_WRAP_T, GL.GL_TEXTURE_WRAP_R):
                    GL.glTexParameteri(target, axis, GL.GL_CLAMP_TO_EDGE)

            GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
            GL.glEnable(GL.GL_TEXTURE_CUBE_MAP_SEAMLESS)
            for prefix, unit, name, target in (
                ('default', 5, 'uFurEnvironment', GL.GL_TEXTURE_CUBE_MAP),
                ('local', 7, 'uHairLocalCubes', GL.GL_TEXTURE_CUBE_MAP_ARRAY),
            ):
                texture(unit, name, target)
                compressed = params['cube_formats'][prefix] == 'bc6u'
                base_width = arrays[f'{prefix}_bc6_mip0'].shape[-2] * 4 if compressed else 0
                for mip in range(6):
                    data = arrays[f'{prefix}_bc6_mip{mip}' if compressed else f'{prefix}_mip{mip}']
                    width = max(1, base_width >> mip) if compressed else data.shape[-2]
                    if prefix == 'default':
                        for face in range(6):
                            pixels = np.ascontiguousarray(data[face])
                            pointer = ctypes.c_void_p(pixels.ctypes.data)
                            if compressed:
                                glCompressedTexImage2D(GL.GL_TEXTURE_CUBE_MAP_POSITIVE_X + face, mip,
                                    GL.GL_COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT, width, width, 0, pixels.nbytes, pointer)
                            else:
                                glTexImage2D(GL.GL_TEXTURE_CUBE_MAP_POSITIVE_X + face, mip,
                                    GL.GL_RGB32F, width, width, 0, GL.GL_RGB, GL.GL_FLOAT, pointer)
                    elif compressed:
                        glCompressedTexImage3D(target, mip, GL.GL_COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT,
                            width, width, data.shape[0] * 6, 0, data.nbytes, ctypes.c_void_p(data.ctypes.data))
                    else:
                        glTexImage3D(target, mip, GL.GL_RGB32F, width, width, data.shape[0] * 6,
                                    0, GL.GL_RGB, GL.GL_FLOAT, ctypes.c_void_p(data.ctypes.data))
                sampling(target, 6)

            for unit, name, key, internal in (
                (8, 'uHairProbeRows', 'probe_records', GL.GL_RGBA32F),
                (10, 'uHairGridLookup', 'grid_lookup', GL.GL_R32UI),
                (11, 'uHairGridRecords', 'grid_data', GL.GL_RGBA32UI),
            ):
                data = arrays[key]
                buffer = int(GL.glGenBuffers(1))
                self.buffers.append(buffer)
                GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, buffer)
                GL.glBufferData(GL.GL_TEXTURE_BUFFER, max(16, data.nbytes), data if data.nbytes else None, GL.GL_STATIC_DRAW)
                texture(unit, name, GL.GL_TEXTURE_BUFFER)
                GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, internal, buffer)

            data = arrays['probe_lookup']
            texture(9, 'uHairProbeLookup', GL.GL_TEXTURE_2D_ARRAY)
            glTexImage3D(GL.GL_TEXTURE_2D_ARRAY, 0, GL.GL_R32UI, data.shape[2], data.shape[1], data.shape[0],
                         0, GL.GL_RED_INTEGER, GL.GL_UNSIGNED_INT, ctypes.c_void_p(data.ctypes.data))
            sampling(GL.GL_TEXTURE_2D_ARRAY, 1, True)
            data = arrays.get('distant_height', np.zeros((1, 1), np.float32))
            texture(12, 'uHairDistantHeight', GL.GL_TEXTURE_2D)
            glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_R32F, data.shape[1], data.shape[0], 0,
                         GL.GL_RED, GL.GL_FLOAT, ctypes.c_void_p(data.ctypes.data))
            sampling(GL.GL_TEXTURE_2D, 1)
            data = arrays.get('distant_samples', np.zeros((1, 1, 1, 4), np.float32))
            texture(13, 'uHairDistantSamples', GL.GL_TEXTURE_3D)
            glTexImage3D(GL.GL_TEXTURE_3D, 0, GL.GL_RGBA32F, data.shape[2], data.shape[1], data.shape[0],
                         0, GL.GL_RGBA, GL.GL_FLOAT, ctypes.c_void_p(data.ctypes.data))
            sampling(GL.GL_TEXTURE_3D, 1)
            if params['has_key_shadow']:
                depth = arrays['key_shadow_depth']
                tex = texture(14, 'uHairShadowAtlas', GL.GL_TEXTURE_2D)
                glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_DEPTH_COMPONENT16, 8192, 8192, 0,
                             GL.GL_DEPTH_COMPONENT, GL.GL_UNSIGNED_SHORT, ctypes.c_void_p(depth.ctypes.data))
                sampling(GL.GL_TEXTURE_2D, 1)
                # One atlas with independent regular and strict-Less samplers.
                self.bindings.append((15, 'uHairShadowCompare', GL.GL_TEXTURE_2D, tex))
                sampler = int(GL.glGenSamplers(1))
                self.samplers.append((15, sampler))
                for name, value in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR),
                                    (GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR),
                                    (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
                                    (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE),
                                    (GL.GL_TEXTURE_COMPARE_MODE, GL.GL_COMPARE_REF_TO_TEXTURE),
                                    (GL.GL_TEXTURE_COMPARE_FUNC, GL.GL_LESS)):
                    GL.glSamplerParameteri(sampler, name, value)
            else:
                self.bindings.extend(((14, 'uHairShadowAtlas', GL.GL_TEXTURE_2D, 0),
                                      (15, 'uHairShadowCompare', GL.GL_TEXTURE_2D, 0)))
            for unit, name, key, internal, form, kind in (
                (16, 'uHairReflectionHistory', 'reflection_history', GL.GL_R11F_G11F_B10F, GL.GL_RGB, GL.GL_UNSIGNED_INT_10F_11F_11F_REV),
                (17, 'uHairReflectionVelocity', 'reflection_velocity', GL.GL_RG16F, GL.GL_RG, GL.GL_HALF_FLOAT),
            ):
                if params['has_history']:
                    data = arrays[key]
                    texture(unit, name, GL.GL_TEXTURE_2D)
                    glTexImage2D(GL.GL_TEXTURE_2D, 0, internal, data.shape[1], data.shape[0], 0,
                                 form, kind, ctypes.c_void_p(data.ctypes.data))
                    sampling(GL.GL_TEXTURE_2D, 1)
                else:
                    self.bindings.append((unit, name, GL.GL_TEXTURE_2D, 0))
            if params['has_local_resources']:
                data = arrays['light_lookup']
                texture(18, 'uHairLocalLightLookup', GL.GL_TEXTURE_2D_ARRAY)
                glTexImage3D(
                    GL.GL_TEXTURE_2D_ARRAY, 0, GL.GL_R32UI,
                    data.shape[2], data.shape[1], data.shape[0], 0,
                    GL.GL_RED_INTEGER, GL.GL_UNSIGNED_INT,
                    ctypes.c_void_p(data.ctypes.data),
                )
                sampling(GL.GL_TEXTURE_2D_ARRAY, 1, True)
                data = np.ascontiguousarray(
                    arrays['light_records']).view('<u4').reshape(-1, 4)
                buffer = int(GL.glGenBuffers(1))
                self.buffers.append(buffer)
                GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, buffer)
                GL.glBufferData(
                    GL.GL_TEXTURE_BUFFER, data.nbytes, data,
                    GL.GL_STATIC_DRAW)
                texture(19, 'uHairLocalLightRows', GL.GL_TEXTURE_BUFFER)
                GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32UI, buffer)
            if params['has_light_volumes'] or params['has_local_resources']:
                data = arrays.get(
                    'light_volumes', np.zeros((1, 128), np.uint8))
                data = np.ascontiguousarray(data).view('<u4').reshape(-1, 4)
                buffer = int(GL.glGenBuffers(1))
                self.buffers.append(buffer)
                GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, buffer)
                GL.glBufferData(
                    GL.GL_TEXTURE_BUFFER, data.nbytes, data,
                    GL.GL_STATIC_DRAW)
                texture(20, 'uHairLocalVolumeRows', GL.GL_TEXTURE_BUFFER)
                GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32UI, buffer)
            if params['has_gobo_atlas']:
                data = arrays['gobo_atlas']
                texture(21, 'uHairGoboAtlas', GL.GL_TEXTURE_2D)
                glTexImage2D(
                    GL.GL_TEXTURE_2D, 0, GL.GL_R11F_G11F_B10F,
                    data.shape[1], data.shape[0], 0, GL.GL_RGB,
                    GL.GL_UNSIGNED_INT_10F_11F_11F_REV,
                    ctypes.c_void_p(data.ctypes.data),
                )
                sampling(GL.GL_TEXTURE_2D, 1)
            elif params['has_local_resources']:
                self.bindings.append(
                    (21, 'uHairGoboAtlas', GL.GL_TEXTURE_2D, 0))
            if params['has_cloud_shadow']:
                data = arrays['cloud_shadow']
                unit = 22 if has_auxiliary else 18
                texture(unit, 'uHairCloudShadow', GL.GL_TEXTURE_2D)
                storage = params['cloud_shadow_storage']
                if storage == 'rgba8':
                    internal, form, kind = (
                        GL.GL_RGBA8, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
                elif storage == 'r11g11b10':
                    internal, form, kind = (
                        GL.GL_R11F_G11F_B10F, GL.GL_RGB,
                        GL.GL_UNSIGNED_INT_10F_11F_11F_REV)
                else:
                    channels = data.shape[2]
                    internal = GL.GL_RGB32F if channels == 3 else GL.GL_RGBA32F
                    form = GL.GL_RGB if channels == 3 else GL.GL_RGBA
                    kind = GL.GL_FLOAT
                glTexImage2D(
                    GL.GL_TEXTURE_2D, 0, internal,
                    data.shape[1], data.shape[0], 0, form, kind,
                    ctypes.c_void_p(data.ctypes.data))
                sampling(GL.GL_TEXTURE_2D, 1)
            if params['has_denoise_mask']:
                # Post passes use preview-oriented textures. Keep fractional
                # Skin masks separate from Hair write eligibility.
                data = np.ascontiguousarray(arrays['denoise_mask'][::-1])
                self.denoise_mask_texture = int(GL.glGenTextures(1))
                self.textures.append(self.denoise_mask_texture)
                GL.glActiveTexture(GL.GL_TEXTURE3)
                previous_texture = int(GL.glGetIntegerv(GL.GL_TEXTURE_BINDING_2D))
                GL.glBindTexture(GL.GL_TEXTURE_2D, self.denoise_mask_texture)
                glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_R8, data.shape[1], data.shape[0], 0,
                             GL.GL_RED, GL.GL_UNSIGNED_BYTE, ctypes.c_void_p(data.ctypes.data))
                sampling(GL.GL_TEXTURE_2D, 1)
                GL.glBindTexture(GL.GL_TEXTURE_2D, previous_texture)
            self.unbind()
            GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, 0)
        except Exception:
            self.close()
            raise

    def bind(self, program):
        from OpenGL import GL
        for unit, name, target, texture in self.bindings:
            GL.glUniform1i(GL.glGetUniformLocation(program, name), unit)
            GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
            GL.glBindTexture(target, texture)
        p = self.params
        for unit, sampler in self.samplers:
            GL.glBindSampler(unit, sampler)
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHairHasKeyShadow'), p['has_key_shadow'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHairHasHistory'), p['has_history'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHairHasLocalLights'), p['has_local_lights'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHairHasGoboAtlas'), p['has_gobo_atlas'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHairHasCloudShadow'), p['has_cloud_shadow'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHairHasLightVolumes'), p['has_light_volumes'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHairLocalLookupWords'), p['local_light_word_count'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHairLocalRecordCount'), p['local_light_record_count'])
        GL.glUniform1ui(GL.glGetUniformLocation(program, 'uHairSceneFlags'), p['scene_flags'])
        GL.glUniform4f(GL.glGetUniformLocation(program, 'uHairViewToScreen'), *p['view_to_screen'])
        GL.glUniformMatrix3x2fv(GL.glGetUniformLocation(program, 'uHairHistoryWorldToClip'), 1, False,
                               np.asarray(p['history_world_to_clip'], np.float32))
        GL.glUniform1f(GL.glGetUniformLocation(program, 'uTemporalIndex'), p['temporal_index'])
        GL.glUniform1f(GL.glGetUniformLocation(program, 'uTemporalPlusCycle'), p['temporal_plus_cycle'])
        GL.glUniform4fv(GL.glGetUniformLocation(program, 'uHairSceneConstants'), 56, self.world_constants)
        for name, values in (
            ('uHairGridCamera', p['camera_position']), ('uHairAmbientFill', p['ambient_fill']),
            ('uHairDistantConstants', p['distant']), ('uHairSceneKeyColor', p['key_color']),
            ('uLightDir', p['key_direction']),
        ):
            GL.glUniform3f(GL.glGetUniformLocation(program, name), *values)
        GL.glUniform4f(GL.glGetUniformLocation(program, 'uHairDistantUV'), *p['distant_uv'])
        GL.glUniform1f(GL.glGetUniformLocation(program, 'uHairIntensity'), p['intensity'])
        GL.glUniform1f(GL.glGetUniformLocation(program, 'uHairBleedReduction'), p['bleed_reduction'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHairProbeCount'), p['record_count'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHairLookupWords'), p['word_count'])

    def unbind(self):
        from OpenGL import GL
        for unit, _, target, _ in self.bindings:
            GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
            GL.glBindTexture(target, 0)
        for unit, _ in self.samplers:
            GL.glBindSampler(unit, 0)
        GL.glActiveTexture(GL.GL_TEXTURE0)

    def bind_denoise(self, program):
        """Bind this frame's projection, timing and neighboring material mask."""
        from OpenGL import GL
        p = self.params
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHasSceneProjection'), 1)
        GL.glUniform4f(GL.glGetUniformLocation(program, 'uSceneScreenToView'), *p['screen_to_view'])
        GL.glUniform4f(GL.glGetUniformLocation(program, 'uSceneViewToScreen'), *p['view_to_screen'])
        GL.glUniformMatrix3fv(GL.glGetUniformLocation(program, 'uViewRotation'), 1, True,
                             np.asarray(p['view_rotation'], np.float32))
        GL.glUniform1f(GL.glGetUniformLocation(program, 'uTemporalIndex'), p['temporal_index'])
        GL.glUniform1f(GL.glGetUniformLocation(program, 'uTemporalPlusCycle'), p['temporal_plus_cycle'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uHasSceneDenoiseMask'), p['has_denoise_mask'])
        GL.glUniform1i(GL.glGetUniformLocation(program, 'uSceneDenoiseMask'), 3)
        GL.glActiveTexture(GL.GL_TEXTURE3)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.denoise_mask_texture)

    def close(self):
        from OpenGL import GL
        self.unbind()
        if self.textures:
            GL.glDeleteTextures(self.textures)
            self.textures.clear()
        self.denoise_mask_texture = 0
        if self.buffers:
            GL.glDeleteBuffers(len(self.buffers), self.buffers)
            self.buffers.clear()
        if self.samplers:
            GL.glDeleteSamplers(len(self.samplers), [sampler for _, sampler in self.samplers])
            self.samplers.clear()
        self.bindings.clear()
