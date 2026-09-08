"""CPU checks for the recovered Hair key-light modulation boundary."""
import numpy as np
import pytest

from core.hair_key_modulation import (
    cloud_shadow_coordinates,
    key_gobo_coordinates,
    key_shadow_volume_range,
    resolve_cloud_shadow_sample,
    resolve_key_gobo_sample,
)


def test_cloud_shadow_projection_and_visibility_fade():
    transform = np.asarray((
        (1, 2, 0, 0),
        (0, 1, 3, 0),
        (2, 0, 1, 0),
    ), np.float32)
    coordinates = cloud_shadow_coordinates(
        (5, 7, 11), (2, 100, 3), transform, (1, .25, .1, 0))
    assert coordinates is not None
    np.testing.assert_allclose(
        coordinates.uv, (0.8275862, 0.7241379), rtol=0, atol=1e-7)
    assert resolve_cloud_shadow_sample(coordinates, .4) == pytest.approx(.55)


def test_disabled_cloud_shadow_is_unit_visibility():
    coordinates = cloud_shadow_coordinates(
        (0, 0, 0), (0, 0, 0), np.zeros((3, 4), np.float32),
        (0, .5, .1, 0))
    assert coordinates is None
    assert resolve_cloud_shadow_sample(coordinates, -100) == 1


@pytest.mark.parametrize('arguments,message', [
    (((0, 0), (0, 0, 0), np.zeros((3, 4)), (1, 0, 1, 0)), 'float3'),
    (((0, 0, 0), (0, 0, 0), np.zeros((4, 4)), (1, 0, 1, 0)), '3x4'),
    (((0, 0, 0), (0, 0, 0), np.zeros((3, 4)), (1, 2, 1, 0)), 'out of range'),
])
def test_cloud_shadow_boundary_rejects_invalid_inputs(arguments, message):
    with pytest.raises(ValueError, match=message):
        cloud_shadow_coordinates(*arguments)


def test_cloud_shadow_resolve_rejects_invalid_sample():
    coordinates = cloud_shadow_coordinates(
        (0, 0, 0), (0, 0, 0), np.zeros((3, 4), np.float32),
        (1, 0, 1, 0))
    with pytest.raises(ValueError, match='0..1'):
        resolve_cloud_shadow_sample(coordinates, 2)


def test_key_gobo_projection_and_rgb_modulation():
    transform = np.asarray((
        (1, 2, 0, 0),
        (0, 1, 3, 0),
        (2, 0, 1, 0),
    ), np.float32)
    coordinates = key_gobo_coordinates(
        (3, 7, 8), transform, (.1, .2, .25, .3))
    assert coordinates is not None
    np.testing.assert_allclose(coordinates.uv, (.15, .4), rtol=0, atol=2e-7)
    np.testing.assert_allclose(
        resolve_key_gobo_sample(coordinates, (2, 3, 4), (.5, .25, 1)),
        (1, .75, 4), rtol=0, atol=1e-7)


def test_disabled_key_gobo_preserves_radiance():
    coordinates = key_gobo_coordinates(
        (0, 0, 0), np.zeros((3, 4), np.float32), (0, 0, 0, 0))
    assert coordinates is None
    np.testing.assert_array_equal(
        resolve_key_gobo_sample(coordinates, (2, 3, 4), (-1, -1, -1)),
        (2, 3, 4))


def test_key_shadow_volume_range_uses_nonstochastic_cascade_level():
    constants = np.zeros((56, 4), np.float32)
    constants[14] = (1, 0, 2, 0)
    constants[15] = 1
    constants[24, 3] = 3.125
    selected = key_shadow_volume_range((4, 0, 0), constants)
    assert selected is not None
    assert (selected.cascade, selected.first, selected.count) == (2, 3, 8)
    constants[24, 3] = 3
    assert key_shadow_volume_range((4, 0, 0), constants) is None
    assert key_shadow_volume_range(
        (4, 0, 0), constants, enabled=False) is None
