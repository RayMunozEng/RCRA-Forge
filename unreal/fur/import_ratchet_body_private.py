"""Import and validate the private retail Ratchet skeletal FBX fixture in UE."""

import json
from pathlib import Path
import traceback
import unreal


root = Path(__file__).resolve().parent
source = root / "recovered/ratchet-body/RatchetRetailLOD0.glb"
out = root / "recovered/ratchet-body/ue-import-report.json"
destination = "/Game/FurValidation/RatchetBodyV2"
report = {"source": str(source), "destination": destination, "completed": False}

try:
    assets = unreal.EditorAssetLibrary.list_assets(destination, recursive=True)
    meshes = [unreal.load_asset(path) for path in assets]
    meshes = [asset for asset in meshes if isinstance(asset, unreal.SkeletalMesh)]
    # This is a private generated fixture. Reimport it even when the prior 31
    # parts exist so newly recovered vertex channels replace stale mesh data.
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(source))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", "SK_RatchetRetailLOD0")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = list(task.get_editor_property("imported_object_paths"))
    assets = unreal.EditorAssetLibrary.list_assets(destination, recursive=True)
    meshes = [unreal.load_asset(path) for path in assets]
    meshes = [asset for asset in meshes if isinstance(asset, unreal.SkeletalMesh)]
    mesh = meshes[0] if meshes else None
    if mesh is None:
        raise RuntimeError("GLB import did not create a SkeletalMesh")

    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = actors.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector())
    component = actor.get_editor_property("skeletal_mesh_component")
    component.set_skeletal_mesh_asset(mesh)
    bounds_origin, bounds_extent = actor.get_actor_bounds(False)
    report.update(
        completed=True,
        imported_object_paths=imported,
        skeletal_mesh_parts=len(meshes),
        skeletal_mesh=mesh.get_path_name(),
        bones=component.get_num_bones(),
        first_bones=[str(component.get_bone_name(i))
                     for i in range(min(component.get_num_bones(), 16))],
        bounds_origin=[bounds_origin.x, bounds_origin.y, bounds_origin.z],
        bounds_extent=[bounds_extent.x, bounds_extent.y, bounds_extent.z],
    )
except Exception:
    report["error"] = traceback.format_exc()
finally:
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    unreal.SystemLibrary.execute_console_command(world, "QUIT_EDITOR")

if not report["completed"]:
    unreal.log_error(report["error"])
