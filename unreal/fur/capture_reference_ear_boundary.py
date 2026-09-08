"""Identify base versus nonbase contribution without altering coverage equations."""
from pathlib import Path
p=Path(__file__).with_name('capture_reference_environment.py')
exec(compile(p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0],str(p),'exec'),globals())
source=Path(builder.__file__).read_text()
marker='    for src,prop in [(output_color,'
assert source.count(marker)==1
source=source.replace(marker,"    if fur:\n        opacity=custom('return A * (D<0.00001 ? Base : Outer);',dict(A=opacity,D=pd,Base=scalar('ShowBase',1),Outer=scalar('ShowOuter',1)))\n        output_color=custom('return lerp(C,D<0.00001 ? float3(1,0,0) : float3(0,1,1),Debug);',dict(C=output_color,D=pd,Debug=scalar('DebugBoundary',0)),f3)\n"+marker)
ns={};exec(compile(source,'<boundary-builder>','exec'),ns)
material=ns['create']('M_EarBoundary_v1',textures,fur=True,recovered=True,temporal=True,scene=True,
    environment=test_environment,environment_brdf=test_environment_brdf,settings=shape,asset_path='/Game/FurValidation/Materials')
fur.fur_material=material;fur.shell_count=32;fur.rebuild_fur()
controller.enable_shadows=False;controller.set_environment(test_environment,test_environment_brdf,.6)
mat=fur.get_editor_property('shells').get_material(0)
out=root/'recovered/ear-boundary';out.mkdir(exist_ok=True)
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['reference','outer-only','base-only','colored'];settings=[(1,1,0),(0,1,0),(1,0,0),(1,1,1)]
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,rows=[])
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 try:
  now=time.monotonic()
  if now-started>140:raise RuntimeError('Boundary timeout')
  if now-state['draw']<.15:return
  state['busy']=True
  try:
   assert unreal.FurViewportProbe.advance();state['draw']=now
   if now-state['last']<(20 if state['stage']==0 else 8):return
   i=state['stage'];row=json.loads(unreal.FurViewportProbe.capture(str(out/(labels[i]+'.png'))))
   assert row['draw_realtime'] and row['resolved_aa_method']==2
   row.update(label=labels[i],settings=settings[i]);state['rows'].append(row)
   i+=1
   if i==len(labels):
    (out/'report.json').write_text(json.dumps(state['rows'],indent=2));stop();return
   for name,value in zip(('ShowBase','ShowOuter','DebugBoundary'),settings[i]):mat.set_scalar_parameter_value(name,value)
   state.update(stage=i,last=time.monotonic())
  finally:state['busy']=False
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
