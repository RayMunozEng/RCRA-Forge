"""Indexed retail model nodes: placements must survive mixed scene buffers."""
import struct

import numpy as np
import pytest

from core.level_assembler import _build_matrix
from core.zone import (
    TAG_MODEL_ASSETS, TAG_MODEL_INDICES, TAG_SCENE_NODES, ZoneParser,
)


MATRIX = (0, 2, 0, 0, 0, 0, 3, 0, -4, 0, 0, 0, 10, 20, 30, 1)
IDS = (0x8123456789ABCDEF, 0x923456789ABCDEF0, 0xA3456789ABCDEF01)


def _model(size=320, model_index=2, instance=0xFEDCBA9876543210):
    node = bytearray(size)
    struct.pack_into('<16f', node, 0, *MATRIX)
    struct.pack_into('<I', node, 0x5C, 0x112)
    struct.pack_into('<I', node, 0x7C, 0x80000000 | size)
    struct.pack_into('<I', node, 0xF0, 0xFFFFFFFF)  # Not the model index.
    struct.pack_into('<Qh', node, 0x100, instance, 0)
    struct.pack_into('<h', node, 0x110, model_index)
    return node


def _zone(scene=None, offsets=None, refs=None):
    # A non-model record separates two model nodes of different serialized sizes.
    if scene is None:
        scene = _model() + bytes(176) + _model(384, 0, 0xF123456789ABCDEF)
    paths = b'a.model\0b.model\0c.model\0'
    pool_start = 16 + 3 * 12
    if refs is None:
        refs = struct.pack('<3Q3I', *IDS, pool_start, pool_start+8, pool_start+16)
    sections = {
        TAG_SCENE_NODES: scene,
        TAG_MODEL_INDICES: struct.pack('<2I', 496, 0) if offsets is None else offsets,
        TAG_MODEL_ASSETS: refs,
    }
    payload = bytearray(paths)
    directory = bytearray()
    for tag, data in sections.items():
        directory.extend(struct.pack('<III', tag, pool_start+len(payload), len(data)))
        payload.extend(data)
    return (struct.pack('<IIIHH', 0x44415431, 0x1F390AA0,
                        pool_start+len(payload), 3, 0) + directory + payload)


def test_explicit_offsets_preserve_models_among_variable_sized_nodes():
    # Also exercise the installed asset's outer header.
    zone = ZoneParser(bytes(36) + _zone()).parse()
    assert zone.model_ids == list(IDS)  # Trailing name offsets are not IDs.
    assert zone.model_paths == ['a.model', 'b.model', 'c.model']
    assert zone.entry_count == 2
    first, second = zone.entries
    assert [entry.scene_offset for entry in zone.entries] == [496, 0]
    assert [len(entry.raw) for entry in zone.entries] == [384, 320]
    assert [entry.model_id for entry in zone.entries] == [IDS[0], IDS[2]]
    assert [entry.name for entry in zone.entries] == ['a', 'c']
    assert first.instance_id == 0xF123456789ABCDEF
    assert second.instance_id == 0xFEDCBA9876543210
    assert first.asset_id == 0  # Instance IDs are not loadable actor assets.
    assert first.position == (10, 20, 30)
    assert first.rot == (0, 2, 0, 0, 0, 3, -4, 0, 0)
    assert first.matrix == MATRIX
    assert first.flags == 0x112


def test_export_keeps_all_axes_scale_reflection_and_translation():
    entry = ZoneParser(_zone()).parse().entries[0]
    gltf_matrix = np.asarray(_build_matrix(entry)).reshape((4, 4), order='F')
    assert gltf_matrix @ (1, 2, 3, 1) == pytest.approx((-2, 22, 36, 1))
    assert np.linalg.det(gltf_matrix[:3, :3]) == pytest.approx(-24)


def test_empty_model_offset_table_does_not_guess_nodes_from_scene_size():
    assert ZoneParser(_zone(offsets=b'')).parse().entries == []


@pytest.mark.parametrize('offsets', [b'\0', struct.pack('<I', 10000)])
def test_invalid_model_offsets_fail_instead_of_realigning(offsets):
    with pytest.raises(ValueError, match='offsets|Truncated model node'):
        ZoneParser(_zone(offsets=offsets)).parse()


def test_model_reference_table_requires_complete_parallel_arrays():
    with pytest.raises(ValueError, match='reference table'):
        ZoneParser(_zone(refs=bytes(16))).parse()


@pytest.mark.parametrize('model_index', [-1, 3])
def test_model_table_index_is_signed_and_bounds_checked(model_index):
    with pytest.raises(ValueError, match='model table index'):
        ZoneParser(_zone(_model(model_index=model_index), struct.pack('<I', 0))).parse()


@pytest.mark.parametrize('size_flags', [0x80000080, 0x80010000])
def test_serialized_model_size_is_checked(size_flags):
    node = _model()
    struct.pack_into('<I', node, 0x7C, size_flags)
    with pytest.raises(ValueError, match='model node size'):
        ZoneParser(_zone(node, struct.pack('<I', 0))).parse()


def test_model_offsets_must_point_to_model_node_type():
    node = _model()
    node[0x5F] = 2
    with pytest.raises(ValueError, match='different scene node type'):
        ZoneParser(_zone(node, struct.pack('<I', 0))).parse()
