r"""
core/material.py
Ratchet & Clank: Rift Apart PC — material asset parser.

Reverse-engineered from hex dump of hero_ratchet_head.material (852 bytes).

DAT1 layout (unk1 = 0x88730155 = 'material'):
  Two sections:

  Section 1  tag=0xE1275683  (Material Built File header)
    Offset 0x00: string "Material Built File"
    Offset ~0x20: string "required\materials\basic_normal_gloss_subsurface.materialgraph"
    This describes which material graph/shader this material uses.
    Size: ~40 bytes

  Section 2  tag=0xF5260180 (Texture slot table + string table)
    Header (32 bytes):
      +0x00 uint32 total_size        — byte size of this whole section
      +0x14 uint32 texture_count     — number of texture slots
      +0x18 uint32 entry_array_off   — byte offset of texture entries
      +0x1C uint32 string_table_off  — byte offset of string table

    Then:         <texture_count> × 8-byte entries:
                    uint32  string_offset   — byte offset of path in string table
                    uint32  asset_id_lo     — low 32 bits of texture asset CRC64 hash
    Then:         string table — null-separated texture paths

  Texture slot naming convention (corrected by ilaac, May 2026):
    _c   → base_color       (primary base color map)
    id_  → color_id         (color ID — alternative base color when _c absent)
    _g   → specular_color   (specular color — was mislabeled albedo)
    _g_a → specular_ior     (Specular IOR Level, greyscale)
    _m   → mask             (packed: R=emission_mask, G=height, B=AO)
    _n   → normal           (normal map)
    _ao  → ambient_occlusion (dedicated AO — replaces _m when present)
    _sm  → micro_variation   (NPC dinosaur detail variation — Grunthors/Monks only, ~30 textures)
    _v   → detail
    _d   → detail_normal
    _s   → specular

  The asset_id_lo (low 32 bits of CRC64) can be used to look up the full
  asset entry in the TOC via HashLookup, or the path string can be hashed
  directly to find the matching texture asset.
"""

import struct
import re
from dataclasses import dataclass, field
from typing import Optional

from core.archive import DAT1


BLIZAR_LAVA_FLOW_GRAPH = (
    'materialgraph/environment/blizarprime/ground/blz_gbl_lava_01_flow/'
    'blz_gbl_lava_01_flow.materialgraph'
)

# These hashes are graph input names, not texture asset IDs.  The mapping and
# two retained graph defaults are taken from the shipped materialgraph's
# 0x1CAFE804 binding table.  Keeping the graph inputs distinct is essential:
# the lava material intentionally binds an FX map and a CMA map into the two
# inputs named as base maps by the graph.
_BLIZAR_LAVA_BINDING_ROLES = {
    0x2D487BD9: 'retail_lava_normal_a',
    0x3A336F9A: 'retail_lava_normal_b',
    0x8791CCB9: 'retail_lava_noise',
    0xC97834C0: 'retail_lava_color_a',
    0xF0F50805: 'retail_lava_color_b',
}
_BLIZAR_LAVA_GRAPH_DEFAULTS = (
    (
        0x0056CBD0,
        'retail_lava_mask_a',
        'textures/environment/ground/gnd_lava_rock_01/'
        'gnd_lava_rock_01_cma.texture',
    ),
    (
        0x39DBF715,
        'retail_lava_mask_b',
        'textures/environment/ground/gnd_lava_rock_01/'
        'gnd_lava_rock_01_cma.texture',
    ),
)

# ── DAT1 section tags ─────────────────────────────────────────────────────────
TAG_MATERIAL_HEADER  = 0xE1275683   # float params / built data
TAG_TEXTURE_TABLE    = 0xF5260180   # texture slot table + string table (from RE)
TAG_FUR_MATERIAL     = 0xD9B12454   # composite-fur settings + DAT1 string offsets

# Texture slot role inferred from path suffix.
# Channel breakdowns confirmed from Blender RE by community (Fanis + N7Lombax57):
#
#   _g  → albedo/gloss     (base color + gloss packed)
#   _c  → color            (albedo variant, e.g. skin color layer)
#   _n  → normal map       (tangent-space, BC5/RG)
#   _m  → AO + Emission    R=AmbientOcclusion, G=Emission, B=unused/mix
#                          ↳ mostly blue for non-emissive (Ratchet head)
#                          ↳ red/pink highlights for emissive parts (wrench bolts)
#   _s  → specular
#   _v  → detail variant
#   _d  → detail normal
#   _ao → ambient occlusion (dedicated AO map, rare)
_SUFFIX_ROLES = {
    # Base color
    '_c':         'base_color',      # primary base color map
    '_col':       'base_color',
    '_basecolor': 'base_color',
    '_diffuse':   'base_color',
    '_alb':       'base_color',
    # Specular color (_g was previously mislabeled as albedo — corrected by ilaac)
    '_g':         'specular_color',  # specular color map
    '_g_a':       'specular_ior',    # Specular IOR Level (greyscale)
    # Packed mask (_m channels: R=emission mask, G=height, B=AO — confirmed ilaac)
    '_m':         'mask',            # packed: R=emission_mask G=height B=ao
    # Normal map
    '_n':         'normal',
    '_nrm':       'normal',
    '_nor':       'normal',
    # Dedicated AO (replaces _m when present)
    '_ao':        'ambient_occlusion',
    # Detail maps
    '_v':         'detail',
    '_d':         'detail_normal',
    '_s':         'specular',
    # Micro-variation mask (NPC dinosaurs only — Grunthors, Monks)
    # Used by npc_dinosaur_detail_variation materialgraph (~30 textures total)
    # Makes each individual NPC look slightly unique
    '_sm':        'micro_variation',
    '_e':         'emissive',
}

# Prefix-based roles (checked separately — these are prefixes not suffixes)
_PREFIX_ROLES = {
    'id_':  'color_id',   # color ID map — alternative base color when _c is absent
}


def _infer_role(path: str) -> str:
    """Infer texture slot role from path prefix or suffix before .texture."""
    stem = path.rsplit('.', 1)[0].lower()   # strip .texture
    filename = stem.rsplit('/', 1)[-1]  # just the filename

    # Composite-fur materials use a dedicated control texture rather than the
    # ordinary serialized texture table.  Match this before the generic
    # suffixes so ``*_fur_control`` cannot fall through to ``unknown``.
    if filename.endswith('_fur_control'):
        return 'fur_control'

    # Effect graphs use descriptive packed-map suffixes rather than the
    # ordinary character/prop PBR convention. Blizar Prime lava is one such
    # material: its visible colour is synthesized from an HDR ``_fx`` map,
    # a ``_cma`` breakup mask, two normals, and a tiled noise source.
    if 'noise' in filename:
        return 'noise'
    if stem.endswith('_fx'):
        return 'emissive'
    if stem.endswith('_cma'):
        return 'effect_mask'

    # Check prefixes first (e.g. id_something)
    for prefix, role in _PREFIX_ROLES.items():
        if filename.startswith(prefix):
            return role

    # Check suffixes
    for suffix, role in _SUFFIX_ROLES.items():
        if stem.endswith(suffix):
            return role

    return 'unknown'


def _base_color_candidates(material_name: str, slots: list,
                           source_path: str = '') -> list[str]:
    """Return conservative base-map fallbacks for ordinary materials.

    The Blizar lava graph is deliberately excluded.  Retail bytecode confirms
    that it synthesizes colour from its FX/CMA inputs; loading a sibling ``_c``
    texture changes the shipped material rather than repairing it.
    """
    context = ' '.join((material_name or '', source_path or '')).replace('\\', '/').lower()
    if 'lava_rock' not in context:
        return []
    return []


@dataclass
class TextureSlot:
    """One texture binding in a material."""
    index:       int          # slot index (0-based)
    path:        str          # full asset path, e.g. 'characters/.../head_n.texture'
    asset_id_lo: int          # graph input/binding hash (legacy field name)
    role:        str          # inferred role: 'albedo', 'normal', 'metallic', etc.

    @property
    def name(self) -> str:
        """Short filename without extension."""
        return self.path.rsplit('/', 1)[-1].rsplit('.', 1)[0]

    @property
    def binding_hash(self) -> int:
        return self.asset_id_lo

    def __repr__(self):
        return f"<TextureSlot[{self.index}] {self.role} '{self.name}'>"


@dataclass
class MaterialAsset:
    """Parsed .material asset."""
    graph_path:    str                    # material graph path (shader type)
    slots:         list = field(default_factory=list)  # list[TextureSlot]
    parameters:    dict = field(default_factory=dict)  # graph-input hash -> raw bytes
    fur_settings:  tuple = field(default_factory=tuple)
    fur_layer_count: int = 0
    fur_lod_reduction: float = 0.0

    @property
    def albedo_slot(self) -> Optional['TextureSlot']:
        """Primary base color slot — _c first, then color_id fallback."""
        # Priority 1: base_color (_c)
        for s in self.slots:
            if s.role == 'base_color':
                return s
        # Priority 2: color_id (id_ prefix) — used when _c is absent
        for s in self.slots:
            if s.role == 'color_id':
                return s
        # Priority 3: first non-utility slot
        _non_albedo = {'normal', 'mask', 'specular_color', 'specular_ior',
                       'specular', 'detail', 'detail_normal', 'ambient_occlusion',
                       'fur_control', 'unknown'}
        for s in self.slots:
            if s.role not in _non_albedo:
                return s
        # Last resort: slot 0
        return self.slots[0] if self.slots else None

    @property
    def normal_slot(self) -> Optional['TextureSlot']:
        for s in self.slots:
            if s.role == 'normal':
                return s
        return None

    @property
    def mask_slot(self) -> Optional['TextureSlot']:
        """Packed mask map: R=emission_mask, G=height, B=AO (_m suffix)."""
        for s in self.slots:
            if s.role == 'mask':
                return s
        return None

    @property
    def ao_emission_slot(self) -> Optional['TextureSlot']:
        """Backwards-compat alias for mask_slot."""
        return self.mask_slot

    @property
    def specular_color_slot(self) -> Optional['TextureSlot']:
        """Specular color map (_g suffix)."""
        for s in self.slots:
            if s.role == 'specular_color':
                return s
        return None

    @property
    def specular_ior_slot(self) -> Optional['TextureSlot']:
        """Specular IOR Level map (_g_a suffix)."""
        for s in self.slots:
            if s.role == 'specular_ior':
                return s
        return None

    @property
    def color_id_slot(self) -> Optional['TextureSlot']:
        """Color ID map (id_ prefix) — alternative base color."""
        for s in self.slots:
            if s.role == 'color_id':
                return s
        return None

    @property
    def ao_slot(self) -> Optional['TextureSlot']:
        """Dedicated AO map (_ao suffix) — replaces _m when present."""
        for s in self.slots:
            if s.role == 'ambient_occlusion':
                return s
        return None

    def slot_by_role(self, role: str) -> Optional['TextureSlot']:
        """Look up a slot by role string."""
        for s in self.slots:
            if s.role == role:
                return s
        return None

    def __repr__(self):
        return f"<MaterialAsset graph='{self.graph_path}' slots={len(self.slots)}>"


# ── Parser ────────────────────────────────────────────────────────────────────

class MaterialParser:
    """
    Parse a raw .material DAT1 asset blob into a MaterialAsset.

    The format was reverse-engineered from hero_ratchet_head.material (852 bytes).

    Section layout within DAT1:
      Section 1 (tag 0xE1275683, ~40 bytes):
        Null-terminated strings:
          [0] "Material Built File"
          [1] graph path, e.g. 'required\\materials\\basic_normal_gloss_subsurface.materialgraph'

      Section 2 (large section, tag varies):
        uint32  total_size
        uint32  entry_count        (number of texture slots)
        uint32  string_table_off   (byte offset of string table within section data)
        ... (header padding / float params) ...
        entry_count × 8-byte entries:
          uint32  str_off           (byte offset of path string in string table)
          uint32  asset_id_lo       (low 32 bits of CRC64 asset hash)
        string table:
          null-separated path strings

    The entry array begins at (section_data_start + string_table_off - entry_count*8)
    based on the observed layout where string table immediately follows entries.
    """

    def __init__(self, data: bytes):
        self.data = data
        try:
            self.dat1 = DAT1(data)
        except Exception as ex:
            raise ValueError(f"Failed to parse DAT1: {ex}")

    def parse(self) -> MaterialAsset:
        graph_path = self._parse_graph_path()
        slots      = self._parse_texture_slots()
        slots      = self._apply_graph_bindings(graph_path, slots)
        parameters = self._parse_parameters()
        fur_layer_count, fur_lod_reduction = self._parse_fur_header()
        fur_settings = self._parse_fur_settings()
        return MaterialAsset(
            graph_path=graph_path,
            slots=slots,
            parameters=parameters,
            fur_settings=fur_settings,
            fur_layer_count=fur_layer_count,
            fur_lod_reduction=fur_lod_reduction,
        )

    def _parse_fur_header(self) -> tuple[int, float]:
        """Return the authored Fur_LayerCount and Fur_LoDReduction fields."""
        tagged = self.dat1.sections.get(TAG_FUR_MATERIAL)
        sec = bytes(tagged) if tagged is not None else None
        if sec is None or len(sec) < 8:
            return 0, 0.0
        try:
            return struct.unpack_from('<If', sec, 0)
        except struct.error:
            return 0, 0.0

    def _parse_fur_settings(self) -> tuple:
        """Return length, density, offset, gloss, specular, transmittance, wind."""
        tagged = self.dat1.sections.get(TAG_FUR_MATERIAL)
        sec = bytes(tagged) if tagged is not None else None
        if sec is None or len(sec) < 36:
            return ()
        try:
            return struct.unpack_from('<7f', sec, 8)
        except struct.error:
            return ()

    # ── Private ───────────────────────────────────────────────────────────────

    def _parse_graph_path(self) -> str:
        """
        Extract the material graph path from the DAT1 string pool.

        The string pool sits between the DAT1 header+directory and the first
        section data. Layout:
          uint32  total_pool_size
          uint32  string_data_size
          bytes   null-separated strings:
                    [0] "Material Built File"
                    [1] graph path (e.g. 'required\\materials\\...materialgraph')
        """
        try:
            match = re.search(
                rb'([A-Za-z0-9_./\\-]+\.materialgraph)\x00',
                self.data,
                flags=re.IGNORECASE,
            )
            if match:
                return re.sub(
                    r'/+', '/',
                    match.group(1).decode('utf-8', errors='replace')
                    .replace('\\', '/'),
                ).lower()
            return 'unknown'
        except Exception:
            return 'unknown'

    def _parse_parameters(self) -> dict:
        """Decode instance parameter overrides from Material Serialized Data."""
        section = self.dat1.sections.get(TAG_TEXTURE_TABLE)
        if section is None or len(section) < 40:
            return {}
        data = bytes(section)
        try:
            _, count, _, _, batch_end = struct.unpack_from('<IIIII', data, 0)
            keys_end = 40 + count * 8
            if count > 128 or batch_end < keys_end or batch_end > len(data):
                return {}
            values = data[keys_end:batch_end]
            result = {}
            for index in range(count):
                offset, size, key = struct.unpack_from('<HHI', data, 40 + index * 8)
                result[key] = values[offset:offset + size]
            return result
        except Exception:
            return {}

    @staticmethod
    def _apply_graph_bindings(graph_path: str, slots: list) -> list:
        normalized = (graph_path or '').replace('\\', '/').lower().lstrip('/')
        if normalized != BLIZAR_LAVA_FLOW_GRAPH:
            return slots

        mapped = []
        seen = set()
        for slot in slots:
            role = _BLIZAR_LAVA_BINDING_ROLES.get(slot.binding_hash, slot.role)
            mapped.append(TextureSlot(
                index=slot.index,
                path=slot.path,
                asset_id_lo=slot.asset_id_lo,
                role=role,
            ))
            seen.add(slot.binding_hash)
        for binding_hash, role, path in _BLIZAR_LAVA_GRAPH_DEFAULTS:
            if binding_hash not in seen:
                mapped.append(TextureSlot(
                    index=len(mapped),
                    path=path,
                    asset_id_lo=binding_hash,
                    role=role,
                ))
        return mapped

    def _parse_texture_slots(self) -> list:
        """
        Parse the texture slot table from section TAG_TEXTURE_TABLE (0xF5260180).

        Confirmed layout (from RE of hero_ratchet_head.material):
          Section data header (32 bytes):
            +0x00  uint32  total_size        = 0x270 (624)
            +0x04  uint32  entry_count       = 7
            +0x08  uint32  unk_offset_a      = 0x60  (sub-table offset)
            +0x0C  uint32  padding           = 0
            +0x10  uint32  unk_b             = 0x7C
            +0x14  uint32  entry_count2      = 7  (same as entry_count)
            +0x18  uint32  unk_c             = 0x7C
            +0x1C  uint32  string_table_off  = 0xB4 (180) ← actual string table offset

          Entry array at (string_table_off - entry_count × 8):
            entry_count × 8-byte entries:
              uint32  string_byte_offset  (into string table)
              uint32  asset_id_lo         (low 32 bits of CRC64 hash)

          String table at string_table_off:
            null-separated texture paths
        """
        slots = []

        # The texture table has an explicit DAT1 tag. Large RGB-blend
        # materials also contain hundreds of kilobytes of compiled shader
        # data; choosing the largest non-header section parsed bytecode instead
        # of the actual bindings and incorrectly reported no textures.
        tagged = self.dat1.sections.get(TAG_TEXTURE_TABLE)
        sec = bytes(tagged) if tagged is not None else None
        if sec is None or len(sec) < 32:
            return self._parse_fur_texture_slots()

        try:
            # Confirmed RCRA header layout:
            #   +0x14 texture_count
            #   +0x18 texture_entry_array_offset
            #   +0x1C texture_string_table_offset
            # The +0x04 count describes another binding table and silently
            # drops textures on ordinary materials (or is zero on some).
            total_size = struct.unpack_from('<I', sec, 0)[0]
            entry_count = struct.unpack_from('<I', sec, 0x14)[0]
            entry_array_off = struct.unpack_from('<I', sec, 0x18)[0]
            string_table_off = struct.unpack_from('<I', sec, 0x1C)[0]

            if entry_count == 0 or entry_count > 128:
                return slots
            if string_table_off >= len(sec):
                return slots
            if entry_array_off < 32 or entry_array_off + entry_count * 8 > string_table_off:
                return slots

            str_table = sec[string_table_off:]

            for i in range(entry_count):
                off = entry_array_off + i * 8
                if off + 8 > len(sec):
                    break
                str_off, id_lo = struct.unpack_from('<II', sec, off)
                path = self._read_string(str_table, str_off)
                if not path:
                    continue
                path = re.sub(r'/+', '/', path.replace('\\', '/'))
                slots.append(TextureSlot(
                    index       = i,
                    path        = path,
                    asset_id_lo = id_lo,
                    role        = _infer_role(path),
                ))

        except Exception as ex:
            print(f"[MaterialParser] slot parse error: {ex}")

        return slots

    def _parse_fur_texture_slots(self) -> list:
        """Parse the compact texture list used by shipped fur materials.

        Unlike ordinary materials, composite-fur instances do not carry the
        ``TAG_TEXTURE_TABLE`` section.  Their ``TAG_FUR_MATERIAL`` payload has
        a 36-byte settings header followed by DAT1 string-pool offsets.  The
        observed Ratchet, Rivet, sheep and critter materials all use this
        layout for color, normal, specular and fur-control maps.
        """
        tagged = self.dat1.sections.get(TAG_FUR_MATERIAL)
        sec = bytes(tagged) if tagged is not None else None
        if sec is None or len(sec) < 40:
            return []

        slots = []
        try:
            # Keep the parser conservative: these are string-pool references,
            # not an inline string table, and every accepted value must name a
            # cooked texture asset.
            count = min((len(sec) - 36) // 4, 16)
            for index in range(count):
                string_offset = struct.unpack_from('<I', sec, 36 + index * 4)[0]
                path = self.dat1.get_string(string_offset)
                if not path or not path.lower().endswith('.texture'):
                    continue
                path = re.sub(r'/+', '/', path.replace('\\', '/'))
                role = 'fur_control' if index == 3 else _infer_role(path)
                slots.append(TextureSlot(
                    index=index,
                    path=path,
                    asset_id_lo=0,
                    role=role,
                ))
        except Exception as ex:
            print(f"[MaterialParser] fur slot parse error: {ex}")
        return slots

    def _find_entry_array(self, sec: bytes, count: int, str_table_off: int):
        """
        Fallback: scan backwards from str_table_off to find the entry array
        by verifying that str_off values point to valid null-terminated strings.
        """
        str_table = sec[str_table_off:]
        entry_size = count * 8
        # Try from (str_table_off - entry_size) backwards by 4 bytes
        for candidate in range(str_table_off - entry_size, max(0, str_table_off - entry_size - 64), -4):
            valid = True
            for i in range(count):
                off = candidate + i * 8
                if off + 8 > len(sec):
                    valid = False
                    break
                str_off, _ = struct.unpack_from('<II', sec, off)
                if str_off >= len(str_table):
                    valid = False
                    break
                # Check that str_table[str_off] is a valid printable ASCII path
                if str_off < len(str_table) and not (0x20 <= str_table[str_off] < 0x7F):
                    valid = False
                    break
            if valid:
                return candidate
        return None

    @staticmethod
    def _read_string(data: bytes, offset: int) -> str:
        """Read a null-terminated UTF-8 string from data at offset."""
        if offset >= len(data):
            return ''
        end = data.index(b'\x00', offset) if b'\x00' in data[offset:] else len(data)
        try:
            return data[offset:end].decode('utf-8', errors='replace')
        except Exception:
            return ''


def parse_material_asset(data: bytes) -> MaterialAsset:
    """Convenience function: parse raw bytes → MaterialAsset."""
    return MaterialParser(data).parse()
