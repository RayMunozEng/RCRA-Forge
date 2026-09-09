"""Extract the exact SceneObjectGpu record consumed by retail tail draw 24825."""

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
EVENT = 24825
MODEL_CB = OUTPUT / "e24825-Vertex-b5.bin"
FILENAME = "e24825-SceneObjectGpu.bin"


report = {"event": EVENT, "completed": False}
capture = controller = None
try:
    scene_index = struct.unpack_from("<I", MODEL_CB.read_bytes(), 28)[0]
    capture = rd.OpenCaptureFile()
    status = capture.OpenFile(str(CAPTURE), "", None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    status, controller = capture.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    controller.SetFrameEvent(EVENT, True)
    pipeline = controller.GetPipelineState()
    reflection = pipeline.GetShaderReflection(rd.ShaderStage.Vertex)
    declarations = reflection.readOnlyResources
    matches = []
    for used in pipeline.GetReadOnlyResources(rd.ShaderStage.Vertex):
        if used.access.index >= len(declarations):
            continue
        if declarations[used.access.index].name != "g_SceneObjectView":
            continue
        descriptor = used.descriptor
        stride = descriptor.elementByteSize
        if stride != 128:
            raise RuntimeError(f"SceneObjectGpu stride {stride}, expected 128")
        offset = descriptor.byteOffset + scene_index * stride
        data = bytes(controller.GetBufferData(descriptor.resource, offset, stride))
        if len(data) != stride:
            raise RuntimeError(f"Expected {stride} bytes, got {len(data)}")
        (OUTPUT / FILENAME).write_bytes(data)
        matches.append({
            "scene_index": scene_index,
            "byte_offset": offset,
            "bytes": len(data),
            "file": FILENAME,
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    if len(matches) != 1:
        raise RuntimeError(f"Expected one SceneObjectView binding, got {len(matches)}")
    report.update(record=matches[0], completed=True)
except Exception:
    report["error"] = traceback.format_exc()
finally:
    if controller:
        controller.Shutdown()
    if capture:
        capture.Shutdown()
    (OUTPUT / "tail-draw-scene-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

raise SystemExit(0 if report["completed"] else 1)
