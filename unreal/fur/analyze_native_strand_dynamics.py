"""Measure exact retail wind displacement between skinning and wind outputs."""

import hashlib
import argparse
import json
import math
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "recovered/native-strand-pipeline"
parser = argparse.ArgumentParser()
parser.add_argument("--group", choices=("tail", "head-sparse", "empty-lod", "ears"),
                    default="ears")
args = parser.parse_args()
GROUPS = {
    "tail": (24743, 24762, 0, 633),
    "head-sparse": (24748, 24767, 965, 2109),
    "empty-lod": (24752, 24771, 0, 965),
    "ears": (24756, 24775, 3074, 2781),
}
SKIN_EVENT, WIND_EVENT, START, COUNT = GROUPS[args.group]
STRANDS = SOURCE / f"e{SKIN_EVENT}-Compute-u2-StrandBufferOutput.bin"
SKINNED = SOURCE / f"e{SKIN_EVENT}-Compute-u0-StrandCVBufferOutput.bin"
WINDBLOWN = SOURCE / f"e{WIND_EVENT}-Compute-u0-StrandCVBufferOutput.bin"
OUTPUT = SOURCE / f"dynamics-analysis-{args.group}.json"
CM_PER_PACKED_UNIT = 0.0244140625


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signed16(value):
    return value - 65536 if value & 0x8000 else value


strand_data = STRANDS.read_bytes()
indices = []
for strand in range(START, START + COUNT):
    word = struct.unpack_from("<I", strand_data, strand * 12)[0]
    cv_start = word & 0xFFFFFF
    cv_count = (word >> 24) & 0x7F
    indices.extend(range(cv_start, cv_start + cv_count))
if not indices or len(set(indices)) != len(indices):
    raise RuntimeError("Unexpected control-vertex ranges")


def decode(data, index):
    xy, z_flags = struct.unpack_from("<II", data, index * 8)
    forge = (
        signed16(xy & 0xFFFF),
        signed16((xy >> 16) & 0xFFFF),
        signed16(z_flags & 0xFFFF),
    )
    return (
        forge[0] * CM_PER_PACKED_UNIT,
        forge[2] * CM_PER_PACKED_UNIT,
        forge[1] * CM_PER_PACKED_UNIT,
    )


skinned = SKINNED.read_bytes()
windblown = WINDBLOWN.read_bytes()
distances = []
axis_sum = [0.0, 0.0, 0.0]
for index in indices:
    before = decode(skinned, index)
    after = decode(windblown, index)
    delta = tuple(b - a for a, b in zip(before, after))
    distances.append(math.sqrt(sum(value * value for value in delta)))
    for axis, value in enumerate(delta):
        axis_sum[axis] += value
distances.sort()


def percentile(fraction):
    position = fraction * (len(distances) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    blend = position - low
    return distances[low] * (1.0 - blend) + distances[high] * blend


report = {
    "source_capture_sha256": "c5304097273a3863409956c0e014d48ac390b305f391c6543787097fd6b9647e",
    "group": args.group,
    "skinning_event": SKIN_EVENT,
    "wind_event": WIND_EVENT,
    "strand_start": START,
    "strand_count": COUNT,
    "control_vertices": len(indices),
    "inputs": {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in (STRANDS, SKINNED, WINDBLOWN)
    },
    "displacement_cm": {
        "minimum": distances[0],
        "mean": sum(distances) / len(distances),
        "p50": percentile(0.50),
        "p90": percentile(0.90),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
        "maximum": distances[-1],
        "mean_ue_xyz": [value / len(indices) for value in axis_sum],
    },
}
report["passed"] = report["control_vertices"] == len(indices)
OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
if not report["passed"]:
    raise SystemExit(1)
