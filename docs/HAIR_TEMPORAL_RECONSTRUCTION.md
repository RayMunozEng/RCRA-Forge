# Hair temporal reconstruction evidence

Status: 2026-09-04. The fur motion producer and a motion-aware preview history
consumer are connected. The exact retail native-resolution seed,
full-disocclusion, half-disocclusion, and main-apply DXIL have been recovered
and reconstructed as compiling GLSL. Saved event boundaries now close events
16262, 16269, 18687, 18695, 18704 and 18712 across the full disocclusion,
half-resolution mask, append work queue and accumulated-alpha chain. The mask
and every half-resolution image are bit exact; the append queue has the exact
40,940-entry packed set. Guarded event 20572 also proves the native
shader identity, all eight live resource bindings, the complete 224-byte
runtime cbuffer, every tightly packed input and the post-dispatch output. A
direct R11G11B10 OpenGL dispatch of the recovered apply matches 4,831,458 of
4,953,600 packed pixels exactly. Every red and green channel is within one
stored code; 4,953,596 of 4,953,600 blue channels are within one code.

## Captured event-20572 image validation

The guarded two-boundary capture is 2,638,691,664 bytes with SHA-256
`16e03131a6c26cc7ebe8e72922184f8e251bd8c38a61c29d02d2b30219203d72`.
Event 20572 dispatches `CS_TemporalAaApply` as 430 x 180 x 1 groups. Its DXIL
container SHA-256 is
`b892667bfa835a95a7f58c78b30b35d45e5784b48d750bf6543bf557d9956e0f`;
its 224-byte cbuffer SHA-256 is
`67eb5fbc8fb35a26f20ba03b18e4b7b60204a8f3685f2f74e20e28b9c0d17a62`.

`export_taa_apply_resources.py` replays the original capture through that event
and exports all seven SRVs plus the UAV in their native tight-packed formats.
The eight payloads total 139,939,200 bytes and the replay reports no debug
messages. An independent bounded LZ4 stream parser extracts ResourceId 4070
directly from the RDC `InitialContents`; its tight history SHA-256,
`ad53b991dc5867ef5ba9e30ae82946677a5a6ff177936a555944b8ce646efb7a`,
exactly matches replayed `t6`. ResourceId 4072's capture-start SHA-256 is
`31a8b0a4b64184e754885df2c2fd350ae8a7755ffe637091df4fa586dd2386e2`,
while replayed `u0` is
`ac47eee52cf85cd728cec3d8701ad7fac45e644d1f72a6d9195b99231a4e80b4`.
That difference independently proves the reference UAV bytes are the result of
the selected dispatch rather than the ping-pong target's old contents.

`compare_taa_apply.py` uploads the native input formats, binds the captured
cbuffer, preserves the native 8 x 8 shared-tile path and writes directly to a
complete R11G11B10 image. Its output SHA-256 is
`08938d15e552d105e94e9097cb11b226f12ca1747d3efccdb8b29be43b6120bc`.
Packed agreement is 97.5342781 percent. Per-channel exact agreement is
98.0686370 percent red, 99.6496084 percent green and 99.7868217 percent blue.
RMS decoded error is `8.424303e-6`, `1.149898e-5` and `2.094887e-5`.
The four blue exceptions outside one code consist of three two-code values and
one three-code value. These residuals are bounded backend rounding differences
between Direct3D DXIL and GLSL on the same NVIDIA GPU; the shader algorithm,
branch inputs, native storage conversion, and resource bytes are all matched.
The private job peaked at 1.184 GiB under a 2 GiB hard cap, kept `Default` as
the input desktop, and left no owned process running.

## Captured disocclusion producer validation

One guarded replay exports the exact pre- and post-dispatch state for the three
stages that produce the event-20572 disocclusion inputs. Event 16262 runs
`CS_TemporalAaDisocclusion` with DXIL SHA-256
`5b4710e1aa9806872423d16b5a66bfa8755ee3269bd07685888b808d7b31cc97`.
Event 18704 patches selected tiles with `CS_AccAlphaDisocclusion`, SHA-256
`3325938addce04cf33c1d7d66bc6b22d8c7bd539715ec870a090707d04aee605`.
Event 18712 reduces those tiles through `CS_AccAlphaHalfResProcess`, SHA-256
`f702297bceb7df68c195b3655bf6d24beb75bb9d998a2da3f49644cb911bd5e7`.
The 39 exported payloads total 284,290,084 bytes and independently rehash to
the manifest. Event 16262's two output hashes exactly equal event 18704's two
in-place inputs, and event 18704's final full disocclusion hash exactly equals
event 18712 `t5`. This proves dispatch continuity rather than comparing
unrelated frame resources.

Direct validation exposed and fixed a real reconstruction error: `t7`
(`kTaaDepth0`) supplies the depth and motion probes, while scalar `t8`
(`kMbDisocclTarget`) supplies attenuated history confidence. With those roles
corrected, the base event reproduces 4,953,528 of 4,953,600 RG8 pixels exactly.
All 72 differences are one stored code in red; green is exact everywhere. The
RG16F depth channel is bit exact everywhere. Its camera-motion channel retains
a bounded DXIL/GLSL arithmetic difference with maximum absolute error
`0.00390625` and RMS `2.290501745692104e-5`.

The work-queue reconstruction of event 18704 reproduces the final RG8 output
bit for bit across all 4,953,600 pixels. Its RG16F depth channel is also bit
exact; camera motion has maximum absolute error `5.4836273193359375e-5` and
RMS `7.696582195758626e-6`. Event 18712 then reproduces all 1,238,400 pixels
bit for bit in each of its four outputs: R8 disocclusion, both RG16F velocity
channels, R16F maximum depth and R16F minimum depth. The exact reduction
deliberately excludes texture-gather component `w` from the depth extrema
while retaining it for velocity tie selection.

The capture export peaked at 13.648 GiB under a 15.5 GiB private-job cap. Each
comparison ran under a 2 GiB cap; the exact half-process run peaked at 1.005
GiB. Every run kept `Default` as the input desktop, exited cleanly and left no
owned process. The compact reports and recovered shaders live under
`artifacts/rcra-fur-continuation/capture-tools/`.

## Half mask and accumulated-alpha setup validation

The remaining setup stages can be validated from the resource boundaries
already exported, so they do not require another high-memory RenderDoc replay.
Event 16269 runs `CS_TemporalAaDisocclusionHalf`, DXIL SHA-256
`afad553b7bdab5011e9acc6a61e7818abb723c06f986243e478239b61740a9a8`.
It linearly samples event 16262's full RG8 output through
`m_A = (1/1720, 1/720, 1/3440, 1/1440)`. The recovered shader's R8 SHA-256,
`98e384af9a52a63c809fc259c25f04a585a63f04b6e8ea577880c601b02198a3`,
exactly equals all 1,238,400 bytes present in `kTaaDisocclHalfRes` before
event 18712 updates that resource in place.

Event 18687 runs `CS_AccAlphaHalfResMask`, DXIL SHA-256
`a7f48ebde450132e5eccf52f3161001bd464d74a459ab234fcbe632b641349d7`.
It point-samples full-resolution linear depth and compares it with the
pre-update `kLinearDepthHalfResMin` value multiplied by the exact float32
constant `0.9980000257492065`. Its recovered R8 output SHA-256,
`9e932c839ccffdd049181b5c13d5e442e88c7b18da5a8a43822ca8009fa07b97`,
matches `kTaaMask` bit for bit across all 1,238,400 pixels. This direct GPU
comparison also resolves four coordinates that sit on Direct3D point-sampler
ties and differ from a simple CPU texel choice.

Event 18695 runs `CS_AccAlphaWorkQueue`, DXIL SHA-256
`4c6def4e3af247418b546dd581cf971bd93fc274e3c1163a892f6ec8da3729b1`.
Each thread examines one 4 x 4 mask tile through four gathers and appends
`(y << 16) | x` when any flag is nonzero. The captured mask predicts exactly
40,940 active tiles. That packed set is identical to all 40,940 unique entries
consumed by event 18704. Append order is scheduler-dependent and differs
between a row-major CPU enumeration and the captured GPU sequence; the set and
count are the stable contract, and each tile writes a disjoint 8 x 8 region.

The two additional private comparisons peaked at 0.926 GiB and 0.873 GiB under
2 GiB hard limits. Both retained `Default` as the input desktop and left no
owned process. The alpha-setup run used a 20 GiB pagefile reserve after a
30 GiB preflight correctly refused to launch at 23.68 GiB available.

## Saved full-resolution resources

The fresh 1920x1080 capture manifest contains:

| Resource | Format | Size | Role established offline |
| --- | --- | --- | --- |
| `kGBufferVelocity` | R16G16_FLOAT | 1920x1080 | Current-minus-previous pixel motion written by material passes |
| `kTaaDisoccl` | R8G8_UNORM | 1920x1080 | Full-resolution temporal disocclusion result |
| `kTaaTarget0/1` | R11G11B10_FLOAT | 1920x1080 | Paired temporal color histories |
| `kTaaDepth0/1` | R16G16_FLOAT | 1920x1080 | Paired temporal depth/velocity histories |
| `kTaaMask` | R8_UNORM | 960x540 | Half-resolution temporal mask |
| `kTaaDisocclHalfRes` | R8_UNORM | 960x540 | Half-resolution disocclusion input |

The manifest establishes allocation, names and formats. It does not establish
which history index was current at the Hair frame or the final apply weights.

## Consumer-side velocity evidence

Fresh event 17894 uses `CS_AccAlphaDisocclusion`, resource 4776, SHA256
`3325938addce04cf33c1d7d66bc6b22d8c7bd539715ec870a090707d04aee605`.
This is an accumulated-alpha disocclusion stage, not the main TAA apply. It is
still an independent engine consumer of the same full-resolution temporal
coordinate convention.

The shader:

1. expands an 8x8 work-tile address;
2. reads center and diagonal linear depths;
3. chooses the closest diagonal depth when the center exceeds 1.025 times that
   minimum;
4. loads velocity at the selected depth location;
5. computes both history coordinates as current pixel minus velocity;
6. samples paired history depth around that coordinate;
7. writes current depth plus a camera-motion magnitude to an RG16F history;
8. writes disocclusion and accumulated-alpha confidence to an RG8_UNORM output.

Steps 4-5 prove the velocity sign used by the preview consumer. The shader also
shows why velocity alone cannot reproduce retail rejection: current linear
depth, paired previous depth/velocity, a scatter texture, tile flags and the
`TemporalAaCBuffer` all affect its outputs.

The saved material draw independently establishes that the signal is
meaningful. A CPU-only decode of its 18,630 referenced vertices found a changed
previous skin position for every vertex. Reconstructing the base shell from the
saved current/previous positions and transforms matches current and previous
post-VS clip values within `5.67e-7`; the resulting captured vertex motion has
a median magnitude of `0.64337` pixels and a maximum of `2.27792` pixels at
1920x1080. See [FUR_MOTION_PATH.md](FUR_MOTION_PATH.md) and the private
`capture-tools/fur-position-history/report.json`.

## Recovered native-resolution disocclusion

The static executable family closes the shader-code gap left by the fresh
capture. `CS_TemporalAaDisocclSeedHistory` copies current linear depth to the R
channel of the RG16F depth/velocity history and writes zero to G.
`CS_TemporalAaDisocclusion` consumes current linear depth at `t5`, velocity at
`t6`, the paired depth/velocity history at `t7`, scatter data at `t8`, the
point-clamp sampler at `s0`, and the 224-byte `TemporalAaCBuffer` at `cb2`. It
writes full disocclusion to an RG8_UNORM `u0` and current depth plus measured
camera motion to RG16F `u1`.

The full-resolution DXIL establishes this sequence:

1. select center or closest-diagonal depth with the shared 1.025 test and load
   velocity at that location;
2. form history coordinates as current pixel minus velocity, detect coordinates
   outside the viewport, and attenuate prior depth confidence as velocity rises;
3. reconstruct the selected view-space position and project two cbuffer-driven
   transforms to measure translation and camera-motion discrepancies;
4. sample a three-point triangle in the scatter texture at 1.5 texels around
   history, retaining the motion value paired with its minimum depth;
5. compare transformed depth against that scatter depth, subtract only local
   diagonal depth changes below 7.5 percent of center depth, and switch the
   rejection slope from 120 to 24 when translation projects outside one pixel;
6. combine depth rejection, scatter/camera-motion confidence, a small motion
   floor, out-of-bounds history, and the fuzz-controlled local-depth term into
   the two output channels.

`CS_TemporalAaDisocclusionHalf` is a direct linear resample of full-resolution
disocclusion through `MiscCB.m_A`; it contains no additional rejection logic.
The executable orchestration now proves that this pass runs immediately after
the full-resolution dispatch. It binds the full result at renderer `+0x8A98`
to `t5`, the half output at renderer `+0x8C30` to `u0`, selects shader-object
global `0x14673E1D0`, and dispatches `ceil(halfWidth/8)` by
`ceil(halfHeight/8)`. The 64-byte `MiscCB` consumes only its first vector,
written exactly as `(1/halfWidth, 1/halfHeight, 0.5/halfWidth,
0.5/halfHeight)`. Combined with the shader, this maps each half-resolution
pixel center to the corresponding normalized full-resolution footprint.

The alternate seed branch is also statically closed. Full disocclusion runs
only when the previous depth-history record exists, view byte `+0x1B9E` is
zero, and global `0x146732ECB` is nonzero. When the view reset byte is nonzero
and a current temporal record exists, `CS_TemporalAaDisocclSeedHistory` binds
that record's `+0x40` resource to `u0`, current linear depth at frame-resource
offset `+0x29B8` to `t5`, selects shader-object global `0x14673E178`, and
dispatches over the full-resolution 8x8 grid. The shader writes `(depth, 0)`;
if the required current record is absent, the branch makes no dispatch.
The output-equivalent reconstructions are
`recovered-taa-seed-history.comp`, `recovered-taa-disocclusion.comp`, and
`recovered-taa-disocclusion-half.comp` beside `recovered-main-taa.comp` under
the private `capture-tools/extracted-shaders/` directory. All four compile in
the CPU-only shader validation gate. Their unknown cbuffer values remain
runtime inputs rather than missing shader behavior.

## Recovered cbuffer builder

A CPU-only PE/x64 trace resolves the native-resolution apply builder at
`0x1411D7DA0` and its shader-object use at `0x1411D8771` in the verified
executable. The function allocates all `0xE0` bytes of `TemporalAaCBuffer` and
writes every named region. The stable writes establish:

- a normalized 3x3 Gaussian `exp(-2.29 * (dx*dx + dy*dy))`;
- a normalized separable Catmull-Rom 3x3 kernel;
- final filter weights `mix(normalizedGaussian, normalizedCatmull, 0.8)`;
- filter offsets `width * projectionJitterX * 0.5` and
  `height * projectionJitterY * -0.5` in native top-left pixels;
- fallback nonopaque response `0.04f` (bits `0x3D23D70A`), replaced only by a
  positive value at the optional runtime settings pointer;
- minimum rejection `max(nonopaqueResponse, 0.0625)`, with a separate runtime
  flag able to raise that floor to `0.1f`;
- stencil response `min(runtimeNonopaqueResponse + 0.25, 1.0) / 128`, which the
  apply shader multiplies by the stencil value;
- history warmup as the reciprocal of the active history age plus one;
- dither X/Y of `1/90` and `1/45` on the executable's initial platform enum 26,
  a five-frame Z sequence `0, 2, 4, 1, 3`, and W from the exact 256-float table
  indexed by history age modulo 256.

The response source is also named by the executable schema. Parallel material
property metadata at index 8 identifies `TemporalAA` and describes it as the
control that forces nonopaque materials toward the current buffer and away from
history. The decoder asserts both string pointers and full text before tying the
positive runtime value at material state `+0x22C` to the 0.04 fallback.

The raw dither table has SHA-256
`5747b412a83d10e7430385c2c20b548d5f2b63558993e5b9aa159486f689e328`.
`capture-tools/trace_temporal_cbuffer_static.py` reproduces PE references and
bounded disassembly. `capture-tools/decode_temporal_cbuffer_builder.py`
verifies the executable hash, constants, table, cbuffer offsets, zero-jitter
kernel, and all 32 preview Halton kernels; its report is
`capture-tools/temporal-cbuffer-builder.json`.

That decoder now also guards the native apply's output, seven input bindings,
shader selection, and dispatch. The current output is `+0x40` on the record
returned by helper `0x141235A40`; prior color history is `+0x98` on the record
from `0x141235AB0`. The frame record supplies current color `+0x2D98`, velocity
`+0x7B18`, full disocclusion `+0x8A98`, stencil `+0x26D8`, half mask `+0x88A8`,
and linear depth `+0x29B8`, each with its executable availability/enable guard.
The half-mask guard is exact: `t10` receives frame resource `+0x88A8` only
when byte global `0x146732EC9` or `0x146732EC6` is nonzero and availability
`+0x89E0` is nonzero. The `0x146732EC6` path additionally invokes helper
`0x1411CB890` before binding; every other case binds the empty descriptor.
Matching source/destination dimensions select native apply object global
`0x14673E120`; a mismatch selects upsample object global `0x14673E124`. Dispatch
is `ceil(destination/8)` in X and Y. The helper bodies close the ring rule:
current index is `renderer+0x1C28`, prior index is `1-current`, records have
stride `0x1F0`, and a nonzero frame requires the prior tag to equal
`frame-1`. Two runtime flags choose between the guarded current/prior pool
bases. The frame's actual index and record contents remain capture evidence.

The full-resolution disocclusion orchestration uses a second builder variant.
Its verified writes establish `m_PixelScale = (width, height, 1/width,
1/height)`, zero `m_SrcPixelScale`, and camera-motion normalization
`1920 / max(width, 1920)`. Its history threshold is `-1` when the current-view
frame matches the global frame and `+1` otherwise. Helper `0x141210700`
constructs the prior projection-to-UV values as `(0.5*sx, -0.5*sy,
0.5*(ox+1), 0.5*(1-oy))`. The fuzz flag is exactly enabled when the disable
byte is zero and mode bits `& 6` are nonzero. The two depth thresholds and
current/prior view transforms remain runtime values. The hash-checked decoder
and report are `capture-tools/decode_temporal_disocclusion_builder.py` and
`capture-tools/temporal-disocclusion-builder.json`.
Its prior depth-history helper uses the same `1-current` index, `frame-1` tag
validation, and `0x1F0` stride against the pool at renderer `+0x1698`.
The decoder now guards 16 executable ranges totaling 4,719 bytes, including
the full/seed branch gate, both half-pass blocks, and the complete seed branch.
It also scans all supported direct RIP-relative references to the two dynamic
threshold globals. Exactly four references exist, all SIMD loads in the two
disocclusion builders; no direct store or file-backed absolute pointer supplies
a static default. Their values therefore remain a real runtime-capture boundary.

The shared matrix helper is no longer opaque. It promotes two float32 4x4
matrices to float64, inverts the second, multiplies `first * inverse(second)`,
and converts the result back to float32. Main apply and full disocclusion
therefore write `m_ViewSpaceDelta = currentView * inverse(previousTransform)`.
For the secondary transform stored in `m_FilterWeightsA/B/C`, disocclusion
first replaces the current matrix's fourth float4 with the position at view
offset `+0x560` and `w=1`, repeats the same operation, and stores its first
three float4 values. The conversion, inverse, and multiplication helper ranges
are hash guarded in both builder reports.

The two-frame capture now supplies the disocclusion runtime state for the saved
view. Event 16262's 224-byte cbuffer has SHA-256
`3be6fcdcfaae0b2900aba88fc34429edafc5b11a6fd70a06aa39729f7f661985`;
event 18704's accumulated-alpha variant has SHA-256
`af3ea342a1499f570d156e4d2af2d9e29f1a8f9d8a8ab58fd50ba88fa2d74e0e`.
Both contain the stable-view transform, projection pair, depth base `8.0`,
depth slope `26.875001907348633` (`0x41d70001`), and camera normalization
`0.5581395626068115`. The full pass uses motion threshold `1.0`; the
accumulated-alpha pass uses `0.6666666865348816`. The depth slope is one
float32 code above exact `3440/128`, so it remains a captured runtime
calibration rather than a claimed resolution formula. The CPU-only
`capture-tools/analyze_taa_disocclusion_cbuffer.py` reproduces these values and
writes `taa-disocclusion-cbuffer-analysis.json`.

## Current preview boundary

`TEMPORAL_ACCUM_FRAG` samples the fifth fur material target at decoded Hair
pixels. It converts top-left pixel motion into lower-left OpenGL UV, accounts
for current and previous projection jitter on the preview's stable history grid,
and now selects motion with the recovered center/closest-diagonal 1.025 depth
test. It shares the recovered luma/chroma and HDR transforms in
`core/hair_temporal.glsl`. Moving Hair uses the exact five-tap Catmull-Rom
history kernel above the recovered 0.125-pixel threshold. The accumulator builds
the exact jittered Gaussian/Catmull current filter, keeps measured/history
rejection separate from the 0.0625 final-blend floor, and uses the unfloored
value for history selection, filter broadening and confidence-dependent
cross/diagonal neighborhood bounds. Static non-Hair pixels keep the existing
stable-grid path. The preview now stores paired color histories in native
R11G11B10 precision, paired full disocclusion in RG8, and paired composed
depth/camera-motion history in RG16F. Each frame writes fur depth at active fur
pixels and scene linear depth elsewhere. A dedicated pass reproduces the
recovered center/diagonal depth selection, velocity attenuation, local-depth
confidence, current-to-previous view projection, three-point depth/motion
history triangle, 7.5-percent edge allowance, 24/120 slopes, motion confidence,
and small-camera floor. The live current-to-previous transform is computed in
float64 and stored as float32, matching the executable helper. The isolated
preview's zero-depth background sentinel emits inert values because the retail
frame supplies a valid background depth instead.

Pass order follows the recovered dependency graph. Current motion is
downsampled, reduced through half/quarter/sixteenth neighborhoods and the
40-crossing scatter producer. A paired R16F pass snapshots opaque and composed
depth. The event-16262 base disocclusion writes current RG8 plus RG16F
depth/motion from opaque depth, and the base half pass records four-texel depth
minimum/maximum values. Event 18687 compares the current frame's composed depth
against that pre-alpha half minimum. A dense mask-discard pass then reproduces
the output of events 18695/18704 with the captured `2/3` motion threshold, and a
second mask-discard pass patches the four event-18712 half-resolution outputs.
The dense execution changes scheduling only: flagged pixels receive the same
calculation and unflagged pixels retain the base targets.

The final temporal color pass consumes the current RG8 disocclusion and the
explicit current-frame R8 `kTaaMask` equivalent. It takes full-disocclusion R
directly, half-weights G, contributes `0.5 * mask`, and uses the recovered
nonopaque stencil response `min(0.04 + 0.25, 1) = 0.29` at decoded Hair pixels.
The base half-depth proof in `taa-base-half-depth-analysis.json` matches both
captured extrema bit for bit across all 1,238,400 pixels. The accumulated-alpha
resolve deliberately excludes gather component `w` from its extrema, matching
`CS_AccAlphaHalfResProcess`. The same color pass applies the exact
executable dither table, phase, and top-left pixel pattern at the color-storage
boundary. History warmup is uploaded as
the builder's direct float32 reciprocal rather than reconstructed by subtraction.
Current-sample chroma is rounded through f16 before filtering and neighborhood
bounds, matching the native group-memory precision, while history chroma stays
f32. All history taps explicitly use LOD 0. Frame zero and any history reset use
a finite current-color history input so undefined OpenGL allocation contents
cannot propagate through a full-current blend.

The preview uploads the recovered default `m_Misc.x` independently from history
warmup: `max(0.04f, 0.0625f) = 0.0625f`. This preserves the main apply shader's
separate `max(m_Misc.w, m_Misc.x)` inputs instead of collapsing their meanings.

This remains a bounded preview adaptation. It supplies full disocclusion, the
accumulated-alpha mask and half outputs, motion-blur scatter, depth/camera-motion
history, explicit opaque and fur velocity, and a shared R8UI category target
carrying stencil bit 128. Runtime setters now provide optional nonopaque
response, conditional 0.1 floor and HDR reference values. Missing or invalid
inputs select the executable's exact 0.04 response and 0.25 HDR-scale fallbacks.
The captured response/HDR/history inputs reproduce
`m_Misc = (0.0625, 0.002265624935, 76.10927582, 0.0002742731886)` exactly.

A 640x640 logical/800x800 physical private-desktop production smoke exercised
all of those passes for nine temporal samples. Both RG8 and RG16F history slots
were finite and valid; stable-view full disocclusion was zero, geometry depth
reached `1.4091796875`, and camera motion remained below the recovered threshold
at `0.98779296875`. A second 480x480 logical moving-wind diagnostic exercised
nonzero full disocclusion in both slots (127 and 774 pixels). Its readback proves
nonzero velocity through every motion-blur producer stage. Full velocity reached
`0.50146484375`; shutter reduction left the gathered neighborhood at
`0.07080078125`, correctly below the exact `0.800000011920929` scatter gate, so
both scatter outputs remained zero. Both frames are visually intact. The runs
peaked at 1.748 and 1.568 GiB under a 2 GiB hard limit, retained `Default` as the
input desktop, exited with code zero, and left no process or window.

A later 480x480 logical/600x600 physical smoke exercises the complete live
accumulated-alpha chain for seven temporal samples. Its explicit R8 mask has
2,356 nonzero half-resolution pixels. Both full R16F depth snapshots, all four
half outputs and both full temporal histories are finite; the patched half
velocity is nonzero in 2,350 pixels per component. The saved frame is visually
intact. The isolated job peaked at 1.628 GiB under 2 GiB, retained `Default` as
the input desktop, exited with code zero and left no process or window. All 285
CPU tests and all 53 offline shader cases pass.

A subsequent 480x480 logical/600x600 physical camera-motion smoke exercises the
new shared inputs. Opaque geometry writes RG16F current-minus-previous velocity
with the same native top-left convention as fur. The fur material pass writes
category bit 128 into an R8UI texture attached to both the opaque and fur
framebuffers; the final apply loads that exact bit at the center/closest-diagonal
velocity pixel and multiplies it by the captured `m_Misc.y` scale. Across seven
0.25-degree yaw steps, temporal age advanced from 1 to 9 without a reset.
Opaque velocity was finite and nonzero in 20,686 pixels per component, and the
stencil readback contained only 0 and 128, with 28,362 fur pixels. Both full
disocclusion histories, both depth/motion histories, both motion-scatter slots,
and the accumulated-alpha chain remained valid. The frame is visually intact;
the hidden job peaked at 1.631 GiB under 2 GiB, kept `Default` as the input
desktop, exited with code zero, and left no owned process or window.

This absence is now reproducible rather than a filename search.
`capture-tools/inventory_temporal_shaders.py` scans all 261 exported shader
records, 1,501 draw/dispatch uses, assembly-declared shader hashes, report
container hashes, and MD5 values of the saved binaries. The originating hash
matches none of those namespaces. `CS_AccAlphaDisocclusion` at event 17894 is
the only saved shader that references `TemporalAaCBuffer`. Its immediate saved
sequence is velocity/depth, half-resolution mask, work queue, full-resolution
disocclusion, half-resolution process, occlusion-cover dropouts, then history
copy; no main color apply appears in that chain. The generated evidence is
`capture-tools/temporal-shader-inventory.json`.

## Offline executable recovery

The installed `RiftApart.exe` has SHA-256
`51299faca61866cf10ea9035a15b8f22600a56557dd5ffc1aad390d5a54e6d82`.
An exact CPU-only byte scan found the raw originating shader hash once, in the
`HASH` part of a valid 11,612-byte DXBC container at file offset `0x34235a4`.
The container SHA-256 is
`b892667bfa835a95a7f58c78b30b35d45e5784b48d750bf6543bf557d9956e0f`.
DXC identifies its entry as `CS_TemporalAaApply`, its shader hash as
`4e1b2693fbe9696f3f1eb1d6ac577a01`, and its dispatch size as 8x8.

The recovered binding table is complete:

| Slot | Resource |
| --- | --- |
| `cb2` | 224-byte `TemporalAaCBuffer` |
| `s0`, `s2` | Point-clamp and linear-clamp samplers |
| `t5` | Current color |
| `t6` | History color |
| `t7` | Velocity |
| `t8` | Full-resolution disocclusion |
| `t9` | Stencil |
| `t10` | Half-resolution mask |
| `t11` | Linear depth |
| `u0` | Three-component float output |

The DXIL proves that the apply shader:

1. selects center or closest-diagonal velocity using the same 1.025 depth test
   as accumulated-alpha disocclusion;
2. computes history pixel position as current pixel minus velocity;
3. uses linear history sampling for high rejection or sub-0.125-pixel motion,
   and an optimized five-tap Catmull-Rom sample otherwise, with the base pixel
   selected by DXIL `Round_ni` (floor);
4. converts current samples to luma and two normalized chroma axes, compresses
   luma with `m_Misc.z`, and rounds the two chroma values through f16 group
   storage;
5. applies a nine-sample current filter whose weights come from
   `m_FilterWeightsA/B/C`, blending toward the fixed 0.05/0.10/0.40 Gaussian
   kernel as rejection rises;
6. derives cross and diagonal neighborhood bounds, suppresses diagonal
   expansion as rejection rises, and clamps encoded history when screen
   capture mode is disabled;
7. blends constrained history toward filtered current color by the combined
   disocclusion, mask, stencil and `m_Misc` rejection value;
8. reverses the HDR compression, clamps negative output and applies the
   `m_DitherConsts` multiplier.

A bounded 65-container DXC inventory around the main apply found the adjacent
family with zero disassembly failures: `CS_AccAlphaDisocclusion`,
`CS_AccAlphaHalfResMask`, `CS_AccAlphaHalfResProcess`,
`CS_AccAlphaWorkQueue`, `CS_TemporalAaApplyUpsample`,
`CS_TemporalAaDisocclSeedHistory`, `CS_TemporalAaDisocclusion`, and
`CS_TemporalAaDisocclusionHalf`. The embedded
`CS_AccAlphaDisocclusion` shader hash is
`04d5df274c814fdd0ad97030675b8566`, exactly matching fresh captured resource
4776, so the static family and captured runtime chain are linked directly.

`capture-tools/inspect_temporal_static_assets.py` reproduces the exact scan and
container extraction. `capture-tools/inventory_embedded_temporal_dxil.py`
reproduces the bounded family inventory and preserves each temporal binary and
DXC assembly. `capture-tools/extracted-shaders/recovered-main-taa.comp` and the
three disocclusion GLSL files documented above reconstruct the recovered
native-resolution chain. The dynamic-resolution upsample apply remains
preserved as its exact DXBC and DXC assembly; it is not used by the current
native-resolution preview path. The cbuffer trace/decode scripts and their saved
disassemblies recover the executable-side builder described above. No game,
capture replay, window, OpenGL context, or GPU process is used by these steps.

## Guarded runtime main-apply contract

`riftapart-taa-two-frame_capture.rdc` spans exactly two engine boundaries and
contains native `CS_TemporalAaApply` at event **20572**. The capture is
2,638,691,664 bytes with SHA-256
`16e03131a6c26cc7ebe8e72922184f8e251bd8c38a61c29d02d2b30219203d72`.
The captured 11,612-byte DXIL container has SHA-256
`b892667bfa835a95a7f58c78b30b35d45e5784b48d750bf6543bf557d9956e0f`,
byte-identical to the independently extracted executable container.

The event binds the complete native apply contract:

| Register | Resource | Captured name | Size and format |
| --- | --- | --- | --- |
| `t5` | current color | `kForward` | 3440x1440 R11G11B10_FLOAT |
| `t6` | previous color history | `kTaaTarget0` | 3440x1440 R11G11B10_FLOAT |
| `t7` | velocity | `kGBufferVelocity` | 3440x1440 R16G16_FLOAT |
| `t8` | full disocclusion | `kTaaDisoccl` | 3440x1440 R8G8_UNORM |
| `t9` | stencil | `kHyperDepthStencil` | 3440x1440 D32S8 |
| `t10` | half mask | `kTaaMask` | 1720x720 R8_UNORM |
| `t11` | linear depth | `kLinearDepth16` | 3440x1440 R16_FLOAT |
| `u0` | output history | `kTaaTarget1` | 3440x1440 R11G11B10_FLOAT |

The 224-byte `cb2` payload has SHA-256
`67eb5fbc8fb35a26f20ba03b18e4b7b60204a8f3685f2f74e20e28b9c0d17a62`.
Source and destination scale both encode `(3440, 1440, 1/3440, 1/1440)`.
`m_Misc2.zw` is `(-0.3400000036, 0.0199999809)` pixels. Re-evaluating the
recovered float32 Gaussian/Catmull builder at that offset reproduces all nine
captured filter weights with maximum absolute error `7.4505806e-9`; their sum
is `0.9999999109` after native rounding.

`m_Misc` is `(0.0625, 0.002265624935, 76.10927582,
0.0002742731886)`. Its second field recovers the ordinary `0.04` nonopaque
response, its third implies runtime HDR reference `0.006569501478`, and its
fourth is exactly the float32 reciprocal for history age **3645**. That age
selects dither-table index 61 and phase zero, matching captured
`m_DitherConsts = (1/90, 1/45, 0, 0.4390000105)`. Fuzz and screen-capture flags
are both zero. The final eight reflected padding bytes are unconsumed and are
reported without assigning meaning to them.

`capture-tools/analyze_taa_apply_runtime.py` regenerates these checks from the
runtime report, cbuffer bytes, and static builder report. Its generated
`taa-apply-runtime-analysis/report.json` passes. `core/hair_temporal.py` now
exposes the shader/binding identity, float32 filter and scalar producers,
captured disocclusion calibration, camera normalization, and a typed 224-byte
pack/unpack contract. The captured HDR value remains a per-frame input and is
not hardcoded into the editor preview. All 285 CPU tests and all 45 offline
shader cases pass.

## Production apply validation

`compare_viewport_taa_apply.py` renders the production
`TEMPORAL_ACCUM_FRAG` against all event-20572 saved resources at 3440x1440. It
matches 4,832,111 of 4,953,600 packed output pixels exactly, or
97.5474604 percent. Red, green and blue are exact at 98.1116764,
99.6272408 and 99.7814721 percent; their within-one-code rates are
99.9997779, 99.9998587 and 99.9999394 percent. Against the independent recovered
compute shader, packed exact agreement is 98.9783794 percent.

`analyze_viewport_taa_residuals.py` classifies every residual larger than one
stored code. Only 17 native-output pixels and 14 recovered-compute pixels remain.
All use the ordinary low-rejection, linear-history path: none touches a border,
closest-diagonal selection, Catmull-Rom, stencil 128, disocclusion, accumulated
alpha or elevated rejection. Their maximum squared motion is about
`4.5314e-6`. This isolates the remaining difference to sparse cross-API
arithmetic/storage rounding rather than a missing input or control-flow branch.

The production viewport uses the same dynamic `m_Misc` producer and exact
integer pixel-center history coordinate. A guarded camera-motion render activated
the values above, preserved temporal history and kept every downstream target
finite. The native raster migration subsequently moved the complete live chain
to upper-left, zero-to-one reverse-Z coordinates without reopening temporal
resource or presentation errors.
