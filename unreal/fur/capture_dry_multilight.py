"""Dry key/fill/rim rendered regression; unchanged recovered material response."""
from pathlib import Path
fixture=globals().get('fixture','ratchet')
dynamics_fixture=fixture;dynamics_material=globals().get('dry_material','M_DryMultilight_'+fixture+'_v1')
p=Path(__file__).with_name('capture_reference_dynamics.py')
exec(compile(p.read_text(encoding='utf-8').split('labels=',1)[0],str(p),'exec'),globals())
out=root/'recovered'/globals().get('dry_output','dry-multilight-'+fixture);out.mkdir(exist_ok=True)
controller.enable_shadows=False
fill=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(),unreal.MathLibrary.find_look_at_rotation(unreal.Vector(-1,1,.4),unreal.Vector()))
rim=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(),unreal.MathLibrary.find_look_at_rotation(unreal.Vector(-.8,-1,.5),unreal.Vector()))
fill.light_component.set_light_color(unreal.LinearColor(.25,.55,1,1))
rim.light_component.set_light_color(unreal.LinearColor(1,.3,.06,1))
fill.light_component.set_intensity(2*3.14159265);rim.light_component.set_intensity(3*3.14159265)
controller.key_light.light_component.set_editor_property('forward_shading_priority',10)
fill.light_component.set_editor_property('forward_shading_priority',0)
rim.light_component.set_editor_property('forward_shading_priority',0)
labels=['key','key-fill','key-fill-rim','held','rebuilt','disconnected']
started=time.monotonic();state=dict(stage=0,last=started,draw=started,busy=False,done=False,rows=[])
unreal.FurViewportProbe.enable_world_ticks(True)
def stop():
    state['done']=True;unreal.FurViewportProbe.enable_world_ticks(False)
    unreal.unregister_slate_post_tick_callback(state['handle'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False);command('QUIT_EDITOR')
def tick(delta):
    if state['done'] or state['busy']:return
    try:
        now=time.monotonic()
        if now-started>180:raise RuntimeError('Dry light capture deadline')
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
        finally:pass # Keep reentrant Slate callbacks blocked during shader statistics.
        m=fur.shells.get_material(0)
        assert m.get_scalar_parameter_value('Wetness')==0 and m.get_scalar_parameter_value('WindStrength')==0
        row.update(label=labels[stage],wetness=0,wind=0,material=material.get_path_name(),
            parameters={n:m.get_scalar_parameter_value(n) for n in ['RecoveredShellCount','FurLength','RecoveredDensity','OffsetScale','Wetness','WindStrength']},
            lights={n:[getattr(m.get_vector_parameter_value('Scene'+n+'Radiance'),c) for c in ['r','g','b']] for n in ['Key','Fill','Rim']})
        if globals().get('fur_surface_outputs',False):
            lib=unreal.MaterialEditingLibrary
            outputs=[x for x in lib.get_material_expressions(material) if isinstance(x,unreal.MaterialExpressionFurSurfaceOutput)]
            assert len(outputs)==1
            inputs=lib.get_inputs_for_material_expression(material,outputs[0])
            assert len(inputs)==2 and all(inputs)
            assert not material.get_editor_property('enable_new_hlsl_generator')
            stats=lib.get_statistics(material)
            assert stats.num_pixel_shader_instructions>100 and lib.get_num_shader_types(material)>0
            row['surface_outputs']={'connected_inputs':len(inputs),'shader_types':lib.get_num_shader_types(material),'pixel_instructions':stats.num_pixel_shader_instructions,'legacy_generator':True}
        state['rows'].append(row);state.update(stage=stage+1,last=time.monotonic())
        if stage==0:controller.fill_light=fill
        elif stage==1:controller.rim_light=rim
        elif stage==2:pass # Same lighting, no rebuild: measure temporal sampling noise.
        elif stage==3:fur.rebuild_fur()
        elif stage==4:controller.fill_light=None;controller.rim_light=None
        else:
            (out/'report.json').write_text(json.dumps(state['rows'],indent=2),encoding='utf-8');stop()
        controller.refresh_lighting()
        state['busy']=False
    except Exception:
        import traceback
        unreal.log_error(traceback.format_exc());stop()
state['handle']=unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
