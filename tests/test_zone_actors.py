"""Actor references and component ranges must survive mixed scene ordering."""
import struct
from types import SimpleNamespace

import pytest

from core.actor import ACTOR_TYPE, parse_actor_asset
from core.level_assembler import LevelAssembler
from core.zone import (
    TAG_ACTOR_ASSETS, TAG_ACTOR_INSTANCES, TAG_COMPONENTS, TAG_ENTRY_INDEX,
    TAG_MODEL_ASSETS, TAG_MODEL_INDICES, TAG_SCENE_NODES, ZoneParser,
)


MATRIX = (0, 2, 0, 0, 0, 0, 3, 0, -4, 0, 0, 0, 10, 20, 30, 1)


def _node(size=320, kind=0, renderer_id=0xF000000000000099):
    raw = bytearray(size)
    struct.pack_into('<16f', raw, 0, *MATRIX)
    raw[0x5F] = kind
    struct.pack_into('<I', raw, 0x7C, size)
    if kind == 0:
        struct.pack_into('<Q', raw, 0x100, renderer_id)
    return raw


def _dat1(kind, sections, pool=b''):
    start = 16 + len(sections)*12
    directory = bytearray(); payload = bytearray(pool)
    for tag, value in sections.items():
        directory.extend(struct.pack('<III', tag, start+len(payload), len(value)))
        payload.extend(value)
    return struct.pack('<IIIHH', 0x44415431, kind, start+len(payload), len(sections), 0) + directory + payload


def _zone(mutate=None):
    texts = ['first', 'second', 'a.actor', 'b.actor', 'mesh.model', 'Component']
    pool = b''; names = {}
    for value in texts:
        names[value] = 16 + 8*12 + len(pool)
        pool += value.encode() + b'\0'
    scene = _node() + bytes(192) + _node(renderer_id=0xF000000000000001) + _node(237, 2)
    records = (struct.pack('<iiIiIHHQ', 1, 1, 512, 0, 2, 8, 17, 0xE000000000000001)
               + struct.pack('<iiIiIHHQ', -1, 0, 832, -1, 0, 4, 0, 0xE000000000000002))
    payload = b'inline-data'
    payload_offset = 16 + 8*12 + len(pool)
    components = (struct.pack('<Q6I', 0xD000000000000001, names['Component'], 0x12345678,
                              9, payload_offset, len(payload), 0xFFFFFFFF)
                  + struct.pack('<Q6I', 0xD000000000000002, names['Component'], 0x23456789,
                                3, 0xFFFFFFFF, 0, 42))
    sections = {
        0x76543210: payload, TAG_SCENE_NODES: scene,
        TAG_MODEL_INDICES: struct.pack('<I', 0),
        TAG_MODEL_ASSETS: struct.pack('<QI', 30, names['mesh.model']),
        TAG_ACTOR_INSTANCES: records,
        TAG_ACTOR_ASSETS: struct.pack('<2Q2I', 10, 20, names['a.actor'], names['b.actor']),
        TAG_COMPONENTS: components,
        TAG_ENTRY_INDEX: struct.pack('<2I', names['first'], names['second']),
    }
    if mutate: mutate(sections)
    return _dat1(0x1F390AA0, sections, pool)


def test_mixed_zone_uses_actor_reference_indices_and_separate_ids():
    zone = ZoneParser(bytes(36) + _zone()).parse()
    model, first, second = zone.entries
    assert [entry.index for entry in zone.entries] == [0, 1, 2]
    assert model.model_id == 30
    assert [entry.asset_id for entry in (first, second)] == [20, 10]
    assert zone.actor_ids == [10, 20]
    assert first.name == 'second' and second.name == ''
    assert first.actor_path == 'b.actor'
    assert first.instance_id == 0xE000000000000001
    assert first.renderer_instance_id == 0xF000000000000001
    assert second.renderer_instance_id == 0 and second.node_type == 2
    assert first.matrix == MATRIX and second.matrix == MATRIX
    assert first.scene_offset == 512 and second.scene_offset == 832
    assert (first.instance_flags, first.instance_reserved) == (8, 17)
    inline, default = first.components
    assert inline.data == b'inline-data'
    assert inline.name == 'Component' and inline.flags == 9
    assert inline.instance_id == 0xD000000000000001
    assert inline.type_id == 0x12345678
    assert default.data == b'' and default.data_offset == 0xFFFFFFFF
    assert default.reserved == 42
    assert not second.components


def test_unindexed_scene_bytes_are_not_guessed_to_be_actors():
    raw = _dat1(0x1F390AA0, {TAG_SCENE_NODES: bytes(176*4)})
    assert ZoneParser(raw).parse().entries == []


@pytest.mark.parametrize('field,value,match', [
    (0, 99, 'name index'), (4, -1, 'actor asset index'),
    (8, 90000, 'Truncated actor scene'), (12, -1, 'component range'),
    (16, 99, 'component range'),
])
def test_invalid_actor_references_are_rejected(field, value, match):
    def mutate(sections):
        records = bytearray(sections[TAG_ACTOR_INSTANCES])
        struct.pack_into('<i', records, field, value)
        sections[TAG_ACTOR_INSTANCES] = records
    with pytest.raises(ValueError, match=match):
        ZoneParser(_zone(mutate)).parse()


def test_component_payload_bounds_use_dat1_origin():
    def mutate(sections):
        records = bytearray(sections[TAG_COMPONENTS])
        struct.pack_into('<I', records, 0x14, 999999)
        sections[TAG_COMPONENTS] = records
    with pytest.raises(ValueError, match='component payload'):
        ZoneParser(_zone(mutate)).parse()


def _actor(kind=0):
    # A decoy model string precedes the actual, explicitly referenced model.
    pool = b'decoy.model\0chosen.model\0'
    sections = {0x32FAC8E0: struct.pack('<I', 16+3*12+12),
                0x364A6C7C: _node(kind=kind), 0x135832C8: b''}
    return _dat1(ACTOR_TYPE, sections, pool)


def test_actor_model_comes_from_header_reference_not_string_pool_order():
    actor = parse_actor_asset(bytes(36) + _actor())
    assert actor.model_path == 'chosen.model' and actor.scene_type == 0


def test_non_model_actor_does_not_take_a_model_string_from_its_pool():
    assert not parse_actor_asset(_actor(kind=2)).has_model


def test_assembler_matches_each_actor_and_keeps_mixed_entry_order():
    zone = ZoneParser(_zone()).parse()
    first = zone.entries[1]
    from dataclasses import replace
    # Actor 20 repeats. Actor 99 is absent; a volume must not borrow a mesh.
    zone.entries = [replace(first, asset_id=20), zone.entries[0],
                    replace(first, asset_id=10), replace(first, asset_id=20),
                    replace(first, asset_id=99), zone.entries[2]]
    toc = SimpleNamespace(find_entry=lambda value: None)
    assembler = LevelAssembler(toc, None)
    assembler._actor_cache = {
        10: SimpleNamespace(has_model=True, model_asset_id=100, model_path='a.model'),
        20: SimpleNamespace(has_model=True, model_asset_id=200, model_path='b.model'),
    }
    assembler._model_cache = {30: object(), 100: object(), 200: object()}
    progress = []
    result = assembler.assemble_zone(zone, progress_cb=lambda i,n: progress.append((i,n)))
    assert [node.model_asset_id for node in result.nodes] == [200, 30, 100, 200]
    assert [node.world_matrix for node in result.nodes] == [MATRIX]*4
    assert len(result.skipped) == 2
    assert 'actor not in TOC' in result.skipped[0][1]
    assert 'not a model' in result.skipped[1][1]
    assert progress == [(i,6) for i in range(1,7)]
