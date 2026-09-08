// Native PS_FurShellGBufferDeferred packing. Specular is the square-root
// encoded response; gloss is linear. Output channels are RGBA16_UINT.
uvec4 furPackGBuffer(vec3 normal, float gloss, float specular, uint renderFlags) {
    float scale = inversesqrt(abs(normal.z) * 8.0 + 8.0);
    uvec2 xy = uvec2(normal.xy * 5791.20458984375 * scale + 2048.0);
    uint flags = ((renderFlags << 6u) & 4096u)
        | ((renderFlags >> 13u) & 16384u) | 8192u;
    if (normal.z < 0.0) flags |= 32768u;
    flags ^= 4096u;
    uint specularByte = uint(clamp(specular, 0.0, 1.0) * 255.0 + 0.5);
    uint glossByte = uint(clamp(gloss, 0.0, 1.0) * 255.0 + 0.5);
    return uvec4(xy.x | 24576u, xy.y | flags,
                 (specularByte << 8u) | specularByte,
                 (specularByte << 8u) | glossByte);
}

uint furPackExtra(vec3 strand, float transmittance) {
    float scale = inversesqrt(abs(strand.z) * 8.0 + 8.0);
    uvec2 xy = uvec2(strand.xy * 722.6631469726562 * scale + 256.0);
    uint transmission = uint(clamp(transmittance * 0.5, 0.0, 1.0) * 127.0 + 0.5);
    return xy.x | (xy.y << 9u) | (uint(strand.z < 0.0) << 18u)
        | (transmission << 19u);
}

vec3 furUnpackNormal(uvec4 encoded) {
    vec2 codes = vec2(encoded.xy & uvec2(4095u));
#ifdef GL_ARB_gpu_shader5
    vec2 xy = fma(codes, vec2(uintBitsToFloat(0x3a351044u)),
                  vec2(uintBitsToFloat(0xbfb504f3u)));
#else
    vec2 xy = codes * uintBitsToFloat(0x3a351044u) + uintBitsToFloat(0xbfb504f3u);
#endif
    float radiusSquared = dot(xy, xy);
    float z = 1.0 - radiusSquared * 0.5;
    return vec3(xy * sqrt(1.0 - radiusSquared * 0.25),
                (encoded.y & 32768u) != 0u ? -z : z);
}

vec3 furUnpackStrand(uint encoded) {
    vec2 codes = vec2(encoded & 511u, (encoded >> 9u) & 511u);
#ifdef GL_ARB_gpu_shader5
    vec2 xy = fma(codes, vec2(uintBitsToFloat(0x3bb55fa3u)),
                  vec2(uintBitsToFloat(0xbfb504f3u)));
#else
    vec2 xy = codes * uintBitsToFloat(0x3bb55fa3u) + uintBitsToFloat(0xbfb504f3u);
#endif
    float radiusSquared = dot(xy, xy);
    float z = 1.0 - radiusSquared * 0.5;
    return vec3(xy * sqrt(1.0 - radiusSquared * 0.25),
                (encoded & 262144u) != 0u ? -z : z);
}
