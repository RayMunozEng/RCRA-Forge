// R11G11B10_FLOAT conversion measured on the captured D3D12 Hair UAV.
// Apply at the lighting and denoise stores, before subsequent filtering.
// RGBA16F preview targets represent these values exactly while retaining
// untouched scene pixels and alpha outside the Hair pass.
vec3 hairStoreColor(vec3 color) {
    vec3 finiteColor = clamp(color, vec3(0.0), vec3(65024.0, 65024.0, 64512.0));
    vec3 normal = uintBitsToFloat(floatBitsToUint(finiteColor)
        & uvec3(0xfffe0000u, 0xfffe0000u, 0xfffc0000u));
    vec3 subnormal = floor(finiteColor * vec3(1048576.0, 1048576.0, 524288.0))
        * vec3(0.00000095367431640625, 0.00000095367431640625, 0.0000019073486328125);
    vec3 stored = mix(normal, subnormal, lessThan(finiteColor, vec3(0.00006103515625)));
    stored = mix(stored, color, equal(color, vec3(uintBitsToFloat(0x7f800000u))));
    return mix(stored, vec3(uintBitsToFloat(0x7fc00000u)), isnan(color));
}
