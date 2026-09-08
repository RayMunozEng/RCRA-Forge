"""Private UE moving/held ear fixture; no saved map or production changes."""
from pathlib import Path
import math
p=Path(__file__).with_name('capture_reference_environment.py')
setup=p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0]
exec(compile(setup,str(p),'exec'),globals())
out=root/'recovered/ue-ear-sequence';out.mkdir(exist_ok=True)
controller.enable_shadows=False
controller.set_environment(test_environment,test_environment_brdf,.6)
fur.shell_count=32;fur.rebuild_fur();controller.refresh_lighting()

reference=json.loads((root/'recovered/forge-environment-ratchet-both-scene-sequence/sequence.json').read_text())
forge_camera=json.loads((root/'recovered/forge-environment-ratchet-both-scene-sequence/report.json').read_text())['camera']
def convert(v):return unreal.Vector(v[0]*100,v[2]*100,v[1]*100)
vertices=[convert(v) for v in reference['plane_vertices']]
center=(vertices[0]+vertices[2])*.5
right=vertices[1]-vertices[0];up=vertices[2]-vertices[1]
normal=unreal.MathLibrary.cross_vector_vector(right,up)
plane=actors.spawn_actor_from_class(unreal.StaticMeshActor,center,unreal.MathLibrary.make_rot_from_z(normal))
plane.set_actor_label('Private Ear Background')
plane.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'))
plane.set_actor_scale3d(unreal.Vector(20,20,.001))
plane.static_mesh_component.set_cast_shadow(False)
name='M_EarBackground_Black_v1';path='/Game/FurValidation/Materials'
black=unreal.load_asset(path+'/'+name)
if not black:
    black=unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,path,unreal.Material,unreal.MaterialFactoryNew())
    black.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
    node=unreal.MaterialEditingLibrary.create_material_expression(black,unreal.MaterialExpressionConstant3Vector)
    node.set_editor_property('constant',unreal.LinearColor(0,0,0,1))
    unreal.MaterialEditingLibrary.connect_material_property(node,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    unreal.MaterialEditingLibrary.recompile_material(black)
    unreal.EditorAssetLibrary.save_loaded_asset(black)
plane.static_mesh_component.set_material(0,black)
plane.set_actor_hidden_in_game(True)

def set_camera(yaw):
    pitch=math.radians(forge_camera['pitch']);angle=math.radians(yaw)
    t=forge_camera['target'];d=forge_camera['distance']
    position=convert([t[0]+math.cos(angle)*math.cos(pitch)*d,
                      t[1]+math.sin(pitch)*d,t[2]+math.sin(angle)*math.cos(pitch)*d])
    camera.set_actor_location_and_rotation(position,unreal.MathLibrary.find_look_at_rotation(position,convert(t)),False,True)
    return [position.x,position.y,position.z]

set_camera(30)
unreal.FurViewportProbe.enable_world_ticks(True)
started=time.monotonic()
state=dict(mode=0,index=0,last=started,warm_until=started+20,busy=False,done=False,rows=[])
def stop():
    state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')

def tick(delta):
    if state['busy'] or state['done']:return
    try:
        now=time.monotonic()
        if now-started>150:raise RuntimeError('Ear sequence deadline')
        if now-state['last']<.15:return
        state['busy']=True
        try:
            if now<state['warm_until']:
                assert unreal.FurViewportProbe.advance()
            else:
                mode=('empty','scene')[state['mode']];index=state['index']
                yaw=reference['frames'][index]['yaw'];position=set_camera(yaw)
                assert unreal.FurViewportProbe.advance()
                folder=out/mode;folder.mkdir(exist_ok=True)
                row=json.loads(unreal.FurViewportProbe.capture(str(folder/f'{index:02d}.png')))
                assert row['draw_realtime'] and row['resolved_aa_method']==2
                row.update(mode=mode,yaw=yaw,eye_cm=position,phase='moving' if index<12 else 'held',index=index)
                state['rows'].append(row);state['index']+=1
                if state['index']==24:
                    if state['mode']==0:
                        state.update(mode=1,index=0,warm_until=time.monotonic()+20)
                        plane.set_actor_hidden_in_game(False);set_camera(30)
                    else:
                        (out/'report.json').write_text(json.dumps(dict(captures=state['rows'],
                            plane_center_cm=[center.x,center.y,center.z],plane_vertices_forge=reference['plane_vertices'],
                            limits='UE TAA2; same camera path and mapped plane, thin cube approximation. UE temporal phases/capture cadence differ from Forge. No recovered contact/denoise. Within-engine diagnostic, not cross-engine pixel parity.'),indent=2))
                        stop()
        finally:state['busy']=False;state['last']=time.monotonic()
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
