# Fur motion-vector production path

Status: 2026-09-03. The perspective deferred viewport now allocates, writes and
consumes the native fifth fur material target: two half-float, pixel-space
motion components in `GL_RG16F`. The shader chain compiles offline. A live
viewport comparison of this newly connected path is deferred until game/GPU
work resumes.

## Native evidence

The reference draw is event 24715 in `riftapart-checkpoint_capture_5.rdc`.
`VS_ModelFurShellGBufferDeferredWind` has SHA256
`76b4457d347b2fea846bd2021bbb75e9d8c49c00871201505b2217c1316b6828`;
`PS_FurShellGBufferDeferred` has SHA256
`778f1fc603c882e6186cbec5359933979af342930619e0b8a9747662149193f3`.
The captured output-merger state identifies target 4 as `R16G16_FLOAT`.

The recovered vertex shader computes previous-frame shell position rather than
reusing current clip position. It reads the previous skinned position buffer
when the mesh is skinned, evaluates the wind field at shader time minus delta
time, applies the previous dynamic-object transform and previous camera matrix,
and exports that clip position as `TEXCOORD5`. The pixel shader converts it to
pixel-space motion with inverse viewport size, the near-plane clamp and viewport
size. These producers and the exact pixel formula are visible in the saved DXIL
assembly and constant/resource reflection under
`capture-tools/captured-fur-draws/`.

The recovered VS signature also fixes the post-transform layout. Its 96-byte
record is six `float4` registers in order: `SV_Position`, `TEXCOORD0`,
`TEXCOORD1`, `TEXCOORD2`, `TEXCOORD3`, and previous clip in `TEXCOORD5`.
The earlier private vertex comparison filled the sixth register with preview
visibility diagnostics and therefore never tested previous clip. The offline
helper has been corrected to use all six native registers and keeps its local
diagnostics in a seventh output register. It now requires an explicit
`--allow-gpu` switch and has not been run during the offline-only phase.

The saved `CS_AccAlphaDisocclusion` assembly (`ResourceId-4776`, SHA256
`3325938addce04cf33c1d7d66bc6b22d8c7bd539715ec870a090707d04aee605`)
provides an independent consumer-side sign check. It loads the full-resolution
velocity, subtracts both components from the current pixel, scales that result
to UV, and samples temporal history there. Thus the target is
current-minus-previous in top-left pixel space.

`replay_fur_raster.py` passes captured `TEXCOORD5` through the shared
`furMotionVector` helper. With native upper-left rasterization it matches all
five material targets and hardware depth exactly: 6,308 dry pixels, then 6,206,
6,070 and 5,642 surviving pixels at wetness 0.25, 0.5 and 1.0. Reports are
`fur-raster-replay-wet-shared-{0,0.25,0.5,1}/report.json` in the outer private
evidence directory.

## Offline previous-frame audit

`capture-tools/analyze_fur_position_history.py` reads only saved binary files;
it creates no graphics context. It verifies both source hashes, decodes the
current and previous signed-16-bit skin positions with the captured
`0.000244140625` scale, and checks the previous object/camera transform against
base-shell `TEXCOORD5`.

All 18,630 unique vertices referenced by event 24715 differ between the current
and previous skin streams. Local displacement has median `0.00327549`, RMS
`0.00411025`, and maximum `0.01063064` model units. The captured base shell's
resulting vertex motion has median `0.64337`, RMS `0.91126`, and maximum
`2.27792` pixels at 1920x1080. Thus a previous matrix alone cannot reproduce
motion for this animated draw.

The same CPU calculation reconstructs all 18,630 current and previous base-
shell clip positions from the saved streams, `SceneObjectGpu`,
`DynamicObjectGpu`, current/previous camera state, and matrices. Maximum error
against the post-VS file is `5.54e-7` for current clip and `5.67e-7` for
`TEXCOORD5`; RMS is about `1.27e-7` for each. The report is
`capture-tools/fur-position-history/report.json`. This directly verifies the
matrix interpretation and output-register mapping without replaying the RDC.

## Viewport implementation

The viewport preserves the previous jittered model-view-projection matrix and
wind time after each rendered sample. The vertex shader evaluates both current
and previous wind deformation and forwards the previous clip position through
the geometry stage. On the first sample, after resource resize, after a model or
weather change, and after an explicit temporal reset, previous state equals the
current state so motion starts at zero. Camera movement keeps the prior matrix,
allowing the material target to describe camera motion before the existing
preview accumulator resets its stationary history.

The asset viewer currently renders static bind-pose geometry. Its previous
vertex source is therefore the same authored position, which is the native
non-skinned branch. A future animated viewport must supply previous skinned
positions; matrix and wind history cannot reproduce skeletal deformation.

The lighting stages intentionally continue to unpack the first four material
targets. The preview temporal pass samples target 4 only at decoded Hair pixels.
It converts the top-left velocity Y sign to OpenGL's lower-left texture space,
subtracts current/previous jitter offsets because preview history is stored on a
stable grid, and constrains the reprojected history to the current 3x3
luma/chroma neighborhood.

This consumer remains a preview adaptation, although its color transform,
Catmull-Rom history sampling and neighborhood rejection math now come from the
recovered retail main-apply DXIL. The saved texture manifest proves that retail
also uses full-resolution
`kTaaDisoccl` and paired `kTaaDepth0/1` histories, plus half-resolution
`kTaaMask` and `kTaaDisocclHalfRes`. Those rejection resources are not produced
by the asset viewer. Their recovered interface and the future bounded capture
plan are recorded in
[HAIR_TEMPORAL_RECONSTRUCTION.md](HAIR_TEMPORAL_RECONSTRUCTION.md).

## Verification boundary

The full CPU suite passes, all forward/material/decode/lighting/contact/
denoise/temporal shader sets compile and link with the offline GLSL compiler,
and the shared motion helper retains the exact captured-draw replay result
above. This establishes the target format, interpolation path, pixel formula
and history direction. The saved base shell establishes the previous-clip
producer through CPU reconstruction; it does not establish pixel equality for
the ordinary viewport's animated shells or its temporal output.

Remaining work is to migrate the composed viewport to the native raster origin
and depth convention, recover the production TAA rejection/depth-history
stages, and compare a same-frame material draw through Hair lighting, denoise
and final temporal output. Capture 5's draw 24715 and Hair event 17544 belong to
different engine frames and must not be combined as that proof.
