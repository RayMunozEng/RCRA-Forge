# Ratchet ModelStrand continuation handoff — 2026-09-09

Repository: `https://github.com/RayMunozEng/RCRA-Forge`

Branch: `main`

Source of truth: the commit containing this document

Status: active parity work. The recovered shell and ModelStrand paths are
substantially closer to the retail renderer, but full animated-frame retail
parity has **not** been demonstrated. Continue from the evidence below; do not
replace the fur path with a generic hair approximation or tune by eye.

## Non-negotiable operating constraints

- Run the game, RenderDoc, Unreal, and Forge GPU captures through
  `tools/private_desktop.py`. The job report must show that the user's input
  desktop remained `Default`.
- Do not activate or automate the user's foreground desktop. Earlier visible
  runs interfered with mouse input.
- Use the receiving computer's installed retail game and produce fresh local
  captures when an ignored fixture is absent.
- Treat screenshots as supporting evidence only. Acceptance requires shader,
  buffer, topology, report, and/or deterministic replay evidence.
- Sheep is not a Lombax ModelStrand preset. Its recovered material is the
  separate shell-wool path with authored length `0.09`, density `3`, and offset
  `0`. Preserve that distinction.

## Current renderer result

The production Forge viewport now combines:

1. The already recovered shell-fur material and exact five-target
   material/decode/lighting/contact/denoise path.
2. Capture-derived Ratchet ModelStrand accent groups for the tail, sparse head
   hairs, and ears.
3. Recovered per-group child counts, tessellation, thickness/clump curves,
   reflectance, textures, root frames, and authored guide curves.
4. Retail triangle-strip budgets with explicit OpenGL primitive restarts at
   child-ribbon boundaries.
5. The exact captured wind-only displacement at the recorded retail wind state,
   deliberately excluding the captured gameplay skeletal pose.
6. The same wet material response and native Hair deferred targets used by the
   shell pass.

The latest inspected local dry result is
`unreal/fur/recovered/forge-modelstrand-strip.png`; the matching wet result is
`unreal/fur/recovered/forge-modelstrand-wet.png`. These generated files are
ignored and are not part of the Git transfer.

## Recovered retail facts

All values below were measured from the saved retail RenderDoc capture rather
than inferred from appearance.

| Group | Authored guides | Visible guides | Children | Tessellation | Retail draw vertices |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tail | 633 | 463 | 35 | 11 | 713,020 |
| Sparse head | 2,109 | 119 | 11 | 11 | 57,596 |
| Ears | 2,781 | 2,300 queue entries / 2,277 unique | 2 | 8 | 147,200 |

The draws are non-indexed `TriangleStrip` in retail. Forge preserves the retail
vertex budgets and live geometry counts while adding fixed-index primitive
restart sentinels because native zero-W clip sentinels do not have portable
OpenGL behavior.

The measured maximum wind-only control-vertex offsets at the captured state are:

- tail: `0.702938 cm`
- sparse head: `1.168054 cm`
- ears: `1.399077 cm`

The tail CPU replay of `CS_ModelStrandSimulateWind` matches `98.153%` of packed
position components exactly, has a maximum residual of two packed units, and
matches packed normals exactly. The acceptance report is generated as
`unreal/fur/recovered/native-strand-pipeline/tail-wind-cpu-replay.json`.

## Code to read first

- `core/model_strands.py`: profile constants, fixture loading, retail guide
  sampling, captured wind-only delta, ribbon vertex/index construction.
- `ui/viewport.py`: ModelStrand vertex/material programs,
  `GpuModelStrandGroup`, deferred-target integration, wetness, and draw order.
- `tools/smoke_fur_viewport.py`: isolated GPU capture and deferred-target
  verification.
- `unreal/fur/replay_native_tail_wind.py`: closest instruction-level CPU
  reference for persistent wind.
- `unreal/fur/decode_native_strand_guides.py` and
  `unreal/fur/decode_native_strand_bindings.py`: regeneration of ignored guide
  and skeletal-binding fixtures.
- `unreal/fur/extract_native_strand_topology.py`: isolated topology evidence.
- `unreal/plugins/FurAuthoring/Content/Python/create_strand_groom.py`: exact
  recovered group profiles used by the Unreal validation path.
- `unreal/plugins/FurAuthoring/Source/FurAuthoring/Private/StrandGroomActor.cpp`:
  readable persistent simulation and ribbon-building port.
- `unreal/plugins/FurAuthoring/Source/FurAuthoring/Private/PoseableGroomBindingActor.cpp`:
  skeletal binding validation path.

The accompanying parser/export changes preserve Ratchet's tangent/decode data
and decode both RCRA and legacy skin-batch weights. They are required for the
binding workflow; see `core/mesh.py`, `exporters/gltf_exporter.py`,
`exporters/fbx_exporter.py`, and `tests/test_mesh_skin_batches.py`.

## Ignored evidence that must be regenerated or copied locally

`.gitignore` intentionally excludes `unreal/fur/recovered/`. On the originating
computer the main capture is:

`C:\Users\rmuno\Cloud-Drive\Github\gem-shader\artifacts\rcra-fur-continuation\capture-tools\riftapart-checkpoint_capture_5.rdc`

The retail install used there is:

`C:\Program Files (x86)\Steam\steamapps\common\Ratchet & Clank - Rift Apart`

The receiving computer may use its own install and a fresh capture. Do not
commit the RDC, extracted game buffers, decoded guide JSON, retail textures, or
comparison PNGs.

The ignored fixture directory currently contains the following inputs expected
by `core/model_strands.py`:

- `ratchet-tail-guides-bind-visible.json`
- `ratchet-head-sparse-guides-bind-visible.json`
- `ratchet-ear-guides-bind-visible.json`
- `tail-DiffuseTexture.png`
- `tail-StrandThicknessTexture.png`
- `DiffuseTexture.png`
- `StrandThicknessTexture.png`
- the pre/post skinning and wind buffers named in
  `core/model_strands.py::CAPTURED_WIND_BUFFERS`

It also contains these decoded binding reports:

- `ratchet-tail-skeletal-bindings.json`
- `ratchet-head-sparse-skeletal-bindings.json`
- `ratchet-ears-skeletal-bindings.json`

Each binding maps a retail source strand to an exact body subset, source
triangle, barycentric weights, and named-bone influences derived from the
exported `JOINTS_0`/`WEIGHTS_0` streams.

## Exact captured Forge smoke command

On the originating machine, the current full-character validation uses:

```powershell
.\.venv\Scripts\python.exe tools\private_desktop.py `
  --report <private-job-report.json> `
  --seconds 90 `
  --cwd C:\Users\rmuno\Documents\Codex\2026-08-31\i\RCRA-Forge `
  --ui-restrictions none `
  --max-job-memory-gib 8 `
  --priority below-normal `
  -- `
  C:\Users\rmuno\Documents\Codex\2026-08-31\i\RCRA-Forge\.venv\Scripts\python.exe `
  tools\smoke_fur_viewport.py `
  --game-root "C:\Program Files (x86)\Steam\steamapps\common\Ratchet & Clank - Rift Apart" `
  --hashes hashes.txt `
  --model 0xADE5909F821E9DDE `
  --lod 0 `
  --samples 1 `
  --converge-samples 32 `
  --verify-deferred-targets `
  --width 768 `
  --height 768 `
  --yaw 120 `
  --pitch -5 `
  --distance-scale 0.72 `
  --fur-wetness 0 `
  --fur-wind-strength 0.03709043934941292 `
  --fur-wind-vector -0.9974102378 0 0.0719231740 `
  --fur-wind-object-phase 0.1326904296875 `
  --fur-wind-time 981.7157592773438 `
  --output <forge-modelstrand-strip.png> `
  --report <forge-modelstrand-strip.json>
```

Replace absolute paths with receiving-machine paths. The report must show the
input desktop remained `Default`, a valid GL context, the recovered shell and
capture-derived ModelStrand renderer, all three group summaries, and successful
deferred-target verification.

## Latest verified behavior

- Topology-corrected 768 x 768 full Ratchet render passed
  `--verify-deferred-targets` and completed at about `44.67 ms` per captured
  frame on the originating GPU.
- Exact captured-wind dry render produced 47,780 Hair pixels before the final
  topology correction; the matched wet render produced 45,130, a `-5.546%`
  coverage change.
- Dry/wet comparison changed 43,715 pixels across 160,978 foreground pixels;
  foreground mean absolute RGB changes were `[4.09, 2.75, 1.07]`, with channel
  p95 of `14`.
- Parser tests passed `14/14`; the only message was a pytest cache-permission
  warning.
- Python compilation and `git diff --check` passed apart from Windows
  LF-to-CRLF notices.

These checks demonstrate a functioning recovered path, not complete visual
parity.

## Remaining work, in dependency order

### 1. Connect skeletal binding

The viewport already accepts deformed mesh streams through
`Viewport3D.set_deformed_pose`, but ModelStrand roots/control vertices are still
rendered in their captured bind placement. Load the decoded binding records,
map named bones to the current model skeleton, apply current and previous bone
transforms to guide roots/control vertices, and update root normal/frame-Y.
Binding must run before wind. Validate with controlled poses and exact root
attachment; do not use a guessed gameplay pose.

### 2. Make wind persistent at arbitrary time

The viewport currently applies the exact captured wind-only delta only when
strength and time match the saved capture. Port the validated float32 solver
from `unreal/fur/replay_native_tail_wind.py` to persistent per-group state:

- current skinned base positions;
- previous simulated positions;
- recovered 64-vector cubic random table;
- exact noise, phase, force, drag, stiffness, and length-constraint chain;
- current/previous ribbon positions for motion output.

Avoid rebuilding roughly 918k vertices with nested Python loops every frame.
Precompute guide/child/sample mappings, vectorize the sampled curve expansion,
and update the existing VBO with `glBufferSubData`. Preserve instruction-derived
constants; performance throttling may change update cadence, not the algorithm.

### 3. Close common-frame visual validation

Capture a bounded retail frame and reproduce the same character pose, camera,
weather, water state, and lighting in Forge. Compare silhouette, coverage,
material targets, motion/history, and composed output. Full retail parity can
only be claimed after this common-frame end-to-end comparison.

## Visual assessment of the current checkpoint

The current result visibly restores shell fur, ear-edge fringe, sparse head
accents, and a discrete tail guard-hair tuft. The tail remains rough and dark in
its center, and the static T-pose does not validate groom attachment during
animation. Those are active gaps, not reasons to remove or replace the recovered
technique.
