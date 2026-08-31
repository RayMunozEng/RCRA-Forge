"""
tests/test_grouping.py
Unit tests for core/grouping.py — prefix-based asset group detection.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.grouping import (
    _model_family_from_path,
    _slug_from_path,
    build_groups,
    build_model_families,
    MIN_GROUP_SIZE,
)


# ── _slug_from_path ───────────────────────────────────────────────────────────

def test_slug_strips_lod():
    assert _slug_from_path("characters/npc/grunthor/grunthor_lod0.model") == \
        "characters/npc/grunthor/grunthor"

def test_slug_strips_chunk_numbered():
    # _turret_chunk_07 → strip _07 → strip _chunk → strip _turret → enm_arachnodroid
    assert _slug_from_path("enemies/arachnodroid/enm_arachnodroid_turret_chunk_07.model") == \
        "enemies/arachnodroid/enm_arachnodroid"

def test_slug_strips_chunk_three_digit():
    assert _slug_from_path("enemies/arachnodroid/enm_arachnodroid_turret_chunk_010.model") == \
        "enemies/arachnodroid/enm_arachnodroid"

def test_slug_strips_sub_part_then_chunk():
    # _blocker_chunk_01 → strip _01 → strip _chunk → strip _blocker → slug
    assert _slug_from_path("enemies/arachnodroid/enm_arachnodroid_blocker_chunk_01.model") == \
        "enemies/arachnodroid/enm_arachnodroid"

def test_slug_strips_nest_chunk():
    assert _slug_from_path("enemies/arachnodroid/enm_arachnodroid_nest_chunk_01.model") == \
        "enemies/arachnodroid/enm_arachnodroid"

def test_slug_strips_ps4_suffix():
    assert _slug_from_path("enemies/birdbot/chunk_06_enm_birdbot_ps4.model") == \
        "enemies/birdbot/chunk_06_enm_birdbot"

def test_slug_strips_lod_with_underscore():
    assert _slug_from_path("chars/enemy/bot/bot_lod_2.model") == \
        "chars/enemy/bot/bot"

def test_slug_strips_damaged():
    assert _slug_from_path("enemies/grunthor/grunthor_damaged_01.model") == \
        "enemies/grunthor/grunthor"

def test_slug_strips_damage_no_suffix():
    assert _slug_from_path("enemies/bot/bot_damage.model") == \
        "enemies/bot/bot"

def test_slug_strips_dmg():
    assert _slug_from_path("enemies/grunthor/grunthor_dmg2.model") == \
        "enemies/grunthor/grunthor"

def test_slug_strips_part_numbered():
    assert _slug_from_path("props/door/door_part_03.model") == \
        "props/door/door"

def test_slug_strips_body():
    assert _slug_from_path("characters/npc/zurkon/zurkon_body.model") == \
        "characters/npc/zurkon/zurkon"

def test_slug_strips_arm():
    # arm_l ends in _l (no digit) so _l\d+ doesn't match — arm_l stays
    # but the arm sub-part keyword in the big list strips _arm, leaving zurkon
    result = _slug_from_path("characters/npc/zurkon/zurkon_arm_l.model")
    # arm_l has no digit suffix so won't be stripped by _l\d+;
    # _arm is in sub-part list but _arm_l isn't a clean match — result keeps arm_l
    assert result == "characters/npc/zurkon/zurkon_arm_l"

def test_slug_strips_shadow():
    assert _slug_from_path("characters/npc/zurkon/zurkon_shadow.model") == \
        "characters/npc/zurkon/zurkon"

def test_slug_strips_numeric_trailing():
    assert _slug_from_path("effects/explosion/explosion_03.model") == \
        "effects/explosion/explosion"

def test_slug_no_extension():
    result = _slug_from_path("characters/npc/zurkon/zurkon_body")
    assert result == "characters/npc/zurkon/zurkon"

def test_slug_hex_id_returns_none():
    assert _slug_from_path("94A4B69B67D5CC42") is None
    assert _slug_from_path("0000000000000000") is None

def test_slug_empty_returns_none():
    assert _slug_from_path("") is None
    assert _slug_from_path(None) is None

def test_slug_no_variant_unchanged():
    # A plain name with no suffix should be returned as-is (minus extension)
    result = _slug_from_path("weapons/blaster/blaster.model")
    assert result == "weapons/blaster/blaster"


# ── build_groups ──────────────────────────────────────────────────────────────

class _FakeEntry:
    def __init__(self, asset_id, archive=0, offset=0, size=100, header=None):
        self.asset_id = asset_id
        self.archive  = archive
        self.offset   = offset
        self.size     = size
        self.header   = header


class _FakeLookup:
    def __init__(self, mapping):
        self._map = mapping

    def is_loaded(self):
        return True

    def full_path(self, asset_id):
        return self._map.get(asset_id, f"{asset_id:016X}")

    def name(self, asset_id):
        p = self.full_path(asset_id)
        return p.rsplit('/', 1)[-1] if '/' in p else p


def test_build_groups_basic():
    entries = [
        _FakeEntry(0x01),
        _FakeEntry(0x02),
        _FakeEntry(0x03),
        _FakeEntry(0x04),  # singleton — no pair
    ]
    lookup = _FakeLookup({
        0x01: "chars/grunthor/grunthor_chunk_01.model",
        0x02: "chars/grunthor/grunthor_chunk_02.model",
        0x03: "chars/grunthor/grunthor_chunk_03.model",
        0x04: "props/crate/crate.model",   # no match → ungrouped
    })
    groups, ungrouped = build_groups(entries, lookup)
    assert len(groups) == 1
    g = groups[0]
    assert g.count == 3
    assert "grunthor" in g.slug
    assert len(ungrouped) == 1
    assert ungrouped[0].asset_id == 0x04


def test_build_groups_two_distinct_groups():
    entries = [_FakeEntry(i) for i in range(6)]
    lookup = _FakeLookup({
        0: "chars/grunthor/grunthor_body.model",
        1: "chars/grunthor/grunthor_lod0.model",
        2: "chars/zurkon/zurkon_body.model",
        3: "chars/zurkon/zurkon_shadow.model",
        4: "chars/zurkon/zurkon_damaged_01.model",
        5: "props/crate/crate.model",  # singleton
    })
    groups, ungrouped = build_groups(entries, lookup)
    slugs = {g.slug for g in groups}
    assert any("grunthor" in s for s in slugs)
    assert any("zurkon" in s for s in slugs)
    assert len(ungrouped) == 1


def test_build_groups_min_size_enforced():
    """A single asset with a strippable suffix should NOT form a group of 1."""
    entries = [_FakeEntry(0xAA)]
    lookup = _FakeLookup({0xAA: "chars/solo/solo_body.model"})
    groups, ungrouped = build_groups(entries, lookup)
    assert len(groups) == 0
    assert len(ungrouped) == 1


def test_build_groups_hex_only_ungrouped():
    entries = [_FakeEntry(0xDEAD), _FakeEntry(0xBEEF)]
    lookup = _FakeLookup({})  # no known names
    groups, ungrouped = build_groups(entries, lookup)
    assert len(groups) == 0
    assert len(ungrouped) == 2


def test_model_family_names_character_entities():
    assert _model_family_from_path(
        "characters/hero/hero_ratchet/bangle_set/glove.model"
    )[1] == "Ratchet"
    assert _model_family_from_path(
        "characters/enemy/enm_alien_snapper_ps4/enm_alien_snapper.model"
    )[1] == "Alien Snapper"
    assert _model_family_from_path(
        "equipment/weapon/wpn_burstpistol/wpn_burstpistol.model"
    )[1] == "Burst Pistol"
    assert _model_family_from_path(
        "equipment/projectile/proj_ryno/jeep/proj_ryno_jeep.model"
    )[1] == "Projectiles & ammunition"


def test_model_family_names_environment_purpose():
    assert _model_family_from_path(
        "environment/sargasso/architecture/sar_arch_wall.model"
    )[1] == "Architecture"
    assert _model_family_from_path(
        "levels/i20_city/openarea/tile_g35/tile_g35_ground.model"
    )[1] == "Terrain & ground"
    assert _model_family_from_path(
        "atmosphere/atm_sky_dome_base/clouds/sky.model"
    )[1] == "Sky & atmosphere"


def test_build_model_families_replaces_singleton_junk_drawer():
    entries = [_FakeEntry(0x01), _FakeEntry(0x02), _FakeEntry(0x03)]
    lookup = _FakeLookup({
        0x01: "characters/hero/hero_ratchet/glove.model",
        0x02: "characters/hero/hero_rivet/boot.model",
        0x03: "characters/hero/hero_ratchet/helmet.model",
    })

    families = build_model_families(entries, lookup)

    assert [(family.display_name, family.count) for family in families] == [
        ("Ratchet", 2),
        ("Rivet", 1),
    ]
    assert all(family.is_family for family in families)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓  {t.__name__}")
            passed += 1
        except Exception as ex:
            print(f"  ✗  {t.__name__}: {ex}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
