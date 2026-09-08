"""Dry static fur rapid translation and disocclusion, persistent TAA viewport."""
from pathlib import Path
environment_fixture=globals().get('dry_fixture','ratchet')
p=Path(__file__).with_name('capture_reference_environment.py')
exec(compile(p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0],str(p),'exec'),globals())
out=root/'recovered'/('dry-motion-'+fixture+'-20260907');out.mkdir(exist_ok=True)
controller.enable_shadows=False
fur.set_weather(0,0)
for mat in materials:mat.set_scalar_parameter_value('EnvironmentIntensity',.6)
shift=camera.get_actor_right_vector()*15
# Move the complete imported character, including non-fur eyes/helmet/skin.
moving=[a for a in actors.get_all_level_actors() if a==fur or isinstance(a,unreal.StaticMeshActor)]
origins=[a.get_actor_location() for a in moving]
for actor in moving:
 component=actor.get_editor_property('shells') if actor==fur else actor.static_mesh_component
 component.set_mobility(unreal.ComponentMobility.MOVABLE)
fur.get_editor_property('shells').set_mobility(unreal.ComponentMobility.MOVABLE)
unreal.FurViewportProbe.enable_world_ticks(True)
started=time.monotonic();state=dict(last=started,draw=started,busy=False,done=False,rows=[],moved=False)
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle']);unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 try:
  now=time.monotonic()
  if now-started>160:raise RuntimeError('Dry motion deadline')
  if now-state['draw']<.1:return
  state['busy']=True
  try:
   if not state['rows'] and now-started<20:
    unreal.FurViewportProbe.advance();state['draw']=now;return
   i=len(state['rows'])
   if i==1 and not state['moved']:
    for actor,origin in zip(moving,origins):actor.set_actor_location(origin+shift,False,False)
    state['moved']=True
   assert unreal.FurViewportProbe.advance()
   label='before' if i==0 else ('settled' if i==13 else 'move-'+str(i-1))
   row=json.loads(unreal.FurViewportProbe.capture(str(out/(label+'.png'))))
   assert row['draw_realtime'] and row['resolved_aa_method']==2,row
   row.update(label=label,elapsed=now-started,wetness=materials[0].get_scalar_parameter_value('Wetness'),wind=materials[0].get_scalar_parameter_value('WindStrength'))
   assert row['wetness']==0 and row['wind']==0
   state['rows'].append(row);state['draw']=time.monotonic()
   if i==13:
    (out/'report.json').write_text(json.dumps(dict(fixture=fixture,captures=state['rows'],translation_cm=15,limits='Abrupt15cm rigid translation of the full imported character with dry fur against black background. Capture samples are not guaranteed consecutive engine frames. Does not establish skeletal disocclusion or native parity.'),indent=2));stop()
  finally:state['busy']=False
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick);unreal.EditorPythonScripting.set_keep_python_script_alive(True)
