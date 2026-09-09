"""Prove exact retail tail guides follow the recovered skeletal binding."""

import json
import math
from pathlib import Path
import re
import time
import traceback

import unreal


root = Path(__file__).resolve().parent
out = root / "recovered/ratchet-strand-binding"
out.mkdir(exist_ok=True)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level.new_level("/Game/FurValidation/RatchetStrandBinding")
for inherited in actors.get_all_level_actors():
    inherited.set_actor_hidden_in_game(True)

asset_root = "/Game/FurValidation/RatchetBodyV2/RatchetRetailLOD0/SkeletalMeshes"
paths = unreal.EditorAssetLibrary.list_assets(asset_root, recursive=True)
tail_path = next(path for path in paths if re.search(r"subset12-", path))
tail_mesh = unreal.load_asset(tail_path)
if not isinstance(tail_mesh, unreal.SkeletalMesh):
    raise RuntimeError("Ratchet subset12 is not a skeletal mesh")

pose_actor = actors.spawn_actor_from_class(
    unreal.PoseableGroomBindingActor, unreal.Vector())
pose_actor.set_actor_label("Ratchet Tail Pose Source")
pose = pose_actor.get_editor_property("pose_mesh")
pose.set_skinned_asset_and_update(tail_mesh, True)

groom = actors.spawn_actor_from_class(unreal.StrandGroomActor, unreal.Vector())
groom.set_actor_label("Retail Event 24825 Tail Skeletal Binding")
groom.set_editor_property(
    "groom_asset", unreal.load_asset(
        "/Game/FurValidation/Strands/DA_RatchetTailRetail24825"))
groom.set_editor_property(
    "strand_material", unreal.load_asset(
        "/Game/FurValidation/Materials/M_RatchetTailStrands_v8"))
groom.set_editor_property("binding_mesh", pose)
groom.set_editor_property("strand_width", 1.0)
groom.set_editor_property("wind_strength", 0.0)
groom.rebuild_groom()
groom.set_strand_lighting(
    unreal.Vector(0.45, -0.35, 0.82),
    unreal.LinearColor(0.65, 0.61, 0.57, 1.0))

light = actors.spawn_actor_from_class(
    unreal.DirectionalLight, unreal.Vector(), unreal.Rotator(-35.0, 145.0, 0.0))
light.light_component.set_intensity(0.8)
camera = actors.spawn_actor_from_class(
    unreal.CameraActor, unreal.Vector(58.0, -18.0, 88.0),
    unreal.MathLibrary.find_look_at_rotation(
        unreal.Vector(58.0, -18.0, 88.0), unreal.Vector(0.0, -59.0, 60.0)))
camera.camera_component.set_field_of_view(42.0)
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

guide_rows = groom.get_editor_property("groom_asset").get_editor_property("guides")
guide_count = len(guide_rows)
bound_guide_count = sum(
    bool(guide.get_editor_property("bone_influences")) for guide in guide_rows)
labels = [
    "bind-pose", "tail-7-rotated", "tail-7-rotated-wind-first-response",
    "tail-7-rotated-wind-settled", "bind-pose-restored"]
unreal.FurViewportProbe.enable_world_ticks(True)
started = time.monotonic()
state = dict(stage=0, last=started, draw=started, busy=False, done=False,
             captures=[], roots=[], normals=[], frame_ys=[], bones=[])


def roots():
    return [groom.get_guide_root_world_position(index) for index in range(guide_count)]


def normals():
    return [groom.get_guide_root_world_normal(index) for index in range(guide_count)]


def frame_ys():
    return [groom.get_guide_root_world_frame_y(index) for index in range(guide_count)]


def stop():
    state["done"] = True
    unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state["handle"])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    command("QUIT_EDITOR")


def distance(a, b):
    return (a - b).length()


def angle_degrees(a, b):
    dot = a.x * b.x + a.y * b.y + a.z * b.z
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def bone_state():
    transform = pose.get_bone_transform_by_name(
        "tail_7", unreal.BoneSpaces.COMPONENT_SPACE)
    location = transform.translation
    rotation = transform.rotation.rotator()
    return {
        "location_cm": [location.x, location.y, location.z],
        "rotation_degrees": [rotation.pitch, rotation.yaw, rotation.roll],
    }


def tick(delta):
    if state["done"] or state["busy"]:
        return
    state["busy"] = True
    try:
        now = time.monotonic()
        if now - started > 90:
            raise RuntimeError("Ratchet strand binding capture timeout")
        if now - state["draw"] >= 0.1:
            assert unreal.FurViewportProbe.advance()
            state["draw"] = now
        stage = state["stage"]
        waits = {
            "tail-7-rotated-wind-first-response": 0.12,
            "tail-7-rotated-wind-settled": 2.0,
        }
        if now - state["last"] < (15 if stage == 0 else waits.get(labels[stage], 5)):
            return
        assert unreal.FurViewportProbe.advance()
        row = json.loads(unreal.FurViewportProbe.capture(
            str(out / (labels[stage] + ".png"))))
        row["label"] = labels[stage]
        row["strand_max_displacement_cm"] = groom.get_maximum_displacement_cm()
        state["captures"].append(row)
        state["roots"].append(roots())
        state["normals"].append(normals())
        state["frame_ys"].append(frame_ys())
        state["bones"].append(bone_state())
        next_stage = stage + 1
        if next_stage == len(labels):
            baseline, rotated, _, _, restored = state["roots"]
            moved = [distance(a, b) for a, b in zip(baseline, rotated)]
            restore_error = [distance(a, b) for a, b in zip(baseline, restored)]
            normal_baseline, normal_rotated, _, _, normal_restored = state["normals"]
            frame_baseline, frame_rotated, _, _, frame_restored = state["frame_ys"]
            normal_motion = [angle_degrees(a, b) for a, b in zip(
                normal_baseline, normal_rotated)]
            normal_restore = [angle_degrees(a, b) for a, b in zip(
                normal_baseline, normal_restored)]
            frame_motion = [angle_degrees(a, b) for a, b in zip(
                frame_baseline, frame_rotated)]
            frame_restore = [angle_degrees(a, b) for a, b in zip(
                frame_baseline, frame_restored)]
            report = {
                "source_asset": "ADE5909F821E9DDE subset12",
                "source_event": 24825,
                "bone": "tail_7",
                "rotation_delta_degrees": 25.0,
                "guide_count": guide_count,
                "bound_guide_count": bound_guide_count,
                "moved_guides_over_0_001_cm": sum(value > 0.001 for value in moved),
                "maximum_root_motion_cm": max(moved),
                "mean_root_motion_cm": sum(moved) / len(moved),
                "maximum_restore_error_cm": max(restore_error),
                "root_normals_moved_over_0_01_degrees": sum(
                    value > 0.01 for value in normal_motion),
                "maximum_root_normal_motion_degrees": max(normal_motion),
                "maximum_root_normal_restore_error_degrees": max(normal_restore),
                "root_frame_y_moved_over_0_01_degrees": sum(
                    value > 0.01 for value in frame_motion),
                "maximum_root_frame_y_motion_degrees": max(frame_motion),
                "maximum_root_frame_y_restore_error_degrees": max(frame_restore),
                "captured_wind_strength": 0.0370904393,
                "final_wind_strength": groom.get_editor_property("wind_strength"),
                "bone_states": state["bones"],
                "captures": state["captures"],
                "passed": (max(moved) > 0.1 and max(restore_error) < 0.001
                           and max(normal_motion) > 0.1
                           and max(frame_motion) > 0.1
                           and max(normal_restore) < 0.01
                           and max(frame_restore) < 0.01
                           and state["captures"][3]["strand_max_displacement_cm"] > 0.1),
                "limits": "Exact decoded retail triangle/barycentric binding reduced through decoded body skin weights. Controlled poseable-mesh tail_7 rotation verifies root position and both groom-frame axes, captured retail wind strength/timer origin, then exact reset.",
            }
            (out / "report.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8")
            stop()
            return
        if next_stage == 1:
            initial = pose.get_bone_rotation_by_name(
                "tail_7", unreal.BoneSpaces.COMPONENT_SPACE)
            rotated = unreal.MathLibrary.compose_rotators(
                unreal.Rotator(25.0, 0.0, 0.0), initial)
            pose.set_bone_rotation_by_name(
                "tail_7", rotated, unreal.BoneSpaces.COMPONENT_SPACE)
        elif next_stage == 2:
            groom.set_editor_property(
                "wind_timer_offset",
                981.7157592773438 - unreal.SystemLibrary.get_game_time_in_seconds(world))
            groom.set_editor_property(
                "wind_direction", unreal.Vector(-0.9974102378, -0.0719231740, 0.0))
            groom.set_strand_weather(0.0, 0.0370904393)
            groom.reset_simulation()
        elif next_stage == 4:
            groom.set_strand_weather(0.0, 0.0)
            pose.reset_bone_transform_by_name("tail_7")
            groom.reset_simulation()
        state.update(stage=next_stage, last=time.monotonic())
    except Exception:
        unreal.log_error(traceback.format_exc())
        stop()
    finally:
        state["busy"] = False


state["handle"] = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
