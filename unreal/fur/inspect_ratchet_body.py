"""Inspect the installed full Ratchet model without exporting proprietary assets."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import winreg

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.archive import TocParser
from core.asset_loader import load_asset
from core.hashes import HashLookup
from core.mesh import mesh_to_numpy


ASSET = 0xADE5909F821E9DDE
OUTPUT = ROOT / "unreal/fur/recovered/ratchet-body-inspection.json"


def find_game_install() -> Path:
    steam_candidates = []
    for hive, subkey, value in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath"),
    ):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                steam_candidates.append(Path(winreg.QueryValueEx(key, value)[0]))
        except FileNotFoundError:
            pass
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if program_files_x86:
        steam_candidates.append(Path(program_files_x86) / "Steam")

    steam = next(
        (candidate for candidate in steam_candidates if (candidate / "steamapps/libraryfolders.vdf").is_file()),
        None,
    )
    if steam is None:
        raise FileNotFoundError("Steam libraryfolders.vdf was not found")

    library_vdf = steam / "steamapps/libraryfolders.vdf"
    libraries = [
        Path(value.replace(r"\\", "\\"))
        for value in re.findall(r'"path"\s+"([^"]+)"', library_vdf.read_text(encoding="utf-8"))
    ]
    if steam not in libraries:
        libraries.insert(0, steam)

    for library in libraries:
        manifest = library / "steamapps/appmanifest_1895880.acf"
        if not manifest.is_file():
            continue
        text = manifest.read_text(encoding="utf-8")
        match = re.search(r'"installdir"\s+"([^"]+)"', text)
        if match:
            game = library / "steamapps/common" / match.group(1)
            if (game / "toc").is_file():
                return game
    raise FileNotFoundError("Steam app 1895880 is not installed in any configured library")


GAME = find_game_install()

toc = TocParser(str(GAME / "toc"))
toc.parse()
lookup = HashLookup()
lookup.load(str(ROOT / "hashes.txt"))
entry = toc.find_entry(ASSET)
if entry is None:
    raise RuntimeError(f"Installed asset {ASSET:016X} was not found")
loaded = load_asset(entry, toc, lookup)
model = loaded.model
if model is None:
    raise RuntimeError("Full Ratchet asset did not decode as a model")

meshes = []
for index, mesh in enumerate(model.meshes):
    positions, _, _, indices = mesh_to_numpy(model, mesh)
    meshes.append({
        "index": index,
        "lod": mesh.lod_level,
        "look": mesh.look_index,
        "material_index": mesh.material_index,
        "material_name": model.material_names[mesh.material_index],
        "vertex_start": mesh.vertex_start,
        "flags": mesh.flags,
        "first_weight_index": mesh.first_weight_index,
        "first_skin_batch": mesh.first_skin_batch,
        "skin_batches_count": mesh.skin_batches_count,
        "decoded_skin_vertices": sum(
            bool(model.skin_weights[mesh.vertex_start + offset])
            for offset in range(mesh.vertex_count)),
        "vertices": len(positions),
        "triangles": len(indices) // 3,
        "bounds_min_m": positions.min(axis=0).tolist(),
        "bounds_max_m": positions.max(axis=0).tolist(),
    })

influences = [len(row) for row in model.rcra_weights]
report = {
    "asset_id": f"{ASSET:016X}",
    "source_path": model.source_path,
    "vertices": len(model.vertexes),
    "mesh_count": len(model.meshes),
    "lod0_mesh_count": sum(row["lod"] == 0 for row in meshes),
    "joints": len(model.joints),
    "joint_positions": len(model.joint_positions),
    "weight_rows": len(model.rcra_weights),
    "decoded_skin_weight_rows": sum(bool(row) for row in model.skin_weights),
    "skin_data_bytes": len(model.skin_data or b""),
    "skin_batches": model.skin_batches,
    "influences_per_vertex": {
        "minimum": min(influences) if influences else 0,
        "maximum": max(influences) if influences else 0,
        "mean": float(np.mean(influences)) if influences else 0,
    },
    "meshes": meshes,
}
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
