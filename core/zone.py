"""
core/zone.py
ZoneDef DAT1 parser for RCRA Forge.

Handles two zone entry paths:
  Actors: 32-byte instance records select scene offsets, actor references,
          instance names/IDs and component ranges.
  ART models: explicit byte offsets in TAG_MODEL_INDICES point into
              TAG_SCENE_NODES without a section header. Other node types can
              occur between models and must not be counted as model records.

Retail model node fields (see docs/ENVIRONMENT_PROBES.md for executable anchors):
  +0x00 (64): row-vector affine matrix, including scale; translation at +0x30
  +0x5C (4): flags, with node type byte at +0x5F (0 for these models)
  +0x7C (4): serialized byte size, high bit marks a prebuilt renderer node
  +0x100 (8): scene instance ID, distinct from the model asset ID
  +0x110 (2): signed model table index

TAG_MODEL_INDICES: u32[] of byte offsets into scene payload, one per model-bearing entry.
  Each offset is relative to the beginning of TAG_SCENE_NODES.

TAG_MODEL_ASSETS: n u64 asset IDs followed by n u32 DAT1 string offsets.
  The section is exactly 12*n bytes; the string offsets are not asset IDs.

Matrices remain zone-local. The owning runtime zone matrix is a separate input.
Actor instances use section 0x70682CB8; models and actors may coexist in a zone.
Unindexed scene data (lights, volumes and other types) is not guessed to be actors.

Name/string pool: DAT1-internal, pool_base = 0x10 + section_count*12
Actor/model paths stored as null-terminated strings in pool.
"""

import struct
from dataclasses import dataclass, field
from typing import Optional

from core.scene_components import SceneComponent, parse_component_records


ZONE_DEF_TYPE      = 0x1F390AA0

TAG_SCENE_NODES    = 0x06abcab2   # Scene node placement array (both formats)
TAG_ENTRY_INDEX    = 0xdc625b3d   # Actor name offsets (indexed by actor instance records)
TAG_MODEL_INDICES  = 0x6987F172   # u32 byte offsets into TAG_SCENE_NODES
TAG_MODEL_ASSETS   = 0xC6A5905E   # u64[n] asset IDs then u32[n] string offsets
TAG_ACTOR_INSTANCES = 0x70682CB8  # 32-byte records
TAG_ACTOR_ASSETS = 0x78684035     # u64[n] actor IDs then u32[n] string offsets
TAG_COMPONENTS = 0x50EDC53D       # 32-byte component records; payload offsets are DAT1-relative


@dataclass
class SceneNodeEntry:
    index:      int
    asset_id:   int       # actor asset ID, or 0 for a direct model
    model_id:   int       # model asset_id (art) or 0 (gp — resolved via actor)
    name:       str
    x:          float
    y:          float
    z:          float
    rot:        tuple
    flags:      int
    raw:        bytes = field(repr=False, default=b'')
    matrix:     tuple = ()  # Retail row-vector 4x4, flat; also glTF column-major
    instance_id: int = 0    # Actor-record ID, or renderer ID for a direct model
    scene_offset: int = 0  # Byte offset into TAG_SCENE_NODES
    node_type: int = 0
    actor_path: str = ''
    instance_flags: int = 0
    instance_reserved: int = 0
    components: tuple[SceneComponent, ...] = ()  # Zone overrides only, not actor defaults
    renderer_instance_id: int = 0  # Model-definition +0x100, when node_type == 0

    @property
    def position(self):
        return (self.x, self.y, self.z)

    @property
    def scene_light(self):
        """Parsed native light data for a type-1 entry, otherwise ``None``."""
        if self.node_type != 1:
            return None
        from core.scene_lights import parse_scene_light_definition
        return parse_scene_light_definition(self.raw)

    def __repr__(self):
        return (f"SceneNodeEntry(index={self.index}, "
                f"name={self.name!r}, "
                f"pos=({self.x:.2f},{self.y:.2f},{self.z:.2f}))")


@dataclass
class ZoneDef:
    asset_id:    int
    name:        str
    entries:     list
    actor_paths: list  = None
    model_paths: list  = None   # .model paths (art zones — direct model refs)
    model_ids:   list  = None   # model asset_id[] from TAG_MODEL_ASSETS (art zones)
    is_art_zone: bool  = False
    actor_ids: list = None

    @property
    def entry_count(self):
        return len(self.entries)

    def __repr__(self):
        kind = 'art' if self.is_art_zone else 'gp'
        return f"ZoneDef(name={self.name!r}, entries={self.entry_count}, kind={kind})"


def _read_string(data: bytes, offset: int) -> str:
    if not data or offset < 0 or offset >= len(data):
        return ''
    end = data.find(b'\x00', offset)
    end = end if end != -1 else len(data)
    try:
        return data[offset:end].decode('utf-8', errors='replace')
    except Exception:
        return ''


class ZoneParser:
    def __init__(self, data: bytes, lookup=None):
        self._data   = data
        self._lookup = lookup

    def parse(self, asset_id: int = 0, name: str = '') -> ZoneDef:
        data = self._data

        dat1_off = data.find(b'\x31\x54\x41\x44')
        if dat1_off == -1:
            raise ValueError(f"No DAT1 in zone {name!r}")

        section_count, unknown_count = struct.unpack_from('<HH', data, dat1_off + 12)
        sections  = {}
        for i in range(section_count):
            base = dat1_off + 0x10 + i * 12
            tag, sec_off, sec_size = struct.unpack_from('<III', data, base)
            abs_off = dat1_off + sec_off
            if abs_off + sec_size > len(data):
                raise ValueError(f'Truncated zone section {tag:08X}')
            sections[tag] = data[abs_off:abs_off + sec_size]
        # Determine zone type from available sections
        is_art = TAG_MODEL_INDICES in sections or TAG_MODEL_ASSETS in sections

        def read_references(tag, label):
            refs = sections.get(tag, b'')
            if len(refs) % 12:
                raise ValueError(f'Malformed zone {label} reference table: expected 12*n bytes')
            count = len(refs) // 12
            ids = list(struct.unpack_from(f'<{count}Q', refs))
            paths = [_read_string(data, dat1_off + offset)
                     for offset in struct.unpack_from(f'<{count}I', refs, count*8)]
            return ids, paths

        model_ids, model_paths = read_references(TAG_MODEL_ASSETS, 'model')
        actor_ids, actor_paths = read_references(TAG_ACTOR_ASSETS, 'actor')
        components = parse_component_records(data[dat1_off:], sections.get(TAG_COMPONENTS, b''))

        # Parse scene nodes
        entries = []
        scene_data = sections.get(TAG_SCENE_NODES, b'')
        entries = self._parse_model_nodes(scene_data, sections.get(TAG_MODEL_INDICES, b''),
                                          model_ids, model_paths)
        actors = self._parse_actor_nodes(
            scene_data, sections.get(TAG_ACTOR_INSTANCES, b''),
            sections.get(TAG_ENTRY_INDEX, b''), actor_ids, actor_paths,
            components, data, dat1_off)
        for entry in actors:
            entry.index += len(entries)
        entries.extend(actors)

        return ZoneDef(
            asset_id=asset_id, name=name, entries=entries,
            actor_paths=actor_paths, model_paths=model_paths,
            model_ids=model_ids, is_art_zone=is_art, actor_ids=actor_ids,
        )

    def _parse_model_nodes(self, scene_data, offsets, model_ids, model_paths):
        if len(offsets) % 4:
            raise ValueError('Malformed zone model offsets: expected u32 entries')
        entries = []
        for index, (offset,) in enumerate(struct.iter_unpack('<I', offsets)):
            if offset + 0x112 > len(scene_data):
                raise ValueError(f'Truncated model node at scene byte {offset}')
            if scene_data[offset + 0x5F] != 0:
                raise ValueError(f'Model offset {offset} points to a different scene node type')
            size = struct.unpack_from('<I', scene_data, offset + 0x7C)[0] & 0x7FFFFFFF
            if size < 0x112 or offset + size > len(scene_data):
                raise ValueError(f'Invalid model node size {size} at scene byte {offset}')
            model_index = struct.unpack_from('<h', scene_data, offset + 0x110)[0]
            if not 0 <= model_index < len(model_ids):
                raise ValueError(f'Invalid model table index {model_index} at scene byte {offset}')
            raw = scene_data[offset:offset + size]
            matrix = struct.unpack_from('<16f', raw)
            model_id = model_ids[model_index]
            path = model_paths[model_index]
            if not path and self._lookup:
                path = self._lookup.name(model_id)
            name = path.replace('\\', '/').rsplit('/', 1)[-1] if path else f'node_{index}'
            entries.append(SceneNodeEntry(
                index=index, asset_id=0, model_id=model_id,
                name=name.removesuffix('.model'),
                x=matrix[12], y=matrix[13], z=matrix[14],
                rot=matrix[0:3] + matrix[4:7] + matrix[8:11],
                flags=struct.unpack_from('<I', raw, 0x5C)[0], raw=raw, matrix=matrix,
                instance_id=struct.unpack_from('<Q', raw, 0x100)[0], scene_offset=offset,
                renderer_instance_id=struct.unpack_from('<Q', raw, 0x100)[0],
            ))
        return entries

    def _parse_actor_nodes(self, scene, records, names, actor_ids, actor_paths,
                           components, full_data, dat1_off):
        if len(records) % 32 or len(names) % 4:
            raise ValueError('Malformed actor instance/name table')
        name_offsets = struct.unpack(f'<{len(names)//4}I', names)
        entries = []
        for index, record in enumerate(struct.iter_unpack('<iiIiIHHQ', records)):
            name_index, actor_index, offset, start, count, flags, reserved, instance_id = record
            if not 0 <= actor_index < len(actor_ids):
                raise ValueError(f'Invalid actor asset index {actor_index} in instance {index}')
            if name_index >= len(name_offsets):
                raise ValueError(f'Invalid actor name index {name_index} in instance {index}')
            if count and (start < 0 or start + count > len(components)):
                raise ValueError(f'Invalid component range in actor instance {index}')
            if offset + 0x80 > len(scene):
                raise ValueError(f'Truncated actor scene definition at byte {offset}')
            size = struct.unpack_from('<I', scene, offset + 0x7C)[0] & 0x7FFFFFFF
            if size < 0x80 or offset + size > len(scene):
                raise ValueError(f'Invalid actor scene size {size} at byte {offset}')
            raw = scene[offset:offset + size]
            matrix = struct.unpack_from('<16f', raw)
            node_type = raw[0x5F]
            if node_type == 0 and size < 0x108:
                raise ValueError(f'Truncated actor model definition at byte {offset}')
            name = (_read_string(full_data, dat1_off + name_offsets[name_index])
                    if name_index >= 0 else '')
            entries.append(SceneNodeEntry(
                index=index, asset_id=actor_ids[actor_index], model_id=0, name=name,
                x=matrix[12], y=matrix[13], z=matrix[14],
                rot=matrix[:3] + matrix[4:7] + matrix[8:11],
                flags=struct.unpack_from('<I', raw, 0x5C)[0], raw=raw, matrix=matrix,
                instance_id=instance_id, scene_offset=offset, node_type=node_type,
                actor_path=actor_paths[actor_index], instance_flags=flags,
                instance_reserved=reserved, components=tuple(components[start:start+count]) if count else (),
                renderer_instance_id=struct.unpack_from('<Q', raw, 0x100)[0] if node_type == 0 else 0,
            ))
        return entries


def parse_zone_asset(data: bytes, asset_id: int = 0,
                     name: str = '', lookup=None) -> Optional[ZoneDef]:
    dat1_off = data.find(b'\x31\x54\x41\x44')
    if dat1_off == -1:
        return None
    unk1 = struct.unpack_from('<I', data, dat1_off + 4)[0]
    if unk1 != ZONE_DEF_TYPE:
        return None
    try:
        return ZoneParser(data, lookup).parse(asset_id=asset_id, name=name)
    except Exception as ex:
        import traceback
        print(f"[zone] parse failed for {name!r}: {ex}")
        traceback.print_exc()
        return None
