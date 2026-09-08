# Fur Rendering Computer Transfer

Latest 2026-09-05: read [FUR_POSE_STREAMS.md](FUR_POSE_STREAMS.md) for paired deformed-position integration, bounded camera-motion results, static-image regression, and the remaining animated-frame parity boundary. The generic TAA capture is a menu frame, not a fur appearance reference.

Newest continuation: read
[HAIR_TEMPORAL_RECONSTRUCTION.md](HAIR_TEMPORAL_RECONSTRUCTION.md). Guarded
runtime event 20572 matches the executable-extracted native
`CS_TemporalAaApply` byte for byte and supplies the full 224-byte cbuffer plus
all eight resource bindings. Captured jitter/filter, 0.04 response, 0.0625
floor, HDR scale, history age and dither index/phase validate the static builder.
The fork exposes a typed binary contract and deterministic runtime-vector tests;
all 283 CPU tests and 24 offline shader cases pass. Matched input/output resource
bytes remain open. Continue from the saved capture without launching the game,
using a reduced or peak-measured replay rather than the retired live controller.

Current continuation: read [HAIR_CONNECTED_REPLAY.md](HAIR_CONNECTED_REPLAY.md).
The production scene lighting/store/denoise chain now matches all 11,215 native
Hair pixels. Native history, combined resolve, scene timing and fractional
neighbor masks are connected; native gather addressing fixes the post-pass
boundary errors. The viewport now writes the fifth RG16F fur material target from
previous camera and wind state and consumes it for Hair history reprojection; see
[FUR_MOTION_PATH.md](FUR_MOTION_PATH.md). Native raster, generated-motion
validation and retail temporal rejection/depth-history parity remain open; a
longer private no-save capture is deferred until game work resumes.
The offline motion audit now proves the six-register post-VS layout, finds
previous-pose changes in all 18,630 referenced vertices, and reconstructs both
base-shell clip positions within `5.67e-7`. The future GPU comparison helper
now supplies the previous skin stream, object/camera matrices, and previous
wind time, and requires explicit `--allow-gpu`; it has not been run.
The required whole-pipeline raster change is inventoried in
[FUR_RASTER_COORDINATES.md](FUR_RASTER_COORDINATES.md).
The temporal resource inventory and the minimum later capture are in
[HAIR_TEMPORAL_RECONSTRUCTION.md](HAIR_TEMPORAL_RECONSTRUCTION.md).

Latest scene integration: start with [HAIR_SCENE_LIGHTING.md](HAIR_SCENE_LIGHTING.md).
The viewport now accepts explicit per-view grid/probe/cube resources and the
native key-shadow atlas. Its captured full replay still matches all 11,215 stored
Hair pixels. Native packed-buffer checks, atlas/contact composition and live
camera/resource lifecycle checks passed. Reflection history, complete scene
loading, native raster/motion/temporal state and composed-frame validation remain.
The local checkpoints are listed in [FUR_PARITY_CHECKPOINTS.md](FUR_PARITY_CHECKPOINTS.md).

Latest material/lighting integration: read
[HAIR_MATERIAL_RESPONSE.md](HAIR_MATERIAL_RESPONSE.md). Shared native material
response, environment frames, diffuse/transmission and final resolve now drive
the viewport. The full captured replay retains all 11,215 exact stored pixels.
Both deferred Hair color stores use measured R11G11B10 precision. Dry/wet/fallback
previews, native store comparisons and all 270 tests pass. Full scene illumination,
matched raster/motion/history and composed-frame validation remain.

Newest integration: read [FUR_DEFERRED_PREVIEW.md](FUR_DEFERRED_PREVIEW.md).
The HDR preview writes five native material targets, decodes the four shading
inputs in a separate GPU program and evaluates lighting afterward. The production
material writer before motion integration matches 24,226 captured pixels across
four wetness levels; the shared five-target raster replay is exact there.
Production vector decoding matches all 11,215 native normals/strands. Layer
clamping, lobe-frame orientation, unblended opaque depth, projection jitter and
motion-aware preview history were connected. Other scene variants, native raster,
retail temporal rejection and composed-frame parity remain incomplete. Use the
new document's verification commands/evidence.

Latest 2026-09-03 continuation: read [HAIR_FULL_REPLAY.md](HAIR_FULL_REPLAY.md).
The complete captured Hair lighting diagnostic now has **11,215/11,215 exact
stored pixels**. Unquantized float RGB remains slightly different. Native
BC6U/seamless cube sampling, the verified DXIL noise function and shared direct
lobes are integrated into the ordinary viewport; its full
scene/deferred/temporal parity remains incomplete. All 270 tests and the viewport
GPU smoke pass. All temporary private jobs are closed.

Newest geometry/material work: read [FUR_CAPTURE_PARITY.md](FUR_CAPTURE_PARITY.md).
The full dry captured draw matches every stored G-buffer target and hardware
depth, with all 6,308 coverage pixels exact. The diagnostic uses native raster
origin; the ordinary preview's complete pipeline still needs that migration.
It corrects coverage rounding and coordinates, exact texture generation, packed
vertex decoding, wind bending, grooming, and contact depth against the fresh
head draw. Native material packing now matches all 6,308 surviving pixels and
is stored in native integer targets before deferred preview lighting. Do not rely on the older nearest-even,
dry UV dithering, or reciprocal-depth buffer claims; the captured buffer stores
linear view depth.

Read [HAIR_DENOISE_REPLAY.md](HAIR_DENOISE_REPLAY.md) for the newly integrated
denoiser, its measured half-depth conversion and full-pass comparison. All
11,215 stored pixels, float RGB values and color/weight sums now match exactly.
All 270 tests and the earlier wet preview GPU smoke pass. Complete scene lighting,
native raster orientation and temporal reconstruction remain to be connected.
`core/hair_surface.glsl` now supplies the denoiser's camera reconstruction;
the shared-surface replay retains every exact float/color-sum result.
The new key-contact resolve runs before denoise/history and preserves environment
light. See [HAIR_CONTACT_REPLAY.md](HAIR_CONTACT_REPLAY.md) for GPU evidence and
the remaining full-depth/scene-lighting limitations.

Date: 2026-09-03

Repository: `https://github.com/RayMunozEng/RCRA-Forge`

Branch: `main`

Source of truth: the commit containing this document

This is the operating handoff for continuing the Rift Apart fur renderer on a
second Windows computer that has its own installed copy of the game. The
detailed reverse-engineering record is in
[`FUR_RENDERING_HANDOFF.md`](FUR_RENDERING_HANDOFF.md).

## Current outcome

The active viewport uses the retail shell-fur architecture, not the retired
camera-facing ribbon prototype:

- exact procedural `Default Fur Shells` 128 x 128 x 32 R8 volume and integer
  mip chain;
- authored per-material layer count, length, density, offset, gloss,
  specular, transmittance, and turbulence;
- decoded tangent frame and handedness from the cooked vertex stream;
- fur-control RG grooming, B extrusion/contact/wind gate, and independent A
  material interpolation;
- recovered shell availability, projected stochastic coverage, wetness,
  native key-contact resolve, HairDenoise gather, Hair direct lobes, default
  environment cube, and exact Hair BRDF lookup;
- captured retail wind field with configurable time, strength, direction, and
  object phase;
- off-desktop, non-activating screenshot verification.

Cooked environment records now resolve texture references and runtime scene
draw lists. The baked BC6 probe atlas decoder is recovered from
`CS_CopyEnvProbe` and verified against all 60 installed texture variants in
the Megalopolis/Malinon inventory. Explicit atlas overrides work in the smoke
viewer; automatic local-probe selection and blending are still unfinished.

The exact captured Hair shader hash was also found in the executable.
`core/probe_lighting.py` now reconstructs its GPU records and spatial/sample
weights with explicit zone transforms and runtime inputs. A raw-buffer CLI
can evaluate a captured point/mask. The spatial kernel passed 47,229 CPU/GPU
comparisons; connecting verified records to the viewport is the next stage.

The second-computer continuation also decodes all level regions/checkpoints,
recovers the complete Hair light-grid branch, and connects grid/probe kernels
in an explicit offscreen replay. See
[`HAIR_INDIRECT_REPLAY.md`](HAIR_INDIRECT_REPLAY.md) for captured-resource input
requirements. The grid passes 4,096 comparisons against the original shader
instruction slice; the combined upload path passes 192 controlled queries.
The Malinon streamed grid and Sargasso inline grid formats are decoded. An
optional isolated x86 emulator executes the verified retail interpolation and
fallback initialization. Stored grid positions are copied directly into the
runtime lookup path; its coordinate hash and integer fade packing now match
original instructions bit for bit. `tools/reconstruct_light_grid.py` builds
replay resources with explicit asset/fade selection and compacted slots.
The complete 354-brick Sargasso candidate passes 4,096 original-shader comparisons
(max error 4.7684e-7) and 192 combined replay queries (max error 1.1921e-7).
The valid-entry collision decision also matches original instructions in 331 cases.
Actual capture residency, probe placement and original frame resources remain
unresolved. These kernels have not replaced the ordinary viewport's environment path.

The user does not know the original capture location. Local searches found no
RDC in readable storage and likely user folders; do not ask that question again.
Fresh retail D3D12 captures now record and replay on an inactive private desktop.
The user approved the focus shim, which is loaded and verified. Native device
creation (`-noStreamline`), headless RenderDoc Start/EndFrameCapture and the
separate WM_NCACTIVATE notification resolved the capture/startup blockers.
A saved profile-selection capture replays successfully, but an actual character
reference is still required. Read [PRIVATE_CAPTURE.md](PRIVATE_CAPTURE.md) for
current bounded-session reports, evidence and temporary settings to restore.

This is evidence-backed progress toward retail parity, not a parity claim.
Production local-probe reconstruction, the full deferred/G-buffer integration,
and production temporal history behavior remain incomplete. Sheep uses the
same retail shell pipeline as Lombaxes but retains its distinct authored curly
surface and 9 cm / density 3 material; it must not receive a fabricated
Lombax-style preset.

## Files that carry the implementation

- `core/material.py`: special fur material parsing and authored settings.
- `core/mesh.py`: packed tangent-frame and handedness decoding.
- `core/texture.py`: authored mips, BC6 cubes, and packed probe atlas decode.
- `core/environment_probes.py`: cooked probe records and resource references.
- `core/probe_lighting.py`: GPU probe records, transforms, sorting, and Hair weights.
- `core/light_grid_assets.py`: inline/streamed containers and cooked brick codec.
- `core/retail_light_grid.py`: optional isolated retail interpolation/fallback reference.
- `core/light_grid_resources.py`: verified lookup packing and explicit replay resources.
- `tools/reconstruct_light_grid.py`: full asset reconstruction with an explicit fade.
- `core/fur_resources.py`: exact shell volume and embedded exact Hair BRDF.
- `core/asset_loader.py`: fur texture/environment background loading.
- `ui/main_window.py`: fur environment handoff into the viewport.
- `ui/viewport.py`: shell geometry, grooming, wind, water, Hair lighting,
  contact, denoise, and temporal accumulation.
- `tools/analyze_material_headers.py`: installed-material evidence scanner.
- `tools/analyze_environment_probes.py`: zone probe dependency inventory.
- `tools/analyze_probe_buffer.py`: raw GPU buffer and lookup-mask analysis.
- `tools/smoke_fur_viewport.py`: off-desktop GPU verification harness.
- `tools/private_desktop.py`: bounded Windows capture launcher and owned-job cleanup.
- `tests/test_material_resolution.py`, `tests/test_parsers.py`, and
  `tests/test_viewport_textures.py`, `tests/test_probe_atlas.py`,
  `tests/test_environment_probes.py`, `tests/test_probe_lighting.py`, and
  `tests/test_fur_environment.py`, the level/actor regressions, and the new
  grid/replay regressions: **238 tests pass** on the second computer.

## First setup on the second computer

Open PowerShell and clone the fork:

```powershell
git clone https://github.com/RayMunozEng/RCRA-Forge.git
Set-Location RCRA-Forge
git switch main
git pull --ff-only
```

Create the environment without launching a foreground window:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
```

If `py` is unavailable, install Python 3.10 or newer or use that machine's
Python executable. `run.bat` performs equivalent one-time dependency setup but
also launches the application.

Set a machine-local game path. Do not commit this path:

```powershell
$GameInstallPath = 'D:\SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart'
Test-Path -LiteralPath (Join-Path $GameInstallPath 'toc')
```

The test must print `True`. The repository already contains the tracked
`hashes.txt`. The parser may generate `hashes.txt.cache`; it is intentionally
ignored and can be regenerated on either computer.

## Required verification before changing the renderer

Run the complete automated suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Then run a head-only LOD0 GPU smoke capture. This window is deliberately
off-desktop and non-activating:

```powershell
$GameInstallPath = 'D:\SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart'
$TransferOutputPath = Join-Path $env:TEMP 'rcra-fur-transfer'
New-Item -ItemType Directory -Force -Path $TransferOutputPath | Out-Null
.\.venv\Scripts\python.exe tools\smoke_fur_viewport.py `
  --game-root $GameInstallPath `
  --hashes .\hashes.txt `
  --model 0xAA4A5371E9C251F7 `
  --lod 0 `
  --samples 5 `
  --converge-samples 32 `
  --width 1024 `
  --height 1024 `
  --output (Join-Path $TransferOutputPath 'ratchet-head.png') `
  --report (Join-Path $TransferOutputPath 'ratchet-head.json')
```

Acceptance evidence is both the PNG and JSON report. The report must show a
valid OpenGL context, active fur material(s), rendered shell instances, and
`recovered_procedural_128x128x32` as the layer source. A screenshot alone is
not sufficient.

The smoke tool now shares the application's default Hair environment loader.
Normal captures must also report `fur_environment.source = installed_default`,
`gpu_ready = true`, six faces, six mips per face, and the embedded BRDF hash
listed below. Older default smoke captures omitted these resources and are
not equivalent to the application's lighting. `--disable-fur-environment`
retains that path only as an explicit diagnostic. Captured environment
overrides use the embedded exact BRDF unless `--fur-brdf-dds` is supplied.

To exercise the exact captured weather state:

```powershell
.\.venv\Scripts\python.exe tools\smoke_fur_viewport.py `
  --game-root $GameInstallPath `
  --hashes .\hashes.txt `
  --model 0xAA4A5371E9C251F7 `
  --lod 0 `
  --samples 5 `
  --converge-samples 32 `
  --fur-wind-strength 0.030973274260759354 `
  --fur-wind-vector -0.9966111779 0 0.0822560638 `
  --fur-wind-time 104.03866577148438 `
  --fur-wind-object-phase 0.1326904296875 `
  --output (Join-Path $TransferOutputPath 'ratchet-head-wind.png') `
  --report (Join-Path $TransferOutputPath 'ratchet-head-wind.json')
```

The full Ratchet asset is `0xADE5909F821E9DDE`. Use it after the focused head
test passes; it is materially heavier and exercises the head, limb, and tail
fur materials together.

To regenerate the installed-material correlation evidence on the second
computer:

```powershell
.\.venv\Scripts\python.exe tools\analyze_material_headers.py `
  --game-root $GameInstallPath `
  --hashes .\hashes.txt `
  --output (Join-Path $TransferOutputPath 'material-header-correlation.json')
```

## Retail evidence that is not in Git

The following items are intentionally excluded because they are large,
machine-specific, generated, or redistributable game/capture data:

- the installed Rift Apart game and its archives;
- RenderDoc 1.46 portable binaries;
- `work/fur-analysis/captures/riftapart-taa_frame7328.rdc` (about 5 GB);
- extracted frame-7328 textures, buffers, shader disassembly, and JSON reports;
- generated PNG comparisons under the workspace `outputs` directory;
- `hashes.txt.cache` and `hashes.txt.cache.cache`.

The renderer does not require those artifacts. Copy the capture/research
workspace separately only if the second machine must continue exact retail
frame analysis. Otherwise create a fresh capture from that machine's own game
installation. Never launch or hook the retail game on the user's active
desktop during automated work: use the established private-desktop/background
capture path so mouse focus and input remain untouched.

The most useful local visual evidence from the originating machine is:

- `outputs/retail-frame7328-ratchet-crop.png`: retail reference crop;
- `outputs/ratchet-retail-local14-wind-v88.png`: focused dry/wind viewer result;
- `outputs/ratchet-full-local14-rear-close-v89.png`: full-character rear result;
- `outputs/ratchet-retail-local14-wet-v90.png`: recovered wetness-path result.

Captured local cube 14 is valid only for the recorded frame/location. It may be
injected into the smoke harness with `--fur-environment-dds-dir` and
`--fur-environment-cube 14` after copying the extracted DDS directory, but it
must not become a generic default or be presented as archive reconstruction.
The normal application path loads the installed default environment probe and
embedded exact BRDF automatically.

For an explicit installed baked-probe check, pass
`--fur-environment 0x837545B07B72296F` without captured DDS arguments. The
decoder extracts six 256 x 256 faces and six mips from its 1024 x 512 atlas.
This is a texture override, not an established match to captured cube 14.
The detailed handoff records matched-camera Ratchet, Rivet, and Sheep checks;
a default-probe control remained pixel-identical after adding the decoder.

## Evidence anchors

- Hair compute event 68471, shader hash
  `5ff73b6b2aca9640cf18cd78b88ba3c0`.
- HairDenoise event 68478, shader hash
  `d1bd89676f0e3560ee38fd16c950de23`.
- TAA apply shader hash `4e1b2693fbe9696f3f1eb1d6ac577a01`.
- Default environment asset `0x8F083136CEB5FB07`, a 1024 BC6 cube with six
  faces and six mips.
- Exact 64 x 64 RG16F Hair BRDF slice SHA-256
  `4fa9755a296ec4c8c11d19e62598217eedd8625814bb75128c947ca325038672`.
- Captured Ratchet head center `(-230.588, 9.146, 670.816)` selected local
  probe record 10 / cube-array index 14 at full weight.

## Fresh capture milestone â€” 2026-09-03

Fresh gameplay captures and the exact Hair event are available locally; see
`PRIVATE_CAPTURE.md`. Native BC6U replay now passes 16 captured indirect-lighting
queries against D3D12-verified samples (maximum error 1.1921e-7). This is limited
to full grid fallback plus local specular probes, not full renderer parity.
The active record 10 / cube 18 is runtime draw-list probe F896FB5315175B7C in
9C292F5F8A79EEC2 / tile_zz27_lgt.zone. Its first 124 GPU bytes match the cooked
record builder with identity placement. It must be generated from the scene or
supplied from the explicit capture; no nearby baked texture is an equivalent.
All private game/Steam jobs are closed and display preferences are restored.

## Next evidence-backed work

1. Reconstruct production local-probe arrays and spatial blending. Start with
   [ENVIRONMENT_PROBES.md](ENVIRONMENT_PROBES.md) and the saved CPU reports.
   The fresh Hair event's active record 10 stores cube 18 and uniquely matches
   runtime draw-list probe `F896FB5315175B7C` in `9C292F5F8A79EEC2` /
   `tile_zz27_lgt.zone` under identity placement. It is catalogue index 3976,
   kind-5 region 184, child ordinal 122 of Megalopolis root 61; 29,359 saved
   screen tiles can select it. It has no installed baked-asset equivalent and
   requires scene rendering or that capture's explicit cube. Malinon Day
   texture `0x837545B07B72296F` instead matches captured cube 40, inactive in
   this frame. The older frame-7328 cube-14 association is separate evidence.
   `--resolve-scene-models` now maps runtime draw IDs to both indexed models
   and actor-bound models, preserving their full zone-local matrices and all
   duplicate candidates. Actor instance/reference/component parsing replaces
   the GP guesses and round-robin model assignment. The combined scan resolves
   12,465 of 14,526 IDs; 2,061 remain unresolved and 640 have multiple candidates.
   The zone-loading component is `PrefabZoneComponent` (`F39305D5`), absent
   from all 5,892 scanned zone bindings and the 1,950 defaults of 562 referenced
   actor assets. Region/checkpoint association and both executable selectors
   are now parsed. Kind-4 roots consume child primary lists through two runtime
   masks; kinds 3/5 consume immediate-parent then selected-region primary lists.
   Forge now recognizes the retail level type `587B60A6`; `i29.level` exposes
   9,176 verified zone references. Malinon lighting zone `81D3F7A27166B843`
   is catalogue index 251 / name index 183. Catalogue membership alone does
   not establish a world matrix or active zone set. See
   [ENVIRONMENT_PROBES.md](ENVIRONMENT_PROBES.md) for the exact consumers.
   The 1,216 regions and 860 checkpoints retain exact primary and paired
   replacement lists. The older declared Malinon/Megalopolis union has 503
   candidates. Executable selection keeps the kind-4 child input separate from
   the root list and still depends on the captured runtime mask state.
   The raw-buffer analyzer now reports spatial/specular/diffuse weights and,
   with explicit Hair vectors and gloss, the recovered parallax fetch plan.
   Its visibility helper also accepts the real light-grid scalar. Recover
   the original buffer/zone placement or use a fresh private-desktop capture,
   match resource contents, and run the new combined indirect replay before
   integrating those bindings into the viewport. The light-grid shader math,
   missing-cell interpolation, coordinate hash, integer fade packing, and
   fallback initialization are implemented and independently verified. The
   saved frame establishes the active probe placement and cube identity.
   Child-mask state, light-grid fades and rendering the draw-list cube still
   require runtime evidence. See the latest detailed handoff for the boundary.
2. Match the production deferred Hair/G-buffer composition, light-grid,
   shadows, GI, and screen-space occlusion using resource captures and shader
   disassembly rather than visual tuning.
3. Validate the recovered production TAA chain for stochastic shells. Exact
   seed-history, full-disocclusion, half-disocclusion and main-apply binaries,
   DXC assemblies, resource tables, and output-equivalent GLSL reconstructions
   are preserved offline. Static x64 analysis also recovers the 224-byte cbuffer
   builder's jittered filter, 0.04 nonopaque-response fallback, 0.0625 ordinary
   rejection floor, conditional 0.1 floor, stencil response, warmup and dither
   sequence. One bounded matched frame is still needed for its dynamic
   matrix/HDR/optional response override and flag fields, selected history indices, stencil and pre/post
   resources. The current 32-sample editor accumulator shares the recovered color
   encoding, exact current/history filters, motion selection, confidence bounds,
   native R11G11B10 history storage, independent default rejection and warmup,
   and final dither while those runtime values are absent.
   The full-resolution disocclusion builder's pixel scale, 1920-pixel camera
   normalization, history threshold, prior projection-to-UV transform and fuzz
   predicate are also statically recovered. Its two depth thresholds, view
   transforms, selected history, and scatter resource remain frame inputs.
   The adjacent half pass now has exact resource offsets, a verified 64-byte
   cbuffer vector `(1/w, 1/h, 0.5/w, 0.5/h)`, and an exact 8x8 dispatch. The
   reset path likewise has exact seed conditions and bindings for current
   depth-history and linear depth. Sixteen orchestration ranges totaling 4,719
   bytes are hash guarded. A whole-text direct-xref scan confirms that the two
   depth-threshold globals have only four load sites and no static initializer.
   Main apply now has exact guarded pointer rules for all seven inputs and its
   current/prior color-history records, plus native-versus-upsample shader
   selection and 8x8 dispatch. The frame index and resource contents still
   determine the concrete record pair.
   The ring rule itself is recovered: current index is stored at renderer
   `+0x1C28`, previous is `1-current`, record stride is `0x1F0`, and prior
   history must carry the `frame-1` tag.
   The common matrix helper is decoded as float64
   `currentView * inverse(previousTransform)` followed by float32 storage; all
   three conversion/inverse/multiply functions are hash guarded. The preview
   now also applies native f16 rounding to current-sample chroma, uses explicit
   LOD 0 history taps, and prevents undefined storage from entering frame zero
   or a reset history.
4. Re-run controlled, matched-camera comparisons for Ratchet, Rivet, and Sheep
   after each isolated change. Record shader/resource evidence, report data,
   and image deltas before accepting it.
5. Keep wind and water attached to authored grooming and shell data. Do not
   substitute a character-specific fake or reinterpret control alpha as fur
   length; the live draw proved extrusion uses control blue.

## Commit discipline on the second machine

Before publishing more work:

```powershell
git status --short
git diff --check
.\.venv\Scripts\python.exe -m pytest -q
```

Stage explicit source, tests, tools, and documentation paths. Do not stage
captures, game files, generated comparisons, virtual environments, or cache
files. Record the exact smoke command and JSON evidence in the detailed
handoff when behavior changes.

## Latest CPU-only local-light producer state

The fork now includes a strict parser for placed scene-light nodes and an exact
base-path `LightGpu` producer. Static retail ranges establish five main and five
auxiliary structured-buffer tiers at a 128-byte stride, the mapped upload
selector, the only exact direct packer call, and the field map from the internal
0x170-byte render-light record. All eight populated saved-frame light records
rebuild byte for byte through `build_light_gpu_base_record()`; see
`light-gpu-producer-validation.json` and `HAIR_SCENE_LIGHTING.md`.

The installed 177-zone scan finds 21 placed type-1 nodes, none matching the
captured eight-light group, so those capture lights are runtime-created dynamic
state. The direct cooked subtype-1 runtime transfer is now implemented too:
semantic scalar names, flag derivation, the native `0.01` attenuation-override
clamp, and the volumetric-fog chain from serialized `+0xB0` through persistent
`+0xF0` are hash-gated and checked across 22 retail records. The scalar derived
initializer, source-matrix local-basis normalization and resolved-transform
classifier are implemented as well. Constructor `0x140FDFA10` normalizes source
byte `+0x3B` into owner flag `+0xC6`; selector `0x140FE5C30` then prioritizes the
embedded `+0x60` override, already-world fallback, non-null `+0x10` holder and
null-holder fallback. The runtime-backed fallback at `0x146838510` has no
file-backed value. The placement loop applies the exact row-vector
`record_local * owner_transform` composition after dispatch. The 17-range report
`scene-light-runtime-transfer-validation.json` has SHA256
`b3caea75910e954aed6c4f3b569c7e642c22dc9ef84ce9d4a789377d4d73f3e0`; the
static source audit has SHA256
`53170f909032cbca6fc2af5e00c6dc69868a1b026dc7ec54aa47f0b8092f15a2`.
Negative-radius base packing is also complete; the current LightGpu producer
report SHA256 is
`29527e3f0f8b6c49b3b35598503b351222d4c769a55dffaa300ecf14e64eeb20`.
The subtype-1 auxiliary allocator and native primary-clip, gobo,
projected/point shadow-map and shadow-volume constructors are implemented too.
The subtype-3 and subtype-4 static packers include their native affine
inverses, subtype-specific field rewrites, allocation order and tier-full
behavior; subtype 4 covers both color-volume dimension modes. The CPU-only
report `light-gpu-auxiliary-allocation.json` hash-gates 15 retail ranges and has
SHA256
`a3676dd8e7c145761930c9663874965be0ab665b6c530d7e076b10c6bbfced58`.
Atlas handles now resolve exactly from an explicit manager table snapshot. The
manager candidate worker's exact distance/fade math, ordered gates and
16-entry batch membership are pinned together with its 0x18a0-byte query state.
An optional completion sequence reproduces the exact `lock xadd` selected-count
reservation and contiguous pointer-copy order, including empty chunks that
reserve no output slots. Secondary eligibility and flag mutation, the
512-pointer merge cap, exact
skip/defer/priority sequence, descending binary32 priority score, allocation
weights, final frame-packer handoff, common spatial submit/worker contract and
source-to-persistent shell stream association are pinned. Explicit snapshots
now drive the exact object-visibility, resource-readiness, type-resource,
auxiliary-volume and bit-21 distance predicates. The source-side view wrapper
also builds the exact oriented-box query for the manager's 16-bit depth
hierarchy. The optional secondary spatial query now builds its center from
manager translation plus the global forward distance times manager axis Z,
uses radius 48.0, and emits the exact component-major 0x100-byte 16-plane
descriptor. Four descriptor cases and three sphere cases match the bounded
retail oracle; `light-manager-secondary-query-descriptor.json` has SHA256
`1db9e9765713354fe7e0e56e155a578b58bdb4839abafbe73a486eb75865d5fe`
and its port report has SHA256
`6e41d1d5ec8f3741414c6ecb3c2fb863565eb32d0c73635e8b4cdae5b4eb6a6c`.
The common primary path copies six manager planes and derives ten edge planes
from eight points with the exact retail helper. Its oracle and port reports have
SHA256
`0d596d3c4b395c4e24cd615b2792906a636cec6f98daed4491b659eea19a8b47`
and
`028210af8958d9741dfc5106ac7b60b66c3a81338705d6dbb30d189b8f0ead21`.
The manager owner now covers the view-flag branch too: `+0x438` bit 1 selects
an alternate 16-plane OBB descriptor built from three axes, extents and
translation. Nine ordinary, nonorthogonal and degenerate cases match native
binary32 values and signed zeros. Its oracle and independent port reports have
SHA256
`bade3470b43bc63b992b4f89d1a2aa6924ba59a40312cb5e51025aee11c555e6`
and
`039244de6a160e7e5fd6cdd5d2de1b895ca4c96eb18d449db6bf08263229e775`;
the port output hash is
`0bc515edc8156b77c57ba84d93ea2cbbbe71afda578c50a14773617fb9c54da5`.
The optional primary override replaces planes 11 through 15 and zero to two
final tail slots. All four enable/tail-count cases match; its oracle and port
reports have SHA256
`19f6c490ffecdb37563f308700ad2906ef438fef7f13bc9cf1332bed009f209a`
and
`11a43e678d0a45901ae0b63355f7e283a83e9629597f81f56afee72aa4b1b1c6`.
Primary spatial refinement `0x1412B72A0` now transforms each source OBB,
tests support against all 16 primary planes and compacts retained pointers in
input order. Five cases covering 16 sources match retail exactly, including the
negative-zero boundary rule. Its oracle and independent port reports have SHA256
`cd913360327ab43362e7649acb4a379d672ec13928206b1db5937fdd53fd3a19`
and
`4b2e82fba60065366112b9b771b14bbedf100fee3b2206fd400a4bc065544040`;
the ordered output hash is
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
`97d534c56709b41fb8ee71f436065952d48ff9710f79a7870cfb66a1323cbef2`. The spatial cell front end is now reproduced through its consumed outputs.
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
The composite `light-manager-selection-validation.json` has SHA256
`9ad136cab3adc0b29bab4ab308d13ce91826910cbb85f18f8630e57f211dc608`.
The complete manager hierarchical-depth routine at `0x14118CE60` is now
snapshot-driven in production: eight-corner projection, conservative 16-bit
threshold, level-zero corner gate, span-selected mip rejection and masked
signed-int16 base scan all match ten bounded native cases. The native and port
reports have SHA256
`993a854927faefe5b32caeab38fcfe3e718b8fb70ded32a1e8fbf70172fb6f75` and
`2d3bc22fc10bf3b7a85fe5fd386f5aacb0373579666cec260527a155ea890714`;
the shared semantic output hash is
`0680e5a4f26a9e629e235b5583b8f1edb40a6f7702770cd5d41d96b889d1c663`.
Only the live frame's manager values and populated depth words remain external.
Priority ties now reproduce the retail generic sort exactly: insertion below
seven, middle pivot at seven, median-of-three above seven and
pseudomedian-of-nine above forty with Bentley-McIlroy partitioning. All 34
threshold and mixed-key cases through the 512-entry cap match
`light-manager-equal-score-sort.json` (SHA256
`52d2f7acced0d798248706155bce3708626e4a28c229589da6ad757ea64fa29f`,
case hash `3022e0729e94fe710df264bd2266ff7fd0b16c92a91db0a6e7eb341aea18c4bb`).
The expanded 84-range, fifteen-table report also pins the primary owner and
alternate builder, the sole resource-refresh caller, raw-CRC
version cache, all type dispatches, padded float3 allocation, two authored shell
tables and the exact 36/48/216/432-vertex box, procedural-cone and rounded
streams. The refresh now generates the resolved oriented-box planes and
per-type scalar Z planes in native order, clips/caps sequentially, copies the
persistent float3 stream, derives its AABB and midpoint/farthest-vertex sphere,
and applies the 98-percent source-bound shrink rule. Five clip-plane cases and
two packed-output cases match the CPU-only Unicorn oracle bit for bit. The
report SHA256 is
`9ad136cab3adc0b29bab4ab308d13ce91826910cbb85f18f8630e57f211dc608`.
All 593 CPU tests pass; the 201-test local-light module passes independently.
Continue with live spatial-database contents and scene membership, the live manager view values and populated hierarchical-depth words, captured resolved-resource inputs,
the frame-specific runtime scheduler completion sequence and captured placement/prepared-stream
values, including the concrete owner transform selected for the frame. Active-Hair output validation remains separate
work. No game or graphics workload is needed for the static continuation.
