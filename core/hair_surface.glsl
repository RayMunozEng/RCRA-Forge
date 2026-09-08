// Hair surface preparation. Inputs use native top-left pixel coordinates,
// linear view depth and decoded G-buffer vectors (without renormalizing them).
// Include in GLSL 4.30+, or enable GL_ARB_gpu_shader5 for GLSL 3.30.

vec3 hairViewPosition(vec2 pixel, float depth, vec2 inverseDimensions,
                      vec4 screenToViewA, vec2 screenToViewB) {
    vec2 uv = (pixel + 0.5) * inverseDimensions;
#ifdef GL_ARB_gpu_shader5
    precise vec2 screen = fma(uv, screenToViewA.xy, screenToViewA.zw);
    precise float scale = fma(screenToViewB.x, depth, screenToViewB.y);
#else
    vec2 screen = uv * screenToViewA.xy + screenToViewA.zw;
    float scale = screenToViewB.x * depth + screenToViewB.y;
#endif
    return vec3(screen * scale, depth);
}

vec3 hairRelativeWorldPosition(vec3 viewPosition, mat3 viewToWorld) {
#ifdef GL_ARB_gpu_shader5
    precise vec3 relative = fma(vec3(viewPosition.y), viewToWorld[1],
                                viewPosition.x * viewToWorld[0]);
    relative = fma(vec3(viewPosition.z), viewToWorld[2], relative);
#else
    vec3 relative = viewPosition.x * viewToWorld[0]
        + viewPosition.y * viewToWorld[1];
    relative += viewPosition.z * viewToWorld[2];
#endif
    return relative;
}

vec3 hairViewDirection(vec3 relativeWorldPosition) {
    vec3 toEye = -relativeWorldPosition;
    return toEye * inversesqrt(dot(toEye, toEye));
}

