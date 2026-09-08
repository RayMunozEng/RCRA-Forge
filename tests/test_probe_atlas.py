"""Verify the packed BC6 layout recovered from CS_CopyEnvProbe."""

from dataclasses import replace

import numpy as np
import pytest

from core.texture import DXGI_BC6U, TextureAsset


# Explicit source rectangles in 4x4 BC6 blocks, in D3D face order.
# These cover the six destination mips allocated at VA 0x141356790.
MIP_ORIGINS = (
    ((0, 0), (64, 0), (128, 0), (192, 0), (0, 64), (64, 64)),
    ((128, 64), (160, 64), (192, 64), (224, 64), (128, 96), (160, 96)),
    ((192, 96), (208, 96), (224, 96), (240, 96), (192, 112), (208, 112)),
    ((224, 112), (232, 112), (240, 112), (248, 112), (224, 120), (232, 120)),
    ((240, 120), (244, 120), (248, 120), (252, 120), (240, 124), (244, 124)),
    ((248, 124), (250, 124), (252, 124), (254, 124), (248, 126), (250, 126)),
)
MIP_SIDES = (256, 128, 64, 32, 16, 8)


@pytest.fixture
def atlas():
    # Distinct words detect row/face swaps, flips, and partial-block copies.
    payload = np.arange(128 * 256 * 4, dtype='<u4').tobytes()
    return TextureAsset(
        sd_len=len(payload), sd_width=1024, sd_height=512, sd_mips=1,
        hd_len=0, hd_width=1024, hd_height=512, hd_mips=1,
        fmt=DXGI_BC6U, array_size=1, planes=4, pixel_data=payload,
    )


def test_packed_probe_preserves_every_block_and_d3d_face_orientation(atlas):
    faces = atlas.compressed_cube_mips()
    source = np.frombuffer(atlas.pixel_data, dtype='<u4').reshape(128, 256, 4)
    visited = np.zeros((128, 256), dtype=np.uint8)

    assert atlas.is_packed_probe_atlas
    assert len(faces) == 6
    for face, levels in enumerate(faces):
        assert len(levels) == 6
        for mip, (width, height, payload) in enumerate(levels):
            side = MIP_SIDES[mip]
            block_side = side // 4
            x, y = MIP_ORIGINS[mip][face]
            assert (width, height) == (side, side)
            assert payload == source[y:y + block_side, x:x + block_side].tobytes()
            visited[y:y + block_side, x:x + block_side] += 1

    # Only the final 4x2 block rectangle is unused. No invented 4/2/1 mips.
    assert np.count_nonzero(visited) == 32760
    assert visited.max() == 1
    assert np.array_equal(np.argwhere(visited == 0), [
        [126, 252], [126, 253], [126, 254], [126, 255],
        [127, 252], [127, 253], [127, 254], [127, 255],
    ])


@pytest.mark.parametrize('byte_delta', [-16, -1, 1, 16])
def test_packed_probe_rejects_incomplete_or_extra_payload(atlas, byte_delta):
    payload = atlas.pixel_data[:byte_delta] if byte_delta < 0 else (
        atlas.pixel_data + bytes(byte_delta)
    )
    assert replace(atlas, pixel_data=payload).compressed_cube_mips() == []


@pytest.mark.parametrize('fields', [
    {'planes': 1},       # Same-size 2D HDR images are not probe atlases.
    {'array_size': 2},
    {'fmt': 0x60},       # The recovered copy path is unsigned BC6.
    {'sd_width': 512},
    {'sd_height': 1024},
    {'sd_mips': 2},
])
def test_packed_probe_requires_recovered_resource_signature(atlas, fields):
    other = replace(atlas, **fields)
    assert not other.is_packed_probe_atlas
    assert other.compressed_cube_mips() == []


def test_packed_probe_uses_active_hd_payload_when_present(atlas):
    streamed = replace(
        atlas, sd_width=16, sd_height=8, sd_len=128, pixel_data=bytes(128),
        hd_len=len(atlas.pixel_data), hd_pixel_data=atlas.pixel_data,
    )
    assert streamed.is_packed_probe_atlas
    assert streamed.compressed_cube_mips() == atlas.compressed_cube_mips()
