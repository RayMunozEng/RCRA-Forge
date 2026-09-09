from pathlib import Path
dynamics_fixture=globals().get('surface_fixture','sheep')
dynamics_material='M_FurSurface_'+dynamics_fixture+'_v2'
fur_surface_outputs=True
surface_filter_mode=globals().get('surface_filter_mode','probe')
p=Path(__file__).with_name('capture_reference_dynamics.py')
exec(compile(p.read_text(encoding='utf-8').split('labels=',1)[0],str(p),'exec'),globals())
surface_output_tag=('fur-surface-production-' if surface_filter_mode=='production' else 'fur-surface-live-')+dynamics_fixture
out=root/'recovered'/surface_output_tag;out.mkdir(exist_ok=True)
controller.enable_shadows=False
fill=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(),unreal.MathLibrary.find_look_at_rotation(unreal.Vector(-1,1,.4),unreal.Vector()))
rim=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(),unreal.MathLibrary.find_look_at_rotation(unreal.Vector(-.8,-1,.5),unreal.Vector()))
fill.light_component.set_light_color(unreal.LinearColor(.25,.55,1,1))
rim.light_component.set_light_color(unreal.LinearColor(1,.3,.06,1))
fill.light_component.set_intensity(2*3.14159265);rim.light_component.set_intensity(3*3.14159265)
controller.key_light.light_component.set_editor_property('forward_shading_priority',10)
controller.fill_light=fill;controller.rim_light=rim;controller.refresh_lighting()
started=time.monotonic();state=dict(last=started,busy=False,armed=False,done=False,stage=0,stage_time=started,rows=[])
def stop():
 state['done']=True
 if surface_filter_mode=='production':command('r.FurAuthoring.Denoise 0')
 else:unreal.FurViewportProbe.set_surface_filter_enabled(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['busy'] or state['done']:return
 state['busy']=True
 try:
  now=time.monotonic()
  if now-started>150:raise RuntimeError('surface capture deadline')
  if now-state['last']<.1:return
  state['last']=now
  assert unreal.FurViewportProbe.advance()
  if not state['armed'] and now-started>25:
   assert unreal.FurViewportProbe.arm_surface_readback(str(out/'surface'))
   state['armed']=True
  if state['armed']:
   status=unreal.FurViewportProbe.surface_readback_status()
   if state['stage']==0:
    if status.startswith('error: no fur batches'):
     state['armed']=False;state['last']=now+1.9
     return
    if status.startswith('error'):raise RuntimeError(status)
    if status=='complete':state.update(stage=1,stage_time=now)
   elif now-state['stage_time']>({1:15,2:5,3:20,4:5}[state['stage']]):
    stage=state['stage'];label={1:'unfiltered-a',2:'unfiltered-b',3:'filtered-a',4:'filtered-b'}[stage]
    row=json.loads(unreal.FurViewportProbe.capture(str(out/(label+'.png'))));row['label']=label
    if surface_filter_mode=='production':
     row['production_filter_enabled']=unreal.FurDenoiseLibrary.is_recovered_fur_denoise_enabled()
    state['rows'].append(row)
    if stage==2:
     if surface_filter_mode=='production':command('r.FurAuthoring.Denoise 1')
     else:assert unreal.FurViewportProbe.set_surface_filter_enabled(True)
    if stage==4:
     (out/'report.json').write_text(json.dumps(dict(status='complete',filter_mode=surface_filter_mode,material=material.get_path_name(),frames=state['rows']),indent=2),encoding='utf-8')
     if globals().get('verify_kernel',False):
      import runpy
      runpy.run_path(str(root/'capture_denoise_kernel.py'))
     unreal.log('FUR_SURFACE_LIVE_OK');stop()
    else:state.update(stage=stage+1,stage_time=now)

 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
 finally:state['busy']=False
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
