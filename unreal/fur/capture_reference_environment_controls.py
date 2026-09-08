"""Exercise Details/Blueprint environment settings and material rebuild rebinding."""
from pathlib import Path
p=Path(__file__).with_name('capture_reference_environment.py')
setup=p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0]
exec(compile(setup,str(p),'exec'),globals())
out=root/'recovered/environment-controls';out.mkdir(exist_ok=True)
controller.enable_shadows=False
controller.override_environment=True;controller.enable_environment=False
controller.environment_cube=test_environment;controller.environment_brdf=test_environment_brdf
controller.refresh_lighting()
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['disabled','enabled','double','rebuilt','disabled-again','missing-brdf','restored','material-defaults']
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,rows=[])
def stop():
    state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
    if state['done'] or state['busy']:return
    try:
        now=time.monotonic()
        if now-started>180:raise RuntimeError('Environment controls timeout')
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
        mat=fur.get_editor_property('shells').get_material(0)
        value=mat.get_scalar_parameter_value('EnvironmentIntensity')
        expected=[0,.6,1.2,1.2,0,0,.9,.6][stage]
        assert abs(value-expected)<1e-5,(stage,value,expected)
        if stage==7:assert abs(mat.get_scalar_parameter_value('Wetness')-.8)<1e-5
        row.update(label=labels[stage],intensity=value,status=controller.environment_status,wetness=mat.get_scalar_parameter_value('Wetness'))
        state['rows'].append(row);state.update(stage=stage+1,last=time.monotonic())
        if stage==0:controller.set_environment(test_environment,test_environment_brdf,.6)
        elif stage==1:controller.environment_intensity=1.2
        elif stage==2:fur.rebuild_fur()
        elif stage==3:controller.enable_environment=False
        elif stage==4:controller.enable_environment=True;controller.environment_brdf=None
        elif stage==5:controller.set_environment(test_environment,test_environment_brdf,.9);fur.set_weather(.8,0)
        elif stage==6:controller.override_environment=False
        else:
            (out/'report.json').write_text(json.dumps(state['rows'],indent=2));stop()
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
