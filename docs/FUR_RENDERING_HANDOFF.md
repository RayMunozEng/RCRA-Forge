# Character Fur Rendering Handoff

Latest 2026-09-09: read
[MODELSTRAND_HANDOFF_20260909.md](MODELSTRAND_HANDOFF_20260909.md) before
continuing Ratchet work. It records the recovered tail, sparse-head, and ear
ModelStrand geometry/material path, retail topology evidence, the exact captured
wind-only state, private-desktop validation command, local ignored fixtures,
and the remaining skeletal/persistent-wind/common-frame parity boundary.

Latest 2026-09-05: read [FUR_POSE_STREAMS.md](FUR_POSE_STREAMS.md) for paired deformed-position integration, bounded camera-motion results, static-image regression, and the remaining animated-frame parity boundary. The generic TAA capture is a menu frame, not a fur appearance reference.

For a clean checkout and continuation on another Windows computer, start with
[`FUR_RENDERING_TRANSFER.md`](FUR_RENDERING_TRANSFER.md). This document is the
detailed evidence and implementation log; the transfer document is the
machine-independent operating checklist.

Date: 2026-08-31  
Branch: `main`  
Fork: `https://github.com/RayMunozEng/RCRA-Forge`  
Status: **active experimental renderer; continue improving toward retail parity**

## Latest continuation status â€” 2026-09-04

Read **HAIR_TEMPORAL_RECONSTRUCTION.md** first for the newest result. Guarded
capture event 20572 proves the executable-extracted `CS_TemporalAaApply`
container at runtime, its complete 224-byte cbuffer and all eight native
resource payloads. The independent RDC stream parser and replay export produce
the same `t6` history hash. A direct R11G11B10 dispatch of the recovered shader
matches 4,831,458 of 4,953,600 packed output pixels exactly; red and green are
within one stored code everywhere and blue is within one code at all but four
pixels. The validation also found and fixed a real preview error: the native
global rejection floor applies only to the final blend, while history
selection, broadening and neighborhood confidence use unfloored rejection.
No additional game run is required for this native-resolution TAA boundary.
The same saved capture now closes the next producer boundary. Event 16262's
base disocclusion output feeds event 18704 byte for byte, and event 18704's
final full-resolution result feeds event 18712 byte for byte. The recovered
event-18704 work-queue shader reproduces its RG8 output exactly. The recovered
event-18712 half-resolution process reproduces all four outputs bit for bit
across 1,238,400 pixels. Base event 16262 is exact in green everywhere and in
red at 4,953,528 of 4,953,600 pixels, with every residual one stored code;
its depth history is bit exact. The bounded motion-channel differences and
private replay memory measurements are recorded in
**HAIR_TEMPORAL_RECONSTRUCTION.md**.

Offline recovery of event 16269 `CS_TemporalAaDisocclusionHalf`, event 18687
`CS_AccAlphaHalfResMask` and event 18695 `CS_AccAlphaWorkQueue` is now
complete. The recovered half reduction and mask each match all 1,238,400 R8
pixels bit for bit. The captured mask predicts exactly the 40,940 unique packed
tiles consumed by event 18704; append sequence is scheduler-dependent, while
the set and count are exact. Offline shader validation covers all of these
stages.

The next boundary is the production viewport. Supply live previous-depth,
motion-blur scatter, half-depth extrema, stencil and accumulated-alpha
resources, then compare a composed frame. Do not substitute captured resource
bytes into the general viewport; connect each path from its live producer.

Start with **HAIR_CONNECTED_REPLAY.md**. Native reflection history and combined
material resolve are now connected. The unmodified production packed decode,
scene lighting, GPU store and denoise chain matches all **11,215** captured Hair
pixels exactly at both stored-color boundaries. Fractional neighboring Skin
masks and native gather addressing fix the connected denoise differences.
The viewport now also writes the fifth native RG16F material target from previous
camera and wind state and uses it to reproject preview Hair history; read
**FUR_MOTION_PATH.md** for its evidence and validation boundary. The archived
disocclusion shader independently confirms current-minus-previous velocity.
Continue with a single bounded matched-frame capture, native raster/generated-
motion validation, and the remaining dynamic temporal inputs. The older
milestones below are historical.

Read **HAIR_SCENE_LIGHTING.md** first. Explicit scene light-grid/probe resources,
native BC6 cubes, key radiance and the native cascaded key-shadow atlas now have
a production viewport path. Camera/model/viewport changes invalidate the supplied
lookup. Atlas/contact visibility combines by minimum and preserves environment
light. The full replay with all shared kernels retains **11,215/11,215 exact
stored RGB pixels**. Production packed-buffer and live lifecycle checks passed;
their remaining float differences are documented separately. Next are native
reflection history and combined resolve, then scene/raster/motion/temporal and
composed-frame validation. The requested material-response checkpoint is saved.

Read **HAIR_MATERIAL_RESPONSE.md** for the latest shared material/occlusion,
reflection-frame, transmission and final-resolve changes. They are integrated in
the ordinary viewport and keep the full captured replay at **11,215/11,215 stored
RGB exact**. Native float error decreased to max 4.94719e-5 / RMS 5.25779e-7.
Lighting and denoise now store Hair color at native R11G11B10 precision; the GPU
helper matches all 11,215 native outputs in each pass plus 35 format cases.
Dry/wet/fallback previews and 250 tests pass. The next major work is complete
scene illumination and matched raster/motion/history, followed by composed-frame
validation. Full-frame parity remains open.

The ordinary HDR preview now has separate native material, vector decode and
lighting programs. Read **FUR_DEFERRED_PREVIEW.md** first for the new pass graph,
verification and remaining scope. The pre-motion production material writer
matches its four targets, coverage and hardware depth at **24,226** captured
pixels across four wetness states. The shared material replay, including captured
motion input, matches all five targets at the same pixels. Production vector decoding matches all
**11,215** native normals/strands exactly. The layer-32 sample now clamps correctly,
the reversed lobe normal is corrected, opaque depth bypasses color blending, and
contact/denoise reconstruction includes projection jitter. This supersedes the
inline pack/decode/lighting description below. Full-frame parity remains open.

The complete captured Hair lighting pass now matches **all 11,215 stored RGB
pixels exactly**. The ordinary preview shares the verified lobe distribution,
normalization and Fresnel functions in `core/hair_lobes.glsl`. Shared camera
reconstruction matches all captured positions/view directions and is used by
HairDenoise. See **HAIR_FULL_REPLAY.md** for evidence, float-error limits and the
remaining deferred/scene/temporal work. This is not full-frame parity.
The preview now separates key and environment lighting, applies the shared
native contact kernel only to the key, then denoises and accumulates history.
The contact toggle and environment/non-fur preservation pass focused GPU checks;
all 270 tests and the earlier wet/wind viewport smoke pass. See
**HAIR_CONTACT_REPLAY.md**.
The opaque depth producer was also corrected from reciprocal to linear depth;
explicit fur masks keep opaque pixels out of denoise while allowing occlusion.
All 4,096 tested opaque shader outputs have exact depth and cleared fur fields.

The complete dry captured fur draw now matches all five G-buffer outputs,
hardware depth and coverage exactly at all 6,308 pixels. See the full raster
section in **FUR_CAPTURE_PARITY.md**. Native upper-left raster origin is
essential to this comparison. The preview now uses captured anisotropic
filtering and shared material arithmetic. Wet material controls also match
every target and coverage exactly: 24,226 surviving pixels across 0%, 25%,
50% and 100% wetness. The shared HairDenoise kernel is now integrated and
matches all 11,215 stored pixels, native float RGB values and accumulation sums
exactly; see **HAIR_DENOISE_REPLAY.md** for the fused-arithmetic correction and
current preview limitations.

Read **FUR_CAPTURE_PARITY.md** for the newest geometry/material corrections:
all 128 fur texture subresources match the capture, and all 93,150 checked
vertices agree on visibility. Six material fields (including both coverage
phases and contact depth) match all 6,308 captured pixels exactly. Historical
nearest-even, dry UV dithering, and wetness-based contact-depth claims below
are superseded by the native shader measurements. Packed material output also
matches all 6,308 pixels. The newest correction uses linear view depth, not
reciprocal depth, throughout the preview's contact and denoise buffers. Full
frame parity is pending.

Read `FUR_RENDERING_TRANSFER.md` and `HAIR_INDIRECT_REPLAY.md` for the current
operating state. Historical sections below record earlier limitations; this
continuation has recovered inline and streamed light-grid containers, exact
first-stage decoding, isolated retail interpolation, position hashing, integer
fade packing, and fallback initialization. The ordinary viewport has not yet
adopted the new indirect replay kernels. Full captured-frame parity is unverified.

The complete 354-brick Sargasso candidate is reconstructed, with 1,454,080
records including fallback. Using that installed data, 4,096 queries pass
against the original Hair shader slice (max error 4.7684e-7), and 192 pass
the combined replay upload (max error 1.1921e-7). Valid-entry collision selection
also matches original instructions in 331 cases. The candidate is not a
verified frame-7328 resource; original probe/cube/G-buffer state is still needed.

The original frame-7328 capture was not found and the user does not know its
location. Do not ask again. Fresh gameplay captures now provide Ratchet's actual
Hair event **17544**, its G-buffer, constants, probes, complete light grid and
cube resources. The captured Hair DXIL matches the recovered shader byte for
byte. See [PRIVATE_CAPTURE.md](PRIVATE_CAPTURE.md) for the capture chain.

The replay now accepts native BC6U cube and cube-array blocks, preserving GPU
sampling precision. Sixteen captured Hair queries pass against traced shader
arithmetic with all **64 cube samples independently measured on D3D12**. Maximum
absolute error is **1.1921e-7**; diffuse and coarse luminance match exactly. These
queries exercise full grid fallback and local specular probes, with no local
diffuse-probe contribution. They do not establish full Hair/frame/TAA parity.
RenderDoc's offline debugger mis-sampled all 32 default-cube fetches in this
check (maximum discrepancy 0.41015625); all 32 local-cube fetches matched hardware.
Do not use the debugger's default-cube colors as a renderer oracle.

Captured GPU record 10 / cube 18 is the runtime draw-list probe
`F896FB5315175B7C` in `tile_zz27_lgt.zone` (`9C292F5F8A79EEC2`). The existing record
builder reproduces its first 124 bytes exactly from the cooked asset with an
identity zone matrix; only the camera-dependent Z-bin word is excluded. Ten
captured records match identity placement. This is evidence for those records,
not a general identity-transform assumption. The active cube is generated from
scene draw lists, so it has no baked texture to substitute. Three other captured
cubes match installed atlases across all 36 face/mip subresources each.

The regular viewport now uses native BC6U cube sampling with seamless filtering
and the shared DXIL Hair noise function. The complete captured Hair pass matches
all 11,215 valid stored pixels exactly. See
[HAIR_FULL_REPLAY.md](HAIR_FULL_REPLAY.md) for the native DXBC/DXIL control, measured
output conversion, resolved boundaries, and reproducible evidence. Integration of
scene lighting, the complete deferred G-buffer/direct/shadow path, and retail
temporal reconstruction remains. Changes are local and uncommitted. All private
game/Steam jobs are closed, and the original Exclusive Fullscreen / 3440 x 1440
display preferences were restored and verified. Default remained the user's input
desktop. The native BC6 replay validation tests pass (14 tests), and the full fork suite
now passes **250 tests**. The native-cube/noise viewport GPU smoke also passed.

## User-visible state

The viewer discovers and decodes the special fur material textures used by
Ratchet and similarly authored characters and renders a procedural GPU strand
pass. The renderer is the intended direction of work. Continue improving it;
do not disable or remove fur as a response to remaining parity gaps.

The latest public verification image is:

`docs/verification/ratchet-fur.png`

That image is historical evidence of the initial failure mode, not the current
renderer or an approved target. It was captured from the head-only Ratchet
bangle at LOD1 because the original smoke test deliberately switched from LOD0
to LOD1 to verify texture rebinding. Current results are documented below.

## Commits in this work

- `c0b4ccc` â€” parse and load shipped fur material textures
- `a20bc37` â€” remove incorrect generated shells and hide untextured composite helpers
- `2da9dd7` â€” add the current experimental geometry-shader strand pass
- `38f1a45` â€” update the public verification capture

## Confirmed asset evidence

### Models

- Full Ratchet: `0xADE5909F821E9DDE`
  - `characters/hero/hero_ratchet/hero_ratchet.model`
- Ratchet head bangle used for the focused smoke test: `0xAA4A5371E9C251F7`
  - `characters/hero/hero_ratchet/bangle_set/bangle_head_default/hero_ratchet_bangle_head_default.model`

### LOD0 head geometry

In the head bangle:

- Fur-root surface, material index 2:
  - 18,630 vertices
  - 35,888 triangles
  - 9 connected components
- Ordinary head surface, material index 4:
  - 6,202 vertices
  - 11,664 triangles
- Composite-shell helper, material index 5:
  - 6,519 vertices
  - 11,872 triangles
  - no decoded albedo of its own

The fur geometry is a dense connected surface, not exported individual hair
cards. The separate `compositeshell` mesh must not be drawn as an ordinary
opaque material; doing so caused the large flat pink/white patches seen in an
earlier capture.

### Special material format

Ordinary materials use DAT1 section `0xF5260180`. Fur materials instead use
section `0xD9B12454`, with a 36-byte settings header followed by DAT1 string
offsets. Ratchet's head material resolves four textures:

1. `hero_ratchet_Head_c.texture`
2. `hero_ratchet_Head_n.texture`
3. `hero_ratchet_Head_g.texture`
4. `hero_ratchet_head_fur_control.texture`

The installed executable names the two leading fields `Fur_LayerCount` and
`Fur_LoDReduction`, followed by `Fur_Length`, `Fur_Density`,
`Fur_OffsetScale`, `Fur_GlossScale`, `Fur_SpecularScale`,
`Fur_TransmittanceScale`, and `Fur_WindTurbulence`. These names match the
section's binary layout and observed values; they replace the earlier
provisional interpretations.

Ratchet also has special fur-format materials for limbs and tail whose paths
do not include the word `fur`. Detection must therefore remain based on the
`fur_control` binding, not solely on material-name keywords.

## What is implemented

### Material parsing and texture loading

Files:

- `core/material.py`
- `core/asset_loader.py`
- `exporters/texture_exporter.py`

The parser recognizes `0xD9B12454`, resolves its string-pool offsets, assigns
the `fur_control` role, and sends base color, normal, specular, and control maps
through the normal progressive texture-loading path. This portion worked in
the live app for Ratchet's head, limbs, and tail.

### Viewport rendering

File: `ui/viewport.py`

The viewport:

- uploads `fur_control` as a dedicated GPU texture;
- treats the control binding as the authoritative fur-material signal;
- hides composite-shell helpers from the shaded pass;
- draws the ordinary textured fur-root surface;
- then runs `FUR_VERT_SRC`, `FUR_GEOM_SRC`, and `FUR_FRAG_SRC`.

The geometry stage currently emits three camera-facing ribbon fibers per
source triangle. This is a synthetic approximation, not recovered retail
strand data.

## Original prototype gaps (historical)

These were the confirmed gaps in commit `2da9dd7`. The follow-up sections below
supersede this list: root allocation, authored dimensions, anisotropic lighting,
antialiasing, LOD0 profiling, and OIT have since been implemented.

1. **Invented root distribution** â€” exactly three fibers are emitted at fixed
   barycentric positions per triangle, so density follows mesh triangulation.
2. **Unverified channel semantics** â€” the shader assumes fur-control RG is comb
   direction, B is length, and A is density. That mapping is plausible from
   channel statistics but has not been decoded from the retail shader.
3. **Arbitrary dimensions** â€” strand length and width constants are hand-tuned,
   not read from confirmed material parameters.
4. **Incorrect shading model** â€” fibers use basic diffuse lighting only. There
   is no anisotropic specular response, backscatter, self-shadowing, roughness,
   or strand normal model.
5. **Transparency artifacts** â€” camera-facing ribbons use ordinary alpha
   blending with depth writes disabled and no order-independent transparency.
6. **Aliasing** â€” texture sampling is forced to mip 0 in the geometry shader,
   and there is no alpha-to-coverage, strand-aware antialiasing, or temporal
   stabilization.
7. **LOD sensitivity** â€” root count changes with model triangulation. The
   published capture is LOD1 and therefore does not prove LOD0 quality.
8. **Performance unmeasured** â€” the full Ratchet model has multiple fur
   materials. The head-only model was tested, but full-character strand cost
   has not been profiled.

Lighting contributes to the bad look, but it is not the root cause. The larger
problems are synthetic geometry, unverified control interpretation, arbitrary
strand dimensions, and inadequate transparency/antialiasing.

## Verification already run

- `python -m pytest -q`
  - 72 tests passed after the strand pass was added.
- Live Windows/PyQt/OpenGL smoke test on asset `0xAA4A5371E9C251F7`
  - valid OpenGL context;
  - geometry shader linked successfully;
  - base color and `fur_control` reached the GPU;
  - LOD texture rebinding completed;
  - screenshot captured successfully.

These checks prove that the code path runs. They do **not** prove visual parity.

## Original next steps (historical)

1. Treat `2da9dd7` as an experiment, not a parity implementation. Continue the
   geometric fur pass while reverse engineering improves its inputs and model.
2. Extract and inspect the retail shader/permutation selected by special fur
   materials. Resolve the exact meaning of `0xD9B12454` fields and each
   `fur_control` channel before tuning constants.
3. Determine whether additional strand/root data exists in currently unparsed
   model vertex streams or other DAT1 sections. The current model parser only
   exposes position, normal, and UV inputs to the fur pass.
4. Capture a close LOD0 retail reference and a matching viewer angle. Use that
   as the visual acceptance oracle for silhouette length, density, direction,
   color, and lighting.
5. Once data semantics are known, implement the correct root distribution and
   a strand-appropriate lighting/transparency path. Add screen-space LOD and
   antialiasing before testing the full character.
6. Extend the GPU smoke report with fur-specific evidence: fur material count,
   bound control textures, active fur program, chosen LOD, and strand/root
   counts. Do not rely only on a screenshot.
7. Validate at least Ratchet, Rivet, and one non-hero fur asset before claiming
   generic support.

## Local-only files to preserve

The following files are intentionally untracked and should not be committed or
deleted:

- `hashes.txt.cache`
- `launch_live_game.bat`

`launch_live_game.bat` contains a machine-specific Steam installation path.

## Follow-up: authored settings and area-normalized roots

Work continued on 2026-08-31 with fresh extraction from the installed PC game.

- The `uint32` layer count and `float` LOD reduction at byte offsets 0 and 4,
  plus the seven named floats at byte offset 8 of `0xD9B12454`, are preserved
  on `MaterialAsset` and carried with the fur-control texture to the viewport.
- Cross-asset evidence strongly identifies float 0 as authored maximum fur
  length: Rivet `no_fur` is `0.0`, Ratchet limbs `0.015`, Ratchet ears `0.02`,
  Ratchet head `0.03`, the Schrodinger critter `0.045`, sheep `0.09`, Ratchet
  tail `0.10`, and Rivet head `0.012`.
- `Fur_Density` is used as an area-density scale. Observed examples
  include sheep `3`, Ratchet ears `8`, Ratchet tail `12`, and Ratchet
  head/limbs plus Rivet head `16`.
- The fourth texture binding in the special fur section is treated as the
  control map by position. This fixes the Schrodinger critter, whose binding
  ends in `_fur.texture` rather than `_fur_control.texture`.
- Control blue is the per-texel extrusion multiplier used by the live shipped
  fur vertex shader. The active shell pass uses
  `Fur_Length * control blue * layer depth`.
- Area-normalized root budgets and per-root alpha modulation belonged to the
  retired ribbon experiment. They are not used by the active shell path.
- The fragment pass now includes a restrained tangent-based anisotropic lobe.
  This is a standard strand approximation, not a recovered retail BRDF.
- Ribbon width now retains its authored world-space projection up close but
  has a conservative sub-pixel floor at distance. The fragment pass applies
  derivative-based coverage across each ribbon, replacing broken silhouette
  stipple with continuous antialiased strands without increasing root count.

Reusable verification tool:

`tools/smoke_fur_viewport.py`

Fresh LOD0 results on an RTX 5070 Ti / OpenGL 4.6:

- Ratchet head: 35,888 fur triangles, 69,691 expected area-weighted roots,
  4.81 ms median synchronous frame time across seven samples.
- Full Ratchet: three fur materials, 43,888 fur triangles, 90,627 expected
  roots, 11.76 ms median and 13.81 ms p95 across seven samples.
- Rivet head: two fur materials, 34,744 fur triangles, 92,253 expected roots,
  6.60 ms median and 9.39 ms p95 across five samples.
- Sheep (non-hero): one fur material, 17,364 fur triangles, 42,607 expected
  roots, 4.28 ms median and 5.98 ms p95 across five samples.

After adding screen-space width stabilization and analytic edge coverage, the
same 1024x1024 smoke test produced 12.63 ms median for full Ratchet, 7.83 ms
for Rivet head, and 3.57 ms for sheep across seven samples each. All three fur
programs linked successfully on the NVIDIA driver.

The HDR path now uses weighted blended order-independent transparency for fur.
Two fur-only RGBA16F attachments accumulate weighted premultiplied color and
revealage, then a fullscreen pass composites the result into scene color before
bloom/tone mapping. This removes draw-order dependence without sorting emitted
geometry. Drivers without per-target blending, plus the non-HDR path, retain
the ordinary alpha-blended fallback.

With OIT active, the same smoke test produced 15.12 ms median for full Ratchet,
7.84 ms for Rivet head, and 3.78 ms for sheep across seven samples each. A
forced non-HDR Ratchet-head run also linked and rendered through the fallback.

This paragraph describes the superseded ribbon implementation. The active
viewport path now draws instanced, depth-writing shells; see the recovered
shader and layered-shell follow-ups below.

## Follow-up: retail references and composite-shell evidence

Insomniac's GDC 2022 lighting presentation explicitly calls the production
geometry "fur shells." It also says fur shells were omitted from shadow maps,
with base geometry providing the coarse shadow and screen-space contact shadows
recovering fine strand shadows. Source: [Recalibrating Our Limits: Lighting on
Ratchet & Clank: Rift Apart](https://media.gdcvault.com/GDC%2B2022/Speaker%2BSlides/RecalibratingOurLimits_Mullen_Brian.pdf).

The installed model data supports treating `compositeshell` meshes as cooked
outer envelopes/proxies rather than ordinary visible surfaces:

- Ratchet's tail surface and shell each contain 2,031 vertices / 3,904
  triangles. Nearest-surface shell displacement has median magnitude `0.01872`,
  median normal component `0.01802`, and median tangential component `0.00073`.
- Ratchet's limb surface and shell each contain 2,182 vertices / 4,096
  triangles. Their median values are `0.01003`, `0.00994`, and `0.00113`
  respectively.
- Ratchet's head shell is a lower-resolution combined proxy (6,519 vertices /
  11,872 triangles) around the 18,630-vertex / 35,888-triangle fur surface.
  Rivet likewise has one combined shell around separate head and ear surfaces.

The live event-32398 vertex shader resolves the earlier static-disassembly
ambiguity: it samples component 2 (blue) for shell displacement and for the
wind gate. Exported channel images agree with that data flow: blue contains the
sparse authored cheek/ear/face length envelope, while alpha is nearly white.
The proxy measurements remain useful geometric evidence for predominantly
normal shell expansion only.

## Superseded next steps

These items were completed or replaced by the later dated sections. The active
remaining gaps are local scene-probe/light-grid blending, production shadow
atlas/GI inputs, and production TAA history rejection/reprojection. Ratchet,
Rivet, and Sheep remain the required live verification set.

Two additional installed textures are named
`hero_ratchet_head_fur_mask_m.texture` and
`hero_ratchet_tail_fur_mask_m.texture`. Their RG channels are effectively
neutral and blue contains mask-like variation. A scan of all 187 installed
Ratchet-named materials found no path binding to either texture, and the only
fur-named material graph in `hashes.txt` is absent from the installed TOC.
These are therefore auxiliary/legacy evidence, not a basis for replacing the
active four-channel `fur_control` binding.

## Follow-up: shell-envelope root contact shadow

The strand fragment pass now applies a restrained analytical contact shadow at
the fur root. Its strength is scaled by control blue, matching the recovered
shell-extrusion multiplier, and fades fully by 52% of strand length. It runs
identically through weighted OIT and the ordinary-alpha fallback.

This analytical term is a shell-envelope-informed approximation, not the
production screen-space contact-shadow algorithm described by Insomniac. The
depth-backed screen-space complement is documented below.

## Follow-up: screen-space fur contact shadow

The HDR path now copies opaque depth from its renderbuffer into a detached
`GL_DEPTH_COMPONENT24` texture before drawing fur. Keeping the sampled texture
detached avoids the undefined feedback loop that would result from sampling the
same depth image currently attached for depth testing. Allocation and copying
are capability-gated; failure leaves the analytical root term and ordinary
alpha fallback intact.

The strand fragment pass samples three opaque-depth points at 1.5, 3, and 5
physical pixels toward the projected key light. Only geometry closer than the
strand by a derivative-scaled depth bias contributes occlusion, and the effect
fades toward the outer shell. The exact-camera Ratchet-head comparison changed
11,776 pixels relative to the analytical-contact baseline, all toward darker
values, with a mean changed-pixel delta of `-1.46` and maximum delta of `-17`.
The smoke report exposes `fur_screen_space_shadow` so future runs prove that
the depth-backed pathâ€”not just the shader programâ€”was active.

On the RTX 5070 Ti, the 1024x1024 full-Ratchet LOD0 smoke test kept all three
fur materials active and measured `12.22 ms` median / `13.26 ms` p95 across
seven synchronous samples. The forced non-HDR run reported the screen-space
term disabled and rendered successfully through the analytical-shadow and
ordinary-alpha fallback. Models without drawable fur skip the depth copy.

## Follow-up: stable screen-space root LOD

The geometry pass now projects each material's authored maximum fur length at
the triangle center. Root density stays full at six physical pixels or more,
smoothly thins below that threshold, and retains a 25% floor below one pixel.
The existing deterministic per-triangle hashes provide a stable disappearance
order as the camera moves instead of selecting a new random subset each frame.

The smoke report independently reproduces the projection and reports expected
post-LOD roots, retention, and projected-length quantiles. The close Ratchet
head retained `99.85%` of its area-normalized roots. Full Ratchet at the normal
framed distance retained `96.71%`; a four-times-farther stress view retained
`49.86%` without removing the fur silhouette. The normal full-character run
measured `12.78 ms` median across five synchronous 1600x1200 logical samples.

## Follow-up: taper, root coverage, and removal of unvalidated layers

The ribbon's physical width and anti-aliasing floor now both reach exactly zero
at the mathematical tip. This removed the prior blunt half-pixel cap. The
per-triangle root cap increased from three to six while keeping the existing
area budget, because the old cap visibly saturated large triangles. The close
Ratchet report consequently increased its expected area roots from `69,691` to
`100,803`; the retained implementation measured `5.87 ms` median at the same
1600x1200 logical camera.

An intermediate undercoat/guard split, gravity term, UV clump bend, and random
color variation were removed. Their constants had only promotional-image
visual justification, not a decoded retail field. Strands now terminate at the
directly supported `authored length * alpha` envelope and sample authored base
color without synthetic tuft modulation. Root width remains a renderer/raster
approximation because no cooked strand-width field has been recovered.

## Recovered retail shader semantics

The installed executable contains DXBC for `VS_ModelFurShellGBufferDeferred`
and `PS_FurShellGBufferDeferred`. Microsoft FXC disassembly establishes the
runtime behavior directly:

- `ModelFurCB` contains `m_BaseOffsetMapScale`, `m_InverseLayerCount`,
  `m_Length`, `m_WindStrength`, and `m_WindTurbulence`.
- Each shell is an instance. The vertex pass culls most front-facing shells,
  retains all grazing-angle shells, renormalizes the survivors, and passes a
  0-32 array-slice coordinate to the pixel shader.
- The live vertex shader samples fur-control blue and multiplies it by
  normalized layer depth and `m_Length` for normal extrusion.
- The pixel shader decodes fur-control RG from `[0,1]` to `[-1,1]` for combed
  normal construction. It samples `g_FurLayerMap` as a `Texture2DArray` and
  clips pixels stochastically from that result. Control B scales fur length and
  the packed contact-depth offset; control A independently participates in the
  tangent-shift/material interpolation rather than shell extrusion.
- The layer texture is registered by the executable as `Default Fur Shells`.

The complete recovered equations, varying map, wetness path, two discard
conditions, packed outputs, and six-instruction depth composite are recorded in
`work/fur-analysis/RECOVERED_FUR_PIPELINE.md` in the research workspace.

## Current implementation: recovered shell volume and pass

The active viewport now uses the game's procedural `Default Fur Shells` volume,
not a guessed noise texture or ribbon substitute. Static analysis of
`TextureDefaultsInit` in the installed executable recovered the full generator:

- a 128x128x32 scalar volume with four stored levels per slice (128, 64, 32,
  and 16), packed at a 0x5500-byte stride;
- fixed xorshift128 state `075BCD15 159A55E5 1F123BB5 05491333`;
- one 24-bit random value per XY texel, mapped to strand height as
  `min(floor(float32(random24)^2 * 2^-43) + 1, 32)`;
- for each surviving layer `i`, byte coverage
  `255 * clamp(1 - 0.8 * max(2*(i+1)/height - 1, 0)^2, 0, 1)`;
- zero above the selected height and 2x2 integer-average mip generation.

The viewport uploads that exact volume and its executable-defined integer mip
chain, draws source triangles as shell instances, uses the recovered
control-map extrusion/groom equations, and applies stochastic opaque coverage.
Halton projection jitter and a 32-sample temporal accumulator provide a
practical reconstruction in the editor. The recovered reciprocal-depth contact
ray, HairDenoise gather, direct Hair lobes, default-probe indirect term, and
exact BRDF lookup are active. Local scene-probe blending and the production TAA
history rejection/reprojection remain incomplete. There is no sheep-specific
shader or invented grazing mask in the active shell pass.

Correction on 2026-09-03: this earlier implementation misread `round_ni`.
It is floor, not nearest-even. The current shader uses top-left D3D pixel
coordinates, `TemporalPlusCycle`, and a native fused X offset. The generated
phase now matches all 6,308 surviving pixels of the captured head draw exactly.
See `FUR_CAPTURE_PARITY.md` for the evidence and scope.

Sheep uses the same executable shell pass, but not the same visual treatment.
Its installed material is 9 cm / density 3 / offset 0 over an authored curly
wool surface. Ratchet and Rivet use short 1.2-3 cm, density 12-16, directionally
groomed fur. The renderer therefore keeps Sheep's curly base and long sparse
fringe rather than applying a Lombax preset.

Earlier comparison captures are `ratchet-exact-stratified-v25.png`,
`rivet-exact-stratified-v25.png`, `sheep-exact-stratified-v25.png`, and
`ratchet-full-exact-stratified-v25.png`. The full-character smoke run exercises
three distinct Ratchet fur materials and 1,296,528 rendered shell triangles.
Smoke reports identify the layer source as `recovered_procedural_128x128x32`
and count Sheep's shell instances as rendered shells.

## 2026-09-01 exact-frame and controlled-capture update

The 16-byte RCRA vertex stream now supplies the complete authored tangent frame
used by retail instead of deriving handedness from UVs. `NXYZ[20:30]` stores
tangent X, `abs(W)&0x3ff` stores tangent Y, bit 30/31 store tangent/normal Z
signs, and the sign of W stores handedness. The high W bits also provide the
position-decode correction used by the vertex shader's shell-budget equation.
Measurements on the installed Ratchet, Rivet, and Sheep fur meshes keep median
`abs(dot(N,T))` below 0.008; the previous UV-derived handedness was opposite the
retail value on essentially every sampled Ratchet fur vertex.

Two additional DXBC mismatches were removed:

- `dp2(r.wwww,r.wwww)` makes shell availability
  `min(2*(1-front)^2+0.1,1)`, not `(1-front)^2+0.1`;
- both stochastic hashes use screen coordinates normalized by inverse viewport
  dimensions, and the dry material path still dithers the fur-layer UV divisor
  between 1 and 1.375.

The texture uploader now preserves the game's authored block-compressed mip
chain instead of regenerating it from mip 0. RCRA stores the upper HD levels
and the SD tail separately; for Sheep's 2048 BC1 maps this reconstructs the
exact 2048, 1024, 512, 256, 128, 64, 32, 16, and 8 levels.

The fur material's deferred-lighting routing is proven from matching bitfields:
the fur pixel shader ORs `0x6000` into G-buffer normal/spec word 0, setting the
three-bit shading-model field at bit 13 to value 3. The executable's
`CS_ApplyGBufferLighting_Hair` extracts those same three bits and rejects any
pixel whose value is not 3. The editor now evaluates the recovered Hair direct
lobes and captured default environment/BRDF terms in its forward shell pass.
Production local light-grid selection, local-probe blending, shadow atlases,
GI, and screen-space occlusion history remain separate parity work.

Automated captures now keep the Qt widget off-desktop and non-activating, apply
camera overrides before convergence, and verify the 32-frame history before
capturing. Current controlled results are
`ratchet-retail-authored-mips-v47.png`,
`rivet-retail-authored-mips-v47.png`,
`sheep-retail-full-authored-mips-v46.png`, and the
256-frame diagnostic `sheep-retail-steady-state-v40.png`.

The Sheep result is still not retail-presentable. A one-shell diagnostic
(`sheep-fur-base-shell-v41.png`) shows a clean authored curly surface; the
radial structure appears only when the outer shells are composited and remains
after 256 stationary frames. This rules out insufficient convergence and bad
base UVs. Further visual parity work must reproduce the production G-buffer,
deferred fur lighting/depth composite, contact shadows, and TAA behavior rather
than introduce a guessed wool preset or alter the proven 9 cm / density 3 /
offset 0 material. Controlled A/B captures also show that exact ties-to-even
screen rounding and the complete authored HD+SD mip chain do not remove the
radial structure; those two causes are now ruled out.

## 2026-09-01 grooming, weather, and Hair-depth update

The installed shaders prove that grooming, wind, and water are separate parts
of the same shell pipeline:

- Fur-control RG constructs the groomed tangent-frame normal and offsets the
  layer-volume lookup along the authored comb direction. The stable geometric
  normal remains in `GBufNormalSpec`; the groomed normal is packed separately
  in `GBufExtra` for `CS_ApplyGBufferLighting_Hair`.
- A second, 337-instruction fur vertex permutation consumes
  `m_WindStrength`, `m_WindTurbulence`, `GlobalWorldCB.m_WindVec`, shader time,
  and the scene object's packed random half. It deforms current and previous
  strand normals and writes motion-vector inputs. The viewport implements the
  proven tangent-plane bend, 0.0075 m activation threshold, x50 ramp, and
  `(d*d + 0.4*d)` shell-depth curve. The captured object record supplies the
  exact half-float phase `0.1326904296875`; the viewport accepts it as runtime
  state instead of fabricating one. Installed Ratchet, Rivet, Sheep, and
  critter materials all carry authored turbulence 0; wind strength is runtime
  state.
- `MaterialFurCB.m_Wetness` changes the layer-UV divisor, expands the layer
  field into larger clumps, darkens albedo by shell depth, and changes the
  control-blue custom reciprocal-depth offset. Those recovered equations are
  active behind `Viewport3D.set_fur_weather`; static inspection remains dry.

The mini Hair target is now RGBA32F and receives reciprocal depth from ordinary
geometry plus the fur shader's exact control-blue/wetness offset. The recovered
four-tap contact ray must compare `rcp(rayDepth) - sampledReciprocalDepth` at
each quarter tap. An earlier linear-depth comparison was wrong and created
broad dark bands. Correcting the units reduced the controlled Ratchet A/B mean
absolute delta from 3.03 to 0.85 levels and reduced pixels above a 24-level
change from 160,561 to 42. The corrected contact is enabled; broad-band
captures from v62-v71 are rejected diagnostics. Current checks are
`ratchet-reciprocal-contact-v72.png` and
`sheep-reciprocal-contact-v73.png` in the task output directory.

Wetness and wind controls are exposed by `tools/smoke_fur_viewport.py` as
`--fur-wetness`, `--fur-wind-strength`, and `--fur-wind-vector`. Captures use
an off-desktop, non-activating Qt tool window and must stay that way.

## 2026-09-02 live-groom, HairDenoise, wind, and environment update

The live frame-7328 draw at event 32398 settled the control-channel ambiguity.
The vertex shader uses fur-control blue for extrusion and wind response; the
pixel shader retains RG for comb direction and alpha for an independent
tangent/material interpolation. Using alpha for extrusion inflated nearly the
whole head uniformly and is a rejected implementation.

The exact captured weather state was `m_WindStrength = 0.030973274260759354`,
world wind `(-0.9966111779, 0, 0.0822560638)`, shader time
`104.03866577148438`, and object phase `0.1326904296875`. The viewport now uses
the recovered 64-vector cubic procedural field, spatial sine frequencies,
radius cap, tangent-plane bend, control-blue gate, and shell-depth curve.

The Hair compute dispatch (`5ff73b6b2aca9640cf18cd78b88ba3c0`) and its
HairDenoise pass (`d1bd89676f0e3560ee38fd16c950de23`) were recovered from the
same capture. The active path implements the direct primary, secondary,
diffuse, and transmission equations plus the captured three-step tangent/depth
mask gather.

Hair's default indirect inputs were exported and validated independently. The
installed `0x8F083136CEB5FB07` BC6 cube is face-major with six complete mip
chains; CPU BC6 decode matched RenderDoc's face images to at most `0.00048`
normalized mean absolute error. `Default Brdf Lookup` slice 0 is retained as
the exact 64x64 RG16F payload with SHA-256
`4fa9755a296ec4c8c11d19e62598217eedd8625814bb75128c947ca325038672`.
Fur models load these resources in the background through the ordinary Forge
asset path. The capture also used one local probe, whose spatial blending is
not yet reproduced in the isolated model viewer.

The local selection was subsequently traced without guessing. Intersecting
`g_EnvProbeLookupView` with the captured Hair mask shows Ratchet's central fur
tiles carry bitmask `0x40400`, i.e. records 10 and 18. The shader processes the
lowest set bit first. Ratchet's recovered head center
`(-230.588, 9.146, 670.816)` lies inside record 10's full-weight interior, so
the head resolves to record 10 / cube-array index 14 before the broader record
18 or default probe contributes. The smoke harness can inject the exact
captured cube-14 faces and mips with `--fur-environment-dds-dir` and
`--fur-environment-cube 14`; this is capture verification, not a fabricated
generic model-viewer preset.

The only other named Malinon probe candidate in the installed catalog,
`0x837545B07B72296F`, was tested as both lat-long and octahedral input across
all 24 proper axis rotations. Its best correlation to runtime cube 14 was
`0.09` and relative mean absolute error remained above `0.92`, so that mapping
is rejected. The later atlas recovery below proves those projection tests
used the wrong layout; they do not rule out the asset itself as a candidate.
Automatic archive reconstruction of arbitrary local probe arrays remains
unresolved.

## 2026-09-02 second-computer baseline and cooked probe dependencies

The fork was updated to `10b3b26` on the second Windows computer. Its installed
game is available and the pre-change suite passed all 91 tests. Off-desktop
GPU verification runs on an NVIDIA RTX 5060 Ti / OpenGL 4.6.

The transfer smoke command exposed a verification bug: it loaded model textures
but omitted the default Hair environment that `AssetLoader` loads in the app.
Its report showed `fur_environment.gpu_ready = false`. The app and smoke tool
now share `core.asset_loader.load_fur_environment`, using the installed
`0x8F083136CEB5FB07` cube and embedded exact BRDF. Reports include the source,
face/mip counts, and BRDF SHA-256. Missing default resources or a failed GPU
upload fail the smoke run; `--disable-fur-environment` is an explicit control.
Captured environment overrides no longer need a separately transferred BRDF
DDS unless deliberately overriding the embedded lookup.

At the same Ratchet camera, adding the omitted environment changed 139,565
pixels, with full-image mean absolute RGBA delta 2.215 levels and maximum
channel delta 115. This corrects the verification path, not the retail lighting
model. No fur shader constants or character presets were changed.

All four corrected LOD0 runs report a valid GL context, active shell program,
33 accumulated samples after framebuffer capture, six environment faces with
six mips each, the expected BRDF hash, and `gpu_ready = true`:

| Model | Asset ID | Fur materials | Rendered shell triangles | Median synchronous frame ms |
| --- | --- | ---: | ---: | ---: |
| Ratchet head | `AA4A5371E9C251F7` | 1 | 1,148,416 | 4.72 |
| Full Ratchet | `ADE5909F821E9DDE` | 3 | 1,340,416 | 7.00 |
| Rivet head | `B1C377CA094E4902` | 2 | 1,111,808 | 6.28 |
| Sheep | `959F9CE032472D83` | 1 | 555,648 | 4.73 |

These five-sample synchronous timings describe the smoke runs, not a retail
performance comparison. The images were inspected; Sheep still needs the
production lighting/composition/history work described above.

Exact corrected capture command, run from the fork directory, with the
machine-local game and output paths set in PowerShell:

```powershell
.\.venv\Scripts\python.exe tools\smoke_fur_viewport.py `
  --game-root $GameInstallPath --hashes .\hashes.txt `
  --model 0xAA4A5371E9C251F7 --lod 0 --samples 5 --converge-samples 32 `
  --width 1024 --height 1024 `
  --output (Join-Path $TransferOutputPath 'default-ratchet-head.png') `
  --report (Join-Path $TransferOutputPath 'default-ratchet-head.json')
```

Use the other table IDs and corresponding `default-ratchet-full`,
`default-rivet-head`, and `default-sheep` output names for the remaining runs.
This computer's generated evidence is under the enclosing workspace's
`artifacts/rcra-fur-continuation/`, outside the fork's tracked tree.

Static analysis also recovered the zone probe record, texture-reference, and
per-face scene draw-list layouts. Details and executable anchors are in
[ENVIRONMENT_PROBES.md](ENVIRONMENT_PROBES.md). The new parser and
`tools/analyze_environment_probes.py` scanned 2,192 installed zones, resolving
85 probes in 42 zones without errors: 56 texture-backed and 29 with runtime
scene draw lists. This establishes why texture-name searches alone cannot
recover every runtime local cube. At this stage it had not matched a record to
the older captured cube 14; the later fresh-frame provenance section resolves
record 10 / cube 18 for its separate event.

The suite now has 104 passing tests, including resource-loading failures,
condition-dependent probe texture indices, 64-bit per-face scene IDs, and
malformed probe sections. Next work should match the captured probe records
against this inventory, then reconstruct the appropriate texture or scene
rendering path before implementing spatial blending.

## 2026-09-02 baked probe atlas recovery

The texture-backed path is now decoded from executable evidence.
`CS_CopyEnvProbe` copies complete BC6 blocks from one 1024 x 512 atlas into
six cube faces. The destination array allocation independently establishes
256 x 256 faces and six mips down to 8 x 8. The atlas contains all 36
subresources; its declared single mip is not the cube's mip count.
[ENVIRONMENT_PROBES.md](ENVIRONMENT_PROBES.md) records the shader hash,
registration and allocation addresses, exact copy equations, and source
rectangles.

`core/texture.py` now recognizes the recovered BC6U/planes-4/array-size-1
atlas signature and extracts the original blocks in D3D face order. The
existing RGB16F decode preserves HDR values. The conventional default cube
path remains intact. Smoke reports now state the source layout and face size,
so an installed atlas override is distinguishable from a captured cube or
the installed default.

All 60 distinct installed texture variants referenced by the 56
texture-backed probes in the inventory were checked. Every one of their
2,160 face/mip outputs exactly matched both the original block rectangles and
the pixels obtained by independently decoding the full atlas. The Malinon
Day example has linear HDR values up to 195.0, which survive the RGB16F path.
Twelve new regression cases cover packing, orientation, unused blocks,
malformed payloads, classification, and active HD data. The suite passes all
116 tests.

Four off-desktop LOD0 GPU runs explicitly selected installed texture
`0x837545B07B72296F`. Each used the same camera and render state as its
previous default-probe run, six 256 x 256 cube faces with six mips, the exact
embedded BRDF, 33 accumulated samples after capture, and a successful GPU
environment upload. Images were inspected.

| Model | Changed pixels vs default probe | Full-image mean absolute RGBA delta | Median synchronous frame ms |
| --- | ---: | ---: | ---: |
| Ratchet head | 139,139 | 1.226 | 6.15 |
| Full Ratchet | 34,345 | 0.336 | 6.81 |
| Rivet head | 139,922 | 2.956 | 8.30 |
| Sheep | 218,013 | 5.817 | 6.77 |

The deltas measure the explicit environment substitution, not agreement with
retail. The five-sample timings are smoke evidence, not a performance
comparison. A fresh Ratchet head run using the normal default environment
produced **identical RGBA pixels** to its pre-atlas baseline. Fur geometry,
grooming, character materials, wind, and lighting equations were not changed.

Reproduce the focused override with:

```powershell
.\.venv\Scripts\python.exe tools\smoke_fur_viewport.py `
  --game-root $GameInstallPath --hashes .\hashes.txt `
  --model 0xAA4A5371E9C251F7 --fur-environment 0x837545B07B72296F `
  --lod 0 --samples 5 --converge-samples 32 --width 1024 --height 1024 `
  --output (Join-Path $TransferOutputPath 'atlas-ratchet-head.png') `
  --report (Join-Path $TransferOutputPath 'atlas-ratchet-head.json')
```

Use the prior model table's other IDs and `atlas-ratchet-full`,
`atlas-rivet-head`, or `atlas-sheep` names for the remaining captures.
This computer's evidence is in the enclosing workspace's
`artifacts/rcra-fur-continuation/baked-probes/`: shader containers/disassembly,
the atlas/face preview, `atlas-validation.json`, the four PNG/JSON captures,
`default-ratchet-control.png/json`, and `smoke-comparison.json`.

This recovery corrects the earlier Malinon comparison's premise: the source
is a face/mip atlas, so lat-long and octahedral projection correlations do
not decide its identity. The older frame-7328 cube 14 remained unmatched at
this stage. The later fresh-frame join identifies record 10 / cube 18 as a
runtime draw-list probe and identifies the Malinon Day atlas as inactive cube
40 in that frame. Runtime draw-list probes still need the scene-rendering path;
deferred Hair composition and dynamic production TAA inputs remain unfinished.

## 2026-09-02 local-probe spatial records and Hair weighting

The exact captured Hair DXIL hash `5ff73b6b2aca9640cf18cd78b88ba3c0` was
located in the installed `CS_ApplyGBufferLighting_Hair` shader container.
Its paired DXBC supplies the local-probe code and reflected 128-byte GPU
record layout. The manager's executable code independently connects those
fields to the cooked zone records. Full offsets, addresses, and equations
are recorded in [ENVIRONMENT_PROBES.md](ENVIRONMENT_PROBES.md).

The cooked parser now exposes half extents, capture offset, directional
falloffs, half-float proxy bounds, shape, diffuse flag, and priority.
`core/probe_lighting.py` adds explicit row-vector zone transforms, handedness,
the runtime sort key and residency fade, GPU record parsing/writing, box and
cylinder weights, and ordered Hair specular sample weights. The latter
preserve subtractive remaining coverage, sample normalization, and the final
default-probe blend. `tools/analyze_probe_buffer.py` evaluates actual raw GPU
buffers using a world point and lookup mask, including masks spanning words.

The helper requires an explicit zone matrix, actual resident cube slot, and
fade. The viewport has not yet been connected to these local-probe helpers.
Parallax directions, diffuse accumulation, and scene rendering for runtime
draw-list probes remain unfinished.

Verification passed **137 tests**, including an end-to-end buffer CLI check.
The expanded scan processed 2,192 zones with zero errors and found 85 probes
in 42 populated zones: 84 box records, one cylinder, and seven with diffuse
contribution enabled. An offscreen GLSL instruction translation of Hair's
spatial branch checked **47,229 points** on the RTX 5060 Ti. Maximum CPU/GPU
absolute difference was **4.887581e-6**, mean **2.651224e-9**, with all weights
finite. Identity zone matrices were used only to isolate the kernel.

Evidence is in the enclosing workspace's
`artifacts/rcra-fur-continuation/spatial-environment-probes.json` and
`probe-analysis/`, including shader containers/disassembly,
`verify_probe_weights_gpu.py`, and `probe-weight-gpu-validation.json`.
Pytest used a fresh workspace `--basetemp` because this sandbox cannot access
the existing system pytest temporary directory.

Next steps, in order:

1. Recover the original raw `g_EnvProbeEnvs` buffer and owning zone placement,
   or capture fresh resources through the established private-desktop route
   and use that capture's own point/mask. The original frame's resources
   remain absent on this computer.
2. Run the buffer analyzer against point `(-230.588, 9.146, 670.816)` and mask
   `0x40400` only with the original frame-7328 bytes. Correlate the resulting
   geometry/zone transform with the cooked inventory and compare cube mips.
3. Connect verified records and cubes to the viewport with retail parallax,
   residency/order, and diffuse handling, then repeat matched-camera Ratchet,
   Rivet, and Sheep comparisons.
4. Continue deferred composition and production temporal-history recovery.

Report concrete next steps before requesting user input, as requested in
this task. These changes remain local and uncommitted at this handoff point.

## 2026-09-02 Hair probe sampling and environment-normal correction

Continued the zone-placement trace. Zone instances are `0x270` bytes, with
their matrix at `+8`. The initializer writes identity, but a verified
zone-loading component path replaces it with its owner's matrix through
`0x1413CF430` / `0x1413CACB0`. The serialized reference is copied from input
`+0x14` to component `+0x4C` at `0x1413CEF00`. The owner is at component
`+0x10`; its first pointer supplies the matrix. This confirms another runtime
input without establishing any particular cooked zone's final placement.
Detailed anchors and the extracted `i29.level` location are recorded in
[ENVIRONMENT_PROBES.md](ENVIRONMENT_PROBES.md).

The exact Hair shader's parallax, diffuse coverage, and visibility equations
are now implemented in `core/probe_lighting.py`. `probe_sampling_plan()`
reports gloss-dependent specular mip/capture-offset scale, box-projected
specular and diffuse vectors, the separate unprojected mip-5 luminance fetch,
and independent specular/default and diffuse/light-grid weights. The raw
buffer CLI accepts `--reflection-direction`, `--shading-normal`, and
`--average-gloss` together to produce this plan. Undefined signed-zero ray
cases are explicit JSON nulls with finite flags; no arbitrary epsilon is
inserted into the shader equations.

`hair_probe_specular_visibility()` recovers the light-grid scalar/coarse-cube
luminance ratio. It requires actual inputs. These helpers are not yet wired
to local resources in the viewport and do not reconstruct the light grid,
BRDF inputs, runtime residency, or captured cube identity.

One visible correction **is** integrated: the environment normal now blends
using `(primaryGloss + secondaryGloss) * 0.25 + 0.5`. The previous code first
averaged the gloss values and then still used 0.25, halving their effect.
The variable was renamed `averageGloss` to describe what the shader supplies.

Verification:

- **153 tests passed** in 1.94 seconds; `git diff --check` passed.
- Offscreen GPU verification used 85 distinct installed probes and two
  synthetic rotated/mirrored records, with 22,794 queries and **45,588
  parallax vectors**. 45,333 vectors were finite; 255 signed-zero degenerate
  vectors matched the GPU's NaN/signed-infinity classifications. Maximum
  normalized-direction error was `3.576279e-7`; the actual viewport normal
  expression matched the independent DXBC equation within `2.831221e-6`.
- Four installed-default smoke captures passed with six faces/six mips,
  embedded exact BRDF, successful GPU upload, and 33 temporal samples.
  Cameras, material counts, and rendered shell counts match prior defaults.

| Model | Mean absolute RGB8 change | Max RGB8 change | Median frame ms |
| --- | ---: | ---: | ---: |
| Ratchet head | 0.315918 | 15 | 8.05 |
| Full Ratchet | 0.080984 | 14 | 6.57 |
| Rivet head | 0.199746 | 13 | 6.11 |
| Sheep | 0.424481 | 55 | 4.93 |

All four PNGs were visually inspected. These are controlled viewer
comparisons, not matched retail frame renders. Evidence in the enclosing
workspace is under `artifacts/rcra-fur-continuation/probe-sampling/` (model
PNGs/JSON/logs and `smoke-comparison.json`) and `probe-analysis/`
(`verify_probe_sampling_gpu.py`, `hair-probe-sampling.comp`,
`probe-sampling-gpu-validation.json`). The GPU kernel used identity matrices
only to isolate the equations; it does not assert actual zone placements.

Exact smoke command, run from the fork (replace model/name for each case):

```powershell
.\.venv\Scripts\python.exe tools/smoke_fur_viewport.py `
  --game-root 'F:\SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart' `
  --hashes .\hashes.txt --model 0xAA4A5371E9C251F7 --lod 0 `
  --samples 5 --converge-samples 32 --width 1024 --height 1024 `
  --output ../../artifacts/rcra-fur-continuation/probe-sampling/ratchet-head.png `
  --report ../../artifacts/rcra-fur-continuation/probe-sampling/ratchet-head.json
```

RenderDoc is installed locally, but no original RDC or private-desktop
capture helper was found in this workspace. The user-provided
`launch_live_game.bat` launches Forge, not the retail game. No retail game
was launched or hooked. The original frame-7328 buffer/resources remain
unavailable here.

Next steps:

1. Follow the zone-loading component's owner to its serialized scene-node
   transform and zone association. Start from the saved `0x1413CEF00` and
   `0x1413CF430` trace rather than repeating the probe manager analysis.
2. Recover the original GPU probe buffer/cubes and light-grid resources, or
   establish a private-desktop capture route for a fresh frame. Use that
   frame's own point, lookup mask, and Hair vectors; retain the original
   `0x40400`/cube-14 association only for the original capture.
3. Match record geometry and cube contents, then integrate the recovered
   sampling/blending helpers with explicit residency and the real light-grid
   RGB/scalar inputs. Repeat controlled Ratchet/Rivet/Sheep comparisons.
4. Continue deferred composition and production TAA recovery afterward.

All changes remain local and uncommitted. Report these next steps before
requesting any user input.

## 2026-09-02 continuation: indexed scene models and runtime draw dependencies

The owning-zone trace led through the gameplay owner's lazy renderer-node
creation (`0x140F17BF0` / `0x1412A8430`) and exposed incorrect assumptions in
Forge's art-zone parser. `core/zone.py` now follows the explicit model offsets
in `0x6987F172` into `0x06ABCAB2`. There is no 32-byte scene header and no
single stride across mixed node types. The model table contains parallel
u64 asset IDs and u32 string offsets (`12*n` bytes), not one u64 array.

Model entries now retain the full row-vector matrix, serialized size, scene
offset, and 64-bit scene instance ID at `+0x100`. The signed model index is at
`+0x110`. `core/level_assembler.py` preserves the full matrix in exports,
including nonuniform scale and reflections, instead of reconstructing a
rotation from one axis. The matrix remains zone-local until an actual owning
zone matrix is established. The old GP interpretation remains legacy code
and must not be used as evidence for probe geometry or placement.

`tools/analyze_environment_probes.py --resolve-scene-models` now resolves
runtime probe draw IDs against indexed model definitions in the selected
installed zones. The report includes all candidates, their matrices and
model installation status, per-face match counts, unresolved IDs, and IDs
with multiple candidates. It does not infer active zones or residency.

Verification:

- **164 tests passed** in 2.59 seconds, including 11 new indexed-node and
  matrix/export regressions. `git diff --check` passed.
- The production CLI scanned **2,340 zones** and parsed **177,404 indexed
  models in 163 zones**, with **zero parsing errors**.
- **12,434 of 14,526 distinct draw IDs matched**, giving 13,090 candidate
  records. All candidate zone IDs, scene offsets, model IDs, and matrices
  matched an independent raw-section scan exactly.
- **639 IDs had multiple candidates; 2,092 remained unresolved** within this
  scope. 45 matched candidates refer to uninstalled models and are marked
  as such. Two missing model references appear in 19 zone tables; that is
  separate from record parsing.
- The broader `malinon` filter includes overlays and produced 52 probe zones
  containing 110 texture-source and 29 runtime-source records. This differs
  from the earlier narrower 2,192-zone inventory without changing the format.
- No fur shader changed in this increment. The previous controlled Ratchet,
  Rivet, and Sheep captures remain the visual baseline. No retail game was
  launched or hooked, and no private-desktop capture helper was added.

Evidence is in the enclosing workspace under
`artifacts/rcra-fur-continuation/probe-analysis/`:
`resolved-environment-probes.json`, `scene-dependency-validated.json`,
`scene-model-validation-summary.json`, and the saved executable disassembly.
`scan_scene_dependencies.py` plus `complete_scene_validation.py` preserve the
independent analysis. The first scan's `scene-dependency-scan.json` included
missing-asset assertions as errors; the validated report separates those
missing dependencies from parsing and includes the affected zones.

Reproduce the production report from the fork:

```powershell
.\.venv\Scripts\python.exe tools/analyze_environment_probes.py `
  --game-root 'F:\SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart' `
  --zone-filter megalopolis --zone-filter malinon --resolve-scene-models `
  --output ../../artifacts/rcra-fur-continuation/probe-analysis/resolved-environment-probes.json
```

Next steps:

1. Replace the legacy GP guesses with the verified 32-byte actor-instance
   records in `0x70682CB8`, actor reference table `0x78684035`, and component
   bindings in `0x50EDC53D`. Follow the zone-loading component to its owning
   scene definition and level/zone association. Exact offsets and consumer
   addresses are in [ENVIRONMENT_PROBES.md](ENVIRONMENT_PROBES.md).
2. Resolve the remaining scene IDs and choose model candidates using the
   active zone set. Recover the original capture's probe/cube/light-grid
   resources or establish a private-desktop route for a fresh capture. The
   current cooked candidates do not establish cube 14 or world placement.
3. Match record geometry and cube contents, then integrate the recovered
   probe sampling/blending with explicit residency and actual light-grid
   RGB/scalar inputs. Repeat controlled Ratchet/Rivet/Sheep comparisons.
4. Continue deferred composition and production TAA recovery afterward.

Changes remain local and uncommitted. Report next steps before requesting
user input; no additional permission is needed for the remaining static trace.

## 2026-09-02 continuation: regions, indirect replay, and cooked light-grid stream

The user requested: **keep going until parity**, and continues to require
concrete next steps before any prompt. Full retail visual parity is still
unverified. All changes below are local and uncommitted; no retail game was
launched/hooked and no private-desktop capture helper was added.

### Implemented and verified

- `core/level.py` parses the exact 36-byte region and 48-byte checkpoint
  records, signed catalogue indices, paired replacement lists, parent/child
  topology, checkpoint bindings, and preserved bounds/property ranges.
  `tools/analyze_level_regions.py` reports explicit region/checkpoint primary
  dependencies with parent candidates. All 1,216 regions and 860 checkpoints
  match independent raw checks. Malinon region 21 + parent has 29 zones;
  Megalopolis region 61 has 486; union 503. These are not a residency claim.
- `core/hair_probe_lighting.glsl` implements the recovered probe kernel.
  Its 4,096-query GPU check covers 40 records/two lookup words, rotated boxes
  and cylinders, parallax, independent diffuse coverage and visibility.
  Maximum absolute CPU/GPU difference: 8.8215e-6.
- `core/light_grid.py` and `core/hair_light_grid.glsl` implement the entire
  matching Hair light-grid branch, including eight-corner addressing,
  directional radiance/occlusion decoding, interpolation, default fallback,
  and distant GI. A mechanical translation of the original 559 DXBC
  instructions with exact immediate bits provides an independent GPU oracle.
  All 4,096 queries pass: CPU maximum absolute error 4.7684e-6; shared GLSL
  2.2650e-6. These use controlled analytic texture callbacks.
- `core/hair_lighting_replay.py` and `tools/replay_hair_indirect.py` connect
  both kernels to explicit GPU buffers, cube-array mips and 2D/3D GI textures
  in an offscreen compute replay. A 192-query resource fixture passes with
  maximum absolute error 8.9407e-8, including lookup bit 33 and different
  decoded/environment normal inputs. The ordinary CLI also passes on the
  fixture. See `docs/HAIR_INDIRECT_REPLAY.md` for the NPZ interchange schema.
  This is before BRDF/direct/deferred/TAA composition. It has not replaced
  the normal viewport's environment path or proven hardware cube-seam parity.
- `core/light_grid_assets.py` and `tools/analyze_light_grid_asset.py` decode
  the indexed cooked brick stream before optional missing-cell interpolation.
  Malinon day asset 97BE230CA4381B39 has metadata TOC entry 33371 and separate
  stream entry 101036, both archive 50. The streamed span has 34,383,747 bytes;
  its SHA256 is 0797756f290d97b301065f61544e6fdc5457024d35b7b0e0505c3e65b4ca924a.
  All 1,796 bricks / 7,356,416 expanded records consume their exact ranges.
  Authored kinds 2/3 total 2,494,135 cells. Kinds 0/1 remain sentinel cells
  requiring the retail fill path; they are not final black lighting samples.
- `core/retail_light_grid.py` now executes the complete optional fill path
  in an isolated Unicorn VM, using Windows CRT expf/logf and MXCSR 0x1F80.
  It requires the exact verified executable hash. Eight varied Malinon bricks
  match the independent first stage and retain all authored records through
  interpolation. No native game process is used; optional dependency is in
  `requirements-evidence.txt`.
- Inline compression is also recovered. All 648 installed metadata assets
  were scanned for the brick center derived from the old Ratchet coordinate.
  The unique coordinate candidate is **83971B86890068A0**, Sargasso tile_l25
  overcast, brick **55/354**. All 354 brick byte ranges validate. Brick 55
  matches retail decoding and fills 3,682 cells while retaining 414 authored
  cells. Coordinate overlap does not establish captured resource identity.
- The actual load/copy path uses stored brick positions directly. The
  64^3-ring position hash, resident-slot/fade packing and permanent fallback
  initialization are recovered in `core/light_grid_resources.py`. They pass
  4,096 position queries and 1,792 upload commands bit for bit against original
  x86 in isolation. `tools/reconstruct_light_grid.py` reconstructs a supplied
  complete asset with explicit fade, rejects ring collisions and compacts
  slots for diagnostic replay. Runtime asset/condition selection stays explicit.
- Full reconstruction of the Sargasso coordinate candidate is complete:
  354 bricks, 350 distinct payloads, 1,282,753 filled cells, 1,454,080 records
  including fallback. All unique payloads match the first stage and retain
  authored cells. Installed-data shader comparison: 4,096 queries, max error
  4.7684e-7. Combined replay upload: 192 queries, max error 1.1921e-7.
  The 512/409.6-unit valid-entry selection rule also passes 331 isolated
  x86 cases, including all priority pairs and boundary behavior.
- Full suite: **238 passed**. `compileall` over core/tools and
  `git diff --check` pass. No ordinary viewport shader changed this phase;
  previous controlled fur images remain the visual baseline.

### Evidence and reproduction

All evidence below is in
`artifacts/rcra-fur-continuation/probe-analysis/` outside the tracked fork:

- `level-region-dependencies.json`, `level-region-validation.json`,
  `level-region-raw-inventory.json`, and saved level accessor/consumer assembly.
- `verify_probe_lighting_gpu.py` / `probe-lighting-gpu-validation.json`.
- `disassemble_dxbc.py`, `env-struct-381ee4c.hex.asm.txt`,
  `verify_light_grid_gpu.py`, `light-grid-original-and-shared.comp`, and
  `light-grid-gpu-validation.json`.
- `verify_indirect_resource_replay.py`, `indirect-resource-replay-fixture.npz`,
  `indirect-resource-replay-expected.npz`, `indirect-resource-replay-validation.json`,
  and `indirect-resource-replay-cli.npz/.json`.
- `97BE230CA4381B39.light-grid-stream.bin`, `malinon-light-grid-decode.json`,
  `malinon-light-grid-brick0.npz`, and saved codec/loader assembly.
- `light-grid-retail-vm-validation.json`, `light-grid-retail-crt-brick*.npz`,
  `all-grid-coordinate-candidates.json`, `83971B86890068A0.zonelightbin`,
  `sargasso-l25-light-grid-decode.json`, `sargasso-l25-light-grid-brick55-filled.npz`.
- `verify_light_grid_lookup.py`, `light-grid-lookup-vm-validation.json`,
  `light-grid-manager-runtime.asm.txt`, and individual function disassemblies.
- `verify_light_grid_selection.py`, `light-grid-selection-vm-validation.json`,
  `sargasso-l25-grid-reconstructed.json/.npz`,
  `sargasso-l25-light-grid-gpu-validation.json`,
  `sargasso-l25-indirect-fixture.npz`, `sargasso-l25-indirect-validation.json`,
  `sargasso-environment-inventory.json` and `sargasso-nearest-stored-probes.json`.

Run the verifier scripts using the fork's `.venv/Scripts/python.exe`.
The standalone replay command/schema is in `HAIR_INDIRECT_REPLAY.md`.
The cooked decoder command is also there. Do not move installed game streams,
capture resources, generated fixtures, or evidence into tracked source.

### Next steps to reach parity

1. Recover original frame `riftapart-taa_frame7328.rdc`, or its exported
   `g_EnvProbeEnvs`, `g_EnvProbeLookupView`, cube resources, t50/t51 grids,
   cb0/cb6, G-buffers and query state. An asynchronous question asking where
   to read that capture/resources is outstanding; no location was supplied.
   The original capture is not in this workspace. Do not reuse frame-7328
   point/mask values with unrelated resources. A fresh capture needs its own
   state and a verified private-desktop route; never launch/hook the game on
   the active desktop.
2. Use the isolated decoder and explicit resource builder for cooked grid
   reconstruction. The optional retail interpolation gate is the inverse of
   byte at `1452F115F`; the tool deliberately runs it enabled. Runtime gate,
   fade, asset condition, priorities and residency still need frame evidence.
   Position copying and lookup construction are now traced; do not invent
   offsets to force the Malinon stored range onto the old Ratchet coordinate.
   The Sargasso coordinate candidate is still only a candidate. Detailed
   function anchors are in `ENVIRONMENT_PROBES.md`.
3. Resolve runtime grid residency and probe cube identity/placement, bind the
   verified resources through the combined replay, and compare actual outputs.
   Keep decoded surface normal r6.xyz separate from environment normal r21.yzw.
   The grid/probe intensity is cb6 byte 732; grid reflection is unscaled.
4. Integrate verified bindings into the viewport, then continue full deferred
   composition, shadows/screen-space terms, and production temporal behavior.
   Run matched-camera Ratchet/Rivet/Sheep comparisons before claiming parity.

## 2026-09-02 continuation: actor bindings, prefab identity, and level catalogue

This increment completes the indexed actor work listed immediately above.
`core/zone.py` reads the 32-byte actor instances in `0x70682CB8`, exact actor
references in `0x78684035`, and component ranges in `0x50EDC53D`. It retains
full zone-local matrices, actor IDs, renderer IDs, node types, and flags.
`core/scene_components.py` shares the verified 32-byte component format with
the actor parser; payload offsets are DAT1-relative, excluding outer headers.
Empty payloads request factory defaults. Actor defaults and zone overrides
remain separate because their type-specific merging is not yet established.

`core/actor.py` follows header `0x32FAC8E0` to the model reference and exposes
default scene `0x364A6C7C` and components `0x135832C8`. It no longer chooses
a model by string-pool order. `core/level_assembler.py` now assigns each node
its actual actor/model reference; the legacy round-robin model assignment
has been removed. Non-model actors and missing references are skipped with
reasons. Scene diagnostics and displayed IDs use the verified records.

The exact zone-loading component is now identified as **PrefabZoneComponent,
type `F39305D5`**. Registration `0x14015AEB0` links its name to constructor
`0x1413CF210`, which installs vtable `0x1444D3160`. The first virtual entry
is the already traced initializer `0x1413CEF00`; loading `0x1413CF430` sets
the target zone matrix from the owner's renderer node through `0x1413CACB0`.
The type hash is the retail CRC initialized with `0xEDB88320`, without a final
inversion; see [ENVIRONMENT_PROBES.md](ENVIRONMENT_PROBES.md) for the Python
equivalent and a second observed component-hash check.

The bounded search found **no PrefabZoneComponent** in the 5,892 zone bindings
or in 1,950 component defaults from all 562 distinct actor assets referenced
by the 177 actor zones. All 562 assets parsed, none were missing, and their
default scene types agreed with their placed instances. Do not infer an
identity world matrix from that absence.

The next static trace reached the actual retail level loader `0x14107BEE0`.
Forge previously did not recognize its type, **`587B60A6`**. `core/archive.py`
now dispatches it to `core/level.py`, which decodes the verified zone catalogue:
header `7CA7267D + 0x18` gives the count, `4E023760` contains 12-byte records
`<QhH>`, and the signed name index selects a DAT1 string offset in `2BA33702`.
The scene panel now lists those references. This is a catalogue, not a list
of active instances or their world matrices.

Verification:

- **180 tests passed** in 2.11 seconds. Eleven actor/component/assembly
  regressions and five level-catalogue regressions were added. The earlier
  actor-dispatch fixture now supplies the real header/scene sections instead
  of relying on a string-pool guess. Core, UI, and the analysis CLI compile.
- The production scan covered **2,340 zones**, including **290 scene-bearing
  zones**, **177,404 direct models**, and **14,555 actor instances** with
  **5,892 component bindings**. Both raw and production scans reported zero
  parsing errors.
- **12,465 of 14,526 distinct draw IDs now match**, adding **31 actor-model
  IDs** represented by **32 candidates**. All **13,090 direct-model
  candidates are unchanged**, and all 32 actor candidates agree exactly with
  the independent scan on IDs, scene offsets, and all matrix components.
- The combined result has **13,122 candidates, 640 ambiguous IDs, and 2,061
  unresolved IDs**. The 45 uninstalled-model candidates remain marked. All
  348 per-face match counts were checked. Runtime residency is still unknown.
- `i29.level` (`95A02E80D5D79CF7`) contains **9,176 verified zone references**.
  Every path produces its recorded CRC64 ID. The 133 names absent from
  `hashes.txt` are also absent from the installed TOC, so they do not add
  installed zones to the current scan.
- Malinon lighting zone `81D3F7A27166B843` is **catalogue index 251**, name
  index **183**, path
  `levels/i29/instance/Malinon_Intro/Malinon_Intro/malinon_intro_lgt.zone`.
- An offscreen Qt check displayed all 9,176 level references and switched
  back to a mixed actor/model zone with correct columns and node count.
- No fur shader changed. The previous controlled fur captures remain the
  visual baseline. No retail game was launched or hooked, and no capture
  helper was added. The original RDC/resources are still unavailable here.

Evidence is outside the tracked fork in
`artifacts/rcra-fur-continuation/probe-analysis/`:

- `resolved-actor-environment-probes.json`: production report. Use the same
  CLI command as above with this output filename.
- `actor-dependency-validation.json`, `actor-model-validation-summary.json`:
  independent actor decode and exact candidate/face-count comparison.
  Reproduce with `scan_actor_dependencies.py` and `complete_actor_validation.py`.
- `prefab-actor-defaults.json`: complete bounded actor-default search;
  reproduce with `scan_prefab_actor_defaults.py`.
- `level-catalogue-validation.json`: raw catalogue comparison, CRC64 checks,
  unavailable-name/asset inventory, and offscreen scene-panel check.
- `continued-14015ae70.asm.txt`, `continued-1413cf210.asm.txt`,
  `continued-14107bee0.asm.txt`, `level-accessors-after-load.asm.txt`, and
  the existing actor/component disassembly preserve the executable evidence.

This static trace is now resolved. The kind-4 streaming builder walks child
primary lists and filters them with two runtime bitsets; the distinct kind-3/5
selector visits the immediate parent and selected region. The saved fresh Hair
frame's active record 10 / cube 18 is identified as runtime draw-list probe
`F896FB5315175B7C` in zone `9C292F5F8A79EEC2`, a kind-5 child of Megalopolis
root 61. See the latest offline region/probe provenance section below for the
exact evidence boundary and remaining work. The older frame-7328 cube-14
association is a different capture and must not be combined with this frame.

All changes remain local and uncommitted. Report next steps before requesting
user input; no additional permission is needed for the remaining static trace.

## 2026-09-03 offline motion-history audit

The event-24715 VS output is now mapped exactly: six `float4` registers with
previous clip in the final `TEXCOORD5` slot. The old private viewport comparison
helper had placed layer/visibility diagnostics there, so its earlier reports
did not validate motion. The helper now reads `source-previous-vertices.bin`,
uses the captured previous dynamic-object transform and camera matrix, evaluates
wind at `ShaderTimer - DeltaTime`, writes `vsPreviousClip` to the native slot,
and keeps diagnostics in a seventh register. It requires `--allow-gpu` and was
not executed in this offline phase.

The new CPU-only `analyze_fur_position_history.py` verifies source hashes and
decodes both skin streams. Every one of the 18,630 draw-referenced vertices
changed; displacement median/RMS/max is `0.00327549 / 0.00411025 / 0.01063064`
model units. A direct reconstruction from saved current/previous object and
camera state matches base-shell current clip within `5.54e-7` and previous clip
within `5.67e-7`. Captured base-shell motion median/RMS/max is
`0.64337 / 0.91126 / 2.27792` pixels at 1920x1080. Evidence is in the outer
private `capture-tools/fur-position-history/report.json`; no game, replay, Qt,
OpenGL, or GPU process was used.

Next steps remain offline: keep the source and documentation gates green and
prepare the bounded single-frame temporal runtime export described in
[HAIR_TEMPORAL_RECONSTRUCTION.md](HAIR_TEMPORAL_RECONSTRUCTION.md). When live
game work resumes, run only the guarded vertex comparison and one bounded frame
needed for the TAA cbuffer, selected histories and rejection/depth resources.

The saved-shader absence check is now scripted as
`capture-tools/inventory_temporal_shaders.py`. Across 261 shader records and
1,501 uses, the old main-TAA hash matches no report container hash,
assembly-declared shader hash, or saved-binary MD5. Event 17894 is the sole
`TemporalAaCBuffer` user and is the already identified accumulated-alpha
disocclusion pass. This closes the saved-capture search boundary: implementing
a retail color-history apply from that capture alone would require invention.

## 2026-09-03 offline temporal executable recovery

The saved-capture boundary above remains true, but the installed executable
provides a separate static source. `inspect_temporal_static_assets.py` found the
raw old main-TAA hash exactly once in `RiftApart.exe` SHA-256
`51299faca61866cf10ea9035a15b8f22600a56557dd5ffc1aad390d5a54e6d82`.
It is the `HASH` part of a valid 11,612-byte DXBC container at `0x34235a4`.
DXC identifies the entry as `CS_TemporalAaApply`, shader hash
`4e1b2693fbe9696f3f1eb1d6ac577a01`, with the complete 224-byte cbuffer layout,
two samplers, seven SRVs and one UAV. The extracted container SHA-256 is
`b892667bfa835a95a7f58c78b30b35d45e5784b48d750bf6543bf557d9956e0f`.

A bounded 65-container scan around it recovered eight related temporal entries,
including the upsample apply and full/half disocclusion shaders, with zero DXC
failures. The embedded `CS_AccAlphaDisocclusion` hash
`04d5df274c814fdd0ad97030675b8566` exactly matches captured resource 4776.
This links the executable family to the saved runtime chain. All nine temporal
binaries and assemblies are preserved under the outer private
`capture-tools/extracted-shaders/embedded-temporal/` directory, and
`recovered-main-taa.comp` reconstructs the exact main-apply algorithm in GLSL.

The remaining temporal gap is runtime data rather than shader code: the actual
frame-specific `TemporalAaCBuffer`, current history index, stencil and matched
pre/post resources were not saved for the apply event. The later static builder
recovery below supersedes this section's earlier uncertainty about filter
weights, rejection floors, and dither constants. Dynamic HDR/matrix/response
values still require the bounded frame.

## 2026-09-03 offline native TAA chain reconstruction

The native-resolution temporal chain is now reconstructed through four
standalone, offline-compiling GLSL compute shaders in the outer private
`capture-tools/extracted-shaders/` directory:

- `recovered-taa-seed-history.comp`, matching
  `CS_TemporalAaDisocclSeedHistory` hash
  `10ac8bf15ec0bd2f3b5f345fcd031cdc`;
- `recovered-taa-disocclusion.comp`, matching
  `CS_TemporalAaDisocclusion` hash
  `c5e3d1ab23522047aea731e0fb9ec5d7`;
- `recovered-taa-disocclusion-half.comp`, matching
  `CS_TemporalAaDisocclusionHalf` hash
  `5a4031e742d4547b5fab304a4e0b3a22`;
- `recovered-main-taa.comp`, matching `CS_TemporalAaApply` hash
  `4e1b2693fbe9696f3f1eb1d6ac577a01`.

The full-disocclusion translation preserves both outputs and the DXIL's exact
center/diagonal selection, current-minus-velocity history position,
out-of-bounds test, two view-space projections, three-sample scatter triangle,
7.5-percent local depth-edge filter, 24/120 rejection slopes, fuzz branch and
camera-motion floor. The half pass is only a transformed linear resample of the
full-resolution red channel. The production preview now shares the recovered
main-apply color transforms, five-tap Catmull-Rom history sample, motion
thresholds and neighborhood bounds through `core/hair_temporal.glsl`.

The offline validator passes 24 shader cases: the ordinary and native-raster
viewport sets, full scene replay, motion producer, and all four reconstructed
temporal compute stages. This does not establish frame output parity because
the runtime cbuffer values and matched history/stencil/resource contents are
still absent. No game, capture replay, window, OpenGL context or GPU workload
was used.

## 2026-09-03 offline TAA cbuffer and storage integration

Static x64 tracing resolves the native-resolution apply builder at
`0x1411D7DA0`. It allocates and initializes all 224 bytes. The exact current
filter is a normalized 3x3 Gaussian with falloff 2.29 mixed 80 percent toward a
normalized separable Catmull-Rom kernel. The builder also proves the 0.0625
minimum rejection, stencil scale/offset, reciprocal history warmup, HDR-scale
formula, jitter offsets, and four dither values. The 1,024-byte dither table has
SHA-256 `5747b412a83d10e7430385c2c20b548d5f2b63558993e5b9aa159486f689e328`.

The ordinary temporal preview now uses the exact current filter, direct float32
warmup, center/closest-diagonal depth-selected motion, native R11G11B10 paired
histories, f16 current-sample chroma, explicit LOD 0 history sampling, finite
reset-history input, and final dither table/phase with top-left pixel addressing. The
reproducible static reports are `temporal-cbuffer-static.json` and
`temporal-cbuffer-builder.json` in the outer capture-tools directory. All 278
CPU tests and 24 offline shader cases pass. The game and GPU tools stayed closed.

The settings fallback is now closed statically as well. Leaf constructor
`0x140FB4270` writes `0x3D23D70A` (`0.04f`) and `1.0f`; the apply builder calls
it for the local response pair and selects the optional value at
`*(global 0x146732C48 + 0x22C)` only when that pointer exists and the value is
positive. Consequently the ordinary fallback `m_Misc.x` is exactly
`max(0.04f, 0.0625f) = 0.0625f`. A separate runtime flag at `0x146838420` can
raise it to `0.1f`; the saved executable has no file-backed initializer for
that flag, so a frame is still required to establish whether runtime code set
it. The production preview now uploads fallback `m_Misc.x` separately from the
reciprocal history warmup, matching the native shader's two independent inputs.
The byte assertions and decoded values live in
`capture-tools/decode_temporal_cbuffer_builder.py` and its JSON report.
The same decoder verifies the parallel material-schema entry at index 8: its
name is `TemporalAA`, and its description explicitly defines the value as the
nonopaque current-versus-history control.

The companion full-resolution disocclusion builder is now decoded by
`capture-tools/decode_temporal_disocclusion_builder.py`. Sixteen code ranges
(4,719 bytes total) are SHA-256 guarded. This closes the stable pixel scale, zero
source scale, `1920/max(width,1920)` camera-motion normalization, `-1/+1`
history threshold, prior projection-to-UV formula, and fuzz predicate. The
frame's two depth thresholds, view transforms, flags, selected history, and
scatter resource remain runtime evidence. The generated report is
`capture-tools/temporal-disocclusion-builder.json`.

The same trace now closes the two surrounding paths. After full disocclusion,
the half pass binds full `+0x8A98` to `t5`, half output `+0x8C30` to `u0`, and
uploads a 64-byte `MiscCB` whose consumed vector is exactly
`(1/w, 1/h, 0.5/w, 0.5/h)` before an 8x8-grid dispatch. The seed branch runs
when the current temporal record exists and view reset byte `+0x1B9E` is set;
it binds current depth-history `+0x40` to `u0` and linear depth `+0x29B8` to
`t5`, then dispatches the recovered `(depth, 0)` shader. A whole-text direct
xref scan finds both dynamic disocclusion threshold globals only in four SIMD
loads across the two builders, with no direct store or file-backed pointer, so
their frame values cannot be inferred statically.

The shared transform helper is now decoded too. It promotes the two float32
matrices to float64, computes `first * inverse(second)`, and converts the result
back to float32. Thus `m_ViewSpaceDelta` is exactly
`currentView * inverse(previousTransform)` in both builders. Disocclusion's
secondary three-row transform uses a current-view copy whose fourth float4 is
replaced by view `+0x560` xyz and `w=1`. The main-apply decoder now guards nine
ranges totaling 3,523 bytes; the disocclusion decoder includes the same three
matrix helpers in its totals above.

Main-apply resource selection is statically mapped in the cbuffer report too.
The current/prior record helpers supply output `+0x40` and color history
`+0x98`; the frame record supplies current color, velocity, full disocclusion,
stencil, half mask, and linear depth at their exact guarded offsets. The
half-mask rule specifically requires global `0x146732EC9` or
`0x146732EC6` plus availability `+0x89E0`; the second flag invokes helper
`0x1411CB890` before `+0x88A8` is bound, and failed guards bind the empty
descriptor. Matching
dimensions select the native shader object and dispatch in 8x8 groups; differing
dimensions select the recovered upsample object. The runtime frame index still
selects the concrete history records, so their contents and pair remain part of
the later bounded frame.

The two helper bodies now prove the ring mechanics: current index comes from
renderer `+0x1C28`, previous index is `1-current`, each record is `0x1F0` bytes,
and a nonzero frame accepts history only when its prior tag equals `frame-1`.
Separate runtime flags choose the active current/prior pool bases. The apply
decoder guards nine ranges totaling 3,523 bytes including these helpers and the
shared float64 matrix inversion/multiplication path.

## 2026-09-04 guarded runtime TAA contract

The self-terminating two-boundary capture contains `CS_TemporalAaApply` at event
20572. Its 11,612-byte DXIL SHA-256 is
`b892667bfa835a95a7f58c78b30b35d45e5784b48d750bf6543bf557d9956e0f`,
exactly matching the executable extraction. The event binds `kForward`,
`kTaaTarget0`, `kGBufferVelocity`, `kTaaDisoccl`, `kHyperDepthStencil`,
`kTaaMask`, and `kLinearDepth16` at `t5..t11`, with `kTaaTarget1` at `u0`.
Native source and destination dimensions are both 3440x1440; the mask is
1720x720.

The event's 224-byte cbuffer SHA-256 is
`67eb5fbc8fb35a26f20ba03b18e4b7b60204a8f3685f2f74e20e28b9c0d17a62`.
Its runtime values independently validate the static producer chain: jitter
pixels `(-0.34, 0.02)`, maximum filter-formula error `7.4505806e-9`, ordinary
response/floor `0.04/0.0625`, HDR scale `76.10927582`, history age 3645,
dither table index 61, phase zero, and disabled fuzz/screen-capture flags.
`analyze_taa_apply_runtime.py` regenerates the audit, and the fork now contains
the typed builder/serializer plus focused captured-vector tests.

The two-boundary live controller is retired until its guard behavior is audited:
its report crossed the stated page-file threshold without discarding the
capture. Do not reuse it. A later raw-resource replay with a hard 12 GiB job cap
failed safely with RenderDoc `E_OUTOFMEMORY` during `OpenCapture`; the owned job
was terminated, no textures were exported, and no process remained. Continue
from the saved capture with a reduced or measured replay route. Do not launch
the game for this next step.

## 2026-09-03 offline region selection and captured-probe provenance

The remaining level selectors are decoded and guarded without opening the
game. For a kind-4 root, the builder at the saved `region-streaming-selection`
trace walks every child record and consumes each child's primary-zone list.
It partitions retained zones through two 15,360-zone runtime bitsets and does
not consume the root's own primary list. Megalopolis root 61 has 241 children
and 1,848 distinct child-primary inputs; its 486-entry root list is separate.
For kind 3 or 5, `0x1419A1A30` visits exactly the immediate parent first and
the selected region second, consuming and deduplicating their primary lists.
The exact operations are implemented by the two `LevelInfo` candidate helpers
and reported by `tools/analyze_level_regions.py`.

The saved Hair event 17544 now has complete CPU-only probe provenance. Active
record 10 stores cube 18 exactly. Its first 124 static GPU bytes uniquely match
runtime draw-list probe `F896FB5315175B7C` in `tile_zz27_lgt.zone`
(`9C292F5F8A79EEC2`) under identity zone placement. The level join places that
zone at catalogue index 3976 in kind-5 region 184, child ordinal 122 of
Megalopolis root 61. The production-loadable scene bundle contains the same
record/cube pair, and 29,359 captured screen tiles can select record 10.

Cube 18 has no installed baked-asset match because this probe is rendered from
scene draw lists. Malinon lighting zone `81D3F7A27166B843` remains a declared
dependency of region 21 and root 61; its Day texture `837545B07B72296F`
matches captured cube 40 across the recovered atlas, but cube 40 is inactive
in this frame. These identities are frame-specific. The old frame-7328
record-10/cube-14 evidence belongs to a different capture.

Reproduce the joins with `tools/decode_region_streaming_selection.py` and
`tools/analyze_captured_probe_provenance.py`. Reports and guarded disassembly
are in the outer `probe-analysis/` and `capture-tools/` evidence directories.
No game, replay, viewport, window, OpenGL context, or GPU workload is required.

Next offline work is limited to source/checkpoint maintenance and further
static executable traces. Full-frame parity now requires the deferred Hair
composition inputs and a single bounded same-frame export of the dynamic TAA
cbuffer, selected history resources, stencil, depth/rejection resources, and
the active probe's scene-rendered cube when live game work resumes.

## 2026-09-04 live temporal depth-history integration

The production viewport now owns paired full-resolution R16F temporal depth
attachments beside the native R11G11B10 color histories. It composes fur linear
depth over scene linear depth, writes that value with each temporal sample, and
uses the previous attachment to reproduce the captured accumulated-alpha mask
semantics: gather at the half-resolution center, exclude component `w`, compare
current depth against `previousMinimum * 0.9980000257492065`, and contribute
`0.5` rejection. This removes one captured-resource dependency from the live
path while preserving the separate raw rejection and final 0.0625 blend floor.

Native R11G11B10 allocation now uses the raw OpenGL entry point, avoiding the
high-level PyOpenGL null-input conversion failure that had silently disabled
the temporal path. A bounded 800x800 private-desktop smoke reached nine temporal
samples with deferred lighting, contact, and denoise active. Its frame is
visually intact; the job peaked at 1.661 GiB under a 2 GiB cap, input remained
on `Default`, and it exited cleanly. A subsequent proof-only run stopped at its
24 GiB physical-memory reserve and cleaned up without producing partial output.

The next production gap is the retail full-resolution disocclusion input. Trace
the writer of captured `kMbDisocclTarget` resource 4114, recover its live
motion-blur scatter/confidence data, and feed the verified
`CS_TemporalAaDisocclusion` algorithm. After that, add stencil bit 128, the
RG16F camera-motion channel, and dynamic HDR/matrix/response cbuffer values.
Do not hardcode the captured frame's bytes into the general viewport.

## 2026-09-04 live motion scatter and full disocclusion

That production gap is now closed. A bounded XML/LZ4 extractor recovered the
six consecutive motion-blur cbuffers from mapped resource 10245 without replay.
The generate cbuffer SHA-256 is
`80993c833f1fa8369b25875aece0d97344b0a49132f9d205de22edc9d4c13159`.
Its exact values include half-resolution pixel scale, velocity scale
`152.21853637695312`, ramp `(0.25, -0.6000000238418579, 0, 2)`, and the
downsample shutter `0.14122892916202545`. The production viewport now runs the
recovered downsample, half and quarter neighborhood reductions, 5x5 gathered
neighborhood, and 40-crossing R8 scatter stages in that order.

The capture also resolves both disocclusion cbuffers. Event 16262's cbuffer
SHA-256 is `3be6fcdcfaae0b2900aba88fc34429edafc5b11a6fd70a06aa39729f7f661985`;
event 18704's is
`af3ea342a1499f570d156e4d2af2d9e29f1a8f9d8a8ab58fd50ba88fa2d74e0e`.
The live pass writes paired full-resolution RG8 disocclusion and RG16F
depth/camera-motion histories before temporal color apply. It uses dynamic
current/previous camera transforms, the captured full-pass depth calibration
and motion threshold, the exact 24/120 slopes and three-history-probe rule, and
an inert output for the preview's zero-depth background sentinel. Temporal
apply consumes R directly, half-weights G, retains the event-18687 half-mask,
and applies the recovered 0.29 Hair stencil response.

The stable 640x640 logical smoke reached nine samples with both history slots
valid and finite. Camera motion stayed below threshold at `0.98779296875` and
full disocclusion correctly remained zero. The 480x480 moving-wind diagnostic
produced nonzero full disocclusion in both slots and nonzero values through all
six motion stages. Its full velocity maximum was `0.50146484375`; shutter
scaling reduced the gathered maximum to `0.07080078125`, correctly below the
native `0.800000011920929` scatter gate. Both guarded runs exited with no
process/window residue or focus change and peaked below 1.75 GiB under a 2 GiB
hard limit. All 285 CPU tests and 45 shader cases pass.

Continue with the exact accumulated-alpha half-resolution producer, actual
D32S8 stencil and opaque velocity. Those allow camera history to survive view
changes and leave a composed same-frame output comparison as the final temporal
validation. Dynamic HDR, optional response and conditional-floor state remain
explicit runtime inputs.

## 2026-09-04 live accumulated-alpha chain

The production viewport now runs the recovered accumulated-alpha dependency in
frame order. It stores opaque and fur-composed depth in full-resolution R16F,
reduces opaque depth to exact four-texel half-resolution minimum/maximum values,
builds the event-18687 R8 mask from the current composed depth, reruns full
disocclusion only for flagged pixels at the captured
`0.6666666865348816` motion threshold, and patches R8 disocclusion, RG16F
velocity and R16F depth extrema at half resolution. Dense full-screen draws
replace the native append queue while discarding unflagged pixels, so the
observable texture results retain the recovered sparse-pass contract.

`analyze_taa_base_half_depth.py` independently verifies the previously
unresolved pre-alpha reduction. The four non-overlapping R16F full-depth texels
produce both saved half-depth extrema bit for bit for all 1,238,400 pixels. The
final TAA pass now samples the explicit current-frame mask bound in the captured
`t10` role; it no longer approximates that mask from a previous temporal depth
history.

A guarded 480x480 logical/600x600 physical smoke reached seven temporal samples.
All seven new targets have the expected R16F, RG16F and R8 formats. The mask has
2,356 active pixels, and the patched half velocity has 2,350 nonzero pixels per
component. All outputs are finite, the saved frame is visually intact, and the
job peaked at 1.628 GiB under its 2 GiB cap while preserving the `Default` input
desktop and leaving no owned process or window. All 285 CPU tests and 53 shader
cases pass.

Continue with an explicit stencil-category texture and opaque velocity, then
validate camera motion without resetting temporal history. Dynamic HDR,
optional response and conditional-floor state remain runtime inputs before a
composed same-frame output comparison.

## 2026-09-04 live opaque velocity and stencil category

The production viewport now writes ordinary opaque motion into a full-resolution
RG16F target using the same current-minus-previous, native top-left pixel
convention as the recovered fur material pass. Motion-blur downsample,
full-resolution disocclusion, accumulated-alpha half resolve, and final temporal
apply select between opaque and fur velocity through the composed fur mask.
Camera fields are no longer part of the temporal reset signature because the
previous projection/view and per-pixel velocity now carry view changes.

An R8UI category texture is shared between the HDR and fur-material
framebuffers. Opaque draws write zero; surviving stochastic fur fragments write
128. Final apply loads `(stencil & 128)` at the selected velocity pixel and
multiplies it by the recovered `m_Misc.y = temporal_stencil_rejection(0.04)`
scale, reproducing the captured 0.29 nonopaque rejection without inferring the
category from a fur mask.

A guarded 480x480 logical/600x600 physical smoke stepped camera yaw by 0.25
degrees for seven frames. Temporal age advanced from 1 to 9, both history slots
remained valid, and opaque velocity was finite and nonzero in 20,686 pixels per
component. Stencil readback contained exactly 331,638 zero pixels and 28,362
bit-128 pixels. The saved frame is visually intact. The isolated job peaked at
1.631 GiB under 2 GiB, retained `Default` as the input desktop, exited with code
zero and left no process or window. All 285 CPU tests and all 53 shader cases
pass.

Continue with live HDR scale, optional response and conditional-floor state,
then compare the composed output against the saved same-frame native targets.

## 2026-09-04 production TAA apply and same-frame comparison

The live TAA scalar producer now accepts runtime nonopaque response, conditional
floor and HDR reference state. It preserves the executable fallbacks for absent
or invalid values and reproduces the captured event-20572 `m_Misc` tuple exactly.
The production shader also uses normalized linear accumulated-alpha sampling,
the recovered scalar color-operation order, exact integer pixel-center history
coordinates and native broadening/filter/blend arithmetic.

An isolated 3440x1440 production fragment replay against every saved event-20572
input matches 4,832,111 of 4,953,600 packed R11G11B10 outputs exactly
(97.5474604 percent). Every channel exceeds 99.9997 percent within one stored
code. Only 17 native-output pixels differ by more than one code; all use the
ordinary low-rejection linear-history path and none intersects the border,
closest-diagonal, Catmull-Rom, stencil, disocclusion or alpha-mask branches.
The remaining residual is therefore sparse cross-API arithmetic/storage
rounding, not a missing resource or control-flow path.

Evidence is in `viewport-taa-apply-comparison/report.json` and
`residual-analysis.json`. Its private job exited with no process/window residue
or focus change and stayed below the 2 GiB hard limit.

## 2026-09-04 native raster activation

The production viewport now detects core OpenGL 4.5 or
`GL_ARB_clip_control` and activates the captured upper-left, zero-to-one,
reverse-Z convention as one switch. All viewport programs compile with the same
raster define. Opaque and fur draws share a depth-clear-zero `GreaterEqual`
attachment; perspective and orthographic projections, grid unprojection,
material/decode/contact/denoise addressing, motion/disocclusion, temporal jitter
and fullscreen copies select the matching coordinate path. CCW back-face culling
is scoped to the recovered fur draw. The final Qt framebuffer temporarily uses
lower-left raster origin so Qt presents upper-left offscreen resources upright.

The guarded perspective run activated native raster on the NVIDIA 4.6 driver,
kept all deferred and temporal readbacks valid, preserved history through seven
camera steps, and rendered upright. The final orthographic run confirms correct
reverse-depth ordering and intact face, eye, helmet, ear, fur and grid geometry.
The two accepted jobs peaked at 1.580 and 1.487 GiB under 2 GiB, retained the
`Default` input desktop, exited with code zero and left no process or window.

The remaining broad renderer work is automatic scene placement/residency,
source-light selection and active-Hair validation of the connected local-light
and key-modulation branches. `core/local_lights.py` now fixes the
exact 128-byte light/light-volume layouts, ordered per-tile lookup iteration
and the zero-radius base radiance stage. Its separate Hair area-light path now
preserves spherical broadening, finite-segment direction selection, three-lobe
averaging, area-distance correction and the negative-radius compatibility
branch. It also recreates the exact local-light
Z-bin word texture from a caller-supplied submitted prefix: the extracted
`CS_LightLookupGenerateZBin` reads byte offset 96, uses inclusive low/high
limits and matches the environment-probe producer instruction for instruction
after its source binding and field offset are normalized. Captured input validation independently
finds zero selected light references at all 11,215 Hair pixels while retaining
lights 0..7 on 1,414 other scene tiles; see
`hair-local-light-lookup-validation.json` (SHA256
`cc034335216d7479875b111e43dea5b9ceee8d74d47f00e2a1ad8936cfe79b6f`).
The report validates the Z-bin generator over all 65,536 unsigned bins for the
observed contiguous record prefix. Its dispatch active-count cbuffer was not
exported, so the count remains an explicit input.
The same module now reproduces ordered clip-volume rejection and flag-2 box or
radial accumulated-light color volumes, all three gobo coordinate modes and
the ordered five-plane shadow-volume sample/fade chain. The production scene
shader accepts exact raw local lookup/light/volume inputs, walks records in
native order and connects the supported point/area and modulation branches to
the Hair resolve. It also accepts local shadow-map records, using their
`LightVolumeGpu` transforms and the shared `t39` depth atlas for projective or
packed six-face coordinates, strict comparison and four rotated raw-depth taps.
Flag-2 lights continue through the shared four-tap screen-contact kernel with
the evaluated local direction, frame noise and combined depth before visibility
is applied. This frame contains no active Hair lookup reference with which to
validate those branches' output. Static executable recovery identifies
`FillLightLookup` event `0x67`, the manager-owned prepared float3 stream and
the exact 96-byte per-draw cbuffer builder. `LightShellPlacement` and
`build_local_light_frame_lookup()` now create the light Z bins and both
full/opaque screen lookup resources from an explicit submitted prefix.
`build_hair_scene_local_lookup()` attaches those resources to a current scene
view. The recovered near-plane path gates on the light sphere, constructs the
expanded plane and clips/caps straddling shells before fan triangulation. A
nonempty transformed shell matches the shared probe route bit for bit. The
CPU-only report `light-shell-producer-validation.json` pins 14 executable ranges
and has SHA256
`f26ef671151fa063a36019780037e6443dc8c5d5dff27227ca89c6f7bbd8296c`.
This capture contains neither those manager placements nor Hair pixels touched
by the two active area records. Automatic source-light selection and manager
ownership remain open.

`core/hair_key_modulation.py` and `hair_key_modulation.glsl` recover and connect
the executable's key cloud attenuation, periodic key gobo and ordered
five-plane shadow-volume chain. The production shader applies them after key
shadow/contact visibility and in the captured instruction order. The saved
frame disables each path, so its 11,215 Hair pixels verify the captured white
identity behavior; deterministic synthetic cases anchor the cloud projection,
atlas coordinates and nonstochastic cascade selector. The report is
`hair-key-modulation-validation.json` (SHA256
`9ca8ad1a98f703bb385eda6559889c2c6011175e51595b39e549c60e29bbf343`).
The complete CPU suite passes 392 tests, and all 53 offline production/recovered
shader cases compile; the shader report SHA256 is
`b272aeb05a0f139cfdf22d3d9c6ce5bb1537a4fae07755005cbd866f99efae4a`.

## 2026-09-04 environment-probe lookup producer recovery

The environment-probe Z-bin chain is now recovered on the CPU side. Static
executable analysis identified the exact compute/front/back shader family and
the submit routine at `0x14108D200`. The submit routine constructs a clamped
view-depth sphere interval for each eligible probe, chooses the shared
`1024 / max(1024, farthestBound)` scale, floors the minimum, and stores the
exclusive upper edge as `floor(scaledMaximum) + 1`. The compute shader treats
that stored high half as inclusive while writing record bits. The word count is
`(recordCount + 31) >> 5`.

`core/probe_lookup.py` now produces the packed record ranges, recreates the
Z-bin word texture, applies the front-shell OR and opaque back-shell clear
operations to supplied raster coverage, and exposes both captured back-depth
predicates. Against the saved 1920x1080 scene inputs, the producer matches all
22 records in the effective prefix and the scale's exact uint32 representation
`0x3F20CEFB`. The integer generator also matches an independent scalar oracle
over every unsigned 16-bit bin. The CPU-only report is
`probe-lookup-cpu-validation.json`, SHA-256
`28e6b30693e2ce4a2d436230fe7b9e15753af663ea8ccdcf2ec7840dee150fbe`.

The lookup depth bounds are also recovered. Exact-byte extraction identifies
`CS_GenerateEighthResMinDepth` (SHA-256
`fa143e5c5d7dcf78ed51f6f9793b2c881c5755c662f6d3a72733d8bf73d36610`)
as a four-gather, 16-sample minimum reducer. The shell submit helper uses the
exact table value `2.0` for mode 4. `PS_InitLightLookup` writes the reverse-depth
far bound to `SV_Depth` and clears the lookup words. The active
quarter-resolution width is 480, producing `m_VertPushScale =
0.006054521072655916` from the captured screen-to-view scale. The exact box
stream at `0x1432D3AB0` contains 36 vertices / 12 outward triangles.

Against the saved 1920x1080 depth and 240x135 opaque lookup, the original
unexpanded ray/box interval model matches 712,626/712,800 decisions. Applying
the recovered vertex shader, box topology, and push to both passes improves
that to 712,774/712,800 (99.9963524 percent), IoU 0.99971679. Evidence is
`probe-triangle-mask-analysis.json`, SHA-256
`d7220d8ab2d111ac8da19eb02f1669990e5ab55721c420b39d399c7502925689`.
The remaining 26 pixels keep D3D depth quantization, triangle ownership and
per-primitive coarse derivative helper lanes open; this is not yet an exact
hardware-raster claim.

The remaining lookup gaps are runtime active-resource lifecycle,
cube residency/fade assignment, arbitrary zone placement, and the last 26
fixed-function raster decisions.

The submit loop defines the compacted count precisely once its job inputs exist:
it tests `selectionMask[managerRecord.resourceIndex]`, preserves the sorted
manager order for nonzero entries, and increments the compacted count.
`compact_selected_probe_records()` implements that boundary. The per-view mask
producer is now traced to `0x14108BE90`: manager active-bitset gate, six-plane
sphere/OBB visibility, and two transition-index exclusions, followed by the byte
write at `0x14108C6AC`. It is separate from residency fade.

## 2026-09-04 cooked probe placement and frame builder

All 22 active records are now associated with cooked definitions across 10
zones. Placement-invariant GPU fields uniquely identify 19 records; records
8-10 share a common runtime-draw-list definition but each has one exact identity
placement among the 17 candidates. The recovered record order is strictly
descending by `probe_sort_key`. Seven zones are identity placed. Every probe in
each of the three transformed overlay zones independently solves to the same
rigid zone matrix within 6.10352e-5 translation spread.

`core/probe_lighting.py` now exposes `ProbePlacement` and
`build_selected_probe_shader_records`, preserving the retail sequence of sort,
resource-indexed view selection and compacted record emission.
`core/probe_lookup.py` adds the capture-validated homogeneous clipping,
pixel-center shell raster, coarse derivative envelope and end-to-end
`build_probe_frame_lookup`. It builds placed records, exact Z bins and full and
opaque screen lookup resources from explicit live inputs without opening the
game.

The cooked-to-frame validator preserves captured manager order, matches all
placement-invariant bytes, all 22 packed Z-bin words and the scale bit exactly.
Fourteen records are byte exact before Z-bin; solved-matrix rounding leaves a
maximum 6.10352e-5 float error in the others. The final screen result remains at
26 mismatches out of 712,800 decisions, IoU 0.999716791. Reports are
`captured-probe-invariant-matches.json` and
`cooked-probe-frame-validation.json`. Runtime ownership of future zone
transforms, active-resource state, transition indices, cube slots and fades
remains the next manager boundary; the final D3D fixed-function edge is also
still open. The matrix-derived frustum selector includes all 22 captured active
records.

The round-shell topology at `0x1432D3C60` is now implemented too. It is a
16-segment circumscribed cylinder with 192 vertices and 64 outward triangles;
the generated stream matches all 2,304 executable bytes exactly, SHA-256
`8fe24507143963629632edf3c199c15a0bc0911d9af08280adf985f777d7cd46`.
The screen lookup selects box or cylinder from record flag bit 0. A saved active
round probe is unavailable, so output-level round raster validation remains
distinct from the closed source-topology boundary.

## 2026-09-04 scene-light and LightGpu producer recovery

The installed scene scan and exact type-1 node parser now separate static
placed light definitions from the captured runtime light list. Across all 177
pinned zones, 21 placed type-1 nodes occur in five zones; none matches the
captured eight-record group. The captured group is therefore runtime-created
dynamic state rather than a direct serialization of those placed nodes.
`core/scene_lights.py` strictly parses the verified serialized boundary, and
`SceneNodeEntry.scene_light` exposes it without assigning names to unverified
fields.

Static x64 recovery identifies the 0x170-byte persistent render-light record,
its runtime fill routine at `0x1410BE180`, the ten `InitLightSB` capacity tiers,
the mapped-buffer selector at `0x1410A9560`, and the exact 128-byte
`LightGpu`/`LightVolumeGpu` packer at `0x1410A9710`. Its only exact direct call
is `0x1410B37E2` in the `FillLightLookup` path. The main tiers contain 32, 64,
128, 256 or 512 records; the auxiliary tiers contain 128, 256, 512, 1024 or
2048 records; every record has a 128-byte stride.

`LightGpuBaseSource` and `build_light_gpu_base_record()` now implement the
verified captured path. All eight populated capture records rebuild byte for
byte, including float32 Z-bin flooring, inclusive maximum, native attenuation
floor, radiance modes, float16 volumetric-fog packing and legacy
negative-radius compatibility. The prefix SHA256 is
`79c2c34c74d87ac272eb0651d923cf0dc8d0a8f730b2fb8e6b3da0e232e12c69`.
The CPU-only report `light-gpu-producer-validation.json` has SHA256
`29527e3f0f8b6c49b3b35598503b351222d4c769a55dffaa300ecf14e64eeb20`.
The shared subtype-1 auxiliary allocation layer now preserves primary clip,
gobo, three shadow-map slots and ordered shadow-volume allocation, range
encoding and tier-full skips. Native source constructors cover the primary clip
transpose, standard and dual-sign gobo atlas mapping, projected and six-face
point shadow maps, the 0x68-byte shadow-volume boundary, and both subtype-4
color-volume dimension modes. The subtype-3 and subtype-4 static packers now
include their native affine inverses, subtype-specific field rewrites,
auxiliary allocation order, reference encoding and capacity behavior. The
CPU-only report `light-gpu-auxiliary-allocation.json` pins 15 executable ranges
and has SHA256
`a3676dd8e7c145761930c9663874965be0ab665b6c530d7e076b10c6bbfced58`.
Atlas handle resolution is exact given an explicit manager allocation-table
snapshot. The CPU-visible manager candidate predicate is recovered too,
including overflow-safe distance/fade math, ordered flag and emission gates,
16-entry chunk membership and the downstream selected-entry stride. The optional
`completed_chunk_order` input reproduces the exact atomic selected-count
reservation and contiguous copy order; empty chunks reserve no output slots.
The observed frame's scheduler completion sequence remains an explicit input.
Its per-frame owner allocates and zeroes the 0x18a0-byte state, submits primary and
optional secondary pointer queries, schedules the predicate, merges at most
512 entries, reproduces secondary eligibility and bits 29/30/31, applies the
exact skip/defer/priority sequence, ranks priority lights by binary32
projected-bound score, appends deferred lights, and hands the final list to the
persistent/GPU record packer. Equal scores now use the exact retail permutation:
insertion below seven, middle pivot at seven, median-of-three above seven and
pseudomedian-of-nine above forty with Bentley-McIlroy partitioning. The bounded
CPU oracle verifies 34 threshold and mixed-key cases through 512 entries
(`light-manager-equal-score-sort.json`, SHA256
`52d2f7acced0d798248706155bce3708626e4a28c229589da6ad757ea64fa29f`,
case hash `3022e0729e94fe710df264bd2266ff7fd0b16c92a91db0a6e7eb341aea18c4bb`).
Type 0 contributes six allocation units and
other types one. The common query submitter/worker contract now pins the copied
0x100-byte descriptor, caller-owned pointer/count/capacity values, bounded atomic
append and completion signal. The optional secondary query is now exact from
its manager transform to its submitted bytes: center equals translation plus
global forward distance times axis Z, radius is 48.0, and 16 coefficient-table
planes are packed as four component-major 4x4 groups. The bounded oracle
`light-manager-secondary-query-descriptor.json` has SHA256
`1db9e9765713354fe7e0e56e155a578b58bdb4839abafbe73a486eb75865d5fe`
and case hash
`f731f8922b973ca49abfb4a61be629790219c2a483411766b9fc8e4bfcc329d3`.
The independent port report has SHA256
`6e41d1d5ec8f3741414c6ecb3c2fb863565eb32d0c73635e8b4cdae5b4eb6a6c`
and output hash
`a70911832bb756d89177d5453aa3d59006d5e7992a617c062f7b274b6f87998d`.
The common primary descriptor copies six manager planes and derives ten edge
planes from eight points with the exact overflow-safe retail plane helper. The
0x100-byte component-major result matches two bounded oracle cases bit for bit;
the oracle and port reports have SHA256
`0d596d3c4b395c4e24cd615b2792906a636cec6f98daed4491b659eea19a8b47`
and
`028210af8958d9741dfc5106ac7b60b66c3a81338705d6dbb30d189b8f0ead21`.
The primary owner at `0x1412155C0` now covers its view-flag branch too.
Manager `+0x438` bit 1 selects an alternate 16-plane OBB descriptor built from
three axes, extents and translation. Nine ordinary, nonorthogonal and
degenerate cases match the bounded native oracle bit for bit, including signed
zeros, and the owner and direct-builder outputs agree in every case. The oracle
and independent port reports have SHA256
`bade3470b43bc63b992b4f89d1a2aa6924ba59a40312cb5e51025aee11c555e6`
and
`039244de6a160e7e5fd6cdd5d2de1b895ca4c96eb18d449db6bf08263229e775`;
the port output hash is
`0bc515edc8156b77c57ba84d93ea2cbbbe71afda578c50a14773617fb9c54da5`.
The optional primary override replaces planes 11 through 15 from the manager
origin, center, axis offset, extents and terminal normal, then overwrites the
last zero to two slots with authored tail planes. All four enable/tail-count
cases match. Its oracle and port reports have SHA256
`19f6c490ffecdb37563f308700ad2906ef438fef7f13bc9cf1332bed009f209a`
and
`11a43e678d0a45901ae0b63355f7e283a83e9629597f81f56afee72aa4b1b1c6`;
the port output hash is
`69a2ea6dc6961d754c3bb77f9030c7737699216ecb5c04a5ccf75bcab659ef88`.
The basic primary spatial refinement helper at `0x1412B72A0` transforms each
source center and three OBB half axes, evaluates support against all 16 primary
planes, and compacts retained pointers in source order. Its five native-oracle
cases cover 16 sources, boundary contact, fractional transforms, tail-plane
gates and the zero-count path; the production port matches every retained index.
The oracle and independent port reports have SHA256
`cd913360327ab43362e7649acb4a379d672ec13928206b1db5937fdd53fd3a19`
and
`4b2e82fba60065366112b9b771b14bbedf100fee3b2206fd400a4bc065544040`;
the exact output hash is
`7c77ceda29740d070eab319827808f2df481a52db8336316ae99bfee7827fae2`.
The optional refinement helper at `0x1412B78B0` repeats primary membership,
then evaluates four component-major planes as an exclusion volume. It removes
only OBBs strictly inside all four planes; boundary contact or crossing any
plane stays visible. All 20 sources across five exclusion, primary-precedence,
transformed and empty cases match native ordered compaction. Its oracle and port
reports have SHA256
`be69572e6145680f590c3c9cf40a8ee21a6fc03812d60f704714f9d984819a5a`
and
`bd8b20e2338c93452b0bf6eb9a7eeacf26bd299b8cb41682335a692893081946`;
the exact ordered output hash is
`97d534c56709b41fb8ee71f436065952d48ff9710f79a7870cfb66a1323cbef2`.The spatial cell front end is now reproduced through its consumed outputs.
Classifier `0x141603A80` returns intersection and full containment for a
center/half-extent AABB, letting the worker skip per-entry coarse tests for
fully contained cells. Helper `0x141603D40` emits intersecting cell indices in
input order at both observed 32- and 48-byte strides. The consumed intersection
output of oriented helper `0x141603FE0` also matches all eight cases. Seven AABB
cases, three batches and eight oriented cases match the native oracle. The
oracle and independent port reports have SHA256
`54a75db361683fdd21f7e804a9016e2ed2a2c6b5864b4805b7e1a30b9a47fed6`
and
`216aca809858c90598a017d28ae0a9a0f465f03127e86adc43d967bd9a321441`.
The oriented helper's query-coverage output evaluates support minus distance across all 16 planes; it and intersection match all eight native cases.
The spatial-bound packer and admissibility gate match 7 and 5 native cases; their oracle and port reports have SHA256 b89305c55d2a9b3f2c971c00e147f79767c40f6289514f5f0e211ca4141aee5d and 5fe4e71938a631909684f5f50d5cc2c507d5c33a4a87c39dbb52a978df6bd95d.
The static spatial-database layout/lifecycle report pins ten retail ranges and recovers eight 0x70-byte owners, 0x30-byte cells, 0x100-byte pages with 15 entries, 0x10-byte packed entries, `(page << 4) | slot` handles, insertion, swap-compacting removal, bound updates and dirty-cell rebuilding; its SHA256 is `66eb7e352db2077435fb6905475c4b9e87a625c92c95ef537c13631ad5dff304`. Live runtime contents and scene membership remain external.
The static tree path is now recovered through exact retail allocation, lookup and subdivision. Nodes are 0x20 bytes with eight uint16 slots; lookup consumes one signed-coordinate bit per depth in x/y/z slot order and distinguishes cells from child nodes with the slot high bit. Subdivision derives child origins, parent links and depths exactly, then redistributes entries in source append order while reusing occupied octants and rebuilding each child bound with the same signed-int16 sphere union. Ten lookup cases, six link-prelude cases and three full redistribution cases covering 16 entries match the bounded native oracles. Native/port report SHA256 pairs are `81b02ec7ff56ffc5af8bf04b0ee5eb2d3280edb47466217ca4d8e5704023adc7` / `85b61894e9499e8098e1b6cef019f6d6045dd98670964607857dcbd92564fdd1`, `44969d03fcd4e628ab2bf6b9d9b14b3d05f5d1e2ab7415c703bc692a25122e12` / `e42ad75baf30befcffe586fa7d2c2c20bb961008ed870d6fc81d8db1d3fe6b88`, and `b1b90db7e8e6af853479e5b0622104136ad6d306199b6260308a87b0f5fa68dd` / `3f34021b52d11f5106072fe218815525f52eddf00d337199971a8fb5b8309698`. The removal tail at `0x141669C7D..0x141669D77` completes static tree symmetry: it clears the released cell slot, retains a node with any occupied sibling, prepends empty ancestors to the free list, repairs the maximum active index only when required and clears the root after releasing the final ancestor. Six sibling-retention, nonmaximum, gap-rescan, two-ancestor and root-release cases match native output exactly. The native and port report SHA256 values are `f30a9a8a69c9011bf3617cea643cd12c1d8615212b444ce6ecb8a9f5663c21a3` and `37f8f6b45e3cf86b5e66484c9b219ded7307b60a4db7aa3eff4e50b5ea21b277`; their shared semantic output SHA256 is `074375c5eb37b244a8c79a7ee701186544e69b6266f66cc7c58e5ca675150e72`.
The dirty-cell rebuild port matches 23 packed entries across five single-page, linked-page and signed-saturation native cases bit for bit. The oracle and independent port reports have SHA256 `0b746abb20109519392e4e42693377930195151819c39a05c60a323e8eec8bfe` and `f6f1b93ceb5a174093e5b83e25d7f48140a8a6d507a01436156b2dad855ed993`; their shared output SHA256 is `1d312100d5abd9e9dfdeecc40c790d15388bb8efd0703951215c4ed21a632824`.
The worker's three-state packed-sphere classifier matches six native direct, ambiguous and rejection cases; its oracle and port reports have SHA256 `d003024e9ad7f504a4ed40b84b445757b9f81004fc6037ae1a28184b04a7f71f` and `357f636f19a321589ba35bf056dc29cad632efa93780be35f342e6727a941723`. The explicit raw-page decoder and newest-to-oldest primary bucketer pass three contract cases in `light-spatial-page-chain-port-validation.json` (SHA256 `b58e0c8d048cf82db9bbbfe0f00726b05c4ef7ee02c51c23d79b22982bdd5e5c`).
The bounded primary resolver prepends direct indices, runs ambiguous indices through the native-verified exact OBB predicate and applies output capacity. Its three native-linked cases pass in `light-spatial-primary-resolution-port-validation.json` (SHA256 `3ca2fc599260dc354ca55748e73dbe15b50a4d018d5be9d1e6f507e53fcaa006`).
The optional worker classifier at `0x1412B8FB0` also matches six native
direct, ambiguous and rejection states. It applies the primary sphere gate,
rejects spheres fully inside the optional exclusion volume, and routes
surviving boundary cases to exact optional OBB refinement. Its oracle and port
reports have SHA256
`7accdfc006f6f20ee81ecc7b97b79dde0cba25c0ac52635dc0e3bad464a78b62`
and
`e1ab7a1a012a6dc01cc57040c2732f4734b6339eeb524767693b40aea79a0086`.
The optional raw-page bucketer and bounded direct-first resolver pass a linked
page case plus three native-refinement/capacity cases; their report SHA256 is
`204784599a701d9037f30d2470f47e0a33960280ad674e16c9f7873a98e75829`.
The worker's midstream and final flush blocks now match seven bounded retail
cases. A bucket flushes only when `count + 15 > 1024`; direct pointers
reserve and copy before exact-refinement output, capacity clips each
reservation, and final cleanup repeats that order. The native oracle and
independent port reports have SHA256
`7b5d2685cc75a6c7531d4d309036fe0edbd34ee373f54796339e0ce72728e19f`
and
`26bcd6b3693230ad8e7cb71a2ef00c54d5c92f195add4e308406851871c61421`;
their exact shared output hash is
`3f2308c237c7630b26b766114fa5bac56062a40c0d17de3efe219e0ec4fac53e`.
The full primary and optional page-stream resolvers now preserve intermediate
flush interleaving as well as final direct-before-refined order.
Each final source creates a 0x170-byte persistent
record whose `+0x140` stream and `+0x13c` count are consumed through the same
record pointer by the full and opaque `FillLightLookup` shell passes.
Object visibility, resource readiness, type-resource availability, the
auxiliary-volume plane classifier and bit-21 deferral now evaluate from explicit
snapshots. The source-side view wrapper builds the exact oriented-box input and
`0.01` bias consumed by the manager's 16-bit hierarchical-depth test. The full
`0x14118CE60` consumer is now implemented from an explicit snapshot: it projects
eight OBB corners, computes the pixel rectangle and conservative 16-bit depth,
checks level-zero corners, chooses the span mip, rejects from its four corners
and otherwise scans masked signed-int16 maxima in the base rectangle. Nine
bounded native cases cover every return path and match the independent port.
The native report SHA256 is
`993a854927faefe5b32caeab38fcfe3e718b8fb70ded32a1e8fbf70172fb6f75`, the port
report SHA256 is
`2d3bc22fc10bf3b7a85fe5fd386f5aacb0373579666cec260527a155ea890714`, and their
shared semantic output SHA256 is
`0680e5a4f26a9e629e235b5583b8f1edb40a6f7702770cd5d41d96b889d1c663`.
The resource-version and refresh boundary is recovered too. Its raw CRC cache,
per-type dispatch, zero-count behavior and padded float3 allocation are exact.
All selected geometry sources are implemented: the authored box and rounded
tables produce 36 and 432 vertices, while the two circumscribed cone builders
produce 216 and 48 vertices using the retail scalar trigonometric polynomial.
Six isolated executable samples match every XYZ float bit. The only direct
refresh call is `0x1410BAD85`. The refresh builds six planes from an optional
resolved oriented box, partitions them around the source origin or type-3
negative local Z, inserts the lower-Z then upper-Z type scalars between the
partitions, and applies the resulting world planes sequentially through the
existing clip/cap path. No camera object is passed at this boundary.

Output helper `0x1410B8CB0` copies exact XYZ values, writes the local AABB and
computes its sphere from the AABB midpoint and farthest vertex. For source types
other than 3 and 4, the refresh calls `0x1412B6AA0` when the new half-extent
volume is below 98 percent of the old bound volume; the helper writes center,
radius and half extents and marks the source dirty. Five clip-plane cases and
both output samples match the CPU-only Unicorn oracle bit for bit.
`light-manager-selection-validation.json` pins 84 retail executable ranges and
15 static tables, with composite clip/output hash
`59f74079f39ef78bcabacbe6c22424b7665d64fff6bf8b0c0ad40fef272ba414`.
Its SHA256 is
`9ad136cab3adc0b29bab4ab308d13ce91826910cbb85f18f8630e57f211dc608`.

The cooked subtype-1 input boundary is implemented in
`SceneLightType1RuntimeTransfer`. The exact common converter and type dispatcher
establish semantic names for all 13 serialized scalars: intensity, attenuation,
cutoff and cut-on radii, specular intensity/fade, general fade, inner/outer cone,
bulb radius/length/push and shadow cut-on distance. Serialized `+0xB0` is
volumetric-fog intensity and reaches the GPU through runtime `+0xB4` and
persistent `+0xF0`. The model also reproduces the native `0.01` attenuation
override floor and flag derivation. The CPU-only report
`scene-light-runtime-transfer-validation.json` hash-gates 15 retail ranges and
checks all 22 extracted records, including all 11 native subtype-1 records.
The scalar derived initializer now covers automatic color radius, the native
polynomial trigonometric pair, cone ramp, cutoff, cut-on and local culling-shape
inputs. The resolved-transform commit reproduces handedness, nonuniform-scale
and median-axis classification. The `0x1402BD1A0` source-matrix helper now reproduces oriented orthonormal
local-basis normalization, native degenerate fallbacks and translation
preservation. Constructor `0x140FDFA10` normalizes source-descriptor byte `+0x3B`
into owner-state `+0xC6`. Selector `0x140FE5C30` prioritizes an embedded `+0x60`
override, the already-world fallback, a non-null `+0x10` holder transform and
the null-holder fallback. Address `0x146838510` lies in unbacked `.data`; its
concrete runtime value is not inferred. The complete placement routine at
`0x140FEED30` either keeps the raw record matrix or computes
`record_local * owner_transform` at `0x141627F80` before the runtime apply at
`0x1412B6BF0`. Four selector cases and four composition cases match production
bit for bit with output SHA256 values
`f896b0d5835c075302996f6b690a9750586efaad37624dfdb00352ed26d0d1ae` and
`6d191d26b08857050303e9d4f7b5dd2fb7a54aadaf7d8a667f0dc04c7a7179ce`.
The static source audit SHA256 is
`53170f909032cbca6fc2af5e00c6dc69868a1b026dc7ec54aa47f0b8092f15a2`.
The native and port report SHA256 values are
`9f36d5aad10a5bfb0fadce0e5410c87460341a4ea4f3b57eb67bc5c9c7a3daf8`
and `84b79696fc97d3425bae6d5a81fb563d16a948474c75bb2af0a347d8b3f15db8`.
The 17-range integrated report SHA256 is
`b3caea75910e954aed6c4f3b569c7e642c22dc9ef84ce9d4a789377d4d73f3e0`.

All 593 CPU tests, including the independently passing 201-test local-light module, and all 53 offline
shader cases pass at this boundary. The shader report remains SHA256
`b272aeb05a0f139cfdf22d3d9c6ce5bb1537a4fae07755005cbd866f99efae4a`.

The capture supplies packed outputs but not the 0x170-byte packer inputs, and
none of the captured Hair pixels selects a local light. Remaining evidence work
is the live spatial database and scene membership, the live manager view values and populated hierarchical-depth words,
captured resolved-resource
inputs,
the frame-specific runtime scheduler completion sequence and captured placement/prepared-stream
values, including the concrete owner transform selected for that frame, followed by an active-Hair
local-light capture when game work resumes.


## 2026-09-05 — returned to fur and lighting, including sheep

User redirected work from smoke to fur/lighting and explicitly included sheep. Current priority is visual fur and scene illumination for Ratchet and sheep, not further smoke or unrelated scene-manager tracing.

Fresh sheep LOD0 model959F9CE032472D83 was rendered through the current production viewport at480x480 logical pixels, 33 accumulated samples. Native raster and deferred Hair lighting are active. Readbacks validate45273 Hair mask pixels, finite fur color, native color storage at both lighting/denoise boundaries, preserved314727 non-Hair pixels and shared depth/stencil attachments. This is internal pipeline verification, not comparison against retail sheep pixels.

Matched camera/material/sample-count control disables only the fur environment. Visual inspection shows the installed default cube supplies much of the blue cast and brightness; the control is substantially darker and warmer. Do not treat removal of the environment as a fix or apply a guessed sheep preset. Authored length0.09, density3, offset0, layers32 remain unchanged. Current full wool is visually cohesive; no claim of retail parity without a matched native reference.

Evidence: outer artifacts/rcra-fur-continuation/sheep-lighting-resumed.json/.png, sheep-lighting-no-environment.json/.png, their job reports, and sheep-lighting-comparison.json/.jpg. Both jobs exited0 on inactive desktops with input desktop unchanged. Primary job peaked1.328GiB under3GiB cap; renderer RTX5060Ti. No game launched. Saved earlier Ratchet pose and native lighting evidence remains valid within its documented scope, but was not re-run this turn.

Next: obtain/select valid scene illumination for the intended character placement and camera, then make controlled Ratchet/sheep lighting comparisons. A captured Ratchet resource bundle must not be called sheep-native lighting without matching placement/view. Animated sequence and same-frame retail appearance validation remain open.

## 2026-09-05 — reproducible Ratchet/sheep relighting

Added Viewport3D.set_preview_light_direction and smoke tool --preview-light-direction. The isolated-view key is normalized, copied and validated; changes invalidate temporal history. Existing default direction is unchanged, and valid scene lighting retains its native key. The smoke CLI rejects combining this preview override with a scene bundle. Five focused CPU tests pass; modified scripts compile and diff whitespace checks pass.

Three sequential bounded inactive-desktop renders compare default key(0.6,1,0.8) with alternate key(0.6,0.3,-1) for Ratchet head and sheep. The sheep default from the immediately preceding checkpoint is reused. build_relighting_comparison.py verifies matched camera, logical viewport,33 accumulated samples, environment metadata and authored material fields within each pair; both paths use deferred lighting. All jobs exit0 with input desktop unchanged and memory below3GiB. Comparison images were inspected. These are controlled editor-lighting tests, not matched native scene parity. Ratchet shows a stronger visible key response; sheep remains dominated by the default environment contribution, consistent with the preceding environment-off control.

Artifacts: fur-relighting-comparison.jpg/.json and build_relighting_comparison.py in outer artifacts/rcra-fur-continuation. Individual ratchet-relight-default, ratchet-relight and sheep-relight PNG/JSON/job/log files preserve inputs. Local static comparison page: /fur-lighting.html on preview port8769. This page has no render loop or GPU workload.

The saved native scene bundle remains camera/placement specific and was not attached to these unrelated isolated models. Next is a valid scene-probe and placement reference, then matched scene relighting for Ratchet and sheep. Default environment color should not be corrected by altering authored wool/albedo. Full native animated/frame parity remains open.

## 2026-09-05 — dry/wet wind animation preview

User requested trying the animation. Added bounded --animation-frames (0..96) and --animation-fps (1..24) to smoke_fur_viewport.py. Sequences begin after convergence, advance explicit shader time and retain renderer history via grabFramebuffer. Animation requires an explicit initial wind time and rejects simultaneous time-step mode. GIF and JSON retain48 sampled frames,12fps and per-frame shader times/image-change metrics. This is fur wind deformation, not skeletal animation.

Rendered Ratchet head and sheep, wetness0 and1, sequentially on inactive desktops with200-second job limits and3GiB memory caps. All four jobs exit0 with input desktop Default. Wind strength0.3 is a deliberate stronger diagnostic, compared with saved native0.0309733; direction/time/object phase use saved captured inputs. Original material turbulence remains unchanged, including sheep0. The default environment is used. Motion was not compared with a matching native sequence.

publish_wind_preview.py checks all reports/GIF frame counts and creates /fur-animation.html on local port8769. One selected sequence plays only after clicking Play and pauses on tab hiding; model/wetness changes return to a still. Representative frame24 dry/wet contact sheet was visually inspected. Pixel changes include temporal sampling and GIF quantization and are not a pure geometric displacement metric. Artifacts: {ratchet,sheep}-wind-wet{0,1}.gif/.png/.json/-job.json/.log, fur-wind-validation.json, fur-wind-contact.jpg. Source syntax and whitespace checks pass. No native game launched.
