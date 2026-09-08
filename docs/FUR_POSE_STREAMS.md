# Fur pose-stream checkpoint — 2026-09-05

The production opaque and fur vertex shaders now consume attribute 5 as previous deformed position. GpuSubMesh supplies current position as the static default, and update_pose accepts current positions, current normals/tangents and optional explicit previous positions. The viewport exposes set_deformed_pose with a dictionary keyed by uploaded GPU-submesh index; each value is (positions, normals, tangents), in that submesh's vertex order. This API must be called on the UI thread after model upload.

Queued updates coalesce and are copied. Previous position refers to the last rendered pose, not an intermediate queued update. History settles after rendering, resets with temporal/camera/resource resets, and clears on model/LOD replacement. The producer must supply correctly skinned current normals and tangents. Native animation clip decoding and skeletal skinning are separate work; this is a deformed-stream integration, not a native animation player.

## Fresh evidence

- Five pose-history CPU tests and 23 affected viewport tests: 28 passed.
- Real offscreen GPU buffer test: static current/previous equality, separate deformed streams, attribute binding and stationary next-frame settling passed.
- Production fur vertex source against captured animated draw 24715: 93,150 checks, zero visibility mismatches; maximum previous-clip residual 8.344650268554688e-7. The comparison helper now uses the real previous-position input declaration instead of injecting it.
- Full bounded hidden viewport render and deferred-target verification passed. The static image is byte-identical to the pre-change control.
- Camera sweep: 23 increments of 0.5 degrees. Its endpoint and stationary control have identical camera and sample count (25). Mean absolute whole-image RGB-byte difference 0.28634, 95th percentile 2. No obvious trailing silhouette in endpoint visual inspection. This does not establish shimmer behavior throughout a sequence or all disocclusions.
- Re-reading saved connected native Hair denoise evidence confirms 11,215/11,215 exact RGB pixels. The new image shows both with identical diagnostic display mapping. This starts with captured native G-buffers; it is not a complete animated game-frame comparison.
- The recovered full-frame event-20572 TAA output is a menu screen. It validates generic temporal arithmetic but must not be presented as a fur appearance reference.

Evidence lives in outer artifacts/rcra-fur-continuation: pose-stream-gpu.json, fur-motion-comparison.json/.jpg, fur-native-pass-comparison.json/.jpg, fur-pose-integration.json, and the matching job report. New jobs used inactive desktops, time limits and 3 GiB memory caps; no game was launched.

## Remaining boundary

Core static fur is substantially implemented. Final native animated-frame visual parity remains unverified. Native clip/skin decoding, sequence-level shimmer/disocclusion checks and a common-frame end-to-end capture are needed to close that claim. Do not restart unrelated scene-manager reverse engineering under the fur task.
