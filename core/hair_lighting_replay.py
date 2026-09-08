"""Replay the recovered Hair indirect-lighting kernels with explicit resources.

This is a diagnostic compute path. It requires captured/resolved inputs and
does not claim complete deferred, shadow, BRDF, or temporal image parity.
"""
from __future__ import annotations

from pathlib import Path
import struct

import numpy as np


def validate_replay_bundle(bundle):
    """Validate the NPZ interchange schema before creating GPU resources."""
    arrays = {}

    def array(name, shape, kind, size=None):
        if name not in bundle:
            raise ValueError(f'Missing replay input: {name}')
        value = np.asarray(bundle[name])
        if len(value.shape) != len(shape) or any(a != b for a, b in zip(value.shape, shape) if b is not None):
            raise ValueError(f'{name} must have shape {shape}; got {value.shape}')
        if value.dtype.kind != kind or (size and value.dtype.itemsize != size):
            raise ValueError(f'{name} has an incompatible dtype: {value.dtype}')
        if kind == 'f' and not np.isfinite(value).all():
            raise ValueError(f'{name} contains nonfinite values')
        arrays[name] = np.ascontiguousarray(value, dtype=np.float32 if kind == 'f' else value.dtype.newbyteorder('='))
        if kind == 'f' and not np.isfinite(arrays[name]).all():
            raise ValueError(f'{name} exceeds the shader float32 range')
        return arrays[name]

    positions = array('world_points', (None, 3), 'f')
    count = len(positions)
    if count == 0:
        raise ValueError('At least one replay query is required')
    cells = np.floor(positions.astype(np.float64) - .5)
    if np.any(cells < -(2**31)) or np.any(cells > 2**31 - 2):
        raise ValueError('World points exceed signed 32-bit light-grid addressing')
    for name in ('shading_normals', 'environment_normals', 'reflection_directions'):
        directions = array(name, (count, 3), 'f')
        if np.any(np.linalg.norm(directions, axis=1) == 0):
            raise ValueError(f'{name} cannot contain zero directions')
    array('average_gloss', (count,), 'f')
    view = array('viewport_cbuffer', (480,), 'u', 1).tobytes()
    world = array('world_cbuffer', (896,), 'u', 1).tobytes()
    word_count = struct.unpack_from('<I', world, 748)[0]
    masks = array('lookup_words', (count, word_count), 'u', 4)
    records = array('probe_records', (None, 128), 'u', 1)
    record_count = len(records)
    if 'probe_record_count' in bundle:
        supplied_count = np.asarray(bundle['probe_record_count'])
        if supplied_count.shape != () or supplied_count.dtype.kind not in 'ui':
            raise ValueError('probe_record_count must be an integer scalar')
        record_count = int(supplied_count)
        if record_count < 0 or record_count > len(records):
            raise ValueError('probe_record_count references a missing record in the supplied probe buffer')
    active = []
    for word in range(word_count):
        combined = int(np.bitwise_or.reduce(masks[:, word]))
        active.extend(word * 32 + bit for bit in range(32) if (combined >> bit) & 1)
    if active and max(active) >= record_count:
        raise ValueError('A probe lookup bit references a missing record')
    lookup = array('grid_lookup', (64**3,), 'u', 4)
    grid = array('grid_data', (None, 4), 'u', 4)
    if len(grid) == 0 or np.any((lookup.astype(np.uint64) & 0xFFFFF000) + 4095 >= len(grid)):
        raise ValueError('The light-grid lookup references missing brick data')
    cube_count = None
    cube_formats = {}
    for prefix, extra in (('default', (6,)), ('local', (None, 6))):
        compressed = f'{prefix}_bc6_mip0' in bundle
        cube_formats[prefix] = 'bc6u' if compressed else 'float32'
        if compressed and any(f'{prefix}_mip{mip}' in bundle for mip in range(6)):
            raise ValueError(f'{prefix} must provide either BC6U blocks or decoded texels, not both')
        base_width = None
        for mip in range(6):
            key = f'{prefix}_bc6_mip{mip}' if compressed else f'{prefix}_mip{mip}'
            value = array(key, (*extra, None, None, 16 if compressed else 3),
                          'u' if compressed else 'f', 1 if compressed else None)
            if base_width is None:
                base_width = value.shape[-2] * (4 if compressed else 1)
                if base_width < 32 or base_width & (base_width - 1):
                    raise ValueError(f'{prefix} mip 0 must have power-of-two faces at least 32 pixels wide')
            width = max(1, base_width >> mip)
            stored_width = max(1, (width + 3) // 4) if compressed else width
            if value.shape[-3:-1] != (stored_width, stored_width):
                raise ValueError(f'{prefix} mip {mip} must have {width}x{width} faces with complete blocks/texels')
            if prefix == 'local':
                if cube_count is None:
                    cube_count = value.shape[0]
                if value.shape[0] != cube_count or cube_count == 0:
                    raise ValueError('Local probe mip levels must have the same nonzero cube count')
    if active:
        cube_indices = records[active].view('<f4').reshape(-1, 32)[:, 15]
        if (not np.isfinite(cube_indices).all() or np.any(cube_indices != np.floor(cube_indices))
                or np.any(cube_indices < 0) or np.any(cube_indices >= cube_count)):
            raise ValueError('An eligible probe references a missing cube array slot')
    params = {
        'camera_position': struct.unpack_from('<3f', view, 48),
        'bleed_reduction': struct.unpack_from('<f', world, 704)[0],
        'ambient_fill': struct.unpack_from('<3f', world, 720),
        'intensity': struct.unpack_from('<f', world, 732)[0],
        'distant_uv': struct.unpack_from('<4f', world, 672),
        'distant': struct.unpack_from('<3f', world, 688),
        'word_count': word_count,
        'record_count': record_count,
        'record_capacity': len(records),
        'cube_formats': cube_formats,
    }
    constants = [*params['camera_position'], params['bleed_reduction'], *params['ambient_fill'],
                 params['intensity'], *params['distant_uv'], *params['distant']]
    if not np.isfinite(constants).all():
        raise ValueError('The selected global lighting constants must be finite')
    if params['distant_uv'][0] != 0:
        height = array('distant_height', (None, None), 'f')
        samples = array('distant_samples', (None, None, None, 4), 'f')
        if any(dim == 0 for dim in (*height.shape, *samples.shape)):
            raise ValueError('Distant GI textures cannot be empty')
    return arrays, params


def replay_hair_lighting(bundle):
    """Return one row per supplied world-point query, rendered offscreen."""
    arrays, params = validate_replay_bundle(bundle)
    from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
    from PyQt6.QtWidgets import QApplication
    from OpenGL import GL
    from OpenGL.GL.shaders import compileProgram, compileShader
    from OpenGL.raw.GL.VERSION.GL_1_3 import glCompressedTexImage2D, glCompressedTexImage3D
    import ctypes

    app = QApplication.instance() or QApplication([])
    fmt = QSurfaceFormat(); fmt.setVersion(4, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    context = QOpenGLContext(); context.setFormat(fmt)
    if not context.create():
        raise RuntimeError('Could not create the OpenGL 4.3 replay context')
    surface = QOffscreenSurface(); surface.setFormat(context.format()); surface.create()
    if not context.makeCurrent(surface):
        raise RuntimeError('Could not activate the offscreen replay surface')
    root = Path(__file__).resolve().parent
    source = '''#version 430 core
layout(local_size_x=64) in;
layout(std430,binding=0) readonly buffer Probes { vec4 probeRows[]; };
layout(std430,binding=1) readonly buffer Lookup { uint gridLookup[]; };
layout(std430,binding=2) readonly buffer Grid { uvec4 gridRecords[]; };
layout(std430,binding=3) readonly buffer Queries { vec4 queries[]; };
layout(std430,binding=4) readonly buffer Masks { uint masks[]; };
layout(std430,binding=5) writeonly buffer Results { vec4 results[]; };
uniform samplerCube defaultCube;
uniform samplerCubeArray localCubes;
uniform sampler2D distantHeight;
uniform sampler3D distantSamples;
uniform uint queryCount, wordCount;
uniform int recordCount;
uniform vec3 cameraPosition, ambientFill, distantConstants;
uniform float bleedReduction, intensity;
uniform vec4 distantUV;
uint queryIndex;
''' + (root / 'hair_light_grid.glsl').read_text() + (root / 'hair_probe_lighting.glsl').read_text() + '''
uint hairGridLookup(uint i) { return gridLookup[i]; }
uvec4 hairGridRecord(uint i) { return gridRecords[i]; }
vec3 hairGridDefault(vec3 d,float mip) { return textureLod(defaultCube,d,mip).rgb; }
float hairGridDistantHeight(vec2 uv) { return textureLod(distantHeight,uv,0.0).r; }
vec4 hairGridDistantSamples(vec3 uvw) { return textureLod(distantSamples,uvw,0.0); }
vec4 hairProbeRow(int i,int row) { return probeRows[i*8+row]; }
bool hairProbeEligible(int i) {
    return uint(i/32)<wordCount && (masks[queryIndex*wordCount+uint(i/32)] & (1u<<uint(i%32)))!=0u;
}
vec3 hairProbeLocal(float index,vec3 d,float mip) { return textureLod(localCubes,vec4(d,index),mip).rgb; }
vec3 hairProbeDefault(vec3 d,float mip) { return textureLod(defaultCube,d,mip).rgb; }
void main() {
    queryIndex=gl_GlobalInvocationID.x;if(queryIndex>=queryCount)return;
    uint q=queryIndex*4u,o=queryIndex*4u;
    HairGridParameters p;
    p.cameraPosition=cameraPosition;p.bleedReduction=bleedReduction;p.ambientFill=ambientFill;
    p.intensity=intensity;p.distantUVScaleOffset=distantUV;
    p.distantIrradianceScale=distantConstants.x;p.distantMidHeight=distantConstants.y;
    p.distantHeightScale=distantConstants.z;
    HairGridLighting grid=hairGridLighting(queries[q].xyz,queries[q+1u].xyz,queries[q+2u].xyz,p);
    HairProbeLighting probe=hairProbeLighting(recordCount,queries[q].xyz,queries[q+2u].xyz,
        queries[q+3u].xyz,queries[q].w,grid.diffuse,grid.reflection,intensity);
    results[o]=vec4(probe.specular,probe.visibility);
    results[o+1u]=vec4(probe.diffuse,probe.coarseLuminance);
    results[o+2u]=vec4(grid.diffuse,grid.reflection);
    results[o+3u]=vec4(probe.defaultCoverage,probe.diffuseCoverage,grid.fallbackWeight,0);
}
'''
    program = 0
    buffers, textures = [], []
    try:
        try:
            program = compileProgram(compileShader(source, GL.GL_COMPUTE_SHADER))
        except Exception as error:
            raise RuntimeError(f'Indirect replay shader failed: {error.args[0]}') from None
        count = len(arrays['world_points'])
        queries = np.zeros((count, 4, 4), np.float32)
        for row, name in enumerate(('world_points', 'shading_normals', 'reflection_directions', 'environment_normals')):
            queries[:, row, :3] = arrays[name]
        queries[:, 0, 3] = arrays['average_gloss']
        output_bytes = count * 4 * 4 * 4
        buffers = list(GL.glGenBuffers(6))
        inputs = [arrays['probe_records'], arrays['grid_lookup'], arrays['grid_data'],
                  queries, arrays['lookup_words'], None]
        for slot, (buffer, data) in enumerate(zip(buffers, inputs)):
            GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER, buffer)
            size = output_bytes if data is None else max(16, data.nbytes)
            # Empty record/mask buffers still need a valid GL allocation.
            payload = data if data is not None and data.nbytes == size else None
            GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER, size, payload, GL.GL_DYNAMIC_READ if data is None else GL.GL_STATIC_DRAW)
            if data is not None and data.nbytes and payload is None:
                GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER, 0, data.nbytes, data)
            GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER, slot, buffer)
        textures = list(GL.glGenTextures(4))
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        for unit, (prefix, target) in enumerate((('default', GL.GL_TEXTURE_CUBE_MAP), ('local', GL.GL_TEXTURE_CUBE_MAP_ARRAY))):
            GL.glActiveTexture(GL.GL_TEXTURE0 + unit); GL.glBindTexture(target, textures[unit])
            compressed = params['cube_formats'][prefix] == 'bc6u'
            base_width = arrays[f'{prefix}_bc6_mip0'].shape[-2] * 4 if compressed else 0
            for mip in range(6):
                if compressed:
                    data = arrays[f'{prefix}_bc6_mip{mip}']
                    width = max(1, base_width >> mip)
                    # Use the raw entry points: PyOpenGL's array-image converter
                    # does not reliably marshal compressed cube-array payloads.
                    if prefix == 'default':
                        for face in range(6):
                            pixels = data[face]
                            glCompressedTexImage2D(GL.GL_TEXTURE_CUBE_MAP_POSITIVE_X + face, mip,
                                GL.GL_COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT, width, width, 0,
                                pixels.nbytes, ctypes.c_void_p(pixels.ctypes.data))
                    else:
                        glCompressedTexImage3D(target, mip, GL.GL_COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT,
                            width, width, data.shape[0] * 6, 0, data.nbytes,
                            ctypes.c_void_p(data.ctypes.data))
                    error = GL.glGetError()
                    if error != GL.GL_NO_ERROR:
                        raise RuntimeError(f'{prefix} BC6U mip {mip} upload failed: GL {error:#x}')
                    continue
                data = arrays[f'{prefix}_mip{mip}']; width = data.shape[-2]
                if prefix == 'default':
                    for face in range(6):
                        GL.glTexImage2D(GL.GL_TEXTURE_CUBE_MAP_POSITIVE_X + face, mip, GL.GL_RGB32F,
                                        width, width, 0, GL.GL_RGB, GL.GL_FLOAT, data[face])
                else:
                    GL.glTexImage3D(target, mip, GL.GL_RGB32F, width, width, data.shape[0] * 6,
                                    0, GL.GL_RGB, GL.GL_FLOAT, data)
            GL.glTexParameteri(target, GL.GL_TEXTURE_MAX_LEVEL, 5)
            GL.glTexParameteri(target, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR_MIPMAP_LINEAR)
            GL.glTexParameteri(target, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            for axis in (GL.GL_TEXTURE_WRAP_S, GL.GL_TEXTURE_WRAP_T, GL.GL_TEXTURE_WRAP_R):
                GL.glTexParameteri(target, axis, GL.GL_CLAMP_TO_EDGE)
        for unit, name, target in ((2, 'distant_height', GL.GL_TEXTURE_2D), (3, 'distant_samples', GL.GL_TEXTURE_3D)):
            GL.glActiveTexture(GL.GL_TEXTURE0 + unit); GL.glBindTexture(target, textures[unit])
            data = arrays.get(name)
            if data is None:
                data = np.zeros((1, 1) if unit == 2 else (1, 1, 1, 4), np.float32)
            if unit == 2:
                GL.glTexImage2D(target, 0, GL.GL_R32F, data.shape[1], data.shape[0], 0, GL.GL_RED, GL.GL_FLOAT, data)
            else:
                GL.glTexImage3D(target, 0, GL.GL_RGBA32F, data.shape[2], data.shape[1], data.shape[0],
                                0, GL.GL_RGBA, GL.GL_FLOAT, data)
            GL.glTexParameteri(target, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(target, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            for axis in (GL.GL_TEXTURE_WRAP_S, GL.GL_TEXTURE_WRAP_T, GL.GL_TEXTURE_WRAP_R):
                GL.glTexParameteri(target, axis, GL.GL_CLAMP_TO_EDGE)
        GL.glEnable(GL.GL_TEXTURE_CUBE_MAP_SEAMLESS)
        GL.glUseProgram(program)
        location = lambda name: GL.glGetUniformLocation(program, name)
        for unit, name in enumerate(('defaultCube', 'localCubes', 'distantHeight', 'distantSamples')):
            GL.glUniform1i(location(name), unit)
        GL.glUniform1ui(location('queryCount'), count); GL.glUniform1ui(location('wordCount'), params['word_count'])
        GL.glUniform1i(location('recordCount'), params['record_count'])
        for name, value in (('cameraPosition', params['camera_position']), ('ambientFill', params['ambient_fill']),
                             ('distantConstants', params['distant'])):
            GL.glUniform3f(location(name), *value)
        GL.glUniform4f(location('distantUV'), *params['distant_uv'])
        GL.glUniform1f(location('bleedReduction'), params['bleed_reduction'])
        GL.glUniform1f(location('intensity'), params['intensity'])
        GL.glDispatchCompute((count + 63) // 64, 1, 1)
        GL.glMemoryBarrier(GL.GL_SHADER_STORAGE_BARRIER_BIT | GL.GL_BUFFER_UPDATE_BARRIER_BIT)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER, buffers[5])
        raw = GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER, 0, output_bytes)
        output = np.frombuffer(raw, np.float32).reshape(count, 4, 4).copy()
        if not np.isfinite(output).all():
            raise ValueError('Replay produced nonfinite lighting; inspect the input geometry and resources')
        return {
            'specular': output[:, 0, :3], 'visibility': output[:, 0, 3],
            'diffuse': output[:, 1, :3], 'coarse_luminance': output[:, 1, 3],
            'grid_diffuse': output[:, 2, :3], 'grid_reflection': output[:, 2, 3],
            'default_coverage': output[:, 3, 0], 'diffuse_coverage': output[:, 3, 1],
            'grid_fallback_weight': output[:, 3, 2],
            'renderer': GL.glGetString(GL.GL_RENDERER).decode(),
        }
    finally:
        if buffers: GL.glDeleteBuffers(len(buffers), buffers)
        if textures: GL.glDeleteTextures(textures)
        if program: GL.glDeleteProgram(program)
        context.doneCurrent()
