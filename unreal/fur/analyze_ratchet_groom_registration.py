"""Measure captured groom roots against exact corresponding retail LOD0 surfaces."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.archive import TocParser
from core.asset_loader import load_asset
from core.hashes import HashLookup
from core.mesh import mesh_to_numpy


GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Ratchet & Clank - Rift Apart")
ASSET = 0xADE5909F821E9DDE
AUDIT = ROOT / "unreal/fur/recovered/native-strand-pipeline"
OUTPUT = ROOT / "unreal/fur/recovered/ratchet-groom-registration.json"
GROUPS = {
    "tail": ("ratchet-tail-guides-bind-visible.json", 12),
    "head-sparse": ("ratchet-head-sparse-guides-bind-visible.json", 26),
    "ears": ("ratchet-ear-guides-bind.json", 26),
}


toc = TocParser(str(GAME / "toc"))
toc.parse()
lookup = HashLookup()
lookup.load(str(ROOT / "hashes.txt"))
model = load_asset(toc.find_entry(ASSET), toc, lookup).model
if model is None:
    raise RuntimeError("Full Ratchet model could not be decoded")


def ue_positions(mesh_index):
    positions, _, _, _ = mesh_to_numpy(model, model.meshes[mesh_index])
    return positions[:, [0, 2, 1]].astype(np.float64) * 100.0


def nearest_vertex_distances(points, surface):
    result = []
    for start in range(0, len(points), 128):
        chunk = points[start:start + 128]
        squared = np.sum(
            (chunk[:, None, :] - surface[None, :, :]) ** 2, axis=2)
        result.extend(np.sqrt(np.min(squared, axis=1)).tolist())
    return np.asarray(result)


rows = []
for group, (filename, mesh_index) in GROUPS.items():
    data = json.loads((AUDIT / filename).read_text(encoding="utf-8"))
    roots = np.asarray(
        [guide["control_vertices_cm"][0] for guide in data["guides"]],
        dtype=np.float64)
    surface = ue_positions(mesh_index)
    distances = nearest_vertex_distances(roots, surface)
    rows.append({
        "group": group,
        "source_event": data["source_event"],
        "guides": len(roots),
        "surface_mesh_index": mesh_index,
        "surface_material": model.material_names[
            model.meshes[mesh_index].material_index],
        "surface_vertices": len(surface),
        "nearest_vertex_distance_cm": {
            "minimum": float(np.min(distances)),
            "median": float(np.median(distances)),
            "p95": float(np.percentile(distances, 95)),
            "maximum": float(np.max(distances)),
        },
        "root_bounds_min_cm": roots.min(axis=0).tolist(),
        "root_bounds_max_cm": roots.max(axis=0).tolist(),
        "surface_bounds_min_cm": surface.min(axis=0).tolist(),
        "surface_bounds_max_cm": surface.max(axis=0).tolist(),
    })

report = {
    "source_asset": f"{ASSET:016X}",
    "metric": "Euclidean distance from each guide root to the nearest LOD0 surface vertex; this is an upper bound on root-to-triangle distance.",
    "groups": rows,
}
OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
