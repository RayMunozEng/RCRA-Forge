"""Extract exact clip-space positions produced by the retail strand vertex shader."""

from __future__ import annotations

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
EVENTS = (24825, 24831, 24844)


report = {"schema_version": 1, "events": [], "completed": False}
capture = controller = None
try:
    capture = rd.OpenCaptureFile()
    status = capture.OpenFile(str(CAPTURE), "", None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    status, controller = capture.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    for event in EVENTS:
        controller.SetFrameEvent(event, True)
        mesh = controller.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
        if mesh.vertexResourceId == rd.ResourceId.Null() or not mesh.numIndices:
            raise RuntimeError(f"Event {event} did not produce post-VS mesh data")
        raw = bytes(controller.GetBufferData(
            mesh.vertexResourceId, mesh.vertexByteOffset,
            mesh.vertexByteStride * mesh.numIndices))
        positions = [
            struct.unpack_from("<4f", raw, index * mesh.vertexByteStride)
            for index in range(mesh.numIndices)
        ]
        if not all(all(value == value for value in point) for point in positions):
            raise RuntimeError(f"Event {event} post-VS positions contain NaNs")
        packed = b"".join(struct.pack("<4f", *point) for point in positions)
        filename = f"e{event}-postvs-clip-float4.bin"
        (OUTPUT / filename).write_bytes(packed)
        projectable = [point for point in positions if abs(point[3]) > 1e-12]
        if not projectable:
            raise RuntimeError(f"Event {event} has no projectable post-VS vertices")
        ndc = [[point[axis] / point[3] for axis in range(3)] for point in projectable]
        report["events"].append({
            "event": event,
            "vertices": mesh.numIndices,
            "projectable_vertices": len(projectable),
            "zero_w_vertices": mesh.numIndices - len(projectable),
            "source_stride": mesh.vertexByteStride,
            "source_byte_offset": mesh.vertexByteOffset,
            "clip_file": filename,
            "clip_sha256": hashlib.sha256(packed).hexdigest(),
            "ndc_min": [min(point[axis] for point in ndc) for axis in range(3)],
            "ndc_max": [max(point[axis] for point in ndc) for axis in range(3)],
        })
    report["completed"] = True
except Exception:
    report["error"] = traceback.format_exc()
finally:
    if controller:
        controller.Shutdown()
    if capture:
        capture.Shutdown()
    (OUTPUT / "postvs-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

raise SystemExit(0 if report["completed"] else 1)
