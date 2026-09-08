"""Explicit cube pixel encoding shared by asset loading and GPU uploads."""
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CubeMipChain(Sequence):
    faces: Sequence
    encoding: str

    def __len__(self):
        return len(self.faces)

    def __getitem__(self, index):
        return self.faces[index]


def validate_cube_mips(cube):
    """Accept native BC6U or the existing decoded RGB16F diagnostic input."""
    encoding = cube.encoding if isinstance(cube, CubeMipChain) else 'rgb16f'
    if encoding not in ('bc6u', 'rgb16f'):
        raise ValueError(f'Unsupported Hair cube encoding: {encoding}')
    if len(cube) != 6 or not cube[0]:
        raise ValueError('Hair environment requires six cube faces')
    level_count = len(cube[0])
    base_width, base_height, _ = cube[0][0]
    if base_width <= 0 or base_width != base_height or base_width & (base_width-1):
        raise ValueError('Hair cube faces must be square powers of two')
    if level_count > base_width.bit_length():
        raise ValueError('Hair cube has too many mip levels')
    for face in cube:
        if len(face) != level_count:
            raise ValueError('Hair environment faces have unequal mip counts')
        for level, (width, height, pixels) in enumerate(face):
            side = max(1, base_width >> level)
            if (width, height) != (side, side):
                raise ValueError('Hair environment has incorrect mip dimensions')
            expected = max(1, (side+3)//4)**2*16 if encoding == 'bc6u' else side*side*6
            if len(pixels) != expected:
                raise ValueError(f'Hair {encoding} face needs {expected} bytes, got {len(pixels)}')
    return encoding
