// Shared color/history math recovered from CS_TemporalAaApply
// (shader hash 4e1b2693fbe9696f3f1eb1d6ac577a01; captured DXIL container
// SHA-256 b892667bfa835a95a7f58c78b30b35d45e5784b48d750bf6543bf557d9956e0f).

const float HAIR_TEMPORAL_MIN_LUMA = 0.000001;

float hairTemporalLuma(vec3 rgb) {
    float halfGreen = rgb.g * 0.5;
    float quarterRedBlue = (rgb.r + rgb.b) * 0.25;
    return max(quarterRedBlue + halfGreen, HAIR_TEMPORAL_MIN_LUMA);
}

vec3 hairTemporalEncode(vec3 rgb, float hdrScale) {
    float halfGreen = rgb.g * 0.5;
    float quarterRedBlue = (rgb.r + rgb.b) * 0.25;
    float luma = max(quarterRedBlue + halfGreen, HAIR_TEMPORAL_MIN_LUMA);
    return vec3(
        (1.0 / (1.0 + hdrScale * luma)) * luma,
        (halfGreen - quarterRedBlue) / luma,
        0.5 * (rgb.r - rgb.b) / luma
    );
}

vec3 hairTemporalRoundCurrentChroma(vec3 encoded) {
    // The native apply stores current-sample chroma in f16 group memory while
    // retaining compressed luma as f32. History encoding stays full precision.
    vec2 rounded = unpackHalf2x16(packHalf2x16(encoded.yz));
    return vec3(encoded.x, rounded);
}

vec3 hairTemporalPremultiply(vec3 encoded) {
    return vec3(encoded.x, encoded.x * encoded.y, encoded.x * encoded.z);
}

vec3 hairTemporalDecodePremultiplied(vec3 value) {
    return vec3(
        value.x - value.y + value.z,
        value.x + value.y,
        value.x - value.y - value.z
    );
}

vec3 hairTemporalDecode(vec3 encoded) {
    return hairTemporalDecodePremultiplied(hairTemporalPremultiply(encoded));
}

float hairTemporalCatmullWeight(float distance) {
    distance = abs(distance);
    float squared = distance * distance;
    float cubed = squared * distance;
    if (distance < 1.0) {
        return 1.0 - 2.5 * squared + 1.5 * cubed;
    }
    return 2.0 - 4.0 * distance + 2.5 * squared - 0.5 * cubed;
}

void hairTemporalFilterWeights(vec2 offsetPixels, out float weights[9]) {
    float gaussian[9];
    float catmull[9];
    float gaussianSum = 0.0;
    float catmullSum = 0.0;
    int index = 0;
    for (int y = -1; y <= 1; ++y) {
        float dy = float(y) - offsetPixels.y;
        for (int x = -1; x <= 1; ++x) {
            float dx = float(x) - offsetPixels.x;
            gaussian[index] = exp(-2.29 * (dx * dx + dy * dy));
            catmull[index] = hairTemporalCatmullWeight(dx)
                * hairTemporalCatmullWeight(dy);
            gaussianSum += gaussian[index];
            catmullSum += catmull[index];
            ++index;
        }
    }
    for (int i = 0; i < 9; ++i) {
        float normalizedGaussian = gaussian[i] / gaussianSum;
        float normalizedCatmull = catmull[i] / catmullSum;
        weights[i] = mix(normalizedGaussian, normalizedCatmull, 0.8);
    }
}

vec3 hairTemporalHistoryCatmullRom(
    sampler2D historyTexture,
    vec2 historyPixel,
    vec2 inverseDimensions
) {
    vec2 centered = historyPixel - 0.5;
    vec2 base = floor(centered) + 0.5;
    vec2 fraction = historyPixel - base;
    vec2 f2 = fraction * fraction;
    vec2 f3 = f2 * fraction;

    vec2 w0 = f2 - 0.5 * f3 - 0.5 * fraction;
    vec2 w3 = 0.5 * fraction * (f2 - fraction);
    vec2 w1 = 1.0 - 2.5 * f2 + 1.5 * f3;
    vec2 w12 = 1.0 - w0 - w3;
    vec2 baseUv = base * inverseDimensions;
    vec2 centerUv = (base + 1.0) * inverseDimensions
        - inverseDimensions * (w1 / w12);
    float centerWeight = 1.0
        - w12.x * w0.y
        - w12.x * w3.y
        - w12.y * w0.x
        - w12.y * w3.x;

    vec3 result = textureLod(historyTexture, centerUv, 0.0).rgb * centerWeight;
    result += textureLod(
        historyTexture,
        vec2(centerUv.x, baseUv.y) + vec2(0.0, -1.0) * inverseDimensions,
        0.0
    ).rgb * (w12.x * w0.y);
    result += textureLod(
        historyTexture,
        vec2(baseUv.x, centerUv.y) + vec2(-1.0, 0.0) * inverseDimensions,
        0.0
    ).rgb * (w12.y * w0.x);
    result += textureLod(
        historyTexture,
        vec2(baseUv.x, centerUv.y) + vec2(2.0, 0.0) * inverseDimensions,
        0.0
    ).rgb * (w12.y * w3.x);
    result += textureLod(
        historyTexture,
        vec2(centerUv.x, baseUv.y) + vec2(0.0, 2.0) * inverseDimensions,
        0.0
    ).rgb * (w12.x * w3.y);
    return max(result, vec3(HAIR_TEMPORAL_MIN_LUMA));
}

vec3 hairTemporalUndoHdrCompression(vec3 rgb, float hdrScale) {
    float denominator = 1.0 - hdrScale * dot(rgb, vec3(0.25, 0.5, 0.25));
    return max(rgb / denominator, vec3(0.0));
}
