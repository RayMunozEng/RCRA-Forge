"""Private sheep input probes; no production material changes."""
from pathlib import Path
p=Path(__file__).with_name('capture_reference_environment.py')
environment_fixture='sheep'
exec(compile(p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0],str(p),'exec'),globals())
source=Path(builder.__file__).read_text()
marker='return RFSceneDirect(n,strand,normalize(V.xzy),'
assert source.count(marker)==1
source=source.replace(marker,'''uint4 packedProbe=furPackGBuffer(n,response.x,response.y,0u);
float3 normalProbe=furUnpackNormal(packedProbe);
if(Probe>0.5 && Probe<1.5) return normalProbe*.5+.5;
if(Probe>1.5 && Probe<2.5) return Albedo;
if(Probe>2.5 && Probe<3.5) return float3(float(packedProbe.w & 255u)/255.0,float(packedProbe.w >> 8u)/255.0,AO);
if(Probe>3.5) return FurEnvironment.SampleLevel(FurEnvironmentSampler,normalProbe.xzy,5).rgb*.6;
'''+marker)
marker="Scale=scalar('OffsetScale',settings['offset']),Transmission="
assert source.count(marker)==1
source=source.replace(marker,"Probe=scalar('LightingProbe',0),"+marker)
ns={};exec(compile(source,'<sheep-lighting-input-builder>','exec'),ns)
material=ns['create']('M_SheepLightingInputs_20260907_v1',textures,fur=True,recovered=True,temporal=True,scene=True,
 environment=test_environment,environment_brdf=test_environment_brdf,settings=shape,asset_path='/Game/FurValidation/Materials')
fur.fur_material=material;fur.rebuild_fur()
controller.enable_shadows=False;controller.set_environment(test_environment,test_environment_brdf,.6)
materials=[fur.shells.get_material(0)];weather(0,0,0)
out=root/'recovered/environment-sheep-inputs';out.mkdir(exist_ok=True)
labels=['combined','normal','albedo','response','diffuse']
unreal.FurViewportProbe.enable_world_ticks(True)
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,rows=[])
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 try:
  now=time.monotonic()
  if now-started>180:raise RuntimeError('Lighting inputs timeout')
  if now-state['draw']<.1:return
  state['busy']=True
  try:
   assert unreal.FurViewportProbe.advance();state['draw']=now
   if now-state['last']<(25 if state['stage']==0 else 8):return
   i=state['stage'];row=json.loads(unreal.FurViewportProbe.capture(str(out/(labels[i]+'.png'))))
   assert row['draw_realtime'] and row['resolved_aa_method']==2
   row.update(label=labels[i],material=material.get_path_name(),parameters={k:materials[0].get_scalar_parameter_value(k) for k in ('EnvironmentIntensity','EnvironmentMaxMip','EnvironmentRecoveredAxes','Wetness','LightingProbe')})
   state['rows'].append(row);i+=1
   if i==len(labels):
    (out/'report.json').write_text(json.dumps(state['rows'],indent=2));stop();return
   materials[0].set_scalar_parameter_value('LightingProbe',i)
   state.update(stage=i,last=time.monotonic())
  finally:state['busy']=False
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
