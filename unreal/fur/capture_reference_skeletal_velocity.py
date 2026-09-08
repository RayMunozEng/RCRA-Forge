"""Raw skeletal fur motion during live animation and after stopping."""
from pathlib import Path
p=Path(__file__).with_name('capture_reference_dynamics.py')
exec(compile(p.read_text().split("labels=(",1)[0],str(p),'exec'),globals())
out=root/'recovered/skeletal-velocity-20260907';out.mkdir(exist_ok=True)
source.set_visibility(False,False)
for layer in layers:layer.set_visibility(True,False)
assert unreal.FurViewportProbe.set_velocity_view(False)
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['still','walk-a','walk-b','stopped']
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,pending=False,rows=[])
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 try:
  now=time.monotonic()
  if now-started>140:raise RuntimeError('Skeletal velocity deadline')
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
     error=0;pose=[]
     for b in range(source.get_num_bones()):
      bone=source.get_bone_name(b);v=source.get_socket_location(bone);pose.append([v.x,v.y,v.z])
      for layer in layers:error=max(error,(v-layer.get_socket_location(bone)).length())
     assert error<.001,error
     row.update(label=label,bone_follow_error_cm=error,bone_positions=pose)
     state['rows'].append(row)
     unreal.FurViewportProbe.capture(str(out/(label+'.png')))
     if i+1==len(labels):
      (out/'report.json').write_text(json.dumps(dict(captures=state['rows'],limits='Live tutorial skeleton with production fur shells. Tests velocity activity and settling; no per-vertex vector ground truth or retail animation parity.'),indent=2));stop();return
     source.set_play_rate(1 if i<2 else 0)
     state.update(stage=i+1,last=now,pending=False)
   elif now-state['last']>=(20 if i==0 else 3):
    assert unreal.FurViewportProbe.arm_velocity_readback(str(out/(label+'.f32')));state['pending']=True
   assert unreal.FurViewportProbe.advance();state['draw']=now
  finally:state['busy']=False
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
