"""Run once in UE 5.8's Python console. Creates /FurAuthoring/Materials/M_FurAuthoring.
Existing material is preserved. Assign it to a Fur Actor and choose Source Mesh.
"""
import unreal

PATH = '/FurAuthoring/Materials'
NAME = 'M_FurAuthoring'

def create_material():
    existing = unreal.load_asset(PATH + '/' + NAME)
    if existing:
        unreal.log('Fur material already exists; preserving it.')
        return existing
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        NAME, PATH, unreal.Material, unreal.MaterialFactoryNew())
    material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
    material.set_editor_property('two_sided', True)
    material.set_editor_property('used_with_instanced_static_meshes', True)
    library = unreal.MaterialEditingLibrary
    def node(cls):
        return library.create_material_expression(material, cls)
    def scalar(name, default):
        n = node(unreal.MaterialExpressionScalarParameter)
        n.set_editor_property('parameter_name', name)
        n.set_editor_property('default_value', default)
        return n
    def vector(name, default):
        n = node(unreal.MaterialExpressionVectorParameter)
        n.set_editor_property('parameter_name', name)
        n.set_editor_property('default_value', unreal.LinearColor(*default))
        return n
    def link(source, dest, pin, output=''):
        if not library.connect_material_expressions(source, output, dest, pin):
            raise RuntimeError('Could not connect material pin ' + pin)
    def custom(code, inputs, kind):
        n = node(unreal.MaterialExpressionCustom)
        n.set_editor_property('code', code)
        n.set_editor_property('output_type', kind)
        n.set_editor_property('include_file_paths', ['/Plugin/FurAuthoring/FurAuthoring.ush'])
        fields = []
        for name in inputs:
            field = unreal.CustomInput()
            field.set_editor_property('input_name', name)
            fields.append(field)
        n.set_editor_property('inputs', fields)
        for name, source in inputs.items():
            if isinstance(source, tuple): link(source[0], n, name, source[1])
            else: link(source, n, name)
        return n
    def output(n, prop):
        if not library.connect_material_property(n, '', prop):
            raise RuntimeError('Could not connect material property ' + str(prop))
    uv = node(unreal.MaterialExpressionTextureCoordinate)
    depth = node(unreal.MaterialExpressionPerInstanceCustomData)
    depth.set_editor_property('data_index', 0)
    interpolated = node(unreal.MaterialExpressionVertexInterpolator)
    link(depth, interpolated, 'VS')
    wet = scalar('Wetness', 0)
    length = scalar('FurLength', 3)
    density = scalar('Density', 100)
    width = scalar('StrandWidth', .2)
    roughness = scalar('Roughness', .65)
    root = vector('RootColor', (.12,.06,.025,1))
    tip = vector('TipColor', (.6,.32,.12,1))
    groom = vector('Groom', (0,0,0,0))
    wind = vector('WindDirection', (1,0,0,0))
    strength = scalar('WindStrength', .15)
    speed = scalar('WindSpeed', 1)
    normal = node(unreal.MaterialExpressionVertexNormalWS)
    time = node(unreal.MaterialExpressionTime)
    offset = custom('return FAOffset(N,UV,D,L,G,W,S,V,T,Wet);',
        dict(N=normal, UV=uv, D=depth, L=length, G=(groom,'RGB'), W=(wind,'RGB'),
             S=strength,V=speed,T=time,Wet=wet), unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    coverage = custom('return FACoverage(UV,D,Density,Width,Wet);',
        dict(UV=uv,D=interpolated,Density=density,Width=width,Wet=wet),
        unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    color = custom('return FAColor(Root,Tip,D,Wet);',
        dict(Root=(root,'RGB'),Tip=(tip,'RGB'),D=interpolated,Wet=wet),
        unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    rough = custom('return lerp(R,0.2,saturate(Wet));',dict(R=roughness,Wet=wet),
                   unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    output(offset, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    output(coverage, unreal.MaterialProperty.MP_OPACITY_MASK)
    output(color, unreal.MaterialProperty.MP_BASE_COLOR)
    output(rough, unreal.MaterialProperty.MP_ROUGHNESS)
    library.layout_material_expressions(material)
    library.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    unreal.log('Created '+PATH+'/'+NAME)
    return material

if __name__ == '__main__':
    create_material()
