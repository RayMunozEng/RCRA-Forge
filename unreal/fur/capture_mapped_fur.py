"""Fixed camera/light captures for missing maps, masks and groom directions."""
import json
from pathlib import Path
import time
import unreal

root = Path(__file__).resolve().parent/'recovered'
unreal.EditorLoadingAndSavingUtils.load_map('/FurAuthoring/Demo/FurMaps')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
fur = [a for a in actors.get_all_level_actors() if isinstance(a,unreal.FurAuthoringActor)]
assert len(fur)==2
maps = {name:unreal.load_asset('/FurAuthoring/Textures/Authoring/T_'+name)
        for name in ['LengthBands','DensityBands','GroomDirections']}
assert all(maps.values())
for actor in fur:
    actor.set_fur_maps(None,None,None)
    actor.set_weather(0,0)
position = unreal.Vector(320,280,180)
target = unreal.Vector(0,75,80)
camera = actors.spawn_actor_from_class(unreal.CameraActor,position,unreal.MathLibrary.find_look_at_rotation(position,target))
camera.camera_component.set_field_of_view(55)
camera.camera_component.set_editor_property('constrain_aspect_ratio',False)
unreal.SystemLibrary.execute_console_command(world,'t.MaxFPS 10')
started = time.monotonic()
state = {'stage':0,'requested':False,'last':started}
outputs = [root/('maps-'+s+'.png') for s in ['unmasked','length-density','groom']]
old = [p.stat().st_mtime_ns if p.exists() else 0 for p in outputs]

def stop():
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.execute_console_command(world,'QUIT_EDITOR')

def tick(delta):
    try:
        now = time.monotonic()
        if now-started>160:
            raise RuntimeError('Map captures timed out')
        stage = state['stage']
        out = outputs[stage]
        if state['requested'] and out.exists() and out.stat().st_mtime_ns>old[stage]:
            if stage==2:
                (root/'maps-render.json').write_text(json.dumps({
                    'screenshots':[str(p) for p in outputs],
                    'seconds':now-started,'scope':'Static authoring maps; no skeletal or native lighting parity'},indent=2))
                stop()
                return
            for actor in fur:
                wool = 'Wool' in actor.get_actor_label()
                if stage==0:
                    actor.set_fur_maps(None if wool else maps['LengthBands'],maps['DensityBands'] if wool else None,None)
                else:
                    actor.set_editor_property('groom_strength',2)
                    actor.rebuild_fur()
                    actor.set_fur_maps(None,None,maps['GroomDirections'])
            state.update(stage=stage+1,requested=False,last=now)
        elif not state['requested'] and now-state['last']>(40 if stage==0 else 5):
            assert unreal.AutomationLibrary.take_high_res_screenshot(640,480,str(out),camera=camera,delay=0,force_game_view=True)
            state['requested'] = True
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc())
        stop()

state['handle'] = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
