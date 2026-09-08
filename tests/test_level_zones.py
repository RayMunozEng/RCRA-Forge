"""Retail level catalogue dispatch and indexed names, independent of residency."""
import struct

import pytest

from core.archive import AssetEntry
from core.asset_loader import load_asset
from core.level import ASSET_TYPE_LEVEL_RCRA, LevelParser


def _level(*, declared_count=3, records=None, names=None, header_size=0x24):
    pool = b'first.zone\0second.zone\0third.zone\0'
    pool_start = 16 + 3*12
    header = bytearray(header_size)
    if len(header) >= 0x1C:
        struct.pack_into('<I', header, 0x18, declared_count)
    sections = {
        0x7CA7267D: header,
        0x4E023760: records if records is not None else (
            struct.pack('<QhH', 0x8000000000000001, 2, 17)
            + struct.pack('<QhH', 0x8000000000000002, 0, 23)
            + struct.pack('<QhH', 0x8000000000000003, -1, 0)),
        0x2BA33702: names if names is not None else struct.pack('<3I', pool_start, pool_start+11, pool_start+23),
    }
    directory, body = bytearray(), bytearray(pool)
    for tag, raw in sections.items():
        directory += struct.pack('<III', tag, pool_start+len(body), len(raw))
        body += raw
    return struct.pack('<IIIHH', 0x44415431, ASSET_TYPE_LEVEL_RCRA,
                       pool_start+len(body), 3, 0) + directory + body


def test_rcra_level_dispatch_uses_signed_name_index_with_dat1_origin():
    raw = bytes(36) + _level()
    class Toc:
        def extract_asset(self, _): return raw
    result = load_asset(AssetEntry(0, 99, 0, 0, len(raw)), Toc())
    assert result.atype == 'level' and result.error is None
    level = result.level
    assert level.zone_ids == [0x8000000000000001, 0x8000000000000002, 0x8000000000000003]
    assert [zone.name for zone in level.zones] == ['third.zone', 'first.zone', '']
    assert [zone.name_index for zone in level.zones] == [2, 0, -1]
    assert [zone.table_index for zone in level.zones] == [0, 1, 2]
    assert [zone.reserved for zone in level.zones] == [17, 23, 0]


@pytest.mark.parametrize('kwargs', [
    {'declared_count': 4}, {'records': b'\0'*35}, {'names': b'\0'*8}, {'header_size': 16},
])
def test_rcra_level_rejects_missing_or_truncated_catalogue_data(kwargs):
    with pytest.raises(ValueError):
        LevelParser(_level(**kwargs)).parse_info()
