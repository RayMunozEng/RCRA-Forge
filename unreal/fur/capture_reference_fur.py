"""Fixed-camera private Ratchet baseline; no native lighting parity claim."""
import json
from pathlib import Path
import time
import unreal

out=Path(__file__).resolve().parent/'matched-reference'
inputs=json.loads((out/'inputs.json').read_text())
unreal.EditorLoadingAndSavingUtils.load_map('/Game/FurReference/MatchedRatchet')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
position=unreal.Vector(*inputs['camera']['ue_eye_cm'])
target=unreal.Vector(*inputs['camera']['ue_target_cm'])
camera=actors.spawn_actor_from_class(unreal.CameraActor,position,unreal.MathLibrary.find_look_at_rotation(position,target))
camera.camera_component.set_field_of_view(60)
camera.camera_component.set_editor_property('constrain_aspect_ratio',False)
light_direction=unreal.Vector(.6,.8,1)
light=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(),unreal.MathLibrary.find_look_at_rotation(light_direction,unreal.Vector()))
light.light_component.set_intensity(3.14159265)
light.light_component.set_cast_shadows(False)
for cmd in ['t.MaxFPS 10','r.EyeAdaptationQuality 0','ShowFlag.Tonemapper 0','ShowFlag.EyeAdaptation 0',
            'r.BloomQuality 0','r.MotionBlurQuality 0','r.AntiAliasingMethod 0','r.ScreenPercentage 100']:
    unreal.SystemLibrary.execute_console_command(world,cmd)
parts=[a for a in actors.get_all_level_actors() if a.get_actor_label().startswith('RatchetHeadPart')]
assert len(parts)==7
modes=globals().get('reference_modes',['Unlit','Lit'])
def mode(name):
    for actor in parts:
        mid=actor.get_actor_label().split('_M')[-1]
        suffix='Lit' if name=='Recovered' and mid!='2' else name
        material=unreal.load_asset('/Game/FurReference/Materials/M_Ratchet'+mid+'_'+suffix)
        assert material
        if isinstance(actor,unreal.FurAuthoringActor):
            actor.set_editor_property('fur_material',material)
            actor.rebuild_fur()
        else:
            mesh=actor.static_mesh_component.static_mesh
            for slot in range(mesh.get_num_sections(0)):
                actor.static_mesh_component.set_material(slot,material)
mode(modes[0])
filenames={'Unlit':'ue-unlit.png','Lit':'ue-default-lit.png','Recovered':'ue-recovered-key.png'}
outputs=[out/filenames[m] for m in modes]
old=[p.stat().st_mtime_ns if p.exists() else 0 for p in outputs]
started=time.monotonic()
state={'stage':0,'requested':False,'last':started}
def stop():
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.execute_console_command(world,'QUIT_EDITOR')
def tick(delta):
    try:
        now=time.monotonic()
        if now-started>180: raise RuntimeError('Reference capture timed out')
        stage=state['stage']
        p=outputs[stage]
        if state['requested'] and p.exists() and p.stat().st_mtime_ns>old[stage]:
            if stage==len(modes)-1:
                (out/('render-recovered.json' if 'Recovered' in modes else 'render.json')).write_text(json.dumps({'camera':inputs['camera'],'screenshots':[str(p) for p in outputs],
                    'light_to_source_ue':[.6,.8,1],'light_intensity_lux':3.14159265,
                    'modes':modes,'limits':['Recovered mode evaluates a fixed key in an emissive material, not a UE shading-model integration',
                              'No environment, shadow, temporal AA or tonemapping',
                              'Static posed head, fixed-depth shells, zero wind and wetness']},indent=2))
                stop()
                return
            mode(modes[stage+1])
            state.update(stage=stage+1,requested=False,last=now)
        elif not state['requested'] and now-state['last']>(45 if stage==0 else 10):
            assert unreal.AutomationLibrary.take_high_res_screenshot(600,600,str(p),camera=camera,delay=0,force_game_view=True)
            state['requested']=True
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc())
        stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
