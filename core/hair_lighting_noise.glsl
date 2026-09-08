float hairScreenHash(vec2 normalizedPixel, float temporalIndex) {
    return fract(sin(dot(normalizedPixel, vec2(
        uintBitsToFloat(0x414fd639u), uintBitsToFloat(0x429c774cu)
    ))) * uintBitsToFloat(0x472aee8cu) + temporalIndex);
}

// Fur PS uses pixel centers; Hair/HairDenoise compute use integer coordinates.
// DXIL unary opcode 27 is Round_ni (floor), including negative shell offsets.
float hairScreenPhase(vec2 pixel, vec2 inverseDimensions,
                      float temporalIndex, float temporalPlusCycle) {
    vec2 cell = floor(pixel);
    float base = cell.x + cell.y * 2.0 + temporalPlusCycle;
#ifdef GL_ARB_gpu_shader5
    precise float seed = base + hairScreenHash(pixel * inverseDimensions, temporalIndex);
#else
    float seed = base + hairScreenHash(pixel * inverseDimensions, temporalIndex);
#endif
    return fract(seed * uintBitsToFloat(0x3e4ccccdu));
}

float hairCoveragePhase(vec2 pixel, float slice, vec2 inverseDimensions,
                        float temporalIndex, float temporalPlusCycle) {
#ifdef GL_ARB_gpu_shader5
    // Native D3D12 fuses x - 10*slice. The one-ULP difference in this
    // coordinate changes the amplified sine hash at fractional shell slices.
    vec2 shifted = vec2(fma(-10.0, slice, pixel.x), pixel.y + slice);
#else
    vec2 shifted = pixel + vec2(-10.0 * slice, slice);
#endif
    return hairScreenPhase(shifted, inverseDimensions, temporalIndex, temporalPlusCycle);
}

float hairWetnessStep(float wetness, float phase) {
    float remaining = 1.0 - clamp(wetness, 0.0, 1.0);
    float wetBase = (1.0 - remaining * remaining) * 8.0;
    return clamp(floor((phase * 0.1 + 0.45) + wetBase) * 0.125, 0.0, 1.0);
}

// CS_ApplyGBufferLighting_Hair DXIL: integer pixel coordinates in D3D order.
// Keep the base and jitter addition before the 0.2 scale. Distributing that
// scale changes shadow/reflection sample positions at float32 precision.
vec3 hairLightingNoise(
        vec2 pixel, vec2 inverseDimensions,
        float temporalIndex, float temporalPlusCycle) {
    float phaseScale = uintBitsToFloat(0x3e4ccccdu);
    float angleScale = uintBitsToFloat(0x4196cbe4u);
    float base = pixel.x + pixel.y * 2.0 + temporalPlusCycle;
    float checker = fract((pixel.x + pixel.y + temporalIndex) * 0.5 + 0.25);
#ifdef GL_ARB_gpu_shader5
    precise float directSeed = base + checker;
#else
    float directSeed = base + checker;
#endif
    vec2 normalizedPixel = pixel * inverseDimensions;
    float hash = hairScreenHash(normalizedPixel, temporalIndex);
#ifdef GL_ARB_gpu_shader5
    precise float reflectionSeed = base + hash;
#else
    float reflectionSeed = base + hash;
#endif
    float contactPhase = fract(base * phaseScale)
        + float((int(pixel.x) + int(pixel.y) + int(temporalIndex)) & 1)
            * uintBitsToFloat(0x3dcccccdu);
    return vec3(fract(directSeed * phaseScale) * angleScale,
                fract(reflectionSeed * phaseScale) * angleScale,
                contactPhase);
}
