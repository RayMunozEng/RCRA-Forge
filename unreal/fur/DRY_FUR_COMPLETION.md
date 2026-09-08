# Dry fur completion gate

User priority: finish plain dry fur before more wind/wetness work.
Status: INCOMPLETE. No full dry-fur release or native parity claim.

- Texture/controlled lighting: Ratchet and sheep Forge/UE comparisons exist; sheep sRGB correction accepted.
- Added scene lighting: key plus optional fill/rim implemented using recovered hair response. C++ build, SM5 compilation, eight actual API binding checks and Ratchet/sheep rendered contributions verified. Extras are unshadowed directional lights; this is not complete native scene lighting. New scene materials required for new inputs.
- Sheep rebuild discrepancy isolated: unchanged-frame MAE5.2219 versus rebuilt5.1779; material/light settings identical. Rebuild binding is correct. Strongly lit wool static temporal noise still exceeds the3RGB8 quality gate.
- Geometry/coverage: lower-ear contour remains unresolved. Official native photo-mode closeups now obtained and inspected. Pose/camera/lighting are not registered. Rejected count/spacing/background experiments must not be promoted.
- Skeletal following/velocity: existing controlled source-bone and opaque velocity checks pass; they do not establish full animated fur quality.
- Corrected dry rigid motion: both whole-character Ratchet and sheep15cm tests now completed. Ratchet newly uncovered mask191360 pixels: zero above8RGB8. Sheep mask76511 pixels:0..8 above8RGB8 across saved samples, settled zero. Capture cadence is not frame-locked and silhouette margin is excluded; this is not general no-ghosting or native motion parity.
- Authoring shell count: runtime-verified count correction delivered in0.9.1-preview. No new ZIP published for lighting yet.

Next: resolve bright-wool temporal noise and remaining ear/native visual acceptance; then complete dry release validation. All work stays dry. No native game launch, resource-cap increase, foreground takeover or changes to other applications.

Visual update: recovered/dry-lighting-20260907/comparison.html.
Native references: recovered/published-native-reference-20260907/comparison.html.
Motion: recovered/dry-motion-sheep-20260907/comparison.html.

Temporal schedule update: builder corrected32-frame coverage reset to160 joint period. Isolated coverage MAE2.47% to0.21%; separate sheep GPU same-lit pair5.22 to4.56RGB8, still above3 target. This is not a completed temporal/noise fix. See recovered/dry-cycle160-sheep/comparison.html.

Filter implementation update: recovered compute kernel and explicit RDG pass built; seven actual tiny-buffer GPU tests passed. Optional material surface outputs compile with both inputs connected (legacy translator;24 shader types). Live fur MRT producer and pre-TAA scene-color connection still missing, so current character images remain unfiltered. See FUR_FILTER_INTEGRATION.md.


Live filter update: the private UE fixture now runs the recovered filter before TAA on actual sheep surface buffers. Non-fur pixels are unchanged. One sustained bright-light pair improved from 4.1456 to 3.1744 RGB8 MAE, still above the 3.0 gate. Production plugin integration and dry parity remain incomplete. See FUR_FILTER_INTEGRATION.md.

Final live-filter checkpoint (supersedes intermediate numeric results above): full-precision surface MRTs validated for both characters. Sheep 4.0044 -> 3.1640 RGB8 MAE (fails 3.0); Ratchet 1.0751 -> 1.0031 (passes static gate only). All seven kernel checks passed again. Review recovered/dry-live-filter-20260907/comparison.html. Production integration and full dry parity remain incomplete.
