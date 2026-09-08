"""Measure selected fur-shell self occlusion and WPO recapture, not parity."""
from pathlib import Path
dynamics_material='M_FilteredShadow_ratchet_v1'
dynamics_fixture='ratchet'
setup=Path(__file__).with_name('capture_reference_dynamics.py').read_text().split('labels=',1)[0]
exec(compile(setup,str(Path(__file__).with_name('capture_reference_dynamics.py')),'exec'),globals())
out=root/'recovered/self-shadows';out.mkdir(exist_ok=True)
controller.shadow_casters=[fur]
controller.enable_shadows=False
controller.refresh_animated_casters=False
controller.shadow_bias=.5
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['unshadowed','self-default','self-low-bias','wind-frozen','wind-refreshed','wind-unshadowed']
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
        if now-started>180:raise RuntimeError('Self-shadow capture timeout')
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
        row.update(material=material.get_path_name(),label=labels[stage],captures=controller.get_shadow_capture_count(),bias=controller.shadow_bias,elapsed=now-started)
        state['rows'].append(row)
        state.update(stage=stage+1,last=time.monotonic())
        if stage==0:controller.enable_shadows=True
        elif stage==1:controller.shadow_bias=.05
        elif stage==2:weather(0,.12,1.5)
        elif stage==3:controller.refresh_lighting()
        elif stage==4:controller.enable_shadows=False
        else:
            rows=state['rows']
            assert rows[2]['captures']==rows[3]['captures'],'Frozen WPO control recaptured'
            assert rows[4]['captures']>rows[3]['captures'],'WPO refresh missing'
            (out/'report.json').write_text(json.dumps(rows,indent=2));stop()
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
