"""Small, bounded editor screenshot. Run on an inactive desktop."""
import json
import time
from pathlib import Path
import unreal

root = Path(__file__).resolve().parent
unreal.EditorLoadingAndSavingUtils.load_map('/Game/FurAuthoring/FurDemo')
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
target = unreal.Vector(0,75,80)
position = unreal.Vector(320,280,180)
rotation = unreal.MathLibrary.find_look_at_rotation(position, target)
camera = actors.spawn_actor_from_class(unreal.CameraActor, position, rotation)
camera.camera_component.set_field_of_view(55)
camera.camera_component.set_editor_property('constrain_aspect_ratio', False)
for actor in actors.get_all_level_actors():
    if isinstance(actor, unreal.DirectionalLight):
        actor.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(unreal.Vector(250,150,400), target),False)
        actor.light_component.set_editor_property('intensity', 4)
    if isinstance(actor, unreal.StaticMeshActor):
        actor.static_mesh_component.set_material(0,unreal.load_asset('/Engine/BasicShapes/BasicShapeMaterial'))
fill = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(-200,-150,200),
    unreal.MathLibrary.find_look_at_rotation(unreal.Vector(-200,-150,200), target))
fill.light_component.set_editor_property('intensity',1)
unreal.EditorAssetLibrary.make_directory('/FurAuthoring/Demo')
assert unreal.EditorLoadingAndSavingUtils.save_map(world, '/FurAuthoring/Demo/FurDemo')
for command in ['t.MaxFPS 10', 'r.ScreenPercentage 100']:
    unreal.SystemLibrary.execute_console_command(world, command)
started = time.monotonic()
state = {'requested':False}
output = root/'fur-ue58-preview-framed.png'

def stop():
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.execute_console_command(world, 'QUIT_EDITOR')

def tick(delta):
    try:
        elapsed = time.monotonic() - started
        if elapsed > 140:
            unreal.log_error('Fur preview timed out waiting for screenshot')
            stop()
        elif state['requested'] and output.exists():
            (root/'render-validation.json').write_text(json.dumps({
                'screenshot':str(output),'engine':unreal.SystemLibrary.get_engine_version(),
                'requested_size':[640,480],'elapsed_seconds':elapsed,
                'camera_position':[position.x,position.y,position.z],
                'camera_rotation':[rotation.pitch,rotation.yaw,rotation.roll],
                'scope':'Static-mesh material render; not native game parity'},indent=2))
            stop()
        elif not state['requested'] and elapsed > 40:
            accepted = unreal.AutomationLibrary.take_high_res_screenshot(
                640,480,str(output),camera=camera,delay=0.0,force_game_view=True)
            if not accepted:
                raise RuntimeError('Screenshot request rejected')
            state['requested'] = True
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc())
        stop()

state['handle'] = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
