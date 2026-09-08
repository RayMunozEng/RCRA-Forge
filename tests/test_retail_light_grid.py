"""Fixed executable addresses must never be applied to an unverified build."""
import sys

import pytest

from core.retail_light_grid import RetailLightGridDecoder


@pytest.mark.skipif(sys.platform != 'win32', reason='Optional decoder uses the Windows CRT')
def test_retail_decoder_rejects_an_unverified_executable(tmp_path):
    pytest.importorskip('unicorn')
    executable = tmp_path / 'unknown-build.exe'
    executable.write_bytes(b'MZ' + bytes(510))
    with pytest.raises(ValueError, match='differs from the build'):
        RetailLightGridDecoder(executable)
