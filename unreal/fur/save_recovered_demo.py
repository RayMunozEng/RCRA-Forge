"""Save the recovered-core demo with persistent material instances.

Do not use TextureExporterDDS for array readback: UE5.8's ImageUtils.cpp
asserts on Texture2DArray despite the exporter reporting support.
"""
import unreal

# Save a separate, inspectable demo. MICs retain recovered density/spacing
# through actor reconstruction, rather than relying on transient DMI edits.
material = unreal.load_asset('/FurAuthoring/Materials/M_FurRecovered')
assert material
instances = {}
for label, density, offset in [('Short',12,1),('Wool',3,0)]:
    path = '/FurAuthoring/Materials/MI_Recovered' + label
    instance = unreal.load_asset(path)
    if not instance:
        instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            'MI_Recovered'+label,'/FurAuthoring/Materials',
            unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
        unreal.MaterialEditingLibrary.set_material_instance_parent(instance,material)
        for name,value in [('RecoveredDensity',density),('OffsetScale',offset),('RecoveredShellCount',32)]:
            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance,name,value)
        assert unreal.EditorAssetLibrary.save_loaded_asset(instance)
    instances[label] = instance
unreal.EditorLoadingAndSavingUtils.load_map('/FurAuthoring/Demo/FurDemo')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for actor in actors.get_all_level_actors():
    if isinstance(actor,unreal.FurAuthoringActor):
        label = 'Wool' if 'Wool' in actor.get_actor_label() else 'Short'
        actor.set_editor_property('fur_material',instances[label])
        actor.set_editor_property('shell_count',32)
        actor.set_editor_property('wind_strength',0)
        actor.set_editor_property('wetness',0)
        actor.rebuild_fur()
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert unreal.EditorLoadingAndSavingUtils.save_map(world,'/FurAuthoring/Demo/FurRecovered')
unreal.log('RECOVERED_DEMO_SAVED /FurAuthoring/Demo/FurRecovered')
