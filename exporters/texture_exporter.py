"""
exporters/texture_exporter.py
Bundled texture export for RCRA Forge — WolvenKit-style workflow.

Handles:
  - Writing PNG or DDS files from decoded RGBA texture data
  - Embedding textures into GLB binary buffers
  - Writing textures/ subfolder for FBX exports
  - Supplying PBR material node data for GLB material definitions

PBR slot mapping (RCRA → Blender):
  albedo / color    → Base Color
  normal            → Normal Map
  ao_emission       → AO (R) + Emission (G)  [split channels]
  specular_ior      → Specular IOR Level
"""

import io
import os
import struct
import base64
from dataclasses import dataclass, field
from typing import Optional


# ── Texture format constants ───────────────────────────────────────────────────

# DXGI format codes (subset we need for DDS export)
DXGI_BC1  = 0x47
DXGI_BC3  = 0x4D
DXGI_BC5  = 0x53
DXGI_BC7  = 0x62
DXGI_BC7S = 0x63

# DDS magic and flags
DDS_MAGIC           = b'DDS '
DDSD_CAPS           = 0x1
DDSD_HEIGHT         = 0x2
DDSD_WIDTH          = 0x4
DDSD_PIXELFORMAT    = 0x1000
DDSD_LINEARSIZE     = 0x80000
DDSD_MIPMAPCOUNT    = 0x20000
DDPF_FOURCC         = 0x4
DDSCAPS_TEXTURE     = 0x1000
DDSCAPS_MIPMAP      = 0x400008
FOURCC_DX10         = b'DX10'


# ── Slot role → Blender PBR socket name ──────────────────────────────────────

ROLE_TO_BLENDER = {
    'base_color':         'baseColorTexture',
    'color_id':           'baseColorTexture',   # fallback base color
    'specular_color':     'specularColorTexture',
    'specular_ior':       'specularTexture',
    'normal':             'normalTexture',
    'mask':               'occlusionTexture',    # packed R=emission G=height B=AO
    'ambient_occlusion':  'occlusionTexture',    # dedicated AO (replaces mask)
}

# Roles we export textures for
EXPORT_ROLES = {
    'base_color', 'color_id',
    'specular_color', 'specular_ior',
    'normal', 'mask', 'ambient_occlusion',
    'emissive', 'effect_mask', 'noise',
    'fur_control',
    'retail_lava_color_a', 'retail_lava_color_b',
    'retail_lava_normal_a', 'retail_lava_normal_b',
    'retail_lava_noise',
    'retail_lava_mask_a', 'retail_lava_mask_b',
    'micro_variation',   # _sm — NPC dinosaur detail variation (Grunthors/Monks)
}


def _role_in_export_roles(role: str) -> bool:
    """Match exact role or indexed variant (e.g. 'base_color_1', 'normal_2')."""
    if role in EXPORT_ROLES:
        return True
    # Strip trailing _N index and check base role
    parts = role.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit() and parts[0] in EXPORT_ROLES:
        return True
    return False


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ExportedTexture:
    """Result of exporting one texture slot."""
    role:      str          # 'albedo', 'normal', etc.
    mat_name:  str          # material name stem
    tex_name:  str          # texture file stem (e.g. 'hero_ratchet_head_g')
    rgba:      bytes        # raw RGBA pixel data
    width:     int
    height:    int
    png_path:  Optional[str] = None   # set after writing PNG
    dds_path:  Optional[str] = None   # set after writing DDS
    png_bytes: Optional[bytes] = None  # set when embedding in GLB


# ── PNG writer (pure Python, no Pillow required) ──────────────────────────────

def _write_png(rgba: bytes, width: int, height: int) -> bytes:
    """Encode raw RGBA bytes as a PNG file, returned as bytes."""
    try:
        from PIL import Image
        img = Image.frombytes('RGBA', (width, height), rgba)
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=False)
        return buf.getvalue()
    except ImportError:
        pass

    # Fallback: pure-Python PNG writer (no compression for speed)
    import zlib

    def png_chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    # IHDR
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA

    # IDAT — scanlines with filter byte 0
    raw_rows = b''
    stride = width * 4
    for y in range(height):
        raw_rows += b'\x00' + rgba[y * stride:(y + 1) * stride]
    idat_data = zlib.compress(raw_rows, 1)

    return (
        b'\x89PNG\r\n\x1a\n'
        + png_chunk(b'IHDR', ihdr)
        + png_chunk(b'IDAT', idat_data)
        + png_chunk(b'IEND', b'')
    )


# ── DDS writer ────────────────────────────────────────────────────────────────

def _write_dds_from_rgba(rgba: bytes, width: int, height: int, dxgi_fmt: int = DXGI_BC7) -> bytes:
    """
    Write a DDS file from raw RGBA data.
    Re-encodes to the specified BCn format if imagecodecs is available,
    otherwise writes an uncompressed DDS (BGRA8).
    """
    try:
        import imagecodecs
        import numpy as np

        arr = np.frombuffer(rgba, dtype=np.uint8).reshape((height, width, 4))
        # imagecodecs BCn encoding
        if dxgi_fmt in (DXGI_BC7, DXGI_BC7S):
            compressed = imagecodecs.bc7_encode(arr)
            fourcc_code = DXGI_BC7
        elif dxgi_fmt == DXGI_BC1:
            compressed = imagecodecs.bc1_encode(arr)
            fourcc_code = DXGI_BC1
        elif dxgi_fmt == DXGI_BC3:
            compressed = imagecodecs.bc3_encode(arr)
            fourcc_code = DXGI_BC3
        else:
            compressed = imagecodecs.bc7_encode(arr)
            fourcc_code = DXGI_BC7

        return _build_dds_dx10(compressed, width, height, fourcc_code)
    except Exception:
        # Fallback: uncompressed BGRA8 DDS
        return _build_dds_uncompressed(rgba, width, height)


def _build_dds_dx10(pixel_data: bytes, width: int, height: int, dxgi_fmt: int) -> bytes:
    """Build a DX10-extended DDS file."""
    buf = io.BytesIO()

    # DDS_PIXELFORMAT (32 bytes)
    pf = struct.pack('<IIIIIII',
        32,             # size
        DDPF_FOURCC,    # flags
        *struct.unpack('<I', FOURCC_DX10),  # FourCC = 'DX10'
        0, 0, 0, 0      # RGB bit counts + masks
    )

    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    # DDS_HEADER (124 bytes)
    header = struct.pack('<IIIIIIIII',
        124,            # size
        flags,
        height,
        width,
        len(pixel_data),  # pitchOrLinearSize
        0,              # depth
        1,              # mipMapCount
        0, 0            # reserved[0:2]
    )
    header += b'\x00' * (4 * 9)   # reserved[2:11]
    header += pf
    header += struct.pack('<II', DDSCAPS_TEXTURE, 0)   # caps, caps2
    header += b'\x00' * 8         # caps3, caps4, reserved2

    # DX10 header (20 bytes)
    dx10 = struct.pack('<IIIII',
        dxgi_fmt,   # dxgiFormat
        3,          # resourceDimension = D3D10_RESOURCE_DIMENSION_TEXTURE2D
        0,          # miscFlag
        1,          # arraySize
        0,          # miscFlags2
    )

    buf.write(DDS_MAGIC)
    buf.write(header)
    buf.write(dx10)
    buf.write(pixel_data)
    return buf.getvalue()


def _build_dds_uncompressed(rgba: bytes, width: int, height: int) -> bytes:
    """Fallback: uncompressed BGRA8 DDS (no imagecodecs needed)."""
    import numpy as np
    arr = np.frombuffer(rgba, dtype=np.uint8).reshape((height, width, 4))
    bgra = arr[:, :, [2, 1, 0, 3]].tobytes()

    pf = struct.pack('<IIIIIII',
        32, 0x41, 0,   # size, flags=DDPF_RGB|DDPF_ALPHAPIXELS, fourCC=0
        32,            # RGB bit count
        0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000  # BGRA masks
    )
    pitch = width * 4
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | 0x8  # DDSD_PITCH
    header = struct.pack('<IIIIIIIII', 124, flags, height, width, pitch, 0, 1, 0, 0)
    header += b'\x00' * 36 + pf
    header += struct.pack('<II', DDSCAPS_TEXTURE, 0) + b'\x00' * 8

    buf = io.BytesIO()
    buf.write(DDS_MAGIC)
    buf.write(header)
    buf.write(bgra)
    return buf.getvalue()


# ── Main exporter class ───────────────────────────────────────────────────────

class TextureExporter:
    """
    Exports textures from decoded material data alongside a model export.

    tex_data format (from AssetLoader.materials_ready signal, extended):
      {mat_idx: {role: (rgba_bytes, width, height, tex_name)}}

    Usage:
        exporter = TextureExporter(tex_data, mat_names, output_dir, model_stem)
        results = exporter.export(fmt='png')  # 'png', 'dds', or 'both'
    """

    def __init__(self,
                 tex_data: dict,
                 mat_names: dict,
                 output_dir: str,
                 model_stem: str):
        """
        tex_data:   {mat_idx: {role: (rgba, w, h, tex_name)}}
        mat_names:  {mat_idx: str}  — material name stem per index
        output_dir: directory to write textures into
        model_stem: base name of the model (for naming textures/ subfolder)
        """
        self.tex_data   = tex_data
        self.mat_names  = mat_names
        self.output_dir = output_dir
        self.model_stem = model_stem

    def export(self, fmt: str = 'png') -> dict:
        """
        Write texture files to output_dir/textures/.
        fmt: 'png', 'dds', or 'both'
        Returns: {mat_idx: {role: ExportedTexture}}
        """
        tex_dir = os.path.join(self.output_dir, 'textures')
        os.makedirs(tex_dir, exist_ok=True)

        results: dict = {}
        written_names: set = set()   # deduplicate by filename stem

        for mat_idx, roles in self.tex_data.items():
            results[mat_idx] = {}
            mat_name = self.mat_names.get(mat_idx, f'mat{mat_idx}')

            for role, (rgba, w, h, tex_name) in roles.items():
                if not _role_in_export_roles(role):
                    continue

                et = ExportedTexture(
                    role=role, mat_name=mat_name,
                    tex_name=tex_name, rgba=rgba, width=w, height=h
                )

                if fmt in ('png', 'both'):
                    png_path = os.path.join(tex_dir, tex_name + '.png')
                    if tex_name not in written_names:
                        png_data = _write_png(rgba, w, h)
                        with open(png_path, 'wb') as f:
                            f.write(png_data)
                        et.png_path  = png_path
                        et.png_bytes = png_data
                        print(f"[texexport] wrote {tex_name}.png ({w}×{h})")
                        written_names.add(tex_name)
                    else:
                        et.png_path = png_path   # still reference the path

                if fmt in ('dds', 'both'):
                    dds_path = os.path.join(tex_dir, tex_name + '.dds')
                    if tex_name not in written_names:
                        dds_data = _write_dds_from_rgba(rgba, w, h)
                        with open(dds_path, 'wb') as f:
                            f.write(dds_data)
                        et.dds_path = dds_path
                        print(f"[texexport] wrote {tex_name}.dds ({w}×{h})")
                        written_names.add(tex_name)

                results[mat_idx][role] = et

        return results

    def for_glb_embed(self) -> dict:
        """
        Encode all textures as PNG bytes ready for embedding in GLB.
        Returns: {mat_idx: {role: ExportedTexture with png_bytes set}}
        """
        results: dict = {}
        for mat_idx, roles in self.tex_data.items():
            results[mat_idx] = {}
            mat_name = self.mat_names.get(mat_idx, f'mat{mat_idx}')
            for role, (rgba, w, h, tex_name) in roles.items():
                if not _role_in_export_roles(role):
                    continue
                et = ExportedTexture(
                    role=role, mat_name=mat_name,
                    tex_name=tex_name, rgba=rgba, width=w, height=h,
                    png_bytes=_write_png(rgba, w, h)
                )
                results[mat_idx][role] = et
        return results


# ── GLB material builder ──────────────────────────────────────────────────────

def build_glb_materials(exported: dict, gltf: dict, buffer_data: bytearray) -> list:
    """
    Add textures + PBR materials to a glTF dict (in-place) and append
    image data to buffer_data.

    exported: {mat_idx: {role: ExportedTexture}}  — from for_glb_embed()
    gltf:     the glTF JSON dict being built
    buffer_data: the binary buffer bytearray

    Returns: list of glTF material indices (one per mat_idx, in sorted order)
    """
    if 'images' not in gltf:     gltf['images'] = []
    if 'textures' not in gltf:   gltf['textures'] = []
    if 'materials' not in gltf:  gltf['materials'] = []
    if 'bufferViews' not in gltf: gltf['bufferViews'] = []

    mat_idx_to_gltf_mat = {}

    for mat_idx in sorted(exported.keys()):
        roles = exported[mat_idx]
        pbr = {}
        extras = {}

        for role, et in roles.items():
            if not et.png_bytes:
                continue

            # Append image bytes to buffer
            offset = len(buffer_data)
            # Align to 4 bytes
            pad = (4 - offset % 4) % 4
            buffer_data += b'\x00' * pad
            offset += pad

            buffer_data += et.png_bytes
            length = len(et.png_bytes)

            bv_idx = len(gltf['bufferViews'])
            gltf['bufferViews'].append({
                'buffer': 0,
                'byteOffset': offset,
                'byteLength': length,
                'name': et.tex_name,
            })

            img_idx = len(gltf['images'])
            gltf['images'].append({
                'bufferView': bv_idx,
                'mimeType': 'image/png',
                'name': et.tex_name,
            })

            tex_idx = len(gltf['textures'])
            gltf['textures'].append({'source': img_idx, 'name': et.tex_name})

            # Map role → glTF PBR property
            if role in ('base_color', 'color_id'):
                pbr['baseColorTexture'] = {'index': tex_idx}
            elif role == 'normal':
                pbr['normalTexture'] = {'index': tex_idx}
            elif role in ('mask', 'ambient_occlusion'):
                pbr['occlusionTexture'] = {'index': tex_idx}
                if role == 'mask':
                    extras['mask_texture'] = tex_idx  # R=emission G=height B=AO
            elif role == 'specular_color':
                extras['specular_color_texture'] = tex_idx
            elif role == 'specular_ior':
                extras['specular_ior_texture'] = tex_idx

        mat_name = roles[next(iter(roles))].mat_name if roles else f'mat{mat_idx}'
        gltf_mat = {
            'name': mat_name,
            'pbrMetallicRoughness': pbr,
        }
        if extras:
            gltf_mat['extras'] = extras

        gltf_mat_idx = len(gltf['materials'])
        gltf['materials'].append(gltf_mat)
        mat_idx_to_gltf_mat[mat_idx] = gltf_mat_idx

    return mat_idx_to_gltf_mat


# ── FBX texture patcher ───────────────────────────────────────────────────────

def get_fbx_texture_paths(exported: dict, rel_prefix: str = 'textures/') -> dict:
    """
    Returns {mat_idx: {role: relative_path}} for patching into FBX material nodes.
    rel_prefix: relative path prefix from the .fbx file to the textures/ folder.
    """
    result = {}
    for mat_idx, roles in exported.items():
        result[mat_idx] = {}
        for role, et in roles.items():
            if et.png_path:
                fname = os.path.basename(et.png_path)
                result[mat_idx][role] = rel_prefix + fname
            elif et.dds_path:
                fname = os.path.basename(et.dds_path)
                result[mat_idx][role] = rel_prefix + fname
    return result
