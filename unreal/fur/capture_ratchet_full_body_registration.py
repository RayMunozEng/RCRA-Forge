"""Render captured Ratchet ModelStrand groups on the decoded full skinned body."""

import json
import importlib.util
from pathlib import Path
import re
import time
import traceback
import unreal


root = Path(__file__).resolve().parent
builder_path = (root.parent / "plugins/FurAuthoring/Content/Python/create_strand_groom.py")
builder_spec = importlib.util.spec_from_file_location("strand_builder", builder_path)
strand_builder = importlib.util.module_from_spec(builder_spec)
builder_spec.loader.exec_module(strand_builder)
out = root / "recovered/ratchet-full-body-registration"
out.mkdir(exist_ok=True)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level.new_level("/Game/FurValidation/RatchetFullBodyRegistration")
for inherited_actor in actors.get_all_level_actors():
    inherited_actor.set_actor_hidden_in_game(True)

asset_root = "/Game/FurValidation/RatchetBodyV2/RatchetRetailLOD0/SkeletalMeshes"
asset_paths = unreal.EditorAssetLibrary.list_assets(asset_root, recursive=True)
mesh_paths = [path for path in asset_paths
              if isinstance(unreal.load_asset(path), unreal.SkeletalMesh)]
mesh_paths.sort(key=lambda path: int(re.search(r"subset(\d+)-", path).group(1)))
if len(mesh_paths) != 31:
    raise RuntimeError(f"Expected 31 Ratchet body parts, found {len(mesh_paths)}")


def import_retail_base_material(material_index, texture_filename):
    texture_name = f"T_RatchetRetail_M{material_index:02d}_BaseColor_v1"
    texture_root = "/Game/FurValidation/RatchetRetailMaterials/Textures"
    texture_path = texture_root + "/" + texture_name
    texture = unreal.load_asset(texture_path)
    task = unreal.AssetImportTask()
    task.set_editor_property(
        "filename", str(root / "recovered/ratchet-body/textures" / texture_filename))
    task.set_editor_property("destination_path", texture_root)
    task.set_editor_property("destination_name", texture_name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    task.set_editor_property("factory", unreal.TextureFactory())
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    texture = unreal.load_asset(texture_path)
    if texture is None:
        raise RuntimeError(
            f"Could not import retail base color for material {material_index}: "
            f"{texture_filename}")
    texture.set_editor_property("srgb", True)
    unreal.EditorAssetLibrary.save_loaded_asset(texture)

    material_root = "/Game/FurValidation/RatchetRetailMaterials"
    material_name = f"M_RatchetRetail_M{material_index:02d}_Base_v1"
    material_path = material_root + "/" + material_name
    material = unreal.load_asset(material_path)
    if material is None:
        material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            material_name, material_root, unreal.Material, unreal.MaterialFactoryNew())
        material.set_editor_property("used_with_skeletal_mesh", True)
        sample = unreal.MaterialEditingLibrary.create_material_expression(
            material, unreal.MaterialExpressionTextureSampleParameter2D)
        sample.set_editor_property("parameter_name", "RetailBaseColor")
        sample.set_editor_property("texture", texture)
        sample.set_editor_property(
            "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        if not unreal.MaterialEditingLibrary.connect_material_property(
                sample, "RGB", unreal.MaterialProperty.MP_BASE_COLOR):
            raise RuntimeError(
                f"Could not connect retail base color for material {material_index}")
        unreal.MaterialEditingLibrary.layout_material_expressions(material)
        unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    return material


body_report = json.loads(
    (root / "recovered/ratchet-body/report.json").read_text(encoding="utf-8"))
body_inspection = json.loads(
    (root / "recovered/ratchet-body-inspection.json").read_text(encoding="utf-8"))
lod0_meshes = [mesh for mesh in body_inspection["meshes"] if mesh["lod"] == 0]
if len(lod0_meshes) != len(mesh_paths):
    raise RuntimeError(
        f"Body inspection has {len(lod0_meshes)} LOD0 subsets, expected {len(mesh_paths)}")
retail_materials = {}
subset_material_indices = []
unmapped_subsets = []
for subset_index, mesh_report in enumerate(lod0_meshes):
    if mesh_report["index"] != subset_index:
        raise RuntimeError(
            f"Unexpected LOD0 subset order at {subset_index}: {mesh_report['index']}")
    material_index = mesh_report["material_index"]
    subset_material_indices.append(material_index)
    material_report = body_report["materials"].get(str(material_index))
    base_color = (material_report or {}).get("textures", {}).get("base_color")
    if base_color is None:
        unmapped_subsets.append({
            "subset": subset_index,
            "material_index": material_index,
            "material_name": mesh_report["material_name"],
        })
        continue
    if material_index not in retail_materials:
        retail_materials[material_index] = import_retail_base_material(
            material_index, base_color)

body_actors = []
composite_shell_indices = []
for body_index, path in enumerate(mesh_paths):
    mesh = unreal.load_asset(path)
    actor = actors.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector())
    actor.set_actor_label("Body " + mesh.get_name())
    component = actor.get_editor_property("skeletal_mesh_component")
    component.set_skeletal_mesh_asset(mesh)
    material_index = subset_material_indices[body_index]
    if material_index in retail_materials:
        component.set_material(0, retail_materials[material_index])
    if body_index in (9, 16, 23):
        actor.set_actor_hidden_in_game(True)
        composite_shell_indices.append(body_index)
    body_actors.append(actor)


def import_fur_texture(part, role, srgb):
    asset_name = "T_Ratchet_" + part + "_" + role + "_rgba_v1"
    asset_path = "/Game/FurValidation/RatchetTail/Textures/" + asset_name
    texture = unreal.load_asset(asset_path)
    if texture is None:
        task = unreal.AssetImportTask()
        task.set_editor_property(
            "filename", str(root / ("recovered/ratchet-" + part + "-surface") /
                            (role + "-rgba.dds")))
        task.set_editor_property("destination_path", "/Game/FurValidation/RatchetTail/Textures")
        task.set_editor_property("destination_name", asset_name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        task.set_editor_property("factory", unreal.TextureFactory())
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        texture = unreal.load_asset(asset_path)
    if texture is None:
        raise RuntimeError("Could not import Ratchet tail " + role)
    texture.set_editor_property("srgb", srgb)
    texture.set_editor_property(
        "compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    texture.set_editor_property(
        "mip_gen_settings", unreal.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS)
    unreal.EditorAssetLibrary.save_loaded_asset(texture)
    return texture


part_specs = {
    "head": {"mesh": 26, "length": 3.0, "density": 16.0,
             "shells": 32, "transmittance": 0.1},
    "limbs": {"mesh": 20, "length": 1.5, "density": 16.0,
              "shells": 24, "transmittance": 0.2},
    "tail": {"mesh": 12, "length": 10.0, "density": 12.0,
             "shells": 24, "transmittance": 0.1},
}
part_textures = {
    part: {
        "base_color": import_fur_texture(part, "base_color", True),
        "fur_control": import_fur_texture(part, "fur_control", False),
        "specular_color": import_fur_texture(part, "specular_color", True),
        "normal": import_fur_texture(part, "normal", False),
    }
    for part in part_specs
}
builder_path = root.parent / "plugins/FurAuthoring/Content/Python/create_scene_fur.py"
spec = importlib.util.spec_from_file_location("tail_scene_builder", builder_path)
tail_scene_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tail_scene_builder)
part_materials = {}
for part, settings in part_specs.items():
    part_materials[part] = tail_scene_builder.create(
        "M_Ratchet" + part.title() + "ShellFull_v3", part_textures[part],
        fur=True, recovered=True, temporal=True, scene=True,
        settings=dict(length=settings["length"], density=settings["density"],
                      offset=1.0, transmittance=settings["transmittance"]),
        asset_path="/Game/FurValidation/RatchetTail/Materials", skeletal=True)
tail_debug_material = tail_scene_builder.create(
    "M_RatchetTailShellUnlitDebug_v4", part_textures["tail"], fur=True, unlit=True,
    settings=dict(length=10.0, density=12.0, offset=1.0, transmittance=0.1),
    asset_path="/Game/FurValidation/RatchetTail/Materials", skeletal=True)
head_debug_material = tail_scene_builder.create(
    "M_RatchetHeadShellUnlitDebug_v2", part_textures["head"], fur=True, unlit=True,
    settings=dict(length=3.0, density=16.0, offset=1.0, transmittance=0.1),
    asset_path="/Game/FurValidation/RatchetTail/Materials", skeletal=True)

part_fur = {}
part_sources = {}
for part, settings in part_specs.items():
    source = body_actors[settings["mesh"]].get_editor_property("skeletal_mesh_component")
    fur_actor = actors.spawn_actor_from_class(
        unreal.SkeletalFurAuthoringActor, unreal.Vector())
    fur_actor.set_actor_label("Retail Ratchet " + part.title() + " Shell Fur")
    fur_actor.set_editor_property("fur_material", part_materials[part])
    fur_actor.set_editor_property("length", settings["length"])
    fur_actor.set_editor_property("recovered_density", settings["density"])
    fur_actor.set_editor_property("groom_strength", 1.0)
    fur_actor.set_editor_property("shell_count", settings["shells"])
    fur_actor.set_editor_property("use_map_controls", True)
    fur_actor.set_pose_source(source)
    fur_actor.rebuild_fur()
    assert fur_actor.refresh_preview_pose()
    for layer in fur_actor.get_editor_property("skeletal_shells"):
        layer.get_material(0).set_scalar_parameter_value(
            "UseRetailDecodeCorrection", 1.0)
    part_fur[part] = fur_actor
    part_sources[part] = source
tail_fur = part_fur["tail"]
tail_source = part_sources["tail"]
tail_debug_fur = actors.spawn_actor_from_class(
    unreal.SkeletalFurAuthoringActor, unreal.Vector())
tail_debug_fur.set_actor_label("Ratchet Tail Shell Unlit Diagnostic")
tail_debug_fur.set_editor_property("fur_material", tail_debug_material)
tail_debug_fur.set_editor_property("length", 10.0)
tail_debug_fur.set_editor_property("recovered_density", 12.0)
tail_debug_fur.set_editor_property("groom_strength", 1.0)
tail_debug_fur.set_editor_property("shell_count", 24)
tail_debug_fur.set_editor_property("use_map_controls", True)
tail_debug_fur.set_pose_source(tail_source)
tail_debug_fur.rebuild_fur()
assert tail_debug_fur.refresh_preview_pose()
for layer in tail_debug_fur.get_editor_property("skeletal_shells"):
    layer.get_material(0).set_scalar_parameter_value(
        "UseRetailDecodeCorrection", 1.0)
head_debug_fur = actors.spawn_actor_from_class(
    unreal.SkeletalFurAuthoringActor, unreal.Vector())
head_debug_fur.set_actor_label("Ratchet Head Shell Unlit Diagnostic")
head_debug_fur.set_editor_property("fur_material", head_debug_material)
head_debug_fur.set_editor_property("length", 3.0)
head_debug_fur.set_editor_property("recovered_density", 16.0)
head_debug_fur.set_editor_property("groom_strength", 1.0)
head_debug_fur.set_editor_property("shell_count", 32)
head_debug_fur.set_editor_property("use_map_controls", True)
head_debug_fur.set_pose_source(part_sources["head"])
head_debug_fur.rebuild_fur()
assert head_debug_fur.refresh_preview_pose()
for layer in head_debug_fur.get_editor_property("skeletal_shells"):
    layer.get_material(0).set_scalar_parameter_value(
        "UseRetailDecodeCorrection", 1.0)
tail_layers = list(tail_fur.get_editor_property("skeletal_shells"))
if len(tail_layers) != 24:
    raise RuntimeError(f"Expected 24 live tail shell layers, found {len(tail_layers)}")
tail_layer_materials = [layer.get_material(0) for layer in tail_layers]
tail_shell_diagnostics = {
    "source_material_slots": tail_source.get_num_materials(),
    "layers": len(tail_layers),
    "material_asset": part_materials["tail"].get_path_name(),
    "material_two_sided": part_materials["tail"].get_editor_property("two_sided"),
    "layer_material_paths": sorted({material.get_path_name() for material in tail_layer_materials}),
    "shell_depths": [material.get_scalar_parameter_value("ShellDepth")
                     for material in tail_layer_materials],
    "fur_lengths_cm": sorted({material.get_scalar_parameter_value("FurLength")
                               for material in tail_layer_materials}),
    "recovered_densities": sorted({material.get_scalar_parameter_value("RecoveredDensity")
                                    for material in tail_layer_materials}),
}

for actor in actors.get_all_level_actors():
    if isinstance(actor, (unreal.DirectionalLight, unreal.SkyLight)):
        actors.destroy_actor(actor)

groups = [
    ("Retail Event 24825 Tail Strands", "/Game/FurValidation/Strands/DA_RatchetTailRetail24825",
     "/Game/FurValidation/Materials/M_RatchetTailStrands_v8", 0.7029384789),
    ("Retail Event 24831 Sparse Head Strands", "/Game/FurValidation/Strands/DA_RatchetHeadSparseRetail24831",
     "/Game/FurValidation/Materials/M_RatchetHeadSparseStrands_v8", 1.1680540736),
    ("Retail Event 24844 Ear Strands", "/Game/FurValidation/Strands/DA_RatchetEarRetail24844",
     "/Game/FurValidation/Materials/M_RatchetStrandAccent_v13", 1.3990770295),
]
grooms = []
for label, asset_path, material_path, _ in groups:
    actor = actors.spawn_actor_from_class(unreal.StrandGroomActor, unreal.Vector())
    actor.set_actor_label(label)
    actor.set_editor_property("groom_asset", unreal.load_asset(asset_path))
    actor.set_editor_property("strand_material", unreal.load_asset(material_path))
    actor.set_editor_property(
        "binding_mesh", body_actors[0].get_editor_property("skeletal_mesh_component"))
    actor.set_editor_property("strand_width", 1.0)
    actor.set_editor_property("wind_strength", 0.0)
    actor.set_editor_property("wind_direction", unreal.Vector(-0.9974102378, -0.0719231740, 0.0))
    actor.set_editor_property("wind_turbulence", 0.0
    )
    actor.set_editor_property("stiffness_inverse_length", 20.0)
    actor.set_editor_property("stiffness_power", 2.0)
    actor.set_editor_property("drag", 0.5)
    actor.rebuild_groom()
    actor.set_strand_lighting(
        unreal.Vector(0.45, -0.35, 0.82),
        unreal.LinearColor(0.65, 0.61, 0.57, 1.0))
    grooms.append(actor)

light = actors.spawn_actor_from_class(
    unreal.DirectionalLight, unreal.Vector(),
    unreal.Rotator(-35.0, 145.0, 0.0))
light.light_component.set_intensity(0.8)
light.light_component.set_light_color(unreal.LinearColor(1.0, 0.86, 0.72, 1.0))
fill = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector())
fill.light_component.set_intensity(0.1)
lighting = actors.spawn_actor_from_class(unreal.FurLightingController, unreal.Vector())
lighting.set_editor_property("key_light", light)
lighting.set_editor_property("targets", list(part_fur.values()))
lighting.set_editor_property("enable_shadows", False)
lighting.refresh_lighting()
scene_material = next(iter(part_fur.values())).get_editor_property(
    "skeletal_shells")[0].get_material(0)
if scene_material is None:
    raise RuntimeError("Could not resolve a lit shell MID for strand lighting")
for strand_actor in grooms:
    strand_builder.copy_scene_lighting(scene_material, strand_actor)

eye = unreal.Vector(215.0, -285.0, 115.0)
target = unreal.Vector(0.0, -18.0, 72.0)
camera = actors.spawn_actor_from_class(
    unreal.CameraActor, eye, unreal.MathLibrary.find_look_at_rotation(eye, target))
camera.camera_component.set_field_of_view(38.0)
camera.camera_component.set_editor_property("constrain_aspect_ratio", False)
level.pilot_level_actor(camera)
level.editor_set_game_view(True)
camera_fill = actors.spawn_actor_from_class(unreal.PointLight, eye)
camera_fill.light_component.set_intensity(10.0)
camera_fill.light_component.set_attenuation_radius(500.0)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def command(value):
    unreal.SystemLibrary.execute_console_command(world, value)


for value in (
        "t.MaxFPS 10", "r.EyeAdaptationQuality 0", "ShowFlag.EyeAdaptation 0",
        "ShowFlag.Tonemapper 0", "r.BloomQuality 0", "r.MotionBlurQuality 0",
        "r.ScreenPercentage 100", "r.AntiAliasingMethod 2", "r.TemporalAASamples 8"):
    command(value)

labels = [
    "body-only", "tail-shell-only", "combined-dry-full", "head-close-dry",
    "head-close-base-only", "head-close-shell-only",
    "head-close-shell-unlit-debug",
    "head-close-head-strands-only", "head-close-ear-strands-only",
    "head-close-combined-restored",
    "tail-close-base-only", "tail-close-shell-only", "tail-close-shell-unlit-debug",
    "tail-close-dry",
    "tail-close-wind-first-response", "tail-close-wind-settled",
    "tail-close-wind-reversed-first-response", "tail-close-wet-dry",
    "tail-close-wet-wind"]
for groom in grooms:
    groom.set_actor_hidden_in_game(True)
for fur_actor in part_fur.values():
    fur_actor.set_actor_hidden_in_game(True)
tail_debug_fur.set_actor_hidden_in_game(True)
head_debug_fur.set_actor_hidden_in_game(True)
unreal.FurViewportProbe.enable_world_ticks(True)
started = time.monotonic()
state = dict(stage=0, last=started, draw=started, busy=False, done=False, captures=[])


def stop():
    state["done"] = True
    unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state["handle"])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    command("QUIT_EDITOR")


def tick(delta):
    if state["done"] or state["busy"]:
        return
    state["busy"] = True
    try:
        now = time.monotonic()
        if now - started > 240:
            raise RuntimeError("Full-body registration capture timeout")
        if now - state["draw"] >= 0.1:
            assert unreal.FurViewportProbe.advance()
            state["draw"] = now
        stage = state["stage"]
        waits = {
            "tail-close-wind-first-response": 0.12,
            "tail-close-wind-settled": 2.0,
            "tail-close-wind-reversed-first-response": 0.12,
        }
        if now - state["last"] < (20 if stage == 0 else waits.get(labels[stage], 8)):
            return
        assert unreal.FurViewportProbe.advance()
        row = json.loads(unreal.FurViewportProbe.capture(str(out / (labels[stage] + ".png"))))
        row["label"] = labels[stage]
        row["strand_max_displacement_cm"] = [
            groom.get_maximum_displacement_cm() for groom in grooms]
        state["captures"].append(row)
        next_stage = stage + 1
        if next_stage == len(labels):
            report = {
                "source_asset": "ADE5909F821E9DDE",
                "skeletal_parts": len(body_actors),
                "bones_per_part": body_actors[0].get_editor_property(
                    "skeletal_mesh_component").get_num_bones(),
                "hidden_composite_shell_indices": composite_shell_indices,
                "retail_base_material_subsets": len(body_actors) - len(unmapped_subsets),
                "subset_material_indices": subset_material_indices,
                "unmapped_subsets": unmapped_subsets,
                "source_events": [24825, 24831, 24844],
                "authored_guide_range": 5523,
                "captured_work_items": 2882,
                "rendered_ribbons": 22114,
                "projectable_vertices": 740904,
                "tail_shell_diagnostics": tail_shell_diagnostics,
                "fur_surface_settings": part_specs,
                "groups": [
                    {"event": 24825, "authored_guides": 633, "captured_work_items": 463,
                     "children": 35, "tessellation": 11, "projectable_vertices": 583380,
                     "captured_max_wind_offset_cm": 0.7029384789},
                    {"event": 24831, "authored_guides": 2109, "captured_work_items": 119,
                     "children": 11, "tessellation": 11, "projectable_vertices": 47124,
                     "captured_max_wind_offset_cm": 1.1680540736},
                    {"event": 24844, "authored_guides": 2781, "captured_work_items": 2300,
                     "unique_visible_guides": 2277, "duplicate_work_items": 23,
                     "children": 2, "tessellation": 8, "projectable_vertices": 110400,
                     "captured_max_wind_offset_cm": 1.3990770295},
                ],
                "captures": state["captures"],
                "limits": "Registration view uses exact decoded body geometry, skin weights, bind-pose grooms, captured retail base-color maps where decoded, fur-control maps, captured work queues, exact skeletal root binding, and the CPU-validated retail wind equations. Retail normal/specular/mask channel semantics and the six utility/stitch subsets without decoded base color are not yet reproduced.",
            }
            (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            stop()
            return
        next_label = labels[next_stage]
        if next_label == "tail-shell-only":
            body_actors[12].set_actor_hidden_in_game(True)
            tail_fur.set_actor_hidden_in_game(False)
        elif next_label == "combined-dry-full":
            body_actors[12].set_actor_hidden_in_game(False)
            for fur_actor in part_fur.values():
                fur_actor.set_actor_hidden_in_game(False)
            for groom in grooms:
                groom.set_actor_hidden_in_game(False)
        elif next_label == "head-close-dry":
            head_eye = unreal.Vector(89.6394883, 43.4770155, 162.9388489)
            head_target = unreal.Vector(0.0, -8.2763672, 114.6728516)
            camera.set_actor_location_and_rotation(
                head_eye, unreal.MathLibrary.find_look_at_rotation(head_eye, head_target), False, False)
            camera_fill.set_actor_location(head_eye, False, False)
            camera.camera_component.set_field_of_view(60.0)
        elif next_label == "head-close-base-only":
            for groom in grooms:
                groom.set_actor_hidden_in_game(True)
            for fur_actor in part_fur.values():
                fur_actor.set_actor_hidden_in_game(True)
        elif next_label == "head-close-shell-only":
            part_fur["head"].set_actor_hidden_in_game(False)
        elif next_label == "head-close-shell-unlit-debug":
            part_fur["head"].set_actor_hidden_in_game(True)
            head_debug_fur.set_actor_hidden_in_game(False)
        elif next_label == "head-close-head-strands-only":
            head_debug_fur.set_actor_hidden_in_game(True)
            grooms[1].set_actor_hidden_in_game(False)
        elif next_label == "head-close-ear-strands-only":
            grooms[1].set_actor_hidden_in_game(True)
            grooms[2].set_actor_hidden_in_game(False)
        elif next_label == "head-close-combined-restored":
            for fur_actor in part_fur.values():
                fur_actor.set_actor_hidden_in_game(False)
            for groom in grooms:
                groom.set_actor_hidden_in_game(False)
        elif next_label == "tail-close-base-only":
            tail_eye = unreal.Vector(58.0, -18.0, 88.0)
            tail_target = unreal.Vector(0.0, -59.0, 60.0)
            camera.set_actor_location_and_rotation(
                tail_eye, unreal.MathLibrary.find_look_at_rotation(tail_eye, tail_target), False, False)
            camera_fill.set_actor_location(tail_eye, False, False)
            camera_fill.set_actor_hidden_in_game(True)
            camera.camera_component.set_field_of_view(42.0)
            for groom in grooms:
                groom.set_actor_hidden_in_game(True)
            for fur_actor in part_fur.values():
                fur_actor.set_actor_hidden_in_game(True)
        elif next_label == "tail-close-shell-only":
            body_actors[12].set_actor_hidden_in_game(True)
            tail_fur.set_actor_hidden_in_game(False)
        elif next_label == "tail-close-shell-unlit-debug":
            tail_fur.set_actor_hidden_in_game(True)
            tail_debug_fur.set_actor_hidden_in_game(False)
        elif next_label == "tail-close-dry":
            tail_debug_fur.set_actor_hidden_in_game(True)
            for fur_actor in part_fur.values():
                fur_actor.set_actor_hidden_in_game(False)
            body_actors[12].set_actor_hidden_in_game(False)
            for groom in grooms:
                groom.set_actor_hidden_in_game(False)
        elif next_label == "tail-close-wind-first-response":
            for groom in grooms:
                groom.reset_simulation()
                groom.set_editor_property(
                    "wind_timer_offset",
                    981.7157592773438 - unreal.SystemLibrary.get_game_time_in_seconds(world))
                groom.set_strand_weather(0.0, 0.0370904393)
            for fur_actor in part_fur.values():
                fur_actor.set_weather(0.0, 0.0370904393)
        elif next_label == "tail-close-wind-reversed-first-response":
            for groom in grooms:
                groom.set_strand_weather(0.0, 0.0)
                groom.reset_simulation()
                groom.set_editor_property(
                    "wind_direction", unreal.Vector(0.9974102378, 0.0719231740, 0.0))
                groom.set_editor_property(
                    "wind_timer_offset",
                    981.7157592773438 - unreal.SystemLibrary.get_game_time_in_seconds(world))
                groom.set_strand_weather(0.0, 0.0370904393)
            for fur_actor in part_fur.values():
                fur_actor.set_editor_property(
                    "wind_direction", unreal.Vector(0.9974102378, 0.0719231740, 0.0))
        elif next_label == "tail-close-wet-dry":
            for groom in grooms:
                groom.set_strand_weather(1.0, 0.0)
                groom.reset_simulation()
            for fur_actor in part_fur.values():
                fur_actor.set_weather(1.0, 0.0)
        elif next_label == "tail-close-wet-wind":
            for groom in grooms:
                groom.set_strand_weather(1.0, 0.0370904393)
            for fur_actor in part_fur.values():
                fur_actor.set_weather(1.0, 0.0370904393)
        state.update(stage=next_stage, last=time.monotonic())
    except Exception:
        unreal.log_error(traceback.format_exc())
        stop()
    finally:
        state["busy"] = False


state["handle"] = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
