"""Recovered fur: temporal edges, a real directional light, and depth-map shadows."""
import importlib.util
import json
from pathlib import Path
import time
import unreal

root=Path(__file__).resolve().parent
sheep=globals().get('reference_fixture')=='sheep'
out=root/('sheep-reference' if sheep else 'matched-reference')
asset_root='/Game/FurReference/Sheep' if sheep else '/Game/FurReference'
mid='0' if sheep else '2'
shape={'length':9,'density':3,'offset':0,'transmittance':.2} if sheep else None
inputs=json.loads((out/'inputs.json').read_text())
spec=importlib.util.spec_from_file_location('builder',root/'create_reference_material.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
textures={r:unreal.load_asset(asset_root+'/Textures/M'+mid+'_'+r) for r in ('base_color','fur_control','specular_color')}
material=builder.create('M_Sheep0_SceneTemporal_v2' if sheep else 'M_Ratchet2_SceneTemporal_v2',textures,fur=True,recovered=True,temporal=True,scene=True,settings=shape)
unreal.EditorLoadingAndSavingUtils.load_map(asset_root+('/MatchedSheep' if sheep else '/MatchedRatchet'))
# This legacy high-res path checks light/shadow response only. The Python
# Realtime(True) API only removes a disabling override; it does not enable it.
# Use capture_reference_viewport.py for verified live temporal filtering.
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
fur=next(a for a in actors.get_all_level_actors() if isinstance(a,unreal.FurAuthoringActor))
fur.set_editor_property('fur_material',material);fur.rebuild_fur()
position=unreal.Vector(*inputs['camera']['ue_eye_cm']);target=unreal.Vector(*inputs['camera']['ue_target_cm'])
camera=actors.spawn_actor_from_class(unreal.CameraActor,position,unreal.MathLibrary.find_look_at_rotation(position,target))
camera.camera_component.set_field_of_view(60)
camera.camera_component.set_editor_property('constrain_aspect_ratio',False)
key=unreal.Vector(.6,.8,1)
rotation=unreal.MathLibrary.find_look_at_rotation(key,unreal.Vector())
light=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(),rotation)
light.light_component.set_intensity(3.14159265)
controller=actors.spawn_actor_from_class(unreal.FurLightingController,unreal.Vector())
controller.key_light=light;controller.targets=[fur];controller.enable_shadows=False
controller.refresh_lighting()
for cmd in ['t.MaxFPS 10','r.EyeAdaptationQuality 0','ShowFlag.Tonemapper 0','ShowFlag.EyeAdaptation 0',
    'r.BloomQuality 0','r.MotionBlurQuality 0','ShowFlag.TemporalAA 1','r.AntiAliasingMethod 2','r.TemporalAASamples 8',
    'r.TemporalAACurrentFrameWeight 0.05','r.HighResScreenshotDelay 32','r.ScreenPercentage 100']:
    unreal.SystemLibrary.execute_console_command(world,cmd)
blocker=actors.spawn_actor_from_class(unreal.StaticMeshActor,target+key*70)
blocker.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'))
blocker.set_actor_scale3d(unreal.Vector(.28,.28,.28))
blocker.static_mesh_component.set_editor_property('visible_in_scene_capture_only',True)
controller.shadow_casters=[blocker]
labels=['clean','relit','shadow']
outputs=[out/('ue-scene-'+s+'.png') for s in labels]
old=[p.stat().st_mtime_ns if p.exists() else 0 for p in outputs]
started=time.monotonic();state={'stage':0,'requested':False,'last':started,'checks':[]}
def check():
    material=fur.get_editor_property('shells').get_material(0)
    color=material.get_vector_parameter_value('SceneKeyRadiance')
    state['checks'].append({'stage':labels[state['stage']],
        'radiance':[color.r,color.g,color.b],
        'shadow_enabled':material.get_scalar_parameter_value('SceneShadowEnabled')})
def stop():
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.execute_console_command(world,'QUIT_EDITOR')
def tick(delta):
    if state.get('finishing'): return
    try:
        now=time.monotonic()
        if now-started>200: raise RuntimeError('Scene comparison timed out')
        i=state['stage'];p=outputs[i]
        if state['requested'] and p.exists() and p.stat().st_mtime_ns>old[i]:
            check()
            if i==2:
                state['finishing']=True
                assert state['checks'][0]['radiance']!=state['checks'][1]['radiance']
                assert state['checks'][2]['shadow_enabled']==1
                # Keep the capture-only blocker in the saved fixture so the
                # shadow test can be toggled again without rebuilding the scene.
                controller.enable_shadows=False
                controller.refresh_lighting()
                assert unreal.EditorLoadingAndSavingUtils.save_map(world,asset_root+'/SceneLighting')
                (out/'scene-render.json').write_text(json.dumps({'screenshots':[str(p) for p in outputs],
                    'checks':state['checks'],'aa':'Requested TAA, 8 camera jitter phases, 32 Halton coverage phases; effective history unverified in this high-res path',
                    'shadows':'512x512 orthographic SceneDepth, explicit casters, 3x3 PCF',
                    'limits':['One directional light bridge; no VSM/Lumen/probe integration',
                              'No deforming-caster auto-invalidation; call RefreshLighting for those',
                              'Native shell selection and temporal resolve are not ported']},indent=2))
                stop();return
            if i==0:
                light.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(unreal.Vector(-.6,.8,1),unreal.Vector()),False)
                light.light_component.set_light_color(unreal.LinearColor(.3,.55,1,1))
            else:
                light.set_actor_rotation(rotation,False)
                light.light_component.set_light_color(unreal.LinearColor(1,1,1,1))
                controller.enable_shadows=True
            controller.refresh_lighting()
            state.update(stage=i+1,requested=False,last=now)
        elif not state['requested'] and now-state['last']>(30 if i==0 else 6):
            state['requested']=True
            assert unreal.AutomationLibrary.take_high_res_screenshot(600,600,str(p),camera=camera,delay=0,force_game_view=True)
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
