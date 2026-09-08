"""Address boundaries and analytically known packed-grid lighting."""
import numpy as np
import pytest

from core.light_grid import evaluate_light_grid, light_grid_addresses, parse_light_grid_data


def resources():
    # Low half: Y=63, both chroma codes 0 => RGB (1,0,3) at scale 1.
    # High half has Y=21 => one third that radiance. All six axes are uniform.
    words = np.full((4096, 4), np.uint32(63 | (21 << 16)))
    words[:, 3] = 63 | (10 << 10) | (32 << 14) | (32 << 20) | (32 << 26)
    return np.zeros(64**3, np.uint32), words


def evaluate(lookup, records, **kwargs):
    params = dict(world_point=(1.2, 2.3, 3.4), shading_normal=(1, 0, 0),
                  reflection=(-1, 0, 0), camera_position=(0, 0, 0),
                  bleed_reduction=.1, grid_intensity=2, ambient_fill=(.05, .1, .2),
                  default_sample=lambda direction, mip: (.2, .4, .6))
    params.update(kwargs)
    return evaluate_light_grid(lookup=lookup, data=records, **params)


def test_half_integer_centers_and_brick_offsets():
    indices, offsets, fraction = light_grid_addresses((16.5, 16.5, 16.5))
    np.testing.assert_array_equal(indices, [4161] * 8)
    np.testing.assert_array_equal(offsets, [0, 1, 16, 17, 256, 257, 272, 273])
    np.testing.assert_array_equal(fraction, [0, 0, 0])


def test_signed_brick_and_ring_wrap():
    indices, offsets, _ = light_grid_addresses((-.5, -.5, -.5))
    np.testing.assert_array_equal(indices, [262143, 262080, 258111, 258048, 4095, 4032, 63, 0])
    np.testing.assert_array_equal(offsets, [4095, 4080, 3855, 3840, 255, 240, 15, 0])
    wrapped = light_grid_addresses((1023.5, 1023.5, 1023.5))
    np.testing.assert_array_equal(wrapped[0], indices)
    np.testing.assert_array_equal(wrapped[1], offsets)


def test_uniform_directional_grid_separates_diffuse_from_reflection():
    lookup, records = resources()
    result = evaluate(lookup, records)
    np.testing.assert_allclose(result.diffuse, [2, .1, 6], rtol=2e-6)
    assert result.reflection == pytest.approx(1 / 3, rel=2e-6)
    assert result.fallback_weight == 0


@pytest.mark.parametrize('exponent', [0, 5, 10, 15])
def test_packed_scale_exponent(exponent):
    lookup, records = resources()
    records[:, 3] = (records[:, 3] & np.uint32(0xFFFFC3FF)) | np.uint32(exponent << 10)
    result = evaluate(lookup, records, grid_intensity=1, ambient_fill=(0, 0, 0))
    np.testing.assert_allclose(result.diffuse, np.array([1, 0, 3]) * 2.0**(exponent - 10), atol=1e-7, rtol=2e-6)
    assert result.reflection == pytest.approx(2.0**(exponent - 10) / 3, rel=2e-6)


@pytest.mark.parametrize('source', ['lookup', 'record', 'distance'])
def test_full_fallback_and_grid_intensity(source):
    lookup, records = resources()
    extras = {}
    if source == 'lookup':
        lookup[:] = 960
    elif source == 'record':
        records[:, 3] |= np.uint32(960)
    else:
        extras['camera_position'] = (600, 0, 0)
    result = evaluate(lookup, records, **extras)
    assert result.fallback_weight == pytest.approx(1, abs=2e-7)
    np.testing.assert_allclose(result.diffuse, [.4, .8, 1.2], atol=2e-6)
    assert result.reflection == pytest.approx(.4, abs=2e-6)


def test_minimum_corner_weight_keeps_closed_occlusion_finite():
    lookup, records = resources()
    records[:, 3] = 10 << 10
    result = evaluate(lookup, records, bleed_reduction=0)
    np.testing.assert_array_equal(result.corner_weights, [2**-18] * 8)
    np.testing.assert_allclose(result.diffuse, [2, .1, 6], rtol=2e-6)


def test_missing_data_records_fail_instead_of_sampling_unrelated_memory():
    lookup, records = resources()
    lookup[:] = 4096
    with pytest.raises(ValueError, match='missing data record'):
        evaluate(lookup, records)


def test_raw_grid_record_size():
    raw = np.arange(8, dtype='<u4').tobytes()
    np.testing.assert_array_equal(parse_light_grid_data(raw), [[0, 1, 2, 3], [4, 5, 6, 7]])
    with pytest.raises(ValueError, match='16-byte'):
        parse_light_grid_data(raw + b'\0')
