"""Reproduce frozen bone shadows, then verify scheduled deformation refresh."""
from pathlib import Path
dynamics_fixture='ratchet'
setup=Path(__file__).with_name('capture_reference_dynamics.py').read_text().split('labels=',1)[0]
exec(compile(setup,str(Path(__file__).with_name('capture_reference_dynamics.py')),'exec'),globals())
out=root/'recovered'/globals().get('shadow_output','animated-shadows');out.mkdir(exist_ok=True)
caster=actors.spawn_actor_from_class(unreal.SkeletalMeshActor,target+unreal.Vector(.6,.8,1)*70-unreal.Vector(0,0,31.5))
caster.set_actor_scale3d(unreal.Vector(.35,.35,.35))
skin=caster.skeletal_mesh_component
skin.set_skeletal_mesh_asset(unreal.load_asset('/Engine/Tutorial/SubEditors/TutorialAssets/Character/TutorialTPP'))
skin.set_editor_property('visible_in_scene_capture_only',True)
skin.set_update_animation_in_editor(True)
skin.set_editor_property('visibility_based_anim_tick_option',unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
skin.play_animation(unreal.load_asset('/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Walk_Fwd'),True)
skin.set_play_rate(0);skin.set_position(0,False)
helper=actors.spawn_actor_from_class(unreal.SkeletalFurAuthoringActor,unreal.Vector())
helper.set_pose_source(skin);helper.set_actor_hidden_in_game(True)
assert helper.refresh_preview_pose()
controller.shadow_casters=[caster]
controller.enable_shadows=False
controller.refresh_animated_casters=False
controller.shadow_updates_per_second=5
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['unshadowed','pose-a','pose-b-frozen','pose-b-live','moved-out','disabled']
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,rows=[])
def stop():
    state['done']=True
    unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    command('QUIT_EDITOR')
def tick(delta):
    if state['done'] or state['busy']:return
    try:
        now=time.monotonic()
        if now-started>180:raise RuntimeError('Shadow capture timeout')
        if now-state['draw']>=.1:
            state['busy']=True
            try:assert unreal.FurViewportProbe.advance()
            finally:state['busy']=False
            state['draw']=now
        stage=state['stage']
        if now-state['last']<(20 if stage==0 else 6):return
        state['busy']=True
        try:
            assert unreal.FurViewportProbe.advance()
            row=json.loads(unreal.FurViewportProbe.capture(str(out/(labels[stage]+'.png'))))
        finally:state['busy']=False
        assert row['draw_realtime'] and row['resolved_aa_method']==2
        row.update(material=material.get_path_name(),label=labels[stage],captures=controller.get_shadow_capture_count(),elapsed=now-started)
        row['bones']=[[p.x,p.y,p.z] for p in (skin.get_socket_location(skin.get_bone_name(i)) for i in range(skin.get_num_bones()))]
        state['rows'].append(row)
        state.update(stage=stage+1,last=time.monotonic())
        if stage==0:controller.enable_shadows=True
        elif stage==1:skin.set_position(.33,False);assert helper.refresh_preview_pose()
        elif stage==2:controller.refresh_animated_casters=True
        elif stage==3:caster.set_actor_location(caster.get_actor_location()+unreal.Vector(100,0,0),False,False)
        elif stage==4:controller.enable_shadows=False
        else:
            rows=state['rows']
            assert rows[1]['captures']==rows[2]['captures'],'Frozen control unexpectedly recaptured'
            assert rows[3]['captures']>rows[2]['captures'],'Animated refresh did not recapture'
            assert rows[5]['captures']==rows[4]['captures'],'Disabled shadows still capture'
            (out/'report.json').write_text(json.dumps(rows,indent=2));stop()
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
