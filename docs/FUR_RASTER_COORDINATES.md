# Fur raster coordinate contract

Status: 2026-09-04. The captured native raster state is active in the production
viewport on OpenGL 4.5 or `GL_ARB_clip_control` contexts. Older contexts retain
the complete legacy lower-left/forward-depth path rather than mixing conventions.

## Proven native state

The dry captured draw at event 24715 matches all 6,308 surviving pixels, all
five material targets and hardware depth exactly when the replay uses:

- upper-left window origin;
- zero-to-one clip depth;
- counter-clockwise front faces and back-face culling;
- reverse-Z `GreaterEqual` depth testing with depth writes;
- captured resource rows without a compensating vertical flip.

The same state retains exact results at wetness 0.25, 0.5 and 1.0, for 24,226
surviving pixels in total. The reports are
`fur-raster-replay-wet-shared-{0,0.25,0.5,1}/report.json` under the outer
private evidence directory.

A lower-left control followed by a row flip produced two missing and five extra
pixels. That establishes raster origin as part of the result, not a presentation
choice that can be repaired after shading.

## Current viewport state

The viewport detects core 4.5 or `GL_ARB_clip_control`, enables upper-left
zero-to-one clip control, clears depth to zero and uses `GreaterEqual`. Perspective
and orthographic draws use their right-handed reverse-Z matrices, and opaque and
fur material passes share the same depth renderbuffer. Every viewport shader is
compiled through one mode injector, so material coverage, motion, lighting,
contact, denoise, temporal and fullscreen paths all select the same convention.

The final QOpenGLWidget framebuffer is the single presentation boundary. Its
composite temporarily restores a lower-left raster origin while the native
fullscreen vertex shader samples the upper-left offscreen textures. This gives
Qt the row ownership it expects without flipping any production render target.

## Atomic production migration

The production migration changed the complete pipeline together:

1. Enable upper-left, zero-to-one clip control before any scene draw.
2. Replace the perspective projection with its reverse-Z zero-to-one form,
   clear depth to zero and use `GreaterEqual` for opaque and fur draws.
3. Keep the shared opaque/fur depth attachment in that convention; changing only
   the fur pass would compare incompatible depth values.
4. Re-audit every manual Y adapter in `ui/viewport.py`, including material,
   motion, decode, contact, denoise, gather and temporal sampling. With an
   upper-left window origin, several current flips become double flips.
5. Re-audit texture upload row order and the scene bundle's top-left addressing.
   Native gather selection must still happen before any storage-orientation
   conversion.
6. Revalidate the grid inverse projection, camera picking, bloom/composite
   passes, orthographic fallback and the Qt default framebuffer.

The right-handed reverse-Z perspective coefficients for view-space forward
along negative Z are `m22 = near / (far - near)`,
`m23 = near * far / (far - near)`, `m32 = -1`. The orthographic counterpart
maps the API's right-handed view planes at `z = -near` and `z = -far` to one
and zero. CPU endpoint tests cover both builders. The legacy builders remain as
the coherent fallback for contexts without clip control.

## Offline source audit

The migration inventory below follows every active composed-frame boundary.
“Direct” means the pass uses the framebuffer's own storage coordinate and
should remain direct after all render targets adopt upper-left origin.

| Pass or helper | Current lower-left adaptation | Upper-left migration |
| --- | --- | --- |
| Fur coverage `screenLayerRandom` | Converts `gl_FragCoord.y` to `height-y` | Remove the conversion; pass the native fragment position |
| Wet layer divisor | Converts `gl_FragCoord.y` to `height-y` | Remove the conversion |
| Contact-depth material phase | Converts `gl_FragCoord.y` to `height-y` | Remove the conversion |
| Material motion output | Converts `gl_FragCoord.y` to `height-y` | Remove the conversion; `furMotionVector` itself stays unchanged |
| Deferred decode | Direct `texelFetch` at `gl_FragCoord` | Preserve direct addressing |
| Hair lighting center loads | Direct `texelFetch`, then converts center Y for native math | Preserve direct loads and remove the native-math conversion |
| `hairHistoryDepth` / contact depth loads | Converts native top-left Y back to texture Y | Remove the conversion |
| Contact resolve | Direct center loads, then converts center Y | Preserve direct loads and remove the conversion |
| Denoise center loads | Direct `texelFetch`, then converts center Y | Preserve direct loads and remove the conversion |
| Denoise gather-address path | Native address is converted to texture Y | Remove the conversion after render-target row zero becomes top |
| Denoise hardware gather fallback | Flips UV and reverses gather components | Use native UV and re-establish component order with an upper-left shader check |
| Denoise scalar fallback | Converts each native gather address to texture Y | Remove the conversion |
| Denoise tile occupancy | Converts each top-left tile pixel to texture Y | Remove the conversion |
| Temporal motion consumer | Uses `(-motion.x, +motion.y)` for lower-left UV | Use `-motion.xy` in the upper-left storage frame and the CPU-tested upper-left jitter offset |
| Fullscreen `POST_VERT` | NDC Y and texture V both increase upward | Flip generated texture V so upper-left clip-space raster samples row zero at the screen top |
| Infinite grid | Unprojects clip depths -1 and +1 | Unproject reverse depths 1 and 0; preserve ray direction from near to far |
| Opaque and fur depth | Default clear 1 / `Less` | Clear 0 / `GreaterEqual`, with writes enabled for both |
| Legacy ribbon screen shadow | Treats smaller depth as closer | Reverse the comparison if this inactive diagnostic is retained |
| Qt final framebuffer | Uses the same fullscreen shader | Validate orientation and front-face behavior with the migrated `POST_VERT` |

Material UVs and uploaded texture rows are independent of window origin. They
must retain their numeric UV contract; only screen-space resources and
fullscreen copies change. Camera mouse deltas also stay in Qt's top-left UI
coordinates and do not depend on OpenGL clip control.

The projection-jitter Y sign is now derived and covered by a stable-coordinate
CPU test: with the existing matrix perturbation, upper-left raster X moves by
`-jitter.x` and Y by `+jitter.y`. The native temporal branch therefore subtracts
both motion components and uses the corresponding upper-left history offset.
The native denoise fallback uses explicit texel addresses, avoiding an
implementation-facing `textureGather` component-order assumption. Camera
disocclusion also flips reconstructed and projected centered Y under the native
mode; leaving those two signs in the legacy frame would corrupt camera-motion
rejection even though ordinary material output remained upright.

## Runtime validation

A guarded 480x480 logical/600x600 physical perspective run activated native
raster on an NVIDIA OpenGL 4.6 context. Deferred material, contact, denoise,
motion blur, disocclusion, accumulated alpha and TAA remained valid. The frame
contained 27,973 exact Hair-category pixels and 17,857 nonzero opaque-velocity
pixels per component, while temporal age advanced from 1 to 9 across seven
camera-yaw steps. Direct image comparison against the prior upright frame has
2.0864 RGB RMSE; comparing against its vertical flip has 21.7763 RMSE. This
proves the Qt presentation boundary is oriented correctly.

A guarded orthographic run exposed and then closed two migration defects. The
captured CCW/back-face state is now scoped to the recovered fur draw so editor
materials remain two-sided, and the orthographic matrix now evaluates planes at
`-near/-far`, restoring correct reverse-depth ordering. The final 500x450
physical image has intact face, eye, helmet, ears, fur and grid geometry.

The perspective and orthographic jobs exited with code zero, retained `Default`
as the input desktop, left no process or window, and peaked at 1.580 and 1.487
GiB under a 2 GiB hard limit. All legacy/native production shader variants
compile offline.
