// Native cascaded key-light atlas evaluation. Constants use GlobalWorldCB rows.
// Atlas callbacks use linear/clamp filtering; comparison uses strict Less.
vec4 hairKeyConstant(int row);
float hairKeyDepth(vec2 uv);
float hairKeyCompare(vec3 uvDepth);

float hairKeyShadowVisibility(vec3 relative, uint transmissionCode, vec2 noiseAnglePhase) {
    precise vec4 bounds = fma(vec4(relative.x), hairKeyConstant(15), relative.y * hairKeyConstant(16));
    bounds = fma(vec4(relative.z), hairKeyConstant(17), bounds);
    bounds += hairKeyConstant(18);
    float maximum = max(max(bounds.x, bounds.y), max(bounds.z, bounds.w));
    vec4 cascadeParameters = hairKeyConstant(14);
    precise float fade = clamp(fma(maximum, cascadeParameters.w, -9.0), 0.0, 1.0);
    if (fade >= 1.0) return 1.0;
    precise float level = min(max(fma(log2(maximum), cascadeParameters.x, cascadeParameters.y), 0.0), cascadeParameters.z);
    int cascade = int(level);
    precise float transition = max(fma(fract(level), 16.0, -15.0), 0.0);
    if (noiseAnglePhase.y < transition) cascade = min(cascade + 1, int(cascadeParameters.z));
    vec3 scale = hairKeyConstant(22 + cascade).xyz;
    vec4 clampBounds = hairKeyConstant(34 + cascade);
    precise vec3 position = fma(vec3(relative.y), hairKeyConstant(20).xyz, relative.z * hairKeyConstant(21).xyz);
    position = fma(vec3(relative.x), hairKeyConstant(19).xyz, position);
    position = fma(position, scale, hairKeyConstant(28 + cascade).xyz);
    position.xy = clamp(position.xy, clampBounds.xy, clampBounds.zw);
    float inverseScale = 1.0 / max(uintBitsToFloat(0x358637bdu), scale.z);
    // DXIL folds the packed transmission/radius transformation into this FMA.
    precise float radius = fma(float(transmissionCode), uintBitsToFloat(0x39041aa4u), uintBitsToFloat(0x3b03126fu));
    float depthBias = (radius * inverseScale) * uintBitsToFloat(0x39000000u);
    float visibility;
    if (position.z < depthBias) {
        visibility = hairKeyCompare(position);
    } else {
        vec2 footprint = max(radius * scale.xy, vec2(uintBitsToFloat(0x39400000u)));
        precise float absorption = fma(-float(transmissionCode), uintBitsToFloat(0x3c810204u), 1.0);
        absorption *= 4.0;
        absorption = fma(absorption, absorption, 1.0);
        absorption *= 35.0;
        vec2 direction = vec2(cos(noiseAnglePhase.x), sin(noiseAnglePhase.x));
        float distanceSquared = 0.125;
        float sum = 0.0;
        for (int tap = 0; tap < 4; ++tap) {
            precise vec2 uv = fma(footprint * direction, vec2(sqrt(distanceSquared)), position.xy);
            uv = clamp(uv, clampBounds.xy, clampBounds.zw);
            // DXIL subtracts before scaling the sampled depth difference.
            precise float separation = (position.z - hairKeyDepth(uv)) * inverseScale;
            separation = max(fma(-distanceSquared, depthBias, separation), 0.0);
            float opticalDepth = absorption * separation;
            sum += exp2(opticalDepth * uintBitsToFloat(0xbfb8aa3bu));
            precise float nextX = fma(direction.x, uintBitsToFloat(0xbf3cc434u),
                -(direction.y * uintBitsToFloat(0x3f2cecf0u)));
            float nextY = dot(direction, vec2(uintBitsToFloat(0x3f2cecf0u), uintBitsToFloat(0xbf3cc434u)));
            direction = vec2(nextX, nextY);
            distanceSquared += 0.25;
        }
        visibility = sum * 0.25;
    }
    precise float faded = fma(-visibility, fade, fade) + visibility;
    return faded;
}
