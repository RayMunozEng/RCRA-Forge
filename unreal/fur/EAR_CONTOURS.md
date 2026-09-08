# Ear contour investigation

User identified contour bands along Ratchet's lower ear rim in both Forge and
Unreal. Do not conflate this with the separate sheep lighting difference.

Shared code inspection:
- Both previews use discrete shell surfaces and the same recovered 32-slice
  procedural density texture. Slice 0 has 81.9% fully opaque texels, slice 1
  68.9%, slice 2 60.0%, and slice 4 47.1% at mip0.
- Dense inner shells can present continuous bands at grazing angles. This is a
  candidate explanation, not proof that the marked line is a specific shell.
- Unreal uses fixed i/count depth; Forge also implements view-dependent shell
  availability. Availability reaches 1 near grazing, so lack of that feature
  alone does not explain an artifact visible in both at the rim.

Diagnostic: capture_reference_ear_contours.py compares lit32, unlit32, unlit16,
unlit64 and a collapsed one-shell base. This changes no saved reference scene
or production shader. The 64-shell stage is only a short isolation test within
the existing actor cap, not a shipped solution or a claim of native parity.

Before choosing a fix, inspect whether contours persist without lighting,
whether their spacing changes with shell count, and whether the same line
exists on the base surface. Do not hide geometry bands by darkening textures,
adding ambient fill or blurring the entire character.

Completed diagnostic: all five captures succeeded on the bounded retry. See
recovered/ear-contours/report.json and the named PNGs. The count sweep changes
the edge envelope; 64 shells mostly extend dense coverage rather than proving
a contour fix. ear-edge-profile.json records the edge transition relative to
the base silhouette. No production shader change was made.

Next check final fur compositing, including Forge's currently disabled
contact-depth/denoise paths, before changing recovered coverage. Cause remains
under investigation; the contour issue is not fixed yet.

## Post-processing and shell-depth isolation, September 6

Completed matched Forge captures with neither pass, contact only, denoise only,
and both. Actual report toggles are recorded in
recovered/ear-contours/post-comparison.json. Ear-rectangle mean absolute RGB8
changes relative to neither are 4.390, 0.640 and 6.255 respectively. These
measure image change, not improvement. Neither pass nor their combination
demonstrates clean removal of the rim contour. Each run exited 0 near 2 GiB.

Added private --shell-depth diagnostic to capture_forge_environment.py and its
guarded runner. It changes albedo only after the original coverage/discard;
displacement, texture alpha, depth testing and shell availability remain intact.
Base is red, nonbase slices below 4 cyan, 4–8 green, 8–16 blue, 16–32 magenta.
Lighting and temporal averaging remain active, so this is not an exact per-pixel
shell-ID buffer. The capture visibly shows nested depth bands at the lower ear
rim and outer magenta coverage beyond them. This strengthens the shell-envelope
explanation; it does not register the user's marked pixels to individual shells.

First diagnostic process exited 3221226505 before saving a capture, peak 1.3401
GiB. Found an integer used as a GLSL ternary condition in the temporary shader;
corrected it to an explicit comparison. Retry exited 0, peak 2.00684 GiB, with
a fresh report and capture. No guard limits changed; no graphics job remains.

compare_ear_post.py generated comparison.html with five original-image crops at
1:1 pixels, plus report settings and image hashes. No resampled or synthesized
image evidence. Production shaders and release ZIP remain unchanged.

Next: isolate the band transition against continuous shell depth and the
authored length/control field, retaining the original coverage as a control.
Use the existing captured-draw replay as the native reference before modifying
recovered material equations: FUR_CAPTURE_PARITY.md documents exact coverage
for one captured dry draw, which is stronger evidence than a cosmetic preview
adjustment. The preview's coordinate/temporal limitations remain separate.

## Geometry isolation follow-up

User preferred the comparison and requested continuation. Preserved that
checkpoint. Ran two additional private Forge variants with both post passes:
fixed-spacing removes view-dependent depth scaling/rejection; uniform-length
sets vertex controlLength=0.5. Original authored reference is unchanged.

Both captures exited0, peak job memory2.00225/2.00291GiB respectively. Fixed
spacing retains the visible rim transition. Uniform length also retains an
edge transition and grows fur into normally short/zero-length areas near the
eye and headgear. Neither demonstrates a clean improvement. Uniform length is
not a pure coverage test: it also affects curved UV offsets and invalidates
authored contact-depth agreement. Do not ship either override as a fix.

compare_ear_post.py --geometry verifies camera/model/LOD/size/temporal count
and post settings against the reference, then writes geometry-comparison.html
and .json. Ear rectangle MAE3.642/3.168 RGB8 measures change only. The earlier
five-panel comparison remains intact. Python syntax checks passed for all
three diagnostic scripts; all graphics processes finished. Production and
release package unchanged.

Next investigate the final temporal edge reconstruction against saved native
capture evidence. Do not continue tweaking authored length or shell count on
the strength of these inconclusive isolation tests. Distinguish a residual
shell limitation from a missing native resolve step before a production fix.

## Temporal evidence audit and background-depth isolation

Corrected the earlier assumption that native raster migration was outstanding:
FUR_RASTER_COORDINATES.md and the current capture reports confirm native
upper-left/reverse-Z is active. The final Production apply validation section
of HAIR_TEMPORAL_RECONSTRUCTION.md documents the production temporal shader
against saved event20572 inputs, with sparse residual rounding differences.
Older statements in FUR_CAPTURE_PARITY.md and intermediate temporal sections
are superseded. Do not port a second TAA implementation based on those notes.

Found a concrete isolated-preview boundary: temporal opaque/composed depth is
zero behind the head. Center/diagonal minimum selection can pick that sentinel
at the silhouette; the disocclusion pass deliberately returns inert values for
selectedDepth<=0. The game has valid background depth at this boundary.

Added private --far-background experiment: only TEMPORAL_LINEAR_DEPTH_FRAG
substitutes 100.0 for empty opaque depth. The composed target retains actual fur
depth where fur exists. Geometry, material coverage, lighting, contact/denoise,
camera and 33 temporal samples are unchanged. This does NOT add background
motion or scatter inputs and must not be shipped as a full scene fix.

Capture exited0, peak2.00246GiB under unchanged guards. Fine silhouette coverage
changes, but the broad rim transition remains; no demonstrated complete fix.
Ear rectangle MAE0.7651RGB8, whole0.1925 measures change, not improvement.
compare_ear_post.py --temporal verified matched settings and generated
temporal-comparison.html/.json, leaving preferred and geometry comparisons
intact. No graphics processes remain; no production shader or package change.

Next useful gate is a proper background geometry/depth/motion fixture and an
edge-stability comparison, rather than more density/length changes or a second
temporal implementation. Native resource evidence already validates the filter;
remaining preview inputs and scene context must be isolated coherently.

## World-space background and moving/held camera fixture

Added private ear_scene_fixture.py, installed only by --scene-sequence, with
optional --scene-background. Two world-space triangles write black color,
hardware depth, opaque linear depth, current/previous-MVP velocity and stencil0
before the character. The plane stays fixed while the camera orbits. Both
control and plane use the same extended far clip100 (near unchanged), authored
fur, contact+denoise and the same 24-frame schedule: yaw30.15..31.8 for12frames,
then12 held frames. Native raster required; FPS/resource guards unchanged.

Validation caught an initial fixture error: the ordinary model-fitted far clip
excluded the plane. Initial images were therefore invalid as background tests.
A readback assertion run exited3221226505 (~2.0071GiB); follow-up RGBA readback
explicitly recorded zero depth/velocity. Extending the fixture far range in
BOTH cases corrected clipping. Final plane/control runs exited0 with peaks
2.00404/2.00740GiB. Three background probes read linear depth3.589195 and finite
nonzero velocity (includes projection jitter). These verify that the background
producer is active; no claim of independent native motion bit parity.

compare_ear_sequence.py verifies identical per-frame camera/temporal schedules,
background flags, 24 frames and positive depth/nonzero velocity probes. It
generates sequence-comparison.html with synchronized Play/scrub controls,
original PNG crops, and sequence-comparison.json. Playback is opt-in10fps and
stops when hidden. No graphics job remains. The top-level environment.png is
pre-sequence, while stock camera fields are final-state; sequence.json is the
authoritative per-frame record.

Across12 held frames, mean temporal RGB8 stddev in the ear rectangle is
1.54649 empty versus1.88811 plane; mean consecutive change1.32911 versus1.72182.
In a shared6227-pixel lower-rim mask it is7.22020 versus11.01777. This mask is
derived from the final empty frame's lower silhouette, extending8pixels inward
and4outward. Values include settling after movement; they are not a pure
stationary shimmer score, contour-quality score or native parity measure.
Real background does not demonstrate an improvement and broader rim remains.

No production shader or release changes. Preferred earlier comparison preserved.
Next compare the original rim symptom in Unreal with equivalent scene/motion
conditions before treating this Forge-specific background behavior as a shared
fur defect. Revisit history rejection inputs only with per-pixel evidence;
do not arbitrarily lower the native temporal response to hide variation.

## Unreal counterpart, September 6

capture_reference_ear_sequence.py reuses the environment fixture and matched
camera path. It records24 moving/held frames each with the backdrop hidden and
visible. Backdrop is a black unlit thin cube (2000x2000x0.1cm) centered on the
converted Forge plane, oriented by its normal; square orientation within the
plane is immaterial at this extent. Authoring32shells, dry/wind0, environment.6,
no selected-caster shadows, live UE TAA2. No saved map or production changes.

Earlier run was interrupted during startup with stale unfinished job metadata;
no editor process remained. Fresh guarded run completed exit0 peak4.09613GiB.
All48 images present and liveAA2. Python syntax checks passed. No jobs remain.
compare_ear_sequence.py --ue creates ue-sequence-comparison.html/.json with
matched camera/index gates and the same within-engine lower-rim metric.

Held12frame ear-rectangle temporal stddev:.90265 empty/.90926 backdrop.
Lower-rim shared6240pixel mask:6.23671/6.32988RGB8. Broad contour remains in
both images. No demonstrated improvement from backdrop. These include settling
and stochastic phase differences; phase/cadence are not locked across UE runs
or to Forge. UE has no recovered Forge contact/denoise and uses its own TAA.
Do not rank engine quality from these values. Unlike Forge, this fixture has
no direct GPU depth/velocity readback; actor setup/visibility is the evidence
for backdrop presence, not a verified buffer contract.

The background experiments provide no basis for a shared production contour fix.
Next return to the spatial shell boundary: register the marked line to source
mesh/base-shell versus outer-shell contributions in UE, using depth/material
isolation. Keep the preferred appearance and do not change global TAA response.

## Direct shell isolation and count compensation — September 6

User requested fixing all remaining contour work, including motion and sheep
regression verification. This request is NOT complete; no accepted contour fix
exists yet. Do not reframe these diagnostics as completion.

capture_reference_ear_boundary.py creates a private material with ShowBase,
ShowOuter and DebugBoundary. Original displacement, sampled coverage and
lighting remain unchanged; the controls mask base/nonbase afterward or replace
final color with red/cyan. Four captures exited0, peak4.17745GiB. Outer-only
retains the ear rim while producing holes elsewhere where the base is needed.
The colored ear rectangle contains0 red base pixels and95293 cyan nonbase
pixels using >100/<50 thresholds. The broad ear boundary is covered by outer
shells, not exposed base geometry. Do not remove the base surface as a fix.

Added optional RFCountedCoverageWithMask helper in RecoveredFurAdapter.ush.
Existing RFCoverageWithMask is a compatibility wrapper fixed at32, preserving
the original equation and branch at all existing call sites. The new helper
uses1-(1-alpha)^(31/(count-1)) for nonbase shells at nonreference counts. This
is an independent-sample optical-depth authoring approximation, NOT native
shader recovery. It is unused by production builders/default materials.
Scalar invariant check over counts16/32/64 and alpha0,.001,.1,.5,.9,1 passed
with max error8.88e-16; correlated volume samples limit its physical assumption.

capture_reference_ear_resampling.py privately binds the new helper and tests
reference32/raw64/normalized64. Exit0, peak4.15130GiB. The adjusted64 image
still shows the contour, so this is NOT an accepted fix or new default.
No release package updated. compare_ear_boundary.py validates images/liveTAA2
and creates boundary-comparison.html/.json with original1:1 crops.

All jobs have stopped. Preferred version remains intact. Motion/sheep regression
for a final correction is still pending because no correction passed the ear
acceptance gate. Next work must address the spatial shell boundary directly;
background/TAA/base-removal/count-only hypotheses have not solved it. Avoid
claiming a unique native bug from these images or introducing global blur.

## Spatial spacing experiment — rejected

capture_reference_ear_spacing.py adds private rest-position sine variation to
interior shell depth (max0.45step), multiplied by4*t*(1-t). Base and outermost
shell remain fixed. Shared smooth noise preserves layer order;6363 CPU cases
(counts2..64, noise-1..1) passed endpoints and strict ordering. No production
builder or shader changed this turn. This is an authoring experiment, not a
recovered native rule.

First startup exited cleanly after Python AttributeError: the UE class is
MaterialExpressionPreSkinnedPosition, not PreSkinnedLocalPosition. Corrected
using installed headers and used a fresh private material M_EarSpacing_v2 so
the partially constructed v1 was not reused. Retry exit0, peak4.13511GiB under
unchanged guards; all3liveTAA2captures completed. No jobs remain.

Original/half/full captured in recovered/ear-spacing. compare_ear_spacing.py
validates labels,AA,size and builds ear-contours/spacing-comparison.html/.json.
Ear rectangle mean change1.24380/1.26880RGB8; change is not improvement.
Broad contour remains, grain changes; no clean fix demonstrated. Rejected for
promotion. Preferred appearance unchanged. Motion and sheep checks for this
candidate are unnecessary because it failed the original symptom gate.

Next obtain a registered native-ear boundary comparison from SAVED capture
evidence before adding more speculative shell changes. Need distinguish a
reproduction defect from expected close-range shell-fur behavior. User's full
fix request remains incomplete; do not package these experiments as fixes.

### Saved native evidence audit — 2026-09-06

See NATIVE_EAR_AUDIT.md and recovered/native-ear-audit/index.html.
CPU byte audit passed: later wet-shared-0 matches all five native raster
outputs, coverage and depth at all 6308 covered pixels. Old four-target
snapshot's motion mismatch is superseded. Native head draw spans only
160x98 pixels; no inspected export provides a matched close-up ear.
Decoded saved TAA output is a menu frame: numerical shader validation
must not be presented as validation of the fur edge or fur motion.
No graphics jobs launched, no defaults/package changed. Ear fix remains
outstanding. Next prerequisite is an applicable native close-up reference;
do not repeat rejected spacing/count/background candidates as fixes.


## Native close-up acquired — 2026-09-07
The earlier image-acquisition block is superseded. Official PlayStation/Insomniac photo-mode images were downloaded and inspected at native pixels; provenance and SHA256 hashes are in recovered/published-native-reference-20260907/sources.json. Native-lighting.jpg and the wall-running native-ear-crop.png contain usable ear detail. The public reference establishes visible strand highlights but has unknown camera intrinsics, pose, lighting and photo-mode settings. It is not a registered pixel-parity target. A Forge dry view at yaw150/pitch5 completed under the unchanged guard (peak1.9554GiB); comparison.html preserves both views and limits. No contour fix or native parity claim follows from this camera change.
