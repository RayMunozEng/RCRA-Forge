# Captured fur geometry and material comparison

Status: 2026-09-03. The ordinary viewport's shell geometry and material helpers
have now been compared directly with a captured Ratchet head draw. This closes
several rendering bugs. Complete viewport/final-frame parity remains unfinished.

## Capture and scope

The private evidence is in the outer workspace's
`artifacts/rcra-fur-continuation/capture-tools/`. The capture is
`riftapart-checkpoint_capture_5.rdc`, draw **24715**, with 107,664 indices and
32 shell instances. It is a later engine frame than Hair lighting event 17544;
do not mix their viewport or world constants.

| Stage | Entry | Original shader SHA256 |
| --- | --- | --- |
| VS | `VS_ModelFurShellGBufferDeferredWind` | `76b4457d347b2fea846bd2021bbb75e9d8c49c00871201505b2217c1316b6828` |
| PS | `PS_FurShellGBufferDeferred` | `778f1fc603c882e6186cbec5359933979af342930619e0b8a9747662149193f3` |

The draw uses density 16, length 0.03, offset scale 1, 32 layers, wind strength
0.03709043935, turbulence 0, and wetness 0. Vertex buffers are captured after
skinning. This establishes shader behavior with captured inputs; it does not
validate the editor's animation or pose reconstruction.

## Corrections integrated into the viewport

- `Round_ni` is **floor**, not nearest-even. A local SDK compiler control maps
  HLSL `floor` to DXIL opcode 27 and `round` to opcode 26. Earlier handoff claims
  about nearest-even and dry 1/1.375 UV dithering were wrong. Dry UV divisor is 1.
- Material and coverage phases use D3D top-left pixel centers and the captured
  `TemporalPlusCycle` term. HairDenoise hashes integer dispatch coordinates.
- Native D3D12 fuses `pixel.x - 10*layerSlice`. Explicit GLSL `fma` reproduces
  this; separate arithmetic changes the sine hash at fractional shell slices.
- Fur volume generation retains the executable's float32 reciprocal and
  operation order. The previous Python float calculation made layer 20 one
  coverage byte too large for 28-layer strands, also affecting its three mips.
- Packed normal/tangent Z magnitude uses `abs` before the stored sign. The
  position correction uses the exact float32 reciprocal of 31744, rather than
  0.000032. An encoded zero scale gives infinite correction and full availability.
- Wind projects onto the tangent/bitangent plane, preserves the supplied wind
  vector magnitude, and uses exact timer/table constants. The bent tangent is
  normalized after raster interpolation. Its W channel carries signed offset
  scale; the pixel shader uses its sign for handedness and magnitude for grooming.
- The pixel shader preserves the cross-product magnitude instead of
  orthogonalizing the bent frame. Gloss samples R; specular samples G. Gloss
  increases with wetness; the previous shell gloss fade was not in this PS.
- Contact linear view depth uses fur **length**, the unshifted material phase,
  and the shell field. The previous wetness-based offset was incorrect.
- Native instrumentation measures depth 4.47-4.87 in this draw. The shared
  buffer holds **linear view depth**, not reciprocal depth. The viewport now
  converts `gl_FragCoord.w` before applying the offset and keeps contact and
  denoise consumers in the same linear units. Older reciprocal-depth handoff
  claims are superseded. Contact ray interpolation itself is perspective-correct.
- Native integer packing and unpacking are shared with the preview's lighting
  path. Geometric normal, groom, gloss/specular and transmission therefore use
  retail quantization. Hair's gloss fade uses linear view depth, not shell index.
- The public weather setter now also preserves wind-vector magnitude; it had
  still normalized the value before sending it to the corrected shader.
- Fur material textures use the captured filtering: albedo 16x anisotropy,
  gloss/control 8x, and a separate linear procedural-volume sampler. Upload
  signatures include filtering so progressive material loading upgrades an
  already uploaded base map when its fur-control role arrives.
- Shared layer UV arithmetic preserves multiply-then-divide ordering. The
  shared motion-vector helper preserves separate current-pixel normalization
  and uses the native fused previous-position subtraction.
- Wet coverage preserves the subtraction before fused interpolation, and
  contact depth uses the native fused final subtraction. These remove the
  final two one-float-step depth differences in controlled wet-material draws.
  Wet albedo also retains the exact native multiplier (float bits 0xBE4CCCCC).

Shared functions live in `core/hair_lighting_noise.glsl` and
`core/fur_material.glsl`, plus `core/fur_gbuffer.glsl`. Exact fused arithmetic requires `GL_ARB_gpu_shader5`;
the legacy fallback has not been shown to match. The isolated preview's cycle
and Halton index are still synthetic, not runtime scene bindings.

## Measurements

| Comparison | Result | Private report |
| --- | --- | --- |
| Procedural fur volume | **128/128 subresources, 696,320 bytes exact** | `fur-volume-capture-comparison.json` |
| Ordinary viewport VS, instances 0/8/16/24/31 | **93,150 vertices, zero visibility disagreements** | `fur-vertex-comparison-corrected/report.json` |
| UVs | Exact for every compared vertex | same |
| Camera-relative position | Max error 7.15256e-7 scene units | same |
| Bent tangent | Max component error 5.95302e-6; previously 0.0608666 | same |
| Material phase, shifted coverage phase, wetness step, contact depth, gloss, specular | **6,308/6,308 pixels exact for each field** | `d3d-fur-material-24715/comparison.json` |
| Shifted coordinates, normalized hash inputs, sine argument, sine and hash | **6,308/6,308 exact for each field** | same |
| Packed normal/gloss/specular and strand/transmission | **6,308/6,308 exact pixels** | same |
| Unpack normal/strand vs retail instruction slice | **11,215/11,215 exact for both vectors** | `fur-gbuffer-decode.json` |
| Decoded normal vs native debug values | 16 queries; max 1.78814e-7 | same |
| Groom direction | Max component error 4.17233e-7 | same |

The original vertex baseline had 94 visibility disagreements across the four
non-base instances. `fur-vertex-comparison-baseline/` retains that measurement.
The corrected vertex report also records shell slice and curved offset errors;
this is not a claim of bit-exact vertex output.

The material oracle reassembles the original PS through the installed SDK,
validates each DXIL container, and instruments only output stores. Float bits
are carried in pairs of 16-bit render-target channels. An unchanged control
reassembly reproduces both original targets exactly. Every instrumentation
variant must affect the replay and retain the same 6,308-pixel coverage mask.
Shader replacements are removed and freed after each variant. Original capture
files and installed game files are unchanged by this comparison.

The initial material checks covered surviving pixels. The full raster replay
below extends this to coverage, texture sampling and depth testing. The asset
preview still does not bind runtime draw clipping,
alpha overrides, tangent-flip flags, or the production LOD transition factor.

## Full captured draw replay

`replay_fur_raster.py` consumes all 32 instances of captured post-VS geometry
(18,630 vertices per instance), the original indices, native compressed texture
mips, constants, and before-draw render/depth targets. The shared GLSL material
helpers write the original five G-buffer formats. Back-face culling, reverse-Z
`GreaterEqual`, depth writes, disabled blending and the original samplers are
reproduced. An independently instrumented native PS supplies the coverage mask.

**The dry draw matches all 6,308 pixels exactly in all five G-buffer targets
and hardware depth, with zero missing or extra coverage.** The targets are
normal/gloss/specular RGBA16_UINT, albedo RGBA8_SRGB, linear depth R32_FLOAT,
strand/transmission R32_UINT and motion RG16_FLOAT. Reports are
`fur-raster-replay-arithmetic-order/report.json` and the shared-helper
confirmation `fur-raster-replay-wet-0/report.json`.

The diagnostic must use `glClipControl(GL_UPPER_LEFT, GL_ZERO_TO_ONE)` and
unflipped D3D resource rows. A lower-left raster origin followed by a row flip
looks equivalent but changes hardware interpolation and stochastic hashes:
that control had two missing and five extra pixels. Upper-left rasterization
matches every compared UV, shell slice, phase, previous clip position and
hardware depth. Some unquantized layer coordinates/biases still differ by
less than 1e-6; they produce identical sampled values and stored targets in
the dry draw. This is not a claim that every intermediate float is identical.

The ordinary preview still uses its existing OpenGL frame orientation and
isolated camera/lighting. Native origin is currently in the captured-draw
diagnostic; migrating the entire deferred/temporal pipeline remains necessary.
See [FUR_RASTER_COORDINATES.md](FUR_RASTER_COORDINATES.md) for the state and
screen-space boundaries that must move together.
The production material framebuffer now includes the native fifth RG16F motion
target and its previous-camera/wind producer; see
[FUR_MOTION_PATH.md](FUR_MOTION_PATH.md). That new producer still awaits a
matched viewport comparison. Its current-minus-previous sign is independently
confirmed by the saved temporal-disocclusion consumer, and the preview
accumulator now uses it for Hair history reprojection.

GPU format inspection also confirms that the installed head already uploads
albedo and gloss as sRGB BC7 (0x8E8D), and control as linear BC7 (0x8E8C).
No role-based color-space override was needed. The isotropic comparison
reduced exact strand pixels from 6,202 to 1,536 before origin correction,
demonstrating why the captured anisotropic filters are required.

Controlled native PS variants also test wetness 0.25, 0.5 and 1.0 with the same
captured geometry. **Coverage, hardware depth and all five G-buffer targets
match exactly**: respectively 6,206, 6,070 and 5,642 pixels. Including the dry
draw, this verifies 24,226 surviving pixels across four material conditions.
Final shared-helper reports are `fur-raster-replay-wet-shared-{0,0.25,0.5,1}/report.json`.
These are controlled material variants, not captures of wet animation.
The unchanged 0.0 native control reproduces every original target byte.

## Preview verification

The shared denoise integration and newest connected replay are documented in
[HAIR_CONNECTED_REPLAY.md](HAIR_CONNECTED_REPLAY.md). Production lighting/store/
denoise matches all 11,215 captured Hair pixels at both stored-color boundaries.

All 270 fork tests pass, including the independent captured texture hashes and
motion/jitter history contract. All shader sets compile and link offline; the
result is recorded in the 17:39 UTC checkpoint.
`git diff --check` passes. `viewport-fur-packed.json` / `.png` records a
successful LOD0 Ratchet head render with native BC6U, wind, contact, denoise,
and the G-buffer round trip enabled. Median synchronous render time is 4.297 ms
at an 800x800 logical viewport on the RTX 5060 Ti. The image was visually checked.
This editor camera and lighting are not the captured scene, so this is a smoke
check, not a matched-frame visual comparison.

The connected production replay supersedes the earlier six-difference result:
all 11,215 stored pixels now match. All temporary private replay and preview jobs
used for those checks exited.

## Reproduction and next work

Use the fork's Python environment and `tools/private_desktop.py` for GPU work.
The private comparison scripts are `compare_viewport_fur_vertices.py` and
`compare_fur_material.py`; native exports use RenderDoc's embedded Python.
Captured hashes are checked before use. `test_fur_mips_match_captured_gpu_texture_hashes`
keeps all four independent captured mip hashes as a regression oracle without
shipping the captured textures.

Next: validate the viewport-generated previous clip values under native raster
coordinates, recover retail TAA depth-history/disocclusion rejection, and make a
same-frame composed comparison. The lighting/store/denoise chain is already
exact at all 11,215 stored Hair pixels; see `HAIR_CONNECTED_REPLAY.md`.
