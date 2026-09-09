"""Create fur materials from user-owned color, packed control and response textures."""
import unreal


def create(name, textures, fur=False, unlit=False, recovered=False, temporal=False, scene=False, settings=None, asset_path='/Game/FurAuthoring/Materials', skeletal=False, environment=None, environment_brdf=None, surface_outputs=False):
    if (environment is None) != (environment_brdf is None):
        raise ValueError('Supply both an environment TextureCube and a linear BRDF Texture2D, or neither.')
    if environment is not None:
        if not isinstance(environment,unreal.TextureCube) or not isinstance(environment_brdf,unreal.Texture2D):
            raise TypeError('Environment requires TextureCube and BRDF Texture2D assets.')
        if environment.srgb or environment_brdf.srgb:
            raise ValueError('Environment and BRDF textures must use linear color.')
        if not (fur and recovered):
            raise ValueError('Environment inputs require recovered fur lighting.')
    if surface_outputs and not (fur and recovered):
        raise ValueError('Surface outputs require recovered fur.')
    settings=settings or {'length':3,'density':16,'offset':1,'transmittance':.1}
    path = asset_path
    existing = unreal.load_asset(path+'/'+name)
    if existing:
        compile_errors=unreal.MaterialEditingLibrary.recompile_material(existing)
        if compile_errors:
            raise RuntimeError('Final material compile failed: '+'; '.join(compile_errors))
        return existing
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,path,unreal.Material,unreal.MaterialFactoryNew())
    if surface_outputs:
        mat.set_editor_property('enable_new_hlsl_generator',False)
    # Captured retail fur raster state is CCW with back-face culling. Rendering
    # recovered shells two-sided exposes inward-facing expanded triangles and
    # feeds their flipped normals into the Hair lighting path.
    mat.set_editor_property('two_sided',not (fur and recovered))
    mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_MASKED)
    mat.set_editor_property('used_with_instanced_static_meshes',fur)
    mat.set_editor_property('used_with_skeletal_mesh',skeletal)
    if unlit or recovered:
        mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
    lib = unreal.MaterialEditingLibrary
    def node(cls):
        return lib.create_material_expression(mat,cls)
    def link(src,dst,pin):
        src,out = src if isinstance(src,tuple) else (src,'')
        assert lib.connect_material_expressions(src,out,dst,pin),pin
    def scalar(name,value):
        n=node(unreal.MaterialExpressionScalarParameter)
        n.set_editor_property('parameter_name',name)
        n.set_editor_property('default_value',value)
        return n
    def vector(name,value):
        n=node(unreal.MaterialExpressionVectorParameter)
        n.set_editor_property('parameter_name',name)
        n.set_editor_property('default_value',unreal.LinearColor(*value))
        return (n,'RGB')
    def custom(code,inputs,kind=unreal.CustomMaterialOutputType.CMOT_FLOAT1):
        n=node(unreal.MaterialExpressionCustom)
        n.set_editor_property('code',code)
        n.set_editor_property('output_type',kind)
        n.set_editor_property('include_file_paths',['/Plugin/FurAuthoring/RecoveredFurAdapter.ush'])
        fields=[]
        for key in inputs:
            field=unreal.CustomInput()
            field.set_editor_property('input_name',key)
            fields.append(field)
        n.set_editor_property('inputs',fields)
        for key,src in inputs.items(): link(src,n,key)
        return n
    def sample(role):
        n=node(unreal.MaterialExpressionTextureSample)
        n.set_editor_property('texture',textures[role])
        n.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if textures[role].srgb else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        return n
    f3=unreal.CustomMaterialOutputType.CMOT_FLOAT3
    color=sample('base_color' if 'base_color' in textures else 'albedo')
    output_color=(color,'RGB')
    opacity=(color,'A')
    if fur:
        uv=node(unreal.MaterialExpressionTextureCoordinate)
        control=sample('fur_control')
        control_object=node(unreal.MaterialExpressionTextureObject)
        control_object.set_editor_property('texture',textures['fur_control'])
        control_object.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        if skeletal:
            # Pose-sharing components already supply i/count, unlike static
            # instances' i/(count-1). Never read instance data on a skinned mesh.
            raw_depth=scalar('ShellDepth',0)
        else:
            raw=node(unreal.MaterialExpressionPerInstanceCustomData)
            raw.set_editor_property('data_index',0)
            raw_depth=custom('return Raw*(Count-1)/max(Count,1);',dict(Raw=raw,Count=scalar('RecoveredShellCount',32)))
        normal=node(unreal.MaterialExpressionVertexNormalWS)
        camera=node(unreal.MaterialExpressionCameraPositionWS)
        position=node(unreal.MaterialExpressionWorldPosition)
        decode_uv=node(unreal.MaterialExpressionTextureCoordinate)
        decode_uv.set_editor_property('coordinate_index',1)
        budget=custom('''
float3 viewDirection=normalize(Camera-Position);
float correction=Decode.x*UseCorrection;
float front=saturate(dot(viewDirection,normalize(N))-correction*0.0065-0.025);
float available=min(2.0*(1.0-front)*(1.0-front)+0.1,1.0);
float unbounded=Raw/max(available,0.000001);
return float2(saturate(unbounded),unbounded<=1.0 ? 1.0 : 0.0);
''',dict(Raw=raw_depth,N=normal,Camera=camera,Position=position,Decode=decode_uv,
         UseCorrection=scalar('UseRetailDecodeCorrection',0)),
            unreal.CustomMaterialOutputType.CMOT_FLOAT2)
        def component_mask(source, red=False, green=False):
            mask=node(unreal.MaterialExpressionComponentMask)
            mask.set_editor_property('r',red)
            mask.set_editor_property('g',green)
            link(source,mask,'')
            return mask
        depth=component_mask(budget,red=True)
        pd=node(unreal.MaterialExpressionVertexInterpolator)
        link(budget,pd,'VS')
        shell_depth=component_mask(pd,red=True)
        shell_visible=component_mask(pd,green=True)
        length=scalar('FurLength',settings['length'])
        tangent=node(unreal.MaterialExpressionVertexTangentWS)
        clock=custom('return lerp(T,Manual,saturate(Override));',
            dict(T=node(unreal.MaterialExpressionTime),Manual=scalar('WindTimeOverride',0),
                 Override=scalar('UseWindTimeOverride',0)))
        wpo=custom('return RFOffset(N,T,1,UV,D,L,RFControlLength(C,UV),W,Clock*Speed,Strength,Turbulence,Phase,Radius);',
            dict(N=normal,T=tangent,L=length,D=depth,C=control_object,UV=uv,
                 W=vector('WindDirection',(1,0,0,0)),Clock=clock,Speed=scalar('WindSpeed',1),
                 Strength=scalar('WindStrength',0),Turbulence=scalar('WindTurbulence',0),
                 Phase=scalar('WindObjectPhase',.1326904),Radius=scalar('WindRadius',1)),f3)
        assert lib.connect_material_property(wpo,'',unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
        layers=node(unreal.MaterialExpressionTextureObject)
        layers.set_editor_property('texture',unreal.load_asset('/FurAuthoring/Textures/T_DefaultFurShells'))
        layers.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
        pn=node(unreal.MaterialExpressionPixelNormalWS)
        view=node(unreal.MaterialExpressionCameraVectorWS)
        wet=scalar('Wetness',0)
        # Integer increments vanish inside hairScreenHash's frac. Match the
        # reference's base-2 Halton fraction plus a separate advancing cycle.
        phase='RFTemporalIndex(View.StateFrameIndex)' if temporal else '0.5'
        # Joint period: 32 Halton samples and five coverage phase steps.
        cycle='float(View.StateFrameIndex % 160u)' if temporal else '0'
        # Native mip bias uses the signed geometric normal after front-face correction.
        # Folding negative smooth-normal facing with abs changes silhouette sampling.
        opacity=custom('if (Visible<0.999) return 0.0; return RFCoverageWithMask(Layers,LayersSampler,UV,C,D,Density,L,Scale,Wet,saturate(dot(normalize(Parameters.TangentToWorld[2])*Parameters.TwoSidedSign,V)),Parameters.SvPosition.xy,View.ViewSizeAndInvSize.zw,'+phase+','+cycle+',Alpha);',
            dict(Layers=layers,UV=uv,C=(control,'RGBA'),D=shell_depth,Visible=shell_visible,Density=scalar('RecoveredDensity',settings['density']),L=length,
                 Scale=scalar('OffsetScale',settings['offset']),Wet=wet,N=pn,V=view,Alpha=(color,'A')))
        output_color=custom('return furWetAlbedo(C,Wet,D).rgb;',dict(C=(color,'RGBA'),Wet=wet,D=shell_depth),f3)
        ao=custom('return saturate(D*0.5)*(1-A)+A;',dict(D=shell_depth,A=(control,'A')))
        assert lib.connect_material_property(ao,'',unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
        if recovered:
            response=sample('specular_color')
            pixel_depth=node(unreal.MaterialExpressionPixelDepth)
            light_inputs={}
            light_code='normalize(float3(.6,1,.8))'
            multiplier='1'
            if scene:
                shadow=node(unreal.MaterialExpressionTextureObjectParameter)
                shadow.set_editor_property('parameter_name','SceneShadowDepth')
                shadow.set_editor_property('texture',unreal.load_asset('/Engine/EngineResources/WhiteSquareTexture'))
                shadow.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
                light_inputs=dict(Key=vector('SceneKeyDirection',(.6,.8,1,0)),
                    Radiance=vector('SceneKeyRadiance',(0,0,0,0)),
                    Shadow=shadow,Position=node(unreal.MaterialExpressionWorldPosition),
                    Origin=vector('SceneShadowOrigin',(0,0,0,0)),
                    Forward=vector('SceneShadowForward',(1,0,0,0)),
                    Right=vector('SceneShadowRight',(0,1,0,0)),Up=vector('SceneShadowUp',(0,0,1,0)),
                    Width=scalar('SceneShadowWidth',300),Bias=scalar('SceneShadowBias',.5),
                    Enabled=scalar('SceneShadowEnabled',0))
                light_code='normalize(Key.xzy)'
                multiplier='Radiance*RFSceneShadow(Shadow,Position,Origin,Forward,Right,Up,Width,Bias,Enabled)'
            additional_code=''
            if scene:
                for label in ('Fill','Rim'):
                    light_inputs[label+'Direction']=vector('Scene'+label+'Direction',(0,0,1,0))
                    light_inputs[label+'Radiance']=vector('Scene'+label+'Radiance',(0,0,0,0))
                    additional_code += (' + RFSceneAdditionalDirect(n,strand,normalize(V.xzy),'
                        +label+'Direction.xzy,'+label+'Radiance,float4(Albedo,AO),response,Depth*.01,Transmission)')
            environment_code=''
            if environment is not None:
                for parameter,texture in [('FurEnvironment',environment),('FurEnvironmentBRDF',environment_brdf)]:
                    obj=node(unreal.MaterialExpressionTextureObjectParameter)
                    obj.set_editor_property('parameter_name',parameter)
                    obj.set_editor_property('texture',texture)
                    obj.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
                    light_inputs[parameter]=obj
                light_inputs.update(EnvironmentIntensity=scalar('EnvironmentIntensity',.6),
                    EnvironmentMaxMip=scalar('EnvironmentMaxMip',5),
                    EnvironmentRecoveredAxes=scalar('EnvironmentRecoveredAxes',0))
                environment_code=''' + RFSceneEnvironment(FurEnvironment,FurEnvironmentSampler,
FurEnvironmentBRDF,FurEnvironmentBRDFSampler,n,strand,normalize(V.xzy),float4(Albedo,AO),response,
Depth*.01,Transmission,hairLightingNoise(Parameters.SvPosition.xy,View.ViewSizeAndInvSize.zw,'''+phase+','+cycle+''').y,
EnvironmentIntensity,EnvironmentMaxMip,EnvironmentRecoveredAxes)'''
            output_color=custom('''
float3 n0=normalize(Parameters.TangentToWorld[2].xzy);
float3 n=n0*Parameters.TwoSidedSign;
float3 t=normalize(Parameters.TangentToWorld[0].xzy);
float3 b=normalize(Parameters.TangentToWorld[1].xzy);
float handedness=dot(cross(n0,t),b)<0 ? -1 : 1;
float3 strand=furStrandDirection(n,float4(t,handedness),furGroom(C.rg,Scale),false);
float2 response=furGlossSpecular(S.rg,1,1,Wet,D);
return RFSceneDirect(n,strand,normalize(V.xzy),'''+light_code+''',float4(Albedo,AO),response,Depth*.01,Transmission)*'''+multiplier+additional_code+environment_code+';',
dict(C=(control,'RGBA'),S=(response,'RGBA'),Wet=wet,D=shell_depth,V=view,Albedo=output_color,AO=ao,Depth=pixel_depth,
     Scale=scalar('OffsetScale',settings['offset']),Transmission=scalar('Transmittance',settings['transmittance']),**light_inputs),f3)
            output_color.set_editor_property('include_file_paths',[
                '/Plugin/FurAuthoring/RecoveredFurAdapter.ush','/Plugin/FurAuthoring/ReferenceHairLighting.ush',
                '/Plugin/FurAuthoring/FurSceneShadow.ush'])
            if surface_outputs:
                # Same authored frame and quantization as the recovered lighting.
                # Emitted into named outputs for the dedicated fur surface pass.
                surface=node(unreal.MaterialExpressionFurSurfaceOutput)
                frame='''
float3 n0=normalize(Parameters.TangentToWorld[2].xzy);
float3 n=n0*Parameters.TwoSidedSign;
float3 t=normalize(Parameters.TangentToWorld[0].xzy);
float3 b=normalize(Parameters.TangentToWorld[1].xzy);
float handedness=dot(cross(n0,t),b)<0 ? -1 : 1;
float3 strand=furStrandDirection(n,float4(t,handedness),furGroom(C.rg,Scale),false);
'''
                for pin,expression in [('Normal','furUnpackNormal(furPackGBuffer(n,0,0,0u))'),
                                       ('Strand','furUnpackStrand(furPackExtra(strand,Transmission))')]:
                    value=custom(frame+'return '+expression+';',dict(C=(control,'RGBA'),
                        Scale=scalar('OffsetScale',settings['offset']),
                        Transmission=scalar('Transmittance',settings['transmittance'])),f3)
                    value.set_editor_property('include_file_paths',[
                        '/Plugin/FurAuthoring/RecoveredFurAdapter.ush',
                        '/Plugin/FurAuthoring/ReferenceHairLighting.ush'])
                    link(value,surface,pin)
    # This baseline intentionally retains Default Lit roughness. Native two-lobe
    # hair response must not be represented as an undocumented roughness tweak.
    roughness=scalar('ReferenceRoughness',.65)
    assert lib.connect_material_property(roughness,'',unreal.MaterialProperty.MP_ROUGHNESS)
    for src,prop in [(output_color,unreal.MaterialProperty.MP_EMISSIVE_COLOR if unlit or recovered else unreal.MaterialProperty.MP_BASE_COLOR),
                     (opacity,unreal.MaterialProperty.MP_OPACITY_MASK)]:
        src,out=src if isinstance(src,tuple) else (src,'')
        assert lib.connect_material_property(src,out,prop)
    lib.layout_material_expressions(mat)
    compile_errors=lib.recompile_material(mat)
    if compile_errors:
        raise RuntimeError('Final material compile failed: '+'; '.join(compile_errors))
    assert unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def create_scene_fur(name, albedo, control, specular_response, settings=None, skeletal=False, environment=None, environment_brdf=None):
    """Create recovered fur lighting; pair with FurLightingController.

    Packed control is linear RG comb, B length, A occlusion. Response RG is
    gloss/specular in the texture's declared color space. Shapes use centimeters.
    Optional environment TextureCube and BRDF Texture2D must both be linear.
    Supply a prefiltered mip chain and clamp-addressed BRDF lookup.
    Existing assets are preserved. Create a new material name to add fill/rim
    inputs to materials built by older plugin versions. TAA must be enabled.
    """
    return create(name, {'base_color':albedo, 'fur_control':control,
                        'specular_color':specular_response}, fur=True,
                  recovered=True, temporal=True, scene=True, settings=settings,skeletal=skeletal,
                  environment=environment,environment_brdf=environment_brdf)
