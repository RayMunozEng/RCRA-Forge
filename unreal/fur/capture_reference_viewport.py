"""Read ordinary persistent viewport frames; do not invoke HighResShot."""
import json
from pathlib import Path
import time
import unreal

root=Path(__file__).resolve().parent
sheep=globals().get('reference_fixture')=='sheep'
fixture='sheep-reference' if sheep else 'matched-reference'
out=root/fixture/'viewport-live'
out.mkdir(exist_ok=True)
unreal.EditorLoadingAndSavingUtils.load_map('/Game/FurReference/'+('Sheep/' if sheep else '')+'SceneLighting')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
camera=next(a for a in actors.get_all_level_actors() if isinstance(a,unreal.CameraActor))
inputs=json.loads((root/fixture/'inputs.json').read_text())
eye=unreal.Vector(*inputs['camera']['ue_eye_cm'])
target=unreal.Vector(*inputs['camera']['ue_target_cm'])
camera.set_actor_location(eye,False,False)
camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(eye,target),False)
level.pilot_level_actor(camera)
level.editor_set_game_view(True)
def command(cmd): unreal.SystemLibrary.execute_console_command(world,cmd)
for cmd in ['t.MaxFPS 10','r.EyeAdaptationQuality 0','ShowFlag.EyeAdaptation 0',
            'ShowFlag.Tonemapper 0','r.BloomQuality 0','r.MotionBlurQuality 0',
            'r.ScreenPercentage 100','r.TemporalAASamples 8',
            'r.TemporalAACurrentFrameWeight 0.05','r.AntiAliasingMethod 0']:
    command(cmd)
start=time.monotonic()
state={'stage':0,'frame':0,'last':start,'last_draw':start,'rows':[],'done':False,'drawing':False}
labels=['no-aa','taa','moving','settled']

def stop():
    state['done']=True
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    command('QUIT_EDITOR')

def tick(delta):
    if state['done'] or state['drawing']: return
    try:
        now=time.monotonic()
        if now-start>180: raise RuntimeError('Viewport capture timeout')
        if now-state['last_draw']>=.1:
            state['last_draw']=now
            state['drawing']=True
            try: assert unreal.FurViewportProbe.advance()
            finally: state['drawing']=False
        stage=state['stage']; frame=state['frame']
        delay=20 if stage==0 and frame==0 else (8 if frame==0 else .35)
        if now-state['last']<delay: return
        name=labels[stage]+'-'+str(frame)+'.png'
        # The editor can add its inactive-window override between callbacks.
        # Read immediately after a controlled draw, while our positive override
        # is the most recent one. Do not label a stale framebuffer as Realtime.
        state['drawing']=True
        try:
            assert unreal.FurViewportProbe.advance()
            state['last_draw']=now
            row=json.loads(unreal.FurViewportProbe.capture(str(out/name)))
        finally: state['drawing']=False
        assert 'error' not in row,row
        assert row['draw_realtime'],row
        assert row['resolved_aa_method']==(0 if stage==0 else 2),row
        row.update(stage=labels[stage],frame=frame,elapsed=now-start)
        state['rows'].append(row)
        state['last']=now
        state['frame']+=1
        if stage==2:
            pos=eye+unreal.Vector(0,(frame+1)*.5,0)
            camera.set_actor_location(pos,False,False)
            camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(pos,target),False)
        if state['frame']>=(12 if stage==2 else 4):
            state.update(stage=stage+1,frame=0)
            if stage==0:
                for cmd in ['ShowFlag.PostProcessing 1','ShowFlag.AntiAliasing 1','ShowFlag.TemporalAA 1','r.AntiAliasingMethod 2']:
                    command(cmd)
            if stage==3:
                (out/'report.json').write_text(json.dumps(state['rows'],indent=2))
                stop()
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
