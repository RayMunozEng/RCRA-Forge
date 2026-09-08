// Native Hair contact shadow. Include hair_surface.glsl first.
// The callback performs a point load in native top-left pixel coordinates and
// returns zero outside the texture. Depth is linear, not hardware Z or 1/Z.
float hairContactLoadDepth(ivec2 pixel);

float hairContactVisibility(vec2 pixel, float depth, vec3 normal,
        vec3 worldLight, vec3 viewLight, vec2 inverseDimensions,
        vec4 screenToViewA, vec2 screenToViewB, vec4 viewToScreen,
        vec2 dimensions, vec2 noiseAnglePhase, float materialRadius) {
    float scale = max((depth * uintBitsToFloat(0x3e0cf26eu)) * screenToViewA.x, 1.0);
    float inverseScale = 1.0 / scale;
    float radius = min(scale * materialRadius, scale * 0.03);
    vec3 origin = hairViewPosition(pixel, depth, inverseDimensions, screenToViewA, screenToViewB);
    float signZ = viewLight.z >= 0.0 ? 1.0 : -1.0;
    float coefficient = -1.0 / (viewLight.z + signZ);
    float crossTerm = (viewLight.x * viewLight.y) * coefficient;
    float tangentX = ((viewLight.x * viewLight.x) * coefficient) * signZ + 1.0;
    float bitangentY = (viewLight.y * viewLight.y) * coefficient + signZ;
    vec2 disc = radius * vec2(cos(noiseAnglePhase.x), sin(noiseAnglePhase.x));
    float length = scale * 0.015;
    vec3 end;
    end.x = ((origin.x + viewLight.x * length) + crossTerm * disc.y) + tangentX * disc.x;
    end.y = ((origin.y + viewLight.y * length) + (crossTerm * disc.x) * signZ) + bitangentY * disc.y;
    end.z = ((depth - viewLight.y * disc.y) + viewLight.z * length) - (viewLight.x * disc.x) * signZ;
    float inverseOrigin = 1.0 / depth, inverseEnd = 1.0 / end.z;
    vec2 originNdc = origin.xy * inverseOrigin;
#ifdef GL_ARB_gpu_shader5
    vec2 samplePixel = fma(originNdc, viewToScreen.xy, viewToScreen.zw) * dimensions;
    vec2 delta = vec2(
        fma(viewToScreen.x * inverseEnd, end.x, -(originNdc.x * viewToScreen.x)),
        fma(end.y, inverseEnd, -originNdc.y) * viewToScreen.y) * dimensions;
    vec2 stepPixel = delta * 0.25;
    float stepDepth = (inverseEnd - inverseOrigin) * 0.25;
    samplePixel = fma(stepPixel, vec2(noiseAnglePhase.y), samplePixel);
    float sampleInverseDepth = fma(stepDepth, noiseAnglePhase.y, inverseOrigin);
#else
    vec2 samplePixel = (originNdc * viewToScreen.xy + viewToScreen.zw) * dimensions;
    vec2 delta = (end.xy * inverseEnd - originNdc) * viewToScreen.xy * dimensions;
    vec2 stepPixel = delta * 0.25;
    float stepDepth = (inverseEnd - inverseOrigin) * 0.25;
    samplePixel += stepPixel * noiseAnglePhase.y;
    float sampleInverseDepth = inverseOrigin + stepDepth * noiseAnglePhase.y;
#endif
    float occlusion = 0.0;
    for (int tap = 0; tap < 4; ++tap) {
        float separation = 1.0 / sampleInverseDepth - hairContactLoadDepth(ivec2(samplePixel));
        float begins = clamp(separation * (inverseScale * uintBitsToFloat(0x4479ffffu)), 0.0, 1.0);
#ifdef GL_ARB_gpu_shader5
        float ends = clamp(fma(-separation, inverseScale * 100.0, 2.0), 0.0, 1.0);
#else
        float ends = clamp(2.0 - separation * (inverseScale * 100.0), 0.0, 1.0);
#endif
        occlusion += begins * ends;
        samplePixel += stepPixel;
        sampleInverseDepth += stepDepth;
    }
    float grazing = 1.0 - clamp(dot(worldLight, normal), 0.0, 1.0);
    return clamp(1.0 - (occlusion * 0.75) * grazing, 0.0, 1.0);
}
