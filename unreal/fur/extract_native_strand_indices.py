"""Extract the native draw index buffer for retail tail ModelStrand event 24825."""

import hashlib
import json
from pathlib import Path
import struct
import traceback

import renderdoc as rd


ROOT = Path.cwd().resolve()
OUTPUT = ROOT / "unreal/fur/recovered/native-strand-pipeline"
CAPTURE = (Path.home() / "Cloud-Drive/Github/gem-shader/artifacts/"
           "rcra-fur-continuation/capture-tools/riftapart-checkpoint_capture_5.rdc")
EVENT = 24825
report = {"schema_version": 1, "event": EVENT, "completed": False}
capture = controller = None


def find_action(actions, event):
    for action in actions:
        if action.eventId == event:
            return action
        found = find_action(action.children, event)
        if found is not None:
            return found
    return None


try:
    capture = rd.OpenCaptureFile()
    status = capture.OpenFile(str(CAPTURE), "", None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    status, controller = capture.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    controller.SetFrameEvent(EVENT, True)
    mesh = controller.GetPostVSData(0, 0, rd.MeshDataStage.VSIn)
    stride = int(mesh.indexByteStride)
    count = int(mesh.numIndices)
    if stride == 0:
        report.update({
            "count": count,
            "index_stride": 0,
            "base_vertex": int(mesh.baseVertex),
            "mapping": "identity non-indexed SV_VertexID order",
            "completed": True,
        })
        raise StopIteration
    if stride not in (2, 4):
        raise RuntimeError(f"Unexpected index stride {stride}")
    offset = int(mesh.indexByteOffset)
    report.update({"index_resource": str(mesh.indexResourceId),
                   "index_stride": stride, "index_byte_offset": offset,
                   "count": count})
    raw = bytes(controller.GetBufferData(
        mesh.indexResourceId, offset, count * stride))
    if len(raw) != count * stride:
        raise RuntimeError(f"Expected {count * stride} bytes, got {len(raw)}")
    code = "H" if stride == 2 else "I"
    indices = struct.unpack(f"<{count}{code}", raw)
    filename = f"e{EVENT}-draw-indices-u{stride * 8}.bin"
    (OUTPUT / filename).write_bytes(raw)
    report.update({
        "count": count,
        "stride": stride,
        "byte_offset": offset,
        "base_vertex": int(mesh.baseVertex),
        "minimum": min(indices),
        "maximum": max(indices),
        "unique": len(set(indices)),
        "file": filename,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "first_32": list(indices[:32]),
        "completed": True,
    })
except StopIteration:
    pass
except Exception:
    report["error"] = traceback.format_exc()
finally:
    if controller:
        controller.Shutdown()
    if capture:
        capture.Shutdown()
    (OUTPUT / "native-index-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    (OUTPUT / "native-index-extract.stop").write_text("done", encoding="utf-8")

raise SystemExit(0 if report["completed"] else 1)
