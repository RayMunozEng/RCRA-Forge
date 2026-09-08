// Hair direct-light lobes. GLSL 4.30+, or GL_ARB_gpu_shader5 in GLSL 3.30.
// The normal/light/view dots refer to the view-oriented strand frame.
float hairLobeNormalizationSquared(float square) {
#ifdef GL_ARB_gpu_shader5
    // Reuse the rounded square. Fusing 1-alpha*alpha changes a captured
    // R11G11B10 boundary; cancellation to a constant also loses retail behavior.
    precise float remainder = clamp(1.0 - square, 0.0, 1.0);
    precise float denominator = max(1.0 - remainder, 0.000001);
#else
    float remainder = clamp(1.0 - square, 0.0, 1.0);
    float denominator = max(1.0 - remainder, 0.000001);
#endif
    return square / denominator;
}

float hairLobeDistribution(vec3 halfDots, vec2 alpha,
                           float normalLight, float normalView) {
    float tangentTerm = halfDots.y * halfDots.y / (alpha.x * alpha.x);
    float sideTerm = halfDots.z * halfDots.z / (alpha.y * alpha.y);
#ifdef GL_ARB_gpu_shader5
    precise float ellipsoid = fma(halfDots.x, halfDots.x, tangentTerm) + sideTerm;
    precise float average = fma(min(alpha.x, alpha.y), 0.75,
                                max(alpha.x, alpha.y) * 0.25);
    precise float masking = fma(average, uintBitsToFloat(0x3eb504f0u),
                                uintBitsToFloat(0x3eb504f0u));
    precise float maskingSquare = masking * masking;
    precise float remainder = fma(-masking, masking, 1.0);
    precise float lightMask = fma(normalLight, remainder, maskingSquare);
    precise float viewMask = fma(normalView, remainder, maskingSquare);
    precise float denominator = (alpha.x * alpha.y) * (ellipsoid * ellipsoid);
    denominator = (denominator * viewMask) * lightMask;
    precise float square = average * average;
    precise float response = (0.25 / max(denominator, 0.00001)) * normalLight;
#else
    float ellipsoid = tangentTerm + halfDots.x * halfDots.x + sideTerm;
    float average = min(alpha.x, alpha.y) * 0.75 + max(alpha.x, alpha.y) * 0.25;
    float masking = average * uintBitsToFloat(0x3eb504f0u) + uintBitsToFloat(0x3eb504f0u);
    float maskingSquare = masking * masking;
    float remainder = 1.0 - maskingSquare;
    float lightMask = normalLight * remainder + maskingSquare;
    float viewMask = normalView * remainder + maskingSquare;
    float denominator = ((alpha.x * alpha.y) * (ellipsoid * ellipsoid) * viewMask) * lightMask;
    float square = average * average;
    float response = (0.25 / max(denominator, 0.00001)) * normalLight;
#endif
    return response * hairLobeNormalizationSquared(square);
}

vec3 hairFresnelFromFactor(vec3 f0, float factor) {
#ifdef GL_ARB_gpu_shader5
    precise vec3 sum = f0 + factor;
    precise vec3 fresnel = fma(vec3(-factor), f0, sum);
    return fresnel;
#else
    return (f0 + factor) - factor * f0;
#endif
}

vec3 hairFresnel(vec3 f0, float viewHalf) {
    float grazing = 1.0 - viewHalf;
    float square = grazing * grazing;
    return hairFresnelFromFactor(f0, (square * square) * grazing);
}
