// PS_FurShellGBufferDeferred material terms, before G-buffer quantization.
vec3 furGroom(vec2 control, float scaledHandedness) {
    vec2 comb = (control * 2.0 - 1.0) * abs(scaledHandedness);
    float combZ = sqrt(1.0 - min(dot(comb, comb), 0.99));
    return normalize(vec3(comb, combZ));
}

vec2 furLayerUV(vec2 uv, float density, vec3 groom, float curvedOffset,
                float uvDivisor) {
    // Preserve multiply-then-divide before adding the base UV. Reassociation
    // crosses a native texture-filter boundary in the captured head draw.
#ifdef GL_ARB_gpu_shader5
    precise vec2 offset = groom.xy * curvedOffset;
    precise vec2 shift = offset / groom.z;
#else
    vec2 offset = groom.xy * curvedOffset;
    vec2 shift = offset / groom.z;
#endif
    return (density * uv + shift) / uvDivisor;
}

float furWetLayerValue(float sampledValue, float wetness) {
    float expanded = exp2(log2(clamp(sampledValue + 0.1, 0.0, 1.0)) * 5.0);
#ifdef GL_ARB_gpu_shader5
    precise float difference = expanded - sampledValue;
    return fma(difference, wetness, sampledValue);
#else
    return sampledValue + (expanded - sampledValue) * wetness;
#endif
}

vec4 furWetAlbedo(vec4 albedo, float wetness, float shellDepth) {
    float wetBlend = sqrt(shellDepth) * wetness;
    // The native multiplier is the float immediately above -0.2.
#ifdef GL_ARB_gpu_shader5
    precise vec4 attenuation = albedo * uintBitsToFloat(0xbe4cccccu);
    return fma(attenuation, vec4(wetBlend), albedo);
#else
    return albedo + albedo * uintBitsToFloat(0xbe4cccccu) * wetBlend;
#endif
}

vec2 furMotionVector(vec2 pixel, vec2 inverseViewport, vec4 previousClip,
                     float nearPlane, vec2 viewportSize) {
    float inversePrevious = 1.0 / max(previousClip.w, nearPlane);
#ifdef GL_ARB_gpu_shader5
    precise vec2 currentUV = pixel * inverseViewport;
    precise vec2 currentCentered = currentUV - 0.5;
    precise vec2 previousHalf = previousClip.xy * 0.5;
    precise vec2 motion = fma(vec2(-1.0, 1.0) * previousHalf,
                             vec2(inversePrevious), currentCentered);
#else
    vec2 currentCentered = pixel * inverseViewport - 0.5;
    vec2 motion = currentCentered
        + vec2(-1.0, 1.0) * (previousClip.xy * 0.5) * inversePrevious;
#endif
    return motion * viewportSize;
}

vec3 furStrandDirection(vec3 normal, vec4 worldTangent, vec3 groom,
                       bool flipTangent) {
    vec3 tangent = normalize(worldTangent.xyz);
    float handedness = worldTangent.w < 0.0 ? -1.0 : 1.0;
    if (flipTangent) handedness = -handedness;
    // Keep the cross-product magnitude. The captured frame is not
    // orthogonalized after bending and raster interpolation.
    vec3 bitangent = cross(normal, tangent) * handedness;
    return normalize(-tangent * groom.x + bitangent * groom.y + normal * groom.z);
}

float furContactDepth(float viewDepth, float controlLength,
                      float layerValue, float phase, float shellDepth,
                      float furLength) {
    float fieldOffset = (0.25 - phase * 0.125) - layerValue * 0.125;
#ifdef GL_ARB_gpu_shader5
    precise float offset = (0.95 * controlLength + 0.05)
        * (1.0 - shellDepth) * fieldOffset;
    return fma(-offset, furLength + 0.005, viewDepth);
#else
    return viewDepth - (0.95 * controlLength + 0.05)
        * (1.0 - shellDepth) * fieldOffset * (furLength + 0.005);
#endif
}

vec2 furGlossSpecular(vec2 sampledResponse, float glossScale,
                     float specularScale, float wetness, float shellDepth) {
    float gloss = clamp(sqrt(max(sampledResponse.r, 0.0)) * glossScale, 0.0, 1.0);
    float wetBlend = sqrt(shellDepth) * clamp(wetness, 0.0, 1.0);
    gloss += (1.0 - gloss) * wetBlend;
    float specular = sqrt(clamp(sampledResponse.g * specularScale, 0.0, 1.0));
    return vec2(gloss, specular);
}
