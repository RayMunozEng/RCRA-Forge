"""Private comparison of recovered signed facing and the old absolute-facing adapter."""
from pathlib import Path
p=Path(__file__).with_name('capture_reference_environment.py')
exec(compile(p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0],str(p),'exec'),globals())
source=Path(builder.__file__).read_text()
old='saturate(dot(normalize(Parameters.TangentToWorld[2])*Parameters.TwoSidedSign,V))'
assert source.count(old)==1
source=source.replace(old,'lerp(abs(dot(normalize(N),V)),saturate(dot(normalize(Parameters.TangentToWorld[2])*Parameters.TwoSidedSign,V)),SignedFacing)')
old_input="Wet=wet,N=pn,V=view,Alpha=(color,'A')"
assert source.count(old_input)==1
source=source.replace(old_input,old_input+",SignedFacing=scalar('SignedFacing',0)")
ns={};exec(compile(source,'<ear-facing-builder>','exec'),ns)
material=ns['create']('M_EarFacing_v1',textures,fur=True,recovered=True,temporal=True,scene=True,
 environment=test_environment,environment_brdf=test_environment_brdf,settings=shape,asset_path='/Game/FurValidation/Materials')
fur.fur_material=material;fur.shell_count=32;fur.rebuild_fur()
controller.enable_shadows=False;controller.set_environment(test_environment,test_environment_brdf,.6)
mat=fur.shells.get_material(0)
out=root/'recovered/ear-facing-audit';out.mkdir(exist_ok=True)
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['absolute-a','absolute-b','signed-a','signed-b']
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,rows=[])
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 state['busy']=True
 try:
  now=time.monotonic()
  if now-started>140:raise RuntimeError('Ear facing timeout')
  if now-state['draw']<.1:return
  assert unreal.FurViewportProbe.advance();state['draw']=now
  if now-state['last']<(20 if state['stage'] in (0,2) else 6):return
  i=state['stage'];row=json.loads(unreal.FurViewportProbe.capture(str(out/(labels[i]+'.png'))))
  assert row['draw_realtime'] and row['resolved_aa_method']==2
  row.update(label=labels[i],signed_facing=mat.get_scalar_parameter_value('SignedFacing'));state['rows'].append(row)
  i+=1
  if i==len(labels):
   (out/'capture-report.json').write_text(json.dumps(state['rows'],indent=2));stop();return
  if i==2:mat.set_scalar_parameter_value('SignedFacing',1)
  state.update(stage=i,last=time.monotonic())
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
 finally:state['busy']=False
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
