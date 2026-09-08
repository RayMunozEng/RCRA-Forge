"""Create an experimental fixed-depth material using the recovered fur kernels.

Preserves existing assets. Requires T_DefaultFurShells imported by the validation
script. Default Lit and fixed-depth shells are host adapters, not native parity.
"""
import unreal


def create_material(with_maps=False, skeletal=False):
    path = '/FurAuthoring/Materials'
    name = 'M_FurSkeletal' if skeletal else ('M_FurAuthoringMaps' if with_maps else 'M_FurRecovered')
    existing = unreal.load_asset(path + '/' + name)
    if existing:
        return existing
    layers = unreal.load_asset('/FurAuthoring/Textures/T_DefaultFurShells')
    assert isinstance(layers, unreal.Texture2DArray), 'Import recovered DDS first'
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, path, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
    mat.set_editor_property('two_sided', True)
    mat.set_editor_property('used_with_instanced_static_meshes', not skeletal)
    mat.set_editor_property('used_with_skeletal_mesh', skeletal)
    lib = unreal.MaterialEditingLibrary

    def node(cls):
        return lib.create_material_expression(mat, cls)

    def link(src, dst, pin):
        output = ''
        if isinstance(src, tuple):
            src, output = src
        assert lib.connect_material_expressions(src, output, dst, pin), pin

    def scalar(name, value):
        n = node(unreal.MaterialExpressionScalarParameter)
        n.set_editor_property('parameter_name', name)
        n.set_editor_property('default_value', value)
        return n

    def vector(name, value):
        n = node(unreal.MaterialExpressionVectorParameter)
        n.set_editor_property('parameter_name', name)
        n.set_editor_property('default_value', unreal.LinearColor(*value))
        return n

    def custom(code, inputs, kind):
        n = node(unreal.MaterialExpressionCustom)
        n.set_editor_property('code', code)
        n.set_editor_property('output_type', kind)
        n.set_editor_property('include_file_paths', ['/Plugin/FurAuthoring/RecoveredFurAdapter.ush'])
        fields = []
        for name in inputs:
            field = unreal.CustomInput()
            field.set_editor_property('input_name', name)
            fields.append(field)
        n.set_editor_property('inputs', fields)
        for name, source in inputs.items():
            link(source, n, name)
        return n

    f1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
    f3 = unreal.CustomMaterialOutputType.CMOT_FLOAT3
    uv = node(unreal.MaterialExpressionTextureCoordinate)
    if skeletal:
        # A separate DMI per skeletal layer supplies native i/count depth.
        depth = scalar('ShellDepth',0)
    else:
        raw = node(unreal.MaterialExpressionPerInstanceCustomData)
        raw.set_editor_property('data_index', 0)
        depth = custom('return Raw * (Count-1.0)/max(Count,1.0);',
                       dict(Raw=raw, Count=scalar('RecoveredShellCount', 32)), f1)
    interpolated = node(unreal.MaterialExpressionVertexInterpolator)
    link(depth, interpolated, 'VS')
    wet = scalar('Wetness', 0)
    length = scalar('FurLength', 3)
    density = scalar('RecoveredDensity', 12)
    scale = scalar('OffsetScale', 1)
    control = vector('Control', (.5,.5,1,1))
    vertex_length = custom('return C.b;',dict(C=(control,'RGBA')),f1)
    pixel_control = (control,'RGBA')
    mask = scalar('Coverage',1)
    if with_maps:
        white = unreal.load_asset('/FurAuthoring/Textures/Authoring/T_White')
        assert isinstance(white,unreal.Texture2D)
        def map_object(name):
            n = node(unreal.MaterialExpressionTextureObjectParameter)
            n.set_editor_property('parameter_name',name)
            n.set_editor_property('texture',white)
            n.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
            return n
        length_map = map_object('LengthMap')
        density_map = map_object('DensityMap')
        groom_map = map_object('GroomMap')
        use_length = scalar('UseLengthMap',0)
        use_density = scalar('UseDensityMap',0)
        use_groom = scalar('UseGroomMap',0)
        vertex_length = custom('return RFLengthMap(Map,UV,Enabled);',
            dict(Map=length_map,UV=uv,Enabled=use_length),f1)
        pixel_control = custom('float2 rg = UseGroom > 0.5 ? saturate(Groom.Sample(GroomSampler,UV).rg) : float2(0.5,0.5); return float4(rg,RFLengthMap(Length,UV,UseLength),1);',
            dict(Groom=groom_map,Length=length_map,UV=uv,UseGroom=use_groom,UseLength=use_length),
            unreal.CustomMaterialOutputType.CMOT_FLOAT4)
        mask = custom('return Enabled > 0.5 ? saturate(Map.Sample(MapSampler,UV).r) : 1.0;',
            dict(Map=density_map,UV=uv,Enabled=use_density),f1)
    normal = node(unreal.MaterialExpressionVertexNormalWS)
    tangent = node(unreal.MaterialExpressionVertexTangentWS)

    def transform(source, source_space, dest_space):
        n = node(unreal.MaterialExpressionTransform)
        n.set_editor_property('transform_source_type', source_space)
        n.set_editor_property('transform_type', dest_space)
        link(source, n, '')
        return n

    local_n = transform(normal, unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                        unreal.MaterialVectorCoordTransform.TRANSFORM_LOCAL)
    local_t = transform(tangent, unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                        unreal.MaterialVectorCoordTransform.TRANSFORM_LOCAL)
    local_w = transform((vector('WindDirection',(1,0,0,0)),'RGB'),
                        unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                        unreal.MaterialVectorCoordTransform.TRANSFORM_LOCAL)
    time = node(unreal.MaterialExpressionTime)
    offset = custom('return RFOffset(N,T,1,UV,D,L,ControlLength,W,Time*Speed,Strength,Turbulence,Phase,Radius);',
        dict(N=local_n,T=local_t,UV=uv,D=depth,L=length,ControlLength=vertex_length,W=local_w,
             Time=time,Speed=scalar('WindSpeed',1),Strength=scalar('WindStrength',.0309733),
             Turbulence=scalar('WindTurbulence',0),Phase=scalar('WindObjectPhase',.1326904),
             Radius=scalar('WindRadius',1)), f3)
    world_offset = transform(offset, unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL,
                             unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    texture = node(unreal.MaterialExpressionTextureObjectParameter)
    texture.set_editor_property('parameter_name','ShellLayers')
    texture.set_editor_property('texture',layers)
    texture.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    view = node(unreal.MaterialExpressionCameraVectorWS)
    pixel_normal = node(unreal.MaterialExpressionPixelNormalWS)
    # SV_Position supplies top-left pixel centers. Explicit temporal constants
    # keep this diagnostic stable; native temporal driving is not integrated.
    # Native mip bias uses the signed geometric normal after front-face correction.
    # Folding negative smooth-normal facing with abs changes silhouette sampling.
    coverage = custom('return RFCoverageWithMask(Layers,LayersSampler,UV,C,D,Density,L,Scale,Wet,saturate(dot(normalize(Parameters.TangentToWorld[2])*Parameters.TwoSidedSign,V)),Parameters.SvPosition.xy,View.ViewSizeAndInvSize.zw,0.5,0,Mask);',
        dict(Layers=texture,UV=uv,C=pixel_control,D=interpolated,Density=density,
             L=length,Scale=scale,Wet=wet,N=pixel_normal,V=view,Mask=mask), f1)
    color = custom('return furWetAlbedo(float4(lerp(Root,Tip,D),1),saturate(Wet),D).rgb;',
        dict(Root=(vector('RootColor',(.12,.06,.025,1)),'RGB'),
             Tip=(vector('TipColor',(.6,.32,.12,1)),'RGB'),D=interpolated,Wet=wet), f3)
    for n, prop in [(world_offset,unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET),
                    (coverage,unreal.MaterialProperty.MP_OPACITY_MASK),
                    (color,unreal.MaterialProperty.MP_BASE_COLOR),
                    (scalar('Roughness',.65),unreal.MaterialProperty.MP_ROUGHNESS)]:
        assert lib.connect_material_property(n,'',prop)
    lib.layout_material_expressions(mat)
    lib.recompile_material(mat)
    assert unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


if __name__ == '__main__':
    create_material()
