// HairDenoise uses D3D top-left UVs, decoded packed vectors (without another
// normalization), conservative half depth, fractional masks and three gathers.
// The caller supplies resource access so captured and preview bindings share
// the same arithmetic. Gather components follow D3D's xyzw order.
// Include hair_surface.glsl before this source.
vec4 hairDenoiseGatherDepth(vec2 uv);
vec4 hairDenoiseGatherMask(vec2 uv);
vec4 hairDenoiseGatherColor(vec2 uv, int component);
bool hairDenoiseTileActive(vec2 uv);

float hairDenoiseHalfDepth(float depth) {
    // Strictly greater representable half: 122,142 captured masked pixels
    // match floor-to-half plus one code, including exactly representable input.
    if (depth < 0.00006103515625) {
        return (floor(max(depth, 0.0) * 16777216.0) + 1.0) / 16777216.0;
    }
    if (depth >= 65504.0) return uintBitsToFloat(0x7f800000u);
    return uintBitsToFloat((floatBitsToUint(depth) & 0xffffe000u) + 8192u);
}

struct HairDenoiseRay {
    vec3 samplePosition; // UV and reciprocal linear depth
    vec3 step;
    float extent;
};

HairDenoiseRay hairDenoiseBuildRay(
        vec2 pixel, float depth, vec3 normal, vec3 strand, vec3 viewTangent,
        vec2 inverseDimensions, vec4 screenToViewA, vec2 screenToViewB,
        vec4 viewToScreen, float phase) {
    float rayLength = min(0.0025, sqrt(1.0 - abs(dot(normal, strand))) * 0.05);
    vec3 position = hairViewPosition(
        pixel, depth, inverseDimensions, screenToViewA, screenToViewB
    );
#ifdef GL_ARB_gpu_shader5
    vec3 negative = fma(-viewTangent, vec3(rayLength * 0.5), position);
    vec3 positive = fma(viewTangent, vec3(rayLength * 0.5), position);
#else
    vec3 offset = viewTangent * (rayLength * 0.5);
    vec3 negative = position - offset;
    vec3 positive = position + offset;
#endif
    float inverseNegative = 1.0 / negative.z;
    float inversePositive = 1.0 / positive.z;
    vec2 negativeNdc = negative.xy * inverseNegative;
#ifdef GL_ARB_gpu_shader5
    vec2 startUV = fma(negativeNdc, viewToScreen.xy, viewToScreen.zw);
    vec2 deltaUV = fma(positive.xy, vec2(inversePositive), -negativeNdc)
        * viewToScreen.xy * uintBitsToFloat(0x3eaaaaabu);
#else
    vec2 startUV = negativeNdc * viewToScreen.xy + viewToScreen.zw;
    vec2 deltaUV = (positive.xy * inversePositive - negativeNdc)
        * viewToScreen.xy * uintBitsToFloat(0x3eaaaaabu);
#endif
    float deltaDepth = (inversePositive - inverseNegative) * uintBitsToFloat(0x3eaaaaabu);
    HairDenoiseRay ray;
#ifdef GL_ARB_gpu_shader5
    ray.samplePosition = vec3(fma(deltaUV, vec2(phase), startUV),
                              fma(deltaDepth, phase, inverseNegative));
#else
    ray.samplePosition = vec3(startUV + deltaUV * phase,
                              inverseNegative + deltaDepth * phase);
#endif
    ray.step = vec3(deltaUV, deltaDepth);
    ray.extent = rayLength;
    return ray;
}

vec4 hairDenoiseDepthWeight(vec4 difference, float scale) {
#ifdef GL_ARB_gpu_shader5
    // A fused operation is observable at stored-color boundaries. Explicit ray
    // FMAs above also preserve projection arithmetic when precise propagates.
    // All 11,215 captured float RGB values and sums match with this ordering.
    precise vec4 value = fma(difference, vec4(scale), vec4(1.0));
    return clamp(value, 0.0, 1.0);
#else
    return clamp(difference * scale + 1.0, 0.0, 1.0);
#endif
}

vec3 hairDenoiseFilter(HairDenoiseRay ray, vec3 centerColor, float centerDepth) {
    vec3 colorSum = centerColor;
    float weightSum = 1.0;
    for (int i = 0; i < 3; ++i) {
        if (hairDenoiseTileActive(ray.samplePosition.xy)) {
            vec4 depths = hairDenoiseGatherDepth(ray.samplePosition.xy);
            vec4 weights = hairDenoiseDepthWeight(
                depths - 1.0 / ray.samplePosition.z, 200.0 / centerDepth
            ) * hairDenoiseGatherMask(ray.samplePosition.xy);
            vec3 gathered = vec3(
                dot(hairDenoiseGatherColor(ray.samplePosition.xy, 0), weights),
                dot(hairDenoiseGatherColor(ray.samplePosition.xy, 1), weights),
                dot(hairDenoiseGatherColor(ray.samplePosition.xy, 2), weights)
            );
            colorSum += gathered;
            weightSum += dot(weights, vec4(1.0));
            // The retail loop advances only when the tile's Hair bit is set.
            ray.samplePosition += ray.step;
        }
    }
    return colorSum * (1.0 / weightSum);
}
