# Captured HairDenoise comparison

Status: 2026-09-03. The shared denoise kernel matches **11,215 of 11,215**
stored pixels exactly in the captured pass. Native float RGB and all four
accumulation sums also match exactly. The ordinary preview uses this shared kernel.
Complete scene lighting and temporal reconstruction are still unfinished.

## Native oracle

Capture: `riftapart-checkpoint_capture_5.rdc`, compute event **17551**, 524
workgroups of 32 threads. The work queue addresses 16,768 pixels, of which
11,215 have a positive input mask. Shader `CS_HairDenoise` is 10,036 bytes,
SHA256 `513269680588fe3fbc67587c61f8bb19d29caea8d16cd83e0d378e83467e57b2`.
This belongs to the same engine frame as Hair lighting event 17544, not the
later fur raster draw 24715.

Private evidence lives in the outer workspace's
`artifacts/rcra-fur-continuation/capture-tools/`.
`export_hair_denoise.py` verifies the shader and captures pre-dispatch inputs
plus the original output. `replay_hair_denoise.py` checks every exported hash
and executes every queue lane with the shared GLSL kernel.

| Binding | Input |
| --- | --- |
| t1 | Packed normal/material, RGBA16_UINT |
| t7 | 524 active work-queue entries |
| t120 | Hair lighting color, R11G11B10_FLOAT |
| t121 | Conservative linear depth, R16_FLOAT |
| t122 | Packed strand/transmission, R32_UINT |
| t123 | Fractional mask, R8_UNORM |
| t124 | 8x8 tile flags, R8_UINT |
| u0 | Denoised color, R11G11B10_FLOAT |

The original output is resource 3529, while color input is resource 3558.
The comparison supplies the actual fractional mask and tile flags. Output
conversion uses the separately verified D3D12 positive R11G11B10 UAV
round-toward-zero behavior, rather than rounding to nearest.

## Findings and preview integration

`core/hair_denoise.glsl` shares ray construction and the three masked gathers.
Include `core/hair_surface.glsl` before it for the shared pixel/depth view-position
reconstruction. After this extraction, `hair-denoise-replay-shared-surface/`
still matches every stored RGB, float RGB and accumulation sum exactly.
It uses decoded packed vectors without another normalization, perspective
interpolation of reciprocal ray depth, and native depth rejection. Sample
coordinates advance only when the tile's Hair flag is present.

The half-depth input is strictly above the source R32_FLOAT value. The next
representable half after truncating to half matches **122,142/122,142** masked
pixels exactly, including values already representable as half. This is a
measured input-conversion rule; the conversion producer has not been located
in the captured resource-usage list. Report: `denoise-depth-rounding.json`.

Tile occupancy derived from packed Hair materials matches the native Hair
bit for all 32,400 tiles, with 262 occupied tiles. The preview derives occupancy
from its explicit fur mask, converts its depth using the measured half rule, and
adapts texture orientation/gather order to the shared kernel. The preview's
lighting mask is still its isolated renderer input; connecting the complete
Hair lighting output is required for full pipeline parity.
Opaque meshes now supply linear depth with a zero fur mask. Positive depth alone
does not make a pixel eligible for denoise. The focused GPU check preserves all
16 opaque test pixels and all 4,080 constant-color fur values exactly.

All 250 tests pass. `viewport-denoise-exact.json` / `.png` records a successful
wet Ratchet head render with wind, 16x/8x texture filtering, native BC6U and
the corrected shared denoiser. Median synchronous time is **4.1612 ms** at 800x800 logical
pixels on the RTX 5060 Ti. The image was visually inspected.

## Resolved arithmetic boundary

Historical reports `hair-denoise-replay-baseline/` and `hair-denoise-replay-shared/`
showed one differing pixel at **(817,953)**. Its sample start and step
coordinates match native float instrumentation exactly. Native versus GLSL
unquantized RGB is:

| | Native | GLSL |
| --- | --- | --- |
| R | 0.4062499701976776 | 0.4062500298023224 |
| G | 0.2382812350988388 | 0.2382812649011612 |
| B | 0.044921875 | 0.0449218787252903 |

The native store rounds R/G below the boundary. Native float instrumentation
quantizes back to all **11,215** original stored pixels exactly. An unchanged
reassembled shader also reproduces every original output byte.

Isolating the final resolve with native sums gives **11,215/11,215 exact
reciprocals and RGB results**. The discrepancy is upstream: at the remaining
pixel, all three color sums agree exactly, but native weight sum is
3.982802629470825 while GLSL has 3.982802391052246. Generic summation-order,
explicit fused depth weighting, and reciprocal-expression controls did not
remove it; those experimental variants are private and are not applied to
the shared kernel.

Original-pixel per-gather instrumentation isolated the first weight:
native 0.9828025698661804 versus baseline GLSL 0.9828025102615356. The other
two gathers each add exactly one. The depth-weight multiply/add must stay fused.
An ordinary GLSL `fma` alone was insufficient on the capture GPU; assigning its
result to a `precise` value preserves the fused operation. That qualifier also
affects upstream expressions, so the ray projection now explicitly preserves
its fused operations as well. The final shared kernel has **11,215/11,215 exact
float RGB values, stored RGB values, and color/weight sums**. No per-pixel fix,
output bias, relaxed tolerance or changed oracle is involved.

Evidence: `hair-denoise-replay-shared-exact/report.json` and `comparison.npz`,
`hair-denoise-replay-explicit-ray/`, `d3d-denoise-pixel-weights-17551/`, and
`denoise-one-pixel/`. The earlier spare-row weight probe is invalid: decoded
values violated weight-range and initial-sum invariants. Its report is marked
invalid and it was replaced by the validated original-pixel trace.

The stored-output result is specific to this captured pass on the RTX 5060 Ti.
Tiny ray UV/step differences remain in a few lanes but do not change any gathered
result here. Full-scene lighting and temporal reconstruction remain separate work.

Scripts: `assemble_denoise_float_probe.py`, `verify_d3d_denoise_float.py`,
`compare_denoise_float.py`, and the corresponding resolve/weight variants.
All substitutions are replay-memory only and are removed after each variant.
No color bias or boundary-specific correction is used.
