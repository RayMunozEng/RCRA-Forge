"""Decode and correlate the bounded retail ModelStrand pipeline extraction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "recovered" / "native-strand-pipeline"
SOURCE = AUDIT / "report.json"
OUTPUT = AUDIT / "analysis.json"
DRAW_EVENTS = (24825, 24831, 24838, 24844)
COMPUTE_EVENTS = {
    "apply_skinning": (24743, 24748, 24752, 24756),
    "simulate_wind": (24762, 24767, 24771, 24775),
    "init_work_queue": (24781, 24784, 24787, 24790),
    "indirect_args": (24796, 24801, 24806, 24811),
}


def model_strand_block(event):
    return next(
        block
        for block in event["constant_blocks"]
        if block["name"] == "ModelStrandCBuffer"
    )


def decode_value(raw, member):
    type_info = member["type"]
    name = type_info["name"]
    if name.startswith("float"):
        code = "f"
    elif name.startswith("uint"):
        code = "I"
    elif name.startswith("int"):
        code = "i"
    else:
        return {"unsupported_type": name}
    lanes = max(1, int(type_info["rows"]) * int(type_info["columns"]))
    elements = max(1, int(type_info["elements"]))
    stride = int(type_info["arrayByteStride"]) if elements > 1 else lanes * 4
    values = []
    for index in range(elements):
        offset = int(member["byteOffset"]) + index * stride
        value = list(struct.unpack_from("<" + code * lanes, raw, offset))
        values.append(value[0] if lanes == 1 else value)
    return values[0] if elements == 1 else values


def compact(name, value):
    if name not in (
        "m_SkinVertexOffsetSubsetRemap",
        "m_BaseVertexOffsetSubsetRemap",
    ):
        return value
    flat = [component for vector in value for component in vector]
    packed = b"".join(struct.pack("<i", component) for component in flat)
    return {
        "count": len(flat),
        "min": min(flat),
        "max": max(flat),
        "unique_count": len(set(flat)),
        "first_16": flat[:16],
        "last_16": flat[-16:],
        "sha256": hashlib.sha256(packed).hexdigest(),
    }


def resources(event, key):
    return {
        item["name"]: {
            "resource": item["descriptor"]["resource"],
            "resource_name": item["resource_name"],
            "byte_offset": item["descriptor"]["byteOffset"],
            "byte_size": item["descriptor"]["byteSize"],
            "element_byte_size": item["descriptor"]["elementByteSize"],
            "fixed_bind_number": item["fixed_bind_number"],
        }
        for item in event[key]
    }


source = json.loads(SOURCE.read_text(encoding="utf-8"))
if not source.get("completed") or len(source.get("events", ())) != 24:
    raise RuntimeError("Native strand extraction is incomplete")
events = {(row["event"], row["stage"]): row for row in source["events"]}

analysis = {
    "schema_version": 1,
    "source": str(SOURCE),
    "capture_sha256": source["capture_sha256"],
    "objects": [],
}

for ordinal, draw_event in enumerate(DRAW_EVENTS):
    vertex = events[(draw_event, "ShaderStage.Vertex")]
    pixel = events[(draw_event, "ShaderStage.Pixel")]
    block = model_strand_block(vertex)
    raw = (AUDIT / block["data"]["file"]).read_bytes()
    root_variable = block["variables"][0]
    decoded = {
        member["name"]: compact(member["name"], decode_value(raw, member))
        for member in root_variable["type"]["members"]
    }
    stages = {}
    for group, group_events in COMPUTE_EVENTS.items():
        event_id = group_events[ordinal]
        compute = events[(event_id, "ShaderStage.Compute")]
        stages[group] = {
            "event": event_id,
            "entry": compute["entry"],
            "dispatch": compute["action"]["dispatchDimension"],
            "read_only": resources(compute, "read_only"),
            "read_write": resources(compute, "read_write"),
        }
    analysis["objects"].append(
        {
            "ordinal": ordinal,
            "draw_event": draw_event,
            "vertex_entry": vertex["entry"],
            "pixel_entry": pixel["entry"],
            "indirect_index_count": vertex["action"]["numIndices"],
            "constants": decoded,
            "compute": stages,
            "vertex_resources": resources(vertex, "read_only"),
            "pixel_resources": resources(pixel, "read_only"),
        }
    )

OUTPUT.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
print(
    json.dumps(
        {
            "status": "passed",
            "objects": len(analysis["objects"]),
            "output": str(OUTPUT),
            "capture_sha256": analysis["capture_sha256"],
        },
        indent=2,
    )
)
