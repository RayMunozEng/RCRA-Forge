"""Render the exact event-24844 Ratchet ear guides over the recovered shell fur."""

import importlib.util
import json
from pathlib import Path
import time
import unreal

root = Path(__file__).resolve().parent
dynamics_fixture = "ratchet"
setup_path = root / "capture_reference_dynamics.py"
setup = setup_path.read_text(encoding="utf-8").split("labels=", 1)[0]
exec(compile(setup, str(setup_path), "exec"), globals())

guide_path = root / "recovered/native-strand-pipeline/ratchet-ear-guides-bind-visible.json"
guide_data = json.loads(guide_path.read_text(encoding="utf-8"))
assert guide_data["source_event"] == 24844
assert guide_data["source_buffer_event"] == 24756
assert guide_data["coordinate_space"] == "pre-skinning bind pose"
assert guide_data["valid_guides"] == 2300
assert guide_data["control_vertices"] == 16100
assert guide_data["captured_visible_unique_guides"] == 2277
assert guide_data["captured_visible_duplicate_entries"] == 23

sparse_path = root / "recovered/native-strand-pipeline/ratchet-head-sparse-guides-bind-visible.json"
sparse_data = json.loads(sparse_path.read_text(encoding="utf-8"))
assert sparse_data["source_event"] == 24831
assert sparse_data["source_buffer_event"] == 24748
assert sparse_data["coordinate_space"] == "pre-skinning bind pose"
assert sparse_data["valid_guides"] == 119
assert sparse_data["control_vertices"] == 1428

tail_path = root / "recovered/native-strand-pipeline/ratchet-tail-guides-bind-visible.json"
tail_data = json.loads(tail_path.read_text(encoding="utf-8"))
assert tail_data["source_event"] == 24825
assert tail_data["source_buffer_event"] == 24743
assert tail_data["coordinate_space"] == "pre-skinning bind pose"
assert tail_data["valid_guides"] == 463
assert tail_data["control_vertices"] == 2315


def load_bindings(group):
    path = root / f"recovered/native-strand-pipeline/ratchet-{group}-skeletal-bindings.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["source_capture_sha256"] == guide_data["source_capture_sha256"]
    return {row["source_strand_index"]: row for row in document["bindings"]}


binding_maps = {
    "ears": load_bindings("ears"),
    "head-sparse": load_bindings("head-sparse"),
    "tail": load_bindings("tail"),
}


def make_bone_influences(group, source_strand_index):
    binding = binding_maps[group][source_strand_index]
    result = []
    for source in binding["bone_influences"]:
        influence = unreal.StrandGroomBoneInfluence()
        influence.set_editor_property("bone", source["bone"])
        influence.set_editor_property("weight", source["weight"])
        result.append(influence)
    return result

asset_path = "/Game/FurValidation/Strands"
asset_name = "DA_RatchetEarRetail24844"
full_asset_path = asset_path + "/" + asset_name
groom_asset = unreal.load_asset(full_asset_path)
if groom_asset is None:
    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", unreal.StrandGroomAsset)
    groom_asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        asset_name, asset_path, unreal.StrandGroomAsset, factory)
if groom_asset is None:
    raise RuntimeError("Could not create " + full_asset_path)

guides = []
for source in guide_data["guides"]:
    guide = unreal.StrandGroomGuide()
    guide.set_editor_property("control_vertices", [
        unreal.Vector(*point) for point in source["control_vertices_cm"]])
    guide.set_editor_property("root_normal", unreal.Vector(*source["root_normal"]))
    guide.set_editor_property("root_frame_y", unreal.Vector(*source["root_frame_y"]))
    guide.set_editor_property("root_uv", unreal.Vector2D(*source["packed_uv_or_seed"]))
    guide.set_editor_property("width_scale", 1.0)
    guide.set_editor_property("bone_influences", make_bone_influences(
        "ears", source["source_strand_index"]))
    guides.append(guide)
groom_asset.set_editor_property("guides", guides)
groom_asset.set_editor_property("tessellation", 8)
groom_asset.set_editor_property("strands_per_clump", 2)
groom_asset.set_editor_property("captured_max_wind_offset_cm", 1.3990770295)
if not unreal.EditorAssetLibrary.save_loaded_asset(groom_asset):
    raise RuntimeError("Could not save " + full_asset_path)

builder_path = root.parent / "plugins/FurAuthoring/Content/Python/create_strand_groom.py"
spec = importlib.util.spec_from_file_location("strand_builder", builder_path)
strand_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strand_builder)
texture_path = "/Game/FurValidation/Strands/T_RatchetEarFurTint"
strand_texture = unreal.load_asset(texture_path)
if strand_texture is None:
    texture_source = root / "recovered/native-strand-pipeline/DiffuseTexture.png"
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(texture_source))
    task.set_editor_property("destination_path", "/Game/FurValidation/Strands")
    task.set_editor_property("destination_name", "T_RatchetEarFurTint")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    strand_texture = unreal.load_asset(texture_path)
if strand_texture is None:
    raise RuntimeError("Could not import the recovered retail fur-tint texture")
strand_texture.set_editor_property("srgb", True)
unreal.EditorAssetLibrary.save_loaded_asset(strand_texture)
strand_material = strand_builder.create_material(
    strand_texture, profile="ears", name="M_RatchetStrandAccent_v13")

sparse_asset_name = "DA_RatchetHeadSparseRetail24831"
sparse_full_path = asset_path + "/" + sparse_asset_name
sparse_asset = unreal.load_asset(sparse_full_path)
if sparse_asset is None:
    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", unreal.StrandGroomAsset)
    sparse_asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        sparse_asset_name, asset_path, unreal.StrandGroomAsset, factory)
if sparse_asset is None:
    raise RuntimeError("Could not create " + sparse_full_path)
sparse_guides = []
for source in sparse_data["guides"]:
    guide = unreal.StrandGroomGuide()
    guide.set_editor_property("control_vertices", [
        unreal.Vector(*point) for point in source["control_vertices_cm"]])
    guide.set_editor_property("root_normal", unreal.Vector(*source["root_normal"]))
    guide.set_editor_property("root_frame_y", unreal.Vector(*source["root_frame_y"]))
    guide.set_editor_property("root_uv", unreal.Vector2D(*source["packed_uv_or_seed"]))
    guide.set_editor_property("width_scale", 1.0)
    guide.set_editor_property("bone_influences", make_bone_influences(
        "head-sparse", source["source_strand_index"]))
    sparse_guides.append(guide)
sparse_asset.set_editor_property("guides", sparse_guides)
sparse_asset.set_editor_property("tessellation", 11)
sparse_asset.set_editor_property("strands_per_clump", 11)
sparse_asset.set_editor_property("captured_max_wind_offset_cm", 1.1680540736)
if not unreal.EditorAssetLibrary.save_loaded_asset(sparse_asset):
    raise RuntimeError("Could not save " + sparse_full_path)

mask_texture_path = "/Game/FurValidation/Strands/T_RatchetHeadFurMask"
mask_texture = unreal.load_asset(mask_texture_path)
if mask_texture is None:
    mask_task = unreal.AssetImportTask()
    mask_task.set_editor_property(
        "filename", str(root / "recovered/native-strand-pipeline/StrandThicknessTexture.png"))
    mask_task.set_editor_property("destination_path", "/Game/FurValidation/Strands")
    mask_task.set_editor_property("destination_name", "T_RatchetHeadFurMask")
    mask_task.set_editor_property("automated", True)
    mask_task.set_editor_property("replace_existing", True)
    mask_task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([mask_task])
    mask_texture = unreal.load_asset(mask_texture_path)
if mask_texture is None:
    raise RuntimeError("Could not import the recovered retail head fur mask")
mask_texture.set_editor_property("srgb", False)
unreal.EditorAssetLibrary.save_loaded_asset(mask_texture)
sparse_material = strand_builder.create_material(
    strand_texture, mask_texture, profile="head-sparse",
    name="M_RatchetHeadSparseStrands_v8")

tail_asset_name = "DA_RatchetTailRetail24825"
tail_full_path = asset_path + "/" + tail_asset_name
tail_asset = unreal.load_asset(tail_full_path)
if tail_asset is None:
    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", unreal.StrandGroomAsset)
    tail_asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        tail_asset_name, asset_path, unreal.StrandGroomAsset, factory)
if tail_asset is None:
    raise RuntimeError("Could not create " + tail_full_path)
tail_guides = []
for source in tail_data["guides"]:
    guide = unreal.StrandGroomGuide()
    guide.set_editor_property("control_vertices", [
        unreal.Vector(*point) for point in source["control_vertices_cm"]])
    guide.set_editor_property("root_normal", unreal.Vector(*source["root_normal"]))
    guide.set_editor_property("root_frame_y", unreal.Vector(*source["root_frame_y"]))
    guide.set_editor_property("root_uv", unreal.Vector2D(*source["packed_uv_or_seed"]))
    guide.set_editor_property("width_scale", 1.0)
    guide.set_editor_property("bone_influences", make_bone_influences(
        "tail", source["source_strand_index"]))
    tail_guides.append(guide)
tail_asset.set_editor_property("guides", tail_guides)
tail_asset.set_editor_property("tessellation", 11)
tail_asset.set_editor_property("strands_per_clump", 35)
tail_asset.set_editor_property("captured_max_wind_offset_cm", 0.7029384789)
if not unreal.EditorAssetLibrary.save_loaded_asset(tail_asset):
    raise RuntimeError("Could not save " + tail_full_path)


def import_texture(source, destination_name, srgb):
    destination = "/Game/FurValidation/Strands/" + destination_name
    texture = unreal.load_asset(destination)
    if texture is None:
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(source))
        task.set_editor_property("destination_path", "/Game/FurValidation/Strands")
        task.set_editor_property("destination_name", destination_name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        texture = unreal.load_asset(destination)
    if texture is None:
        raise RuntimeError("Could not import " + str(source))
    texture.set_editor_property("srgb", srgb)
    unreal.EditorAssetLibrary.save_loaded_asset(texture)
    return texture


tail_diffuse = import_texture(
    root / "recovered/native-strand-pipeline/tail-DiffuseTexture.png",
    "T_RatchetTailFurTint", True)
tail_mask = import_texture(
    root / "recovered/native-strand-pipeline/tail-StrandThicknessTexture.png",
    "T_RatchetTailFurMask", False)
tail_material = strand_builder.create_material(
    tail_diffuse, tail_mask, profile="tail", name="M_RatchetTailStrands_v8")

groom = actors.spawn_actor_from_class(unreal.StrandGroomActor, unreal.Vector())
groom.set_actor_label("Retail Event 24844 Ear Strands")
groom.set_editor_property("groom_asset", groom_asset)
groom.set_editor_property("strand_material", strand_material)
groom.set_editor_property("root_color", unreal.LinearColor(0.2140341, 0.2140341, 0.2140341, 1))
groom.set_editor_property("tip_color", unreal.LinearColor(0.2140341, 0.2140341, 0.2140341, 1))
groom.set_editor_property("strand_width", 1.0)
groom.set_editor_property("wind_strength", 0.0)
groom.set_editor_property("wind_direction", unreal.Vector(
    -0.9974102378, -0.0719231740, 0.0))
groom.set_editor_property("wind_turbulence", 0.0)
groom.set_editor_property("stiffness_inverse_length", 20.0)
groom.set_editor_property("stiffness_power", 2.0)
groom.set_editor_property("drag", 0.5)
groom.rebuild_groom()
head_groom = actors.spawn_actor_from_class(unreal.StrandGroomActor, unreal.Vector())
head_groom.set_actor_label("Retail Event 24831 Sparse Head Strands")
head_groom.set_editor_property("groom_asset", sparse_asset)
head_groom.set_editor_property("strand_material", sparse_material)
head_groom.set_editor_property("strand_width", 1.0)
head_groom.set_editor_property("wind_strength", 0.0)
head_groom.set_editor_property("wind_direction", unreal.Vector(
    -0.9974102378, -0.0719231740, 0.0))
head_groom.set_editor_property("wind_turbulence", 0.0)
head_groom.set_editor_property("stiffness_inverse_length", 20.0)
head_groom.set_editor_property("stiffness_power", 2.0)
head_groom.set_editor_property("drag", 0.5)
head_groom.rebuild_groom()
tail_groom = actors.spawn_actor_from_class(unreal.StrandGroomActor, unreal.Vector())
tail_groom.set_actor_label("Retail Event 24825 Tail Strands")
tail_groom.set_editor_property("groom_asset", tail_asset)
tail_groom.set_editor_property("strand_material", tail_material)
tail_groom.set_editor_property("strand_width", 1.0)
tail_groom.set_editor_property("wind_strength", 0.0)
tail_groom.set_editor_property("wind_direction", unreal.Vector(
    -0.9974102378, -0.0719231740, 0.0))
tail_groom.set_editor_property("wind_turbulence", 0.0)
tail_groom.set_editor_property("stiffness_inverse_length", 20.0)
tail_groom.set_editor_property("stiffness_power", 2.0)
tail_groom.set_editor_property("drag", 0.5)
tail_groom.rebuild_groom()
shell_material = fur.get_editor_property("shells").get_material(0)
key = shell_material.get_vector_parameter_value("SceneKeyDirection")
radiance = shell_material.get_vector_parameter_value("SceneKeyRadiance")
groom.set_strand_lighting(
    unreal.Vector(key.r, key.g, key.b),
    unreal.LinearColor(radiance.r, radiance.g, radiance.b, 1.0))
head_groom.set_strand_lighting(
    unreal.Vector(key.r, key.g, key.b),
    unreal.LinearColor(radiance.r, radiance.g, radiance.b, 1.0))
tail_groom.set_strand_lighting(
    unreal.Vector(key.r, key.g, key.b),
    unreal.LinearColor(radiance.r, radiance.g, radiance.b, 1.0))
for strand_actor in (groom, head_groom, tail_groom):
    strand_builder.copy_scene_lighting(shell_material, strand_actor)

out = root / "recovered/retail-ear-strands"
out.mkdir(exist_ok=True)
labels = [
    "shell-only", "combined-dry-a", "combined-dry-b",
    "combined-wind-a", "combined-wind-b", "combined-wind-turned",
    "combined-wet"]
groom.set_actor_hidden_in_game(True)
head_groom.set_actor_hidden_in_game(True)
tail_groom.set_actor_hidden_in_game(True)
unreal.FurViewportProbe.enable_world_ticks(True)
started = time.monotonic()
state = dict(stage=0, last=started, draw=started, busy=False, done=False, rows=[])


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
        if now - started > 180:
            raise RuntimeError("Retail ear strand capture timeout")
        if now - state["draw"] >= 0.1:
            assert unreal.FurViewportProbe.advance()
            state["draw"] = now
        stage = state["stage"]
        if now - state["last"] < (20 if stage == 0 else 8):
            return
        assert unreal.FurViewportProbe.advance()
        row = json.loads(unreal.FurViewportProbe.capture(str(out / (labels[stage] + ".png"))))
        assert row["draw_realtime"] and row["resolved_aa_method"] == 2, row
        row.update(label=labels[stage], source_events=[24825, 24831, 24844],
                   authored_guide_range=5523, captured_work_items=2882,
                   rendered_ribbons=22114, projectable_vertices=740904,
                   strand_wetness=[actor.get_editor_property("ribbons")
                       .get_material(0).get_scalar_parameter_value("Wetness")
                       for actor in (groom, head_groom, tail_groom)],
                   groups=[
                       dict(event=24825, authored_guides=633, captured_work_items=463,
                            children=35, tessellation=11, projectable_vertices=583380),
                       dict(event=24831, authored_guides=2109, captured_work_items=119,
                            children=11, tessellation=11, projectable_vertices=47124),
                       dict(event=24844, authored_guides=2781, captured_work_items=2300,
                            unique_visible_guides=2277, duplicate_work_items=23,
                            children=2, tessellation=8, projectable_vertices=110400)])
        state["rows"].append(row)
        next_stage = stage + 1
        if next_stage == len(labels):
            report = dict(
                source_capture_sha256=guide_data["source_capture_sha256"],
                source_event=24844,
                source_events=[24825, 24831, 24844],
                source_buffer_event=24756,
                source_buffer_events=[24743, 24748, 24756],
                coordinate_space=guide_data["coordinate_space"],
                captured_control_vertices=19843,
                authored_guide_range=5523,
                captured_work_items=2882,
                rendered_ribbons=22114,
                projectable_vertices=740904,
                groups=[
                    dict(event=24825, authored_guides=633, captured_work_items=463,
                         control_vertices=3165, captured_visible_control_vertices=2315,
                         children=35, tessellation=11, projectable_vertices=583380),
                    dict(event=24831, authored_guides=2109, captured_work_items=119,
                         authored_control_vertices=25308, captured_control_vertices=1428,
                         children=11, tessellation=11, projectable_vertices=47124),
                    dict(event=24844, authored_guides=2781, captured_work_items=2300,
                         unique_visible_guides=2277, duplicate_work_items=23,
                         authored_control_vertices=19467, captured_control_vertices=16100,
                         children=2, tessellation=8, projectable_vertices=110400)],
                retail_clump_thickness_cm=[
                    [0.0, 0.5, 0.5],
                    [0.1618536413, 0.5, 0.5],
                    [0.5918343067, 0.2928571543, 0.2714285859],
                    [1.0, 0.1000000047, 0.1285714330],
                ],
                retail_diffuse_texture=dict(
                    name="hero_ratchet_head_furtint_c.texture",
                    size=[128, 128],
                    format="BC7_SRGB",
                    native_sha256="602c08b1bd59ba7d692f5b610c45c708a6ed8ab1af91985077f943f667283dc0"),
                captures=state["rows"],
                limits="Geometry, topology, width curve, root UVs, fur tint, and hair lighting are capture-derived. CPU dynamics preserve recovered stiffness/drag/wind inputs but are not yet an instruction-equivalent port of the retail GPU solver.")
            (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            stop()
            return
        if next_stage == 1:
            groom.set_actor_hidden_in_game(False)
            head_groom.set_actor_hidden_in_game(False)
            tail_groom.set_actor_hidden_in_game(False)
        elif next_stage == 3:
            fur.set_weather(0.0, 0.0370904393)
            groom.set_strand_weather(0.0, 0.0370904393)
            head_groom.set_strand_weather(0.0, 0.0370904393)
            tail_groom.set_strand_weather(0.0, 0.0370904393)
        elif next_stage == 5:
            groom.set_editor_property("wind_direction", unreal.Vector(
                0.9974102378, 0.0719231740, 0.0))
            head_groom.set_editor_property("wind_direction", unreal.Vector(
                0.9974102378, 0.0719231740, 0.0))
            tail_groom.set_editor_property("wind_direction", unreal.Vector(
                0.9974102378, 0.0719231740, 0.0))
        elif next_stage == 6:
            fur.set_weather(0.8, 0.0370904393)
            groom.set_strand_weather(0.8, 0.0370904393)
            head_groom.set_strand_weather(0.8, 0.0370904393)
            tail_groom.set_strand_weather(0.8, 0.0370904393)
        state.update(stage=next_stage, last=time.monotonic())
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc())
        stop()
    finally:
        state["busy"] = False


state["handle"] = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
