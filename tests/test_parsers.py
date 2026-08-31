"""
tests/test_parsers.py
Unit tests for RCRA Forge using the new ALERT-accurate API.
Run with:  python tests/test_parsers.py
       or: python -m pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_sphere_model():
    from tests.dummy_data import make_sphere_model
    from core.mesh import mesh_to_numpy

    model = make_sphere_model(rings=8, sectors=12)
    assert len(model.meshes) == 1
    assert len(model.vertexes) > 0
    assert len(model.indexes)  > 0

    mesh = model.meshes[0]
    pos, nrm, uvs, idx = mesh_to_numpy(model, mesh)
    assert pos is not None and len(pos) > 0
    assert idx is not None and len(idx) > 0
    assert idx.max() < len(pos), "Index out of range"

    print(f"  ✓ Sphere: {len(pos)} verts, {len(idx)//3} tris")


def test_bc6_hdr_preview_mapping_preserves_range_and_alpha():
    import numpy as np
    from core.texture import _hdr_rgb_to_rgba8

    hdr = np.array([[[0.0, 1.0, 100.0], [4.0, 16.0, 64.0]]], dtype=np.float32)
    rgba = np.frombuffer(_hdr_rgb_to_rgba8(hdr), dtype=np.uint8).reshape(1, 2, 4)

    assert np.all(rgba[:, :, 3] == 255)
    assert rgba[0, 0, 0] == 0
    assert rgba[0, 0, 1] < rgba[0, 0, 2]
    assert rgba[0, 1, 0] < rgba[0, 1, 1] < rgba[0, 1, 2]


def test_bc1_srgb_texture_decodes_for_character_eyes_and_rgb_blend_rocks():
    import struct
    import numpy as np
    from core.texture import TextureAsset

    # One opaque-red BC1 block. Platformdino eye and rock base-colour maps use
    # the official DXGI BC1_UNORM_SRGB enum (0x48).
    block = struct.pack("<HHI", 0xF800, 0x0000, 0)
    texture = TextureAsset(
        sd_len=len(block), sd_width=4, sd_height=4, sd_mips=1,
        hd_len=0, hd_width=0, hd_height=0, hd_mips=1,
        fmt=0x48, array_size=1, planes=0, pixel_data=block,
    )

    rgba = texture.decode_to_rgba()

    assert texture.format_name == "BC1_UNORM_SRGB"
    assert rgba is not None
    pixels = np.frombuffer(rgba, dtype=np.uint8).reshape(4, 4, 4)
    assert np.all(pixels[:, :, 0] > 240)
    assert np.all(pixels[:, :, 1:3] < 16)
    assert np.all(pixels[:, :, 3] == 255)


def test_texture_parser_starts_pixels_after_prefixed_dat1_sections():
    import struct
    from core.texture import TAG_TEXTURE_HEADER, TextureParser

    payload = bytes.fromhex("0842c7395c7aadd5")
    section = bytearray(44)
    struct.pack_into('<II', section, 0, len(payload), 0)
    struct.pack_into('<HH', section, 8, 0, 0)
    struct.pack_into('<HH', section, 12, 4, 4)
    struct.pack_into('<HBB', section, 16, 1, 0, 0)
    struct.pack_into('<HQ', section, 20, 0x47, 0)
    struct.pack_into('<BBBB', section, 30, 1, 0, 1, 0)

    dat1_header = struct.pack('<IIIHH', 0x44415431, 0x5C4580B9, 100, 1, 0)
    directory = struct.pack('<III', TAG_TEXTURE_HEADER, 48, len(section))
    string_pool = b'Texture Built File\0\0'
    assert len(string_pool) == 20
    raw = b'P' * 36 + dat1_header + directory + string_pool + section + payload

    texture = TextureParser(raw).parse()

    assert texture.pixel_data == payload


def test_cube_model():
    from tests.dummy_data import make_cube_model
    from core.mesh import mesh_to_numpy

    model = make_cube_model()
    pos, nrm, uvs, idx = mesh_to_numpy(model, model.meshes[0])
    assert len(pos) == 24
    assert len(idx) == 36
    assert idx.max() < 24
    print(f"  ✓ Cube: {len(pos)} verts, {len(idx)//3} tris")


def test_texture_checkerboard():
    from tests.dummy_data import make_checkerboard_texture

    tex = make_checkerboard_texture(64)
    assert tex.width  == 64
    assert tex.height == 64
    assert len(tex.pixel_data) == 64 * 64 * 4
    assert tex.format_name == 'R8G8B8A8_UNORM'
    print(f"  ✓ Texture: {tex.width}×{tex.height} {tex.format_name}")


def test_texture_dds_export():
    from tests.dummy_data import make_checkerboard_texture

    tex = make_checkerboard_texture(32)
    dds = tex.to_dds_bytes()
    assert dds[:4] == b'DDS ', f"Bad DDS magic: {dds[:4]!r}"
    assert len(dds) > 128
    print(f"  ✓ DDS export: {len(dds):,} bytes")


def test_skeleton():
    from tests.dummy_data import make_demo_skeleton

    skel = make_demo_skeleton()
    assert len(skel.bones) == 5
    roots = skel.root_bones()
    assert len(roots) == 1
    assert roots[0].name == "root"

    world = skel.world_positions()
    assert len(world) == 5
    assert all(len(v) == 3 for v in world.values())
    print(f"  ✓ Skeleton: {len(skel.bones)} bones, root='{roots[0].name}'")


def test_dat1_parse():
    from tests.dummy_data import make_fake_toc_dat1
    from core.archive import DAT1, TAG_ARCHIVES, TAG_ASSET_IDS, TAG_SIZES

    dat1_bytes = make_fake_toc_dat1()
    dat1 = DAT1(dat1_bytes)

    assert dat1.get_section(TAG_ARCHIVES)  is not None, "Missing archives section"
    assert dat1.get_section(TAG_ASSET_IDS) is not None, "Missing asset IDs section"
    assert dat1.get_section(TAG_SIZES)     is not None, "Missing sizes section"
    print(f"  ✓ DAT1 parse: {len(dat1.sections)} sections found")


def test_gltf_export():
    import tempfile
    from tests.dummy_data import make_sphere_model
    from exporters.gltf_exporter import GltfExporter, ObjExporter

    model = make_sphere_model(rings=6, sectors=10)

    with tempfile.TemporaryDirectory() as tmpdir:
        glb_path = os.path.join(tmpdir, "sphere.glb")
        GltfExporter(model, "sphere").export_glb(glb_path)
        assert os.path.exists(glb_path)
        size = os.path.getsize(glb_path)
        assert size > 200, f"GLB too small: {size} bytes"
        # Verify GLB magic
        with open(glb_path, 'rb') as f:
            magic = f.read(4)
        assert magic == b'glTF', f"Bad GLB magic: {magic!r}"
        print(f"  ✓ GLB export: {size:,} bytes")

        obj_path = os.path.join(tmpdir, "sphere.obj")
        ObjExporter(model, "sphere").export(obj_path)
        assert os.path.exists(obj_path)
        content = open(obj_path).read()
        v_count = content.count('\nv ')
        f_count = content.count('\nf ')
        assert v_count > 0
        assert f_count > 0
        print(f"  ✓ OBJ export: {v_count} vertices, {f_count} faces")


def test_crc64_hash():
    from core.archive import crc64_hash
    # Known hash from ALERT: characters/npc/npc_zurkon_jr/npc_zurkon_jr.model
    # = 0x94A4B69B67D5CC42  (mentioned in the PR discussion)
    h = crc64_hash("characters/npc/npc_zurkon_jr/npc_zurkon_jr.model")
    assert h == 0x94A4B69B67D5CC42, f"CRC64 mismatch: {h:#018x}"
    print(f"  ✓ CRC64 hash: {h:#018x}")


def test_actor_dispatch_with_model_link():
    from core.archive import AssetEntry
    from core.asset_loader import load_asset
    from tests.dummy_data import make_actor_asset

    model_path = "characters/enemy/test/test_body.model"
    actor_data = make_actor_asset(model_path)

    class Lookup:
        def is_loaded(self): return True
        def name(self, _): return "test.actor"
        def asset_id(self, path):
            return 0x1122334455667788 if path.replace('\\', '/').lower() == model_path else None

    class Toc:
        def extract_asset(self, _): return actor_data

    entry = AssetEntry(0, 0x8877665544332211, 0, 0, len(actor_data))
    result = load_asset(entry, Toc(), Lookup())

    assert result.atype == 'actor'
    assert result.actor is not None
    assert result.actor.model_path == model_path
    assert result.actor.model_asset_id == 0x1122334455667788


def test_actor_dispatch_data_only():
    from core.archive import AssetEntry
    from core.asset_loader import load_asset
    from tests.dummy_data import make_actor_asset

    actor_data = make_actor_asset()

    class Lookup:
        def is_loaded(self): return True
        def name(self, _): return "navigation.actor"
        def asset_id(self, _): return None

    class Toc:
        def extract_asset(self, _): return actor_data

    entry = AssetEntry(0, 0x1234, 0, 0, len(actor_data))
    result = load_asset(entry, Toc(), Lookup())

    assert result.atype == 'actor'
    assert result.actor is not None
    assert result.actor.has_model is False


def run_all():
    tests = [
        test_sphere_model,
        test_cube_model,
        test_texture_checkerboard,
        test_texture_dds_export,
        test_skeleton,
        test_dat1_parse,
        test_gltf_export,
        test_crc64_hash,
    ]
    passed = failed = 0
    print("\n" + "━"*50)
    print("  RCRA Forge — Test Suite")
    print("━"*50 + "\n")
    for test in tests:
        try:
            print(f"[RUN] {test.__name__}")
            test()
            passed += 1
        except Exception as e:
            import traceback
            print(f"  ✗ FAILED: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{'━'*50}")
    print(f"  {passed}/{len(tests)} passed  {'🟢' if failed == 0 else '🔴'}")
    print("━"*50 + "\n")
    return failed == 0


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
