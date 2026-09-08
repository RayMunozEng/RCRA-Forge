"""Build and capture the recovered unit-key hair diagnostic."""
import importlib.util
import json
from pathlib import Path
import unreal
root=Path(__file__).resolve().parent
out=root/'matched-reference'
info=json.loads((out/'decoded-textures.json').read_text())['M2_specular_color.dds']
path='/Game/FurReference/Textures/M2_specular_color'
texture=unreal.load_asset(path)
if not texture:
    task=unreal.AssetImportTask()
    task.filename=str(out/info['file'])
    task.destination_path='/Game/FurReference/Textures'
    task.destination_name='M2_specular_color'
    task.automated=True
    task.factory=unreal.TextureFactory()
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    texture=unreal.load_asset(path)
    assert isinstance(texture,unreal.Texture2D)
    texture.srgb=True # Authored BC7_UNORM_SRGB, same as the Forge binding.
    texture.compression_settings=unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP
    texture.mip_gen_settings=unreal.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS
    assert unreal.EditorAssetLibrary.save_loaded_asset(texture)
spec=importlib.util.spec_from_file_location('reference_builder',root/'create_reference_material.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
textures={role:unreal.load_asset('/Game/FurReference/Textures/M2_'+role) for role in ('base_color','fur_control','specular_color')}
assert all(textures.values())
builder.create('M_Ratchet2_Recovered',textures,fur=True,recovered=True)
reference_modes=['Recovered']
exec(compile((root/'capture_reference_fur.py').read_text(),str(root/'capture_reference_fur.py'),'exec'),globals())
