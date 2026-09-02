# Character Fur Rendering Handoff

For a clean checkout and continuation on another Windows computer, start with
[`FUR_RENDERING_TRANSFER.md`](FUR_RENDERING_TRANSFER.md). This document is the
detailed evidence and implementation log; the transfer document is the
machine-independent operating checklist.

Date: 2026-08-31  
Branch: `main`  
Fork: `https://github.com/RayMunozEng/RCRA-Forge`  
Status: **active experimental renderer; continue improving toward retail parity**

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

- `c0b4ccc` — parse and load shipped fur material textures
- `a20bc37` — remove incorrect generated shells and hide untextured composite helpers
- `2da9dd7` — add the current experimental geometry-shader strand pass
- `38f1a45` — update the public verification capture

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

1. **Invented root distribution** — exactly three fibers are emitted at fixed
   barycentric positions per triangle, so density follows mesh triangulation.
2. **Unverified channel semantics** — the shader assumes fur-control RG is comb
   direction, B is length, and A is density. That mapping is plausible from
   channel statistics but has not been decoded from the retail shader.
3. **Arbitrary dimensions** — strand length and width constants are hand-tuned,
   not read from confirmed material parameters.
4. **Incorrect shading model** — fibers use basic diffuse lighting only. There
   is no anisotropic specular response, backscatter, self-shadowing, roughness,
   or strand normal model.
5. **Transparency artifacts** — camera-facing ribbons use ordinary alpha
   blending with depth writes disabled and no order-independent transparency.
6. **Aliasing** — texture sampling is forced to mip 0 in the geometry shader,
   and there is no alpha-to-coverage, strand-aware antialiasing, or temporal
   stabilization.
7. **LOD sensitivity** — root count changes with model triangulation. The
   published capture is LOD1 and therefore does not prove LOD0 quality.
8. **Performance unmeasured** — the full Ratchet model has multiple fur
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
the depth-backed path—not just the shader program—was active.

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

The stochastic threshold now follows the exact DXBC ordering: shifted pixel
coordinates use `round_ni` (round to nearest, half-way ties to even),
`x + 2*y + integerFrame + spatialHash` is multiplied by 0.2, and the
fractional part is used as the cutoff. This five-band temporal sequence
eliminated the persistent stipple caused by the earlier fractional golden-ratio
phase.

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
is rejected. Automatic archive reconstruction of arbitrary local probe arrays
remains unresolved.

