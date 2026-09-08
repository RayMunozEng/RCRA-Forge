"""Pose-sharing shell lifecycle and public-API validation in UE5.8."""
import importlib.util
import json
from pathlib import Path
import unreal

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('builder',root.parent/'plugins/FurAuthoring/Content/Python/create_recovered_material.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
material = builder.create_material(with_maps=True,skeletal=True)
assert material
assert builder.create_material(with_maps=True,skeletal=True)==material
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
unreal.EditorLoadingAndSavingUtils.load_map('/FurAuthoring/Demo/FurDemo')
for actor in actors.get_all_level_actors():
    if isinstance(actor,unreal.FurAuthoringActor):
        actors.destroy_actor(actor)
source_actor = actors.spawn_actor_from_class(unreal.SkeletalMeshActor,unreal.Vector(0,75,0))
source_actor.set_actor_label('Animation Source - engine tutorial character')
source = source_actor.skeletal_mesh_component
mesh = unreal.load_asset('/Engine/Tutorial/SubEditors/TutorialAssets/Character/TutorialTPP')
animation = unreal.load_asset('/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Walk_Fwd')
assert isinstance(mesh,unreal.SkeletalMesh)
assert isinstance(animation,unreal.AnimSequence)
source.set_skeletal_mesh_asset(mesh)
fur = actors.spawn_actor_from_class(unreal.SkeletalFurAuthoringActor,unreal.Vector(0,0,0))
fur.use_mapped_fur()
fur.set_pose_source(source)
layers = fur.get_editor_property('skeletal_shells')
assert len(layers)==16
for i,layer in enumerate(layers):
    assert layer.get_editor_property('leader_pose_component')==source
    assert layer.get_attach_parent()==source
    assert layer.get_material(0).get_scalar_parameter_value('ShellDepth')==i/16
fur.set_weather(.7,.05)
for layer in layers:
    assert abs(layer.get_material(0).get_scalar_parameter_value('Wetness')-.7)<1e-6
fur.set_editor_property('shell_count',64)
fur.rebuild_fur()
assert len(fur.get_editor_property('skeletal_shells'))==32
assert fur.get_editor_property('shell_count')==32
for i,layer in enumerate(fur.get_editor_property('skeletal_shells')):
    assert layer.get_material(0).get_scalar_parameter_value('RecoveredShellCount')==32
    assert layer.get_material(0).get_scalar_parameter_value('ShellDepth')==i/32
# A deferred Blueprint count edit must not make material metadata disagree
# with the shells already present when another setter refreshes parameters.
fur.shell_count=8
fur.set_weather(0,0)
assert all(l.get_material(0).get_scalar_parameter_value('RecoveredShellCount')==32 for l in fur.skeletal_shells)
fur.rebuild_fur()
assert len(fur.skeletal_shells)==8
assert all(l.get_material(0).get_scalar_parameter_value('RecoveredShellCount')==8 for l in fur.skeletal_shells)
fur.set_pose_source(None)
assert len(fur.get_editor_property('skeletal_shells'))==0
assert len(fur.get_components_by_class(unreal.SkeletalMeshComponent))==0
fur.set_editor_property('shell_count',16)
fur.set_pose_source(source)
fur.rebuild_fur()
fur.rebuild_fur()
assert len(fur.get_components_by_class(unreal.SkeletalMeshComponent))==16
fur.set_weather(0,0)
fur.set_editor_property('length',2)
fur.set_editor_property('root_color',unreal.LinearColor(.10,.04,.015,1))
fur.set_editor_property('tip_color',unreal.LinearColor(.65,.3,.10,1))
fur.rebuild_fur()
source.set_visibility(False,False)
source.set_editor_property('visibility_based_anim_tick_option',unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
source.set_update_animation_in_editor(True)
source.override_animation_data(animation,True,True,0,1)
assert fur.refresh_preview_pose()
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert unreal.EditorLoadingAndSavingUtils.save_map(world,'/FurAuthoring/Demo/FurSkeletal')
report = {'checks':['skeletal material creation/preservation','16 pose-sharing layers',
          'unique shell depths','weather reaches every layer','32-layer cap and reflected count','material count matches built geometry after deferred edits',
          'source removal cleans components','rebuild does not accumulate components'],
          'engine':unreal.SystemLibrary.get_engine_version(),'demo':'/FurAuthoring/Demo/FurSkeletal',
          'scope':'Lifecycle/API checks, not rendered deformation or native motion-vector parity'}
(root/'recovered/skeletal-validation.json').write_text(json.dumps(report,indent=2))
unreal.log('SKELETAL_FUR_API_OK '+json.dumps(report))
