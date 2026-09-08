# Connected Hair shading and denoise

2026-09-03: the unmodified production decode, scene lighting, color-store and
denoise shaders reproduce **all 11,215 captured Hair pixels exactly at both
stored-color boundaries**. This closes the connected shading/denoise comparison
for events 17544 and 17551. Full raster, generated-motion and temporal parity
remains open.

## Production changes

`hair_history.glsl` implements the native three-tap reflection-history sampling,
velocity reprojection, depth weighting and occlusion. The scene path combines
the key, probe and history accumulators before the shared material resolve.
Atlas/contact visibility is resolved before those accumulations. The post pass
then performs the native color store without applying contact a second time.

Scene bundles accept optional `reflection_history` (half-resolution packed
R11G11B10 uint32), `reflection_velocity` (half-resolution RG16F) and
`denoise_mask` (full-resolution R8_UNORM uint8). Color and velocity must be
provided together. History dimensions round up for odd viewport sizes.
`HairSceneGpu` owns their allocations and uses 18 fragment units for lighting.
Scene projection and frame timing also drive denoise and material coverage;
camera invalidation restores the preview's own timing.

The denoiser keeps Hair write eligibility separate from neighboring Skin's
fractional filter mask. It preserves surrounding scene color. Native gather
addresses come from a viewport-sized R32UI index texture: hardware chooses the
four addresses using the original top-left UV, then texel loads account for the
preview's vertical texture orientation. Flipping UV before the gather changed
subtexel rounding and caused 1,309 remaining stored-color differences. The
address map removes every one. It costs four bytes per framebuffer pixel and
is recreated/released with the other viewport targets.

## Evidence and boundaries

Evidence is under the outer workspace's private
`artifacts/rcra-fur-continuation/capture-tools/` directory.

| Check | Result | Report |
| --- | --- | --- |
| Production packed decode through scene lighting | 11,215 exact stored RGB; unquantized max 4.9471855e-5, RMS 5.249596e-7 | `scene-complete-native/report.json` |
| Actual production GPU color store | 11,215 exact RGB; max 0 | Same report, `store` |
| Connected production denoise and second color store | 11,215 exact RGB; max 0 | Same report, `denoise` |
| Native full replay with shared history kernel | 11,215 exact stored RGB | `hair-shared-history/report.json` |
| Live viewport history/mask, camera fallback, release and reattachment | Passed with and without atlas | `viewport-scene-lifecycle.json`, `viewport-scene-shadow-lifecycle.json` |
| CPU validation and source compilation | 268 tests; all shader sets compile | `pytest-hair-chain-20260903`, `scene-shader-validation/report.json` |

The connected check begins with original native packed G-buffers and scene
resources. It clears every Hair color before drawing; native Hair output is
used only for comparison. Already-shaded **non-Hair** scene color and fractional
Skin masks are supplied as neighboring scene inputs. Consequently it verifies
the Hair integration into that scene, not reconstruction of the other materials.

Lighting shader SHA256:
`1bb188a4f97187aec1447194ca5b751256ebcd8987cd6ef695eb718d0ed813c5`.
Denoise shader SHA256:
`a47d8a2c06ca75bd57a736d4489beef25d7d94d7fe46a56eb3b2a7990748466`.
The history scene bundle SHA256 is
`c882b13f5ee2343e2739b53a72b2a6f29961024f5e67ed995495a0b8e548b9a1`;
the connected tool separately adds the verified denoise mask.

Dry, wet and forward fallback viewport checks passed. The combined five-check
wrapper reached its 180-second deadline during the last atlas check. That final
check was rerun separately and exited successfully; the first timed-out wrapper
must not be reported as a completed five-check run.

## Next comparison

Capture 5 starts after the fur material draws that supplied event 17544. Its
recorded head draw 24715 belongs to the following frame, whose lighting is beyond
the capture's end. The complete indirect-dispatch inventory after that draw
contains no Hair pass (`second-frame-hair/report.json`). Capture 6 also ends
before its recorded head draw's Hair lighting. Do not combine these different
frame intervals as an end-to-end raster proof.

A longer private no-save capture is deferred until game work resumes. Native
raster origin/depth, generated motion, disocclusion and final temporal apply are
now connected; see [HAIR_TEMPORAL_RECONSTRUCTION.md](HAIR_TEMPORAL_RECONSTRUCTION.md).
Local point/area lighting, shadow/contact paths and key cloud/gobo/volume
modulation are also connected from exact scene resources. Their contributions
are absent in the verified 17544 reference, so nontrivial output parity still
needs an active-Hair capture. The local screen-shell producer and near-plane
clip/cap preparation now run from explicit manager inputs; automatic scene
ownership and source-light selection remain open.
