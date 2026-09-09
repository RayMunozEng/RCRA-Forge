"""Measure native tail control-map values at the exact LOD0 tail UVs."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import imagecodecs
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.archive import TocParser
from core.asset_loader import load_asset, load_model_textures
from core.hashes import HashLookup
from core.mesh import mesh_to_numpy


GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Ratchet & Clank - Rift Apart")
ASSET = 0xADE5909F821E9DDE
MATERIAL = 19
MESH = 12
OUTPUT = ROOT / "unreal/fur/recovered/ratchet-tail-shell-inputs.json"


def summarize(values):
    values = np.asarray(values, dtype=np.float64)
    return {
        "minimum": float(values.min()),
        "p05": float(np.percentile(values, 5)),
        "median": float(np.median(values)),
        "mean": float(values.mean()),
        "p95": float(np.percentile(values, 95)),
        "maximum": float(values.max()),
        "positive_fraction": float(np.mean(values > 0.0)),
    }


toc = TocParser(str(GAME / "toc"))
toc.parse()
lookup = HashLookup()
lookup.load(str(ROOT / "hashes.txt"))
entry = toc.find_entry(ASSET)
model = load_asset(entry, toc, lookup).model
textures = load_model_textures(model, entry, toc, lookup, material_indices=[MATERIAL])
_, _, uvs, indices = mesh_to_numpy(model, model.meshes[MESH])
def decoded(role):
    payload = textures[MATERIAL][role]
    width, height = payload[1:3]
    mip_width, mip_height, blocks = payload[4]["compressed_mips"][0]
    assert (width, height) == (mip_width, mip_height)
    pixels = imagecodecs.bcn_decode(
        blocks, format=7, shape=(height, width, 4)).astype(np.float32) / 255.0
    return pixels, width, height


control, width, height = decoded("fur_control")
base_color, base_width, base_height = decoded("base_color")


def sampled(flip_v):
    sample_uvs = np.mod(uvs, 1.0).copy()
    if flip_v:
        sample_uvs[:, 1] = 1.0 - sample_uvs[:, 1]
    x = np.minimum((sample_uvs[:, 0] * width).astype(np.int64), width - 1)
    y = np.minimum((sample_uvs[:, 1] * height).astype(np.int64), height - 1)
    control_values = control[y, x]
    base_x = np.minimum((sample_uvs[:, 0] * base_width).astype(np.int64), base_width - 1)
    base_y = np.minimum((sample_uvs[:, 1] * base_height).astype(np.int64), base_height - 1)
    base_values = base_color[base_y, base_x]
    result = {
        channel: summarize(control_values[:, channel_index])
        for channel, channel_index in (("groom_x", 0), ("groom_y", 1), ("length", 2), ("occlusion", 3))
    }
    result["base_color"] = {
        channel: summarize(base_values[:, channel_index])
        for channel, channel_index in (("red", 0), ("green", 1), ("blue", 2), ("alpha", 3))
    }
    return result


report = {
    "source_asset": f"{ASSET:016X}",
    "surface_mesh_index": MESH,
    "surface_material_index": MATERIAL,
    "vertices": int(len(uvs)),
    "triangles": int(len(indices) // 3),
    "uv_bounds": [uvs.min(axis=0).tolist(), uvs.max(axis=0).tolist()],
    "native_uv": sampled(False),
    "vertically_flipped_uv": sampled(True),
    "exporter_current_behavior": "TEXCOORD_0 stores (u, 1-v)",
}
OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
