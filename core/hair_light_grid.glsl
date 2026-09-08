// Hair DXBC 5ff73b6b2aca9640cf18cd78b88ba3c0: t50/t51 and distant GI.
// GLSL 4.30+, or GLSL 3.30 with GL_ARB_gpu_shader5 and
// GL_ARB_shading_language_packing for fma / unpackHalf2x16.
// Callbacks use the actual resident resources; positions are world coordinates.
uint hairGridLookup(uint index);
uvec4 hairGridRecord(uint index);
vec3 hairGridDefault(vec3 direction, float mip);
float hairGridDistantHeight(vec2 uv);
vec4 hairGridDistantSamples(vec3 uvw);

struct HairGridParameters {
    vec3 cameraPosition;
    float bleedReduction;
    vec3 ambientFill;
    float intensity;
    vec4 distantUVScaleOffset;
    float distantIrradianceScale;
    float distantMidHeight;
    float distantHeightScale;
};
struct HairGridLighting {
    vec3 diffuse;
    float reflection;
    float fallbackWeight;
};

float hairGridSat(float v) { return isnan(v) ? 0.0 : clamp(v, 0.0, 1.0); }
vec2 hairGridSat(vec2 v) { return vec2(hairGridSat(v.x), hairGridSat(v.y)); }

vec4 hairGridRadiance(uvec3 radiance, vec3 normal, vec3 reflection) {
    uvec3 nShift = uvec3(lessThanEqual(normal, vec3(0.0))) * 16u;
    uvec3 rShift = uvec3(lessThanEqual(reflection, vec3(0.0))) * 16u;
    uvec3 selected = radiance >> nShift;
    vec3 x = vec3(selected.xxx & uvec3(63, 1984, 63488));
    vec3 y = vec3(selected.yyy & uvec3(63, 1984, 63488));
    vec3 z = vec3(selected.zzz & uvec3(63, 1984, 63488));
    vec3 n2 = normal * normal, r2 = reflection * reflection;
    vec3 encoded = fma(z, vec3(n2.z), fma(x, vec3(n2.x), y * n2.y));
    vec2 chroma = fma(encoded.yz, vec2(1.0 / 992.0, 1.0 / 31744.0), vec2(-1.0));
    chroma *= abs(chroma);
    float middle = fma(-chroma.x, encoded.x, encoded.x);
    vec3 rgb = vec3(fma(chroma.y, encoded.x, middle),
                    fma(chroma.x, encoded.x, encoded.x),
                    fma(-chroma.y, encoded.x, middle));
    vec3 lumas = vec3((radiance >> rShift) & uvec3(63));
    float scalar = fma(lumas.z, r2.z, lumas.x * r2.x + lumas.y * r2.y);
    return vec4(rgb, scalar);
}

vec4 hairGridDistant(vec3 point, vec3 normal, vec3 reflection,
                     vec4 defaultLighting, HairGridParameters p) {
    vec2 uv = fma(point.xz, p.distantUVScaleOffset.xy, p.distantUVScaleOffset.zw);
    float height = hairGridDistantHeight(uv) * p.distantHeightScale;
    bool above = point.y > p.distantMidHeight;
    float start = above ? p.distantMidHeight : 1.0;
    float end = above ? height : p.distantMidHeight;
    float h = hairGridSat(fma((point.y - start) / (end - start), 0.5, above ? 0.5 : 0.0));
    vec4 zs = fma(vec4(h), vec4(2.0), vec4(0.5, 3.5, 6.5, 9.5)) * (1.0 / 12.0);
    vec4 a = hairGridDistantSamples(vec3(uv, zs.x));
    vec4 b = hairGridDistantSamples(vec3(uv, zs.y));
    vec4 c = hairGridDistantSamples(vec3(uv, zs.z));
    vec4 d = hairGridDistantSamples(vec3(uv, zs.w));
    vec3 directionLuma = mix(b.xyz, a.xyz, greaterThanEqual(normal, vec3(0.0)));
    vec3 reflectionLuma = mix(b.xyz, a.xyz, greaterThanEqual(reflection, vec3(0.0)));
    vec2 xChroma = normal.x >= 0.0 ? c.xy : d.xy;
    vec2 zChroma = normal.z >= 0.0 ? c.zw : d.zw;
    vec2 yChroma = normal.y >= 0.0 ? vec2(a.w, b.w) : ((c.xy + d.xy) + c.zw + d.zw) * 0.25;
    vec3 n2 = normal * normal, r2 = reflection * reflection;
    float luma = fma(directionLuma.z, n2.z, directionLuma.x * n2.x + directionLuma.y * n2.y);
    float refl = fma(reflectionLuma.z, r2.z, reflectionLuma.x * r2.x + reflectionLuma.y * r2.y);
    vec2 chroma = fma(zChroma, vec2(n2.z), fma(yChroma, vec2(n2.y), xChroma * n2.x));
    chroma = fma(chroma, vec2(2.0), vec2(-1.0));
    chroma *= abs(chroma);
    luma *= luma;
    vec3 rgb = fma(vec3(chroma.y), vec3(0.621, -0.6474, 1.7046),
                   fma(vec3(luma), vec3(4.0), chroma.x * vec3(0.9563, -0.2721, -1.107)));
    vec3 scaled = rgb * p.distantIrradianceScale;
    refl = (refl * refl) * p.distantIrradianceScale;
    float blend = hairGridSat((point.y - height) * (1.0 / 16.0));
    return vec4(fma(vec3(blend), fma(-rgb, vec3(p.distantIrradianceScale), defaultLighting.xyz), scaled),
                fma(blend, fma(-refl, 4.0, defaultLighting.w), refl * 4.0));
}

HairGridLighting hairGridLighting(vec3 worldPoint, vec3 normal, vec3 reflection,
                                  HairGridParameters p) {
    vec3 point = worldPoint - 0.5;
    ivec3 cell = ivec3(floor(point));
    vec3 fraction = fract(point);
    vec3 eased = fma(fraction * fraction, fma(-fraction, vec3(2.0), vec3(3.0)), fraction);
    vec3 low = fma(-eased, vec3(0.5), vec3(1.0)), high = eased * 0.5;
    float weights[8];
    uvec4 records[8];
    float total = 0.0, fallback = 0.0;
    for (uint i = 0u; i < 8u; ++i) {
        ivec3 corner = ivec3(int(i & 1u), int((i >> 1u) & 1u), int(i >> 2u));
        ivec3 coordinate = cell + corner;
        uvec3 brick = uvec3(coordinate >> 4) & uvec3(63);
        uint word = hairGridLookup(brick.x | (brick.y << 6u) | (brick.z << 12u));
        uvec3 local = uvec3(coordinate) & uvec3(15);
        uint index = (word & 0xfffff000u) | local.x | (local.y << 4u) | (local.z << 8u);
        records[i] = hairGridRecord(index);
        uint occlAndScale = records[i].w;
        vec3 delta = fraction - vec3(corner);
        vec3 axisWeights = mix(low, high, notEqual(corner, ivec3(0)));
        float trilinear = (axisWeights.y * axisWeights.x) * axisWeights.z;
        vec3 plane = fma(vec3(uvec3(occlAndScale >> 26u, (occlAndScale >> 20u) & 63u, (occlAndScale >> 14u) & 63u)),
                         vec3(8.0 / 63.0), vec3(-4.0));
        float occlusion = hairGridSat(fma(float(occlAndScale & 63u), 16.0 / 63.0, dot(plane, delta)) - 7.0);
        float normalWeight = max(hairGridSat(dot(normal, -delta)), p.bleedReduction);
        float weight = max((occlusion * trilinear) * normalWeight, 0.000003814697265625);
        total += weight;
        fallback = fma(float(max(word & 1020u, occlAndScale & 960u)), weight, fallback);
        // Exactly the half-float exponent synthesis (bits & 0x3c00) + 0x1400.
        weights[i] = weight * unpackHalf2x16((occlAndScale & 0x3c00u) + 0x1400u).x;
    }
    float inverseTotal = 1.0 / total;
    for (int i = 0; i < 8; ++i) weights[i] *= inverseTotal;
    fallback *= inverseTotal;
    vec4 accumulated = fma(hairGridRadiance(records[0].xyz, normal, reflection), vec4(weights[0]),
                           hairGridRadiance(records[1].xyz, normal, reflection) * weights[1]);
    for (int i = 2; i < 8; ++i)
        accumulated = fma(hairGridRadiance(records[i].xyz, normal, reflection), vec4(weights[i]), accumulated);
    vec4 lighting = accumulated * (1.0 / 63.0);
    if (max(abs(point.x - p.cameraPosition.x), abs(point.z - p.cameraPosition.z)) > 512.0)
        fallback = max(fallback, 960.0);
    if (fallback > 0.0) {
        vec4 defaultLighting = vec4(hairGridDefault(normal, 5.0),
                                    dot(hairGridDefault(reflection, 5.0), vec3(0.25, 0.5, 0.25)));
        if (p.distantUVScaleOffset.x != 0.0)
            defaultLighting = hairGridDistant(point, normal, reflection, defaultLighting, p);
        fallback *= 1.0 / 960.0;
        lighting = fma(vec4(fallback), fma(-accumulated, vec4(1.0 / 63.0), defaultLighting), lighting);
    }
    HairGridLighting result;
    result.diffuse = max(lighting.xyz * p.intensity, p.ambientFill);
    result.reflection = lighting.w;
    result.fallbackWeight = fallback;
    return result;
}
