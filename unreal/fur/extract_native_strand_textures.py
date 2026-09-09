"""Extract exact retail textures bound by a captured ModelStrand draw."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import traceback

import renderdoc as rd


ROOT = Path.cwd().resolve()
OUTPUT = ROOT / "unreal/fur/recovered/native-strand-pipeline"
CAPTURE_CANDIDATES = (
    ROOT / "artifacts/rcra-fur-continuation/capture-tools/riftapart-checkpoint_capture_5.rdc",
    Path.home() / "Cloud-Drive/Github/gem-shader/artifacts/rcra-fur-continuation/capture-tools/riftapart-checkpoint_capture_5.rdc",
)
parser = argparse.ArgumentParser()
parser.add_argument(
    "--group", choices=("head-sparse", "tail"),
    default=os.environ.get("RCRA_STRAND_TEXTURE_GROUP", "head-sparse"))
args = parser.parse_args()
GROUPS = {
    "head-sparse": {
        "event": 24831,
        "prefix": "head-sparse",
        "diffuse": (128, 128, "hero_ratchet_head_furtint_c.texture"),
        "mask": (None, None, "hero_ratchet_head_fur_mask_m.texture"),
    },
    "tail": {
        "event": 24825,
        "prefix": "tail",
        "diffuse": (None, None, "hero_ratchet_limbs_furtint_c.texture"),
        "mask": (None, None, "hero_ratchet_tail_fur_mask_m.texture"),
    },
}
group = GROUPS[args.group]
EVENT = group["event"]
EXPECTED = {
    "g_DiffuseTexture": (rd.ShaderStage.Pixel, *group["diffuse"]),
    "g_SpecTexture": (rd.ShaderStage.Pixel, 4, 4, "Default White"),
    "g_GlossTexture": (rd.ShaderStage.Pixel, 4, 4, "Default White"),
    "g_StrandThicknessTexture": (rd.ShaderStage.Vertex, *group["mask"]),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


capture_path = next((path for path in CAPTURE_CANDIDATES if path.is_file()), None)
if capture_path is None:
    raise FileNotFoundError("Retail capture not found")
report = {
    "schema_version": 1,
    "capture": str(capture_path.resolve()),
    "capture_sha256": "c5304097273a3863409956c0e014d48ac390b305f391c6543787097fd6b9647e",
    "group": args.group,
    "event": EVENT,
    "textures": [],
    "completed": False,
}
capture = controller = None
try:
    capture = rd.OpenCaptureFile()
    status = capture.OpenFile(str(capture_path.resolve()), "", None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    status, controller = capture.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    controller.SetFrameEvent(EVENT, True)
    pipeline = controller.GetPipelineState()
    names = {resource.resourceId: resource.name for resource in controller.GetResources()}
    textures = {texture.resourceId: texture for texture in controller.GetTextures()}
    for stage in (rd.ShaderStage.Vertex, rd.ShaderStage.Pixel):
      reflection = pipeline.GetShaderReflection(stage)
      declarations = reflection.readOnlyResources
      for used in pipeline.GetReadOnlyResources(stage):
        if used.access.index >= len(declarations):
          continue
        declaration = declarations[used.access.index]
        if declaration.name not in EXPECTED or EXPECTED[declaration.name][0] != stage:
          continue
        _, width, height, expected_name = EXPECTED[declaration.name]
        resource_id = used.descriptor.resource
        texture = textures[resource_id]
        resource_name = names.get(resource_id, "")
        if resource_name != expected_name or (
                width is not None and (texture.width, texture.height) != (width, height)):
            raise RuntimeError(
                f"Unexpected {declaration.name}: {texture.width}x{texture.height} {resource_name}")
        data = bytes(controller.GetTextureData(resource_id, rd.Subresource()))
        stem = declaration.name[2:] if declaration.name.startswith("g_") else declaration.name
        native_filename = group["prefix"] + "-" + stem + ".native"
        (OUTPUT / native_filename).write_bytes(data)
        png_filename = group["prefix"] + "-" + stem + ".png"
        texture_save = rd.TextureSave()
        texture_save.resourceId = resource_id
        texture_save.mip = 0
        texture_save.slice.sliceIndex = 0
        texture_save.destType = rd.FileType.PNG
        if not controller.SaveTexture(texture_save, str(OUTPUT / png_filename)):
            raise RuntimeError("RenderDoc could not export " + declaration.name)
        png_data = (OUTPUT / png_filename).read_bytes()
        report["textures"].append({
            "binding": declaration.name,
            "resource_name": resource_name,
            "stage": str(stage),
            "width": texture.width,
            "height": texture.height,
            "format": texture.format.Name(),
            "native_file": native_filename,
            "native_bytes": len(data),
            "native_sha256": sha256(data),
            "png_file": png_filename,
            "png_bytes": len(png_data),
            "png_sha256": sha256(png_data),
        })
    if {row["binding"] for row in report["textures"]} != set(EXPECTED):
        raise RuntimeError("Not all expected strand textures were extracted")
    report["completed"] = True
except Exception:
    report["error"] = traceback.format_exc()
finally:
    if controller:
        controller.Shutdown()
    if capture:
        capture.Shutdown()
    (OUTPUT / (group["prefix"] + "-texture-report.json")).write_text(
        json.dumps(report, indent=2), encoding="utf-8")

raise SystemExit(0 if report["completed"] else 1)
