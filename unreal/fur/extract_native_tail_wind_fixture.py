"""Extract the two per-object records needed to replay retail tail wind."""

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
EVENT = 24762
MODEL_CB = OUTPUT / "e24762-Compute-b5.bin"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


report = {"event": EVENT, "completed": False}
capture = controller = None
try:
    model_cb = MODEL_CB.read_bytes()
    scene_index = struct.unpack_from("<I", model_cb, 28)[0]
    if scene_index != 38960:
        raise RuntimeError(f"Unexpected tail scene-object index {scene_index}")
    capture = rd.OpenCaptureFile()
    status = capture.OpenFile(str(CAPTURE), "", None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    status, controller = capture.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    controller.SetFrameEvent(EVENT, True)
    pipeline = controller.GetPipelineState()
    reflection = pipeline.GetShaderReflection(rd.ShaderStage.Compute)
    declarations = reflection.readOnlyResources
    wanted = {
        "g_SceneObjectView": (128, "e24762-SceneObjectGpu.bin"),
        "g_DynamicObjectView": (64, "e24762-DynamicObjectGpu.bin"),
    }
    rows = []
    for used in pipeline.GetReadOnlyResources(rd.ShaderStage.Compute):
        if used.access.index >= len(declarations):
            continue
        name = declarations[used.access.index].name
        if name not in wanted:
            continue
        stride, filename = wanted[name]
        descriptor = used.descriptor
        if descriptor.elementByteSize != stride:
            raise RuntimeError(
                f"{name} stride {descriptor.elementByteSize}, expected {stride}")
        offset = descriptor.byteOffset + scene_index * stride
        data = bytes(controller.GetBufferData(descriptor.resource, offset, stride))
        if len(data) != stride:
            raise RuntimeError(f"{name}: expected {stride} bytes, got {len(data)}")
        (OUTPUT / filename).write_bytes(data)
        rows.append({"binding": name, "scene_index": scene_index,
                     "byte_offset": offset, "bytes": len(data),
                     "file": filename, "sha256": sha256(data)})
    if {row["binding"] for row in rows} != set(wanted):
        raise RuntimeError("Both per-object records were not extracted")
    read_write = pipeline.GetReadWriteResources(rd.ShaderStage.Compute)
    if len(read_write) != 1:
        raise RuntimeError(f"Expected one wind output, found {len(read_write)}")
    output_descriptor = read_write[0].descriptor
    output_size = output_descriptor.byteSize
    controller.SetFrameEvent(EVENT - 1, True)
    pre_dispatch = bytes(controller.GetBufferData(
        output_descriptor.resource, output_descriptor.byteOffset, output_size))
    if len(pre_dispatch) != output_size:
        raise RuntimeError(
            f"Pre-dispatch u0: expected {output_size} bytes, got {len(pre_dispatch)}")
    pre_filename = "e24762-pre-Compute-u0-StrandCVBufferOutput.bin"
    (OUTPUT / pre_filename).write_bytes(pre_dispatch)
    rows.append({"binding": "g_StrandCVBufferOutput-pre-dispatch",
                 "event": EVENT - 1, "bytes": len(pre_dispatch),
                 "file": pre_filename, "sha256": sha256(pre_dispatch)})
    report.update(scene_index=scene_index, records=rows, completed=True)
except Exception:
    report["error"] = traceback.format_exc()
finally:
    if controller:
        controller.Shutdown()
    if capture:
        capture.Shutdown()
    (OUTPUT / "tail-wind-fixture-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

raise SystemExit(0 if report["completed"] else 1)
