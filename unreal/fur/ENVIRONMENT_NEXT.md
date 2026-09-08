# Environment lighting integration notes — 2026-09-06

Current UE material emits recovered direct-light response only. Shadowed fur
therefore receives no environment illumination. Do not compensate by changing
fur albedo, weakening occlusion, or claiming a constant fill matches the game.

Recovered source available in external/RCRA-Forge/core:

- hair_environment_frame.glsl: anisotropic environment normal and reflection
  using the primary lobe frame, strand direction, both roughness axes and noise.
- hair_preview_lighting.glsl, evaluatePreviewHairLighting: environment specular
  sampled at 5 - saturate(averageGloss) * 5, diffuse at mip 5, then a BRDF LUT
  at (abs(dot(environment.normal, view)), averageGloss). The asset-preview
  multiplier is 0.6; it is not a universal UE skylight intensity conversion.
- hair_scene.glsl / hair_probe_lighting.glsl: the fuller game path adds spatial
  grid/probe selection and visibility. A single supplied cube cannot claim this.

Next implementation boundary:

1. Translate the recovered environment frame with the existing HLSL generator
   and preserve its source hash. Use the same decoded normal/strand/material
   response already used by RFSceneDirect.
2. Add optional author-supplied environment cube and BRDF LUT inputs to a new
   versioned material. Missing inputs must preserve current direct-only output.
   Keep cube orientation explicit: the recovered direct frame uses UE xzy.
3. Use controlled owned cube fixtures to check all six axis orientations,
   intensity zero/scale, roughness mip response, and BRDF coordinates. The
   recovered game LUT remains a private validation input unless distribution
   rights are established; no extracted game assets go into the plugin.
4. Match Forge/UE cameras and environment inputs for Ratchet and sheep, compare
   dry/wet and shadowed views, and show actual image pairs. Ensure environment
   illumination is not multiplied by the directional shadow map.
5. Treat Unreal Skylight/Lumen/probe access as a separate renderer integration.
   Inspect UE 5.8 source interfaces before selecting that implementation.

This file is an implementation plan grounded in local source inspection, not
an assertion that environment lighting has been implemented or tested in UE.


2026-09-06 implementation update: the optional cube/LUT material path is now
implemented. Recovered environment-frame source is translated by
export_reference_lighting.py and included in its SHA256 provenance. Ratchet and
sheep response controls passed (see recovered/environment-validation.json).
The validation studio cube uses constant face colors and controlled mip blends;
it is not a real captured/convolved scene. No matched Forge image-parity claim
is made by these tests. Automatic scene lighting remains open.

After the texture sampling gate, the next work is a user-facing environment
setup workflow and then a matched Forge comparison using identical cube inputs,
camera, exposure and wetness. A plugin-owned BRDF/prefilter generation workflow
would avoid requiring users to source compatible data manually. That needs a
clearly documented response model; do not silently ship the private game LUT.
