"""Import the exact array with UE's DDS TextureFactory; preserve authored mips."""
import json
from pathlib import Path
import unreal

root = Path(__file__).resolve().parent
task = unreal.AssetImportTask()
task.filename = str(root / 'recovered/DefaultFurShells.dds')
task.destination_path = '/FurAuthoring/Textures'
task.destination_name = 'T_DefaultFurShells'
task.automated = True
task.replace_existing = True
task.save = False
task.factory = unreal.TextureFactory()
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
array = unreal.load_asset('/FurAuthoring/Textures/T_DefaultFurShells')
assert isinstance(array, unreal.Texture2DArray), str(task.imported_object_paths)
array.set_editor_property('srgb', False)
array.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_GRAYSCALE)
array.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS)
array.set_editor_property('filter', unreal.TextureFilter.TF_TRILINEAR)
array.set_editor_property('address_x', unreal.TextureAddress.TA_WRAP)
array.set_editor_property('address_y', unreal.TextureAddress.TA_WRAP)
array.set_editor_property('address_z', unreal.TextureAddress.TA_CLAMP)
assert unreal.EditorAssetLibrary.save_loaded_asset(array)
report = {'asset': array.get_path_name(), 'class': array.get_class().get_name(),
          'srgb': array.get_editor_property('srgb'),
          'mip_policy': str(array.get_editor_property('mip_gen_settings')),
          'scope': 'UE DDS import and settings verified; cooked GPU bytes not read back yet.'}
(root/'recovered/ue-import.json').write_text(json.dumps(report, indent=2))
unreal.log('RECOVERED_FUR_ARRAY_OK ' + json.dumps(report))
import importlib.util
builder = root.parent / 'plugins/FurAuthoring/Content/Python/create_recovered_material.py'
spec = importlib.util.spec_from_file_location('recovered_material', builder)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
material = module.create_material()
assert module.create_material() == material
unreal.log('RECOVERED_FUR_MATERIAL_OK ' + material.get_path_name())
