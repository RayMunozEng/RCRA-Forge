"""Controlled skeletal pose steps with CPU vertex references."""
from pathlib import Path
p=Path(__file__).with_name('capture_reference_dynamics.py')
exec(compile(p.read_text().split("labels=(",1)[0],str(p),'exec'),globals())
out=root/'recovered/skeletal-accuracy-20260907';out.mkdir(exist_ok=True)
source.set_visibility(False,False)
source.set_forced_lod(1)
# One production leader-pose follower with an opaque zero-WPO material isolates skinning.
lib=unreal.MaterialEditingLibrary
mat=unreal.load_asset('/Game/FurValidation/Materials/M_SkeletalAccuracy_v1')
if not mat:
 mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_SkeletalAccuracy_v1','/Game/FurValidation/Materials',unreal.Material,unreal.MaterialFactoryNew())
 mat.set_editor_property('used_with_skeletal_mesh',True)
 mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
 n=lib.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector);n.set_editor_property('constant',unreal.LinearColor(1,1,1,1))
 lib.connect_material_property(n,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
 lib.recompile_material(mat);unreal.EditorAssetLibrary.save_loaded_asset(mat)
for i,layer in enumerate(layers):
 layer.set_visibility(i==0,False);layer.set_forced_lod(1)
 for slot in range(layer.get_num_materials()):layer.set_material(slot,mat)
assert unreal.FurViewportProbe.set_velocity_view(False)
command('r.AntiAliasingMethod 0')
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['still','step-a','step-b','settled'];times=[0,.01,.02,.02]
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,pending=False,rows=[])
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 try:
  now=time.monotonic()
  if now-started>140:raise RuntimeError('Skeletal accuracy deadline')
  if now-state['draw']<.1:return
  state['busy']=True
  try:
   i=state['stage'];label=labels[i]
   if state['pending']:
    status=unreal.FurViewportProbe.velocity_readback_status()
    if status.startswith('error'):raise RuntimeError(status)
    if status=='complete':
     path=out/(label+'.f32');row=json.loads(Path(str(path)+'.json').read_text());assert row['saved']
     row.update(label=label,previous_time=times[max(0,i-1)],current_time=times[i],eye=[eye.x,eye.y,eye.z],basis={k:[v.x,v.y,v.z] for k,v in [('forward',camera.get_actor_forward_vector()),('right',camera.get_actor_right_vector()),('up',camera.get_actor_up_vector())]},horizontal_fov=50)
     state['rows'].append(row);unreal.FurViewportProbe.capture(str(out/(label+'.png')))
     if i+1==len(labels):
      (out/'report.json').write_text(json.dumps(dict(captures=state['rows'],limits='LOD0 opaque leader-pose follower, fixed camera, AA off, no WPO. CPU-skinned vertices provide pose projection reference.'),indent=2));stop();return
     state.update(stage=i+1,last=now,pending=False)
   elif now-state['last']>=(20 if i==0 else 2):
    assert unreal.FurViewportProbe.save_skinned_pose(source,str(out/(label+'-previous.json')))
    source.set_position(times[i],False);assert fur.refresh_preview_pose()
    assert unreal.FurViewportProbe.save_skinned_pose(source,str(out/(label+'-current.json')))
    unreal.FurViewportProbe.flush_pose_updates(source)
    assert unreal.FurViewportProbe.arm_velocity_readback(str(out/(label+'.f32')));state['pending']=True
   assert unreal.FurViewportProbe.advance();state['draw']=now
  finally:state['busy']=False
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
