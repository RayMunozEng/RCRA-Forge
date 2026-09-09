"""Validate sparse-head and ear retail guides under controlled bone motion."""

import json
import math
from pathlib import Path
import re
import time
import traceback

import unreal


root = Path(__file__).resolve().parent
out = root / "recovered/ratchet-head-binding"
out.mkdir(exist_ok=True)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level.new_level("/Game/FurValidation/RatchetHeadBinding")
for inherited in actors.get_all_level_actors():
    inherited.set_actor_hidden_in_game(True)

paths = unreal.EditorAssetLibrary.list_assets(
    "/Game/FurValidation/RatchetBodyV2/RatchetRetailLOD0/SkeletalMeshes",
    recursive=True)
head_path = next(path for path in paths if re.search(r"subset26-", path))
head_mesh = unreal.load_asset(head_path)
pose_actor = actors.spawn_actor_from_class(
    unreal.PoseableGroomBindingActor, unreal.Vector())
pose = pose_actor.get_editor_property("pose_mesh")
pose.set_skinned_asset_and_update(head_mesh, True)

specs = [
    ("head", "/Game/FurValidation/Strands/DA_RatchetHeadSparseRetail24831",
     "/Game/FurValidation/Materials/M_RatchetHeadSparseStrands_v8"),
    ("ears", "/Game/FurValidation/Strands/DA_RatchetEarRetail24844",
     "/Game/FurValidation/Materials/M_RatchetStrandAccent_v13"),
]
grooms = {}
for name, asset_path, material_path in specs:
    actor = actors.spawn_actor_from_class(unreal.StrandGroomActor, unreal.Vector())
    actor.set_actor_label("Retail Ratchet " + name.title() + " Binding")
    actor.set_editor_property("groom_asset", unreal.load_asset(asset_path))
    actor.set_editor_property("strand_material", unreal.load_asset(material_path))
    actor.set_editor_property("binding_mesh", pose)
    actor.set_editor_property("strand_width", 1.0)
    actor.set_editor_property("wind_strength", 0.0)
    actor.rebuild_groom()
    actor.set_strand_lighting(
        unreal.Vector(0.45, -0.35, 0.82),
        unreal.LinearColor(0.65, 0.61, 0.57, 1.0))
    grooms[name] = actor

light = actors.spawn_actor_from_class(
    unreal.DirectionalLight, unreal.Vector(), unreal.Rotator(-35.0, 145.0, 0.0))
light.light_component.set_intensity(0.8)
eye = unreal.Vector(89.6394883, 43.4770155, 162.9388489)
target = unreal.Vector(0.0, -8.2763672, 114.6728516)
camera = actors.spawn_actor_from_class(
    unreal.CameraActor, eye, unreal.MathLibrary.find_look_at_rotation(eye, target))
camera.camera_component.set_field_of_view(60.0)
camera.camera_component.set_editor_property("constrain_aspect_ratio", False)
level.pilot_level_actor(camera)
level.editor_set_game_view(True)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def command(value):
    unreal.SystemLibrary.execute_console_command(world, value)


for value in (
        "t.MaxFPS 10", "r.EyeAdaptationQuality 0", "ShowFlag.EyeAdaptation 0",
        "ShowFlag.Tonemapper 0", "r.BloomQuality 0", "r.MotionBlurQuality 0",
        "r.ScreenPercentage 100", "r.AntiAliasingMethod 2", "r.TemporalAASamples 8"):
    command(value)


def groom_roots(groom):
    count = len(groom.get_editor_property("groom_asset").get_editor_property("guides"))
    return [groom.get_guide_root_world_position(index) for index in range(count)]


def groom_frames(groom, getter):
    count = len(groom.get_editor_property("groom_asset").get_editor_property("guides"))
    return [getattr(groom, getter)(index) for index in range(count)]


def distances(before, after):
    return [(a - b).length() for a, b in zip(before, after)]


def angles(before, after):
    result = []
    for a, b in zip(before, after):
        dot = a.x * b.x + a.y * b.y + a.z * b.z
        result.append(math.degrees(math.acos(max(-1.0, min(1.0, dot)))))
    return result


labels = [
    "bind-pose", "head-rotated", "head-restored",
    "left-ear-tip-rotated", "bind-pose-restored"]
unreal.FurViewportProbe.enable_world_ticks(True)
started = time.monotonic()
state = dict(stage=0, last=started, draw=started, busy=False, done=False,
             roots=[], normals=[], frame_ys=[], captures=[])


def stop():
    state["done"] = True
    unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state["handle"])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    command("QUIT_EDITOR")


def rotate(bone, degrees):
    initial = pose.get_bone_rotation_by_name(bone, unreal.BoneSpaces.COMPONENT_SPACE)
    changed = unreal.MathLibrary.compose_rotators(
        unreal.Rotator(degrees, 0.0, 0.0), initial)
    pose.set_bone_rotation_by_name(bone, changed, unreal.BoneSpaces.COMPONENT_SPACE)


def tick(delta):
    if state["done"] or state["busy"]:
        return
    state["busy"] = True
    try:
        now = time.monotonic()
        if now - started > 100:
            raise RuntimeError("Ratchet head binding capture timeout")
        if now - state["draw"] >= 0.1:
            assert unreal.FurViewportProbe.advance()
            state["draw"] = now
        stage = state["stage"]
        if now - state["last"] < (15 if stage == 0 else 5):
            return
        assert unreal.FurViewportProbe.advance()
        row = json.loads(unreal.FurViewportProbe.capture(
            str(out / (labels[stage] + ".png"))))
        row["label"] = labels[stage]
        state["captures"].append(row)
        state["roots"].append({name: groom_roots(groom)
                               for name, groom in grooms.items()})
        state["normals"].append({
            name: groom_frames(groom, "get_guide_root_world_normal")
            for name, groom in grooms.items()})
        state["frame_ys"].append({
            name: groom_frames(groom, "get_guide_root_world_frame_y")
            for name, groom in grooms.items()})
        next_stage = stage + 1
        if next_stage == len(labels):
            baseline, head_pose, head_reset, ear_pose, final = state["roots"]
            head_motion = distances(baseline["head"], head_pose["head"])
            head_restore = distances(baseline["head"], head_reset["head"])
            ear_motion = distances(head_reset["ears"], ear_pose["ears"])
            final_error = distances(baseline["ears"], final["ears"])
            normal_base, normal_head, normal_reset, normal_ear, normal_final = state["normals"]
            frame_base, frame_head, frame_reset, frame_ear, frame_final = state["frame_ys"]
            head_normal_motion = angles(normal_base["head"], normal_head["head"])
            head_normal_restore = angles(normal_base["head"], normal_reset["head"])
            head_frame_motion = angles(frame_base["head"], frame_head["head"])
            head_frame_restore = angles(frame_base["head"], frame_reset["head"])
            ear_normal_motion = angles(normal_reset["ears"], normal_ear["ears"])
            ear_normal_restore = angles(normal_base["ears"], normal_final["ears"])
            ear_frame_motion = angles(frame_reset["ears"], frame_ear["ears"])
            ear_frame_restore = angles(frame_base["ears"], frame_final["ears"])
            report = {
                "source_asset": "ADE5909F821E9DDE subset26",
                "source_events": [24831, 24844],
                "head_guides": len(head_motion),
                "ear_guides": len(ear_motion),
                "head_bone_rotation_degrees": 10.0,
                "head_moved_guides_over_0_001_cm": sum(x > 0.001 for x in head_motion),
                "head_maximum_root_motion_cm": max(head_motion),
                "head_maximum_restore_error_cm": max(head_restore),
                "head_maximum_root_normal_motion_degrees": max(head_normal_motion),
                "head_maximum_root_normal_restore_error_degrees": max(head_normal_restore),
                "head_maximum_root_frame_y_motion_degrees": max(head_frame_motion),
                "head_maximum_root_frame_y_restore_error_degrees": max(head_frame_restore),
                "left_ear_4_rotation_degrees": 15.0,
                "ear_moved_guides_over_0_001_cm": sum(x > 0.001 for x in ear_motion),
                "ear_maximum_root_motion_cm": max(ear_motion),
                "ear_maximum_restore_error_cm": max(final_error),
                "ear_root_normals_moved_over_0_01_degrees": sum(
                    x > 0.01 for x in ear_normal_motion),
                "ear_maximum_root_normal_motion_degrees": max(ear_normal_motion),
                "ear_maximum_root_normal_restore_error_degrees": max(ear_normal_restore),
                "ear_root_frame_y_moved_over_0_01_degrees": sum(
                    x > 0.01 for x in ear_frame_motion),
                "ear_maximum_root_frame_y_motion_degrees": max(ear_frame_motion),
                "ear_maximum_root_frame_y_restore_error_degrees": max(ear_frame_restore),
                "captures": state["captures"],
                "passed": (sum(x > 0.001 for x in head_motion) == len(head_motion)
                           and max(head_restore) < 0.001
                           and max(head_normal_motion) > 0.1
                           and max(head_frame_motion) > 0.1
                           and max(head_normal_restore) < 0.01
                           and max(head_frame_restore) < 0.01
                           and 100 < sum(x > 0.001 for x in ear_motion) < 2000
                           and max(ear_motion) > 0.1 and max(final_error) < 0.001
                           and max(ear_normal_motion) > 0.1
                           and max(ear_frame_motion) > 0.1
                           and max(ear_normal_restore) < 0.01
                           and max(ear_frame_restore) < 0.01),
                "limits": "Exact decoded retail bindings on subset26. Controlled head and LF_ear_4 rotations with wind disabled; root position plus both groom-frame axes must respond and reset.",
            }
            (out / "report.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8")
            stop()
            return
        if next_stage == 1:
            rotate("head", 10.0)
        elif next_stage == 2:
            pose.reset_bone_transform_by_name("head")
        elif next_stage == 3:
            rotate("LF_ear_4", 15.0)
        elif next_stage == 4:
            pose.reset_bone_transform_by_name("LF_ear_4")
        state.update(stage=next_stage, last=time.monotonic())
    except Exception:
        unreal.log_error(traceback.format_exc())
        stop()
    finally:
        state["busy"] = False


state["handle"] = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
