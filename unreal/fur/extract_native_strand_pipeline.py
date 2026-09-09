"""Extract bounded, hash-checked metadata for the retail ModelStrand pipeline.

This replays the existing checkpoint capture only. It neither launches the game
nor activates a desktop. Run it through qrenderdoc under private_desktop.py.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import traceback

import renderdoc as rd


ROOT = Path.cwd().resolve()
OUTPUT = ROOT / "unreal" / "fur" / "recovered" / "native-strand-pipeline"
CAPTURE = (
    Path.home()
    / "Cloud-Drive"
    / "Github"
    / "gem-shader"
    / "artifacts"
    / "rcra-fur-continuation"
    / "capture-tools"
    / "riftapart-checkpoint_capture_5.rdc"
)
COMPUTE_EVENTS = {
    "apply_skinning": (24743, 24748, 24752, 24756),
    "simulate_wind": (24762, 24767, 24771, 24775),
    "init_work_queue": (24781, 24784, 24787, 24790),
    "indirect_args": (24796, 24801, 24806, 24811),
}
DRAW_EVENTS = (24825, 24831, 24838, 24844)
EXPECTED = {
    "CS_ModelStrandApplySkinning": "12ae0b829076ef1857b39feb439e6a811fdc6ad301261ba78b5f41b256e89303",
    "CS_ModelStrandSimulateWind": "1f25b70e707f4f2b623bf40b1df70f3cf765907c805cd3461e5887389ff60c1b",
    "CS_ModelStrandInitWorkQueue": "ec15bae289f400bf1a4caa6ae55c5d5a9d0290e7de3cc510722663ef55323339",
    "CS_ModelStrandIndirectArgs": "6f094f9addec5699ada3773fc55b2f06578a201ac77c555a4d5d5c2843637362",
    "VS_ModelStrandTextured": "abf8643734c271684028c68003aa1cfa6d6e77236a1c0a24b41c627ee6c04740",
    "VS_ModelStrand": "d27d58a2c400086c68ec4e231e3c180aaad9f892f74bff98376efdd369b434a7",
    "PS_ModelStrandStandard": "a622c15599ca020c599412607800ab75417a62a272b771ae068ed78d90965a77",
}


def simple(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return [simple(item) for item in value]
    return str(value)


def fields(obj, names):
    return {name: simple(getattr(obj, name)) for name in names if hasattr(obj, name)}


def constant_type(item):
    result = fields(
        item,
        (
            "name",
            "baseType",
            "rows",
            "columns",
            "elements",
            "arrayByteStride",
            "matrixByteStride",
            "pointerTypeID",
        ),
    )
    members = getattr(item, "members", ())
    if members:
        result["members"] = [constant(member) for member in members]
    return result


def constant(item):
    result = fields(
        item,
        ("name", "byteOffset", "bitFieldOffset", "bitFieldSize", "defaultValue"),
    )
    if hasattr(item, "type"):
        result["type"] = constant_type(item.type)
    return result


def descriptor(item):
    result = fields(
        item,
        (
            "resource",
            "secondary",
            "view",
            "byteOffset",
            "byteSize",
            "elementByteSize",
            "bufferStructCount",
            "counterByteOffset",
            "firstMip",
            "numMips",
            "firstSlice",
            "numSlices",
            "minLODClamp",
            "textureType",
            "type",
            "flags",
            "swizzle",
        ),
    )
    result["format"] = item.format.Name()
    return result


def save(name, raw):
    data = bytes(raw)
    path = OUTPUT / name
    path.write_bytes(data)
    return {"file": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def checkpoint(report):
    temporary = OUTPUT / "report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT / "report.json")


def collect_actions(actions, result):
    for action in actions:
        result[action.eventId] = action
        collect_actions(action.children, result)


OUTPUT.mkdir(parents=True, exist_ok=True)
report = {
    "schema_version": 1,
    "capture": str(CAPTURE),
    "capture_sha256": "c5304097273a3863409956c0e014d48ac390b305f391c6543787097fd6b9647e",
    "compute_groups": COMPUTE_EVENTS,
    "draw_events": DRAW_EVENTS,
    "events": [],
    "completed": False,
}
checkpoint(report)
capture = controller = None

try:
    if not CAPTURE.is_file():
        raise FileNotFoundError(CAPTURE)
    capture = rd.OpenCaptureFile()
    status = capture.OpenFile(str(CAPTURE), "", None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    status, controller = capture.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))

    names = {resource.resourceId: resource.name for resource in controller.GetResources()}
    buffers = {buffer.resourceId: buffer for buffer in controller.GetBuffers()}
    textures = {texture.resourceId: texture for texture in controller.GetTextures()}
    actions = {}
    collect_actions(controller.GetRootActions(), actions)

    event_stages = []
    for group, events in COMPUTE_EVENTS.items():
        event_stages.extend((event, group, rd.ShaderStage.Compute) for event in events)
    for event in DRAW_EVENTS:
        event_stages.extend(
            (event, "draw", stage)
            for stage in (rd.ShaderStage.Vertex, rd.ShaderStage.Pixel)
        )

    exported_shaders = {}
    for event, group, stage in event_stages:
        controller.SetFrameEvent(event, True)
        pipe = controller.GetPipelineState()
        reflection = pipe.GetShaderReflection(stage)
        if not reflection:
            raise RuntimeError(f"No {stage} reflection at event {event}")
        shader_hash = hashlib.sha256(bytes(reflection.rawBytes)).hexdigest()
        if EXPECTED.get(reflection.entryPoint) != shader_hash:
            raise RuntimeError(
                f"Unexpected {reflection.entryPoint} shader at {event}: {shader_hash}"
            )
        if reflection.entryPoint not in exported_shaders:
            stem = reflection.entryPoint
            binary = save(stem + ".dxil", reflection.rawBytes)
            assembly_text = controller.DisassembleShader(
                rd.ResourceId.Null(), reflection, ""
            )
            assembly_path = OUTPUT / (stem + ".txt")
            assembly_path.write_text(assembly_text, encoding="utf-8")
            exported_shaders[reflection.entryPoint] = {
                "binary": binary,
                "disassembly": {
                    "file": assembly_path.name,
                    "characters": len(assembly_text),
                    "sha256": hashlib.sha256(
                        assembly_text.encode("utf-8")
                    ).hexdigest(),
                },
            }
            report["shaders"] = exported_shaders
        action = actions[event]
        row = {
            "event": event,
            "group": group,
            "stage": str(stage),
            "entry": reflection.entryPoint,
            "shader_sha256": shader_hash,
            "action": fields(
                action,
                (
                    "numIndices",
                    "numInstances",
                    "indexOffset",
                    "vertexOffset",
                    "instanceOffset",
                    "dispatchDimension",
                    "dispatchThreadsDimension",
                ),
            ),
            "constant_blocks": [],
            "read_only": [],
            "read_write": [],
        }
        report["events"].append(row)

        for index, block in enumerate(reflection.constantBlocks):
            used = pipe.GetConstantBlock(stage, index, 0)
            bound = used.descriptor
            block_row = {
                "index": index,
                "name": block.name,
                "fixed_bind_number": block.fixedBindNumber,
                "fixed_bind_space": block.fixedBindSetOrSpace,
                "byte_size": block.byteSize,
                "buffer_backed": block.bufferBacked,
                "descriptor": descriptor(bound),
                "variables": [constant(variable) for variable in block.variables],
            }
            if block.bufferBacked and str(bound.resource) != "ResourceId::0":
                block_row["data"] = save(
                    f"e{event}-{str(stage).split('.')[-1]}-b{block.fixedBindNumber}.bin",
                    controller.GetBufferData(bound.resource, bound.byteOffset, block.byteSize),
                )
            row["constant_blocks"].append(block_row)

        for writable in (False, True):
            declarations = (
                reflection.readWriteResources if writable else reflection.readOnlyResources
            )
            used_resources = (
                pipe.GetReadWriteResources(stage)
                if writable
                else pipe.GetReadOnlyResources(stage)
            )
            destination = row["read_write" if writable else "read_only"]
            for used in used_resources:
                if used.access.index >= len(declarations):
                    continue
                declaration = declarations[used.access.index]
                bound = used.descriptor
                resource_row = {
                    "name": declaration.name,
                    "fixed_bind_number": declaration.fixedBindNumber,
                    "fixed_bind_space": declaration.fixedBindSetOrSpace,
                    "bind_array_size": declaration.bindArraySize,
                    "descriptor_type": str(declaration.descriptorType),
                    "variable_type": constant_type(declaration.variableType),
                    "access": fields(
                        used.access, ("index", "arrayElement", "staticallyUnused")
                    ),
                    "descriptor": descriptor(bound),
                    "resource_name": names.get(bound.resource, ""),
                }
                if bound.resource in buffers:
                    resource_row["buffer"] = fields(
                        buffers[bound.resource], ("length", "creationFlags", "gpuAddress")
                    )
                    byte_size = int(bound.byteSize)
                    if (
                        declaration.name.startswith("g_Strand")
                        and 0 < byte_size <= 2 * 1024 * 1024
                    ):
                        access_name = "u" if writable else "t"
                        safe_name = declaration.name.replace("g_", "")
                        resource_row["data"] = save(
                            f"e{event}-{str(stage).split('.')[-1]}-"
                            f"{access_name}{declaration.fixedBindNumber}-{safe_name}.bin",
                            controller.GetBufferData(
                                bound.resource, bound.byteOffset, byte_size
                            ),
                        )
                elif bound.resource in textures:
                    resource_row["texture"] = fields(
                        textures[bound.resource],
                        (
                            "width",
                            "height",
                            "depth",
                            "arraysize",
                            "mips",
                            "msSamp",
                            "creationFlags",
                        ),
                    )
                    resource_row["texture"]["format"] = textures[
                        bound.resource
                    ].format.Name()
                destination.append(resource_row)
        checkpoint(report)

    report["completed"] = True
except Exception:
    report["error"] = traceback.format_exc()
finally:
    if controller:
        controller.Shutdown()
    if capture:
        capture.Shutdown()
    checkpoint(report)

raise SystemExit(0 if report["completed"] else 1)
