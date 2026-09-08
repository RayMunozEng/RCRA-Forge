# Hair contact shadow and preview pass order

Status: 2026-09-03. The ordinary preview now evaluates contact visibility on
the direct-light contribution **before HairDenoise and temporal history**.
Environment light is preserved. `core/hair_contact_shadow.glsl` is shared with
the complete captured Hair replay, which still matches all **11,215 stored RGB
pixels exactly** after the replacement.

The optional [native scene atlas](HAIR_SCENE_LIGHTING.md) now supplies full-
precision key visibility through the indirect target's alpha. The resolve takes
the minimum of atlas and contact visibility and writes opaque Hair alpha. The
GPU composition check matches all 4,080 Hair pixels, including 2,048 fractional
contact values, while preserving environment light and the 16 non-Hair pixels.

## Measured behavior

The native Hair DXIL uses a material-dependent stochastic disk around the
view-space key-light direction, four point depth loads, reciprocal ray-depth
interpolation and linear-depth rejection. It sums the four occlusion weights;
there is no quarter-average of their contribution. Grazing attenuation uses
the decoded surface normal. The result limits key-light visibility before
direct diffuse, both specular lobes and transmission are resolved.

The former preview pass used four evenly spaced taps with no disk jitter,
averaged their weights, used the strand for grazing, and multiplied the whole
scene color inside temporal sampling. That path has been removed.

The preview now writes native packed material targets and decodes vectors in a
separate pass; see **FUR_DEFERRED_PREVIEW.md**. Deferred lighting writes key RGB
and transmission code to one RGBA32F attachment and environment to another.
A dedicated resolve writes `environment + visibility * key`, then
HairDenoise reads that resolved texture, followed by temporal accumulation.
Non-fur pixels are copied unchanged. Disabling contact still resolves both
lighting contributions; the non-HDR path combines them in the material shader.
Orthographic viewing skips the perspective contact ray.

Opaque meshes now write linear depth into the shared depth attachment and
explicitly clear the fur mask/key outputs. The old opaque producer still wrote
reciprocal depth. HairDenoise eligibility and tile occupancy now use the explicit
fur mask, so opaque depth can occlude fur without becoming a denoise target.

`hair_surface.glsl` and `hair_lighting_noise.glsl` supply the camera and stochastic
inputs. The preview adapts its texture/view orientation to native top-left
coordinates. Material radius uses the measured transmission-code constants.

## Evidence

Private files live under the outer workspace's
`artifacts/rcra-fur-continuation/capture-tools/`.

| Check | Result | Evidence |
| --- | --- | --- |
| Complete Hair with shared contact/lobes | 11,215/11,215 stored RGB exact | `hair-dxil-shared-contact/report.json` |
| Native intermediate probe | Validated, unchanged-control output exact | `d3d-hair-shadow-17544/report.json` |
| Contact disabled | 4,080 test pixels equal key plus environment exactly | `preview-contact-behavior/report.json` |
| Contact fully shadows key | All 4,080 test pixels retain environment exactly | same report |
| Non-fur mask | 16 test pixels preserved in both modes | same report |
| Denoise with occupied opaque depth | Opaque pixels skipped; 4,080 constant fur colors exact | same report |
| Actual opaque shader outputs | 4,096 linear depths exact; fur mask/key outputs clear | same report |
| Wet head viewport, opaque depth, wind and denoise | Successful render; 4.4534 ms median synchronous frame time | `viewport-depth-mask.json` / `.png` |
| Fork suite | 250 passed | `pytest-opaque-depth-mask` |
| Non-HDR fallback | Full lighting renders with deferred/contact disabled | `viewport-contact-nohdr.json` / `.png` |

The GPU behavior check runs the actual `FUR_CONTACT_FRAG` source against
controlled textures. It checks the externally visible lighting/mask behavior;
it does not reproduce the shader equation on the CPU as its oracle.

## Remaining scope

Native material targets and separate vector decoding are now connected. Visible
opaque meshes and fur share consistent linear depth, with alpha blending disabled
for opaque depth. Runtime render flags remain to be connected. Lighting remains the isolated
unit key and default environment cube. Scene shadows, local lights/probes/grid,
native raster orientation, temporal history, matched camera/pose and full-frame
validation remain open. Captured unquantized lighting floats are slightly
different even though their stored RGB values agree exactly.
