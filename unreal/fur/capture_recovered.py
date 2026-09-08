"""Bounded dry/wet comparison of the recovered-core UE material."""
import importlib.util
import json
from pathlib import Path
import time
import unreal

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('recovered', root.parent/'plugins/FurAuthoring/Content/Python/create_recovered_material.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
material = module.create_material()
unreal.EditorLoadingAndSavingUtils.load_map('/FurAuthoring/Demo/FurDemo')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
fur = []
for actor in actors.get_all_level_actors():
    if isinstance(actor, unreal.FurAuthoringActor):
        actor.set_editor_property('fur_material', material)
        actor.set_editor_property('shell_count',32)
        actor.set_editor_property('wind_strength',0.0)
        actor.rebuild_fur()
        dmi = actor.get_editor_property('shells').get_material(0)
        dmi.set_scalar_parameter_value('RecoveredShellCount',32)
        wool = 'Wool' in actor.get_actor_label()
        dmi.set_scalar_parameter_value('RecoveredDensity',3 if wool else 12)
        dmi.set_scalar_parameter_value('OffsetScale',0 if wool else 1)
        fur.append(actor)
assert len(fur) == 2
position = unreal.Vector(320,280,180)
target = unreal.Vector(0,75,80)
camera = actors.spawn_actor_from_class(unreal.CameraActor,position,unreal.MathLibrary.find_look_at_rotation(position,target))
camera.camera_component.set_field_of_view(55)
camera.camera_component.set_editor_property('constrain_aspect_ratio',False)
for cmd in ['t.MaxFPS 10','r.ScreenPercentage 100']:
    unreal.SystemLibrary.execute_console_command(world,cmd)
started = time.monotonic()
state = {'stage':0,'requested':False,'last':started}
outputs = [root/'recovered/ue-dry.png',root/'recovered/ue-wet.png']
# Reject stale files as evidence; a new timestamp is required.
old_times = [p.stat().st_mtime_ns if p.exists() else 0 for p in outputs]

def stop():
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.execute_console_command(world,'QUIT_EDITOR')

def tick(delta):
    try:
        now = time.monotonic()
        if now-started > 150:
            raise RuntimeError('Recovered material screenshot timed out')
        stage = state['stage']
        out = outputs[stage]
        if state['requested'] and out.exists() and out.stat().st_mtime_ns > old_times[stage]:
            if stage == 0:
                for actor in fur:
                    actor.set_weather(1,0)
                state.update(stage=1,requested=False,last=now)
            else:
                (root/'recovered/render.json').write_text(json.dumps({
                    'screenshots':[str(p) for p in outputs],
                    'engine':unreal.SystemLibrary.get_engine_version(),
                    'scope':'Recovered coverage and wet albedo, fixed-depth shells, UE Default Lit; not native renderer parity',
                    'seconds':now-started},indent=2))
                stop()
        elif not state['requested'] and now-state['last'] > (60 if stage==0 else 5):
            assert unreal.AutomationLibrary.take_high_res_screenshot(640,480,str(out),camera=camera,delay=0,force_game_view=True)
            state['requested'] = True
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc())
        stop()

state['handle'] = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
