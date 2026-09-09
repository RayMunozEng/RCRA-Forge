"""Export the installed retail Ratchet LOD0 as a private skeletal FBX fixture."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import winreg


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.archive import TocParser
from core.asset_loader import load_asset, load_model_textures
from core.hashes import HashLookup
from exporters.fbx_exporter import FbxExporter
from exporters.gltf_exporter import GltfExporter
from exporters.texture_exporter import TextureExporter


ASSET = 0xADE5909F821E9DDE
OUTPUT = ROOT / "unreal/fur/recovered/ratchet-body"


def find_game_install() -> Path:
    candidates = []
    for hive, subkey, value in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath"),
    ):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                candidates.append(Path(winreg.QueryValueEx(key, value)[0]))
        except FileNotFoundError:
            pass
    if os.environ.get("ProgramFiles(x86)"):
        candidates.append(Path(os.environ["ProgramFiles(x86)"]) / "Steam")
    steam = next((path for path in candidates
                  if (path / "steamapps/libraryfolders.vdf").is_file()), None)
    if steam is None:
        raise FileNotFoundError("Steam libraryfolders.vdf was not found")
    text = (steam / "steamapps/libraryfolders.vdf").read_text(encoding="utf-8")
    libraries = [Path(value.replace(r"\\", "\\"))
                 for value in re.findall(r'"path"\s+"([^"]+)"', text)]
    if steam not in libraries:
        libraries.insert(0, steam)
    for library in libraries:
        manifest = library / "steamapps/appmanifest_1895880.acf"
        if not manifest.is_file():
            continue
        match = re.search(
            r'"installdir"\s+"([^"]+)"', manifest.read_text(encoding="utf-8"))
        if match:
            game = library / "steamapps/common" / match.group(1)
            if (game / "toc").is_file():
                return game
    raise FileNotFoundError("Steam app 1895880 is not installed")


game = find_game_install()
toc = TocParser(str(game / "toc"))
toc.parse()
lookup = HashLookup()
lookup.load(str(ROOT / "hashes.txt"))
entry = toc.find_entry(ASSET)
if entry is None:
    raise RuntimeError(f"Installed asset {ASSET:016X} was not found")
model = load_asset(entry, toc, lookup).model
if model is None:
    raise RuntimeError("Full Ratchet asset did not decode as a model")

OUTPUT.mkdir(parents=True, exist_ok=True)
decoded_textures = load_model_textures(model, entry, toc, lookup)
# Fur-control payloads may carry a fifth metadata item; TextureExporter needs
# the common decoded RGBA tuple only. Preserve every role while normalizing the
# private fixture at this boundary.


def rgba_payload(payload):
    rgba, width, height, _ = payload[:4]
    if len(rgba) == width * height * 4:
        return rgba
    metadata = payload[4] if len(payload) > 4 else {}
    blocks = metadata.get("compressed_mip0")
    dxgi = metadata.get("dxgi_format")
    bcn = {0x47: 1, 0x48: 1, 0x4A: 2, 0x4B: 2,
           0x4D: 3, 0x4E: 3, 0x4F: 4, 0x50: 4, 0x51: 4,
           0x53: 5, 0x54: 5, 0x62: 7, 0x63: 7}.get(dxgi)
    if blocks is None or bcn is None:
        return None
    import imagecodecs
    import numpy as np
    channels = {1: 4, 2: 4, 3: 4, 4: 1, 5: 2, 7: 4}[bcn]
    shape = (height, width, channels) if channels > 1 else (height, width)
    decoded = np.asarray(
        imagecodecs.bcn_decode(blocks, format=bcn, shape=shape),
        dtype=np.uint8)
    if decoded.ndim == 2:
        decoded = np.dstack((decoded, decoded, decoded,
                             np.full_like(decoded, 255)))
    elif decoded.shape[2] == 2:
        blue = np.zeros((height, width, 1), dtype=np.uint8)
        alpha = np.full((height, width, 1), 255, dtype=np.uint8)
        decoded = np.concatenate((decoded, blue, alpha), axis=2)
    return decoded.tobytes()


normalized = {
    material_index: {
        role: (rgba_payload(payload), *payload[1:4])
        for role, payload in roles.items()
    }
    for material_index, roles in decoded_textures.items()
}
invalid_texture_payloads = [
    {"material_index": material_index, "role": role, "texture": payload[3]}
    for material_index, roles in normalized.items()
    for role, payload in roles.items()
    if payload[0] is None
]
texture_payloads = {
    material_index: {
        role: payload
        for role, payload in roles.items()
        if payload[0] is not None
    }
    for material_index, roles in normalized.items()
}
material_names = {
    index: name for index, name in enumerate(model.material_names or [])
}
exported_textures = TextureExporter(
    texture_payloads, material_names, str(OUTPUT), "RatchetRetailLOD0"
).export("png")
fbx = OUTPUT / "RatchetRetailLOD0.fbx"
FbxExporter(model, "RatchetRetail", 0).export(str(fbx))
glb = OUTPUT / "RatchetRetailLOD0.glb"
GltfExporter(model, "RatchetRetail", 0).export_glb(str(glb))
report = {
    "asset_id": f"{ASSET:016X}",
    "source_path": model.source_path,
    "lod": 0,
    "mesh_count": sum(mesh.look_index == 0 and mesh.lod_level == 0 for mesh in model.meshes),
    "vertices": sum(mesh.vertex_count for mesh in model.meshes
                    if mesh.look_index == 0 and mesh.lod_level == 0),
    "joints": len(model.joints),
    "decoded_materials": len(texture_payloads),
    "decoded_texture_roles": sum(len(roles) for roles in texture_payloads.values()),
    "exported_texture_roles": sum(len(roles) for roles in exported_textures.values()),
    "invalid_texture_payloads": invalid_texture_payloads,
    "materials": {
        str(index): {
            "name": material_names.get(index, f"material_{index}"),
            "textures": {
                role: Path(texture.png_path).name
                for role, texture in roles.items()
                if texture.png_path
            },
        }
        for index, roles in exported_textures.items()
    },
    "fbx_file": fbx.name,
    "fbx_bytes": fbx.stat().st_size,
    "fbx_sha256": hashlib.sha256(fbx.read_bytes()).hexdigest(),
    "glb_file": glb.name,
    "glb_bytes": glb.stat().st_size,
    "glb_sha256": hashlib.sha256(glb.read_bytes()).hexdigest(),
    "scope": "Private validation fixture generated from the user's installed game; ignored by Git.",
}
(OUTPUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
