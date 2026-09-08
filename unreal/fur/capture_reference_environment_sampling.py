"""Display six cube axes at six mip levels and BRDF coordinate probes."""
from pathlib import Path
p=Path(__file__).with_name('capture_reference_environment.py')
setup=p.read_text().split("out=root/'recovered'/('environment-'+fixture)",1)[0]
exec(compile(setup,str(p),'exec'),globals())
out=root/'recovered/environment-sampling';out.mkdir(exist_ok=True)
lib=unreal.MaterialEditingLibrary
path='/Game/FurValidation/Materials'
name='M_EnvironmentSampling_v2'
diag=unreal.load_asset(path+'/'+name)
if not diag:
    diag=unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,path,unreal.Material,unreal.MaterialFactoryNew())
    diag.set_editor_property('two_sided',True);diag.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
    n=lib.create_material_expression(diag,unreal.MaterialExpressionCustom)
    n.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    n.set_editor_property('code','''
float2 uv=Parameters.SvPosition.xy*View.ViewSizeAndInvSize.zw;
int face=clamp(int(uv.x*6),0,5);
int row=clamp(int(uv.y*7),0,6);
float3 directions[6]={float3(1,0,0),float3(-1,0,0),float3(0,1,0),float3(0,-1,0),float3(0,0,1),float3(0,0,-1)};
if(row<6) return Cube.SampleLevel(CubeSampler,directions[face],row).rgb;
return float3(Lut.SampleLevel(LutSampler,float2((face+.5)/6,.5),0).rg,0);
''')
    fields=[]
    for key,texture in [('Cube',test_environment),('Lut',test_environment_brdf)]:
        field=unreal.CustomInput();field.set_editor_property('input_name',key);fields.append(field)
    n.set_editor_property('inputs',fields)
    for key,texture in [('Cube',test_environment),('Lut',test_environment_brdf)]:
        obj=lib.create_material_expression(diag,unreal.MaterialExpressionTextureObject)
        obj.set_editor_property('texture',texture);obj.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        assert lib.connect_material_expressions(obj,'',n,key)
    assert lib.connect_material_property(n,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    lib.recompile_material(diag);assert unreal.EditorAssetLibrary.save_loaded_asset(diag)
for actor in actors.get_all_level_actors():
    if actor!=camera:actor.set_actor_hidden_in_game(True)
box=actors.spawn_actor_from_class(unreal.StaticMeshActor,eye)
box.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'))
box.set_actor_scale3d(unreal.Vector(100,100,100));box.static_mesh_component.set_material(0,diag)
unreal.FurViewportProbe.enable_world_ticks(True)
started=time.monotonic();state=dict(draw=started,busy=False,done=False)
def stop():
    state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
    if state['done'] or state['busy']:return
    try:
        now=time.monotonic()
        if now-started>100:raise RuntimeError('Sampling capture timeout')
        if now-state['draw']<.1:return
        state['busy']=True
        try:assert unreal.FurViewportProbe.advance()
        finally:state['busy']=False
        state['draw']=now
        if now-started<20:return
        row=json.loads(unreal.FurViewportProbe.capture(str(out/'sampling.png')))
        assert row['draw_realtime'] and row['resolved_aa_method']==2
        (out/'report.json').write_text(json.dumps(row,indent=2));stop()
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
