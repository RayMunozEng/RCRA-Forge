"""Live recovered-lighting checks for skeletal depth/poses and wet/wind response."""
import importlib.util
import json
from pathlib import Path
import time
import unreal

root=Path(__file__).resolve().parent
fixture=globals().get('dynamics_fixture','skeletal')
out=root/'recovered'/('dynamics-'+fixture)
out.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('scene_builder',root.parent/'plugins/FurAuthoring/Content/Python/create_scene_fur.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
skeletal=fixture=='skeletal'
if skeletal:
    unreal.EditorLoadingAndSavingUtils.load_map('/FurAuthoring/Demo/FurSkeletal')
    for actor in actors.get_all_level_actors():
        if isinstance(actor,unreal.DirectionalLight): actors.destroy_actor(actor)
        elif isinstance(actor,unreal.StaticMeshActor): actor.set_actor_hidden_in_game(True)
    fur=next(a for a in actors.get_all_level_actors() if isinstance(a,unreal.SkeletalFurAuthoringActor))
    source=fur.get_editor_property('pose_source')
    source.set_update_animation_in_editor(True)
    source.set_editor_property('visibility_based_anim_tick_option',unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
    source.play_animation(unreal.load_asset('/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Walk_Fwd'),True)
    source.set_play_rate(0);source.set_position(0,False)
    white=unreal.load_asset('/FurAuthoring/Textures/Authoring/T_White')
    textures=dict(base_color=white,fur_control=white,specular_color=white)
    shape=dict(length=2,density=12,offset=0,transmittance=.1)
    eye=unreal.Vector(380,390,210);target=unreal.Vector(0,75,90)
else:
    sheep=fixture=='sheep'
    asset='/Game/FurReference/'+('Sheep/' if sheep else '')
    scene=asset+'SceneLighting' if sheep else asset+'MatchedRatchet'
    unreal.EditorLoadingAndSavingUtils.load_map(scene)
    fur=next(a for a in actors.get_all_level_actors() if isinstance(a,unreal.FurAuthoringActor))
    mid='0' if sheep else '2'
    textures={r:unreal.load_asset(asset+'Textures/M'+mid+'_'+r) for r in ('base_color','fur_control','specular_color')}
    shape=dict(length=9,density=3,offset=0,transmittance=.2) if sheep else dict(length=3,density=16,offset=1,transmittance=.1)
    fixture_inputs='sheep-reference' if sheep else 'matched-reference'
    input_candidates=(
        root/fixture_inputs/'inputs.json',
        Path.home()/'Cloud-Drive/Github/gem-shader/unreal/fur'/fixture_inputs/'inputs.json',
    )
    inputs_path=next((path for path in input_candidates if path.is_file()),None)
    if inputs_path is None:
        raise FileNotFoundError('fixture inputs not found: '+', '.join(map(str,input_candidates)))
    inputs=json.loads(inputs_path.read_text(encoding='utf-8'))
    eye=unreal.Vector(*inputs['camera']['ue_eye_cm']);target=unreal.Vector(*inputs['camera']['ue_target_cm'])
material=builder.create(globals().get('dynamics_material','M_Dynamics_'+fixture+'_v1'),textures,fur=True,recovered=True,temporal=True,scene=True,
    environment=globals().get('test_environment'),environment_brdf=globals().get('test_environment_brdf'),
    settings=shape,asset_path='/Game/FurValidation/Materials',skeletal=skeletal,
    surface_outputs=globals().get('fur_surface_outputs',False))
fur.set_editor_property('fur_material',material)
fur.set_editor_property('length',shape['length'])
fur.set_editor_property('use_map_controls',True)
fur.set_editor_property('recovered_density',shape['density'])
fur.set_editor_property('groom_strength',shape['offset'])
fur.rebuild_fur()
if skeletal:
    assert fur.refresh_preview_pose()
    layers=fur.get_editor_property('skeletal_shells')
    assert len(layers)==16
    for i,layer in enumerate(layers):
        assert layer.get_material(0).get_scalar_parameter_value('ShellDepth')==i/16
    light=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(),
        unreal.MathLibrary.find_look_at_rotation(unreal.Vector(.6,.8,1),unreal.Vector()))
    light.light_component.set_intensity(3.14159265)
    controller=actors.spawn_actor_from_class(unreal.FurLightingController,unreal.Vector())
    controller.key_light=light;controller.targets=[fur];controller.enable_shadows=False
else:
    level_actors=actors.get_all_level_actors()
    controller=next((a for a in level_actors if isinstance(a,unreal.FurLightingController)),None)
    if controller is None:
        key=next((a for a in level_actors if isinstance(a,unreal.DirectionalLight)),None)
        if key is None:
            key=actors.spawn_actor_from_class(
                unreal.DirectionalLight,unreal.Vector(),
                unreal.MathLibrary.find_look_at_rotation(
                    unreal.Vector(.6,.8,1),unreal.Vector()))
            key.light_component.set_intensity(3.14159265)
        controller=actors.spawn_actor_from_class(unreal.FurLightingController,unreal.Vector())
        controller.key_light=key
        controller.targets=[fur]
        controller.enable_shadows=False
controller.refresh_lighting()
camera=actors.spawn_actor_from_class(unreal.CameraActor,eye,unreal.MathLibrary.find_look_at_rotation(eye,target))
camera.camera_component.set_field_of_view(50 if skeletal else 60)
camera.camera_component.set_editor_property('constrain_aspect_ratio',False)
level.pilot_level_actor(camera);level.editor_set_game_view(True)
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
def command(cmd): unreal.SystemLibrary.execute_console_command(world,cmd)
for cmd in ['t.MaxFPS 10','r.EyeAdaptationQuality 0','ShowFlag.EyeAdaptation 0','ShowFlag.Tonemapper 0',
            'r.BloomQuality 0','r.MotionBlurQuality 0','r.ScreenPercentage 100','r.TemporalAASamples 8',
            'r.TemporalAACurrentFrameWeight 0.05','ShowFlag.PostProcessing 1','ShowFlag.AntiAliasing 1',
            'ShowFlag.TemporalAA 1','r.AntiAliasingMethod 2']:
    command(cmd)
materials=[l.get_material(0) for l in layers] if skeletal else [fur.get_editor_property('shells').get_material(0)]
def weather(wet,strength,clock):
    fur.set_weather(wet,strength)
    for mat in materials:
        mat.set_scalar_parameter_value('UseWindTimeOverride',1)
        mat.set_scalar_parameter_value('WindTimeOverride',clock)
        assert abs(mat.get_scalar_parameter_value('Wetness')-wet)<1e-5
        assert abs(mat.get_scalar_parameter_value('WindStrength')-strength)<1e-5
weather(0,0,0)
labels=(['dry']+['walk-'+str(i) for i in range(12)]+['pose-change','pose-settled','wind-a','wind-b','wet-wind']) if skeletal else ['dry','wind-a','wind-b','wet-wind']
start=time.monotonic()
state=dict(stage=0,last=start,draw=start,busy=False,done=False,rows=[],poses=[])
def sample_bones():
    locations=[];error=0
    for i in range(source.get_num_bones()):
        bone=source.get_bone_name(i);p=source.get_socket_location(bone)
        locations.append([p.x,p.y,p.z])
        for layer in layers:
            error=max(error,(p-layer.get_socket_location(bone)).length())
    assert error<.001,error
    state['poses'].append(locations)
    return error
def stop():
    state['done']=True
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    command('QUIT_EDITOR')
def tick(delta):
    if state['done'] or state['busy']:return
    try:
        now=time.monotonic()
        if now-start>200:raise RuntimeError('Dynamics capture timeout')
        if now-state['draw']>=.1:
            state['busy']=True
            try:assert unreal.FurViewportProbe.advance()
            finally:state['busy']=False
            state['draw']=now
        stage=state['stage'];label=labels[stage]
        delay=20 if stage==0 else (.2 if label.startswith('walk-') or label=='pose-change' else 8)
        if now-state['last']<delay:return
        state['busy']=True
        try:
            assert unreal.FurViewportProbe.advance()
            row=json.loads(unreal.FurViewportProbe.capture(str(out/(label+'.png'))))
        finally:state['busy']=False
        assert row['draw_realtime'] and row['resolved_aa_method']==2,row
        row.update(label=label,wetness=materials[0].get_scalar_parameter_value('Wetness'),
                   wind=materials[0].get_scalar_parameter_value('WindStrength'))
        if skeletal and label in ('dry','pose-change'):row['bone_follow_error_cm']=sample_bones()
        state['rows'].append(row)
        state.update(stage=stage+1,last=time.monotonic())
        if stage+1==len(labels):
            report=dict(fixture=fixture,captures=state['rows'],
                        limits='Fixed wind-time snapshots and sampled walk poses; native velocity and fast-motion ghosting remain unverified.')
            if skeletal:
                motion=max(sum((x-y)**2 for x,y in zip(a,b))**.5 for a,b in zip(*state['poses']))
                assert motion>1,motion
                report['bone_motion_cm']=motion
            (out/'report.json').write_text(json.dumps(report,indent=2))
            stop();return
        next_label=labels[stage+1]
        if next_label.startswith('walk-'):
            source.set_position(int(next_label.split('-')[1])*.06,False);assert fur.refresh_preview_pose()
        elif next_label=='pose-change':
            source.set_position(.33,False);assert fur.refresh_preview_pose()
        elif next_label=='wind-a':weather(0,.12,0)
        elif next_label=='wind-b':weather(0,.12,1.5)
        elif next_label=='wet-wind':weather(.8,.12,1.5)
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
