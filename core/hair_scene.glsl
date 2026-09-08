// Full-view resource callbacks for the shared native grid/probe kernels.
uniform samplerCubeArray uHairLocalCubes;
uniform samplerBuffer uHairProbeRows;
uniform usampler2DArray uHairProbeLookup;
uniform usamplerBuffer uHairGridLookup;
uniform usamplerBuffer uHairGridRecords;
uniform sampler2D uHairDistantHeight;
uniform sampler3D uHairDistantSamples;
uniform vec3 uHairGridCamera, uHairAmbientFill, uHairDistantConstants;
uniform vec3 uHairSceneKeyColor;
uniform uint uHairSceneFlags;
uniform bool uFurContactEnabled;
uniform vec4 uHairViewToScreen;
uniform vec4 uHairDistantUV;
uniform float uHairIntensity, uHairBleedReduction;
uniform int uHairProbeCount, uHairLookupWords;
uniform bool uHairHasKeyShadow;
uniform sampler2D uHairShadowAtlas;
uniform sampler2DShadow uHairShadowCompare;
uniform vec4 uHairSceneConstants[56];
uniform bool uHairHasHistory;
uniform sampler2D uHairReflectionHistory, uHairReflectionVelocity;
uniform mat3x2 uHairHistoryWorldToClip;
uniform bool uHairHasLocalLights, uHairHasGoboAtlas;
uniform bool uHairHasCloudShadow;
uniform bool uHairHasLightVolumes;
uniform int uHairLocalLookupWords, uHairLocalRecordCount;
uniform usampler2DArray uHairLocalLightLookup;
uniform usamplerBuffer uHairLocalLightRows, uHairLocalVolumeRows;
uniform sampler2D uHairGoboAtlas;
uniform sampler2D uHairCloudShadow;
ivec2 hairSceneTile;

vec4 hairLocalFloatRow(usamplerBuffer rows, int index) {
    return uintBitsToFloat(texelFetch(rows, index));
}
vec4 hairLocalVolumeRow(int index, int row) {
    return hairLocalFloatRow(uHairLocalVolumeRows, index * 8 + row);
}

vec2 hairHistoryVelocity(ivec2 pixel) {
    if (any(lessThan(pixel, ivec2(0))) || any(greaterThanEqual(pixel, textureSize(uHairReflectionVelocity, 0)))) return vec2(0.0);
    return texelFetch(uHairReflectionVelocity, pixel, 0).rg;
}
vec3 hairHistorySample(vec2 uv) { return textureLod(uHairReflectionHistory, uv, 0.0).rgb; }

vec4 hairKeyConstant(int row) { return uHairSceneConstants[row]; }
float hairKeyDepth(vec2 uv) { return textureLod(uHairShadowAtlas, uv, 0.0).r; }
float hairKeyCompare(vec3 uvDepth) { return textureLod(uHairShadowCompare, uvDepth, 0.0); }

float hairSceneKeyVisibility(vec3 relative, uint strand, vec2 noiseAnglePhase) {
    if (!uHairHasKeyShadow) return 1.0;
    return hairKeyShadowVisibility(relative, (strand >> 19u) & 127u, noiseAnglePhase);
}

uint hairGridLookup(uint i) { return texelFetch(uHairGridLookup, int(i)).r; }
uvec4 hairGridRecord(uint i) { return texelFetch(uHairGridRecords, int(i)); }
vec3 hairGridDefault(vec3 d, float mip) { return textureLod(uFurEnvironment, d, mip).rgb; }
float hairGridDistantHeight(vec2 uv) { return textureLod(uHairDistantHeight, uv, 0.0).r; }
vec4 hairGridDistantSamples(vec3 uvw) { return textureLod(uHairDistantSamples, uvw, 0.0); }
vec4 hairProbeRow(int i, int row) { return texelFetch(uHairProbeRows, i * 8 + row); }
bool hairProbeEligible(int i) {
    int word = i >> 5;
    if (word >= uHairLookupWords) return false;
    ivec3 size = textureSize(uHairProbeLookup, 0);
    if (any(lessThan(hairSceneTile, ivec2(0))) || any(greaterThanEqual(hairSceneTile, size.xy))) return false;
    return (texelFetch(uHairProbeLookup, ivec3(hairSceneTile, word), 0).r & (1u << uint(i & 31))) != 0u;
}
vec3 hairProbeLocal(float index, vec3 d, float mip) { return textureLod(uHairLocalCubes, vec4(d, index), mip).rgb; }
vec3 hairProbeDefault(vec3 d, float mip) { return textureLod(uFurEnvironment, d, mip).rgb; }

HairProbeLighting hairSceneIndirect(vec3 worldPoint, vec3 normal,
                                    HairEnvironmentFrame environment, vec2 pixel) {
    hairSceneTile = ivec2(pixel) >> 3;
    HairGridParameters p;
    p.cameraPosition = uHairGridCamera;
    p.bleedReduction = uHairBleedReduction;
    p.ambientFill = uHairAmbientFill;
    p.intensity = uHairIntensity;
    p.distantUVScaleOffset = uHairDistantUV;
    p.distantIrradianceScale = uHairDistantConstants.x;
    p.distantMidHeight = uHairDistantConstants.y;
    p.distantHeightScale = uHairDistantConstants.z;
    HairGridLighting grid = hairGridLighting(worldPoint, normal, environment.reflection, p);
    return hairProbeLighting(uHairProbeCount, worldPoint, environment.reflection,
        environment.normal, environment.averageGloss, grid.diffuse, grid.reflection, uHairIntensity);
}
