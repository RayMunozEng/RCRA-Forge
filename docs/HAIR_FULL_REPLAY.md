# Captured Hair pass comparison

Status on 2026-09-03: the complete Hair lighting diagnostic matches **all 11,215
valid Hair pixels exactly in R11G11B10 storage** in the fresh Ratchet capture.
This includes shared material response, environment-frame preparation,
diffuse/transmission, lobes, contact and final resolve used by the preview.
Unquantized float RGB is not entirely exact: 4,016 whole RGB values match,
maximum channel error is 4.94719e-5 and RMS error is 5.25779e-7. This is a
captured lighting-pass result; complete viewport/final-frame parity remains open.

The subsequent [scene integration](HAIR_SCENE_LIGHTING.md) adds shared resident
grid/probe evaluation and the native key-shadow atlas. The full replay at
`hair-shared-key-atlas/report.json` retains the same 11,215 exact stored pixels
and native-float error metrics. Production scene-fragment measurements are
reported separately; they are not a complete-frame parity result.

The ordinary viewport now uses native BC6U cube sampling, seamless face filtering,
the shared DXIL Hair noise function, and `core/hair_lobes.glsl` for direct
distribution and Fresnel. `core/hair_surface.glsl` shares camera reconstruction
with the denoiser. Native material targets and separate vector/lighting passes
are integrated. Complete scene light/probe/grid bindings, scene shadows and
retail temporal reconstruction remain. Its preview temporal cycle is synthetic.
See [HAIR_MATERIAL_RESPONSE.md](HAIR_MATERIAL_RESPONSE.md) for the newest full
replay command, component limits and native color-storage integration.
Native contact evaluation now resolves the key contribution before denoise;
see [HAIR_CONTACT_REPLAY.md](HAIR_CONTACT_REPLAY.md).

The subsequent captured geometry/material comparison is documented in
[FUR_CAPTURE_PARITY.md](FUR_CAPTURE_PARITY.md). Those corrections are now shared
with the ordinary viewport and are separate from this lighting-pass comparison.

## Evidence and scope

Capture `riftapart-checkpoint_capture_5.rdc`, Hair event 17544, uses DXIL SHA256
`3f207392ea3179871c2fe5ec50f91ec127c102b6290d67553a81654359220bc0`.
The diagnostic executes all 524 workgroup tiles, or 16,768 lanes. The original
G-buffer classification accepts 11,215 of those lanes as Hair. It includes depth,
packed normal/specular and extra buffers, sRGB albedo, full light/probe/grid
buffers, native BC6 cubes, BRDF lookup, shadow/gobo atlases, and reflection history.
The captured shadow sampler uses linear filtering with **Less** comparison and
clamp addressing. Shader loops are bounded; no guard fired.

All evidence below is under the outer workspace's
`artifacts/rcra-fur-continuation/capture-tools/`. Original game shaders,
capture binaries, and texture/buffer exports remain there, outside the fork.

| Check | Result | Evidence |
| --- | --- | --- |
| Current full Hair replay with shared material/environment/key/resolve | **11,215/11,215 stored RGB exact**, zero stored error | `hair-shared-key-response/report.json` and `comparison.npz` |
| Previous shared lobes/contact replay | 11,215/11,215 stored RGB exact | `hair-dxil-shared-contact/report.json` |
| Native camera reconstruction | All 11,215 relative/world positions and view directions exactly match | `shared-hair-surface-decoded/report.json` |
| Shared HairDenoise after surface extraction | All 11,215 stored/float RGB values and four accumulation sums exact | `hair-denoise-replay-shared-surface/report.json` |
| Repeated original DXIL replay | Byte-exact full output | `d3d-full-hair-dxbc-17544/report.json` |
| Mechanical DXBC-to-GLSL vs native D3D12 DXBC | 11,211/11,215 exact; four one-step differences | `d3d-full-hair-dxbc-17544/comparison.json` |
| Native retail DXBC vs retail DXIL | 82 differing pixels; maximum 0.1875 | same comparison |
| Shared DXIL noise in full GLSL replay vs captured DXIL | 11,209/11,215 exact; max stored error 0.0078125; RMS 0.0000461074 | `full-hair-replay-all-17544-shared-noise/report.json` |
| Captured output-format conversion | 23 independent D3D12 stores match round-toward-zero; all 16 initial replay samples match captured RGB | `d3d-hair-output-format-17544/report.json` |
| Native full-precision DXIL output | All 11,215 decoded float outputs reproduce captured stored RGB; GL/native RMS 3.14433e-6, max 0.000194252 | `d3d-hair-float-probe-17544/comparison.json` |
| Normal viewport GPU smoke | Native BC6U six-face/six-mip probe ready, fur shader compiled, LOD0 head rendered | `viewport-bc6-noise.json` / `.png` |
| Fork tests after shared-kernel integration | 250 passed | `pytest-shared-hair-kernels` run |
| Key-only preview contact resolve | Environment and non-fur pixels preserved; contact toggle verified | `preview-contact-behavior/report.json` |

The retained baseline reports make the compiler difference visible. Do not
attribute the native DXBC/DXIL discrepancy to OpenGL: both original shader builds
were run on the same captured D3D12 resources. The substantial mismatch disappears
when the shader's two noise seeds follow DXIL's **add, then scale** data flow.
The shared `core/hair_lighting_noise.glsl` produces the same full-pass output as
the direct instruction-order correction.

The baseline's six output boundaries are resolved. Native intermediate probes
identified changes to camera-relative reconstruction, shadow-depth subtraction,
frame cross-product fusion, lobe multiplication order, and normalization. Explicit
FMA precision also changes upstream vector decoding, so a separate GPU pass uses
the shared `fur_gbuffer.glsl` to decode the original captured packed vectors.
It matches every native normal and strand component; native float oracle values
are never supplied as lighting inputs.

The final boundary was `(738,654)`. Native secondary-lobe normalization is
0.9999999403953552; the earlier fused square/subtraction produced
1.0000001192092896. Native computes the rounded square first, then reuses it in
`square / max(1 - saturate(1 - square), 1e-6)`. Preserving those intermediate
roundings removes the last stored-color difference. The shared lobe module keeps
that rule, the native constant bits, distribution order and Fresnel arithmetic.
The preview also preserves the signed normal/light dot until diffuse wrap
saturation. No pixel-specific correction, color bias or relaxed comparison is used.

Validated native intermediate evidence is in `d3d-hair-geometry-17544/`,
`d3d-hair-resolve-17544/`, `d3d-hair-stages-17544/`, `d3d-hair-shadow-17544/`,
`d3d-hair-key-17544/`, `d3d-hair-lobes-17544/`, `d3d-hair-basis-17544/`, and
`d3d-hair-distribution-17544/`. Each probe validates its assembled container,
requires an unchanged output-exact control and checks decoded bit ranges.

The full-precision probe assembles the original LLVM IR through the installed
SDK's `IDxcAssembler`, validates the containers with `IDxcValidator`, and changes
only the final output store to encode float bits in seven five-bit chunks.
Unmodified reassembly is byte-exact at the output, and the decoded instrumented
floats reproduce all original stored pixels. An initial unsigned assembly was
ineffective and is retained as `initial-unsigned-report.json`; it is **not** valid
measurement evidence. The replay script now rejects ineffective substitutions.

## Reproduction on the capture machine

Use the fork's Python environment with Qt/OpenGL dependencies. From the outer
workspace, run:

```powershell
external/RCRA-Forge/.venv/Scripts/python.exe artifacts/rcra-fur-continuation/capture-tools/replay_full_hair.py --all-hair --shared-noise --precise-mad --dxil-history --dxil-view --resolve-details --dxil-shadow-depth --vector-pass --dxil-lobes --dxil-distribution --dxil-basis --reverse-frame-cross --dxil-normalization --shared-lobes --shared-contact --raw-wgl --name hair-dxil-shared-contact
```

The script hashes each exported resource before uploading it and writes full
float and stored-color comparisons to `comparison.npz`. The exact DXBC source
disassembly is private evidence in `probe-analysis/`. DXIL operation order was
checked in the installed SDK's `dxc -dumpbin` output, `hair-event-17544/hair.llvm.txt`.
Do not substitute rounded decimal constants from RenderDoc's readable listing.
Use `tools/private_desktop.py` around GPU commands on the capture machine. The
minimal hidden WGL context avoids a measured Qt offscreen-context startup stall;
it never activates its window or switches the user's desktop.

The `verify_d3d_*` scripts require RenderDoc's embedded Python. Their shader
substitutions affect replay memory only and are removed in `finally` blocks.
All private replay and viewport jobs used for these checks have exited. The
original capture files and game installation were unchanged by these comparisons.

## Next work

1. The ordinary viewport now stores native material targets and separately
   decodes vectors and evaluates lighting; see **FUR_DEFERRED_PREVIEW.md**.
   Complete native raster orientation and replace the remaining isolated preview
   lighting expressions with the complete native path.
2. Supply native packed material flags, scene light/probe/grid resources and scene
   shadows. Opaque/fur depth now uses consistent linear units and the new
   key-contact resolve is in place before denoise; the ordinary
   preview still uses its isolated light and environment inputs.
3. Reproduce temporal history with matched camera, pose and scene state. Captured
   material/raster, lighting and denoise pass checks do not establish final-frame
   parity, especially across other GPUs or captures.
