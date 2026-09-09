"""Decode the saved retail packed strand/CV records into a private UE guide fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "recovered" / "native-strand-pipeline"
REPORT = AUDIT / "report.json"
parser = argparse.ArgumentParser()
parser.add_argument(
    "--group", choices=("tail", "head-sparse", "empty-lod", "ears"),
    default="ears", help="Retail ModelStrand object to decode")
parser.add_argument(
    "--bind-pose", action="store_true",
    help="Decode the pre-skinning input buffers from the group's skinning event")
parser.add_argument(
    "--visible-from-lookup", action="store_true",
    help="Keep the exact authored guides emitted by the captured draw work queue")
args = parser.parse_args()
GROUPS = {
    "tail": {"draw": 24825, "skinning": 24743, "stem": "ratchet-tail-guides",
             "tess": 11, "children": 35, "draw_vertices": 713020},
    "head-sparse": {"draw": 24831, "skinning": 24748,
                    "stem": "ratchet-head-sparse-guides",
                    "tess": 11, "children": 11, "draw_vertices": 57596},
    "empty-lod": {"draw": 24838, "skinning": 24752,
                  "stem": "ratchet-empty-lod-guides",
                  "tess": 9, "children": 1, "draw_vertices": 0},
    "ears": {"draw": 24844, "skinning": 24756, "stem": "ratchet-ear-guides",
             "tess": 8, "children": 2, "draw_vertices": 147200},
}
group = GROUPS[args.group]
DRAW_EVENT = group["draw"]
EVENT = group["skinning"] if args.bind_pose else DRAW_EVENT
suffix = "-bind" if args.bind_pose else ""
if args.visible_from_lookup:
    suffix += "-visible"
OUTPUT = AUDIT / (group["stem"] + suffix + ".json")
METERS_PER_PACKED_UNIT = 0.000244140625


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signed16(value):
    return value - 65536 if value & 0x8000 else value


def oct_decode(x_byte, y_byte):
    x = x_byte * (2.0 / 255.0) - 1.0
    y = y_byte * (2.0 / 255.0) - 1.0
    z = 1.0 - abs(x) - abs(y)
    fold = max(-z, 0.0)
    x += -fold if x >= 0.0 else fold
    y += -fold if y >= 0.0 else fold
    length = math.sqrt(x * x + y * y + z * z)
    return [x / length, y / length, z / length]


def forge_to_ue(vector, scale):
    return [vector[0] * scale, vector[2] * scale, vector[1] * scale]


report = json.loads(REPORT.read_text(encoding="utf-8"))
if not report.get("completed"):
    raise RuntimeError("Native strand pipeline extraction is incomplete")
event_row = next(
    row
    for row in report["events"]
    if row["event"] == EVENT
    and row["stage"] == (
        "ShaderStage.Compute" if args.bind_pose else "ShaderStage.Vertex")
)


def binding(name):
    return next(
        item for item in event_row["read_only"] if item["name"] == name
    )


strand_binding = binding("g_StrandBuffer")
cv_binding = binding("g_StrandCVBuffer")
strand_path = AUDIT / strand_binding["data"]["file"]
cv_path = AUDIT / cv_binding["data"]["file"]
if sha256(strand_path) != strand_binding["data"]["sha256"]:
    raise RuntimeError("Strand buffer hash mismatch")
if sha256(cv_path) != cv_binding["data"]["sha256"]:
    raise RuntimeError("CV buffer hash mismatch")
strand_data = strand_path.read_bytes()
cv_data = cv_path.read_bytes()

block = next(
    block
    for block in event_row["constant_blocks"]
    if block["name"] == "ModelStrandCBuffer"
)
cbuffer = (AUDIT / block["data"]["file"]).read_bytes()
start, count = struct.unpack_from("<II", cbuffer, 56)
meters_per_unit = struct.unpack_from("<f", cbuffer, 32)[0]
if meters_per_unit != METERS_PER_PACKED_UNIT:
    raise RuntimeError(f"Unexpected packed position scale: {meters_per_unit}")

strand_indices = list(range(start, start + count))
visible_local_indices = None
if args.visible_from_lookup:
    draw_row = next(
        row for row in report["events"]
        if row["event"] == DRAW_EVENT and row["stage"] == "ShaderStage.Vertex")
    lookup = next(item for item in draw_row["read_only"] if item["name"] == "g_StrandLookup")
    lookup_path = AUDIT / lookup["data"]["file"]
    if sha256(lookup_path) != lookup["data"]["sha256"]:
        raise RuntimeError("Strand lookup buffer hash mismatch")
    vertices_per_guide = 4 * group["tess"] * group["children"]
    if group["draw_vertices"] % vertices_per_guide:
        raise RuntimeError("Indirect draw count is not guide-aligned")
    visible_count = group["draw_vertices"] // vertices_per_guide
    raw = lookup_path.read_bytes()
    offsets = struct.unpack_from(f"<{visible_count}I", raw)
    if any(value % vertices_per_guide for value in offsets):
        raise RuntimeError("Strand lookup contains a misaligned vertex offset")
    visible_local_indices = [value // vertices_per_guide for value in offsets]
    if any(value >= count for value in visible_local_indices):
        raise RuntimeError("Strand lookup guide index exceeds the captured range")
    strand_indices = [start + value for value in visible_local_indices]

guides = []
all_points = []
invalid = 0
for strand_index in strand_indices:
    word0, word1, word2 = struct.unpack_from("<III", strand_data, strand_index * 12)
    if word0 & 0x80000000:
        invalid += 1
        continue
    cv_count = (word0 >> 24) & 0x7F
    cv_start = word0 & 0x00FFFFFF
    if not 2 <= cv_count <= 20:
        raise RuntimeError(
            f"Invalid CV count {cv_count} at strand {strand_index}"
        )
    points = []
    for cv_index in range(cv_start, cv_start + cv_count):
        packed_xy, packed_z_flags = struct.unpack_from("<II", cv_data, cv_index * 8)
        packed = [
            signed16(packed_xy & 0xFFFF),
            signed16((packed_xy >> 16) & 0xFFFF),
            signed16(packed_z_flags & 0xFFFF),
        ]
        point = forge_to_ue(packed, meters_per_unit * 100.0)
        points.append(point)
        all_points.append(point)
    normal = forge_to_ue(oct_decode(word2 & 0xFF, (word2 >> 8) & 0xFF), 1.0)
    frame_y = forge_to_ue(
        oct_decode((word2 >> 16) & 0xFF, (word2 >> 24) & 0xFF), 1.0)
    guides.append(
        {
            "source_strand_index": strand_index,
            "control_vertices_cm": points,
            "root_normal": normal,
            "root_frame_y": frame_y,
            "packed_uv_or_seed": [
                (word1 & 0xFFFF) / 65535.0,
                ((word1 >> 16) & 0xFFFF) / 65535.0,
            ],
        }
    )

axes = list(zip(*all_points))
output = {
    "schema_version": 1,
    "group": args.group,
    "source_capture_sha256": report["capture_sha256"],
    "source_event": DRAW_EVENT,
    "source_buffer_event": EVENT,
    "coordinate_space": "pre-skinning bind pose" if args.bind_pose else "post-skinning gameplay pose",
    "source_strand_buffer_sha256": sha256(strand_path),
    "source_cv_buffer_sha256": sha256(cv_path),
    "conversion": "Forge packed meters (x,y,z) -> UE centimeters (100x,100z,100y)",
    "strand_range": {"start": start, "count": count, "invalid": invalid},
    "captured_visible_local_indices": visible_local_indices,
    "captured_visible_unique_guides": (
        len(set(visible_local_indices)) if visible_local_indices is not None else None),
    "captured_visible_duplicate_entries": (
        len(visible_local_indices) - len(set(visible_local_indices))
        if visible_local_indices is not None else None),
    "valid_guides": len(guides),
    "control_vertices": len(all_points),
    "bounds_min_cm": [min(axis) for axis in axes],
    "bounds_max_cm": [max(axis) for axis in axes],
    "guides": guides,
}
OUTPUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in output.items() if key != "guides"}, indent=2))
