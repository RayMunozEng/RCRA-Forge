"""Build the discrete, camera-facing strand material used by StrandGroomActor."""

import unreal


PROFILES = {
    "ears": {
        "children": 2.0,
        "reflectance": (0.2140340954065323,) * 3,
        "stray_power": 100.0,
        "stray_strength": 0.0,
        "strand": ((0.0, 0.0), (0.23989396, 0.0010498867),
                   (0.67051762, 0.00059640512), (1.0, 0.0)),
        "clump_x": ((0.0, 0.005), (0.16185364, 0.005),
                    (0.59183431, 0.0029285715), (1.0, 0.001)),
        "clump_y": ((0.0, 0.005), (0.16185364, 0.005),
                    (0.59183431, 0.0027142859), (1.0, 0.0012857143)),
    },
    "head-sparse": {
        "children": 11.0,
        "reflectance": (0.21768173575401306,) * 3,
        "stray_power": 100.0,
        "stray_strength": 0.0,
        "strand": ((0.0, 0.0), (0.30419964, 0.00090624543),
                   (0.67051762, 0.00053067307), (1.0, 0.0)),
        "clump_x": ((0.0, 0.008), (0.16248856, 0.008),
                    (0.60707247, 0.008), (1.0, 0.008)),
        "clump_y": ((0.0, 0.008), (0.16248856, 0.008),
                    (0.60707247, 0.008), (1.0, 0.008)),
    },
    "tail": {
        "children": 35.0,
        "reflectance": (0.18269199132919312,) * 3,
        "stray_power": 4.481430530548096,
        "stray_strength": 3.0,
        "strand": ((0.0, 0.0019955141), (0.30419964, 0.0018866096),
                   (0.67051762, 0.0010605373), (1.0, 0.0)),
        "clump_x": ((0.0, 0.015), (0.16185364, 0.015),
                    (0.53277129, 0.0083571430), (1.0, 0.0006428574)),
        "clump_y": ((0.0, 0.015), (0.16185364, 0.015),
                    (0.53277129, 0.0083571430), (1.0, 0.0008571431)),
    },
}


def copy_scene_lighting(source_material, strand_actor):
    """Copy the controller-resolved lighting state into a strand actor's MID."""
    target = strand_actor.get_editor_property("ribbons").get_material(0)
    if target is None:
        raise RuntimeError("Strand actor has no dynamic material")
    for name in (
            "SceneKeyDirection", "SceneKeyRadiance",
            "SceneFillDirection", "SceneFillRadiance",
            "SceneRimDirection", "SceneRimRadiance",
            "SceneShadowOrigin", "SceneShadowForward",
            "SceneShadowRight", "SceneShadowUp"):
        target.set_vector_parameter_value(
            name, source_material.get_vector_parameter_value(name))
    for name in ("SceneShadowWidth", "SceneShadowBias", "SceneShadowEnabled"):
        target.set_scalar_parameter_value(
            name, source_material.get_scalar_parameter_value(name))
    shadow = source_material.get_texture_parameter_value("SceneShadowDepth")
    if shadow is not None:
        target.set_texture_parameter_value("SceneShadowDepth", shadow)
    for name in ("EnvironmentIntensity", "EnvironmentMaxMip",
                 "EnvironmentRecoveredAxes"):
        target.set_scalar_parameter_value(
            name, source_material.get_scalar_parameter_value(name))
    for name in ("FurEnvironment", "FurEnvironmentBRDF"):
        texture = source_material.get_texture_parameter_value(name)
        if texture is not None:
            target.set_texture_parameter_value(name, texture)
    return target


def _curve_code(variable, points):
    rows = []
    for index in range(3):
        x0, y0 = points[index]
        x1, y1 = points[index + 1]
        keyword = "if" if index == 0 else "else if"
        rows.append(
            f"{keyword} (along <= {x1:.10g}) {{ float q = saturate((along - {x0:.10g}) / "
            f"({x1:.10g} - {x0:.10g})); {variable} = lerp({y0:.10g}, {y1:.10g}, q); }}")
    rows.append(f"else {{ {variable} = {points[-1][1]:.10g}; }}")
    return "\n".join(rows)


def create_material(diffuse_texture, thickness_texture=None, profile="ears",
                    name="M_RatchetStrandAccent",
                    asset_path="/Game/FurValidation/Materials"):
    settings = PROFILES[profile]
    full_path = asset_path + "/" + name
    existing = unreal.load_asset(full_path)
    if existing:
        errors = unreal.MaterialEditingLibrary.recompile_material(existing)
        if errors:
            raise RuntimeError("Final strand material compile failed: " + "; ".join(errors))
        return existing

    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, asset_path, unreal.Material, unreal.MaterialFactoryNew())
    material.set_editor_property("two_sided", True)
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    lib = unreal.MaterialEditingLibrary

    def node(cls):
        return lib.create_material_expression(material, cls)

    def link(source, target, pin):
        source, output = source if isinstance(source, tuple) else (source, "")
        if not lib.connect_material_expressions(source, output, target, pin):
            raise RuntimeError("Could not connect strand material pin " + pin)

    def scalar(name, value):
        value_node = node(unreal.MaterialExpressionScalarParameter)
        value_node.set_editor_property("parameter_name", name)
        value_node.set_editor_property("default_value", value)
        return value_node

    def vector(name, value):
        value_node = node(unreal.MaterialExpressionVectorParameter)
        value_node.set_editor_property("parameter_name", name)
        value_node.set_editor_property("default_value", unreal.LinearColor(*value))
        return (value_node, "RGB")

    def custom(code, inputs, output_type):
        value_node = node(unreal.MaterialExpressionCustom)
        value_node.set_editor_property("code", code)
        value_node.set_editor_property("output_type", output_type)
        custom_inputs = []
        for key in inputs:
            item = unreal.CustomInput()
            item.set_editor_property("input_name", key)
            custom_inputs.append(item)
        value_node.set_editor_property("inputs", custom_inputs)
        for key, source in inputs.items():
            link(source, value_node, key)
        return value_node

    def transform(source, source_space, dest_space):
        value_node = node(unreal.MaterialExpressionTransform)
        value_node.set_editor_property("transform_source_type", source_space)
        value_node.set_editor_property("transform_type", dest_space)
        link(source, value_node, "")
        return value_node

    uv = node(unreal.MaterialExpressionTextureCoordinate)
    position = node(unreal.MaterialExpressionWorldPosition)
    camera = node(unreal.MaterialExpressionCameraPositionWS)
    frame_y = node(unreal.MaterialExpressionVertexTangentWS)
    curve_xy = node(unreal.MaterialExpressionTextureCoordinate)
    curve_xy.set_editor_property("coordinate_index", 1)
    curve_z = node(unreal.MaterialExpressionTextureCoordinate)
    curve_z.set_editor_property("coordinate_index", 2)
    guide_index = node(unreal.MaterialExpressionTextureCoordinate)
    guide_index.set_editor_property("coordinate_index", 3)
    curve_local = custom(
        "return normalize(float3(XY, Z.x));",
        dict(XY=curve_xy, Z=curve_z),
        unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    curve_tangent = transform(
        curve_local,
        unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL,
        unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    vertex_color = node(unreal.MaterialExpressionVertexColor)
    guide_uv = custom(
        "return Color.rg;", dict(Color=vertex_color),
        unreal.CustomMaterialOutputType.CMOT_FLOAT2)
    diffuse = node(unreal.MaterialExpressionTextureSample)
    diffuse.set_editor_property("texture", diffuse_texture)
    diffuse.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    link(guide_uv, diffuse, "UVs")
    combined_diffuse = custom(r"""
float3 authoredGamma = pow(saturate(Reflectance), 0.447761);
float3 textureGamma = pow(saturate(Texture), 0.447761);
float3 multiplyBranch = authoredGamma * (2.0 * textureGamma);
float3 screenBranch = 1.0 - (1.0 - textureGamma)
    * (1.0 - (authoredGamma - 0.5) * 2.0);
float3 gammaCombined = lerp(
    screenBranch, multiplyBranch, step(0.5, textureGamma));
return pow(saturate(gammaCombined), 2.23333);
""", dict(
        Texture=(diffuse, "RGB"),
        Reflectance=vector("DiffuseReflectance", (*settings["reflectance"], 0.0))),
        unreal.CustomMaterialOutputType.CMOT_FLOAT3)

    if thickness_texture:
        thickness = node(unreal.MaterialExpressionTextureSample)
        thickness.set_editor_property("texture", thickness_texture)
        thickness.set_editor_property(
            "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        link(guide_uv, thickness, "UVs")
        thickness_source = (thickness, "RGB")
    else:
        thickness_source = vector("ThicknessMask", (0.5, 0.5, 0.5, 0.0))

    vertex_normal = node(unreal.MaterialExpressionVertexNormalWS)
    # Retail distributes children around each guide with the golden angle and
    # m_ClumpThickness, then extrudes a separate camera-facing ribbon using
    # m_StrandThickness. Both native curve values are meters.
    wpo_code = r"""
float side = fmod(UV.x, 2.0);
float child = floor(UV.x * 0.5);
float along = saturate(UV.y);
float strandThickness;
STRAND_CURVE
float clumpX;
CLUMP_X_CURVE
float clumpY;
CLUMP_Y_CURVE
float angle = child * 2.39996;
float radius = sqrt((child + 1.0) / CHILD_COUNT);
float maskAlong = lerp(Mask.g, Mask.b, along);
float3 strand = normalize(Tangent);
float3 radialX = normalize(FrameX);
float3 radialY = normalize(FrameY);
float clumpScaleX = 2.0 * maskAlong * clumpX;
float clumpScaleY = 2.0 * maskAlong * clumpY;
float radialCos = cos(angle) * radius;
float radialSin = sin(angle) * radius;
float3 clumpOffset = radialX * (radialCos * clumpScaleX * 100.0)
                   + radialY * (radialSin * clumpScaleY * 100.0);
float hashBase = frac((GuideIndex.x + child) * 0.318310 + 0.1);
float strayRandom = frac((hashBase * hashBase * 83521.0) * hashBase * (hashBase * 3.0));
float stray = STRAY_BASE * along * STRAY_STRENGTH
    * pow(strayRandom, STRAY_POWER);
float3 strayDirection = radialX * radialCos + radialY * radialSin;
clumpOffset += strayDirection * (stray * 100.0);
float3 view = normalize(Camera - Position);
float3 facing = normalize(cross(strand, view));
float ribbonWidth = 2.0 * Mask.r * strandThickness * 100.0;
ribbonWidth *= WidthScale * GuideScale;
return clumpOffset + facing * ((side - 0.5) * ribbonWidth);
"""
    wpo_code = (wpo_code
                .replace("STRAND_CURVE", _curve_code("strandThickness", settings["strand"]))
                .replace("CLUMP_X_CURVE", _curve_code("clumpX", settings["clump_x"]))
                .replace("CLUMP_Y_CURVE", _curve_code("clumpY", settings["clump_y"]))
                .replace("CHILD_COUNT", f"{settings['children']:.1f}")
                .replace("STRAY_BASE", f"{max(settings['clump_x'][0][1], settings['clump_y'][0][1]):.10g}")
                .replace("STRAY_STRENGTH", f"{settings['stray_strength']:.10g}")
                .replace("STRAY_POWER", f"{settings['stray_power']:.10g}"))
    wpo = custom(wpo_code, dict(
        UV=uv, Position=position, Camera=camera, Tangent=curve_tangent,
        FrameX=vertex_normal, FrameY=frame_y, Mask=thickness_source,
        GuideIndex=guide_index,
        WidthScale=scalar("StrandWidthScale", 1.0),
        GuideScale=(vertex_color, "A")),
        unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    if not lib.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET):
        raise RuntimeError("Could not connect strand world-position offset")

    normal = node(unreal.MaterialExpressionPixelNormalWS)
    view = node(unreal.MaterialExpressionCameraVectorWS)
    depth = node(unreal.MaterialExpressionPixelDepth)
    shadow = node(unreal.MaterialExpressionTextureObjectParameter)
    shadow.set_editor_property("parameter_name", "SceneShadowDepth")
    shadow.set_editor_property(
        "texture", unreal.load_asset("/Engine/EngineResources/WhiteSquareTexture"))
    shadow.set_editor_property(
        "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    environment = node(unreal.MaterialExpressionTextureObjectParameter)
    environment.set_editor_property("parameter_name", "FurEnvironment")
    environment.set_editor_property(
        "texture", unreal.load_asset("/Engine/EngineResources/DefaultTextureCube"))
    environment.set_editor_property(
        "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    environment_brdf = node(unreal.MaterialExpressionTextureObjectParameter)
    environment_brdf.set_editor_property("parameter_name", "FurEnvironmentBRDF")
    environment_brdf.set_editor_property(
        "texture", unreal.load_asset("/Engine/EngineResources/WhiteSquareTexture"))
    environment_brdf.set_editor_property(
        "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    lighting = custom(r"""
float3 n = normalize(N.xzy) * Parameters.TwoSidedSign;
float3 strand = normalize(Tangent.xzy);
float along = saturate(UV.y);
float4 surface = furWetAlbedo(float4(Albedo, 1.0), Wetness, along);
float2 response = furGlossSpecular(
    float2(0.2, 0.0395462364), 1.0, 1.0, Wetness, along);
float viewDepth = Depth * 0.01;
float3 color = RFSceneDirect(
    n, strand, normalize(View.xzy), normalize(Key.xzy),
    surface, response, viewDepth, 0.1);
color *= max(Radiance, 0.0) * RFSceneShadow(
    Shadow, Position, ShadowOrigin, ShadowForward, ShadowRight, ShadowUp,
    ShadowWidth, ShadowBias, ShadowEnabled);
color += RFSceneAdditionalDirect(
    n, strand, normalize(View.xzy), Fill.xzy, max(FillRadiance, 0.0),
    surface, response, viewDepth, 0.1);
color += RFSceneAdditionalDirect(
    n, strand, normalize(View.xzy), Rim.xzy, max(RimRadiance, 0.0),
    surface, response, viewDepth, 0.1);
color += RFSceneEnvironment(
    Environment, EnvironmentSampler, EnvironmentBRDF, EnvironmentBRDFSampler,
    n, strand, normalize(View.xzy), surface, response, viewDepth, 0.1,
    hairLightingNoise(Parameters.SvPosition.xy, View.ViewSizeAndInvSize.zw,
        RFTemporalIndex(View.StateFrameIndex), float(View.StateFrameIndex % 160u)).y,
    EnvironmentIntensity, EnvironmentMaxMip, EnvironmentRecoveredAxes);
return color;
""", dict(
        N=normal, Tangent=curve_tangent, View=view,
        Key=vector("SceneKeyDirection", (0.6, 0.8, 1.0, 0.0)),
        Radiance=vector("SceneKeyRadiance", (1.0, 1.0, 1.0, 0.0)),
        Fill=vector("SceneFillDirection", (0.0, 0.0, 1.0, 0.0)),
        FillRadiance=vector("SceneFillRadiance", (0.0, 0.0, 0.0, 0.0)),
        Rim=vector("SceneRimDirection", (0.0, 0.0, 1.0, 0.0)),
        RimRadiance=vector("SceneRimRadiance", (0.0, 0.0, 0.0, 0.0)),
        Shadow=shadow, Position=position,
        ShadowOrigin=vector("SceneShadowOrigin", (0.0, 0.0, 0.0, 0.0)),
        ShadowForward=vector("SceneShadowForward", (1.0, 0.0, 0.0, 0.0)),
        ShadowRight=vector("SceneShadowRight", (0.0, 1.0, 0.0, 0.0)),
        ShadowUp=vector("SceneShadowUp", (0.0, 0.0, 1.0, 0.0)),
        ShadowWidth=scalar("SceneShadowWidth", 300.0),
        ShadowBias=scalar("SceneShadowBias", 0.5),
        ShadowEnabled=scalar("SceneShadowEnabled", 0.0),
        Environment=environment, EnvironmentBRDF=environment_brdf,
        EnvironmentIntensity=scalar("EnvironmentIntensity", 0.0),
        EnvironmentMaxMip=scalar("EnvironmentMaxMip", 5.0),
        EnvironmentRecoveredAxes=scalar("EnvironmentRecoveredAxes", 0.0),
        Albedo=combined_diffuse, UV=uv,
        Wetness=scalar("Wetness", 0.0),
        Depth=depth), unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    lighting.set_editor_property("include_file_paths", [
        "/Plugin/FurAuthoring/ReferenceHairLighting.ush",
        "/Plugin/FurAuthoring/RecoveredFurAdapter.ush",
        "/Plugin/FurAuthoring/FurSceneShadow.ush"])
    if not lib.connect_material_property(
            lighting, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR):
        raise RuntimeError("Could not connect recovered strand lighting")
    opacity = scalar("StrandOpacity", 1.0)
    if not lib.connect_material_property(
            opacity, "", unreal.MaterialProperty.MP_OPACITY_MASK):
        raise RuntimeError("Could not connect strand opacity")

    lib.layout_material_expressions(material)
    errors = lib.recompile_material(material)
    if errors:
        raise RuntimeError("Final strand material compile failed: " + "; ".join(errors))
    if not unreal.EditorAssetLibrary.save_loaded_asset(material):
        raise RuntimeError("Could not save " + full_path)
    return material
