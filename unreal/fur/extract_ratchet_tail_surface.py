"""Extract installed Ratchet tail surface maps for private UE validation."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import imagecodecs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.archive import TocParser
from core.asset_loader import load_asset, load_model_textures
from core.hashes import HashLookup

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Ratchet & Clank - Rift Apart")
ASSET = 0xADE5909F821E9DDE
PARTS = {
    "head": {"material": 11, "mesh": 26},
    "limbs": {"material": 15, "mesh": 20},
    "tail": {"material": 19, "mesh": 12},
}
parser = argparse.ArgumentParser()
parser.add_argument("--part", choices=sorted(PARTS), default="tail")
args = parser.parse_args()
PART = args.part
MATERIAL = PARTS[PART]["material"]
MESH = PARTS[PART]["mesh"]
OUTPUT = ROOT / ("unreal/fur/recovered/ratchet-" + PART + "-surface")


def encode_dds(payload):
    pixels, width, height, _, metadata = payload
    mips = metadata.get("compressed_mips")
    source_format = metadata["dxgi_format"]
    if not mips:
        if len(pixels) != width * height * 4:
            raise RuntimeError("Decoded texture is not RGBA8")
        mips = [(width, height, pixels)]
        texture_format = 29 if source_format in (29, 72, 75, 78, 91, 93, 99) else 28
        representation = "Forge decoded RGBA8 mip zero"
    else:
        texture_format = source_format
        representation = "authored compressed mip chain"
    header = [124, 0xA1007, height, width, len(mips[0][2]), 0, len(mips)] + [0] * 11
    header += [32, 4, int.from_bytes(b"DX10", "little"), 0, 0, 0, 0, 0]
    header += [0x401008, 0, 0, 0, 0]
    data = b"DDS " + struct.pack("<31I", *header)
    data += struct.pack("<5I", texture_format, 3, 0, 1, 0)
    data += b"".join(mip[2] for mip in mips)
    return data, texture_format, representation, len(mips)


def encode_rgba_dds(payload):
    pixels, width, height, _, metadata = payload
    source_mips = metadata.get("compressed_mips")
    if source_mips:
        decoded_mips = [
            imagecodecs.bcn_decode(data, format=7, shape=(mip_height, mip_width, 4)).tobytes()
            for mip_width, mip_height, data in source_mips
        ]
    else:
        if len(pixels) != width * height * 4:
            raise RuntimeError("Decoded texture is not RGBA8")
        decoded_mips = [pixels]
    srgb = metadata["dxgi_format"] in (29, 72, 75, 78, 91, 93, 99)
    # Uncompressed RGBA uses DDSD_PITCH, not the compressed DDSD_LINEARSIZE
    # flag carried by the source BC7 container. This is the header accepted by
    # UE's TextureFactory and preserves the authored mip chain.
    header = [124, 0x2100F, height, width, width * 4, 0, len(decoded_mips)] + [0] * 11
    header += [32, 4, int.from_bytes(b"DX10", "little"), 0, 0, 0, 0, 0]
    header += [0x401008, 0, 0, 0, 0]
    data = b"DDS " + struct.pack("<31I", *header)
    data += struct.pack("<5I", 29 if srgb else 28, 3, 0, 1, 0)
    data += b"".join(decoded_mips)
    return data


toc = TocParser(str(GAME / "toc"))
toc.parse()
lookup = HashLookup()
lookup.load(str(ROOT / "hashes.txt"))
entry = toc.find_entry(ASSET)
model = load_asset(entry, toc, lookup).model
if model is None:
    raise RuntimeError("Full Ratchet model could not be decoded")
textures = load_model_textures(
    model, entry, toc, lookup, material_indices=[MATERIAL])
if MATERIAL not in textures:
    raise RuntimeError("Tail material textures were not decoded")

OUTPUT.mkdir(parents=True, exist_ok=True)
report = {
    "asset_id": f"{ASSET:016X}",
    "part": PART,
    "mesh_index": MESH,
    "material_index": MATERIAL,
    "material_name": model.material_names[MATERIAL],
    "textures": {},
}
for role, payload in textures[MATERIAL].items():
    if role not in ("base_color", "fur_control", "specular_color", "normal"):
        continue
    data, texture_format, representation, mip_count = encode_dds(payload)
    path = OUTPUT / (role + ".dds")
    path.write_bytes(data)
    rgba_data = encode_rgba_dds(payload)
    rgba_path = OUTPUT / (role + "-rgba.dds")
    rgba_path.write_bytes(rgba_data)
    metadata = payload[4]
    report["textures"][role] = {
        "name": payload[3],
        "size": [payload[1], payload[2]],
        "source_dxgi": metadata["dxgi_format"],
        "dds_dxgi": texture_format,
        "representation": representation,
        "mips": mip_count,
        "sha256": hashlib.sha256(data).hexdigest(),
        "rgba_dds": rgba_path.name,
        "rgba_sha256": hashlib.sha256(rgba_data).hexdigest(),
        "fur_settings": metadata.get("fur_settings"),
        "fur_layer_count": metadata.get("fur_layer_count"),
        "fur_lod_reduction": metadata.get("fur_lod_reduction"),
    }
(OUTPUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
