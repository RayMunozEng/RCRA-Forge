"""Stationary sheep: velocity controls and continuous wet/wind, private only."""
from pathlib import Path
environment_fixture='sheep'
p=Path(__file__).with_name('capture_reference_environment.py')
exec(compile(p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0],str(p),'exec'),globals())
out=root/'recovered/sheep-motion-20260907';out.mkdir(exist_ok=True)
controller.enable_shadows=False;controller.set_environment(test_environment,test_environment_brdf,.6)
materials=[fur.shells.get_material(0)]
for mat in materials:mat.set_scalar_parameter_value('UseWindTimeOverride',0)
stages=[('velocity-still',True,0,0,4,20),('velocity-wind',True,.12,0,8,3),
 ('dry-wind',False,.12,0,6,4),('wet-transition',False,.12,0,9,.2),
 ('wet-wind',False,.12,.8,6,3),('velocity-still-final',True,0,.8,4,3)]
started=time.monotonic();state=dict(stage=0,index=0,last=started,draw=started,busy=False,done=False,rows=[])
def apply_stage(i):
 label,velocity,wind,wet,count,warm=stages[i]
 assert unreal.FurViewportProbe.set_velocity_view(velocity)
 fur.set_weather(wet,wind)
 for mat in materials:mat.set_scalar_parameter_value('UseWindTimeOverride',0)
 state.update(stage=i,index=0,last=time.monotonic())
apply_stage(0)
unreal.FurViewportProbe.enable_world_ticks(True)
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 try:
  now=time.monotonic()
  if now-started>150:raise RuntimeError('Sheep motion capture deadline')
  if now-state['draw']<.1:return
  state['busy']=True
  try:
   label,velocity,wind,wet,count,warm=stages[state['stage']]
   index=state['index']
   if label=='wet-transition':fur.set_weather(index*.1,wind)
   assert unreal.FurViewportProbe.advance();state['draw']=now
   if now-state['last']<(warm if index==0 else .25):return
   row=json.loads(unreal.FurViewportProbe.capture(str(out/(label+'-'+str(index)+'.png'))))
   assert row['draw_realtime'] and row['velocity_view']==velocity
   if not velocity:assert row['resolved_aa_method']==2
   row.update(stage=label,index=index,world_time=unreal.GameplayStatics.get_time_seconds(world),
    wetness=materials[0].get_scalar_parameter_value('Wetness'),wind=materials[0].get_scalar_parameter_value('WindStrength'),
    manual_clock=materials[0].get_scalar_parameter_value('UseWindTimeOverride'),
    camera=[camera.get_actor_location().x,camera.get_actor_location().y,camera.get_actor_location().z])
   assert row['manual_clock']==0
   state['rows'].append(row);state.update(index=index+1,last=time.monotonic())
   if index+1==count:
    if state['stage']+1==len(stages):
     (out/'report.json').write_text(json.dumps({'captures':state['rows'],
      'limits':'Engine Velocity buffer visualization, not raw floating-point vectors. Fixed camera and mesh; only fur WPO wind animates. Live game clock and TAA; no native parity claim. Wetness transitions change appearance, not shell length.'},indent=2));stop();return
    apply_stage(state['stage']+1)
  finally:state['busy']=False
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
