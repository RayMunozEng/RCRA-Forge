"""
core/actor.py
Actor DAT1 parser for RCRA Forge.

Retail loader 0x140F18A20 reads the model-path string offset from section
0x32FAC8E0, the default scene definition from 0x364A6C7C, and component
definitions from 0x135832C8. String-pool order does not select the model.
"""

import struct
from dataclasses import dataclass
from typing import Optional

from core.archive import DAT1
from core.scene_components import SceneComponent, parse_component_records


ACTOR_TYPE = 0x944BD3AD
TAG_ACTOR_HEADER = 0x32FAC8E0
TAG_ACTOR_SCENE = 0x364A6C7C
TAG_ACTOR_COMPONENTS = 0x135832C8


@dataclass
class ActorAsset:
    """Actor model reference, default scene definition, and component defaults."""
    model_path:  Optional[str]   # e.g. "environment\\...\\chair.model"
    model_asset_id: Optional[int]  # resolved via HashLookup (None if not in hashes.txt)
    all_strings: list            # all strings found in pool (for debugging)
    scene_type: Optional[int] = None
    scene_data: bytes = b''
    components: tuple[SceneComponent, ...] = ()

    @property
    def has_model(self) -> bool:
        return self.model_path is not None

    def __repr__(self):
        return f"ActorAsset(model={self.model_path!r})"


def parse_actor_asset(data: bytes,
                      lookup=None) -> Optional[ActorAsset]:
    """
    Parse an actor DAT1 asset.

    Parameters
    ----------
    data   : raw extracted bytes
    lookup : HashLookup instance (optional) — used to resolve model path → asset_id

    Returns ActorAsset or None if not an actor.
    """
    # Find DAT1 magic
    dat1_off = data.find(b'\x31\x54\x41\x44')
    if dat1_off == -1:
        return None

    unk1 = struct.unpack_from('<I', data, dat1_off + 4)[0]
    if unk1 != ACTOR_TYPE:
        return None

    # Parse section count (u16 + u16 unknown_count)
    section_count, unknown_count = struct.unpack_from('<HH', data, dat1_off + 12)

    # String pool base
    pool_rel = 0x10 + section_count * 12 + unknown_count * 8
    pool_abs = dat1_off + pool_rel

    # Find first section offset to bound the pool
    first_off = None
    for i in range(section_count):
        base = dat1_off + 0x10 + i * 12
        _, sec_off, _ = struct.unpack_from('<III', data, base)
        if first_off is None or sec_off < first_off:
            first_off = sec_off

    pool_end = dat1_off + first_off if first_off else len(data)
    pool     = data[pool_abs:pool_end]

    # Extract all null-terminated strings from pool
    all_strings = _read_all_strings(pool)

    dat1_data = data[dat1_off:]
    dat1 = DAT1(dat1_data)
    header = dat1.get_section(TAG_ACTOR_HEADER)
    scene = dat1.get_section(TAG_ACTOR_SCENE)
    scene_type = None
    if scene is not None:
        if len(scene) < 0x80:
            raise ValueError('Truncated actor scene definition')
        size = struct.unpack_from('<I', scene, 0x7C)[0] & 0x7FFFFFFF
        if size < 0x80 or size > len(scene):
            raise ValueError('Invalid actor scene definition size')
        scene_type = scene[0x5F]
        scene = bytes(scene[:size])

    # The renderer uses this reference only when the scene factory selects a model.
    model_path = None
    if header is not None and scene_type == 0:
        if len(header) < 4:
            raise ValueError('Truncated actor header')
        path = dat1.get_string(struct.unpack_from('<I', header)[0])
        if path:
            model_path = path.replace('\\', '/').lower()

    # Resolve model path to asset ID via HashLookup
    model_asset_id = None
    if model_path and lookup and lookup.is_loaded():
        # Try with and without leading slash
        model_asset_id = lookup.asset_id(model_path)
        if model_asset_id is None:
            model_asset_id = lookup.asset_id(model_path.lstrip('/'))
        if model_asset_id is None:
            # Try with .model extension variants
            model_asset_id = lookup.asset_id(model_path.replace('/', '\\'))

    return ActorAsset(
        model_path=model_path,
        model_asset_id=model_asset_id,
        all_strings=all_strings,
        scene_type=scene_type, scene_data=scene or b'',
        components=parse_component_records(dat1_data, dat1.get_section(TAG_ACTOR_COMPONENTS) or b''),
    )


def _read_all_strings(pool: bytes) -> list:
    """Extract all null-terminated strings from a byte pool."""
    strings = []
    i = 0
    while i < len(pool):
        end = pool.find(b'\x00', i)
        if end == -1:
            end = len(pool)
        s = pool[i:end]
        try:
            text = s.decode('utf-8', errors='replace').strip()
            if text:
                strings.append(text)
        except Exception:
            pass
        i = end + 1
    return strings
