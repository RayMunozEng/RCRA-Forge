"""
core/grouping.py
Prefix-based asset grouping for RCRA Forge.

Enemy/character models in Rift Apart are split across many mesh assets that
share a common name prefix (the character "slug"), e.g.

    characters/enemies/npc_grunthor/npc_grunthor_body.model
    characters/enemies/npc_grunthor/npc_grunthor_arm_l.model
    characters/enemies/npc_grunthor/npc_grunthor_damaged_01.model
    characters/enemies/npc_grunthor/npc_grunthor_lod1.model

This module detects those groups from the hashes.txt names and exposes them
so the asset browser can show a "Groups" view and the exporter can batch them
into a single GLB with named mesh nodes.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

# Suffixes that are stripped when computing the "slug" (group key).
# Order matters — longer/more-specific patterns first.
_STRIP_PATTERNS = [
    # LOD levels:  _lod0  _lod_0  _l0  _l1  (must be followed by digit)
    r'_lod_?\d+$',
    r'_l\d+$',
    # Damage states: _damaged_01  _dmg0  _damage
    r'_damage[d]?(_\d+)?$',
    r'_dmg\d*$',
    # Chunk parts (very common in Rift Apart): _chunk_01  _chunk_010  _chunk07
    r'_chunk_?\d*$',
    # Split parts with numeric suffix: _part_01  _part1  _p01
    r'_part_?\d+$',
    r'_p\d{2,}$',
    # Sub-part qualifiers that precede a number: _blocker_01  _nest_01  _turret_01
    # These are stripped AFTER the number so compound suffixes collapse in two passes
    r'_(blocker|nest|turret|cannon|barrel|base|shield|wing|fin|claw|tail|spine|plate|panel|ring|joint|node|core|hull|door|hatch|vent|pipe|wire|cable|gear|wheel|tread|track|pod|arm|leg|head|torso|jaw|chest|back|hip|knee|elbow|wrist|ankle|foot|hand|finger|eye|ear|horn|antenna|rotor|blade|strut|frame|mount|socket|slot|port|cap|tip|nub|knob|bolt|pin|clip|hook|latch|hinge|valve|pump|tank|barrel2|drum|coil|spring|piston)$',
    # Generic trailing _NN counters (2+ digits only — avoid eating real names)
    r'_\d{2,}$',
    # Single digit trailing number attached directly: _1  _2  (only after other stripping)
    r'_\d$',
    # Common part names that are variants of the same model
    r'_(body|shadow|collision|col|coll|fx|effects?)$',
    r'_(hi|lo|mid|high|low|medium)$',
    # ps4/ps5/pc platform suffixes
    r'_(ps4|ps5|pc|art)$',
]
_STRIP_RE = re.compile('|'.join(f'(?:{p})' for p in _STRIP_PATTERNS), re.IGNORECASE)

# Minimum number of assets required to form a group (singleton "groups" are
# shown as normal ungrouped assets).
MIN_GROUP_SIZE = 2


@dataclass
class AssetGroup:
    """A collection of related assets that share a common name prefix."""
    slug: str                        # e.g. "npc_grunthor"
    display_name: str                # user-facing label, e.g. "npc_grunthor  (6)"
    directory: str                   # common directory prefix, e.g. "characters/enemies/"
    entries: list                    # list of AssetEntry objects
    asset_type: str = "MESH"         # dominant type (.model etc.)
    is_family: bool = False           # semantic fallback family, not filename variants

    @property
    def count(self) -> int:
        return len(self.entries)

    def __repr__(self):
        return f"<AssetGroup '{self.slug}' × {self.count}>"


def _slug_from_path(path: str) -> Optional[str]:
    """
    Derive a grouping slug from a full asset path.

    Examples
    --------
    'characters/npc/npc_grunthor/npc_grunthor_body.model'
        → 'characters/npc/npc_grunthor/npc_grunthor'

    'weapons/blaster/blaster_damaged_01.model'
        → 'weapons/blaster/blaster'

    Returns None if the path has no recognisable stem (hex-only ID).
    """
    if not path or re.fullmatch(r'[0-9A-Fa-f]{16}', path):
        return None

    # Strip extension
    if '.' in path.rsplit('/', 1)[-1]:
        path_no_ext = path.rsplit('.', 1)[0]
    else:
        path_no_ext = path

    # Strip trailing variant suffixes — iterate until stable so compound
    # suffixes like _blocker_chunk_07 collapse fully in multiple passes
    slug = path_no_ext
    for _ in range(6):   # max 6 passes, usually converges in 2-3
        new_slug = _STRIP_RE.sub('', slug).rstrip('_')
        if new_slug == slug:
            break
        slug = new_slug
    return slug if slug else None


def build_groups(entries, lookup) -> tuple[list[AssetGroup], list]:
    """
    Partition *entries* into AssetGroups (prefix-matched) and a leftover list
    of ungrouped AssetEntry objects.

    Parameters
    ----------
    entries : list[AssetEntry] or _LazyEntryList
    lookup  : HashLookup  (must be loaded)

    Returns
    -------
    (groups, ungrouped)
        groups     – list of AssetGroup, sorted by slug
        ungrouped  – list of AssetEntry that didn't form a group
    """
    from collections import defaultdict

    slug_map: dict[str, list] = defaultdict(list)
    no_slug: list = []

    entry_list = list(entries)   # materialise lazy list once

    for entry in entry_list:
        full_path = lookup.full_path(entry.asset_id) if lookup and lookup.is_loaded() else ""
        slug = _slug_from_path(full_path)
        if slug:
            slug_map[slug].append(entry)
        else:
            no_slug.append(entry)

    groups: list[AssetGroup] = []
    ungrouped: list = list(no_slug)

    for slug, members in sorted(slug_map.items()):
        if len(members) < MIN_GROUP_SIZE:
            ungrouped.extend(members)
            continue

        # Directory = everything before the last '/'
        directory = slug.rsplit('/', 1)[0] + '/' if '/' in slug else ''
        base_name = slug.rsplit('/', 1)[-1]

        g = AssetGroup(
            slug=slug,
            display_name=base_name,
            directory=directory,
            entries=members,
        )
        groups.append(g)

    return groups, ungrouped


_ENVIRONMENT_FAMILIES = (
    (('collision', '/nav/', 'navigation', 'blocker'), 'Collision & navigation'),
    (('atmosphere', '/sky/', 'sky_', 'cloud'), 'Sky & atmosphere'),
    (('vegetation', 'foliage', 'flora', '/tree', '/plant'), 'Vegetation'),
    (('/terrain/', '/ground/', 'landscape', '/tile_'), 'Terrain & ground'),
    (('/architecture/', '/arch_', 'building', '/structure/'), 'Architecture'),
    (('/lighting/', '/light/', 'lgt_'), 'Lighting'),
    (('/water/', 'ocean', 'river', 'waterfall'), 'Water'),
    (('/prop/', '/props/', '/object/', '/deco', 'set_dressing'), 'Props & set dressing'),
    (('/prefab', '/instance/', '/assembly/'), 'Prefabs & level assemblies'),
    (('background', 'scenery', 'setpiece', 'vista'), 'Background & set pieces'),
)


def _normalized_family_token(token: str) -> str:
    token = (token or '').casefold().strip('_')
    token = re.sub(r'^(?:hero|enm|npc|amb|civ|wpn|gdgt|veh)_', '', token)
    token = re.sub(r'_(?:ps4|ps5|pc|art)$', '', token)
    return token


_FAMILY_NAME_OVERRIDES = {
    'burstpistol': 'Burst Pistol',
    'buzzblades': 'Buzz Blades',
    'lightningrod': 'Lightning Rod',
    'magshield': 'Mag Shield',
    'mrfunguy': 'Mr. Fungi',
    'pixelizer': 'Pixelizer',
}


def _friendly_family_name(token: str) -> str:
    """Turn an internal entity folder such as enm_grunthor_ps4 into Grunthor."""
    token = _normalized_family_token(token)
    return _FAMILY_NAME_OVERRIDES.get(
        token, token.replace('_', ' ').strip().title() or 'Other models'
    )


def _model_family_from_path(path: str) -> tuple[str, str]:
    """Return a stable semantic family key and user-facing label for a model."""
    normalized = re.sub(r'/+', '/', (path or '').replace('\\', '/').casefold())
    parts = [part for part in normalized.split('/') if part]

    if len(parts) >= 3 and parts[0] == 'characters' and parts[1] in {
        'hero', 'enemy', 'enemies', 'npc', 'ambient', 'civilians', 'weapon', 'gadgets',
    }:
        entity = parts[2]
        return f"character:{_normalized_family_token(entity)}", _friendly_family_name(entity)

    if len(parts) >= 3 and parts[0] == 'equipment' and parts[1] in {'weapon', 'gadget'}:
        entity = parts[2]
        return f"equipment:{_normalized_family_token(entity)}", _friendly_family_name(entity)

    if len(parts) >= 2 and parts[0] == 'equipment':
        equipment_families = {
            'pickup': 'Pickups & collectibles',
            'projectile': 'Projectiles & ammunition',
            'attachment': 'Weapon attachments',
        }
        subtype = parts[1]
        label = equipment_families.get(subtype, _friendly_family_name(subtype))
        return f"equipment:{subtype}", label

    if 'vehicle' in parts:
        index = parts.index('vehicle')
        if index + 1 < len(parts):
            entity = parts[index + 1]
            return f"vehicle:{_normalized_family_token(entity)}", _friendly_family_name(entity)

    if normalized.startswith(('visualeffect/', 'visualeffects/', 'objects/fx/')):
        if '/weapon/' in normalized or '/wpn_' in normalized:
            return 'effects:weapons', 'Weapon effects'
        if '/characters/' in normalized:
            return 'effects:characters', 'Character effects'
        if '/environment/' in normalized:
            return 'effects:environment', 'Environment effects'
        return 'effects:global', 'Global effects'

    if normalized.startswith(('cinematics/', 'ui/', 'models/ui/')):
        if normalized.startswith(('ui/', 'models/ui/')):
            return 'cinematics:ui', 'Interface models'
        return 'cinematics:scenes', 'Cinematic scene pieces'

    environment_roots = (
        'environment/', 'levels/', 'procedural/', 'prefabs/', 'atmosphere/',
        'atmospheres/', 'instance/', 'objects/',
    )
    if normalized.startswith(environment_roots):
        for tokens, label in _ENVIRONMENT_FAMILIES:
            if any(token in normalized for token in tokens):
                return f"environment:{label.casefold()}", label
        return 'environment:scenery', 'Level structures & scenery'

    if normalized.startswith('legacy/'):
        return 'other:legacy', 'Legacy assets'
    if normalized.startswith(('test/', 'debug/')) or '/test/' in normalized:
        return 'other:test', 'Test & development models'
    if parts:
        label = _friendly_family_name(parts[0])
        return f"other:{parts[0]}", label
    return 'other:unknown', 'Other models'


def build_model_families(entries, lookup) -> list[AssetGroup]:
    """Group singleton model files into meaningful path-derived families."""
    from collections import defaultdict

    families = defaultdict(list)
    labels = {}
    for entry in entries:
        path = lookup.full_path(entry.asset_id) if lookup and lookup.is_loaded() else ''
        key, label = _model_family_from_path(path)
        families[key].append(entry)
        labels[key] = label

    result = []
    for key, members in families.items():
        result.append(AssetGroup(
            slug=key,
            display_name=labels[key],
            directory='',
            entries=members,
            is_family=True,
        ))
    return sorted(result, key=lambda group: group.display_name.casefold())


def filter_groups(groups: list[AssetGroup], text: str, ext_filter: Optional[str] = None,
                  lookup=None) -> list[AssetGroup]:
    """
    Return a subset of groups whose slug or member paths match *text*.
    Optionally restrict to members matching *ext_filter* (e.g. '.model').
    """
    text = text.lower().strip()
    result = []
    for g in groups:
        name_match = (not text) or (text in g.slug.lower()) or (text in g.display_name.lower())
        if not name_match:
            # Also check individual member paths
            if lookup and lookup.is_loaded():
                name_match = any(
                    text in lookup.full_path(e.asset_id).lower()
                    for e in g.entries
                )
        if not name_match:
            continue

        if ext_filter and ext_filter != 'All Types':
            members = [
                e for e in g.entries
                if (lookup.full_path(e.asset_id) if lookup and lookup.is_loaded() else '').endswith(ext_filter)
            ]
            if not members:
                continue
            g = AssetGroup(
                slug=g.slug,
                display_name=g.display_name,
                directory=g.directory,
                entries=members,
            )

        result.append(g)
    return result
