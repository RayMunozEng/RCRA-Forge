"""Spatial shell-spacing experiment; original geometry endpoints remain fixed."""
from pathlib import Path
p=Path(__file__).with_name('capture_reference_environment.py')
exec(compile(p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0],str(p),'exec'),globals())
source=Path(builder.__file__).read_text()
marker='        pd=node(unreal.MaterialExpressionVertexInterpolator)'
assert source.count(marker)==1
source=source.replace(marker,"""        depth=custom('float end=(Count-1)/max(Count,1); float t=D/max(end,0.00001); float noise=0.5*(sin(dot(P,float3(1.73,2.39,3.11)))+sin(dot(P,float3(-2.67,1.13,2.03)))); return D+Amount*0.45/max(Count,1)*noise*4*t*(1-t);',dict(D=depth,P=node(unreal.MaterialExpressionPreSkinnedPosition),Count=scalar('RecoveredShellCount',32),Amount=scalar('SpatialSpacing',0)))
"""+marker)
ns={};exec(compile(source,'<spacing-builder>','exec'),ns)
material=ns['create']('M_EarSpacing_v2',textures,fur=True,recovered=True,temporal=True,scene=True,
 environment=test_environment,environment_brdf=test_environment_brdf,settings=shape,asset_path='/Game/FurValidation/Materials')
fur.fur_material=material;fur.shell_count=32;fur.rebuild_fur()
controller.enable_shadows=False;controller.set_environment(test_environment,test_environment_brdf,.6)
out=root/'recovered/ear-spacing';out.mkdir(exist_ok=True)
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['reference','spacing-half','spacing-full'];values=[0,.5,1]
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,rows=[])
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 try:
  now=time.monotonic()
  if now-started>140:raise RuntimeError('Spacing timeout')
  if now-state['draw']<.15:return
  state['busy']=True
  try:
   assert unreal.FurViewportProbe.advance();state['draw']=now
   if now-state['last']<(20 if state['stage']==0 else 8):return
   i=state['stage'];row=json.loads(unreal.FurViewportProbe.capture(str(out/(labels[i]+'.png'))))
   assert row['draw_realtime'] and row['resolved_aa_method']==2
   row.update(label=labels[i],spacing=values[i]);state['rows'].append(row)
   i+=1
   if i==len(labels):
    (out/'report.json').write_text(json.dumps(state['rows'],indent=2));stop();return
   fur.get_editor_property('shells').get_material(0).set_scalar_parameter_value('SpatialSpacing',values[i])
   state.update(stage=i,last=time.monotonic())
  finally:state['busy']=False
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
