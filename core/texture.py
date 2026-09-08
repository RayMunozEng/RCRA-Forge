"""
core/texture.py
Ratchet & Clank: Rift Apart PC — texture asset parser.

Written from ALERT dat1lib/types/sections/texture/header.py.

Key facts:
  - Asset is a DAT1 container with unk1 = 0x5C4580B9 ('texture')
  - Single section: TAG 0x4EDE3593 — TextureHeaderSection
  - Section size is 44 bytes for RCRA/MSMR
  - The pixel data itself is NOT in the DAT1 section —
    it is prepended to the asset via the 36-byte AssetEntry.header blob
    (from the TOC's AssetHeadersSection, tag 0x654BDED9)
    OR stored in a separate HD texture archive file

TextureHeaderSection layout (44 bytes for RCRA):
  0x00  4B  sd_len       — byte length of SD (standard def) pixel data
  0x04  4B  hd_len       — byte length of HD pixel data
  0x08  2B  hd_width
  0x0A  2B  hd_height
  0x0C  2B  sd_width
  0x0E  2B  sd_height
  0x10  2B  array_size
  0x12  1B  stex_format  — Insomniac texture format enum
  0x13  1B  planes
  0x14  2B  fmt          — DXGI format enum
  0x16  8B  unk          — uint64
  0x1E  1B  sd_mipmaps
  0x1F  1B  unk2
  0x20  1B  hd_mipmaps
  0x21  1B  unk3
  0x22  2B  unk4         — remaining bytes

fmt field maps to DXGI_FORMAT:
  71 (0x47)  BC1_UNORM
  74 (0x4A)  BC2_UNORM
  77 (0x4D)  BC3_UNORM
  80 (0x50)  BC4_UNORM
  83 (0x53)  BC5_UNORM
  98 (0x62)  BC7_UNORM
  28 (0x1C)  R8G8B8A8_UNORM
  61 (0x3D)  R8_UNORM

Named according to SpiderTex by monax3:
https://github.com/monax3/SpiderTex/blob/main/src/texture_file.rs
"""

import struct
from dataclasses import dataclass
from typing import Optional

from core.archive import DAT1

# ── DAT1 section tag ──────────────────────────────────────────────────────────
TAG_TEXTURE_HEADER = 0x4EDE3593

# ── DXGI format → human-readable name ────────────────────────────────────────
DXGI_FORMAT_NAMES = {
    0x47: 'BC1_UNORM',
    0x48: 'BC1_UNORM_SRGB',
    0x4A: 'BC2_UNORM',
    0x4B: 'BC2_UNORM_SRGB',
    0x4D: 'BC3_UNORM',
    0x4E: 'BC3_UNORM_SRGB',
    0x50: 'BC4_UNORM',
    0x51: 'BC4_SNORM',
    0x53: 'BC5_UNORM',
    0x54: 'BC5_SNORM',
    0x62: 'BC7_UNORM',
    0x63: 'BC7_UNORM_SRGB',
    0x1C: 'R8G8B8A8_UNORM',
    0x3D: 'R8_UNORM',
    0x36: 'B8G8R8A8_UNORM',
    0x41: 'A8_UNORM',
    0x4F: 'BC4_TYPELESS',
    0x5B: 'B8G8R8A8_UNORM_SRGB',
    0x5F: 'BC6H_UF16',
    0x60: 'BC6H_SF16',
}

# DXGI formats that use DXT FourCC in DDS headers
DXGI_DXT1 = 0x47
DXGI_DXT1S = 0x48
DXGI_DXT3 = 0x4A
DXGI_DXT3S = 0x4B
DXGI_DXT5 = 0x4D
DXGI_DXT5S = 0x4E
DXGI_ATI1 = 0x50
DXGI_ATI1S = 0x51
DXGI_ATI2 = 0x53
DXGI_ATI2S = 0x54
DXGI_BC6U = 0x5F
DXGI_BC6S = 0x60
DXGI_BC7  = 0x62
DXGI_BC7S = 0x63


def _hdr_rgb_to_rgba8(rgb) -> bytes:
    """Convert decoded BC6H RGB values into a stable display/preview range."""
    import numpy as np

    values = np.asarray(rgb, dtype=np.float32)
    values = np.nan_to_num(values, nan=0.0, posinf=65504.0, neginf=0.0)
    values = np.maximum(values, 0.0)
    positive = values[values > 0.0]
    scale = float(np.percentile(positive, 99.0)) if positive.size else 1.0
    scale = max(scale, 1.0)
    mapped = np.log1p(values) / np.log1p(scale)
    mapped = np.clip(mapped, 0.0, 1.0)
    rgba = np.empty((*values.shape[:2], 4), dtype=np.uint8)
    rgba[:, :, :3] = np.rint(mapped[:, :, :3] * 255.0).astype(np.uint8)
    rgba[:, :, 3] = 255
    return rgba.tobytes()


@dataclass
class TextureAsset:
    # SD = standard definition (always available, at offset 0x44 in DAT1)
    sd_len:    int
    sd_width:  int
    sd_height: int
    sd_mips:   int
    # HD = high definition (separate TOC entry, same asset ID, larger archive)
    hd_len:    int
    hd_width:  int
    hd_height: int
    hd_mips:   int
    # Format
    fmt:       int         # DXGI_FORMAT value
    array_size: int
    planes:    int
    # Pixel data
    pixel_data:    bytes = b''   # SD pixel data
    hd_pixel_data: bytes = b''   # HD pixel data (injected externally)

    @property
    def width(self) -> int:
        return self.hd_width if self.hd_pixel_data and self.hd_width > 0 else self.sd_width

    @property
    def height(self) -> int:
        return self.hd_height if self.hd_pixel_data and self.hd_height > 0 else self.sd_height

    @property
    def mips(self) -> int:
        return self.hd_mips if self.hd_pixel_data else self.sd_mips

    @property
    def format_name(self) -> str:
        return DXGI_FORMAT_NAMES.get(self.fmt, f'DXGI_{self.fmt:#04x}')

    @property
    def is_block_compressed(self) -> bool:
        return self.fmt in (
            DXGI_DXT1, DXGI_DXT1S, DXGI_DXT3, DXGI_DXT3S,
            DXGI_DXT5, DXGI_DXT5S, DXGI_ATI1, DXGI_ATI1S,
            DXGI_ATI2, DXGI_ATI2S, DXGI_BC6U, DXGI_BC6S,
            DXGI_BC7, DXGI_BC7S,
        )

    def decode_to_rgba(self) -> Optional[bytes]:
        """
        Decode compressed pixel data to raw RGBA8 bytes using imagecodecs.
        Prefers HD pixel data if available, falls back to SD.
        Returns flat bytes (width × height × 4) or None on failure.
        """
        # Prefer HD data if available
        if self.hd_pixel_data and self.hd_width > 0 and self.hd_height > 0:
            data = self.hd_pixel_data
            w, h = self.hd_width, self.hd_height
        elif self.pixel_data and self.sd_width > 0 and self.sd_height > 0:
            data = self.pixel_data
            w, h = self.sd_width, self.sd_height
        else:
            return None
        try:
            import imagecodecs
            import numpy as np

            # Map DXGI format → BCN format number
            BCN_MAP = {
                0x47: 1,   # BC1_UNORM  (DXT1)
                0x48: 1,   # BC1_UNORM_SRGB
                0x4A: 2,   # BC2_UNORM  (DXT3)
                0x4B: 2,   # BC2_UNORM_SRGB
                0x4D: 3,   # BC3_UNORM  (DXT5)
                0x4E: 3,   # BC3_UNORM_SRGB
                0x50: 4,   # BC4_UNORM
                0x51: 4,   # BC4_SNORM
                0x53: 5,   # BC5_UNORM
                0x54: 5,   # BC5_SNORM
                0x5F: 6,   # BC6H_UF16 (HDR RGB)
                0x60: 6,   # BC6H_SF16 (HDR RGB)
                0x62: 7,   # BC7_UNORM
                0x63: 7,   # BC7_UNORM_SRGB
            }
            bcn = BCN_MAP.get(self.fmt)
            if bcn is None:
                # Uncompressed R8G8B8A8 (both linear and sRGB variants)
                if self.fmt in (0x1C, 0x1D):
                    return bytes(data[:w * h * 4])
                return None

            # BC4=1 channel, BC5=2 channels, others=4 channels
            channels = {1: 4, 2: 4, 3: 4, 6: 3, 7: 4}.get(bcn, None)
            if bcn == 4:
                channels = 1
            elif bcn == 5:
                channels = 2

            # Bytes per BCn block (all BCn formats use 4×4 pixel blocks)
            bytes_per_block = 8 if bcn in (1, 4) else 16  # BC1/BC4=8, others=16
            blocks_w = max(1, (w + 3) // 4)
            blocks_h = max(1, (h + 3) // 4)
            mip0_size = blocks_w * blocks_h * bytes_per_block

            # Truncate to first mip level only — imagecodecs doesn't handle
            # mip chains and returns zeros if extra bytes are present.
            mip0_data = data[:mip0_size]

            shape = (h, w, channels) if channels > 1 else (h, w)
            arr = imagecodecs.bcn_decode(mip0_data, format=bcn, shape=shape)
            if bcn == 6:
                return _hdr_rgb_to_rgba8(arr)
            arr = arr.astype(np.uint8)

            # Normalize to RGBA
            if arr.ndim == 2:  # BC4 single channel → replicate to RGB
                rgba = np.zeros((h, w, 4), dtype=np.uint8)
                rgba[:, :, 0] = arr
                rgba[:, :, 1] = arr
                rgba[:, :, 2] = arr
                rgba[:, :, 3] = 255
                return rgba.tobytes()
            elif arr.shape[2] == 2:  # BC5 RG → pad BA
                rgba = np.zeros((h, w, 4), dtype=np.uint8)
                rgba[:, :, 0] = arr[:, :, 0]
                rgba[:, :, 1] = arr[:, :, 1]
                rgba[:, :, 3] = 255
                return rgba.tobytes()
            else:  # BC1/BC2/BC3/BC7 already RGBA
                return arr.tobytes()
        except Exception as ex:
            print(f"[texture] decode_to_rgba failed fmt={self.fmt:#x}: {ex}")
            return None

    def decode_to_rgb_float(self) -> Optional[bytes]:
        """Decode BC6H mip 0 to linear RGB32F for material rendering.

        ``decode_to_rgba`` intentionally tone-maps BC6H for ordinary image
        previews.  Feeding that preview back into a material destroys the HDR
        values used by the shipped lava graph, so the GPU path requests this
        lossless float representation instead.
        """
        if self.fmt not in (DXGI_BC6U, DXGI_BC6S):
            return None
        if self.hd_pixel_data and self.hd_width > 0 and self.hd_height > 0:
            data = self.hd_pixel_data
            width, height = self.hd_width, self.hd_height
        elif self.pixel_data and self.sd_width > 0 and self.sd_height > 0:
            data = self.pixel_data
            width, height = self.sd_width, self.sd_height
        else:
            return None
        try:
            import imagecodecs
            import numpy as np

            blocks_w = max(1, (width + 3) // 4)
            blocks_h = max(1, (height + 3) // 4)
            mip0 = data[:blocks_w * blocks_h * 16]
            decoded = imagecodecs.bcn_decode(
                mip0, format=6, shape=(height, width, 3),
            )
            values = np.asarray(decoded, dtype=np.float32)
            values = np.nan_to_num(
                values, nan=0.0,
                posinf=65504.0,
                neginf=-65504.0 if self.fmt == DXGI_BC6S else 0.0,
            )
            if self.fmt == DXGI_BC6U:
                values = np.maximum(values, 0.0)
            return values.astype(np.float32, copy=False).tobytes()
        except Exception as ex:
            print(f"[texture] decode_to_rgb_float failed fmt={self.fmt:#x}: {ex}")
            return None

    def compressed_mip0(self) -> Optional[bytes]:
        """Return the original block-compressed top mip without transcoding.

        This is the authoritative render payload for GPU formats such as
        BC6H.  Keeping the blocks intact lets the graphics driver perform the
        same format decode as the game instead of routing HDR values through
        a CPU image-preview decoder.
        """
        mip_chain = self.compressed_mips()
        if mip_chain:
            return mip_chain[0][2]
        if not self.is_block_compressed:
            return None
        if self.hd_pixel_data and self.hd_width > 0 and self.hd_height > 0:
            data, width, height = (
                self.hd_pixel_data, self.hd_width, self.hd_height,
            )
        elif self.pixel_data and self.sd_width > 0 and self.sd_height > 0:
            data, width, height = self.pixel_data, self.sd_width, self.sd_height
        else:
            return None
        eight_byte_formats = (DXGI_DXT1, DXGI_DXT1S, DXGI_ATI1, DXGI_ATI1S)
        bytes_per_block = 8 if self.fmt in eight_byte_formats else 16
        byte_count = (
            max(1, (width + 3) // 4)
            * max(1, (height + 3) // 4)
            * bytes_per_block
        )
        return bytes(data[:byte_count]) if len(data) >= byte_count else None

    def compressed_mips(self) -> list[tuple[int, int, bytes]]:
        """Return the authoritative block-compressed mip chain.

        Each item is ``(width, height, blocks)`` in the on-disk top-to-bottom
        order used by DDS and by the game's texture upload path.  Returning an
        empty list rather than a partial chain prevents the viewport from
        silently mixing authored and driver-generated levels.
        """
        if not self.is_block_compressed or self.array_size > 1:
            return []
        eight_byte_formats = (DXGI_DXT1, DXGI_DXT1S, DXGI_ATI1, DXGI_ATI1S)
        bytes_per_block = 8 if self.fmt in eight_byte_formats else 16

        def decode_payload(data: bytes, width: int, height: int,
                           mip_count: int) -> list[tuple[int, int, bytes]]:
            levels: list[tuple[int, int, bytes]] = []
            offset = 0
            for _level in range(max(1, mip_count)):
                blocks_w = max(1, (width + 3) // 4)
                blocks_h = max(1, (height + 3) // 4)
                byte_count = blocks_w * blocks_h * bytes_per_block
                end = offset + byte_count
                if end > len(data):
                    return []
                levels.append((width, height, bytes(data[offset:end])))
                offset = end
                width = max(1, width // 2)
                height = max(1, height // 2)
            return levels

        result: list[tuple[int, int, bytes]] = []
        if self.hd_pixel_data and self.hd_width > 0 and self.hd_height > 0:
            result = decode_payload(
                self.hd_pixel_data, self.hd_width, self.hd_height,
                self.hd_mips,
            )
            if not result:
                return []
        if self.pixel_data and self.sd_width > 0 and self.sd_height > 0:
            sd_levels = decode_payload(
                self.pixel_data, self.sd_width, self.sd_height, self.sd_mips,
            )
            if not sd_levels:
                return []
            if not result:
                result = sd_levels
            elif (
                sd_levels[0][0] < result[-1][0]
                and sd_levels[0][1] < result[-1][1]
            ):
                # RCRA streams top HD levels separately and stores the tail in
                # the SD payload. They are one sampler-visible mip chain.
                result.extend(sd_levels)
        return result

    @property
    def is_packed_probe_atlas(self) -> bool:
        """Identify the shipped BC6U probe atlas, not a 2D lat-long texture.

        TextureManager's local probe array is 256x256 with six mips. Its
        CS_CopyEnvProbe shader copies uint4 BC6 blocks from a 1024x512 atlas.
        See docs/ENVIRONMENT_PROBES.md for the shader and allocation evidence.
        """
        return (
            self.fmt == DXGI_BC6U and self.planes == 4 and self.array_size == 1
            and self.width == 1024 and self.height == 512 and self.mips == 1
        )

    def compressed_cube_mips(self) -> list[list[tuple[int, int, bytes]]]:
        """Return face-major BC mip chains for a cooked cube texture.

        RCRA marks cube resources with ``planes == 4`` and stores six complete
        face-major mip chains even though ``array_size`` remains one. This is
        the layout used by the captured 1024x1024 BC6 environment probe: its
        payload is exactly ``6 * sum(mip_byte_sizes)``. Local baked probes
        instead pack all faces/mips into one 1024x512 BC6U atlas; their header's
        mip count describes the atlas, not the destination cube.
        """
        if not self.is_block_compressed or self.planes != 4:
            return []
        if self.hd_pixel_data and self.hd_width > 0 and self.hd_height > 0:
            data = self.hd_pixel_data
            width, height = self.hd_width, self.hd_height
            mip_count = max(1, self.hd_mips)
        elif self.pixel_data and self.sd_width > 0 and self.sd_height > 0:
            data = self.pixel_data
            width, height = self.sd_width, self.sd_height
            mip_count = max(1, self.sd_mips)
        else:
            return []
        if self.is_packed_probe_atlas:
            if len(data) != 1024 * 512:
                return []
            # CS_CopyEnvProbe uses a 256x128 uint4 view of the BC6 blocks.
            # For each mip, faces 0..3 occupy the upper row and 4..5 the
            # lower row. Remaining space holds the next mip recursively.
            # Preserve the block bits and orientation; there is no resampling.
            result = []
            for face in range(6):
                levels = []
                for mip in range(6):
                    block_side = 64 >> mip
                    source_x = 256 - (4 - (face & 3)) * block_side
                    source_y = 128 - (2 if face < 4 else 1) * block_side
                    blocks = b''.join(
                        data[((source_y + row) * 256 + source_x) * 16:
                             ((source_y + row) * 256 + source_x + block_side) * 16]
                        for row in range(block_side)
                    )
                    side = block_side * 4
                    levels.append((side, side, blocks))
                result.append(levels)
            return result
        eight_byte_formats = (DXGI_DXT1, DXGI_DXT1S, DXGI_ATI1, DXGI_ATI1S)
        bytes_per_block = 8 if self.fmt in eight_byte_formats else 16
        face_stride = 0
        dimensions = []
        mip_width, mip_height = width, height
        for _level in range(mip_count):
            byte_count = (
                max(1, (mip_width + 3) // 4)
                * max(1, (mip_height + 3) // 4)
                * bytes_per_block
            )
            dimensions.append((mip_width, mip_height, byte_count))
            face_stride += byte_count
            mip_width = max(1, mip_width // 2)
            mip_height = max(1, mip_height // 2)
        if len(data) != face_stride * 6:
            return []
        result = []
        for face in range(6):
            offset = face * face_stride
            levels = []
            for mip_width, mip_height, byte_count in dimensions:
                levels.append((
                    mip_width, mip_height,
                    bytes(data[offset:offset + byte_count]),
                ))
                offset += byte_count
            result.append(levels)
        return result

    def decoded_cube_mips_rgb_half(
        self,
    ) -> list[list[tuple[int, int, bytes]]]:
        """Decode a BC6 cube to face-major linear RGB16F mip chains.

        This is the portable upload representation for OpenGL bindings that
        cannot marshal compressed 2D-array data.  It preserves the BC6
        decoder's linear HDR samples; unlike ``decode_to_rgba``, it performs
        no preview tone mapping or 8-bit conversion.
        """
        if self.fmt not in (DXGI_BC6U, DXGI_BC6S):
            return []
        cube_mips = self.compressed_cube_mips()
        if not cube_mips:
            return []
        try:
            import imagecodecs
            import numpy as np

            result = []
            for levels in cube_mips:
                decoded_levels = []
                for width, height, blocks in levels:
                    decoded = imagecodecs.bcn_decode(
                        blocks, format=6, shape=(height, width, 3),
                    )
                    values = np.asarray(decoded, dtype=np.float32)
                    values = np.nan_to_num(
                        values, nan=0.0, posinf=65504.0,
                        neginf=-65504.0 if self.fmt == DXGI_BC6S else 0.0,
                    )
                    if self.fmt == DXGI_BC6U:
                        values = np.maximum(values, 0.0)
                    decoded_levels.append((
                        width, height,
                        values.astype(np.float16).tobytes(),
                    ))
                result.append(decoded_levels)
            return result
        except Exception as ex:
            print(f"[texture] cube BC6 decode failed fmt={self.fmt:#x}: {ex}")
            return []

    def to_png_bytes(self) -> Optional[bytes]:
        """Decode the active SD/HD texture payload to PNG via Pillow."""
        rgba = self.decode_to_rgba()
        if rgba is None:
            return None
        try:
            from PIL import Image
            import io
            img = Image.frombytes('RGBA', (self.width, self.height), rgba)
            out = io.BytesIO()
            img.save(out, format='PNG')
            return out.getvalue()
        except Exception:
            return None

    def to_dds_bytes(self) -> bytes:
        """Wrap the active texture payload in a standard DDS container."""
        return _build_dds(self)


# ── Parser ────────────────────────────────────────────────────────────────────

class TextureParser:
    """
    Parse a raw texture asset blob into a TextureAsset.

    The asset blob is a DAT1 container.  For RCRA the pixel data is stored
    separately — it arrives prepended in the 36-byte header blob from the TOC
    AssetHeadersSection, or via a separate SD/HD archive read.

    Usage:
        raw = toc.extract_asset(entry)   # already includes header bytes
        tex = TextureParser(raw).parse()
    """

    def __init__(self, data: bytes):
        self.data = data
        self.dat1 = DAT1(data)

    def parse(self) -> TextureAsset:
        sec = self.dat1.get_section(TAG_TEXTURE_HEADER)
        if not sec or len(sec) < 34:
            raise ValueError(f"No valid texture header section found (got {len(sec) if sec else 0} bytes)")

        sd_len, hd_len           = struct.unpack_from('<II', sec, 0)
        hd_w, hd_h               = struct.unpack_from('<HH', sec, 8)
        sd_w, sd_h               = struct.unpack_from('<HH', sec, 12)
        array_size, stex_fmt, pl = struct.unpack_from('<HBB', sec, 16)
        fmt, unk                 = struct.unpack_from('<HQ', sec, 20)
        sd_mips, unk2, hd_mips, unk3 = struct.unpack_from('<BBBB', sec, 30)

        # SD blocks follow the complete DAT1 metadata, but extracted RCRA
        # textures may have a 36-byte TOC header prepended.  A fixed absolute
        # offset therefore lands inside the string pool/header for real game
        # assets.  Resolve the DAT1 base and the actual end of its sections.
        dat1_start = self.data.find(b'1TAD', 0, min(len(self.data), 256))
        pixel_offset = 0
        if dat1_start >= 0 and dat1_start + 16 <= len(self.data):
            section_count = struct.unpack_from('<H', self.data, dat1_start + 12)[0]
            directory_end = dat1_start + 16 + section_count * 12
            pixel_offset = directory_end
            for index in range(section_count):
                record = dat1_start + 16 + index * 12
                if record + 12 > len(self.data):
                    break
                _, section_offset, section_size = struct.unpack_from(
                    '<III', self.data, record,
                )
                pixel_offset = max(
                    pixel_offset, dat1_start + section_offset + section_size,
                )

        pixel_data = b''
        if sd_len > 0 and len(self.data) > pixel_offset:
            pixel_data = bytes(self.data[pixel_offset:pixel_offset + sd_len])

        return TextureAsset(
            sd_len     = sd_len,
            sd_width   = sd_w,
            sd_height  = sd_h,
            sd_mips    = max(1, sd_mips),
            hd_len     = hd_len,
            hd_width   = hd_w,
            hd_height  = hd_h,
            hd_mips    = max(1, hd_mips),
            fmt        = fmt,
            array_size = array_size,
            planes     = pl,
            pixel_data = pixel_data,
        )


# ── DDS container builder ─────────────────────────────────────────────────────

DDS_MAGIC       = b'DDS '
DDS_HDR_SIZE    = 124
DDSD_CAPS       = 0x00000001
DDSD_HEIGHT     = 0x00000002
DDSD_WIDTH      = 0x00000004
DDSD_LINEARSIZE = 0x00080000
DDSD_PIXFMT     = 0x00001000
DDSD_MIPMAP     = 0x00020000
DDSCAPS_TEXTURE = 0x00001000
DDSCAPS_MIPMAP  = 0x00400000
DDSCAPS_COMPLEX = 0x00000008
DDPF_FOURCC     = 0x00000004

# DDS FourCC → DXGI format
_FOURCC_MAP = {
    DXGI_DXT1: b'DXT1',
    DXGI_DXT1S: b'DX10',
    DXGI_DXT3: b'DXT3',
    DXGI_DXT3S: b'DX10',
    DXGI_DXT5: b'DXT5',
    DXGI_DXT5S: b'DX10',
    DXGI_ATI1: b'ATI1',
    DXGI_ATI1S: b'DX10',
    DXGI_ATI2: b'ATI2',
    DXGI_ATI2S: b'DX10',
    DXGI_BC6U: b'DX10',
    DXGI_BC6S: b'DX10',
    DXGI_BC7:  b'DX10',
    DXGI_BC7S: b'DX10',
}

# DXGI format resource dimension constant
D3D10_RESOURCE_DIMENSION_TEXTURE2D = 3


def _build_dds(tex: TextureAsset) -> bytes:
    import io
    buf = io.BytesIO()

    if tex.hd_pixel_data and tex.hd_width > 0 and tex.hd_height > 0:
        payload = tex.hd_pixel_data
        width = tex.hd_width
        height = tex.hd_height
        mip_count = max(1, tex.hd_mips)
    else:
        payload = tex.pixel_data
        width = tex.sd_width
        height = tex.sd_height
        mip_count = max(1, tex.sd_mips)
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXFMT | DDSD_LINEARSIZE
    if mip_count > 1:
        flags |= DDSD_MIPMAP

    caps = DDSCAPS_TEXTURE
    if mip_count > 1:
        caps |= DDSCAPS_MIPMAP | DDSCAPS_COMPLEX

    fourcc = _FOURCC_MAP.get(tex.fmt, b'DX10')
    block_bytes = 8 if tex.fmt in (DXGI_DXT1, DXGI_DXT1S, DXGI_ATI1, DXGI_ATI1S) else 16
    pitch = max(1, (width + 3) // 4) * block_bytes

    # DDS header
    buf.write(DDS_MAGIC)
    buf.write(struct.pack('<I', DDS_HDR_SIZE))
    buf.write(struct.pack('<I', flags))
    buf.write(struct.pack('<I', max(1, height)))
    buf.write(struct.pack('<I', max(1, width)))
    buf.write(struct.pack('<I', pitch))
    buf.write(struct.pack('<I', 1))              # depth
    buf.write(struct.pack('<I', mip_count))
    buf.write(b'\x00' * 44)                      # reserved[11]

    # DDS_PIXELFORMAT (32 bytes)
    buf.write(struct.pack('<I', 32))             # size
    buf.write(struct.pack('<I', DDPF_FOURCC))
    buf.write(fourcc)
    buf.write(b'\x00' * 20)

    buf.write(struct.pack('<I', caps))
    buf.write(b'\x00' * 16)                      # caps2-4 + reserved

    # DX10 extension header (needed for BC7 and others without legacy FourCC)
    if fourcc == b'DX10':
        buf.write(struct.pack('<I', tex.fmt))
        buf.write(struct.pack('<I', D3D10_RESOURCE_DIMENSION_TEXTURE2D))
        buf.write(struct.pack('<I', 0))           # miscFlag
        buf.write(struct.pack('<I', max(1, tex.array_size)))
        buf.write(struct.pack('<I', 0))           # miscFlags2

    if payload:
        buf.write(payload)

    return buf.getvalue()
