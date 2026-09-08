# Recovered fur filter integration

Status: running before TAA in the private UE5.8 validation fixture. Not yet connected by a production plugin view extension or included in a new preview archive.

Implemented:
- RecoveredFurDenoise.ush: translated three-gather strand filter, conservative half depth, depth/mask weights and tile gating.
- FurDenoise.usf / AddRecoveredFurDenoisePass: matching viewport inputs, native color-store truncation, explicit pre-exposure handling, row-vector world-to-view conversion and absolute pixel offset for phase. Non-fur pixels pass through.
- MaterialExpressionFurSurfaceOutput: decoded packed Normal/Strand custom outputs and the RecoveredFurSurface shader tag. New materials use the legacy translator; installed UE5.8 does not export the MIR emitter needed by a plugin.
- FurSurface.usf / AddFurSurfacePass: engine depth vertex entry for the existing vertex factory/WPO, identical material coverage clipping, RGBA32F normal+mask and strand+linear-depth MRTs. Both preserve decoded vectors and depth before native arithmetic; RGBA16F would add unwanted rounding. Read-only scene-depth equality excludes hidden samples. Uses AddSimpleMeshPass for GPU scene instances, not the older dynamic draw helper.
- FurActiveTiles.usf / AddFurActiveTilesPass: one active flag per 8x8 block.
- Private FurSurfaceReadback view extension: collects visible static and dynamic mesh batches, crops matching buffers, supplies the jittered projection/native vector conversion/frame phase, filters scene color, and copies the result back before post processing/TAA. Can run once for raw GPU readbacks or continuously for a bounded capture.

Verified evidence:
- Synthetic kernel (rerun successfully after final integration): seven GPU checks on 128x64 buffers (fur-denoise-kernel.json). The actual live captures additionally exercise the projection, exposure=1 and pixel-offset plumbing.
- Actual sheep and Ratchet: their recovered/fur-surface-live-*/validation.json reports. Valid normal/strand/depth values, unchanged non-fur pixels and alpha, many pixels changed beyond native color truncation alone.
- Sustained sheep under key/fill/rim: one settled pair per mode measured 4.0044 RGB8 MAE without the filter and 3.1640 with it. This is about 21% less variation in this pair, still above the 3.0 gate. Not a frame-locked comparison or native parity proof.

- Final Ratchet static pair: 1.0751 off -> 1.0031 on RGB8 MAE (passes the 3.0 gate). Its visual/native ear and motion parity are not established by this static test.
- Both final jobs exited cleanly below 4.7 GiB. Decoded vectors and linear depth remained float32; non-fur colors and alpha were unchanged.

Limits / remaining work:
1. The experimental MRT mask is binary for surviving masked samples. Native fractional mask composition remains to be traced/integrated.
2. Production scene registration, supported material selection/cooking, view lifetime, multi-view/viewport cases and performance need work. Current fixture supports one perspective view, PF_FloatRGBA color and single-sample depth; rejects oversized targets and stereo. It is not the shipped tool path.
3. Actual nonidentity camera conversion is exercised, but native fused rounding and non-unit pre-exposure remain unproven against captures. Do not claim bit-exact parity.
4. Ratchet ear silhouette, movement, scene-light/shadow and final dry quality still need their acceptance evidence. No generic blur or post-TAA smoothing was substituted.

Debug history: the first isolated live test exited with a missing Scene uniform buffer; explicit scene binding fixed it. Material permutations compile on first use; the bounded harness allows them to finish before rejecting an empty mesh pass. Fresh-material construction can log incomplete-graph warnings, so clean reload validation remains necessary.
