"""Record the retail ModelStrand primitive topology for all three live draws."""

import json
from pathlib import Path
import traceback

import renderdoc as rd


ROOT = Path.cwd().resolve()
OUTPUT = ROOT / "unreal/fur/recovered/native-strand-pipeline"
CAPTURE = (Path.home() / "Cloud-Drive/Github/gem-shader/artifacts/"
           "rcra-fur-continuation/capture-tools/riftapart-checkpoint_capture_5.rdc")
EVENTS = (24825, 24831, 24844)
REPORT = OUTPUT / "strand-topology-report.json"
STOP = OUTPUT / "strand-topology.stop"
result = {"schema_version": 1, "completed": False, "events": []}
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
        pipeline = controller.GetPipelineState()
        topology = pipeline.GetPrimitiveTopology()
        mesh = controller.GetPostVSData(0, 0, rd.MeshDataStage.VSIn)
        result["events"].append({
            "event": event,
            "primitive_topology": str(topology),
            "draw_vertices": int(mesh.numIndices),
            "index_stride": int(mesh.indexByteStride),
        })
    result["completed"] = True
except Exception:
    result["error"] = traceback.format_exc()
finally:
    if controller:
        controller.Shutdown()
    if capture:
        capture.Shutdown()
    REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    STOP.write_text("done", encoding="utf-8")

raise SystemExit(0 if result["completed"] else 1)
