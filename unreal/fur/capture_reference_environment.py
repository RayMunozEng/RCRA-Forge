"""Bounded optional-environment response checks using private fixture inputs."""
from pathlib import Path
import unreal
root=Path(__file__).resolve().parent
asset_path='/Game/FurValidation/Environment'
def import_input(name,cube):
    texture=unreal.load_asset(asset_path+'/'+name)
    if not texture:
        task=unreal.AssetImportTask();task.filename=str(root/'recovered/environment-inputs'/(name+'.dds'))
        task.destination_path=asset_path;task.destination_name=name;task.automated=True
        task.factory=unreal.TextureFactory()
        task.factory.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_HDR)
        task.factory.set_editor_property('mip_gen_settings',unreal.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        texture=unreal.load_asset(asset_path+'/'+name)
    assert isinstance(texture,unreal.TextureCube if cube else unreal.Texture2D),name
    texture.srgb=False
    texture.compression_settings=unreal.TextureCompressionSettings.TC_HDR
    texture.mip_gen_settings=unreal.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS
    if not cube:
        texture.address_x=unreal.TextureAddress.TA_CLAMP;texture.address_y=unreal.TextureAddress.TA_CLAMP
    assert unreal.EditorAssetLibrary.save_loaded_asset(texture)
    return texture
test_environment=import_input('StudioCube',True)
test_environment_brdf=import_input('PrivateBRDF',False)
dynamics_fixture=globals().get('environment_fixture','ratchet')
dynamics_material='M_Environment_'+dynamics_fixture+'_v1'
setup=Path(__file__).with_name('capture_reference_dynamics.py').read_text().split('labels=',1)[0]
exec(compile(setup,str(Path(__file__).with_name('capture_reference_dynamics.py')),'exec'),globals())
out=root/'recovered'/('environment-'+fixture);out.mkdir(exist_ok=True)
controller.enable_shadows=False
key=controller.key_light.light_component
key_intensity=key.intensity
controller.shadow_casters=[fur]
def environment(value):
    for mat in materials:mat.set_scalar_parameter_value('EnvironmentIntensity',value)
environment(0)
unreal.FurViewportProbe.enable_world_ticks(True)
labels=['key-only','key-environment','environment-only','environment-double','wet-environment','shadow-environment','shadow-key-only','disabled-return']
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,rows=[])
def stop():
    state['done']=True
    unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    command('QUIT_EDITOR')
def tick(delta):
    if state['done'] or state['busy']:return
    try:
        now=time.monotonic()
        if now-started>180:raise RuntimeError('Environment capture timeout')
        if now-state['draw']>=.1:
            state['busy']=True
            try:assert unreal.FurViewportProbe.advance()
            finally:state['busy']=False
            state['draw']=now
        stage=state['stage']
        if now-state['last']<(20 if stage==0 else 6):return
        state['busy']=True
        try:
            assert unreal.FurViewportProbe.advance()
            row=json.loads(unreal.FurViewportProbe.capture(str(out/(labels[stage]+'.png'))))
        finally:state['busy']=False
        assert row['draw_realtime'] and row['resolved_aa_method']==2
        row.update(label=labels[stage],material=material.get_path_name(),environment_intensity=materials[0].get_scalar_parameter_value('EnvironmentIntensity'),key_intensity=key.intensity,wetness=materials[0].get_scalar_parameter_value('Wetness'),shadow=controller.enable_shadows)
        state['rows'].append(row);state.update(stage=stage+1,last=time.monotonic())
        if stage==0:environment(.6)
        elif stage==1:key.set_intensity(0)
        elif stage==2:environment(1.2)
        elif stage==3:environment(.6);weather(.8,0,0)
        elif stage==4:weather(0,0,0);key.set_intensity(key_intensity);controller.enable_shadows=True
        elif stage==5:environment(0)
        elif stage==6:controller.enable_shadows=False
        else:
            (out/'report.json').write_text(json.dumps(state['rows'],indent=2));stop()
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
