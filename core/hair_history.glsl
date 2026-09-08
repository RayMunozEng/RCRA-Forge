// Native three-tap Hair reflection history. Coordinates and motion are in the
// original top-left, full-resolution pixel frame. Point loads return zero OOB.
float hairHistoryDepth(ivec2 pixel);
vec2 hairHistoryVelocity(ivec2 halfPixel);
vec3 hairHistorySample(vec2 uv);

struct HairHistory {
    vec3 color;
    float occlusion;
};

HairHistory hairReflectionHistory(vec2 pixel, float depth, vec3 strand,
        mat3x2 worldToClip, vec2 dimensions, vec2 inverseDimensions, float angle) {
    precise vec2 projected = fma(vec2(strand.y), worldToClip[1], strand.x * worldToClip[0]);
    projected = fma(vec2(strand.z), worldToClip[2], projected);
    projected.y = -projected.y;
    float inverseDepth = 1.0 / depth;
    precise float radius = ((dimensions.x + dimensions.y) * uintBitsToFloat(0x3bf5c28fu)) * min(1.0, inverseDepth);
    vec2 direction = vec2(cos(angle), sin(angle));
    float phase = uintBitsToFloat(0x3e2aaaabu);
    precise vec4 sum = vec4(0.0);
    float count = 0.0;
    for (int tap = 0; tap < 3; ++tap) {
        precise vec2 samplePixel = fma(vec2(radius * phase), direction, pixel + 0.5);
        float sampledDepth = hairHistoryDepth(ivec2(samplePixel));
        if (sampledDepth > 0.0) {
            precise float difference = (sampledDepth + uintBitsToFloat(0x3a83126fu)) - depth;
            precise float visibility = clamp(fma(difference, inverseDepth * 500.0, 1.0), 0.0, 1.0);
            precise float weight = clamp(fma(difference, inverseDepth * 0.875, 0.125), 0.0, 1.0);
            precise vec2 historyPixel = fma((radius * projected) * phase, vec2(direction.y), pixel);
            vec2 velocity = hairHistoryVelocity(ivec2(historyPixel) >> 1);
            vec3 color = hairHistorySample((historyPixel - velocity) * inverseDimensions);
            sum.rgb = fma(vec3(weight), color, sum.rgb);
            sum.a = fma(visibility, visibility, sum.a);
            count += 1.0;
        }
        precise float nextX = fma(direction.x, uintBitsToFloat(0x3f1bc2a6u),
                                  -(direction.y * uintBitsToFloat(0x3f4b296bu)));
        precise float nextY = fma(direction.x, uintBitsToFloat(0x3f4b296bu),
                                  direction.y * uintBitsToFloat(0x3f1bc2a6u));
        direction = vec2(nextX, nextY);
        phase += uintBitsToFloat(0x3eaaaaabu);
    }
    if (count > 0.0) sum *= 1.0 / count;
    else sum = vec4(0.0, 0.0, 0.0, 1.0);
    return HairHistory(sum.rgb, sum.a);
}
