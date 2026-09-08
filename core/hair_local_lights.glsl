// Recovered Hair local-light lookup, geometry, volume, gobo and shadow stages.
float hairContactVisibility(vec2 pixel, float depth, vec3 normal,
    vec3 worldLight, vec3 viewLight, vec2 inverseDimensions,
    vec4 screenToViewA, vec2 screenToViewB, vec4 viewToScreen,
    vec2 dimensions, vec2 noiseAnglePhase, float materialRadius);

struct HairLocalLight {
    vec3 axisX; float radius;
    vec3 axisY; float sourceLength;
    vec3 axisZ; float pushForward;
    vec3 position; float inverseAttenuationRadius;
    vec3 color; float specularIntensity;
    vec2 cone; float cutOnDepth; float cutOffDepth;
    uint zBinMinMax; uint flags; uint modAndGobo; uint clipVolumes;
    uint shadowMaps; uint shadowVolumes;
    float reciprocalConeSine; float padding;
};

struct HairLocalGeometry {
    vec3 direction;
    vec3 lobeWeights;
    vec3 color;
    float attenuation;
    float distanceFactor;
    float areaMetric;
};

struct HairLocalAccumulation {
    vec3 diffuse;
    vec3 back;
    vec3 specular;
};

HairLocalLight hairLocalLoadLight(int index) {
    int row = index * 8;
    vec4 a = hairLocalFloatRow(uHairLocalLightRows, row + 0);
    vec4 b = hairLocalFloatRow(uHairLocalLightRows, row + 1);
    vec4 c = hairLocalFloatRow(uHairLocalLightRows, row + 2);
    vec4 d = hairLocalFloatRow(uHairLocalLightRows, row + 3);
    vec4 e = hairLocalFloatRow(uHairLocalLightRows, row + 4);
    vec4 f = hairLocalFloatRow(uHairLocalLightRows, row + 5);
    uvec4 g = texelFetch(uHairLocalLightRows, row + 6);
    uvec4 h = texelFetch(uHairLocalLightRows, row + 7);
    return HairLocalLight(
        a.xyz, a.w, b.xyz, b.w, c.xyz, c.w, d.xyz, d.w,
        e.xyz, e.w, f.xy, f.z, f.w, g.x, g.y, g.z, g.w,
        h.x, h.y, uintBitsToFloat(h.z), uintBitsToFloat(h.w));
}

vec3 hairLocalTransformVolumePoint(int index, vec3 point) {
    vec4 a = hairLocalVolumeRow(index, 0);
    vec4 b = hairLocalVolumeRow(index, 1);
    vec4 c = hairLocalVolumeRow(index, 2);
    vec4 d = hairLocalVolumeRow(index, 3);
    return point.x * a.xyz + point.y * b.xyz + point.z * c.xyz + d.xyz;
}

bool hairLocalClipRejected(HairLocalLight light, vec3 worldPoint) {
    uint count = light.clipVolumes >> 16u;
    uint first = light.clipVolumes & 0xffffu;
    bool rejected = false;
    for (uint offset = 0u; offset < count; ++offset) {
        int index = int(first + offset);
        vec3 local = hairLocalTransformVolumePoint(index, worldPoint);
        bool outside = max(max(abs(local.x), abs(local.y)), abs(local.z)) >= 1.0;
        float fade = hairLocalVolumeRow(index, 5).w;
        if (offset != 0u && fade == 0.0) rejected = rejected && outside;
        else rejected = rejected || outside;
    }
    return rejected;
}

vec3 hairLocalColorVolume(HairLocalLight light, vec3 worldPoint) {
    int index = int(light.modAndGobo & 0xffffu);
    vec3 local = worldPoint.x * light.axisX + worldPoint.y * light.axisY
        + worldPoint.z * light.axisZ + light.position;
    vec4 extentFade = hairLocalVolumeRow(index, 5);
    vec3 negative = hairLocalVolumeRow(index, 6).xyz;
    vec3 positive = hairLocalVolumeRow(index, 7).xyz;
    float influence;
    if ((light.flags & 4u) != 0u) {
        vec3 scaled = extentFade.xyz * local;
        vec3 direction = normalize(scaled);
        float edge = dot(max(negative * direction, positive * direction),
                         abs(direction));
        influence = clamp(edge * clamp(1.0 - dot(scaled, direction), 0.0, 1.0),
                          0.0, 1.0);
    } else {
        vec3 fromNegative = negative * (extentFade.xyz + local);
        vec3 fromPositive = positive * (extentFade.xyz - local);
        influence = clamp(min(min(fromNegative.x, fromPositive.x),
                              min(fromNegative.y, fromPositive.y)), 0.0, 1.0);
        influence = min(influence, clamp(min(fromNegative.z, fromPositive.z),
                                         0.0, 1.0));
    }
    influence *= extentFade.w;
    return fma(vec3(influence), light.color - vec3(1.0), vec3(1.0));
}

float hairLocalFastAcos(float value) {
    float magnitude = min(abs(value), 1.0);
    float angle = (1.5707963705062866 - 0.1565829962491989 * magnitude)
        * sqrt(1.0 - magnitude);
    return value < 0.0 ? 3.1415927410125732 - angle : angle;
}

float hairLocalFastAtan2(float numerator, float denominator) {
    float first = abs(numerator), second = abs(denominator);
    float ratio = min(first, second) / max(first, second);
    float squared = ratio * ratio;
    float angle = ((0.08729290217161179 * squared - 0.30189499258995056)
                   * squared + 1.0) * ratio;
    if (first > second) angle = 1.5707963705062866 - angle;
    if (denominator < 0.0) angle = 3.1415927410125732 - angle;
    return numerator < 0.0 ? -angle : angle;
}

vec3 hairLocalGoboColor(HairLocalLight light, vec3 worldPoint,
                        vec3 originalDirection) {
    uint rawIndex = light.modAndGobo >> 16u;
    if (rawIndex == 0xffffu || !uHairHasGoboAtlas) return light.color;
    int index = int(rawIndex);
    vec4 atlas = hairLocalVolumeRow(index, 4);
    vec2 uv;
    float edge = 1.0;
    bool monochrome = false;
    if ((light.flags & 33u) != 0u) {
        vec3 source = -originalDirection;
        vec3 local = vec3(dot(source, light.axisX), dot(source, light.axisY),
                          dot(source, light.axisZ));
        if ((light.flags & 32u) != 0u) {
            float latitude = hairLocalFastAcos(local.z) * 0.31830987334251404;
            float longitude = fract(hairLocalFastAtan2(local.x, local.y)
                                    * 0.15915493667125702 + 0.5);
            uv = atlas.w < 0.0 ? vec2(longitude, latitude)
                               : vec2(latitude, longitude);
            monochrome = true;
        } else {
            uv = vec2(
                fract(hairLocalFastAtan2(local.z, local.x)
                      * 0.15915493667125702 + 0.5),
                hairLocalFastAcos(local.y) * 0.31830987334251404);
        }
    } else {
        vec4 a = hairLocalVolumeRow(index, 0);
        vec4 b = hairLocalVolumeRow(index, 1);
        vec4 c = hairLocalVolumeRow(index, 2);
        vec4 d = hairLocalVolumeRow(index, 3);
        vec4 projected = worldPoint.x * a + worldPoint.y * b
            + worldPoint.z * c + d;
        uv = clamp(vec2(1.0) - projected.xy / projected.w, 0.0, 1.0);
        vec2 centered = abs(2.0 * uv - vec2(1.0));
        edge = clamp(20.0 - 20.25 * max(centered.x, centered.y), 0.0, 1.0);
    }
    vec3 sampleColor = textureLod(uHairGoboAtlas,
        atlas.xy + uv * atlas.zw, 0.0).rgb;
    if (monochrome) sampleColor = sampleColor.rrr;
    return light.color * sampleColor * edge;
}

float hairLocalShadowMaps(HairLocalLight light, vec3 worldPoint,
                          uint transmissionCode, vec2 noiseDirection) {
    uint first = light.shadowMaps & 0xffffu;
    uint count = light.shadowMaps >> 16u;
    if (count == 0u || !uHairHasKeyShadow) return 1.0;
    float visibility = 1.0;
    float radius = fma(float(transmissionCode),
        1.537893695058301e-05, 0.000244140625);
    float absorption = fma(-float(transmissionCode),
        0.06299212574958801, 4.0);
    absorption = fma(absorption, absorption, 1.0);
    for (uint offset = 0u; offset < count; ++offset) {
        int index = int(first + offset);
        vec4 a = hairLocalVolumeRow(index, 0);
        vec4 b = hairLocalVolumeRow(index, 1);
        vec4 c = hairLocalVolumeRow(index, 2);
        vec4 d = hairLocalVolumeRow(index, 3);
        vec4 atlas = hairLocalVolumeRow(index, 4);
        vec2 uv, clampMinimum, clampMaximum;
        float depth, inverseDepthScale;
        if ((light.flags & 1u) == 0u) {
            vec4 projected = worldPoint.x * a + worldPoint.y * b
                + worldPoint.z * c + d;
            vec2 unit = clamp(projected.xy / projected.w, 0.0, 1.0);
            uv = fma(unit, atlas.zw, atlas.xy);
            depth = projected.z;
            inverseDepthScale = inversesqrt(dot(vec3(a.z, b.z, c.z),
                                                vec3(a.z, b.z, c.z)));
            clampMinimum = atlas.xy + vec2(0.00006103515625);
            clampMaximum = atlas.xy + atlas.zw - vec2(0.00006103515625);
        } else {
            vec3 delta = worldPoint - light.position;
            vec3 absolute = abs(delta);
            vec4 face;
            float major, minorA, minorB;
            if (absolute.x >= absolute.y && absolute.x >= absolute.z) {
                face = a; major = delta.x; minorA = delta.z; minorB = delta.y;
            } else if (absolute.y > absolute.z) {
                face = b; major = delta.y; minorA = delta.x; minorB = delta.z;
            } else {
                face = c; major = delta.z; minorA = delta.y; minorB = delta.x;
            }
            vec2 base = major < 0.0 ? face.xy : face.zw;
            vec2 integer = floor(base);
            vec2 atlasOffset = integer * 0.125;
            float atlasScale = base.x - integer.x;
            float signedMinorB = major < 0.0 ? -minorB : minorB;
            float majorAbsolute = abs(major);
            vec2 unit = clamp(vec2(
                (majorAbsolute + minorA) * 0.5 / majorAbsolute,
                (majorAbsolute - signedMinorB) * 0.5 / majorAbsolute),
                0.0, 1.0);
            uv = fma(unit, vec2(atlasScale), atlasOffset);
            depth = fma(majorAbsolute, d.x, d.y);
            inverseDepthScale = 1.0 / d.x;
            clampMinimum = atlasOffset + vec2(0.00006103515625);
            clampMaximum = atlasOffset + vec2(atlasScale - 0.00006103515625);
        }
        float depthBias = radius * inverseDepthScale;
        float localVisibility;
        if (depth < depthBias) {
            localVisibility = hairKeyCompare(vec3(uv, depth));
        } else {
            vec2 direction = noiseDirection;
            float distanceSquared = 0.125;
            float sum = 0.0;
            for (int tap = 0; tap < 4; ++tap) {
                vec2 tapUv = fma(radius * direction,
                    vec2(sqrt(distanceSquared)), uv);
                tapUv = clamp(tapUv, clampMinimum, clampMaximum);
                float separation = (depth - hairKeyDepth(tapUv))
                    * inverseDepthScale;
                separation = max(fma(-distanceSquared, depthBias,
                                     separation), 0.0);
                sum += exp2(absorption * separation * -50.494327545166016);
                direction = vec2(
                    fma(direction.x, -0.7373688220977783,
                        -(direction.y * 0.6754903793334961)),
                    dot(direction, vec2(0.6754903793334961,
                                        -0.7373688220977783)));
                distanceSquared += 0.25;
            }
            localVisibility = sum * 0.25;
        }
        visibility = offset == 0u ? localVisibility
                                  : min(visibility, localVisibility);
    }
    return visibility;
}

vec3 hairLocalShadowVolumes(HairLocalLight light, vec3 worldPoint, vec3 color) {
    if (!uHairHasGoboAtlas || (uHairSceneFlags & 128u) == 0u) return color;
    uint first = light.shadowVolumes & 0xffffu;
    uint count = light.shadowVolumes >> 16u;
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
            vec4 last = hairLocalVolumeRow(index, 7);
            float fade = clamp(1.0 - last.w * fifthDistance, 0.0, 1.0);
            fade = clamp(fade * fade + hairLocalVolumeRow(index, 5).w,
                         0.0, 1.0);
            color *= fma(vec3(fade), vec3(1.0) - sampleColor, sampleColor);
        }
    }
    return color;
}

HairLocalGeometry hairLocalGeometry(HairLocalLight light, vec3 worldPoint,
                                    vec3 normal, HairLobeFrame primary,
                                    HairLobeFrame secondary,
                                    vec3 viewDirection) {
    vec3 delta = light.position - worldPoint;
    float originalDistanceSquared = dot(delta, delta);
    float originalInverseDistance = inversesqrt(originalDistanceSquared);
    vec3 originalDirection = delta * originalInverseDistance;
    float cone = clamp(light.cone.y - dot(originalDirection, light.axisZ)
                       * light.cone.x, 0.0, 1.0);
    float radial = clamp(light.inverseAttenuationRadius
                         * light.inverseAttenuationRadius
                         * originalDistanceSquared, 0.0, 1.0);
    radial = 1.0 - radial * radial;
    float depth = dot(-delta, light.axisZ);
    float depthWeight = clamp((depth - light.cutOnDepth) * 2.0, 0.0, 1.0)
        * clamp((light.cutOffDepth - depth) * 2.0, 0.0, 1.0);
    float attenuation = depthWeight * (cone * radial) * (cone * radial);

    if (light.pushForward != 0.0) delta += light.axisZ * light.pushForward;
    float distanceSquared = dot(delta, delta);
    float inverseDistance = inversesqrt(distanceSquared);
    vec3 direction = delta * inverseDistance;
    vec3 triadDots = clamp(vec3(dot(normal, direction),
                                dot(primary.normal, direction),
                                dot(secondary.normal, direction)), 0.0, 1.0);
    float finiteRadius = clamp(light.inverseAttenuationRadius * 1048576.0,
                               0.0, 1.0);
    float distanceFactor = 1.0 / (finiteRadius * distanceSquared + 1.0);
    float areaMetric = 0.0;

    if (light.radius != 0.0) {
        float radius = light.radius;
        float sourceLength = light.sourceLength;
        if (radius < 0.0) {
            attenuation *= abs(dot(direction, light.axisZ));
            radius = abs(radius);
            sourceLength = max(sourceLength - radius * 1.7724499702453613, 0.0);
        }
        float radiusOverDistance = radius * inverseDistance;
        float disk = clamp(0.5 * radiusOverDistance * radiusOverDistance,
                           0.0, 1.0);
        float diskScale = 1.0 / ((1.0 + disk) * (1.0 + disk));
        triadDots = clamp((triadDots + vec3(disk)) * diskScale, 0.0, 1.0);
        areaMetric = radiusOverDistance;
        if (sourceLength > 0.0) {
            vec3 halfSegment = light.axisX * (sourceLength * 0.5);
            vec3 negative = delta - halfSegment;
            vec3 positive = delta + halfSegment;
            float negativeInverse = inversesqrt(dot(negative, negative));
            float positiveInverse = inversesqrt(dot(positive, positive));
            float inverseProduct = negativeInverse * positiveInverse;
            float endpointCosine = 0.5 + 0.5 * inverseProduct
                * dot(negative, positive);
            float segmentFactor = inverseProduct / (endpointCosine + inverseProduct);
            vec3 negativeDots = vec3(dot(normal, negative),
                dot(primary.normal, negative), dot(secondary.normal, negative));
            vec3 positiveDots = vec3(dot(normal, positive),
                dot(primary.normal, positive), dot(secondary.normal, positive));
            triadDots = (clamp((negativeDots * negativeInverse + vec3(disk))
                               * diskScale, 0.0, 1.0) + triadDots
                         + clamp((positiveDots * positiveInverse + vec3(disk))
                                 * diskScale, 0.0, 1.0)) / 3.0;

            vec3 incident = -viewDirection;
            vec3 reflected = incident - 2.0 * dot(incident, normal) * normal;
            float projected = dot(reflected, halfSegment);
            vec3 segmentVector = reflected * projected - halfSegment;
            float amount = clamp(dot(negative, segmentVector)
                                 / (sourceLength * sourceLength
                                    - projected * projected),
                                 0.0, 1.0);
            vec3 closest = negative + amount * halfSegment;
            inverseDistance = inversesqrt(dot(closest, closest));
            direction = closest * inverseDistance;
            float circle = sqrt(max(1.0 - endpointCosine * endpointCosine, 0.0));
            areaMetric = sqrt(max((circle + radiusOverDistance)
                                  * radiusOverDistance, 0.0));
            distanceFactor = segmentFactor;
        }
        float radiusAtDistance = min(inverseDistance * radius, 1.0);
        float boost = 1.0 + clamp(2.5 - 1.0 / radiusAtDistance,
                                  0.0, 1.0) * 0.15000000596046448;
        distanceFactor *= boost;
    }
    return HairLocalGeometry(direction, triadDots, light.color, attenuation,
                             distanceFactor, areaMetric);
}

float hairLocalDistribution(HairLobeFrame frame, vec3 tangent,
                            vec3 lightDirection, vec3 viewDirection,
                            vec2 alpha, float normalLight) {
    vec3 halfVector = normalize(lightDirection + viewDirection);
    vec3 halfDots = vec3(dot(frame.normal, halfVector),
                         dot(tangent, halfVector), dot(frame.side, halfVector));
    float normalView = min(abs(dot(frame.normal, viewDirection)) + 0.00001, 1.0);
    return hairLobeDistribution(halfDots, alpha,
                                clamp(normalLight, 0.0, 1.0), normalView);
}

void hairApplyLocalLights(vec2 pixel, float viewDepth,
                          vec3 worldPoint, vec3 normal,
                          vec3 primaryTangent, vec3 secondaryTangent,
                          HairLobeFrame primary, HairLobeFrame secondary,
                          HairMaterialResponse material, vec3 viewDirection,
                          uint transmissionCode, vec2 noiseAnglePhase,
                          inout HairLocalAccumulation result) {
    if (!uHairHasLocalLights) return;
    ivec2 tile = ivec2(pixel) >> 3;
    ivec3 lookupSize = textureSize(uHairLocalLightLookup, 0);
    if (any(lessThan(tile, ivec2(0))) || any(greaterThanEqual(tile, lookupSize.xy)))
        return;
    float normalView = dot(normal, viewDirection);
    for (int word = 0; word < uHairLocalLookupWords; ++word) {
        uint bits = texelFetch(uHairLocalLightLookup, ivec3(tile, word), 0).r;
        while (bits != 0u) {
            int bit = findLSB(bits);
            bits ^= 1u << uint(bit);
            int index = word * 32 + bit;
            if (index >= uHairLocalRecordCount) continue;
            HairLocalLight light = hairLocalLoadLight(index);
            if (hairLocalClipRejected(light, worldPoint)) continue;
            if ((light.flags & 2u) != 0u) {
                vec3 multiplier = hairLocalColorVolume(light, worldPoint);
                result.diffuse *= multiplier;
                result.specular *= multiplier;
                continue;
            }
            HairLocalGeometry geometry = hairLocalGeometry(
                light, worldPoint, normal, primary, secondary, viewDirection);
            vec3 originalDirection = normalize(light.position - worldPoint);
            geometry.color = hairLocalGoboColor(
                light, worldPoint, originalDirection);
            geometry.color = hairLocalShadowVolumes(
                light, worldPoint, geometry.color);
            float visibility = hairLocalShadowMaps(
                light, worldPoint, transmissionCode,
                vec2(cos(noiseAnglePhase.x), sin(noiseAnglePhase.x)));
            if (visibility <= 0.0001) continue;
            if (uFurContactEnabled && (uHairSceneFlags & 2u) != 0u) {
                vec3 viewLight = vec3(
                    dot(uViewToWorld[0], geometry.direction),
                    dot(uViewToWorld[1], geometry.direction),
                    dot(uViewToWorld[2], geometry.direction));
                visibility = min(visibility, hairContactVisibility(
                    pixel, viewDepth, normal, geometry.direction, viewLight,
                    1.0 / uViewportSize, uScreenToView, vec2(1.0, 0.0),
                    uHairViewToScreen, uViewportSize, noiseAnglePhase, 0.0));
            }
            vec3 radiance = geometry.color
                * (geometry.attenuation * geometry.distanceFactor * visibility);
            float broaden = min(0.25, geometry.areaMetric * 0.1);
            float primaryDistribution = hairLocalDistribution(
                primary, primaryTangent, geometry.direction, viewDirection,
                clamp(material.primaryAlpha + vec2(broaden), 0.0, 1.0),
                geometry.lobeWeights.y);
            float secondaryDistribution = hairLocalDistribution(
                secondary, secondaryTangent, geometry.direction, viewDirection,
                clamp(material.secondaryAlpha + vec2(broaden), 0.0, 1.0),
                geometry.lobeWeights.z);
            vec3 halfVector = normalize(geometry.direction + viewDirection);
            float viewHalf = dot(viewDirection, halfVector);
            vec3 primaryFresnel = hairFresnel(material.primaryF0, viewHalf);
            vec3 secondaryFresnel = hairFresnel(material.secondaryF0, viewHalf);
            float diffuseResponse = hairDiffuseResponse(
                geometry.lobeWeights.x, material.transmission);
            result.diffuse += radiance * (vec3(diffuseResponse)
                + secondaryFresnel * secondaryDistribution);
            result.specular += primaryFresnel * radiance * primaryDistribution;
            result.back += radiance * hairTransmissionResponse(
                dot(-viewDirection, hairWrappedLight(normal, geometry.direction)),
                geometry.lobeWeights.x, normalView);
        }
    }
}
