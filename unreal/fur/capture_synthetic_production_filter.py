"""Asset-independent rendered A/B for the production pre-TAA fur filter."""
import importlib.util
import json
from pathlib import Path
import time
import unreal

root = Path(__file__).resolve().parent
out = root / 'recovered' / 'fur-denoise-production-synthetic'
out.mkdir(parents=True, exist_ok=True)
assets = unreal.AssetToolsHelpers.get_asset_tools()


def import_texture(name, srgb):
    path = '/Game/FurValidation/Synthetic/' + name
    texture = unreal.load_asset(path)
    if not texture:
        task = unreal.AssetImportTask()
        task.filename = str(root / 'recovered/maps' / (name + '.png'))
        task.destination_path = '/Game/FurValidation/Synthetic'
        task.destination_name = name
        task.automated = True
        task.replace_existing = True
        task.save = False
        task.factory = unreal.TextureFactory()
        assets.import_asset_tasks([task])
        texture = unreal.load_asset(path)
    assert isinstance(texture, unreal.Texture2D), path
    texture.set_editor_property('srgb', srgb)
    texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    texture.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    texture.set_editor_property('filter', unreal.TextureFilter.TF_TRILINEAR)
    assert unreal.EditorAssetLibrary.save_loaded_asset(texture)
    return texture


def import_array():
    path = '/FurAuthoring/Textures/T_DefaultFurShells'
    array = unreal.load_asset(path)
    if not array:
        task = unreal.AssetImportTask()
        task.filename = str(root / 'recovered/DefaultFurShells.dds')
        task.destination_path = '/FurAuthoring/Textures'
        task.destination_name = 'T_DefaultFurShells'
        task.automated = True
        task.replace_existing = True
        task.save = False
        task.factory = unreal.TextureFactory()
        assets.import_asset_tasks([task])
        array = unreal.load_asset(path)
    assert isinstance(array, unreal.Texture2DArray), path
    array.set_editor_property('srgb', False)
    array.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_GRAYSCALE)
    array.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS)
    array.set_editor_property('filter', unreal.TextureFilter.TF_TRILINEAR)
    assert unreal.EditorAssetLibrary.save_loaded_asset(array)
    return array


assert import_array()
textures = {
    'base_color': import_texture('SyntheticAlbedo', True),
    'fur_control': import_texture('SyntheticControl', False),
    'specular_color': import_texture('SyntheticSpecular', False),
}
builder_path = root.parent / 'plugins/FurAuthoring/Content/Python/create_scene_fur.py'
spec = importlib.util.spec_from_file_location('scene_builder', builder_path)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
material = builder.create(
    'M_SyntheticProductionFilter_v1', textures, fur=True, recovered=True,
    temporal=True, scene=True, surface_outputs=True,
    settings={'length': 5, 'density': 20, 'offset': 0.35, 'transmittance': 0.12},
    asset_path='/Game/FurValidation/Synthetic')
assert material

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
map_path = '/Game/FurValidation/SyntheticProductionFilter'
if unreal.EditorAssetLibrary.does_asset_exist(map_path):
    unreal.EditorLoadingAndSavingUtils.load_map(map_path)
    for actor in actors.get_all_level_actors():
        actors.destroy_actor(actor)
else:
    assert level.new_level(map_path)
fur = actors.spawn_actor_from_class(unreal.FurAuthoringActor, unreal.Vector(0, 0, 0))
fur.set_editor_property('source_mesh', unreal.load_asset('/Engine/BasicShapes/Sphere.Sphere'))
fur.set_editor_property('fur_material', material)
fur.set_editor_property('shell_count', 32)
fur.set_editor_property('length', 5.0)
fur.set_editor_property('use_map_controls', True)
fur.set_editor_property('recovered_density', 20.0)
fur.set_editor_property('groom_strength', 0.35)
fur.set_weather(0, 0)
fur.rebuild_fur()
assert fur.shells.get_instance_count() == 32

light = actors.spawn_actor_from_class(
    unreal.DirectionalLight, unreal.Vector(),
    unreal.MathLibrary.find_look_at_rotation(unreal.Vector(0.6, 0.8, 1), unreal.Vector()))
light.light_component.set_intensity(3.14159265)
controller = actors.spawn_actor_from_class(unreal.FurLightingController, unreal.Vector())
controller.key_light = light
controller.targets = [fur]
controller.enable_shadows = False
controller.refresh_lighting()

eye = unreal.Vector(230, 230, 120)
camera = actors.spawn_actor_from_class(
    unreal.CameraActor, eye,
    unreal.MathLibrary.find_look_at_rotation(eye, unreal.Vector(0, 0, 0)))
camera.camera_component.set_field_of_view(48)
camera.camera_component.set_editor_property('constrain_aspect_ratio', False)
level.pilot_level_actor(camera)
level.editor_set_game_view(True)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def command(value):
    unreal.SystemLibrary.execute_console_command(world, value)


for value in [
    't.MaxFPS 10', 'r.EyeAdaptationQuality 0', 'ShowFlag.EyeAdaptation 0',
    'ShowFlag.Tonemapper 0', 'r.BloomQuality 0', 'r.MotionBlurQuality 0',
    'r.ScreenPercentage 100', 'r.TemporalAASamples 8',
    'r.TemporalAACurrentFrameWeight 0.05', 'ShowFlag.PostProcessing 1',
    'ShowFlag.AntiAliasing 1', 'ShowFlag.TemporalAA 1', 'r.AntiAliasingMethod 2']:
    command(value)

assert unreal.FurDenoiseLibrary.is_recovered_fur_denoise_registered()
assert unreal.FurDenoiseLibrary.set_recovered_fur_denoise_enabled(False)
assert not unreal.FurDenoiseLibrary.is_recovered_fur_denoise_enabled()
outcomes = []
labels = ['off-a', 'off-b', 'on-a', 'on-b']
started = time.monotonic()
state = {'stage': 0, 'last': started, 'draw': started, 'busy': False, 'done': False}
unreal.FurViewportProbe.enable_world_ticks(True)


def stop():
    state['done'] = True
    unreal.FurDenoiseLibrary.set_recovered_fur_denoise_enabled(False)
    unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    command('QUIT_EDITOR')


def tick(_delta):
    if state['done'] or state['busy']:
        return
    try:
        now = time.monotonic()
        if now - started > 210:
            raise RuntimeError('Synthetic production filter capture timeout')
        if now - state['draw'] >= 0.1:
            state['busy'] = True
            try:
                assert unreal.FurViewportProbe.advance()
            finally:
                state['busy'] = False
            state['draw'] = now
        stage = state['stage']
        if now - state['last'] < (25 if stage == 0 else 8):
            return
        state['busy'] = True
        assert unreal.FurViewportProbe.advance()
        row = json.loads(unreal.FurViewportProbe.capture(str(out / (labels[stage] + '.png'))))
        row['label'] = labels[stage]
        row['production_filter_enabled'] = unreal.FurDenoiseLibrary.is_recovered_fur_denoise_enabled()
        row['shell_instances'] = fur.shells.get_instance_count()
        outcomes.append(row)
        state['stage'] = stage + 1
        state['last'] = time.monotonic()
        if stage == 1:
            assert unreal.FurDenoiseLibrary.set_recovered_fur_denoise_enabled(True)
            assert unreal.FurDenoiseLibrary.is_recovered_fur_denoise_enabled()
        if state['stage'] == len(labels):
            report = {
                'status': 'complete',
                'fixture': 'repository-owned generated sphere shell fur',
                'material': material.get_path_name(),
                'surface_output_tagged': True,
                'frames': outcomes,
                'limits': [
                    'Synthetic smoke fixture, not a retail character comparison.',
                    'Separate temporal frames; image analysis must treat them as non-frame-locked.'
                ]
            }
            (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            unreal.log('FUR_DENOISE_PRODUCTION_SYNTHETIC_OK ' + json.dumps(report))
            stop()
            return
        state['busy'] = False
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc())
        stop()


state['handle'] = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
