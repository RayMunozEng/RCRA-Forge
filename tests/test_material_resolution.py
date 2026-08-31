import struct

from core.asset_loader import _resolve_model_material_names
from core.hashes import HashLookup
from core.material import (
    BLIZAR_LAVA_FLOW_GRAPH,
    MaterialParser,
    TAG_FUR_MATERIAL,
    TAG_TEXTURE_TABLE,
    TextureSlot,
    _base_color_candidates,
    _infer_role,
)
from tests.dummy_data import make_cube_model


def test_model_viewport_uses_authoritative_material_path(monkeypatch):
    model = make_cube_model()
    model.meshes[0].material_index = 2
    model.material_names = ["cooked_internal_label"]
    material_section = bytearray(3 * 16)
    struct.pack_into("<QQ", material_section, 2 * 16, 0x1234, 0)

    class FakeDat1:
        sections = {0x3250BB80: memoryview(material_section)}

        @staticmethod
        def get_string(offset):
            assert offset == 0x1234
            return "material/environment/blizar_prime/ground/blz_gbl_lava_01_flow"

    monkeypatch.setattr("core.archive.DAT1", lambda _raw: FakeDat1())

    _resolve_model_material_names(model, b"model")

    assert model.material_names == [
        "cooked_internal_label",
        "",
        "material/environment/blizar_prime/ground/blz_gbl_lava_01_flow.material",
    ]


def _texture_table(paths):
    encoded = [path.encode("utf-8") + b"\x00" for path in paths]
    string_offsets = []
    cursor = 0
    for value in encoded:
        string_offsets.append(cursor)
        cursor += len(value)

    count = len(paths)
    entry_array_off = 32
    string_table_off = entry_array_off + count * 8
    result = bytearray(string_table_off + cursor)
    struct.pack_into("<I", result, 0x00, len(result))
    struct.pack_into("<I", result, 0x04, 0)  # unrelated binding count
    struct.pack_into("<I", result, 0x14, count)
    struct.pack_into("<I", result, 0x18, entry_array_off)
    struct.pack_into("<I", result, 0x1C, string_table_off)
    for index, string_offset in enumerate(string_offsets):
        struct.pack_into(
            "<II", result, entry_array_off + index * 8,
            string_offset, 0xA0000000 + index,
        )
    result[string_table_off:] = b"".join(encoded)
    return bytes(result)


def test_material_parser_uses_tagged_rcra_texture_table_and_correct_count():
    section = _texture_table([
        "characters\\hero\\hero_ratchet\\textures\\ratchet_c.texture",
        "characters/hero/hero_ratchet/textures/ratchet_n.texture",
        "textures//shared//paint_003_g.texture",
    ])
    parser = MaterialParser.__new__(MaterialParser)
    parser.dat1 = type("FakeDat1", (), {
        "sections": {
            0xBBFC8900: memoryview(b"compiled shader bytecode" * 1000),
            TAG_TEXTURE_TABLE: memoryview(section),
        }
    })()

    slots = parser._parse_texture_slots()

    assert [slot.role for slot in slots] == [
        "base_color", "normal", "specular_color",
    ]
    assert slots[0].path == "characters/hero/hero_ratchet/textures/ratchet_c.texture"
    assert slots[2].path == "textures/shared/paint_003_g.texture"


def test_material_parser_reads_shipped_fur_texture_bindings():
    paths = [
        "characters\\hero\\ratchet\\textures\\ratchet_head_c.texture",
        "characters/hero/ratchet/textures/ratchet_head_n.texture",
        "characters/hero/ratchet/textures/ratchet_head_g.texture",
        "characters/hero/ratchet/textures/ratchet_head_fur_control.texture",
    ]
    offsets = [0x45, 0x87, 0xC9, 0x10B]
    section = bytearray(52)
    struct.pack_into("<II7f", section, 0, 32, 0, 0.03, 16.0, 1.0, 1.0, 1.0, 0.1, 0.0)
    struct.pack_into("<4I", section, 36, *offsets)

    class FakeDat1:
        sections = {TAG_FUR_MATERIAL: memoryview(section)}

        @staticmethod
        def get_string(offset):
            return paths[offsets.index(offset)]

    parser = MaterialParser.__new__(MaterialParser)
    parser.dat1 = FakeDat1()

    slots = parser._parse_texture_slots()

    assert [slot.role for slot in slots] == [
        "base_color", "normal", "specular_color", "fur_control",
    ]
    assert slots[-1].path.endswith("ratchet_head_fur_control.texture")


def test_fur_control_role_is_recognized_before_generic_suffixes():
    assert _infer_role(
        "characters/hero/hero_rivet/textures/hero_rivet_head_fur_control.texture"
    ) == "fur_control"


def test_hash_reverse_lookup_normalizes_slashes_and_case():
    lookup = HashLookup()
    lookup._map = {
        0x1234: "characters/hero/hero_Ratchet/textures/ratchet_c.texture",
    }
    lookup._loaded = True

    assert lookup.asset_id(
        "\\characters\\hero//hero_ratchet\\textures//ratchet_c.texture"
    ) == 0x1234


def test_lava_effect_texture_roles_are_recognized():
    assert _infer_role("textures/sbs/rock/lava_rock_002_fx.texture") == "emissive"
    assert _infer_role(
        "textures/environment/ground/gnd_lava_rock_01/gnd_lava_rock_01_cma.texture"
    ) == "effect_mask"
    assert _infer_role("textures/effects/noise/fx_noisetile01.texture") == "noise"


def test_lava_rock_does_not_invent_a_sibling_base_color():
    slots = [
        TextureSlot(
            0,
            "textures/sbs/rock/lava_rock_002_fx.texture",
            0,
            "emissive",
        ),
        TextureSlot(
            1,
            "textures/environment/ground/gnd_lava_rock_01/gnd_lava_rock_01_cma.texture",
            0,
            "effect_mask",
        ),
        TextureSlot(
            2,
            "textures/sbs/rock/lava_rock_001_n.texture",
            0,
            "normal",
        ),
    ]

    candidates = _base_color_candidates(
        "material/environment/blizar_prime/ground/blz_gbl_lava_01_flow.material",
        slots,
        "environment/blizar_prime/rock/blz_lava_rock/blz_lava_rock_01.model",
    )

    assert candidates == []
    assert _base_color_candidates("material/props/ordinary_metal.material", slots) == []


def test_blizar_lava_graph_uses_exact_retail_binding_roles_and_defaults():
    slots = [
        TextureSlot(0, "textures/sbs/rock/lava_rock_001_n.texture", 0x2D487BD9, "normal"),
        TextureSlot(1, "textures/sbs/rock/lava_rock_002_n.texture", 0x3A336F9A, "normal"),
        TextureSlot(2, "textures/effects/noise/fx_noisetile01.texture", 0x8791CCB9, "noise"),
        TextureSlot(3, "textures/sbs/rock/lava_rock_002_fx.texture", 0xC97834C0, "emissive"),
        TextureSlot(4, "textures/environment/ground/gnd_lava_rock_01/gnd_lava_rock_01_cma.texture", 0xF0F50805, "effect_mask"),
    ]

    mapped = MaterialParser._apply_graph_bindings(BLIZAR_LAVA_FLOW_GRAPH, slots)

    assert [slot.role for slot in mapped] == [
        "retail_lava_normal_a",
        "retail_lava_normal_b",
        "retail_lava_noise",
        "retail_lava_color_a",
        "retail_lava_color_b",
        "retail_lava_mask_a",
        "retail_lava_mask_b",
    ]
    assert mapped[3].name == "lava_rock_002_fx"
    assert mapped[4].name == "gnd_lava_rock_01_cma"
    assert mapped[5].binding_hash == 0x0056CBD0
    assert mapped[6].binding_hash == 0x39DBF715
