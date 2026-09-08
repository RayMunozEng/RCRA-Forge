"""Exercise actual generated scene-fur light parameters without a GPU launch."""
import importlib.util,json,math
from pathlib import Path
import unreal
root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('scene_builder',root.parent/'plugins/FurAuthoring/Content/Python/create_scene_fur.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
textures={r:unreal.load_asset('/Game/FurReference/Textures/M2_'+r) for r in ('base_color','fur_control','specular_color')}
assert all(textures.values())
material=builder.create('M_DryMultilight_API_v1',textures,fur=True,recovered=True,temporal=True,scene=True,asset_path='/Game/FurValidation/Materials')
assert material
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
fur=actors.spawn_actor_from_class(unreal.FurAuthoringActor,unreal.Vector())
fur.source_mesh=unreal.load_asset('/Engine/BasicShapes/Sphere')
fur.fur_material=material;fur.shell_count=4;fur.set_weather(0,0);fur.rebuild_fur()
controller=actors.spawn_actor_from_class(unreal.FurLightingController,unreal.Vector())
controller.enable_shadows=False;controller.targets=[fur]
def light(intensity):
    a=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector())
    a.light_component.set_intensity(intensity*math.pi)
    return a
key,fill,rim=light(1),light(2),light(3)
controller.key_light=key
def values():
    controller.refresh_lighting()
    m=fur.shells.get_material(0)
    return [m.get_vector_parameter_value('Scene'+label+'Radiance').r for label in ('Key','Fill','Rim')]
def check(expected):
    actual=values();assert all(abs(a-b)<1e-5 for a,b in zip(actual,expected)),(actual,expected)
    return actual
rows=[check([1,0,0])]
controller.fill_light=fill;controller.rim_light=rim;rows.append(check([1,2,3]))
controller.rim_light=fill;rows.append(check([1,2,0]))
controller.fill_light=key;controller.rim_light=rim;rows.append(check([1,0,3]))
controller.fill_light=fill;fill.light_component.set_visibility(False);rows.append(check([1,0,3]))
fill.light_component.set_visibility(True);fill.light_component.set_intensity(4*math.pi)
fur.rebuild_fur();rows.append(check([1,4,3]))
controller.fill_light=None;controller.rim_light=None;rows.append(check([1,0,0]))
assert controller.get_shadow_capture_count()==0
assert fur.shells.get_material(0).get_scalar_parameter_value('Wetness')==0
report={'checks':['absent lights zero','additive slots','duplicate fill ignored as rim','key duplicate ignored','visibility edit','intensity and rebuild rebind','disconnect clears stale contribution','no extra shadow captures'], 'radiance_rows':rows,'material':material.get_path_name(),'limits':'Binding/API only, NullRHI; not a rendered or native parity test.'}
(root/'recovered/dry-multilight-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
unreal.log('DRY_MULTILIGHT_API_OK '+json.dumps(report))
