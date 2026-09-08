"""One-shot raw sheep velocity controls; private viewport only."""
from pathlib import Path
environment_fixture='sheep'
p=Path(__file__).with_name('capture_reference_environment.py')
exec(compile(p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0],str(p),'exec'),globals())
out=root/'recovered/sheep-velocity-float-20260907';out.mkdir(exist_ok=True)
controller.enable_shadows=False;controller.set_environment(test_environment,test_environment_brdf,.6)
materials=[fur.shells.get_material(0)]
for mat in materials:mat.set_scalar_parameter_value('UseWindTimeOverride',0)
assert unreal.FurViewportProbe.set_velocity_view(False)
labels=['still','wind-a','wind-b','returned-still'];strengths=[0,.12,.12,0];warm=[20,3,1,3]
fur.set_weather(0,0)
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,pending=False,rows=[])
unreal.FurViewportProbe.enable_world_ticks(True)
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 try:
  now=time.monotonic()
  if now-started>130:raise RuntimeError('Velocity readback timeout')
  if now-state['draw']<.1:return
  state['busy']=True
  try:
   i=state['stage'];label=labels[i]
   if state['pending']:
    status=unreal.FurViewportProbe.velocity_readback_status()
    if status.startswith('error'):raise RuntimeError(status)
    if status=='complete':
     path=out/(label+'.f32');row=json.loads(Path(str(path)+'.json').read_text())
     assert row['saved'] and path.stat().st_size==row['width']*row['height']*16
     row.update(label=label,wind=materials[0].get_scalar_parameter_value('WindStrength'),manual_clock=materials[0].get_scalar_parameter_value('UseWindTimeOverride'))
     assert row['manual_clock']==0
     state['rows'].append(row)
     unreal.FurViewportProbe.capture(str(out/(label+'.png')))
     if i+1==len(labels):
      (out/'report.json').write_text(json.dumps({'captures':state['rows'],'limits':'Linear float readback of native encoded velocity texture before postprocess, fixed camera, dry fur. Float32 storage does not add precision to the native 16-bit texture. Screenshots are context, not necessarily the exact readback frame.'},indent=2));stop();return
     state.update(stage=i+1,last=now,pending=False);fur.set_weather(0,strengths[i+1])
   elif now-state['last']>=warm[i]:
    assert unreal.FurViewportProbe.arm_velocity_readback(str(out/(label+'.f32')))
    state['pending']=True
   assert unreal.FurViewportProbe.advance();state['draw']=now
  finally:state['busy']=False
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
