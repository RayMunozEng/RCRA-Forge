# Recovered fur filter integration

Status: the recovered pass is connected before TAA by an opt-in production
plugin view extension and remains available in the private UE5.8 validation
fixture. It is not included in a new preview archive.

Implemented:
- RecoveredFurDenoise.ush: translated three-gather strand filter, conservative half depth, depth/mask weights and tile gating.
- FurDenoise.usf / AddRecoveredFurDenoisePass: matching viewport inputs, native color-store truncation, explicit pre-exposure handling, row-vector world-to-view conversion and absolute pixel offset for phase. Non-fur pixels pass through.
- MaterialExpressionFurSurfaceOutput: decoded packed Normal/Strand custom outputs and the RecoveredFurSurface shader tag. New materials use the legacy translator; installed UE5.8 does not export the MIR emitter needed by a plugin.
- FurSurface.usf / AddFurSurfacePass: engine depth vertex entry for the existing vertex factory/WPO, identical material coverage clipping, RGBA32F normal+mask and strand+linear-depth MRTs. Both preserve decoded vectors and depth before native arithmetic; RGBA16F would add unwanted rounding. Read-only scene-depth equality excludes hidden samples. Uses AddSimpleMeshPass for GPU scene instances, not the older dynamic draw helper.
- FurActiveTiles.usf / AddFurActiveTilesPass: one active flag per 8x8 block.
- Private FurSurfaceReadback view extension: collects visible static and dynamic mesh batches, crops matching buffers, supplies the jittered projection/native vector conversion/frame phase, filters scene color, and copies the result back before post processing/TAA. Can run once for raw GPU readbacks or continuously for a bounded capture.
- Production `FFurDenoiseViewExtension`: performs the same tagged-material
  surface collection, per-view crop, recovered filter and scene-color copy-back
  before post processing/TAA. It is registered with the runtime plugin and
  enabled explicitly with `r.FurAuthoring.Denoise 1`; unsupported projection,
  stereo, multisample, format and size cases remain no-op instead of falling
  back to an unrelated blur.
- `UFurDenoiseLibrary` exposes Blueprint-callable enable and status functions;
  extension creation is deferred from the shader-mapping phase until
  `OnPostEngineInit`, then released during module shutdown.
- `capture_fur_surface_production.py` provides a bounded live A/B path that
  toggles the production cvar while leaving the private continuous filter off.
  `run_check.py` now resolves the repository-owned private-desktop runner and
  accepts/detects the local UE 5.8 installation instead of requiring the old
  `F:` workspace layout.

Verified evidence:
- The production extension builds in UE 5.8 and its post-engine-init lifecycle
  passed `validate_production_filter_registration.py`: registered, initially
  disabled, enable observed, disable observed and initial state restored. The
  private NullRHI job exited 0 at 1.112 GiB peak.
- `capture_synthetic_production_filter.py` regenerated the exact recovered
  696,468-byte layer array (SHA-256
  `c495993561a2a7cd8a608bd465f7e77898bf958873c9cd65ad342537a928215f`),
  built a repository-owned 32-shell tagged sphere, and captured two TAA frames
  with the production extension off and two on. A render-thread marker proves
  the production pre-TAA pass executed for one tagged batch at 1017x554. The
  private job exited 0 at 4.312 GiB peak. The verifier passed: 101,805 subject
  pixels, 89,253 off-to-on pixels changed, off-pair MAE 1.926 RGB8 and on-pair
  MAE 1.951 RGB8. This is integration evidence only; the synthetic pair did not
  improve temporal variation and makes no quality or retail-parity claim.
- Synthetic kernel (rerun successfully after final integration): seven GPU checks on 128x64 buffers (fur-denoise-kernel.json). The actual live captures additionally exercise the projection, exposure=1 and pixel-offset plumbing.
- Actual sheep and Ratchet: their recovered/fur-surface-live-*/validation.json reports. Valid normal/strand/depth values, unchanged non-fur pixels and alpha, many pixels changed beyond native color truncation alone.
- Sustained sheep under key/fill/rim: one settled pair per mode measured 4.0044 RGB8 MAE without the filter and 3.1640 with it. This is about 21% less variation in this pair, still above the 3.0 gate. Not a frame-locked comparison or native parity proof.

- Final Ratchet static pair: 1.0751 off -> 1.0031 on RGB8 MAE (passes the 3.0 gate). Its visual/native ear and motion parity are not established by this static test.
- Both final jobs exited cleanly below 4.7 GiB. Decoded vectors and linear depth remained float32; non-fur colors and alpha were unchanged.

Limits / remaining work:
1. The experimental MRT mask is binary for surviving masked samples. Native fractional mask composition remains to be traced/integrated.
2. The production extension uses the proven shader-tag material selection and
   plugin-base shader mapping, and its lifetime follows module startup/shutdown.
   One perspective editor viewport has production-path execution evidence.
   Multi-viewport operation, cooking and performance still require validation.
   PF_FloatRGBA color and single-sample depth are required; oversized targets
   and stereo are rejected.
3. Actual nonidentity camera conversion is exercised, but native fused rounding and non-unit pre-exposure remain unproven against captures. Do not claim bit-exact parity.
4. Ratchet ear silhouette, movement, scene-light/shadow and final dry quality still need their acceptance evidence. No generic blur or post-TAA smoothing was substituted.

Debug history: the first isolated live test exited with a missing Scene uniform buffer; explicit scene binding fixed it. Material permutations compile on first use; the bounded harness allows them to finish before rejecting an empty mesh pass. Fresh-material construction can log incomplete-graph warnings, so clean reload validation remains necessary. On the receiving computer, unrelated processes left less than 8 GiB free RAM; the final synthetic capture constrained shader compilation to one worker and retained a 6 GiB aggregate job cap instead of terminating user processes or raising the cap unsafely.
