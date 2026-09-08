// Native anisotropic environment sample frame. Include hair_frame.glsl first.
struct HairEnvironmentFrame {
    vec3 normal;
    vec3 reflection;
    float blend;
    float averageGloss;
};

HairEnvironmentFrame hairEnvironmentFrame(vec3 normal, vec3 strand, vec3 view,
        HairLobeFrame primaryFrame, vec2 primaryAlpha, vec2 gloss, float angle) {
    HairEnvironmentFrame frame;
    vec3 axis = primaryAlpha.x >= primaryAlpha.y ? primaryFrame.side : strand;
    vec3 perpendicular = hairFrameCross(axis, view);
    vec3 positive = perpendicular.yzx * axis.zxy;
    vec3 negative = perpendicular.zxy * axis.yzx;
    vec3 difference = (-normal - negative) + positive;
    float blend = clamp(((1.0 - dot(normal, strand)) * 1.5)
                         * max(primaryAlpha.x, primaryAlpha.y), 0.0, 1.0);
    float sine = sin(angle), cosine = cos(angle);
    float sineCube = (sine * sine) * sine;
    float cosineCube = (cosine * cosine) * cosine;
    float sumGloss = gloss.x + gloss.y;
#ifdef GL_ARB_gpu_shader5
    precise vec3 base = fma(vec3(blend), difference, normal);
    precise vec3 target = fma(primaryAlpha.x * strand, vec3(sineCube), primaryFrame.normal);
    target = fma(primaryAlpha.y * primaryFrame.side, vec3(cosineCube), target);
    precise float weight = fma(sumGloss, 0.25, 0.5);
    precise vec3 direction = fma(base - target, vec3(weight), target);
#else
    vec3 base = blend * difference + normal;
    vec3 target = primaryFrame.normal + primaryAlpha.x * strand * sineCube;
    target += primaryAlpha.y * primaryFrame.side * cosineCube;
    float weight = sumGloss * 0.25 + 0.5;
    vec3 direction = (base - target) * weight + target;
#endif
    frame.normal = direction * inversesqrt(dot(direction, direction));
    float twiceView = dot(frame.normal, view) * 2.0;
#ifdef GL_ARB_gpu_shader5
    precise vec3 reflection = fma(frame.normal, vec3(twiceView), -view);
    frame.reflection = reflection;
#else
    frame.reflection = frame.normal * twiceView - view;
#endif
    frame.blend = blend;
    frame.averageGloss = sumGloss * 0.5;
    return frame;
}
