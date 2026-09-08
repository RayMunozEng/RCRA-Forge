# Hair indirect-lighting replay

`tools/replay_hair_indirect.py` runs the recovered light-grid and environment
probe kernels together in an offscreen OpenGL 4.3 compute context. It uses
explicit query points, global constants, GPU records, lookup words, and texture
contents. It does not choose a zone transform, infer residency, identify a
captured cube from a cooked asset name, or substitute for the full Hair frame.

The kernels come from the matching retail Hair shader,
`5ff73b6b2aca9640cf18cd78b88ba3c0`. The result is indirect illumination before
the BRDF, direct lighting, shadows, G-buffer composition, and temporal history.
The regular viewport still uses its existing environment path.

## Run

```powershell
.\.venv\Scripts\python.exe tools/replay_hair_indirect.py `
  --input 'path/to/captured-hair-inputs.npz' `
  --output 'path/to/replayed-indirect.npz' `
  --report 'path/to/replayed-indirect.json'
```

The input is an NPZ written with `numpy.savez` or `numpy.savez_compressed`.
Object arrays/pickles are not accepted. Buffer arrays preserve the raw little
endian resource contents. Texture arrays contain decoded **linear** RGB/RGBA
float16 or float32 texels, without exposure, display conversion, flipping,
normalization, or generated replacement mips.

For captured BC6H unsigned cubes, prefer the native block form below. Decoding
BC6H to RGB32F changes the hardware filtering/rounding path; native blocks preserve
the source format as well as the authored texels and mip chain. Each cube resource
must use one representation consistently; decoded and compressed arrays for the
same resource cannot be mixed.

| Array | Shape and dtype | Meaning |
| --- | --- | --- |
| `viewport_cbuffer` | `(480,) uint8` | Captured `GlobalViewportCBuffer` bytes |
| `world_cbuffer` | `(896,) uint8` | Captured `GlobalWorldCBuffer` bytes |
| `probe_records` | `(P,128) uint8` | `g_EnvProbeEnvs`, retaining GPU record order |
| `lookup_words` | `(N,W) uint32` | Actual t34 words for each query pixel; W equals world buffer u32 at byte 748 |
| `grid_lookup` | `(262144,) uint32` | Complete `g_LightGridLookup` ring table, t50 |
| `grid_data` | `(R,4) uint32` | Complete resident `g_LightGridData` records, t51 |
| `world_points` | `(N,3) float` | Hair world position, r10.xyz |
| `shading_normals` | `(N,3) float` | Decoded surface normal, r6.xyz; grid sampling input |
| `environment_normals` | `(N,3) float` | Reconstructed environment normal, r21.yzw before the probe loop; local probe diffuse input |
| `reflection_directions` | `(N,3) float` | Environment reflection, r23.xyz before the grid/probe branches |
| `average_gloss` | `(N,) float` | Mean of primary and secondary Hair gloss |
| `default_mip0` ... `default_mip5` | `(6,H,H,3) float` | Actual default cube's six mip levels |
| `local_mip0` ... `local_mip5` | `(C,6,H,H,3) float` | Actual local cube array, retaining captured cube-slot indices |
| `distant_height` | `(H,W) float` | t62 red channel, required if world float at byte 672 is nonzero |
| `distant_samples` | `(D,H,W,4) float` | t63 RGBA volume, required under the same condition |

Instead of `default_mip0` ... `default_mip5`, supply `default_bc6_mip0` ...
`default_bc6_mip5`, each `(6,B,B,16) uint8`. Instead of `local_mip0` ...
`local_mip5`, supply `local_bc6_mip0` ... `local_bc6_mip5`, each
`(C,6,B,B,16) uint8`. The last dimension is one unmodified 16-byte BC6U block;
blocks use their captured row order. Base face size is four times mip 0's block
width, and `B = max(1, ceil(face_size_at_this_mip / 4))`. Small 1x1 and 2x2 mips
still occupy a complete block. Signed BC6H is not accepted by this representation.

Cube faces are `+X,-X,+Y,-Y,+Z,-Z` in the existing D3D face convention. Each
successive mip halves face dimensions. The replay uses RGB32F for decoded arrays
and native BC6U for compressed arrays, with linear mip filtering and seamless
cube sampling in both cases.
The GPU callback tests exercise cube slots, face ordering, authored mips, and
the separate grid/probe normal inputs. They do not measure hardware sampling
differences against a captured D3D frame at cube seams.

The replay reads camera position at viewport byte 48, bleed reduction at world
byte 704, ambient fill/intensity at 720/732, and distant GI parameters at
672/688/692/696. Environment probe intensity is the same world byte 732 used
for the light-grid diffuse result. The grid reflection scalar remains unscaled.

Output arrays are `specular`, `diffuse`, `visibility`, `coarse_luminance`,
`grid_diffuse`, `grid_reflection`, `default_coverage`, `diffuse_coverage`, and
`grid_fallback_weight`. Reports retain the input SHA256 and GPU renderer. A
successful replay means the explicit resources were processed; it does not
by itself establish capture parity.

## Verification on the second computer

Evidence lives outside the tracked fork in
`artifacts/rcra-fur-continuation/probe-analysis/`:

- `verify_light_grid_gpu.py` mechanically translates the original 559 DXBC
  instructions with exact hexadecimal immediate bits. Both the compact CPU
  implementation and reusable GLSL pass 4,096 comparisons, including signed
  brick boundaries, no-fallback samples, and distant GI. Largest absolute
  errors: CPU `4.7684e-6`, GPU `2.2650e-6`.
- `verify_probe_lighting_gpu.py` checks the probe kernel against the independent
  CPU sampling plan with 40 records, multiple lookup words, rotated boxes and
  cylinders. All 4,096 queries pass; maximum absolute error `8.8215e-6`.
- `verify_indirect_resource_replay.py` checks the complete upload/replay path
  with 192 synthetic queries, two distinct cubes, six distinct faces and mips,
  lookup bit 33, distinct grid/environment normals, and actual GI textures.
  Maximum absolute error `8.9407e-8`. The ordinary replay CLI also processes
  this fixture successfully.

These fixtures are controlled numerical checks, not captured retail imagery.
To compare frame 7328, supply that frame's own resources and query state.

## Cooked light-grid data

`core/light_grid_assets.py` parses the `FA8D90B3` asset and either its separate
stream span or compressed inline data. The inline path validates compressed
lengths, back references, DAT1 ranges and final stream offsets; omit `--stream`
for that storage mode. `tools/analyze_light_grid_asset.py` validates every indexed brick and can
export a selected brick before missing-cell interpolation:

```powershell
.\.venv\Scripts\python.exe tools/analyze_light_grid_asset.py `
  --asset 'path/to/97BE230CA4381B39.zonelightbin' `
  --stream 'path/to/97BE230CA4381B39.light-grid-stream.bin' `
  --output 'path/to/light-grid-report.json' `
  --brick-index 0 --brick-output 'path/to/brick0.npz'
```

The cooked stream's cell kinds 0 and 1 are missing-cell sentinels. They must
not be treated as black lighting or silently passed off as a finished resident
GPU grid. Optional retail interpolation is now available for a selected brick:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-evidence.txt
# Add to the asset decoder command above:
# --interpolate-with-executable 'path/to/RiftApart.exe'
```

`core/retail_light_grid.py` copies the verified decoder instructions into an
isolated Unicorn CPU emulator and uses the Windows CRT for expf/logf. It never
starts or attaches to the game. It accepts only executable SHA256
`51299faca61866cf10ea9035a15b8f22600a56557dd5ffc1aad390d5a54e6d82`, bounds guest
memory/execution, compares the independent first-stage decoder, and verifies
that interpolation preserves all authored samples. Eight selected bricks pass,
including zero-authored and densely authored bricks. Evidence is
`light-grid-retail-vm-validation.json`.

The output then includes interpolated `records`, `fallback_scale` and
`source_missing_indices`. Some filled records legitimately retain the sentinel
plane bits while acquiring radiance; those bits alone do not mean filling
failed. The runtime interpolation gate and CPU floating-point state are not
captured: the tool explicitly runs interpolation with MXCSR 0x1F80. Brick
selection, residency, lighting conditions, and native captured-buffer comparison
remain required for scene parity.

## Explicit grid reconstruction

The runtime path copies the asset's brick positions directly into its work
list. `core/light_grid_resources.py` reproduces its position hashing and fade
conversion, and constructs complete t50/t51 resources from a supplied brick
selection. Slot numbers are compacted for replay. Colliding ring addresses
are rejected; the builder does not guess runtime priorities.

```powershell
.\.venv\Scripts\python.exe tools/reconstruct_light_grid.py `
  --asset 'path/to/83971B86890068A0.zonelightbin' `
  --executable 'path/to/RiftApart.exe' --fade 255 `
  --output 'path/to/grid-reconstructed.npz' `
  --report 'path/to/grid-reconstructed.json'
```

Add `--stream` for a streamed asset. This interpolates every selected asset
brick in isolation, checks the independent first-stage decoder and authored
record preservation, and reuses byte-identical encoded blocks. It also runs
the retail fallback initializer and packer. The NPZ contains `grid_lookup` and
`grid_data` for the indirect replay bundle, plus brick positions, explicit
fade bytes, lookup addresses, and the fallback record/slot. Other replay inputs
must still be supplied from the same controlled reconstruction or captured frame.

The position hash and packed fade have passed **4,096 position queries and
1,792 update records** against isolated original x86 instructions, including
all 256 fade values and removal updates. The default packed record is
`843F843F 843F843F 843F843F 83F81FC0`. See
`light-grid-lookup-vm-validation.json` for the verified executable hash and
function addresses. This verifies runtime operations, not capture residency.

`should_replace_light_grid_brick` also recovers the valid-entry collision
decision at `1410A2160`. It retains current entries within 512 units and admits
candidates within 409.6 units (Chebyshev distance); when both radius tests agree,
the higher priority wins and ties retain the current entry. All **331** isolated
retail comparisons pass, including every priority pair, boundary cases, missing
camera state, output metadata and old-entry flag changes. Empty/stale entries,
the current state table and complete streaming transitions are separate inputs.

The complete Sargasso tile_l25 overcast asset was reconstructed at explicit
fade 255: **354 bricks**, 350 distinct encoded blocks, **1,282,753 filled
cells**, and **1,454,080 GPU records** including the fallback brick. Every
distinct block passed first-stage equality and authored-record preservation.
The reconstructed data SHA256 is
`1cab416f92018a19ee410eae3a5550e652f2c7a5c5490532d5cc1425dcfa8164`.

With these installed records and controlled constants/samplers, **4,096** GPU
queries pass against the original 559-instruction shader slice; maximum
absolute difference is **4.7684e-7**. The complete indirect resource upload also
passes **192** queries, with maximum output difference **1.1921e-7**. Evidence:
`sargasso-l25-grid-reconstructed.json/.npz`,
`sargasso-l25-light-grid-gpu-validation.json`, and
`sargasso-l25-indirect-validation.json`. These checks do not identify the
captured frame's resource bindings or establish visual parity.

## Fresh captured-resource check — 2026-09-03

A fresh Ratchet gameplay capture provides Hair event 17544 with the same DXIL
hash. Native BC6U replay passes 16 actual Hair queries, maximum absolute error
1.1921e-7, against traced arithmetic with all 64 cube fetches independently
measured on D3D12. Diffuse, grid reflection and coarse luminance match exactly.
The captured queries all use full grid fallback and local specular-only probes;
this does not replace the controlled resident-grid/GI/overlapping-probe fixtures.

Evidence is in `artifacts/rcra-fur-continuation/capture-tools/captured-indirect-16/`.
The input NPZ SHA-256 is
`eaee031752d2243417e882cf665ab438fce98b379ddeefdebbfac1d550c2ee28`.
The offline RenderDoc debugger returned different default-cube colors from the
D3D12 GPU, while local-cube colors matched. The comparison explicitly replaces
those texture results with measured hardware samples; the original trace and
initial mismatch are preserved. See `PRIVATE_CAPTURE.md` for provenance and
limitations. Ordinary viewport integration remains separate.
