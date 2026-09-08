// Asset-preview illumination, shared by forward fallback and deferred lighting.
// Shared material/frame/lobe/resolve helpers have captured evidence. Complete
// scene illumination and reflection history remain separate parity work.
void recoveredHairBasis(
        vec3 strandTangent,
        vec3 geometricNormal,
        vec3 viewDirection,
        out vec3 lobeNormal,
        out vec3 lobeSide) {
    // CS_ApplyGBufferLighting_Hair instructions 95-129.  GBufExtra is a
    // strand tangent, not a replacement surface normal.  Retail constructs a
    // view-oriented frame around that tangent for each of its two lobes.
    HairLobeFrame frame = hairLobeFrame(strandTangent, geometricNormal, viewDirection);
    lobeSide = frame.side;
    lobeNormal = frame.normal;
}

float recoveredHairDistribution(
        vec3 lobeNormal,
        vec3 strandTangent,
        vec3 lobeSide,
        vec3 lightDirection,
        vec3 viewDirection,
        vec3 halfVector,
        float alphaAlong,
        float alphaAcross) {
    // Shared with the complete captured Hair lighting comparison.
    float normalHalf = dot(lobeNormal, halfVector);
    float tangentHalf = dot(strandTangent, halfVector);
    float sideHalf = dot(lobeSide, halfVector);
    float normalLight = clamp(dot(lobeNormal, lightDirection), 0.0, 1.0);
    float normalView = min(abs(dot(lobeNormal, viewDirection)) + 0.00001, 1.0);
    return hairLobeDistribution(vec3(normalHalf, tangentHalf, sideHalf),
                                vec2(alphaAlong, alphaAcross), normalLight, normalView);
}

vec3 recoveredHairFresnel(vec3 f0, float viewHalf) {
    return hairFresnel(f0, viewHalf);
}

vec3 sampleD3DCube(vec3 direction, float lod) {
    // Captured D3D/GL cube orientations agree; native filtering crosses edges.
    return textureLod(uFurEnvironment, direction, lod).rgb;
}


void evaluatePreviewHairLighting(
        uvec4 packedMaterial, uint packedStrand, vec3 normal, vec3 strandTangent,
        vec4 albedo, float customViewDepth, vec3 viewDirection,
        vec2 lightingPixel, vec3 worldPoint, float keyVisibility,
        out vec3 directColor, out vec3 indirectColor) {
    // Unit-radiance direct-light evaluation from CS_ApplyGBufferLighting_Hair.
    // The default asset view supplies a unit key and cube. The optional scene
    // path supplies key radiance, tile-selected probes and the resident grid.
    HairMaterialResponse material = hairMaterialResponse(
        packedMaterial, packedStrand, albedo, customViewDepth);
#ifdef HAIR_SCENE_LIGHTING
    vec3 lightDirection = uLightDir;
#else
    vec3 lightDirection = normalize(uLightDir);
#endif
    float normalLight = dot(normal, lightDirection);
    float normalView = dot(normal, viewDirection);
    float diffuseResponse = hairDiffuseResponse(normalLight, material.transmission);
    vec3 wrappedLight = hairWrappedLight(normal, lightDirection);
    float transmissionResponse = hairTransmissionResponse(
        dot(-viewDirection, wrappedLight), normalLight, normalView);

    vec3 secondaryTangent = hairSecondaryStrand(strandTangent, normal, packedStrand >> 26u);
    HairLobeFrame primary = hairLobeFrame(strandTangent, normal, viewDirection);
    HairLobeFrame secondary = hairLobeFrame(secondaryTangent, normal, viewDirection);
    vec3 halfVector = normalize(lightDirection + viewDirection);
    float primaryDistribution = recoveredHairDistribution(
        primary.normal, strandTangent, primary.side, lightDirection, viewDirection,
        halfVector, material.primaryAlpha.x, material.primaryAlpha.y);
    float secondaryDistribution = recoveredHairDistribution(
        secondary.normal, secondaryTangent, secondary.side, lightDirection, viewDirection,
        halfVector, material.secondaryAlpha.x, material.secondaryAlpha.y);
    float viewHalf = dot(viewDirection, halfVector);
    vec3 primaryFresnel = recoveredHairFresnel(material.primaryF0, viewHalf);
    vec3 secondaryFresnel = recoveredHairFresnel(material.secondaryF0, viewHalf);
    vec3 primarySpecular = primaryFresnel * primaryDistribution;
    vec3 secondarySpecular = secondaryFresnel * secondaryDistribution;

    vec3 indirectPrimary = vec3(0.0);
    vec3 indirectDiffuse = vec3(0.0);
    if (uHasFurEnvironment) {
        float angle = hairLightingNoise(lightingPixel,
            1.0 / max(uViewportSize, vec2(1.0)), uTemporalIndex, uTemporalPlusCycle).y;
        HairEnvironmentFrame environment = hairEnvironmentFrame(
            normal, strandTangent, viewDirection, primary,
            material.primaryAlpha, material.gloss, angle);
        vec3 environmentSpecular;
#ifdef HAIR_SCENE_LIGHTING
        HairProbeLighting scene = hairSceneIndirect(worldPoint, normal, environment, lightingPixel);
        environmentSpecular = scene.specular;
        indirectDiffuse = scene.diffuse;
#else
        environmentSpecular = sampleD3DCube(environment.reflection,
            5.0 - clamp(environment.averageGloss, 0.0, 1.0) * 5.0) * 0.6;
        indirectDiffuse = sampleD3DCube(normal, 5.0) * 0.6;
#endif
        vec2 environmentBrdf = textureLod(uFurBrdfLut,
            vec2(abs(dot(environment.normal, viewDirection)), environment.averageGloss), 0.0).rg;
#ifdef GL_ARB_gpu_shader5
        precise vec3 environmentWeight = fma(material.primaryF0,
            vec3(environmentBrdf.x), vec3(environmentBrdf.y));
        precise vec3 specular = environmentSpecular * environmentWeight;
        precise vec3 diffuse = fma(environmentSpecular, material.secondaryF0, indirectDiffuse);
        indirectPrimary = specular;
        indirectDiffuse = diffuse;
#else
        indirectPrimary = environmentSpecular
            * (environmentBrdf.x * material.primaryF0 + environmentBrdf.y);
        indirectDiffuse += environmentSpecular * material.secondaryF0;
#endif
    }

#ifdef HAIR_SCENE_LIGHTING
    HairHistory history = HairHistory(vec3(0.0), 1.0);
    if (uHairHasHistory) {
        float angle = hairLightingNoise(lightingPixel, 1.0 / uViewportSize,
            uTemporalIndex, uTemporalPlusCycle).x;
        history = hairReflectionHistory(lightingPixel, customViewDepth, strandTangent,
            uHairHistoryWorldToClip, uViewportSize, 1.0 / uViewportSize, angle);
    }
    precise vec3 radiance = uHairSceneKeyColor * keyVisibility;
    radiance = radiance * vec3(hairSceneCloudVisibility(worldPoint));
    radiance = hairSceneKeyGobo(worldPoint, radiance);
    radiance = hairSceneKeyShadowVolumes(
        worldPoint - uCameraPosition, worldPoint, radiance);
    precise vec3 keyDiffuse = fma(secondaryFresnel, vec3(secondaryDistribution), vec3(diffuseResponse));
    precise vec3 diffuse = fma(radiance, keyDiffuse, indirectDiffuse);
    precise vec3 specular = fma(primaryFresnel * radiance, vec3(primaryDistribution), indirectPrimary);
    precise vec3 back = radiance * transmissionResponse;
    HairLocalAccumulation localLighting = HairLocalAccumulation(
        diffuse, back, specular);
    vec2 localShadowNoise = hairLightingNoise(
        lightingPixel, 1.0 / uViewportSize,
        uTemporalIndex, uTemporalPlusCycle).xz;
    hairApplyLocalLights(
        lightingPixel, customViewDepth, worldPoint, normal,
        strandTangent, secondaryTangent,
        primary, secondary, material, viewDirection,
        (packedStrand >> 19u) & 127u,
        localShadowNoise, localLighting);
    vec3 weights = hairResolveWeights(material.transmission, normalView, material.occlusion, history.occlusion);
    indirectColor = hairResolveLighting(albedo.rgb, material.occlusion, material.emissive,
        weights, localLighting.diffuse, localLighting.back,
        localLighting.specular, history.color);
    directColor = vec3(0.0);
#else
    // No valid scene reflection-history samples are supplied by the asset view.
    // Use the native fallback (black history, unit history visibility).
    vec3 weights = hairResolveWeights(material.transmission, normalView, material.occlusion, 1.0);
    directColor = hairResolveLighting(albedo.rgb, material.occlusion, 0.0, weights,
        vec3(diffuseResponse) + secondarySpecular, vec3(transmissionResponse),
        primarySpecular, vec3(0.0));
    indirectColor = hairResolveLighting(albedo.rgb, material.occlusion, material.emissive, weights,
        indirectDiffuse, vec3(0.0), indirectPrimary, vec3(0.0));
#endif
}
