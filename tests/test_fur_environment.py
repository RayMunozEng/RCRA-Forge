"""Keep app and verification captures on the same recovered Hair resources."""

import hashlib
from types import SimpleNamespace

import pytest

from core.asset_loader import load_fur_environment
from core.fur_resources import DEFAULT_HAIR_ENVIRONMENT_ASSET_ID


def test_non_fur_models_do_not_extract_environment():
    # A TOC is deliberately unnecessary until the material has a control map.
    assert load_fur_environment({0: {'base_color': object()}}, None) is None
    assert load_fur_environment({}, None) is None


def test_fur_environment_uses_verified_probe_and_exact_brdf(monkeypatch):
    entry = object()
    faces = [[(1, 1, bytes(16))] for _ in range(6)]
    requested_ids = []

    def find_entry(asset_id):
        requested_ids.append(asset_id)
        return entry

    def extract_asset(requested_entry):
        assert requested_entry is entry
        return b'installed probe'

    def parse_texture(raw):
        assert raw == b'installed probe'
        return SimpleNamespace(parse=lambda: SimpleNamespace(
            fmt=0x5F,
            compressed_cube_mips=lambda: faces,
        ))

    monkeypatch.setattr('core.texture.TextureParser', parse_texture)
    toc = SimpleNamespace(find_entry=find_entry, extract_asset=extract_asset)

    cube, brdf, size = load_fur_environment({2: {'fur_control': object()}}, toc)

    assert requested_ids == [DEFAULT_HAIR_ENVIRONMENT_ASSET_ID]
    assert cube.faces is faces
    assert cube.encoding == 'bc6u'
    assert size == (64, 64)
    assert hashlib.sha256(brdf).hexdigest() == (
        '4fa9755a296ec4c8c11d19e62598217eedd8625814bb75128c947ca325038672'
    )


def test_missing_fur_environment_is_not_silently_accepted():
    toc = SimpleNamespace(find_entry=lambda _asset_id: None)
    with pytest.raises(RuntimeError, match='absent from TOC'):
        load_fur_environment({2: {'fur_control': object()}}, toc)


def test_undecodable_fur_environment_is_not_silently_accepted(monkeypatch):
    toc = SimpleNamespace(
        find_entry=lambda _asset_id: object(),
        extract_asset=lambda _entry: b'invalid cube',
    )
    monkeypatch.setattr('core.texture.TextureParser', lambda _raw: SimpleNamespace(
        parse=lambda: SimpleNamespace(fmt=0x5F, compressed_cube_mips=lambda: []),
    ))
    with pytest.raises(RuntimeError, match='no BC6 cube payload'):
        load_fur_environment({2: {'fur_control': object()}}, toc)
