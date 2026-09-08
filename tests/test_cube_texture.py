"""Reject malformed cubes before handing their byte buffers to OpenGL."""
import pytest

from core.cube_texture import CubeMipChain, validate_cube_mips


def native_faces():
    return [[(4, 4, bytes(16)), (2, 2, bytes(16)), (1, 1, bytes(16))] for _ in range(6)]


def test_native_sub_four_pixel_mips_still_use_complete_blocks():
    assert validate_cube_mips(CubeMipChain(native_faces(), 'bc6u')) == 'bc6u'


def test_decoded_diagnostic_input_remains_supported():
    faces = [[(2, 2, bytes(24)), (1, 1, bytes(6))] for _ in range(6)]
    assert validate_cube_mips(faces) == 'rgb16f'


@pytest.mark.parametrize('damage', ['missing_face', 'missing_mip', 'bad_size', 'bad_dimensions'])
def test_incomplete_native_cubes_are_rejected(damage):
    faces = native_faces()
    if damage == 'missing_face': faces.pop()
    elif damage == 'missing_mip': faces[1].pop()
    elif damage == 'bad_size': faces[1][1] = (2, 2, bytes(8))
    elif damage == 'bad_dimensions': faces[1][1] = (1, 1, bytes(16))
    with pytest.raises(ValueError): validate_cube_mips(CubeMipChain(faces, 'bc6u'))


def test_unknown_encoding_is_rejected():
    with pytest.raises(ValueError, match='encoding'):
        validate_cube_mips(CubeMipChain(native_faces(), 'bc7'))
