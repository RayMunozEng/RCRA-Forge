"""Import the private Ratchet fixture without modifying distributable content."""
import importlib.util
import json
from pathlib import Path
import unreal

root=Path(__file__).resolve().parent
sheep=globals().get('reference_fixture')=='sheep'
out=root/('sheep-reference' if sheep else 'matched-reference')
asset_root='/Game/FurReference/Sheep' if sheep else '/Game/FurReference'
prefix='Sheep' if sheep else 'Ratchet'
fur_mid='0' if sheep else '2'
shape={'length':9,'density':3,'offset':0,'transmittance':.2} if sheep else None
inputs=json.loads((out/'inputs.json').read_text())
decoded=json.loads((out/'decoded-textures.json').read_text())
spec=importlib.util.spec_from_file_location('reference_builder',root/'create_reference_material.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
tools=unreal.AssetToolsHelpers.get_asset_tools()
report={'engine':unreal.SystemLibrary.get_engine_version(),'meshes':[],'textures':[],
        'limits':['Bounds and triangle checks do not prove exact imported tangent/UV bytes.',
                  'DDS import decodes BC blocks; GPU texture parity is not yet measured.',
                  'Lit baseline uses Default Lit, not recovered hair lighting.']}
textures={}
for mid,slots in inputs['textures'].items():
    textures[mid]={}
    for role,info in slots.items():
        if role not in ('base_color','albedo','fur_control') and not (sheep and mid==fur_mid and role=='specular_color'): continue
        name=Path(info['file']).stem
        path=asset_root+'/Textures/'+name
        texture=unreal.load_asset(path)
        if not texture:
            task=unreal.AssetImportTask()
            task.filename=str(out/decoded[info['file']]['file'])
            task.destination_path=asset_root+'/Textures'
            task.destination_name=name
            task.automated=True
            task.factory=unreal.TextureFactory()
            tools.import_asset_tasks([task])
            texture=unreal.load_asset(path)
        assert isinstance(texture,unreal.Texture2D),path
        texture.srgb=info['dxgi'] in (29,72,75,78,91,93,99)
        texture.compression_settings=unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP
        texture.mip_gen_settings=unreal.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS
        texture.address_x=unreal.TextureAddress.TA_WRAP
        texture.address_y=unreal.TextureAddress.TA_WRAP
        assert unreal.EditorAssetLibrary.save_loaded_asset(texture)
        textures[mid][role]=texture
        report['textures'].append({'asset':path,'srgb':texture.srgb,'source':info})
materials={}
for mid,slots in textures.items():
    if not any(r in slots for r in ('base_color','albedo')): continue
    materials[mid]={mode:builder.create('M_'+prefix+mid+'_'+mode,slots,fur=mid==fur_mid,unlit=mode=='Unlit',settings=shape) for mode in ('Unlit','Lit')}
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level=asset_root+'/MatchedSheep' if sheep else asset_root+'/MatchedRatchet'
if unreal.EditorAssetLibrary.does_asset_exist(level):
    unreal.EditorLoadingAndSavingUtils.load_map(level)
    for actor in actors.get_all_level_actors():
        if actor.get_actor_label().startswith('SheepPart' if sheep else 'RatchetHeadPart'):
            actors.destroy_actor(actor)
else:
    assert unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).new_level(level)
static=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
for part in inputs['parts']:
    # Material 5 is the authored fur compositing envelope, not a shaded
    # surface. Forge also omits it from its ordinary surface pass.
    if not sheep and part['material']==5:
        report['meshes'].append({'part':part['name'],'role':'fur compositing envelope','rendered':False})
        continue
    name=part['name']
    path=asset_root+'/Meshes/'+name
    mesh=unreal.load_asset(path)
    if not mesh:
        options=unreal.FbxImportUI()
        options.import_mesh=True
        options.import_as_skeletal=False
        options.import_materials=False
        options.import_textures=False
        options.automated_import_should_detect_type=False
        options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
        data=options.static_mesh_import_data
        data.convert_scene=False
        data.convert_scene_unit=False
        data.import_uniform_scale=1
        data.combine_meshes=True
        data.auto_generate_collision=False
        data.generate_lightmap_u_vs=False
        data.remove_degenerates=False
        data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS
        task=unreal.AssetImportTask()
        task.filename=str(out/(name+'-ascii.fbx'))
        task.destination_path=asset_root+'/Meshes'
        task.destination_name=name
        task.automated=True
        task.factory=unreal.FbxFactory()
        task.options=options
        tools.import_asset_tasks([task])
        mesh=unreal.load_asset(path)
    assert isinstance(mesh,unreal.StaticMesh),path
    settings=static.get_lod_build_settings(mesh,0)
    settings.recompute_normals=False
    settings.recompute_tangents=False
    settings.use_full_precision_u_vs=True
    settings.use_high_precision_tangent_basis=True
    settings.remove_degenerates=False
    settings.generate_lightmap_u_vs=False
    static.set_lod_build_settings(mesh,0,settings)
    assert unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    bounds=mesh.get_bounding_box()
    error=max(abs(getattr(v,k)-expected[i]) for v,expected in [(bounds.min,part['bounds_min_cm']),(bounds.max,part['bounds_max_cm'])] for i,k in enumerate(('x','y','z')))
    triangles=mesh.get_num_triangles(0)
    assert error<.01,(name,error,bounds)
    assert triangles==part['triangles'],(name,triangles,part['triangles'])
    mid=str(part['material'])
    material=materials[mid]['Lit']
    if mid==fur_mid:
        actor=actors.spawn_actor_from_class(unreal.FurAuthoringActor,unreal.Vector())
        actor.set_editor_property('source_mesh',mesh)
        actor.set_editor_property('fur_material',material)
        actor.set_editor_property('length',9 if sheep else 3)
        if sheep:
            actor.set_editor_property('use_map_controls',True)
            actor.set_editor_property('recovered_density',3)
            actor.set_editor_property('groom_strength',0)
        actor.set_editor_property('shell_count',32)
        actor.set_weather(0,0)
        actor.rebuild_fur()
    else:
        actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector())
        actor.static_mesh_component.set_static_mesh(mesh)
        for slot in range(mesh.get_num_sections(0)):
            actor.static_mesh_component.set_material(slot,material)
    actor.set_actor_label(name+'_M'+mid)
    report['meshes'].append({'asset':path,'triangles':triangles,'bounds_max_error_cm':error})
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert unreal.EditorLoadingAndSavingUtils.save_map(world,level)
(out/'import-validation.json').write_text(json.dumps(report,indent=2))
unreal.log('MATCHED_REFERENCE_IMPORT_OK')
unreal.SystemLibrary.execute_console_command(world,'QUIT_EDITOR')
