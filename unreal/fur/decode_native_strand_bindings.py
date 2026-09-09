"""Decode retail ModelStrand triangle bindings into skeletal bone weights.

The retail skinning shader binds each guide to three vertices from one body
subset. This joins that exact tuple to JOINTS_0/WEIGHTS_0 in the exported body
fixture; it does not use nearest-point or spatial matching.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent
NATIVE = ROOT / "recovered/native-strand-pipeline"
BODY = ROOT / "recovered/ratchet-body/RatchetRetailLOD0.glb"
CAPTURE_SHA256 = "c5304097273a3863409956c0e014d48ac390b305f391c6543787097fd6b9647e"
GROUPS = {
    "tail": (24743, 7, "ratchet-tail-guides-bind-visible.json"),
    "head-sparse": (24748, 23, "ratchet-head-sparse-guides-bind-visible.json"),
    "ears": (24756, 23, "ratchet-ear-guides-bind-visible.json"),
}

parser = argparse.ArgumentParser()
parser.add_argument("--group", choices=GROUPS, required=True)
args = parser.parse_args()
event, first_subset, guide_name = GROUPS[args.group]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_glb(path):
    raw = path.read_bytes()
    if raw[:4] != b"glTF":
        raise RuntimeError("Body fixture is not a binary glTF")
    json_length, json_type = struct.unpack_from("<II", raw, 12)
    if json_type != 0x4E4F534A:
        raise RuntimeError("First GLB chunk is not JSON")
    doc = json.loads(raw[20:20 + json_length])
    binary_offset = 20 + json_length
    while binary_offset % 4:
        binary_offset += 1
    binary_length, binary_type = struct.unpack_from("<II", raw, binary_offset)
    if binary_type != 0x004E4942:
        raise RuntimeError("Second GLB chunk is not BIN")
    return doc, raw[binary_offset + 8:binary_offset + 8 + binary_length]


FORMATS = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def accessor_values(doc, binary, accessor_index):
    accessor = doc["accessors"][accessor_index]
    view = doc["bufferViews"][accessor["bufferView"]]
    count = accessor["count"]
    components = COMPONENTS[accessor["type"]]
    code = FORMATS[accessor["componentType"]]
    packed_size = struct.calcsize("<" + code * components)
    stride = view.get("byteStride", packed_size)
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    values = []
    for index in range(count):
        values.append(struct.unpack_from("<" + code * components, binary, offset + index * stride))
    return values


doc, binary = load_glb(BODY)
skin = doc["skins"][0]
joint_names = [doc["nodes"][node].get("name", f"bone_{node}") for node in skin["joints"]]
subset_streams = []
for mesh in doc["meshes"]:
    primitive = mesh["primitives"][0]
    attributes = primitive["attributes"]
    subset_streams.append((
        accessor_values(doc, binary, attributes["JOINTS_0"]),
        accessor_values(doc, binary, attributes["WEIGHTS_0"]),
    ))

guides_path = NATIVE / guide_name
guide_doc = json.loads(guides_path.read_text(encoding="utf-8"))
if guide_doc["source_capture_sha256"] != CAPTURE_SHA256:
    raise RuntimeError("Guide fixture is from a different retail capture")
sb_path = NATIVE / f"e{event}-Compute-t7-StrandSBBuffer.bin"
sb = sb_path.read_bytes()

bindings = []
maximum_influences = 0
slots = set()
for guide in guide_doc["guides"]:
    strand_index = guide["source_strand_index"]
    word0, word1 = struct.unpack_from("<II", sb, strand_index * 8)
    vertex_indices = [word0 & 0xFFFF, word0 >> 16, word1 & 0xFFFF]
    first_weight = ((word1 >> 16) & 15) / 15.0
    second_weight = ((word1 >> 20) & 15) / 15.0
    barycentric = [first_weight, second_weight, max(1.0 - first_weight - second_weight, 0.0)]
    binding_slot = (word1 >> 26) * 4 + ((word1 >> 24) & 3)
    subset = first_subset + binding_slot
    if subset >= len(subset_streams):
        raise RuntimeError(f"Guide {strand_index} maps past body subset count")
    joints, weights = subset_streams[subset]
    influences = defaultdict(float)
    for vertex, bary in zip(vertex_indices, barycentric):
        if vertex >= len(joints):
            raise RuntimeError(
                f"Guide {strand_index}: vertex {vertex} exceeds subset {subset}")
        for joint, weight in zip(joints[vertex], weights[vertex]):
            if weight > 0:
                influences[joint_names[joint]] += bary * weight
    total = sum(influences.values())
    if total <= 0:
        raise RuntimeError(f"Guide {strand_index} has no skeletal influence")
    influence_rows = [
        {"bone": bone, "weight": weight / total}
        for bone, weight in sorted(influences.items(), key=lambda item: -item[1])
        if weight / total > 1e-7
    ]
    maximum_influences = max(maximum_influences, len(influence_rows))
    slots.add(binding_slot)
    bindings.append({
        "source_strand_index": strand_index,
        "body_subset": subset,
        "source_vertex_indices": vertex_indices,
        "barycentric_weights": barycentric,
        "bone_influences": influence_rows,
    })

output = {
    "schema_version": 1,
    "group": args.group,
    "source_capture_sha256": CAPTURE_SHA256,
    "source_skinning_event": event,
    "source_binding_buffer": sb_path.name,
    "source_binding_buffer_sha256": sha256(sb_path),
    "source_body_glb_sha256": sha256(BODY),
    "method": "exact retail subset/triangle/barycentric binding joined to exported JOINTS_0/WEIGHTS_0",
    "first_body_subset": first_subset,
    "binding_slots": sorted(slots),
    "guides": len(bindings),
    "maximum_combined_bone_influences": maximum_influences,
    "bindings": bindings,
}
output_path = NATIVE / f"ratchet-{args.group}-skeletal-bindings.json"
output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in output.items() if key != "bindings"}, indent=2))
