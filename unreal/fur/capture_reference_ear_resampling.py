"""Test count-normalized coverage without changing existing material defaults."""
from pathlib import Path
p=Path(__file__).with_name('capture_reference_environment.py')
exec(compile(p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0],str(p),'exec'),globals())
source=Path(builder.__file__).read_text()
source=source.replace('return RFCoverageWithMask(', 'return RFCountedCoverageWithMask(')
assert source.count("+cycle+',Alpha);'")==1
source=source.replace("+cycle+',Alpha);'", "+cycle+',Alpha,lerp(32,Count,Resample));'")
source=source.replace("Alpha=(color,'A')))", "Alpha=(color,'A'),Count=scalar('RecoveredShellCount',32),Resample=scalar('ResampleCoverage',0)))")
ns={};exec(compile(source,'<resampling-builder>','exec'),ns)
material=ns['create']('M_EarResampling_v1',textures,fur=True,recovered=True,temporal=True,scene=True,
 environment=test_environment,environment_brdf=test_environment_brdf,settings=shape,asset_path='/Game/FurValidation/Materials')
fur.fur_material=material;fur.shell_count=32;fur.rebuild_fur()
controller.enable_shadows=False;controller.set_environment(test_environment,test_environment_brdf,.6)
out=root/'recovered/ear-resampling';out.mkdir(exist_ok=True)
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['reference32','raw64','normalized64'];settings=[(32,0),(64,0),(64,1)]
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,rows=[])
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 try:
  now=time.monotonic()
  if now-started>140:raise RuntimeError('Resampling timeout')
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
   fur.shell_count=settings[i][0];fur.rebuild_fur();controller.refresh_lighting()
   fur.get_editor_property('shells').get_material(0).set_scalar_parameter_value('ResampleCoverage',settings[i][1])
   state.update(stage=i,last=time.monotonic())
  finally:state['busy']=False
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
