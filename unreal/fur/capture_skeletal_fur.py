"""Two deterministic animation poses, rendered shells and bone-follow checks."""
import json
from pathlib import Path
import time
import unreal

root = Path(__file__).resolve().parent/'recovered'
unreal.EditorLoadingAndSavingUtils.load_map('/FurAuthoring/Demo/FurSkeletal')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
fur = next(a for a in actors.get_all_level_actors() if isinstance(a,unreal.SkeletalFurAuthoringActor))
source = fur.get_editor_property('pose_source')
assert source
source.set_update_animation_in_editor(True)
source.set_editor_property('visibility_based_anim_tick_option',unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
source.play_animation(unreal.load_asset('/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Walk_Fwd'),True)
source.set_play_rate(0)
source.set_position(0,False)
fur.rebuild_fur()
assert len(fur.get_editor_property('skeletal_shells'))==16
assert fur.refresh_preview_pose()
position = unreal.Vector(380,390,210)
target = unreal.Vector(0,75,125)
camera = actors.spawn_actor_from_class(unreal.CameraActor,position,unreal.MathLibrary.find_look_at_rotation(position,target))
camera.camera_component.set_field_of_view(50)
camera.camera_component.set_editor_property('constrain_aspect_ratio',False)
started = time.monotonic()
state = {'stage':0,'requested':False,'last':started,'poses':[],'errors':[]}
outputs = [root/('skeletal-pose-'+str(i)+'.png') for i in range(2)]
old = [p.stat().st_mtime_ns if p.exists() else 0 for p in outputs]
bones = [source.get_bone_name(i) for i in range(source.get_num_bones())]

def sample_pose():
    reference = []
    error = 0
    for bone in bones:
        location = source.get_socket_location(bone)
        reference.append([location.x,location.y,location.z])
        for layer in fur.get_editor_property('skeletal_shells'):
            other = layer.get_socket_location(bone)
            error = max(error,(location-other).length())
    assert error<.001, 'Layer bone transforms do not match source: '+str(error)
    state['poses'].append(reference)
    state['errors'].append(error)

def stop():
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.execute_console_command(world,'QUIT_EDITOR')

def tick(delta):
    try:
        now = time.monotonic()
        if now-started>160:
            raise RuntimeError('Skeletal capture timed out')
        stage = state['stage']
        out = outputs[stage]
        if state['requested'] and out.exists() and out.stat().st_mtime_ns>old[stage]:
            sample_pose()
            if stage==0:
                source.set_position(.33,False)
                assert fur.refresh_preview_pose()
                state.update(stage=1,requested=False,last=now)
            else:
                motion = max(sum((a-b)**2 for a,b in zip(p,q))**.5 for p,q in zip(*state['poses']))
                assert motion>1, 'Animation did not move the bones'
                report = {'screenshots':[str(p) for p in outputs],
                          'bones':len(bones),'layers':16,'times':[0,.33],
                          'maximum_bone_motion_cm':motion,'maximum_follow_error_cm':max(state['errors']),
                          'seconds':now-started,'scope':'Pose-sharing deformation; native velocity/lighting parity unverified'}
                (root/'skeletal-render.json').write_text(json.dumps(report,indent=2))
                stop()
        elif not state['requested'] and now-state['last']>(40 if stage==0 else 5):
            assert unreal.AutomationLibrary.take_high_res_screenshot(640,480,str(out),camera=camera,delay=0,force_game_view=True)
            state['requested'] = True
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc())
        stop()

state['handle'] = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
