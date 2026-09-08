"""Continuous editor animation and live material-time wind, captured without focus."""
from pathlib import Path
dynamics_fixture='skeletal'
setup=Path(__file__).with_name('capture_reference_dynamics.py').read_text().split('labels=',1)[0]
exec(compile(setup,str(Path(__file__).with_name('capture_reference_dynamics.py')),'exec'),globals())
out=root/'recovered/continuous';out.mkdir(exist_ok=True)
fur.set_weather(.5,.12)
for mat in materials:mat.set_scalar_parameter_value('UseWindTimeOverride',0)
source.set_play_rate(1)
unreal.FurViewportProbe.enable_world_ticks(True)
started=time.monotonic()
state=dict(last=started,draw=started,busy=False,done=False,rows=[])
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
        if now-started>160:raise RuntimeError('Continuous capture timeout')
        if now-state['draw']>=.1:
            state['busy']=True
            try:assert unreal.FurViewportProbe.advance()
            finally:state['busy']=False
            state['draw']=now
        if now-state['last']<(20 if not state['rows'] else .25):return
        state['busy']=True
        try:
            assert unreal.FurViewportProbe.advance()
            row=json.loads(unreal.FurViewportProbe.capture(str(out/('frame-'+str(len(state['rows']))+'.png'))))
        finally:state['busy']=False
        assert row['draw_realtime'] and row['resolved_aa_method']==2
        row['animation_position']=source.get_position()
        row['elapsed']=now-started
        row['world_time']=unreal.GameplayStatics.get_time_seconds(world)
        row['manual_wind_clock']=materials[0].get_scalar_parameter_value('UseWindTimeOverride')
        assert row['manual_wind_clock']==0
        row['bones']=[[p.x,p.y,p.z] for p in (source.get_socket_location(source.get_bone_name(i)) for i in range(source.get_num_bones()))]
        state['rows'].append(row);state['last']=time.monotonic()
        if len(state['rows'])==16:
            assert len({round(r['animation_position'],3) for r in state['rows']})>4,'Editor animation did not advance'
            (out/'report.json').write_text(json.dumps(state['rows'],indent=2));stop()
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
