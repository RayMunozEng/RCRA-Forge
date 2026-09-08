"""Calibrate raw WPO velocity against independent pinhole projection."""
from pathlib import Path
import math
environment_fixture='sheep'
p=Path(__file__).with_name('capture_reference_environment.py')
exec(compile(p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0],str(p),'exec'),globals())
out=root/'recovered/velocity-calibration-20260907';out.mkdir(exist_ok=True)
for actor in actors.get_all_level_actors():
 if actor!=camera:actor.set_actor_hidden_in_game(True)
forward=camera.get_actor_forward_vector();right=camera.get_actor_right_vector();up=camera.get_actor_up_vector()
box=actors.spawn_actor_from_class(unreal.StaticMeshActor,camera.get_actor_location()+forward*100,camera.get_actor_rotation())
box.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
box.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'))
box.set_actor_scale3d(unreal.Vector(.001,.6,.6))
box.static_mesh_component.set_cast_shadow(False)
lib=unreal.MaterialEditingLibrary;asset='/Game/FurValidation/Materials';name='M_VelocityCalibration_20260907_v1'
mat=unreal.load_asset(asset+'/'+name)
if not mat:
 mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,asset,unreal.Material,unreal.MaterialFactoryNew())
 mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
 switch=lib.create_material_expression(mat,unreal.MaterialExpressionPreviousFrameSwitch)
 for parameter,pin in [('CurrentOffset','Current Frame'),('PreviousOffset','Previous Frame')]:
  node=lib.create_material_expression(mat,unreal.MaterialExpressionVectorParameter)
  node.set_editor_property('parameter_name',parameter)
  assert lib.connect_material_expressions(node,'RGB',switch,pin)
 assert lib.connect_material_property(switch,'',unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
 white=lib.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector)
 white.set_editor_property('constant',unreal.LinearColor(1,1,1,1))
 assert lib.connect_material_property(white,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
 lib.recompile_material(mat);assert unreal.EditorAssetLibrary.save_loaded_asset(mat)
box.static_mesh_component.set_material(0,mat)
material=box.static_mesh_component.create_dynamic_material_instance(0)
current=right*.1
material.set_vector_parameter_value('CurrentOffset',unreal.LinearColor(current.x,current.y,current.z,0))
labels=['zero','right-small','right','left','up','down'];deltas=[(0,0),(.01,0),(1,0),(-1,0),(0,1),(0,-1)]
def previous(i):
 dx,dy=deltas[i];v=current-right*dx-up*dy
 material.set_vector_parameter_value('PreviousOffset',unreal.LinearColor(v.x,v.y,v.z,0))
previous(0)
assert unreal.FurViewportProbe.set_velocity_view(False)
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,pending=False,rows=[])
unreal.FurViewportProbe.enable_world_ticks(True)
def stop():
 state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
 unreal.unregister_slate_post_tick_callback(state['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
 if state['done'] or state['busy']:return
 try:
  now=time.monotonic()
  if now-started>140:raise RuntimeError('Calibration deadline')
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
     row.update(label=label,delta_camera_right_up_cm=deltas[i],front_depth_cm=99.95,horizontal_fov=camera.camera_component.field_of_view)
     state['rows'].append(row)
     unreal.FurViewportProbe.capture(str(out/(label+'.png')))
     if i+1==len(labels):
      (out/'report.json').write_text(json.dumps({'captures':state['rows'],'limits':'Known uniform WPO current/previous offsets on an owned camera-facing cube front at 99.95cm depth. Calibrates velocity readback, encoding, orientation and pixel scaling; does not validate the fur wind equation.'},indent=2));stop();return
     previous(i+1);state.update(stage=i+1,last=now,pending=False)
   elif now-state['last']>=(20 if i==0 else 2):
    assert unreal.FurViewportProbe.arm_velocity_readback(str(out/(label+'.f32')));state['pending']=True
   assert unreal.FurViewportProbe.advance();state['draw']=now
  finally:state['busy']=False
 except Exception:
  import traceback
  unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
