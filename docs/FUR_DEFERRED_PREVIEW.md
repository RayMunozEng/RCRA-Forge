# Deferred fur material and lighting integration

Status: 2026-09-03. The perspective HDR preview now stores native fur material
targets before evaluating lighting. Material arithmetic, vector decoding and
lighting compile as separate shader programs. This removes the previous inline
pack/decode/lighting path from normal HDR rendering.

The subsequent [shared material-response integration](HAIR_MATERIAL_RESPONSE.md)
adds native occlusion/emissive, reflection frames, diffuse/transmission and final
resolve helpers. Hair color now has native R11G11B10 precision at both the lighting
and denoise stores. Full scene/frame parity remains open.

The optional [scene-lighting path](HAIR_SCENE_LIGHTING.md) now binds explicit
grid/probe/cube resources, key radiance and native key-shadow cascades. It carries
atlas visibility in the indirect RGBA32F target's alpha; contact limits that
visibility by minimum before color storage. Its lookup is invalidated when the
camera, model or framebuffer changes.

The [motion-vector path](FUR_MOTION_PATH.md) adds the fifth native material
target (`RG16F`). It carries previous camera and wind state through the production
vertex/geometry/material chain. The preview accumulator now consumes it with the
captured current-minus-previous sign and stable-grid jitter correction. The
producer and consumer have only offline validation so far; retail depth-history
and disocclusion rejection remain separate work.

## Passes and data

1. Opaque meshes write scene/bloom color and unblended linear depth. The material
   framebuffer shares their hardware depth attachment, so opaque geometry still
   occludes fur during rasterization.
2. `FUR_MATERIAL_FRAG_SRC` writes RGBA16_UINT material, RGBA8_SRGB albedo/occlusion,
   R32_FLOAT custom linear depth, R32_UINT strand/transmission and RG16_FLOAT
   pixel-space motion. Its alpha is material occlusion, independently of
   stochastic coverage.
3. `FUR_DECODE_FRAG` reads those packed targets with integer samplers. It decodes
   normal/strand into separate RGBA32F buffers, identifies Hair from the native
   material class and exclusion bit, and preserves opaque depth outside Hair.
   Keeping this program separate prevents precise lighting expressions from
   propagating into packed-vector decoding.
4. `FUR_LIGHTING_FRAG` reconstructs view direction from the stored custom depth
   and current projection, then writes environment and key contributions into
   separate RGBA32F textures. `hair_preview_lighting.glsl` contains the isolated
   preview illumination shared with the forward fallback, including the shared
   material, environment-frame and final-resolve helpers.
5. The contact resolve copies non-fur scene color and writes environment plus
   shadowed key at Hair pixels. It clears bloom from opaque surfaces covered by
   fur. Hair RGB is converted to measured R11G11B10 precision in the mixed
   RGBA16F scene target. HairDenoise consumes that result and converts its own
   output at the store. The preview temporal pass reprojects Hair history from
   the fifth material target, then applies its recovered luma/chroma neighborhood
   constraint.

Lighting, contact and denoise now include the projection's jitter offset. The
native view basis is right/down/forward; the preview adapts its GL view rotation
and texture orientation at the pass boundaries. Non-HDR and orthographic views
use the forward fallback; the perspective deferred denoiser is skipped there.

## Captured evidence

Private reports/scripts are under the outer workspace's
`artifacts/rcra-fur-continuation/capture-tools/`. Original game resources remain
outside the fork. GPU jobs use the inactive-desktop helper; no desktop switching
or live game patching is involved.

| Production check | Result | Report |
| --- | --- | --- |
| Pre-motion production material writer at wetness 0, .25, .5, 1 | Coverage, hardware depth and its four targets exact at 6,308 / 6,206 / 6,070 / 5,642 pixels | `fur-raster-replay-preview-material-final-{wetness}/report.json` |
| Shared material plus captured previous-clip input | Coverage, hardware depth and all five native targets exact at 6,308 / 6,206 / 6,070 / 5,642 pixels | `fur-raster-replay-wet-shared-{wetness}/report.json` |
| Stored normal and strand decoding | Every component exact at all 11,215 captured Hair pixels | `preview-deferred-decode/report.json` |
| Full-frame decode masks/depth | All 2,073,600 depths exact; all 2,062,385 non-Hair pixels masked | same report |
| Shared frame preparation | Maximum component error 9.238719940185547e-7 against native intermediates | `preview-hair-frame/report.json` |
| Contact/denoise behavior | 4,080 direct/environment results exact; 16 non-fur pixels preserved | `preview-contact-behavior/report.json` |
| Bloom ownership | Covered opaque bloom cleared at 4,080 fur pixels; 16 non-fur pixels preserved | same report |
| Opaque depth with color blending enabled | 4,096 linear-depth outputs exact | same report |

The pre-motion material comparison uses the production fragment source from that
checkpoint, captured post-VS geometry, native textures/samplers, captured runtime
render flags and native upper-left raster state. Only varying/coordinate/uniform
adapters and a coverage marker are added. The current writer also emits motion
through the shared helper used by the separate five-target replay. This is not an
end-to-end render from the ordinary preview's vertex shader and camera.

That check found an incorrect layer-32 zero override in the previous preview.
Native sampling clamps this array coordinate to the final slice. Removing the
override corrected the missing coverage pixel and changed shell-depth selections;
the production writer now matches all 24,226 tested surviving pixels exactly.
The old claim that this sample returns zero is superseded by this measurement.

The old preview lobe normal also used the reversed cross-product order. Its
direction dotted with the native primary normal was approximately -1 throughout
the captured set. `hair_frame.glsl` now uses the native orientation, explicit
cross-product FMA order, seed construction and secondary-strand shift. Small
floating-point differences remain; frame preparation is not claimed bit-exact.

## Viewport verification

`viewport-native-store-wet.json` / `.png` records the latest pre-motion wet Ratchet head with
captured wind parameters. `--verify-deferred-targets` checks actual texture
formats, packed/decoded mask agreement, shared hardware depth, finite fur color
and exact preservation of non-fur scene color through lighting and denoise. It
also checks each stage's native representable color grid. It predates the fifth
target. The dry and non-HDR
checks have separate `viewport-native-store-dry` and
`viewport-native-response-fallback` reports. The fork suite passes 270 tests.

The final lit smoke has 79,334 matching Hair mask pixels and preserves all
920,666 non-Hair pixels exactly at 1000x1000 physical pixels (800x800 logical).
Dry has 80,690 matching Hair pixels and preserves 919,310 non-Hair pixels.
Three-sample median synchronous frame times are 4.7903 ms dry / 8.6231 ms wet on
the RTX 5060 Ti; these smoke timings are not a controlled performance comparison.
Dry, wet and non-HDR images were visually inspected. The non-HDR path renders without
temporal accumulation, so its individual stochastic sample is visibly grainy.

For reproduction, add `--verify-deferred-targets` to the transfer document's
`tools/smoke_fur_viewport.py` command. On the capture machine, run
`replay_preview_material.py --upper-left --wetness 0 --name preview-material-check`
through `tools/private_desktop.py`; repeat with `.25`, `.5` and `1` and unique
names. `verify_preview_deferred.py` checks the production decoder against native
float probes; `probe_preview_hair_frame.py` measures the shared frame helper.
Those three scripts and the captured resources live in the private evidence
directory, not in the distributable fork.

## Remaining parity work

- Supply automatic live scene placement, residency, cube-slot and fade ownership
  instead of requiring an explicitly assembled scene bundle.
- Connect runtime local-light ownership to the recovered submitted-stream frame
  builder. It now constructs exact per-draw constants, Z bins and full/opaque
  screen lookup words from explicit manager placements. The conditional
  camera-near clip/cap preparation is also recovered; automatic source-light
  selection and placement ownership remain separate.
- Capture a scene where local shadow/contact and key cloud/gobo/volume branches
  affect Hair pixels so their connected nontrivial outputs can be measured.
- Validate a complete same-frame composed result. Existing exact checks cover
  individual material, lighting, stored-color, denoise and temporal boundaries;
  they do not turn different captured frame intervals into an end-to-end proof.
