# Saved native ear evidence — 2026-09-06

The ear contour remains unresolved. This audit runs on saved bytes only and
does not open the game, an RDC replay, Forge, or Unreal.

Run `external/RCRA-Forge/.venv/Scripts/python.exe unreal/fur/audit_native_ear.py`.
Output: `recovered/native-ear-audit/report.json` and `index.html`.

The native draw 24715 matches the later `fur-raster-replay-wet-shared-0`
coverage, all five targets (including motion), and hardware depth at all
6,308 covered pixels. Source manifest hashes are verified. The bounding
rectangle is [723,648,883,746] in a 1920×1080 image: only 160×98 pixels
across the rear head. This does not prove close-up parity.

The older `preview-material-final-0` snapshot matches four material targets
but not motion; its own report only claims four targets. Do not mistake
that superseded result for a current motion regression.

Crucial qualification to prior temporal validation: visually decoding the
saved event20572 TAA output reveals a Pause/Continue Game menu frame.
Shader agreement on those saved resources is still valid, but it is NOT
evidence of close-up fur-edge or fur-motion equivalence. The audit image
uses explicit numerical R11G11B10 decoding, clipping and gamma1/2.2, not
the final game tone mapper.

Other inspected images: approved-focus-later and vanilla-focus are startup
titles; replay-character-frames/scene is severely corrupted; the repeat
scene has small partly obscured rear ears. Hair event17544 is an isolated
lighting pass, not a final composite. No inspected export supplies the
matched close-up needed to classify the contour as native or erroneous.

No production/default/package changes. Preferred preview preserved.
Next prerequisite for a defensible parity decision is a clean native close-up
with matching pose, camera and lighting, or additional applicable saved
capture data. Do not repeat rejected shell count, background, or spacing
experiments on the basis of the menu-frame temporal test.

## Container inventory follow-up

`inventory_native_thumbnails.py` checks all 17 saved riftapart RDC files
without replaying or decompressing frame payloads. All standard thumbnail
fields are empty. Sixteen section tables parse successfully with no extended
thumbnail section. `riftapart-complete_capture.rdc` fails the existing section
parser with an unexpected marker; its extended-thumbnail status is unknown,
not evidence of capture corruption. Details are in
`recovered/native-ear-audit/thumbnails/report.json`.

No new close-up was obtained. A useful next reference is a native-resolution
game screenshot with Ratchet stationary, the striped ear facing the camera,
the lower rim unobscured, and a plain contrasting background. Preserve the
full screenshot and note resolution, AA/upscaler, and photo-mode sharpening
if known. Aim for at least roughly 300 pixels along the ear; do not enlarge
a distant shot. A single screenshot enables a spatial comparison only;
motion parity still requires a sequence. Match the reconstruction to this
reference camera after receiving it, rather than requiring an exact camera
match from the user. No RenderDoc capture is needed for this first check.

### User explicitly requested self-acquired reference — 2026-09-06
Attempted native retail launch rather than asking user for a screenshot.
All jobs: inactive desktop, below-normal, max6GiB, minphysical8GiB,
mincommit8GiB, mindisk2GiB; no RenderDoc injection. No game rendered.
1 live-job: Documents log access denied in sandbox; stopped owned job.
2 live-retry-job: escalated normal file access approved; game reports Steam
not running. Peak1.78033GiB; stopped owned job.
3 live-steam-job: silent Steam/applaunch, web helper repeatedly exits before
game launch; peak.79457GiB. Stopped owned job; inputdesktop Default throughout.
Game-specific mute monitor started before launch; no audio sessions appeared,
so do not claim an actual game audio session was verified muted.
Retry using historical optional --ui-restrictions none was REJECTED by automatic
approval review: removes desktop/display restriction required by background/no
control instruction; also cited unverified mute and crash history. Not executed.
Do not retry via workaround. Need explicit approval of that changed isolation
or a safe solution keeping restrictions. Resource guards must remain unchanged.
Published reference fallback located Insomniac Photo Mode article and its
AaronRatchetLighting image, but image fetch failed; no inspected native closeup
obtained. Browser control tool unavailable in current tool catalog. No parity
claim, no production/default/package changes. Native acquisition still blocked.


## Native close-up acquired — 2026-09-07
The earlier image-acquisition block is superseded. Official PlayStation/Insomniac photo-mode images were downloaded and inspected at native pixels; provenance and SHA256 hashes are in recovered/published-native-reference-20260907/sources.json. Native-lighting.jpg and the wall-running native-ear-crop.png contain usable ear detail. The public reference establishes visible strand highlights but has unknown camera intrinsics, pose, lighting and photo-mode settings. It is not a registered pixel-parity target. A Forge dry view at yaw150/pitch5 completed under the unchanged guard (peak1.9554GiB); comparison.html preserves both views and limits. No contour fix or native parity claim follows from this camera change.
