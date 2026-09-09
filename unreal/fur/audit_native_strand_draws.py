"""Bounded saved-frame audit of native strand draws.

This opens an existing retail capture only. It does not launch the game and it
does not create or activate a visible desktop. Run it through qrenderdoc's
``--python`` entry point under ``tools/private_desktop.py``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import time
import traceback

import renderdoc as rd


# qrenderdoc executes --python scripts with exec(), so __file__ is not defined.
# The private launcher pins cwd to the repository root.
REPO_ROOT = Path.cwd().resolve()
if not (REPO_ROOT / "tools" / "private_desktop.py").is_file():
    raise RuntimeError(f"Expected repository root as cwd, got {REPO_ROOT}")
OUTPUT = REPO_ROOT / "unreal" / "fur" / "recovered" / "ear-strand-audit"
CAPTURE_CANDIDATES = (
    REPO_ROOT
    / "artifacts"
    / "rcra-fur-continuation"
    / "capture-tools"
    / "riftapart-checkpoint_capture_5.rdc",
    Path.home()
    / "Cloud-Drive"
    / "Github"
    / "gem-shader"
    / "artifacts"
    / "rcra-fur-continuation"
    / "capture-tools"
    / "riftapart-checkpoint_capture_5.rdc",
    Path("F:/Cloud-Drive_rmunoz1994@gmail.com/Github/gem-shader")
    / "artifacts"
    / "rcra-fur-continuation"
    / "capture-tools"
    / "riftapart-checkpoint_capture_5.rdc",
)
EVENTS = (24727, 24825, 24831, 24838, 24844)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_bytes(name: str, raw) -> dict:
    data = bytes(raw)
    path = OUTPUT / name
    path.write_bytes(data)
    return {
        "file": name,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def checkpoint(report: dict) -> None:
    temporary = OUTPUT / "draw-report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT / "draw-report.json")


def find_capture() -> Path:
    for candidate in CAPTURE_CANDIDATES:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "Retail checkpoint capture not found. Checked:\n"
        + "\n".join(str(path) for path in CAPTURE_CANDIDATES)
    )


def collect_actions(actions, result: dict) -> None:
    for action in actions:
        result[action.eventId] = action
        collect_actions(action.children, result)


OUTPUT.mkdir(parents=True, exist_ok=True)
capture_path = find_capture()
report = {
    "schema_version": 2,
    "capture": str(capture_path),
    "capture_size": capture_path.stat().st_size,
    "capture_sha256": sha256_file(capture_path),
    "events_requested": list(EVENTS),
    "events": [],
    "completed": False,
}
capture = controller = None
checkpoint(report)

try:
    capture = rd.OpenCaptureFile()
    status = capture.OpenFile(str(capture_path), "", None)
    assert status == rd.ResultCode.Succeeded, str(status)
    status, controller = capture.OpenCapture(rd.ReplayOptions(), None)
    assert status == rd.ResultCode.Succeeded, str(status)

    resources = controller.GetResources()
    names = {resource.resourceId: resource.name for resource in resources}
    textures = {texture.resourceId: texture for texture in controller.GetTextures()}
    actions = {}
    collect_actions(controller.GetRootActions(), actions)
    event_ids = sorted(actions)
    report["resource_count"] = len(resources)
    report["action_count"] = len(actions)
    checkpoint(report)

    def export_albedo(pipeline, filename: str) -> dict | None:
        targets = pipeline.GetOutputTargets()
        if len(targets) <= 1:
            return None
        descriptor = targets[1]
        texture = textures[descriptor.resource]
        if texture.width * texture.height > 4096 * 4096:
            raise RuntimeError(
                f"Refusing oversized target {texture.width}x{texture.height}"
            )
        return {
            "resource": str(descriptor.resource),
            "name": names.get(descriptor.resource),
            "width": texture.width,
            "height": texture.height,
            "depth": texture.depth,
            "arraysize": texture.arraysize,
            "mips": texture.mips,
            "format": texture.format.Name(),
            **save_bytes(
                filename,
                controller.GetTextureData(descriptor.resource, rd.Subresource()),
            ),
        }

    for event in EVENTS:
        row = {"event": event, "stages": [], "completed": False}
        report["events"].append(row)
        checkpoint(report)
        try:
            if event != EVENTS[0]:
                previous_event = event_ids[event_ids.index(event) - 1]
                row["previous_event"] = previous_event
                controller.SetFrameEvent(previous_event, True)
                before = export_albedo(
                    controller.GetPipelineState(), f"{event}-before-albedo.bin"
                )
                if before:
                    row["before_albedo"] = before

            controller.SetFrameEvent(event, True)
            pipeline = controller.GetPipelineState()
            action = actions.get(event)
            if action:
                row["action"] = {
                    "event_id": action.eventId,
                    "name": action.GetName(controller.GetStructuredFile()),
                    "num_indices": action.numIndices,
                    "num_instances": action.numInstances,
                    "instance_offset": action.instanceOffset,
                }

            if event != EVENTS[0]:
                for stage in (
                    rd.ShaderStage.Vertex,
                    rd.ShaderStage.Geometry,
                    rd.ShaderStage.Pixel,
                ):
                    reflection = pipeline.GetShaderReflection(stage)
                    if not reflection:
                        continue
                    stage_row = {
                        "stage": str(stage),
                        "entry": reflection.entryPoint,
                        "sha256": hashlib.sha256(bytes(reflection.rawBytes)).hexdigest(),
                        "buffers": [],
                    }
                    row["stages"].append(stage_row)
                    for index, block in enumerate(reflection.constantBlocks):
                        if block.name != "ModelStrandCBuffer":
                            continue
                        descriptor = pipeline.GetConstantBlock(stage, index, 0).descriptor
                        raw = bytes(
                            controller.GetBufferData(
                                descriptor.resource,
                                descriptor.byteOffset,
                                block.byteSize,
                            )
                        )
                        if len(raw) < 64:
                            raise RuntimeError(
                                f"{stage} ModelStrandCBuffer returned only {len(raw)} bytes"
                            )
                        stage_row["buffers"].append(
                            {
                                "name": block.name,
                                "resource": str(descriptor.resource),
                                "offset": descriptor.byteOffset,
                                "scene_object_gpu": struct.unpack_from("<I", raw, 28)[0],
                                "strand_count": struct.unpack_from("<I", raw, 60)[0],
                                **save_bytes(
                                    f"{event}-{str(stage).split('.')[-1]}-cb.bin", raw
                                ),
                            }
                        )

            albedo = export_albedo(pipeline, f"{event}-albedo.bin")
            if albedo:
                row["albedo"] = albedo
            row["completed"] = True
        except Exception:
            row["error"] = traceback.format_exc()
        checkpoint(report)
        time.sleep(0.15)

    report["completed"] = all(row["completed"] for row in report["events"])
except Exception:
    report["error"] = traceback.format_exc()
finally:
    if controller:
        controller.Shutdown()
    if capture:
        capture.Shutdown()
    checkpoint(report)

raise SystemExit(0 if report["completed"] else 1)
