// View-oriented Hair frames, measured against native DXIL intermediates.
// The geometric normal and strand inputs are decoded G-buffer vectors.
vec3 hairFrameCross(vec3 a, vec3 b) {
#ifdef GL_ARB_gpu_shader5
    precise vec3 value = fma(-a.zxy, b.yzx, a.yzx * b.zxy);
    return value;
#else
    return cross(a, b);
#endif
}

struct HairLobeFrame {
    vec3 normal;
    vec3 side;
};

HairLobeFrame hairLobeFrame(vec3 strand, vec3 normal, vec3 viewDirection) {
    float strandNormal = dot(strand, normal);
    vec3 perpendicular = hairFrameCross(strand, normal);
    float sine = sqrt(dot(perpendicular.yzx, perpendicular.yzx));
#ifdef GL_ARB_gpu_shader5
    precise vec3 seed = fma(viewDirection, vec3(sine), normal * strandNormal);
#else
    vec3 seed = viewDirection * sine + normal * strandNormal;
#endif
    HairLobeFrame frame;
    vec3 side = hairFrameCross(seed, strand);
    frame.side = side * inversesqrt(dot(side, side));
    vec3 front = hairFrameCross(strand, frame.side);
    frame.normal = front * inversesqrt(dot(front, front));
    return frame;
}

vec3 hairSecondaryStrand(vec3 strand, vec3 normal, uint shiftCode) {
#ifdef GL_ARB_gpu_shader5
    float shift = fma(float(shiftCode), uintBitsToFloat(0x3b1c09c2u), 0.075);
    precise vec3 tangent = fma(vec3(shift), -normal - strand, strand);
#else
    float shift = float(shiftCode) * uintBitsToFloat(0x3b1c09c2u) + 0.075;
    vec3 tangent = strand + shift * (-normal - strand);
#endif
    return tangent * inversesqrt(dot(tangent, tangent));
}
