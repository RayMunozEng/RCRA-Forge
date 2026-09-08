"""Run in the isolated FurValidation project with UnrealEditor-Cmd."""
import importlib.util
import json
from pathlib import Path
import unreal

root = Path(__file__).resolve().parent
builder = root.parent/'plugins/FurAuthoring/Content/Python/create_fur_material.py'
spec = importlib.util.spec_from_file_location('fur_material_builder', builder)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
material = module.create_material()
assert material
assert module.create_material() == material
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
mesh = unreal.load_asset('/Engine/BasicShapes/Sphere.Sphere')
actor = subsystem.spawn_actor_from_class(unreal.FurAuthoringActor, unreal.Vector(0,0,80))
assert actor
actor.set_editor_property('source_mesh', mesh)
actor.set_editor_property('fur_material', material)
actor.rebuild_fur()
shells = actor.get_editor_property('shells')
assert shells.get_instance_count() == 24
actor.set_editor_property('shell_count', 100)
actor.rebuild_fur()
assert shells.get_instance_count() == 64
actor.short_fur_preset()
assert shells.get_instance_count() == 24
actor.wool_preset()
assert shells.get_instance_count() == 32
actor.set_weather(2, -1)
assert actor.get_editor_property('wetness') == 1
assert actor.get_editor_property('wind_strength') == 0
actor.set_editor_property('source_mesh', None)
actor.rebuild_fur()
assert shells.get_instance_count() == 0
actor.set_editor_property('source_mesh', mesh)
actor.set_weather(0, .15)
actor.rebuild_fur()
actor.set_actor_label('Wool - edit Fur controls')
second = subsystem.spawn_actor_from_class(unreal.FurAuthoringActor, unreal.Vector(0,150,80))
second.set_editor_property('source_mesh', mesh)
second.set_editor_property('fur_material', material)
second.short_fur_preset()
second.set_actor_label('Short fur - edit Fur controls')
light = subsystem.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0,0,300), unreal.Rotator(-35,-30,0))
light.light_component.set_editor_property('intensity', 4)
floor = subsystem.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0,75,0))
floor.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Plane.Plane'))
floor.set_actor_scale3d(unreal.Vector(8,8,1))
unreal.EditorAssetLibrary.make_directory('/Game/FurAuthoring')
unreal.EditorLoadingAndSavingUtils.save_map(unreal.EditorLevelLibrary.get_editor_world(), '/Game/FurAuthoring/FurDemo')
report = {'engine':unreal.SystemLibrary.get_engine_version(), 'checks':[
    'material creation and repeat preservation','24 default shells','64 shell cap',
    'short fur preset','wool preset','weather clamps','source removal clears shells'],
    'material':material.get_path_name(),'demo_map':'/Game/FurAuthoring/FurDemo',
    'scope':'Editor API and asset workflow; rendering validation recorded separately'}
(root/'editor-validation.json').write_text(json.dumps(report,indent=2))
unreal.log('FUR_VALIDATION_OK '+json.dumps(report))
