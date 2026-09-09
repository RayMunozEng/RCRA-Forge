import struct

import pytest

from core.mesh import MeshDefinition, ModelParser


def test_decode_skin_batch_weights_uses_block_group_count_and_normalizes():
    mesh = MeshDefinition(
        mesh_id=1, vertex_start=0, vertex_count=3,
        index_start=0, index_count=3, flags=0x11, material_index=0,
        first_skin_batch=0, skin_batches_count=1, first_weight_index=0)
    # Stored group count is N-1. This block has two influences per vertex.
    raw = bytes([1, 1, 64, 2, 192, 3, 128, 3, 128, 0, 0, 4, 255])
    batches = [{"offset": 0, "vertex_count": 3, "first_vertex": 0}]

    result = ModelParser._decode_skin_batch_weights([mesh], batches, raw, 3)

    assert result[0] == pytest.approx([(2, .75), (1, .25)])
    assert result[1] == pytest.approx([(3, 1.0)])
    assert result[2][0] == pytest.approx((4, 1.0))


def test_decode_rigid_skin_batch():
    mesh = MeshDefinition(
        mesh_id=1, vertex_start=2, vertex_count=2,
        index_start=0, index_count=3, flags=0x11, material_index=0,
        first_skin_batch=0, skin_batches_count=1, first_weight_index=0)
    raw = bytes([0, 7, 9])
    batches = [{"offset": 0, "vertex_count": 2, "first_vertex": 0}]

    result = ModelParser._decode_skin_batch_weights([mesh], batches, raw, 4)

    assert result[:2] == [[], []]
    assert result[2:] == [[(7, 1.0)], [(9, 1.0)]]
