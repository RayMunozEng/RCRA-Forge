import numpy as np
import pytest

from core.light_grid import light_grid_addresses
from core.light_grid_resources import (
    build_light_grid_resources, light_grid_lookup_address, pack_light_grid_lookup,
    should_replace_light_grid_brick,
)


def test_brick_lookup_matches_shader_corners_with_negative_coordinates():
    assert light_grid_lookup_address((-232, 8, 664)) == 167985
    lookup, offsets, _ = light_grid_addresses((-230.588, 9.146, 670.816))
    assert np.all(lookup == 167985)
    np.testing.assert_array_equal(offsets, [3720, 3721, 3736, 3737, 3976, 3977, 3992, 3993])
    assert light_grid_lookup_address((-232 + 1024, 8, 664)) == 167985


def test_fade_endpoints_and_unrounded_integer_metadata():
    assert pack_light_grid_lookup(17, 0) == (17 << 12) | 960
    assert pack_light_grid_lookup(17, 255) == 17 << 12
    # The runtime integer result retains bits discarded by Hair's 0x3FC mask.
    assert pack_light_grid_lookup(65535, 128) == (65535 << 12) | 478


def test_explicit_resources_preserve_records_and_provide_valid_fallback_address():
    records = np.arange(2 * 4096 * 4, dtype=np.uint32).reshape(2, 4096, 4)
    fallback = np.array([0x843F843F] * 3 + [0x83F81FC0], np.uint32)
    result = build_light_grid_resources([[-232, 8, 664], [-216, 8, 664]], records, [255, 128], fallback)
    np.testing.assert_array_equal(result.data[:8192], records.reshape(-1, 4))
    assert np.all(result.data[8192:] == fallback)
    assert result.lookup[167985] == 0
    assert result.lookup[167986] == 4096 | 478
    assert result.lookup[0] == 8192 | 960
    assert result.fallback_slot == 2


def test_ring_collision_requires_explicit_residency_resolution():
    with pytest.raises(ValueError, match='collide'):
        build_light_grid_resources([[8, 8, 8], [1032, 8, 8]], np.zeros((2, 4096, 4), np.uint32),
                                   [255, 255], np.zeros(4, np.uint32))


def test_resident_selection_uses_different_entry_and_retention_radii():
    assert not should_replace_light_grid_brick([8]*3, 1, [8]*3, 15, [418,8,8])
    assert should_replace_light_grid_brick([8]*3, 1, [8]*3, 15, [408,8,8])
    assert should_replace_light_grid_brick([1032,8,8], 15, [8]*3, 0, [8]*3)
    assert not should_replace_light_grid_brick([8]*3, 0, [1032,8,8], 15, [8]*3)
    assert should_replace_light_grid_brick([8]*3, 1, [8]*3, 2)
    assert not should_replace_light_grid_brick([8]*3, 2, [8]*3, 2)


@pytest.mark.parametrize('slot,fade', [(-1, 0), (65536, 255), (1, -1), (1, 256), (1, .5)])
def test_lookup_rejects_invalid_metadata(slot, fade):
    with pytest.raises(ValueError):
        pack_light_grid_lookup(slot, fade)
