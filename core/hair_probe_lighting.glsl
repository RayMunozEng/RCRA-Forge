// Recovered Hair DXBC hash 5ff73b6b2aca9640cf18cd78b88ba3c0.
// Include in GLSL 4.30+, or enable GL_ARB_gpu_shader5 for fma in GLSL 3.30.
// The caller supplies actual records, eligibility, cube resources and light-grid
// inputs. These callbacks deliberately do not infer runtime bindings/residency.
vec4 hairProbeRow(int recordIndex, int row);
bool hairProbeEligible(int recordIndex);
vec3 hairProbeLocal(float cubeIndex, vec3 direction, float mip);
vec3 hairProbeDefault(vec3 direction, float mip);

float hairProbeSat(float value) {
    return isnan(value) ? 0.0 : clamp(value, 0.0, 1.0);
}
vec2 hairProbeSat(vec2 value) {
    return vec2(hairProbeSat(value.x), hairProbeSat(value.y));
}
vec3 hairProbeSat(vec3 value) {
    return vec3(hairProbeSat(value.x), hairProbeSat(value.y), hairProbeSat(value.z));
}
float hairProbeMin(float a, float b) {
    return isnan(a) ? b : (isnan(b) ? a : min(a, b));
}

vec3 hairProbeBasisPoint(int index, vec3 direction) {
    vec4 x = hairProbeRow(index, 0), y = hairProbeRow(index, 1);
    vec3 z = (x.yzx * y.zxy - x.zxy * y.yzx) * y.w;
    return vec3(dot(direction, x.xyz), dot(direction, y.xyz), dot(direction, z));
}

float hairProbeSpatialWeight(int index, vec3 worldPoint) {
    vec4 originFlags = hairProbeRow(index, 2);
    vec3 local = hairProbeBasisPoint(index, worldPoint - originFlags.xyz);
    vec3 inverseExtent = hairProbeRow(index, 3).xyz;
    vec3 positive = hairProbeRow(index, 4).xyz;
    vec3 negative = hairProbeRow(index, 5).xyz;
    vec3 edge;
    if ((floatBitsToUint(originFlags.w) & 1u) != 0u) {
        vec2 fp = 1.0 / positive.xz, fn = 1.0 / negative.xz;
        vec2 inner = fma(-fp, vec2(0.5), vec2(1.0));
        inner = fma(-fn, vec2(0.5), inner);
        vec2 center = (fn + inner) - 1.0;
        vec2 q = local.xz * inverseExtent.xz;
        vec2 falloff = mix(fn, fp, greaterThan(q, center));
        vec2 radial = fma(local.xz, inverseExtent.xz, -center) / inner;
        float radius = sqrt(dot(radial, radial));
        vec2 direction = radial * (1.0 / radius);
        vec2 selected = falloff * (direction * direction);
        float distance = (radius - 1.0) / (selected.x + selected.y);
        vec2 radialEdge = hairProbeSat(distance * (abs(direction) * inner));
        float py = hairProbeSat(fma(fma(local.y, inverseExtent.y, -1.0), positive.y, 1.0));
        float ny = hairProbeSat(fma(fma(-local.y, inverseExtent.y, -1.0), negative.y, 1.0));
        edge = vec3(radialEdge.x, max(py, ny), radialEdge.y);
    } else {
        vec3 ep = hairProbeSat(fma(fma(local, inverseExtent, vec3(-1.0)), positive, vec3(1.0)));
        vec3 en = hairProbeSat(fma(fma(-local, inverseExtent, vec3(-1.0)), negative, vec3(1.0)));
        edge = max(ep, en);
    }
    float weight = max(1.0 - dot(edge, edge), 0.0);
    return weight * weight;
}

vec3 hairProbeParallax(int index, vec3 worldPoint, vec3 worldRay, float offsetScale) {
    vec3 local = hairProbeBasisPoint(index, worldPoint - hairProbeRow(index, 2).xyz);
    vec3 ray = hairProbeBasisPoint(index, worldRay);
    vec3 negative = vec3(hairProbeRow(index, 4).w, hairProbeRow(index, 5).w,
                         hairProbeRow(index, 6).w);
    vec3 planes = mix(hairProbeRow(index, 6).xyz, negative, lessThan(ray, vec3(0.0)));
    vec3 times = (planes - local) / ray;
    float distance = hairProbeMin(times.z, hairProbeMin(times.y, times.x));
    return fma(worldRay, vec3(distance), (worldPoint - hairProbeRow(index, 7).xyz) * offsetScale);
}

struct HairProbeLighting {
    vec3 specular;
    vec3 diffuse;
    float coarseLuminance;
    float visibility;
    float defaultCoverage;
    float diffuseCoverage;
};

HairProbeLighting hairProbeLighting(int recordCount, vec3 worldPoint,
                                    vec3 reflection, vec3 shadingNormal,
                                    float averageGloss, vec3 lightGridDiffuse,
                                    float lightGridReflection, float environmentIntensity) {
    float gloss = max(averageGloss, 0.0);
    float t = min(gloss * 1.5, 1.0);
    float offsetScale = fma(-t, 2.0, 3.0) * (t * t);
    float mip = fma(gloss, -5.0, 5.0);
    float remaining = 1.0, total = 0.0, diffuseTotal = 0.0, coarse = 0.0;
    vec3 specular = vec3(0.0), diffuse = vec3(0.0);
    // Buffer order corresponds to increasing bits across the lookup words.
    for (int index = 0; index < recordCount && remaining > 0.0; ++index) {
        if (!hairProbeEligible(index)) continue;
        float alpha = hairProbeSpatialWeight(index, worldPoint) * hairProbeRow(index, 0).w;
        if (!(alpha > 0.0)) continue;
        float cubeIndex = hairProbeRow(index, 3).w;
        float contribution = remaining * alpha;
        vec3 color = hairProbeLocal(cubeIndex, hairProbeParallax(index, worldPoint, reflection, offsetScale), mip);
        specular = fma(color, vec3(contribution), specular);
        vec3 coarseColor = hairProbeLocal(cubeIndex, reflection, 5.0);
        coarse = fma(dot(coarseColor, vec3(0.25, 0.5, 0.25)), contribution, coarse);
        if ((floatBitsToUint(hairProbeRow(index, 2).w) & 2u) != 0u) {
            vec3 diffuseColor = hairProbeLocal(cubeIndex, hairProbeParallax(index, worldPoint, shadingNormal, 1.0), 5.0);
            diffuse = fma(diffuseColor, vec3(contribution), diffuse);
            diffuseTotal += contribution;
        }
        total += contribution;
        remaining -= alpha;
    }
    float inverseTotal = 1.0 / max(total, 0.00001);
    vec3 normalizedSpecular = specular * inverseTotal;
    float normalizedCoarse = coarse * inverseTotal;
    if (remaining > 0.0) {
        normalizedSpecular = fma(vec3(remaining), hairProbeDefault(reflection, mip) - normalizedSpecular, normalizedSpecular);
        float defaultCoarse = dot(hairProbeDefault(reflection, 5.0), vec3(0.25, 0.5, 0.25));
        normalizedCoarse = fma(remaining, defaultCoarse - normalizedCoarse, normalizedCoarse);
    }
    float strength = min(1.5 - gloss, 1.0);
    float ratio = hairProbeSat((lightGridReflection * 0.5) / max(normalizedCoarse, 0.000001));
    float visibility = fma(strength * strength, fma(ratio, 2.0, -1.0), 1.0);
    HairProbeLighting result;
    result.specular = (normalizedSpecular * visibility) * environmentIntensity;
    result.diffuse = lightGridDiffuse;
    if (diffuseTotal > 0.0) {
        vec3 localDiffuse = diffuse * ((1.0 / diffuseTotal) * environmentIntensity);
        result.diffuse = fma(vec3(hairProbeSat(diffuseTotal)), localDiffuse - lightGridDiffuse, lightGridDiffuse);
    }
    result.coarseLuminance = normalizedCoarse;
    result.visibility = visibility;
    result.defaultCoverage = max(remaining, 0.0);
    result.diffuseCoverage = hairProbeSat(diffuseTotal);
    return result;
}
