"""UE editor API checks and persistent map-authoring example."""
import importlib.util
import json
from pathlib import Path
import unreal

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('builder',root.parent/'plugins/FurAuthoring/Content/Python/create_recovered_material.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
maps = {}
for name in ['LengthBands','DensityBands','GroomDirections','Black','White']:
    path = '/FurAuthoring/Textures/Authoring/T_'+name
    texture = unreal.load_asset(path)
    if not texture:
        task = unreal.AssetImportTask()
        task.filename = str(root/'recovered/maps'/(name+'.png'))
        task.destination_path = '/FurAuthoring/Textures/Authoring'
        task.destination_name = 'T_'+name
        task.automated = True
        task.factory = unreal.TextureFactory()
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        texture = unreal.load_asset(path)
        assert isinstance(texture,unreal.Texture2D)
        texture.set_editor_property('srgb',False)
        texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
        texture.set_editor_property('address_x',unreal.TextureAddress.TA_WRAP)
        texture.set_editor_property('address_y',unreal.TextureAddress.TA_WRAP)
        assert unreal.EditorAssetLibrary.save_loaded_asset(texture)
    maps[name] = texture
material = builder.create_material(with_maps=True)
assert builder.create_material(with_maps=True) == material
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
unreal.EditorLoadingAndSavingUtils.load_map('/FurAuthoring/Demo/FurRecovered')
fur = [a for a in actors.get_all_level_actors() if isinstance(a,unreal.FurAuthoringActor)]
assert len(fur)==2
actor = fur[0]
actor.use_mapped_fur()
assert actor.get_editor_property('use_map_controls')
actor.set_editor_property('shell_count',16)
actor.rebuild_fur()
dmi = actor.get_editor_property('shells').get_material(0)
assert dmi.get_scalar_parameter_value('RecoveredShellCount') == 16
assert actor.get_editor_property('shells').get_instance_count() == 16
actor.set_fur_maps(maps['LengthBands'],maps['DensityBands'],maps['GroomDirections'])
for role in ['Length','Density','Groom']:
    assert dmi.get_scalar_parameter_value('Use'+role+'Map')==1
assert dmi.get_texture_parameter_value('LengthMap')==maps['LengthBands']
actor.set_fur_maps(None,None,None)
for role in ['Length','Density','Groom']:
    assert dmi.get_scalar_parameter_value('Use'+role+'Map')==0
    assert dmi.get_texture_parameter_value(role+'Map')==unreal.load_asset('/Engine/EngineResources/WhiteSquareTexture')
for actor in fur:
    actor.use_mapped_fur()
    wool = 'Wool' in actor.get_actor_label()
    actor.set_editor_property('recovered_density',3 if wool else 12)
    actor.set_editor_property('groom_strength',1)
    actor.set_editor_property('shell_count',32)
    actor.set_editor_property('length',6)
    actor.rebuild_fur()
    actor.set_fur_maps(maps['LengthBands'] if not wool else None,
                       maps['DensityBands'] if wool else None,None)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert unreal.EditorLoadingAndSavingUtils.save_map(world,'/FurAuthoring/Demo/FurMaps')
report = {'engine':unreal.SystemLibrary.get_engine_version(),
          'checks':['material creation/preservation','switch to mapped material',
                    'shell count synchronization','all three map bindings',
                    'map removal resets flags and texture bindings','persistent diagnostic map'],
          'demo':'/FurAuthoring/Demo/FurMaps',
          'scope':'API and persistence checks; shader rendering checked separately'}
(root/'recovered/maps-validation.json').write_text(json.dumps(report,indent=2))
unreal.log('FUR_MAPS_API_OK '+json.dumps(report))
