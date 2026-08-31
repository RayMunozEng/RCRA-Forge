"""
core/archive.py
Ratchet & Clank: Rift Apart PC — TOC + archive parser.

Written from ALERT (Amazing Luna Engine Research Tools) source by Tkachov.
https://github.com/Tkachov/ALERT  (GPL)

Key facts from ALERT source:
  - RCRA 'toc' magic: 0x34E89035  (toc2.py / TOC2 class)
  - Unlike MSMR, RCRA toc is NOT zlib-compressed — raw DAT1 after 8-byte header
  - DAT1 magic: 0x44415431  ("DAT1")
  - DAT1 section directory: 12B each (tag:u32, offset:u32, size:u32)
  - Asset IDs: 64-bit CRC64 hashes (section 0x506D7B8A)
  - Per-asset metadata: 16B RcraSizeEntry (section 0x65BCF461)
  - Archive filenames: 66B each (section 0x398ABFF0) for RCRA
  - Optional 36-byte per-asset headers section: 0x654BDED9

RcraSizeEntry layout (16 bytes):
  uint32  value          decompressed size
  uint32  archive_index  which .dat file
  uint32  offset         byte offset within archive
  int32   header_offset  into headers section (-1 = none)

Compressed archive block layout (32 bytes, from TOC2.extract_asset):
  uint32  real_offset
  uint32  _pad
  uint32  comp_offset
  uint32  _pad
  uint32  real_size
  uint32  comp_size
  uint8   comp_type      0=none, 2=gdeflate, 3=insomniac
  uint8   _pad
  uint16  _pad
  uint32  _pad
"""

import io
import os
import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional

# ── Version constants ─────────────────────────────────────────────────────────
VERSION_RCRA = 202300
VERSION_MSMR = 202200
VERSION_SO   = 201800

# ── Magic values ──────────────────────────────────────────────────────────────
TOC_MAGIC_MSMR           = 0x77AF12AF
TOC_MAGIC_RCRA           = 0x34E89035
DAT1_MAGIC               = 0x44415431
ARCHIVE_MAGIC_COMPRESSED = 0x52415344  # "DSRA" — compressed archive

# ── DAT1 section tags used in the TOC ────────────────────────────────────────
TAG_ARCHIVES      = 0x398ABFF0   # archive filename list
TAG_ASSET_IDS     = 0x506D7B8A   # array of uint64 asset IDs
TAG_SIZES         = 0x65BCF461   # per-asset size/offset/archive (16B for RCRA)
TAG_ASSET_HEADERS = 0x654BDED9   # optional 36-byte per-asset header blobs
TAG_TEXTURES      = 0x36A6C8CC   # texture asset ID list

# ── Asset type identifiers (unk1 field in DAT1 header) ────────────────────────
ASSET_TYPE_NAMES = {
    0x98906B9F: 'model',       # MSMR/Spider-Man
    0xDB40514C: 'model',       # MM/Miles Morales
    0x9D2C0FA9: 'model',       # RCRA/Rift Apart ← ModelRcra
    0x5C4580B9: 'texture',
    0x8F53A199: 'texture',     # RCRA PC streaming texture container
    0x8A0B1487: 'zone',        # Zone container type
    0x1F390AA0: 'zone',        # ZoneDef (tile/gp zones) ← confirmed from binary
    0x2AFE7495: 'level',
    0x21A56F68: 'config',
    0xF777E4A8: 'animset',
    0xC96F58F3: 'animclip',
    0x7C207220: 'actor',
    0x944BD3AD: 'actor',        # confirmed from binary (actor built file)
    0x39F27E27: 'atmosphere',
    0x1C04EF8C: 'material',
    0x07DC03E3: 'materialgraph',
    0x7E4F1BB7: 'soundbank',
    0xF05EF819: 'visualeffect',
    0x35C9D886: 'wwiselookup',
    0x567CC2F0: 'levellight',
    0x51B8E006: 'toc',
    0xC4999B32: 'cinematic2',
    0x23A93984: 'conduit',
    0x2A077A51: 'dag',
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ArchiveEntry:
    index:    int
    filename: str


@dataclass
class AssetEntry:
    index:    int
    asset_id: int
    archive:  int
    offset:   int
    size:     int
    header:   Optional[bytes] = None

    @property
    def name(self) -> str:
        return f"{self.asset_id:016X}"


# ── DAT1 container ────────────────────────────────────────────────────────────

class DAT1:
    """
    Insomniac DAT1 inner container.

    Header layout:
      0x00  4B  magic          0x44415431
      0x04  4B  unk1           asset-type identifier
      0x08  4B  total_size
      0x0C  2B  section_count
      0x0E  2B  unknown_count
      (16 + section_count*12 + unknown_count*8 bytes = header end)
      then: string table
      then: section data blobs (at their declared offsets)

    Each section header (12B):
      0x00  4B  tag
      0x04  4B  offset   (absolute from byte 0 of DAT1)
      0x08  4B  size
    """

    def __init__(self, data: bytes):
        self.data     = data
        self._view    = memoryview(data)   # zero-copy view
        self.unk1     = 0
        self.sections: dict[int, memoryview] = {}
        self._string_pool: bytes = b''
        self._string_pool_base: int = 0   # absolute offset of pool in DAT1
        self._parse()

    def _parse(self):
        d = self._view
        if len(d) < 16:
            return

        # Try offset 0 first (standard case)
        magic = struct.unpack_from('<I', d, 0)[0]

        # If not found at 0, scan the first 256 bytes for DAT1 magic
        # This handles assets with a prepended header blob
        offset = 0
        if magic != DAT1_MAGIC:
            for off in range(0, min(256, len(d) - 4), 4):
                if struct.unpack_from('<I', d, off)[0] == DAT1_MAGIC:
                    offset = off
                    magic = DAT1_MAGIC
                    break

        if magic != DAT1_MAGIC:
            return

        d = d[offset:]   # slice to start of DAT1
        self.unk1 = struct.unpack_from('<I', d, 4)[0]
        total_size = struct.unpack_from('<I', d, 8)[0]
        section_count, unknown_count = struct.unpack_from('<HH', d, 12)

        # String pool sits between header and first section
        # base = 16 + section_count*12 + unknown_count*8
        pool_base = 16 + section_count * 12 + unknown_count * 8
        self._string_pool_base = pool_base

        for i in range(section_count):
            base = 16 + i * 12
            if base + 12 > len(d):
                break
            tag, sec_offset, size = struct.unpack_from('<III', d, base)
            if sec_offset + size <= len(d):
                self.sections[tag] = d[sec_offset:sec_offset + size]

        # Build string pool: bytes from pool_base up to first section offset
        if section_count > 0 and pool_base < len(d):
            first_sec_off = min(
                struct.unpack_from('<I', d, 16 + i * 12 + 4)[0]
                for i in range(section_count)
                if 16 + i * 12 + 12 <= len(d)
            )
            pool_end = min(first_sec_off, len(d))
            self._string_pool = bytes(d[pool_base:pool_end])

    def get_section(self, tag: int) -> Optional[memoryview]:
        return self.sections.get(tag)

    def get_string(self, absolute_offset: int) -> Optional[str]:
        """
        Read a null-terminated string from the string pool.
        absolute_offset is as stored in section data (absolute from DAT1 start).
        Matches ALERT's DAT1.get_string(offset) behaviour.
        """
        rel = absolute_offset - self._string_pool_base
        if rel < 0 or rel >= len(self._string_pool):
            return None
        end = self._string_pool.find(b'\x00', rel)
        if end == -1:
            end = len(self._string_pool)
        try:
            return self._string_pool[rel:end].decode('utf-8', errors='replace')
        except Exception:
            return None

    @property
    def asset_type(self) -> str:
        return ASSET_TYPE_NAMES.get(self.unk1, f'{self.unk1:#010x}')


class _LazyEntryList:
    """
    A list-like container that stores asset data as raw numpy arrays
    and only constructs AssetEntry objects when individual items are accessed.
    Zero Python object construction during TOC load.
    """
    __slots__ = ('_ids', '_sizes', '_hdr_data', '_count', '_cache')

    def __init__(self, ids_arr, sizes_arr, hdr_data: bytes, count: int):
        self._ids      = ids_arr
        self._sizes    = sizes_arr
        self._hdr_data = hdr_data   # raw bytes buffer, sliced on demand
        self._count    = count
        self._cache: dict[int, AssetEntry] = {}

    def __len__(self) -> int:
        return self._count

    def __iter__(self):
        for i in range(self._count):
            yield self[i]

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            return [self[i] for i in range(*idx.indices(self._count))]
        if idx < 0:
            idx += self._count
        if idx in self._cache:
            return self._cache[idx]
        row   = self._sizes[idx]
        h_off = int(row['hdr_off'])
        hdr   = None
        if h_off != -1 and self._hdr_data is not None:
            start = h_off
            end   = start + 36
            if end <= len(self._hdr_data):
                # Convert memoryview slice to bytes only when actually needed
                hdr = bytes(self._hdr_data[start:end])
        entry = AssetEntry(
            index    = idx,
            asset_id = int(self._ids[idx]),
            archive  = int(row['archive']),
            offset   = int(row['offset']),
            size     = int(row['value']),
            header   = hdr,
        )
        if len(self._cache) < 10000:
            self._cache[idx] = entry
        return entry


# ── TOC parser ────────────────────────────────────────────────────────────────

class TocParser:
    """
    Parse the Rift Apart 'toc' file.

    File layout (RCRA, from toc2.py):
      0x00  4B  magic  0x34E89035
      0x04  4B  size   byte count of raw DAT1 that follows
      0x08  ... raw DAT1 (NOT zlib-compressed, unlike MSMR/Spider-Man)
    """

    def __init__(self, toc_path: str):
        self.toc_path  = toc_path
        self.game_root = os.path.dirname(toc_path)
        self.entries:  list[AssetEntry]  = []
        self.archives: list[ArchiveEntry] = []
        self._dat1:    Optional[DAT1]    = None

    def parse(self) -> list[AssetEntry]:
        return self.parse_with_progress()

    def parse_with_progress(self, progress=None) -> list[AssetEntry]:
        """
        Parse the TOC file and build the asset index.

        Parameters
        ----------
        progress : callable(str) | None
            Optional callback invoked with a human-readable status string
            at each major step. Safe to call from any thread.

        Returns
        -------
        list[AssetEntry]  (actually a _LazyEntryList)
        """
        def _emit(msg: str):
            if progress:
                progress(msg)

        _emit("Reading toc file from disk…")
        with open(self.toc_path, 'rb') as f:
            raw = f.read()

        _emit(f"Parsing DAT1 container ({len(raw) // 1024:,} KB)…")
        magic, size = struct.unpack_from('<II', raw, 0)

        if magic == TOC_MAGIC_RCRA:
            # memoryview — zero-copy slice of the raw buffer
            dat1_data = memoryview(raw)[8:8 + size]
        elif magic == TOC_MAGIC_MSMR:
            dat1_data = zlib.decompress(raw[8:])
        else:
            raise ValueError(
                f"Unknown TOC magic {magic:#010x}. "
                f"Expected {TOC_MAGIC_RCRA:#010x} (Rift Apart) "
                f"or {TOC_MAGIC_MSMR:#010x} (Spider-Man/MSMR)."
            )

        self._dat1 = DAT1(bytes(dat1_data))
        del raw  # free the raw buffer immediately after slicing

        _emit("Building asset index…")
        self._build_entries()
        return self.entries

    def group_by_archive(self) -> list[tuple[int, object]]:
        """
        Group entry indices by archive number.

        Returns a list of (archive_index, numpy_index_array) tuples,
        one per archive, sorted by archive index.  The index arrays
        can be used to slice self.entries directly.

        Must be called after parse() / parse_with_progress().
        """
        import numpy as np
        entries  = self.entries
        arc_col  = entries._sizes['archive'][:len(entries)].astype(np.int32)
        sort_idx = np.argsort(arc_col, kind='stable')
        sorted_arcs = arc_col[sort_idx]
        boundaries  = np.where(np.diff(sorted_arcs))[0] + 1
        starts = np.concatenate([[0], boundaries])
        ends   = np.concatenate([boundaries, [len(sort_idx)]])
        return [
            (int(sorted_arcs[s]), sort_idx[s:e])
            for s, e in zip(starts.tolist(), ends.tolist())
        ]

    def _build_entries(self):
        import numpy as np
        dat1 = self._dat1

        # ── Archives ──────────────────────────────────────────────────────────
        arc_data = dat1.get_section(TAG_ARCHIVES)
        if not arc_data:
            raise ValueError("TOC missing archives section (0x398ABFF0)")

        RCRA_ARC_SIZE = 66
        for i in range(len(arc_data) // RCRA_ARC_SIZE):
            raw = bytes(arc_data[i * RCRA_ARC_SIZE:(i + 1) * RCRA_ARC_SIZE])
            fn  = raw[:40]
            null = fn.find(b'\x00')
            if null >= 0:
                fn = fn[:null]
            filename = fn.decode('ascii', errors='replace').replace('\\', '/')
            self.archives.append(ArchiveEntry(index=i, filename=filename))

        # ── Asset IDs — bulk uint64 parse ─────────────────────────────────────
        ids_data = dat1.get_section(TAG_ASSET_IDS)
        if not ids_data:
            raise ValueError("TOC missing asset IDs section (0x506D7B8A)")
        self._asset_ids_arr = np.frombuffer(ids_data, dtype='<u8')

        # ── Per-asset metadata — bulk struct parse ────────────────────────────
        sizes_data = dat1.get_section(TAG_SIZES)
        if not sizes_data:
            raise ValueError("TOC missing sizes section (0x65BCF461)")
        self._sizes_arr = np.frombuffer(sizes_data, dtype=np.dtype([
            ('value',   '<u4'),
            ('archive', '<u4'),
            ('offset',  '<u4'),
            ('hdr_off', '<i4'),
        ]))

        # ── Optional asset header blobs — zero-copy memoryview ───────────────
        hdrs_data = dat1.get_section(TAG_ASSET_HEADERS)
        # Keep as memoryview — no copy. numpy can read directly from it.
        self._header_data = hdrs_data   # memoryview or None
        self._header_count = (len(hdrs_data) // 36) if hdrs_data else 0

        # ── Build lightweight entry list ──────────────────────────────────────
        count = min(len(self._asset_ids_arr), len(self._sizes_arr))
        self._entry_count = count
        self.entries = _LazyEntryList(
            self._asset_ids_arr,
            self._sizes_arr,
            self._header_data,   # raw buffer, not list of bytes
            count,
        )

    # ── Asset extraction ──────────────────────────────────────────────────────

    def extract_asset(self, entry: AssetEntry) -> bytes:
        """Extract and decompress the raw DAT1 bytes for the given entry."""
        if entry.archive >= len(self.archives):
            raise ValueError(f"Archive index {entry.archive} out of range")

        arc = self.archives[entry.archive]
        arc_path = os.path.join(self.game_root, arc.filename)
        if not os.path.exists(arc_path):
            raise FileNotFoundError(f"Archive file not found: {arc_path}")

        with open(arc_path, 'rb') as f:
            magic_v = struct.unpack('<I', f.read(4))[0]
            is_compressed = (magic_v == ARCHIVE_MAGIC_COMPRESSED)

            data = bytearray()
            if entry.header:
                data += entry.header

            if not is_compressed:
                f.seek(entry.offset)
                data += f.read(entry.size)
                return bytes(data)

            # Compressed: read block directory
            f.seek(12)
            blocks_end = struct.unpack('<I', f.read(4))[0]
            f.seek(32)
            blocks = []
            while f.tell() < blocks_end:
                real_off, _, comp_off, _, real_sz, comp_sz, ctype, _, _, _ = \
                    struct.unpack('<IIIIIIBBHI', f.read(32))
                blocks.append((real_off, comp_off, real_sz, comp_sz, ctype))

            a_off = entry.offset
            a_end = a_off + entry.size
            started = False
            comp_types_seen = set()

            for (real_off, comp_off, real_sz, comp_sz, ctype) in blocks:
                real_end = real_off + real_sz
                if real_off <= a_off < real_end:
                    started = True
                if started:
                    comp_types_seen.add(ctype)
                    f.seek(comp_off)
                    cdata = f.read(comp_sz)
                    block = _decompress_block(cdata, real_sz, ctype)
                    bstart = max(real_off, a_off) - real_off
                    bend   = min(a_end, real_end) - real_off
                    data  += block[bstart:bend]
                if real_off < a_end <= real_end:
                    break

            print(f"[extract_asset] comp_types used: {comp_types_seen}, "
                  f"extracted {len(data):,} bytes")
            return bytes(data)

    def get_archive_path(self, entry: AssetEntry) -> str:
        arc = self.archives[entry.archive]
        return os.path.join(self.game_root, arc.filename)

    def find_entry(self, asset_id: int) -> Optional['AssetEntry']:
        """Find an AssetEntry by asset ID, or None if not found."""
        import numpy as np
        try:
            ids_arr = self.entries._ids[:len(self.entries)]
            hits = np.where(ids_arr == asset_id)[0]
            if len(hits) == 0:
                return None
            return self.entries[int(hits[0])]
        except Exception:
            return None

    def find_entry_by_id_lo(self, asset_id_lo: int) -> Optional['AssetEntry']:
        """
        Find an AssetEntry by the low 32 bits of its asset ID.
        Used when only the lower half of the CRC64 is known (e.g. from
        material texture slot entries). Returns the first match, preferring
        texture-type entries. Returns None if no match.
        """
        import numpy as np
        try:
            ids_arr = self.entries._ids[:len(self.entries)]
            lo_arr  = (ids_arr & 0xFFFFFFFF).astype(np.uint64)
            hits    = np.where(lo_arr == np.uint64(asset_id_lo & 0xFFFFFFFF))[0]
            if len(hits) == 0:
                return None
            # Prefer the smallest match (SD entry) — HD is just raw pixel data
            entries = sorted([self.entries[int(i)] for i in hits], key=lambda e: e.size)
            return entries[0]
        except Exception:
            return None

    def find_all_entries(self, asset_id: int) -> list:
        """
        Find ALL AssetEntries with this asset ID (may be multiple — SD + HD spans).
        Returns entries sorted by size ascending (SD first, HD last).
        """
        import numpy as np
        try:
            ids_arr = self.entries._ids[:len(self.entries)]
            hits = np.where(ids_arr == asset_id)[0]
            entries = [self.entries[int(i)] for i in hits]
            return sorted(entries, key=lambda e: e.size)
        except Exception:
            return []


# ── Block decompression ───────────────────────────────────────────────────────

def _decompress_block(data: bytes, real_size: int, comp_type: int) -> bytearray:
    if comp_type == 0:
        # Uncompressed — data IS the block, just return it
        return bytearray(data[:real_size])
    elif comp_type == 2:
        try:
            from core import gdeflate
            return bytearray(gdeflate.decompress(data, real_size))
        except Exception as ex:
            raise RuntimeError(
                f"GDeflate decompression failed: {ex}\n"
                "Ensure libdeflate.dll is in the working directory."
            )
    elif comp_type == 3:
        return bytearray(_insomniac_decompress(data, real_size))
    raise ValueError(f"Unknown block compression type: {comp_type}")


def _insomniac_decompress(comp_data: bytes, real_size: int) -> bytes:
    """Insomniac custom LZ, ported from ALERT dat1lib/decompression.py."""
    real_data = bytearray(real_size)
    real_i = comp_i = 0
    comp_size = len(comp_data)

    while real_i <= real_size and comp_i < comp_size:
        a = comp_data[comp_i]; comp_i += 1
        b = 0
        if (a & 0xF0) == 0xF0:
            b = comp_data[comp_i]; comp_i += 1

        direct = (a >> 4) + b
        while direct >= 270 and (direct - 15) % 255 == 0:
            v = comp_data[comp_i]; comp_i += 1
            direct += v
            if v == 0:
                break

        for i in range(direct):
            if real_i + i >= real_size or comp_i + i >= comp_size:
                break
            real_data[real_i + i] = comp_data[comp_i + i]
        real_i += direct
        comp_i += direct

        if not (real_i <= real_size and comp_i < comp_size):
            break

        reverse = (a & 0x0F) + 4
        a = comp_data[comp_i]; b = comp_data[comp_i + 1]; comp_i += 2
        reverse_offset = a + (b << 8)

        if reverse == 19:
            reverse += comp_data[comp_i]; comp_i += 1
            while reverse >= 274 and (reverse - 19) % 255 == 0:
                v = comp_data[comp_i]; comp_i += 1
                reverse += v
                if v == 0:
                    break

        for i in range(reverse):
            if real_i + i >= real_size:
                break
            src = real_i + i - reverse_offset
            if 0 <= src < real_size:
                real_data[real_i + i] = real_data[src]
        real_i += reverse

    return bytes(real_data)


# ── CRC64 asset ID hashing (from ALERT dat1lib/crc64.py) ─────────────────────

_CRC64_TABLE = [
    0x0000000000000000,0xB32E4CBE03A75F6F,0xF4843657A840A05B,0x47AA7AE9ABE7FF34,
    0x7BD0C384FF8F5E33,0xC8FE8F3AFC28015C,0x8F54F5D357CFFE68,0x3C7AB96D5468A107,
    0xF7A18709FF1EBC66,0x448FCBB7FCB9E309,0x0325B15E575E1C3D,0xB00BFDE054F94352,
    0x8C71448D0091E255,0x3F5F08330336BD3A,0x78F572DAA8D1420E,0xCBDB3E64AB761D61,
    0x7D9BA13851336649,0xCEB5ED8652943926,0x891F976FF973C612,0x3A31DBD1FAD4997D,
    0x064B62BCAEBC387A,0xB5652E02AD1B6715,0xF2CF54EB06FC9821,0x41E11855055BC74E,
    0x8A3A2631AE2DDA2F,0x39146A8FAD8A8540,0x7EBE1066066D7A74,0xCD905CD805CA251B,
    0xF1EAE5B551A2841C,0x42C4A90B5205DB73,0x056ED3E2F9E22447,0xB6409F5CFA457B28,
    0xFB374270A266CC92,0x48190ECEA1C193FD,0x0FB374270A266CC9,0xBC9D3899098133A6,
    0x80E781F45DE992A1,0x33C9CD4A5E4ECDCE,0x7463B7A3F5A932FA,0xC74DFB1DF60E6D95,
    0x0C96C5795D7870F4,0xBFB889C75EDF2F9B,0xF812F32EF538D0AF,0x4B3CBF90F69F8FC0,
    0x774606FDA2F72EC7,0xC4684A43A15071A8,0x83C230AA0AB78E9C,0x30EC7C140910D1F3,
    0x86ACE348F355AADB,0x3582AFF6F0F2F5B4,0x7228D51F5B150A80,0xC10699A158B255EF,
    0xFD7C20CC0CDAF4E8,0x4E526C720F7DAB87,0x09F8169BA49A54B3,0xBAD65A25A73D0BDC,
    0x710D64410C4B16BD,0xC22328FF0FEC49D2,0x85895216A40BB6E6,0x36A71EA8A7ACE989,
    0x0ADDA7C5F3C4488E,0xB9F3EB7BF06317E1,0xFE5991925B84E8D5,0x4D77DD2C5823B7BA,
    0x64B62BCAEBC387A1,0xD7986774E864D8CE,0x90321D9D438327FA,0x231C512340247895,
    0x1F66E84E144CD992,0xAC48A4F017EB86FD,0xEBE2DE19BC0C79C9,0x58CC92A7BFAB26A6,
    0x9317ACC314DD3BC7,0x2039E07D177A64A8,0x67939A94BC9D9B9C,0xD4BDD62ABF3AC4F3,
    0xE8C76F47EB5265F4,0x5BE923F9E8F53A9B,0x1C4359104312C5AF,0xAF6D15AE40B59AC0,
    0x192D8AF2BAF0E1E8,0xAA03C64CB957BE87,0xEDA9BCA512B041B3,0x5E87F01B11171EDC,
    0x62FD4976457FBFDB,0xD1D305C846D8E0B4,0x96797F21ED3F1F80,0x2557339FEE9840EF,
    0xEE8C0DFB45EE5D8E,0x5DA24145464902E1,0x1A083BACEDAEFDD5,0xA9267712EE09A2BA,
    0x955CCE7FBA6103BD,0x267282C1B9C65CD2,0x61D8F8281221A3E6,0xD2F6B4961186FC89,
    0x9F8169BA49A54B33,0x2CAF25044A02145C,0x6B055FEDE1E5EB68,0xD82B1353E242B407,
    0xE451AA3EB62A1500,0x577FE680B58D4A6F,0x10D59C691E6AB55B,0xA3FBD0D71DCDEA34,
    0x6820EEB3B6BBF755,0xDB0EA20DB51CA83A,0x9CA4D8E41EFB570E,0x2F8A945A1D5C0861,
    0x13F02D374934A966,0xA0DE61894A93F609,0xE7741B60E174093D,0x545A57DEE2D35652,
    0xE21AC88218962D7A,0x5134843C1B317215,0x169EFED5B0D68D21,0xA5B0B26BB371D24E,
    0x99CA0B06E7197349,0x2AE447B8E4BE2C26,0x6D4E3D514F59D312,0xDE6071EF4CFE8C7D,
    0x15BB4F8BE788911C,0xA6950335E42FCE73,0xE13F79DC4FC83147,0x521135624C6F6E28,
    0x6E6B8C0F1807CF2F,0xDD45C0B11BA09040,0x9AEFBA58B0476F74,0x29C1F6E6B3E0301B,
    0xC96C5795D7870F42,0x7A421B2BD420502D,0x3DE861C27FC7AF19,0x8EC62D7C7C60F076,
    0xB2BC941128085171,0x0192D8AF2BAF0E1E,0x4638A2468048F12A,0xF516EEF883EFAE45,
    0x3ECDD09C2899B324,0x8DE39C222B3EEC4B,0xCA49E6CB80D9137F,0x7967AA75837E4C10,
    0x451D1318D716ED17,0xF6335FA6D4B1B278,0xB199254F7F564D4C,0x02B769F17CF11223,
    0xB4F7F6AD86B4690B,0x07D9BA1385133664,0x4073C0FA2EF4C950,0xF35D8C442D53963F,
    0xCF273529793B3738,0x7C0979977A9C6857,0x3BA3037ED17B9763,0x888D4FC0D2DCC80C,
    0x435671A479AAD56D,0xF0783D1A7A0D8A02,0xB7D247F3D1EA7536,0x04FC0B4DD24D2A59,
    0x3886B22086258B5E,0x8BA8FE9E8582D431,0xCC0284772E652B05,0x7F2CC8C92DC2746A,
    0x325B15E575E1C3D0,0x8175595B76469CBF,0xC6DF23B2DDA1638B,0x75F16F0CDE063CE4,
    0x498BD6618A6E9DE3,0xFAA59ADF89C9C28C,0xBD0FE036222E3DB8,0x0E21AC88218962D7,
    0xC5FA92EC8AFF7FB6,0x76D4DE52895820D9,0x317EA4BB22BFDFED,0x8250E80521188082,
    0xBE2A516875702185,0x0D041DD676D77EEA,0x4AAE673FDD3081DE,0xF9802B81DE97DEB1,
    0x4FC0B4DD24D2A599,0xFCEEF8632775FAF6,0xBB44828A8C9205C2,0x086ACE348F355AAD,
    0x34107759DB5DFBAA,0x873E3BE7D8FAA4C5,0xC094410E731D5BF1,0x73BA0DB070BA049E,
    0xB86133D4DBCC19FF,0x0B4F7F6AD86B4690,0x4CE50583738CB9A4,0xFFCB493D702BE6CB,
    0xC3B1F050244347CC,0x709FBCEE27E418A3,0x3735C6078C03E797,0x841B8AB98FA4B8F8,
    0xADDA7C5F3C4488E3,0x1EF430E13FE3D78C,0x595E4A08940428B8,0xEA7006B697A377D7,
    0xD60ABFDBC3CBD6D0,0x6524F365C06C89BF,0x228E898C6B8B768B,0x91A0C532682C29E4,
    0x5A7BFB56C35A3485,0xE955B7E8C0FD6BEA,0xAEFFCD016B1A94DE,0x1DD181BF68BDCBB1,
    0x21AB38D23CD56AB6,0x9285746C3F7235D9,0xD52F0E859495CAED,0x6601423B97329582,
    0xD041DD676D77EEAA,0x636F91D96ED0B1C5,0x24C5EB30C5374EF1,0x97EBA78EC690119E,
    0xAB911EE392F8B099,0x18BF525D915FEFF6,0x5F1528B43AB810C2,0xEC3B640A391F4FAD,
    0x27E05A6E926952CC,0x94CE16D091CE0DA3,0xD3646C393A29F297,0x604A2087398EADF8,
    0x5C3099EA6DE60CFF,0xEF1ED5546E415390,0xA8B4AFBDC5A6ACA4,0x1B9AE303C601F3CB,
    0x56ED3E2F9E224471,0xE5C372919D851B1E,0xA26908783662E42A,0x114744C635C5BB45,
    0x2D3DFDAB61AD1A42,0x9E13B115620A452D,0xD9B9CBFCC9EDBA19,0x6A978742CA4AE576,
    0xA14CB926613CF817,0x1262F598629BA778,0x55C88F71C97C584C,0xE6E6C3CFCADB0723,
    0xDA9C7AA29EB3A624,0x69B2361C9D14F94B,0x2E184CF536F3067F,0x9D36004B35545910,
    0x2B769F17CF112238,0x9858D3A9CCB67D57,0xDFF2A94067518263,0x6CDCE5FE64F6DD0C,
    0x50A65C93309E7C0B,0xE388102D33392364,0xA4226AC498DEDC50,0x170C267A9B79833F,
    0xDCD7181E300F9E5E,0x6FF954A033A8C131,0x28532E49984F3E05,0x9B7D62F79BE8616A,
    0xA707DB9ACF80C06D,0x14299724CC279F02,0x5383EDCD67C06036,0xE0ADA17364673F59,
]


def crc64_hash(path: str) -> int:
    """
    Compute the 64-bit asset ID for a given path string.
    Matches ALERT dat1lib/crc64.py hash() exactly.
    """
    data  = path.lower().replace('\\', '/')
    value = 0xC96C5795D7870F42
    for ch in data:
        value = 0xFFFFFFFFFFFFFFFF & ((value >> 8) ^ _CRC64_TABLE[0xFF & (value ^ ord(ch))])
    return (value >> 2) | 0x8000000000000000
