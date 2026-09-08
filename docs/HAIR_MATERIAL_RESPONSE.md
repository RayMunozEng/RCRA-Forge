# Shared Hair material response and color storage

Status: 2026-09-03. The ordinary viewport now uses recovered material response,
environment-frame preparation, diffuse/transmission response and final material
resolve. The complete captured Hair replay using these helpers retains
**11,215/11,215 exact stored RGB values**. Full scene/frame parity remains open.

## Production changes

- `core/hair_response.glsl` decodes primary/secondary F0, distance-adjusted gloss,
  both anisotropic width pairs, material occlusion/emissive and transmission.
  It shares wrapped-light response, transmission and final diffuse/specular
  blending. The primary-width calculation preserves DXIL's folded coefficients.
- `core/hair_environment_frame.glsl` uses both widths from the primary lobe for
  the strand/side perturbations and axis selection. The old preview mixed widths
  from different lobes. Cross-product orientation/order is shared with
  `hair_frame.glsl`.
- `core/hair_preview_lighting.glsl` calls those helpers from both deferred and
  forward rendering. Packed material alpha now affects diffuse and specular
  occlusion. The emissive branch follows the packed flag. Missing specular
  textures are represented by the material writer's packed values.
- Transmission clamps the normal/light dot before multiplying the normal/view
  dot. The previous expression produced positive attenuation when both were
  negative. The final no-history resolve uses black reflection history and unit
  history visibility, matching the native fallback inputs.
- `core/hair_color_store.glsl` reproduces measured R11G11B10 round-toward-zero
  conversion at the contact/lighting and denoise stores. Positive finite
  overflow clamps to 65024/65024/64512, negative values clamp to zero, subnormal
  spacing differs between RG and B, and positive infinity/NaN remain special.
  The mixed scene targets remain RGBA16F: native R11G11B10 values are exactly
  representable there, while non-fur color and alpha can be preserved.

Color conversion occurs after lighting accumulation and after denoising, not
inside the shared mathematical kernels. The forward fallback uses its framebuffer
precision and does not claim the deferred storage behavior.

## Captured evidence

Private scripts/reports are in the outer workspace's
`artifacts/rcra-fur-continuation/capture-tools/`; original resources stay outside
the fork. The native Hair event is 17544 in `riftapart-checkpoint_capture_5.rdc`,
DXIL SHA256
`3f207392ea3179871c2fe5ec50f91ec127c102b6290d67553a81654359220bc0`.

`d3d-hair-response-17544` contains 24 new native intermediate fields from 49
validated shader variants. The unmodified control remains output-exact; all
instrumented replacements are effective, decoded ranges are valid, and the
native replay reports no debug messages.

| Check | Result | Evidence directory |
| --- | --- | --- |
| Primary F0, adjusted/primary/secondary gloss, four width values, transmission, material occlusion/emissive and average gloss | Every measured field exact at all 11,215 pixels | `shared-hair-response` |
| Three final resolve weights | All 11,215 values exact for each field | same |
| Secondary F0 | Max component error 1.1920929e-7 | same |
| Environment blend | 10,802 exact; max error 1.1920929e-7 | same |
| Environment normal / reflection | Max component errors 6.556511e-7 / 8.34465e-7 | same |
| Final resolve with native boundary inputs | 9,641 whole RGB values exact; max error 2.384185791e-7, RMS 4.317e-9 | same |
| Complete Hair replay with shared material, environment, key response and resolve | **11,215 stored RGB exact**; 4,016 float RGB exact; max float error 4.947185516357422e-5, RMS 5.257787165646732e-7 | `hair-shared-key-response` |
| GPU store helper vs native format edge cases | All 35 RGB stores exact, including subnormal/negative/overflow cases and infinity/NaN classes | `shared-hair-color-store` and `d3d-hair-output-format-extended` |
| GPU store helper vs captured lighting / denoise | All 11,215 RGB outputs exact in each set; every result also survives FP16 round-trip | `shared-hair-color-store` |

The component test intentionally supplies native values at each helper boundary
to isolate its arithmetic. It is not an end-to-end lighting test. In contrast,
the complete replay supplies original packed buffers, textures and constants;
it does **not** supply native float oracle values as shader inputs. Its generated
shader SHA256 is
`e60161e52c21d1e9893ffd0f519abb6db68df938f8dfce1b07ffb84f3dc7b76d`.
The capture's primary F0 is constant and its material uses the occlusion branch;
these measurements are not coverage of every possible material code/flag.

The production `FUR_LIGHTING_FRAG` also passes an independent controlled behavior
check, `preview-material-response`: 64 alpha states across 2,048 occlusion and
2,048 emissive pixels. Direct diffuse scaling is exact; emissive output differs
from the CPU formula by at most 9.5367431640625e-7. This validates integration and
flag routing, not an additional native emissive capture.

## Reproduction

Run the following through `tools/private_desktop.py` with the fork's Python on
the capture machine. The scripts below are in the private evidence directory.

```text
replay_shared_hair_response.py --all-hair --shared-noise --precise-mad --dxil-history --dxil-view --resolve-details --dxil-shadow-depth --vector-pass --dxil-lobes --dxil-distribution --dxil-basis --reverse-frame-cross --dxil-normalization --shared-lobes --shared-contact --raw-wgl --name hair-shared-key-response --material-response --environment-frame --final-resolve --key-response
probe_shared_hair_response.py
verify_shared_hair_color_store.py
verify_preview_material_response.py
```

The wrapper's four extra switches are consumed before the baseline parser, so
the baseline report's `options` object omits them. Keep the command and generated
shader hash when citing this composition. Native intermediate/format probe
scripts use RenderDoc's Python; replacements affect replay memory and are removed
in `finally` blocks.

## Ordinary viewport checks and remaining work

`viewport-native-store-dry` and `viewport-native-store-wet` check both native
color grids, exact material/decoded masks, finite color, shared opaque depth,
and preservation of every non-fur pixel through lighting **and** denoise.
Dry: 80,690 Hair / 919,310 non-Hair pixels. Wet: 79,334 / 920,666. Both images
are 1000x1000 physical pixels and were visually inspected. The non-HDR
`viewport-native-response-fallback` also renders correctly; its single stochastic
sample remains visibly grainy without temporal accumulation.

The controlled contact/denoise/bloom/depth checks remain passing in
`preview-contact-behavior`. The fork suite passes **250 tests**, and
`git diff --check` is clean. Private jobs exited with Default still the input
desktop; no game files or original captures were changed.

Next: connect complete scene light/probe/grid/shadow state, then matched native
raster/motion/history and final reconstruction. The asset preview still supplies
a unit key and an isolated default environment. Its separate direct/indirect
resolves are algebraically compatible with scalar key visibility but do not
preserve the native combined accumulation order. Native reflection-history
sampling and scene-dependent lighting masks remain absent. Small float errors
in frame/resolve helpers remain even though the tested full replay's stored
colors are exact. No complete composed-frame parity claim follows from these
isolated pass results.
