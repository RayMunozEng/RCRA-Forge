// Native Hair material response and final lighting resolve. GLSL 4.30+, or
// GL_ARB_gpu_shader5 in GLSL 3.30. Inputs are stored, decoded G-buffer values.
struct HairMaterialResponse {
    vec3 primaryF0;
    vec3 secondaryF0;
    float adjustedGloss;
    vec2 gloss;
    vec2 primaryAlpha;
    vec2 secondaryAlpha;
    vec2 primarySquared;
    vec2 secondarySquared;
    float occlusion;
    float emissive;
    float transmission;
};

HairMaterialResponse hairMaterialResponse(uvec4 material, uint strand,
                                         vec4 albedo, float depth) {
    HairMaterialResponse response;
    vec3 codes = vec3(material.z >> 8u, material.z & 255u, material.w >> 8u);
    vec3 specular = codes * uintBitsToFloat(0x3b808081u);
    response.primaryF0 = specular * specular;
    response.secondaryF0 = clamp(sqrt(response.primaryF0) * 5.0, 0.0, 1.0)
        / (sqrt(albedo.rgb) + 0.75);
    bool hasOcclusion = (material.y & 8192u) != 0u;
    response.occlusion = hasOcclusion ? albedo.a : 1.0;
    response.emissive = hasOcclusion ? 0.0 : exp2(albedo.a * 5.0) - 1.0;
    response.transmission = float((strand >> 19u) & 127u) * uintBitsToFloat(0x3c810204u);
    float gloss = float(material.w & 255u) * uintBitsToFloat(0x3b808081u);
#ifdef GL_ARB_gpu_shader5
    precise float fade = clamp(fma(depth, 0.125, -0.25), 0.0, 1.0);
    precise float scale = fma(-fade, uintBitsToFloat(0x3eaa7efau), 1.0);
    precise float adjusted = gloss * scale;
    precise float primary = fma(adjusted, 0.6, 0.1);
    precise float secondaryScale = fma(adjusted, 0.3, 0.05);
    precise float secondary = fma(-secondaryScale, primary, primary);
    // DXIL folds the primary gloss transform into these coefficients.
    precise vec2 primaryWidth = clamp(fma(vec2(-adjusted),
        vec2(uintBitsToFloat(0x3ee6d481u), uintBitsToFloat(0x3d38aa00u)),
        vec2(uintBitsToFloat(0x3f65b963u), uintBitsToFloat(0x3f770953u))), 0.0, 1.0);
    precise vec2 secondaryWidth = clamp(fma(vec2(-secondary),
        vec2(uintBitsToFloat(0x3f405bc0u), uintBitsToFloat(0x3d99e300u)),
        vec2(uintBitsToFloat(0x3f78f5c3u))), 0.0, 1.0);
#else
    float fade = clamp(depth * 0.125 - 0.25, 0.0, 1.0);
    float adjusted = gloss * (1.0 - fade * uintBitsToFloat(0x3eaa7efau));
    float primary = adjusted * 0.6 + 0.1;
    float secondary = primary - (adjusted * 0.3 + 0.05) * primary;
    vec2 primaryWidth = clamp(vec2(uintBitsToFloat(0x3f65b963u), uintBitsToFloat(0x3f770953u))
        - adjusted * vec2(uintBitsToFloat(0x3ee6d481u), uintBitsToFloat(0x3d38aa00u)), 0.0, 1.0);
    vec2 secondaryWidth = clamp(vec2(uintBitsToFloat(0x3f78f5c3u))
        - secondary * vec2(uintBitsToFloat(0x3f405bc0u), uintBitsToFloat(0x3d99e300u)), 0.0, 1.0);
#endif
    response.adjustedGloss = adjusted;
    response.gloss = vec2(primary, secondary);
    vec2 primarySquare = primaryWidth * primaryWidth;
    vec2 secondarySquare = secondaryWidth * secondaryWidth;
    response.primaryAlpha = primarySquare * primarySquare;
    response.secondaryAlpha = secondarySquare * secondarySquare;
    response.primarySquared = primarySquare;
    response.secondarySquared = secondarySquare;
    return response;
}

vec3 hairWrappedLight(vec3 normal, vec3 light) {
#ifdef GL_ARB_gpu_shader5
    precise vec3 wrapped = fma(normal - light, vec3(0.25), light);
    return wrapped;
#else
    return (normal - light) * 0.25 + light;
#endif
}

float hairDiffuseResponse(float normalLight, float transmission) {
    float width = transmission + 1.0;
    return clamp((normalLight + transmission) / (width * width), 0.0, 1.0);
}

float hairTransmissionResponse(float phase, float normalLight, float normalView) {
#ifdef GL_ARB_gpu_shader5
    precise float linear = fma(-phase, 10.5, 8.0);
    precise float angular = fma(phase * phase, uintBitsToFloat(0x404af3f5u), linear);
#else
    float linear = 8.0 - phase * 10.5;
    float angular = phase * phase * uintBitsToFloat(0x404af3f5u) + linear;
#endif
    float attenuation = clamp(clamp(normalLight, 0.0, 1.0) * normalView, 0.0, 1.0) + 0.1;
    return 1.0 / (angular * attenuation);
}

// Diffuse transmission blend, specular history blend, specular occlusion.
vec3 hairResolveWeights(float transmission, float normalView,
                        float materialOcclusion, float historyOcclusion) {
#ifdef GL_ARB_gpu_shader5
    precise float grazing = clamp(fma(-normalView, 2.0, 1.0), 0.0, 1.0);
    precise float square = grazing * grazing;
    precise float diffuse = fma(historyOcclusion * 0.5, square, 0.5) * transmission;
    precise float specular = fma(square, uintBitsToFloat(0x3f75c28fu),
                                 uintBitsToFloat(0x3d23d70au)) * transmission;
#else
    float grazing = clamp(1.0 - normalView * 2.0, 0.0, 1.0);
    float square = grazing * grazing;
    float diffuse = (historyOcclusion * 0.5 * square + 0.5) * transmission;
    float specular = (square * uintBitsToFloat(0x3f75c28fu) + uintBitsToFloat(0x3d23d70au)) * transmission;
#endif
    float occlusion = min(materialOcclusion * materialOcclusion,
                          historyOcclusion * historyOcclusion);
    return vec3(diffuse, specular, occlusion);
}

vec3 hairResolveLighting(vec3 albedo, float materialOcclusion, float emissive,
                         vec3 weights, vec3 diffuse, vec3 back,
                         vec3 specular, vec3 history) {
#ifdef GL_ARB_gpu_shader5
    precise vec3 mixedDiffuse = fma(vec3(weights.x), back - diffuse, diffuse);
    precise vec3 mixedSpecular = fma(vec3(weights.y), history - specular, specular);
    precise vec3 shadedDiffuse = fma(mixedDiffuse, vec3(materialOcclusion), vec3(emissive));
    precise vec3 color = fma(albedo, shadedDiffuse, mixedSpecular * weights.z);
#else
    vec3 mixedDiffuse = weights.x * (back - diffuse) + diffuse;
    vec3 mixedSpecular = weights.y * (history - specular) + specular;
    vec3 shadedDiffuse = mixedDiffuse * materialOcclusion + emissive;
    vec3 color = albedo * shadedDiffuse + mixedSpecular * weights.z;
#endif
    return color;
}
