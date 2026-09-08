// Native Hair key-light cloud-shadow projection and visibility fade.
float hairSceneCloudVisibility(vec3 worldPoint) {
    vec4 cloud = uHairSceneConstants[41];
    if (cloud.x <= 0.0 || !uHairHasCloudShadow) return 1.0;
    vec3 relative = vec3(
        worldPoint.x - uCameraPosition.x,
        worldPoint.y,
        worldPoint.z - uCameraPosition.z);
    vec2 projected = vec2(
        dot(vec3(uHairSceneConstants[19].x,
                 uHairSceneConstants[20].x,
                 uHairSceneConstants[21].x), relative),
        dot(vec3(uHairSceneConstants[19].y,
                 uHairSceneConstants[20].y,
                 uHairSceneConstants[21].y), relative));
    projected *= cloud.z;
    float denominator = 0.5 * (
        abs(projected.x + projected.y)
        + abs(projected.y - projected.x)) + 1.0;
    vec2 uv = projected * (0.5 / denominator) + vec2(0.5);
    float sampleVisibility = textureLod(uHairCloudShadow, uv, 0.0).r;
    return clamp(fma(1.0 - cloud.y, sampleVisibility, cloud.y), 0.0, 1.0);
}

vec3 hairSceneKeyGobo(vec3 worldPoint, vec3 color) {
    vec4 gobo = uHairSceneConstants[40];
    if (gobo.w <= 0.0 || !uHairHasGoboAtlas) return color;
    vec2 projected = vec2(
        dot(vec3(uHairSceneConstants[19].x,
                 uHairSceneConstants[20].x,
                 uHairSceneConstants[21].x), worldPoint),
        dot(vec3(uHairSceneConstants[19].y,
                 uHairSceneConstants[20].y,
                 uHairSceneConstants[21].y), worldPoint));
    vec2 tiled = fract(projected * gobo.w + vec2(0.5));
    vec2 uv = vec2(
        gobo.x + gobo.z * tiled.x,
        gobo.y + 2.0 * gobo.z * tiled.y);
    return color * textureLod(uHairGoboAtlas, uv, 0.0).rgb;
}

vec3 hairSceneKeyShadowVolumes(vec3 relative, vec3 worldPoint, vec3 color) {
    if ((uHairSceneFlags & 64u) == 0u
            || !uHairHasLightVolumes || !uHairHasGoboAtlas) return color;
    vec4 bounds = fma(vec4(relative.x), uHairSceneConstants[15],
                      relative.y * uHairSceneConstants[16]);
    bounds = fma(vec4(relative.z), uHairSceneConstants[17], bounds);
    bounds += uHairSceneConstants[18];
    float maximum = max(max(bounds.x, bounds.y), max(bounds.z, bounds.w));
    vec4 cascadeParameters = uHairSceneConstants[14];
    float level = min(max(fma(log2(maximum), cascadeParameters.x,
                              cascadeParameters.y), 0.0), cascadeParameters.z);
    int cascade = int(level);
    float encoded = uHairSceneConstants[22 + cascade].w;
    uint count = uint(fract(encoded) * 64.0);
    uint first = uint(roundEven(encoded));
    for (uint offset = 0u; offset < count; ++offset) {
        int index = int(first + offset);
        vec4 point = vec4(worldPoint, 1.0);
        vec4 a = hairLocalVolumeRow(index, 0);
        vec4 b = hairLocalVolumeRow(index, 1);
        vec4 c = hairLocalVolumeRow(index, 2);
        vec4 d = hairLocalVolumeRow(index, 3);
        vec4 fifth = hairLocalVolumeRow(index, 6);
        vec4 distances = vec4(dot(a, point), dot(b, point),
                              dot(c, point), dot(d, point));
        float fifthDistance = dot(fifth, point);
        if (min(min(distances.x, distances.y),
                min(min(distances.z, distances.w), fifthDistance)) > 0.0) {
            vec4 atlas = hairLocalVolumeRow(index, 4);
            vec2 uv = atlas.xy + vec2(
                distances.x / (distances.x + distances.y),
                distances.z / (distances.z + distances.w)) * atlas.zw;
            vec3 sampleColor = textureLod(uHairGoboAtlas, uv, 0.0).rgb;
            float fade = clamp(
                1.0 - hairLocalVolumeRow(index, 7).w * fifthDistance,
                0.0, 1.0);
            fade = clamp(fade * fade + hairLocalVolumeRow(index, 5).w,
                         0.0, 1.0);
            color *= fma(vec3(fade), vec3(1.0) - sampleColor, sampleColor);
        }
    }
    return color;
}
