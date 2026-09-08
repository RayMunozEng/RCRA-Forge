"""Separate ear shell banding from lighting and the base mesh silhouette."""
from pathlib import Path
dynamics_fixture='ratchet'
setup=Path(__file__).with_name('capture_reference_dynamics.py').read_text().split('labels=',1)[0]
exec(compile(setup,str(Path(__file__).with_name('capture_reference_dynamics.py')),'exec'),globals())
out=root/'recovered/ear-contours';out.mkdir(exist_ok=True)
controller.enable_shadows=False
controller.override_environment=True;controller.enable_environment=False
unlit=builder.create('M_EarCoverage_Unlit_v1',textures,fur=True,unlit=True,temporal=True,
    settings=shape,asset_path='/Game/FurValidation/Materials')
fur.shell_count=32;fur.rebuild_fur()
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['lit-32','unlit-32','unlit-16','unlit-64','base-only']
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,rows=[])
def stop():
    state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
    if state['done'] or state['busy']:return
    try:
        now=time.monotonic()
        if now-started>150:raise RuntimeError('Ear contour capture timeout')
        if now-state['draw']>=.1:
            state['busy']=True
            try:assert unreal.FurViewportProbe.advance()
            finally:state['busy']=False
            state['draw']=now
        stage=state['stage']
        if now-state['last']<(20 if stage==0 else 8):return
        state['busy']=True
        try:
            assert unreal.FurViewportProbe.advance()
            row=json.loads(unreal.FurViewportProbe.capture(str(out/(labels[stage]+'.png'))))
        finally:state['busy']=False
        assert row['draw_realtime'] and row['resolved_aa_method']==2
        row.update(label=labels[stage],shell_count=fur.shell_count,length_cm=fur.length,material=fur.fur_material.get_path_name())
        state['rows'].append(row);state.update(stage=stage+1,last=time.monotonic())
        if stage==0:fur.set_editor_property('fur_material',unlit)
        elif stage==1:fur.shell_count=16
        elif stage==2:fur.shell_count=64
        elif stage==3:fur.shell_count=1;fur.length=0
        else:
            (out/'report.json').write_text(json.dumps(state['rows'],indent=2));stop();return
        fur.rebuild_fur()
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
