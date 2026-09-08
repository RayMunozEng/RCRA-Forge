# UE 5.8 fur-authoring checkpoint — 2026-09-05

User changed direction from Rift Apart inspection to a general UE5.8 tool for making fur. Implemented the first standalone static-mesh authoring plugin in unreal/plugins/FurAuthoring. This is an adapted authoring prototype, not a complete transfer of the recovered native renderer.

Delivered controls: non-destructive instanced shells,1..64 layer cap, length in centimeters, UV-cell density, strand width, world-space comb, root/tip colors, roughness, wind direction/speed/strength and wetness. Short Fur and Wool are starter presets; Wool does not reconstruct the game's authored curly base. Blueprint SetWeather updates material parameters without rebuilding instances. Source removal clears layers. Source collision remains disabled. Groom and wind bounds include the maximum procedural-wave amplitude.

Shader uses an original procedural neighbor-cell coverage function, authoring-oriented wind and Unreal Default Lit shading. Wet albedo attenuation carries over the recovered coefficient/response. It does not yet use the recovered shell-volume texture, original full wind table, native Hair lighting/denoise, skeletal deformation, painted maps, or per-view probe machinery. Do not claim full original-system parity or native-looking sheep fur.

Verification completed:
- Real UE5.8.0 build55116800 C++ Editor build succeeded with one worker, including final bounds correction.
- Standalone HLSL vertex/pixel smoke compiles succeeded.
- UE editor Python workflow passed material creation and repeat preservation, default shell count, cap, two presets, weather clamps, and source removal. Material saved under /FurAuthoring/Materials.
- Corrected neutral demo rendered640x480 underD3D11/SM5, visually inspected, no error lines in final render log. Peak final job4.462GiB under6GiB cap; input desktop stayedDefault. One shader compiler worker. Final render process exited0.
- Packaged source/assets and Win64 editor DLL; ZIP readback matches SHA256 for every manifest file. unreal/fur/package-validation.json records archive SHA256. Binary build ID55116800; other engine builds/platforms require rebuilding source.

Initial failures were resolved: missing Projects import library led to removing that dependency; shader path resolution now checks ordinary project/engine plugin folders then compile-time source root for additional-plugin layouts. An initial path assertion was replaced with graceful error reporting. UE tablet startup failed in the offscreen test, so StylusInput is disabled only in the isolated validation project. UE5.8 asynchronous Python uses EditorPythonScripting.set_keep_python_script_alive. Camera framing uses MathLibrary.find_look_at_rotation. No user project or system tablet configuration was changed. Earlier failed screenshots/log attempts are not success evidence.

Artifact: unreal/fur/FurAuthoring-UE5.8.zip. Extract FurAuthoring into a project's Plugins folder, enable, open Fur Authoring Content / Demo / FurDemo, or place Fur Actor and select Source Mesh. Generated material loads automatically. README documents controls and limits. Test project: unreal/fur/ValidationProject/FurValidation.uproject. Current screenshot: unreal/fur/fur-ue58-preview-framed.png.

## Recovered-core continuation — 2026-09-05

After the user said the prototype was insufficient and authorized continuing,
added a separate recovered material path, not a change to the packaged v0.1.
`export_recovered_core.py` extracts the verified procedural texture generators
without starting a renderer, exports exact 128x128x32 R8/four-mip DDS bytes,
checks all slice/mip readbacks, and generates HLSL from the verified material,
noise and full wind-table kernels with source/output provenance hashes.
Standalone VS/PS HLSL smoke compiles passed. Fused rounding/native parity is
not implied by successful translation or compilation.

UE TextureFactory imported T_DefaultFurShells as a linear Texture2DArray with
LeaveExistingMips. M_FurRecovered compiled and produced fresh 640x480 dry/wet
images for short fur and wool, visually inspected. Images and reports are in
unreal/fur/recovered. Wet coverage now uses the recovered UV divisor/volume
response and darkening; geometry is not shortened by wetness. The recovered
wind kernel is connected but these captures deliberately use zero wind.

Remaining adapters: fixed-depth ISM shells (native whole-triangle view rejection
not implemented), uniform control channels, root/tip gradient, fixed temporal
inputs and Default Lit. No artist map painting, skeletal integration, recovered
lighting, matched Forge/UE mesh comparison or cooked texture readback yet.
RecoveredShellCount must match actor shell count; diagnostic presets use32.
RecoveredDensity and OffsetScale are material-instance parameters; old Density,
StrandWidth and world Groom do not control the experimental material.

Resource/validation issues are recorded, not hidden: first import failed on an
unwritable default DDC; first render timed out on an unwritable shader work dir.
Use project-local LocalDataCachePath AND ShaderWorkingDir with
DDC=InstalledNoZenLocalFallback. Successful capture job peaked4.486GiB under6GiB,
one shader worker, unchanged active desktop, but timed out during shutdown.
A subsequent DDS round-trip attempt hit UE's unsupported Texture2DArray export
assert in ImageUtils.cpp:249. Exporter call removed; do not retry that path.
Exact imported/cooked-byte verification needs a dedicated reader.

`save_recovered_demo.py` saves a separate FurRecovered demo with persistent
MICs; check recovered/save-demo-job.json and log for its final save status.
The historical FurAuthoring-UE5.8.zip remains v0.1; do not present it as including
this recovered-core continuation.

Next: artist control maps/automatic parameter wiring, matched mesh/inputs in
Forge and UE, native shell geometry/skeletal current+previous deformation,
recovered lighting and temporal behavior, LOD/performance and authoring UX.
Do not resume unrelated smoke/scene-manager tracing without user direction.

## Imported authoring maps — 2026-09-05

User authorized the next work. Added actor LengthMap (R), DensityMap (R),
GroomMap (RG), RecoveredDensity/GroomStrength and UseMappedFur/SetFurMaps.
UseMappedFur selects the separate M_FurAuthoringMaps asset. Existing prototype
and recovered material assets are preserved. RecoveredShellCount is now wired
automatically for every actor; opt-in map controls preserve existing MIC density
and offset values when disabled. Map removal resets both enable flags and
bindings. Length uses wrapped mip-zero point sampling, grooming and density
are pixel sampled. Density zero and length zero remove shells while keeping
the base surface. Linear imported maps are supported, not an editor paint brush.

UE5.8 editor build succeeded with one worker (95.14sec). Sandbox build first
failed because UBT rotates its own AppData trace files; the narrowly escalated
build succeeded. Six editor workflow checks passed, including16-shell automatic
synchronization, three bindings, clearing all maps, and saved FurMaps demo.
API job exited0, peak1.425GiB. Diagnostic textures are synthetic, not game assets.

Fresh640x480 baseline, length/density and groom captures rendered without
shader/Python errors and were inspected. Length bands change the short-fur
silhouette; density bands remove wool while leaving its base visible. Groom
changes the layered coverage field; the native strand lighting is still absent.
Warm render job exited0, peak4.385GiB under6GiB, one shader worker, input desktop
Default. The cold run hit its300sec deadline; retained as maps-render-cold logs.
Validation: recovered/maps-validation.json, maps-render.json, maps-api-job.json,
maps-render-job.json. Runner: run_check.py, with local shader/cache directories.

Saved map: /FurAuthoring/Demo/FurMaps. Packaged source/assets/current Win64 DLL
in FurAuthoring-UE5.8-maps-preview.zip, version0.2.0-preview in its descriptor.
29 files,485978bytes, archive SHA256
4d462035a5a0ce35aecbc898414f2eb7a5e0c5d397dcb6ca3b9469fd4b11457f.
Every manifest file passed ZIP readback hashing. Earlier v0.1 ZIP preserved.
Workspace descriptor stays0.1; package script sets the preview version explicitly.

Still outstanding: in-editor painting, skeletal deformation, native triangle
rejection and fur lighting, matched Forge/UE inputs, temporal behavior and LOD.
Do not claim the complete fur-tool roadmap or native parity is finished.

## Skeletal pose sharing — 2026-09-05

User continued. Added ASkeletalFurAuthoringActor (Skeletal Fur Actor), with
PoseSource/SetPoseSource accepting a skinned component. Generated skeletal
components attach to the source and share its evaluated pose via
SetLeaderPoseComponent; they do not run separate animation graphs. Defaults16
layers, maximum32. Each layer has its own DMI and i/count ShellDepth. Shared
map/weather controls update all materials. Rebuild destroys old components;
source removal clears them; source/mesh changes are checked on tick. Source
animation and visibility remain externally owned. Static SourceMesh is unused.

M_FurSkeletal uses skeletal material support and uniform per-layer depth instead
of instancing-only custom data. The existing static materials are preserved.
The new actor requires the skeletal material, not M_FurAuthoringMaps. Existing
base actor methods became virtual/protected to reuse controls without duplicating
their parameter implementation. No source assets were replaced.

Fresh UE5.8 C++ build succeeded with one worker. UHT initially rejected a short
AllowedClasses path; corrected to /Script/Engine.SkinnedMeshComponent. API checks
passed for16 pose-sharing layers, unique depths, weather on every layer,32 cap,
source removal and rebuild cleanup. Final API job exited0, peak1.458GiB.

The first render caught a real reference-pose failure: inactive editor time
selection did not evaluate animation. Added editor-only RefreshPreviewPose:
TickAnimation(0), RefreshBoneTransforms and render-data refresh. It refuses game
worlds and does not select/replace animation assets. Subsequent render showed
two actual Tutorial_Walk_Fwd poses at0 and0.33sec,68 bones and16 layers. Maximum
bone movement39.99089cm, maximum follower/source bone-position error0cm. Both
captures were visually inspected. Render exited0, no shader/Python errors,
peak4.582GiB under6GiB, one shader worker, input desktop stayedDefault. This is
editor deformation evidence, not runtime FPS, native velocity or lighting parity.

Demo /FurAuthoring/Demo/FurSkeletal uses engine TutorialTPP/Tutorial_Walk_Fwd.
Saved animation uses OverrideAnimationData so it survives reload; original mesh
is hidden without propagation and AlwaysTickPoseAndRefreshBones is enabled.
Editor viewport may need Realtime or RefreshPreviewPose. Engine tutorial assets
are referenced, not copied into the plugin. No retail character is bundled.

Reports: recovered/skeletal-validation.json, skeletal-render.json and matching
*-job.json. The failed reference-pose log is retained separately. Scripts:
validate_skeletal_fur.py, capture_skeletal_fur.py, run_check.py. Final API rerun
saved the persistent animation setup and passed against the final binary.

Package: FurAuthoring-UE5.8-skeletal-preview.zip,0.3.0-preview descriptor,
33files,511335bytes. SHA256
bf28435f295ee5458fe0c89a790f0bfe814b16c9612cf819f147b3853890669c.
Every manifest file passed archive readback hashing. Prior previews preserved.

Next: recovered fur lighting and controlled Forge/UE comparisons. Still open:
in-editor paint brush, morph/cloth support, nonuniform-scale validation,
skeletal LOD/performance, native triangle rejection and temporal velocity.
Do not claim those features or full fur parity are complete.

## 2026-09-05: actual Ratchet head matched reference and recovered direct lighting

User asked why the UE fur looked unlike Ratchet, then authorized matching the
actual mesh/textures/camera/light. Implemented a private fixture at
unreal/fur/matched-reference; see its README and JSON evidence. Assets import
under /Game/FurReference, outside the distributable plugin content.

Seven shaded head parts: exact triangle counts and zero bounds error; native
compositing envelope excluded as in Forge. Fixed exporter binary FBX rejection
locally via node-preserving ASCII conversion. BC7 DDS importer rejection handled
by decoding every authored mip to RGBA8 DDS, preserving sRGB interpretation.
Full editor with NullRHI is needed for StaticMeshEditorSubsystem; commandlet
attempts and import failures are retained as diagnostic logs.

Authored packed fur control, color/alpha and specular response now drive the
private reference. ReferenceHairLighting.ush translates the verified G-buffer,
hair frame/lobes/response equations. Standalone SM5 compile and UE recovered-key
render passed. Recovered direct key is an emissive diagnostic with a fixed
light, NOT a production UE lighting/shading-model integration. Existing preview
ZIPs have not been replaced; no retail assets are bundled into them.

Images: matched-reference/forge-unlit.png, forge-lit.png, ue-unlit.png,
ue-recovered-key.png, and ue-default-lit.png. Final cached baseline render passed,
exit 0, peak job memory 4.054 GiB; no Python/material errors, fresh report/images.
Unlit interior ear/cheek MAE 1.93/0.58 RGB8; recovered key 3.12/1.46. These are
limited interior comparisons, not full renderer parity. UE recovered-key job
exited 0, peak job memory 4.615 GiB, input desktop remained Default. Initial
two-view capture timed out after writing the unlit image; retained cold-cache
failure log. run_check now rejects script/shader errors and stale/missing
reference completion reports even if the editor exits zero.

Next: integrate recovered response with real UE scene lighting/shadows/probes,
then address shell silhouette/temporal coverage. Repeat controlled lighting
validation for sheep; sheep is not validated by this Ratchet fixture.

## 2026-09-05: scene lighting and artifact investigation

Added AFurLightingController: one real directional light drives recovered fur
direction, radiance and temperature. Selected casters use a bounded 512-square
orthographic SceneDepth map with 3x3 PCF. This is a plugin bridge, not native
VSM/Lumen/deferred integration. UE 5.8 build succeeded in 97.20 seconds with one
build worker. Reusable material creation now lives in plugin Content/Python;
the private fixture wrapper keeps extracted assets outside plugin content.

Fixed integer-only fractional-noise phase by porting the verified 32-sample
Forge Halton sequence and independent cycle. Also found SceneView.cpp silently
downgrades TAA to FXAA without a Realtime viewport. Captures now explicitly
enable Realtime and TAA with 32 warmup frames. HOWEVER the static interior-ear
high-frequency metric remains 5.6366 before versus 5.6830 after: no measured
artifact reduction. Do not claim the artifact complaint is resolved. Next
investigation should use ordinary viewport frame history rather than relying
on high-resolution still captures, then moving camera and skeletal velocity.

Added actual sheep fixture 959F9CE032472D83, 17,364 fur triangles, authored
9 cm length / density 3 / offset 0 / transmittance 0.2. All imported part counts
and bounds match. Fresh Forge no-environment reference and UE scene-light
captures live under sheep-reference; no retail asset goes into the plugin.

Save callback reentry/template-edit failures were fixed and retained as logs.
One final sheep Realtime attempt stalled during startup and was killed by its
deadline; retained sheep-reference/realtime-startup-timeout*. Latest recovered
job reports and scene-image-validation.json are authoritative for final runs.
All graphics jobs use an inactive private desktop, no sound, 10 FPS and a 6 GB
job cap. No retail game launch.

Remaining: resolve visible temporal artifacts, moving/animated history and
velocity, native shell LOD, scene-material wind wiring, environment/probes and
additional light types, self-shadow validation and editor painting workflow.
Existing wind-enabled materials remain; the new scene material has wetness but
does not yet apply wind deformation. Lighting-preview packaging gates require
successful Ratchet and sheep import/render reports and fresh Realtime captures.

Final retry succeeded: sheep root exit 0, peak job 3.937 GiB; Ratchet root exit
0, peak job 4.023 GiB. Both retained the Default input desktop. Image checks
passed for changed lighting and selected-caster shadows (14,807 Ratchet and
8,488 sheep pixels darkened). These checks do not establish artifact removal.
Packaged FurAuthoring-UE5.8-lighting-preview.zip, v0.4.0-preview, 533,347 bytes,
38 files; every manifest hash verified by archive readback. SHA256:
173a290a24d055f5c85dc313afd7d6f5e3890bb6daaadf1ba9a28242d23a769d.

## 2026-09-05 evening: frozen viewport root cause

Added FurViewportProbe ONLY to the private ValidationProject module, not the
plugin. It reads ordinary viewport pixels and checks the resolved view AA mode.
Initial viewport/report.json proves Realtime was false; all stationary and
camera-move images were byte-identical. Previous "Realtime TAA" JSON labels
described requested settings, not verified effective state; they are not TAA
validation evidence. Source: LevelEditorSubsystem.cpp:223-239 only removes its
own negative override for editor_set_viewport_realtime(True). It does not enable
Realtime. Inactive-window overrides also recur between editor callbacks.

The diagnostic now adds a temporary positive override, advances the persistent
viewport without focus, then reads immediately after the controlled draw. Slate
throttling is disabled only in this isolated test process, which remains capped
at 10 FPS and 6 GiB. No global engine configuration was changed. Final probe
build succeeded in 26.74 seconds. A prior SlateCore import-library link failure
was resolved by avoiding that dependency. Rendering failures are retained in
viewport/ and viewport-live/inactive-override-failure.log.

capture_reference_viewport.py tests no-AA, TAA, camera movement and settling.
verify_viewport_history.py requires live frames, effective TAA and lower static
frame-to-frame variation. Latest viewport-live/report.json and validation.json
are authoritative for the corrected experiment, not the older high-res labels.

Final live viewport tests PASSED for Ratchet and sheep, 24 ordinary frames each
at 2191x942 (the saved editor viewport size). Both runs resolved method 2 for TAA,
rejected frozen frames, and exited 0. Peak job memory: Ratchet 4.098 GiB, sheep
4.105 GiB; input desktop remained Default. Ratchet stationary RGB8 change:
2.636 without AA -> 0.643 with TAA (75.6% reduction); settled 0.667. Sheep:
4.567 -> 0.666 (85.4% reduction); settled 0.807. Both slow camera moves produced
actual changed frames. No skeletal deformation or quantitative ghost-trail test
has been performed in this pass. No recovered fur equations changed this turn.

Latest actual images: matched-reference/viewport-live/taa-3.png and
sheep-reference/viewport-live/taa-3.png. Legacy high-res capture now labels its
AA state as requested/unverified; packaging no longer treats that string as
proof of temporal filtering. The v0.4 ZIP is preserved, not silently replaced.
Next: validate skeletal motion/velocity and fast-motion ghosting, then integrate
wind into the recovered scene-light material and repeat wet/wind lighting tests.

## 2026-09-05: recovered wind and skeletal scene material

Public create_scene_fur.py now connects RFOffset to WPO using world normal,
tangent, wind direction, Unreal material time and actor wind controls. Zero wind
preserves the old world-centimeter extrusion. Optional skeletal=True uses the
pose-sharing component's ShellDepth i/count; it fixes the previous incompatible
static-instance-data input. No recovered lighting/coverage kernel was changed.
Existing materials are preserved; create a new name to get the new graph.
UseWindTimeOverride/WindTimeOverride are deterministic test controls defaulting
off; ordinary materials animate from Unreal time. README documents usage.

capture_reference_dynamics.py: engine tutorial skeletal character with white
textures, 16 shells, a 12-frame sampled walk, pose jump/settling and wet/wind.
Ratchet/sheep wrappers use private extracted fixtures. These assets and the
private viewport probe stay outside the distributable plugin. GPU tests used
effective TAA, an inactive desktop, no sound, 10 FPS and a 6 GiB job cap.

One skeletal walk run was stopped by the resource guard when available commit
fell to 7.989 GiB. Logs retained under dynamics-skeletal/guard-stopped*. The
limit was NOT relaxed. Retried after commit recovered to 22 GiB. Final jobs
exited 0: skeletal peak 3.968 GiB, Ratchet 4.093 GiB, sheep 3.996 GiB. All graphics
jobs have finished; input desktop remained Default.

verify_dynamics.py passed all three fixtures. Bone movement 39.991 cm and shell
following error <0.001 cm. All sampled walk frames changed. In one pose jump,
15,596 vacated pixels had mean residual 0.018 RGB8 and 3 pixels exceeded 10.
This does not prove native velocity or general fast-motion ghosting parity.
Ratchet/sheep zero-wind differences from prior live dry reference were 0.964 /
1.258 RGB8. Wind-time changes were 1.078 / 1.430 RGB8; wet changes 8.821 / 8.347.
Those image deltas include residual TAA variation. See recovered/DYNAMICS.md,
dynamics-validation.json and dynamics-*/report.json for complete evidence.

Packaged FurAuthoring-UE5.8-dynamics-preview.zip (v0.5.0-preview), preserving v0.4.
534,268 bytes, 38 files, all manifest hashes verified by archive readback.
SHA256 d63d59af468720e1ad87e5380e7067c43604d7eca7bac3565ce5cbb2d0dbba32.
No game assets are bundled. Latest weather images are recovered/dynamics-ratchet/
wet-wind.png and recovered/dynamics-sheep/wet-wind.png.

Next: continuous wind/animation history and velocity, dynamic/deforming caster
refresh and self-shadows, then environment/local-light integration. Static
selected-caster bridge and a sampled walk are not full renderer parity.

## 2026-09-05: continuous playback and animated caster shadows

FurLightingController now supports opt-in Refresh Animated Casters and a
1-30 Hz deformation refresh rate (default 10). It ticks in PostUpdateWork.
Actor/component transforms and visibility remain immediate invalidations;
explicit RefreshLighting also remains immediate. Target identity/rotation/scale
now participate in invalidation. GetShadowCaptureCount exposes actual capture
requests for diagnostics. Static scenes retain the default non-periodic mode.
Public controller build passed in 140.47 seconds.

Continuous testing exposed another private-desktop issue: the editor ticked
only time while background throttling was enabled, so animation stayed frozen.
The first failing log is continuous/time-only-failure.log. EditorPerformanceSettings
is not Python-exposed in this build. The private C++ FurViewportProbe now toggles
its CDO in memory with no PostEditChange or SaveConfig and restores it at shutdown.
The diagnostic rebuild passed in 100.48 seconds. This helper is not distributed.
One failed setup was also stopped by the commit reserve guard; limits were not
relaxed. Available commit was 15.78 GiB before the final retry. run_check now
wraps startup scripts with error logging and editor shutdown; that failure path
has not itself been exercised after the wrapper change.

Final continuous run: exit 0, peak job 3.950 GiB. Sixteen distinct animation
positions over 7.730 world seconds, wind override disabled (live material time),
maximum bone movement 74.590 cm, minimum adjacent-frame RGB8 change 3.600.
No manual pose stepping in this test. Effective TAA was verified for every image.

Final animated-shadow run: exit 0, peak job 4.107 GiB. Skeletal caster bones moved
13.997 cm with unchanged actor transform. Capture counts across unshadowed,
pose A, frozen pose B, live pose B, moved-out, disabled: 0,1,1,32,62,62.
The frozen control differed by 0.959 RGB8; live refresh changed 69,230 pixels
by more than 15 RGB8. Disabling shadows returned within 0.871 RGB8 of unshadowed.
The 512-square map is visibly coarse and fully occluded direct-only fur is black.
Do not call this native shadow quality or full lighting parity. Both private
jobs ended with input desktop Default; all graphics processes have finished.

Evidence: recovered/continuous/report.json, recovered/animated-shadows/report.json,
and recovered/stream-shadow-validation.json. verify_stream_shadows.py passed.
One continuous editor sequence and one skeletal caster do not establish native
velocity, all-speed ghosting, WPO fur self-shadowing or game runtime performance.

Packaged FurAuthoring-UE5.8-animated-preview.zip, v0.6.0-preview, preserving v0.5.
535,706 bytes / 38 files, manifest hashes verified by archive readback.
SHA256 94eebe4ce3b8609da67c1308eef198a5c24a717914a11440effbfd0d1ec45472.
No retail fixtures or private diagnostic module are bundled.
Next: WPO fur self-shadow validation, finer/softer shadow filtering and environment
lighting; native velocity and broad fast-motion temporal quality remain open.

## 2026-09-06 — v0.7 filtered shadows and self-occlusion checkpoint

Replaced whole-texel 3x3 PCF with a continuous bilinear comparison filter in
FurSceneShadow.ush. Nine bilinear taps are merged into 16 point depth loads;
no depth interpolation across occluders. Resolution remains 512x512. This
addresses snapping but does not remove coarse-map limits or make shadows
volumetric. No C++ change or editor rebuild was needed.

Fresh material /Game/FurValidation/Materials/M_FilteredShadow_ratchet_v1 was
created and used in both final tests to remove shader-cache ambiguity. Earlier
preliminary captures reused M_Dynamics; only the final reports are release
verification. No saved reference map was changed.

Verification: python unreal/fur/verify_filtered_shadows.py
- 10,000 random neighborhoods versus explicit nine bilinear comparison taps:
  maximum numerical error 2.220446049250313e-16.
- Filtered caster: frozen control error 0.9073 RGB8; disabled control 0.7958;
  70,919 pixels changed after skeletal deformation refresh. Capture counts
  [0,1,1,30,60,60].
- Actual fur actor selected as its own caster: 68,907 pixels darkened >15 RGB8
  relative to unshadowed; 2,568 pixels changed >15 after fixed wind deformation
  and explicit recapture. Capture counts [0,1,1,1,2,2]. Bias 0.05 versus default
  0.5 cm changes foreground mean by 9.848 RGB8: bias is significant.
- All 12 final frames ordinary live viewport, resolved TAA2, 2191x942.
- Both final jobs exited 0, peak job 4.067/4.086 GiB, private desktop, muted,
  10 FPS, existing 6 GiB job limit and 8 GiB reserve guards unchanged.
- No graphics jobs remain running from this work.

Artifacts:
- recovered/filtered-shadows/report.json and six PNGs
- recovered/self-shadows/report.json and six PNGs
- recovered/filtered-shadow-validation.json
- FurAuthoring-UE5.8-filtered-preview.zip, v0.7.0-preview, 536465 bytes,
  38 files, manifest readback hashes verified.
- SHA256 d59754b9bf8730384e9619f1a0af8264d4cf0b778ca7268ea9e359e40ed1287a

Limits: opaque masked depth-map self-occlusion, not strand transmittance or
native game shadow parity. The wind check uses a fixed material time; full
animated skeletal self-shadow quality remains unverified. Environment light,
Lumen/probes, native velocity and general ghosting remain open. No retail assets
or private diagnostics included in package. Earlier ZIPs preserved.

Next: ENVIRONMENT_NEXT.md records recovered source paths and integration tests
for anisotropic environment normal/reflection, cubemap mip response and BRDF LUT.
Implement an optional authored environment input and compare matched Ratchet and
sheep views. Do not call a single cube native probe/Lumen integration. Preserve
existing direct-only behavior when the environment is disabled.

## 2026-09-06 — v0.8 optional environment lighting checkpoint

Implemented an optional authored-cube/BRDF path in create_scene_fur.py and
export_reference_lighting.py / generated ReferenceHairLighting.ush. The exporter
now translates hair_environment_frame.glsl alongside existing response kernels;
matched-reference/lighting-provenance.json records hashes. RFSceneEnvironment
uses packed/decoded normals and strands, anisotropic environment frame,
roughness-dependent cube mip, RG BRDF lookup, both Fresnel responses, and
recovered diffuse/specular resolve. It is added separately from direct shadows.

API: create/create_scene_fur accept environment TextureCube and environment_brdf
Texture2D, both linear, both supplied or neither. Invalid missing/type inputs
are rejected before asset creation (stub-boundary check passed). Existing assets
remain preserved. Parameters: EnvironmentIntensity .6, EnvironmentMaxMip 5,
EnvironmentRecoveredAxes 0 (UE axes; 1 for Forge-oriented input). No environment
textures means the original direct-only graph. Set intensity 0 to disable.

Private validation inputs generated by prepare_environment_inputs.py:
- StudioCube: owned constant-face studio colors with six controlled mip blends,
  RGBA16F. This is not a physically convolved captured environment.
- PrivateBRDF: recovered RG half lookup from Forge fur_resources, padded RGBA16F.
  Kept under ValidationProject /Game/FurValidation/Environment, never packaged.
- Imports use TC_HDR and preserve mips; BRDF clamps U/V. Initial import logged a
  texture recompilation registration warning/error during property changes;
  final sampling verifies RGBA16F values. Factory now requests HDR up front.

Final jobs, ordinary live TAA2 viewport, muted private desktop, 10 FPS:
- Ratchet: eight captures, peak job 4.0718 GiB, exit0.
- Sheep: eight captures, peak job 3.9158 GiB, exit0.
- Cube/LUT diagnostic: one capture, peak job 4.0070 GiB, exit0.
Existing 6 GiB job and 8 GiB reserve limits were unchanged. No jobs remain.
The first sampling attempt hit Material.two_sided AttributeError and exited
cleanly; corrected to set_editor_property and verified M_EnvironmentSampling_v2.

Verification: verify_environment.py and verify_environment_sampling.py passed.
- Ratchet doubling ratio 1.99867, disabled error 1.2716 RGB8,
  shadow/environment independence error .00565 linear, wet change 3.8945 RGB8.
- Sheep doubling ratio 1.99364, disabled error 1.2704 RGB8,
  independence error .00577 linear, wet change 4.8789 RGB8.
- All 36 cube face/mip samples within 1.4861 RGB8 of source expected values;
  six BRDF coordinate samples within .8860 RGB8 (fixed gamma2.2 display).
- Screenshots/report JSON: recovered/environment-ratchet, environment-sheep,
  environment-sampling. Sampling constant faces verify axis order/mip values,
  not arbitrary within-face orientation or seam filtering.

Release: FurAuthoring-UE5.8-environment-preview.zip, v0.8.0-preview,
538289 bytes, 38 files, all manifest hashes verified by ZIP readback.
SHA256 a449c9aec3828c1b1dcd415a9ea7c7c5963b113817bd4ae4f2236188c7f0e14b
Previous releases preserved. No extracted assets or private tests bundled.

Limits/next: this is an authored cube option, not native Skylight, Lumen or
spatial-probe integration. No full game-lighting or matched Forge image-parity
claim yet. The tool still requires compatible user-supplied cube/LUT inputs.
Next provide an easier environment setup workflow, consider an owned LUT and
prefilter generation path with an explicit model, then compare identical Forge
and UE lighting inputs/cameras. ENVIRONMENT_NEXT.md records these boundaries.

## 2026-09-06 — v0.9 environment controls and matched Forge checkpoint

Implemented on AFurLightingController:
- Details: Override Environment, Enable Environment, cube, BRDF, intensity,
  max mip, advanced recovered-axis switch, and visible Environment Status.
- Blueprint SetEnvironment(Cube, BRDF, Intensity) applies immediately.
- No override is the default, preserving old manual/material-driven workflows.
- Overrides rebind after fur DMI rebuilds; invalid/missing inputs disable the
  contribution. Input validation requires linear cube/LUT and LUT clamp U/V.
- Turning Override Environment off restores parent environment parameters only;
  it does not restore earlier manually overridden DMI values. Weather survives.
- Incompatible target materials receive a status message. Existing artist
  materials are not rewritten. Compatible material/cube/LUT still required.

Build: recovered/environment-controls-build.log, success, one worker, 102.16 sec.
Fresh controller render/API test: capture_reference_environment_controls.py via
run_check.py; eight ordinary live TAA2 frames, exit0, peak job 4.0579 GiB.
verify_environment_controls.py passed. Rebuild image difference 1.6401 RGB8;
missing-input versus disabled difference .9953 RGB8. Recorded intensities
[0,.6,1.2,1.2,0,0,.9,.6]. Parent-default return preserved wetness .8.

Matched Forge work:
- capture_forge_environment.py uses the same owned StudioCube DDS and private
  recovered BRDF. Constant cube face pairs Y/Z are swapped for Forge axes.
- Fixed the previous perspective mismatch: Forge 60 vertical vs UE60 horizontal.
  New Forge projection uses horizontal60 at 2191x942. Camera yaw/pitch/distance/
  target match inputs.json for both fixtures and are asserted by comparison.
- Both outputs use gamma2.2, same unit key, environment intensity .6 and dry fur.
- Preliminary grid-background captures were replaced by final black-background
  captures, avoiding background contamination through sparse fur. This reduced
  error only slightly; sheep's mismatch remains.
- Forge main exits via SystemExit. Wrapper now catches successful exit so it can
  append accurate override metadata. Stock smoke resource labels reflect its
  default code path, not the actual overridden studio resource. The appended
  environment_comparison metadata and wrapper source describe actual inputs.
- run_forge_environment_check.py enforces private desktop, <=10 paint calls/sec,
  6 GiB job limit, 8 GiB physical/commit reserve, 240 sec deadline, below-normal
  priority and fresh completion marker. Final Ratchet/sheep runs exited0,
  peak job 2.0033/1.7527 GiB. Retail game was not launched.
- All graphics jobs finished; no processes left from these tests.

Comparison: recovered/forge-environment-comparison.json; captures under
recovered/forge-environment-{ratchet,sheep}/environment.png, compared to the
v0.8 recovered/environment-{ratchet,sheep}/key-environment.png (same material
and inputs, no controller override needed). Interior masks derive from UE's
positive environment response and are eroded four pixels to limit edge mixing.
Ratchet 363576 pixels: mean absolute difference 5.9974 RGB8; mean RGB
Forge [153.88,106.61,59.13], UE [152.73,105.42,58.31].
Sheep 567371 pixels: mean absolute difference 12.5294 RGB8; mean RGB
Forge [114.89,107.02,104.66], UE [102.71,94.48,92.67].
These are scoped image differences, not parity percentages. Non-fur materials,
normal import/raster/temporal paths differ. Constant cube faces cannot establish
within-face orientation/seam behavior. Full native scene lighting remains open.

Release: FurAuthoring-UE5.8-controls-preview.zip, v0.9.0-preview, 542296 bytes,
38 files, ZIP manifest readback hashes verified. Includes freshly built binary.
SHA256 f0fb550ddb8e092b336065a42f9d3a483d98df4351449dacb2bc0f70a4bdfc6e
Older releases preserved, no private or game assets bundled.

Next: isolate sheep's remaining darkening with matched direct-only versus
indirect-only captures and inspect material/control decode, shell depth/AO and
normal response. Do not hide it with an arbitrary intensity/albedo multiplier.
The authoring workflow still needs compatible material creation and owned
BRDF/prefilter generation to remove manual source-data setup entirely.

## 2026-09-06 — user-marked ear contour investigation

User confirmed contour lines and marked Ratchet's lower ear rim. This takes
priority over the sheep brightness trace. Added private
capture_reference_ear_contours.py and run_check entry; no production shader,
actor defaults, saved scene or release ZIP changed.

Diagnostic captured lit32, unlit32, unlit16, unlit64 and base-only (one shell,
zero length). First run spent most of its 300-second budget in editor startup
and compilation; guard stopped it at deadline, peak4.0052 GiB. One retry reused
the compiled material and exited0, peak4.0591 GiB. All five final snapshots have
live TAA2; no graphics job remains. Existing resource limits were not raised.

Images/report: recovered/ear-contours. Unlit material removes fur lighting but
keeps recovered coverage and wet-albedo path. Base-only isolates original mesh
silhouette. Merely increasing shell count is not demonstrated as a clean fix:
64 layers thicken the dense envelope and push its visible transition outward.
No claim that this run proves a unique cause for every marked contour.

Supporting measurements: the shared 32-slice texture has fully opaque texel
fractions .819/.689/.600/.471 at slices0/1/2/4 (mip0). Near-grazing native shell
availability reaches1, so UE's lack of view-dependent availability is not by
itself an explanation for the same rim artifact in Forge. Both use discrete
surfaces and dense inner coverage. ear-edge-profile.json records a mean
luminance profile relative to the base silhouette over x1450..1629. It is an
edge-transition diagnostic, not an objective contour-quality score.

Also found: current matched Forge comparison explicitly disables contact-depth
and fur denoise passes. These are material-lighting diagnostics, not a complete
retail fur composite. Need test their contribution before altering shared
recovered material equations. Next isolate rim coverage/compositing; do not
ship doubled shell counts or arbitrary global blur as a claimed parity fix.
See EAR_CONTOURS.md. Artifact is not fixed yet.

### September 6 — ear post-processing and depth diagnostic

Completed Forge contact-only, denoise-only and combined captures, all exit0
near2GiB. None demonstrates clean contour removal. Added optional private
--shell-depth albedo diagnostic; preserved geometry/coverage. Its first process
failed before capture (3221226505,1.3401GiB); corrected GLSL int condition to
explicit comparison, retry exit0 peak2.00684GiB. No jobs remain and no resource
limits changed. Lower ear shows nested shell-depth bands with outer coverage
beyond them; supports shell-envelope hypothesis, not a unique pixel-level cause.

New compare_ear_post.py creates recovered/ear-contours/comparison.html and
post-comparison.json from five preserved captures, including source hashes and
actual pass settings. EAR_CONTOURS.md has metrics, limitations and next trace.
No production shader or ZIP change; contour remains unresolved. Next isolate
continuous depth versus authored control/length, using captured-draw parity
evidence before any alteration to recovered material coverage.

### Ear geometry follow-up — user preferred the post comparison

Preserved five-panel comparison. Added diagnostic --geometry=fixed-spacing
and --geometry=uniform-length to private Forge capture and guard runner.
Both tested with contact+denoise enabled, exit0, peak2.00225/2.00291GiB.
Neither clearly removes the rim. Uniform length introduces fur near eye and
headgear and is not a valid replacement for authored control. No production
changes. New recovered/ear-contours/geometry-comparison.html and .json verify
matched camera/model/LOD/size/temporal count/post settings and retain hashes.
All three Python scripts parse. No graphics jobs remain. Next trace native
temporal edge reconstruction from saved capture evidence; avoid further
arbitrary shell-count/length tweaks. EAR_CONTOURS.md records limitations.

### Ear temporal audit and background input — September 6

Read current temporal/raster documentation and source. Native raster migration
is already active (fresh report true); production TAA already has saved native
resource validation. Older pending-migration statements are stale. Do not
implement another filter. Concrete isolated input difference: background depth0
can win nearest-diagonal selection and produces inert disocclusion at the rim.

Added private --far-background depth-only isolation to capture/runner. Replaces
empty temporal opaque depth with100, keeps composed fur depth and all geometry/
coverage/shading. Both post passes remain active. Exit0, peak2.00246GiB, no jobs
remain. Fine silhouette changes but broad rim remains. MAE ear.7651/whole.1925
RGB8 is change only. New temporal-comparison.html/.json generated and matched
camera/model/LOD/size/temporalcount/post settings verified. Preferred earlier
comparison intact; production and package unchanged. Next coherent test needs
actual background depth/geometry/motion, not only this partial substitution.

### World-space backdrop and 24-frame camera test

Private ear_scene_fixture.py + --scene-sequence/--scene-background captures
12moving/12held frames with fixed opaque plane writing depth/velocity/stencil.
Initial plane was clipped by model-fit far range; invalidated those comparisons.
One readback assertion process exited3221226505 (~2.0071GiB), later raw probes
confirmed zero inputs. Corrected both test/control far clip to100. Final plane/
empty runs exit0 peak2.00404/2.00740GiB. Positive depth3.589195 and nonzero
velocity probes confirmed background rendering. No graphics jobs remain.

compare_ear_sequence.py passes schedule/background/probe gates, generates
recovered/ear-contours/sequence-comparison.html/.json (opt-in synchronized
playback, stops hidden). Shared lower-rim temporal stddev is7.22020 empty vs
11.01777 plane over12held frames, including post-motion settling. Real background
does not improve this test; do not ship as a fix. Preferred earlier comparison
preserved, no production/package changes. See EAR_CONTOURS.md for metrics and
scope. Next isolate original symptom in UE under equivalent scene/motion before
calling this Forge-specific input behavior the shared cause.

### Unreal ear camera counterpart complete

New capture_reference_ear_sequence.py + run_check entry ue-ear-sequence.
Earlier process disappeared during startup (no report); verified no editor
before fresh launch. Fresh run exit0 peak4.09613GiB, all48liveTAA2images saved.
Same camera orbit12moving/12held per empty/black thin cube backdrop, mapped
Forge plane center/normal, authored32shells, environment.6. No map save or
production/package changes. No graphics jobs remain.

compare_ear_sequence.py --ue validates schedule/AA/dimensions and creates
recovered/ear-contours/ue-sequence-comparison.html/.json. Ear stddev.90265/.90926;
lower-rim6.23671/6.32988RGB8 empty/backdrop. Broad contour remains; no demonstrated
background fix. UE phases/cadence differ, no recovered contact/denoise, no direct
backdrop GPUdepth readback; avoid cross-engine quality claims. Next register
original marked spatial boundary to base/outer shell contributions in UE.

### User says fix it all — still incomplete

Direct boundary isolation complete: new capture_reference_ear_boundary.py and
runner tag ear-boundary,4captures exit0 peak4.17745GiB. Ear ROI colored0redbase/
95293cyanouter. Outer-only retains ear contour; do not delete base geometry.

Tested nonbase opacity count compensation via additive helper
RFCountedCoverageWithMask in RecoveredFurAdapter.ush. Existing function wraps
with32, preserving current callers. Helper is NOT enabled by production builder;
private capture_reference_ear_resampling.py builds a test material and captures
reference32/raw64/normalized64. Exit0 peak4.15130GiB. Contour still visible;
not an accepted fix. Scalar transmittance invariant passed8.88e-16 under stated
independence assumption. New boundary-comparison.html/.json displays both tests.

No packaged release changes or default changes. No active graphics jobs.
Full user request remains outstanding: fix spatial shell boundary, then motion
and sheep regression, then package. Do not say all fixed. Preserve preferred
version, avoid another background/TAA/count-only diagnostic loop. See
EAR_CONTOURS.md for exact changes/limits and previous rejected hypotheses.

### Spatial spacing candidate rejected

Added private capture_reference_ear_spacing.py, run_check tag ear-spacing,
compare_ear_spacing.py. Rest-position variation<=.45shellstep, endpointsfixed,
layer order preserved (6363CPUcases). First run Python class-name error exited
cleanly; corrected to MaterialExpressionPreSkinnedPosition per installed headers,
fresh M_EarSpacing_v2. Retry exit0 peak4.13511GiB;3liveTAA2captures complete.
No graphics jobs remain. No production/default/package changes this turn.

Full/half strength changes grain but broad contour remains; reject candidate.
New recovered/ear-contours/spacing-comparison.html/.json. MAE1.24380/1.26880
measures change only. Preferred version preserved. No reason to run sheep or
motion regression for a candidate failing original symptom. Full fix request
still incomplete. Next use SAVED native render for registered ear-boundary
evidence; avoid another speculative shell/background/TAA tweak loop.

### Native thumbnail inventory follow-up
Checked 17 saved RDC headers without GPU/replay. All standard thumbnails
empty; 16 section tables have no extended thumbnail. Complete_capture section
parser fails on unexpected marker (extended status unknown). Script and report:
inventory_native_thumbnails.py, recovered/native-ear-audit/thumbnails/report.json.
No usable close-up obtained, no graphics launched, contour still unresolved.
Next obtain normal native game screenshot with large unobscured striped ear;
match preview camera to it. NATIVE_EAR_AUDIT.md gives reference requirements.

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

### Approved compatibility retry — Steam sign-in required
User explicitly approved optional UI restrictions off. Retry used private desktop,
6GiB cap, 8GiB reserves, below-normal priority, 300s deadline and mute monitor.
Steam PID39532 already existed before this turn; left it untouched. Owned game
PID43084 failed initialization. approved-start.png shows Failed to initialize
Steam. Current Steam connection log shows Logged Off. Do not bypass login.
Stopped owned game job and mute helper32904. No capture obtained. Peak job
1.80584GiB; input desktop Default before/after. Next: user signs into Steam,
then resume self-acquired reference; do not ask user to take screenshot.

### Steam black interface — shared global atom exhaustion suspected
Normal desktop ownership verified; restoring hidden CEF window showed black
(user confirmed). Clean Steam restart failed. Temporary verified launch flags
-cef-disable-gpu and -cef-disable-gpu-compositing also failed, no saved config
changed. webhelper log20:04:42: CreateOutputWindow / SetProp failed with Not enough
memory resources. Read-only audit_windows_atoms.py: global16296/16384 slots,
user1032, >33GiB RAM and commit available. Global entries predominantly start
nonalphabetic; attribution unknown. No atom deletions, no registry tweaks.
Stopped diagnostic Steam cleanly. Recommend save work and restart Windows;
do not automatically restart or resume graphics testing until resource baseline
is checked. Atom leakage can persist after originating app exits (Microsoft
About Atom Tables); do not blame Steam, Codex, Forge or renderer without trace.
Original native-ear capture request still pending. Recheck atom count after
restart, then sign-in and guarded native reference capture.

### Atom buildup explanation audit
Global count remains16296; approximately16124 entries contain opaque symbol-heavy
names, with no useful application-name attribution. Known markers (Chrome6,
Qt4,etc.) do not identify owner of dominant entries. Pattern aggregates only in
windows-atoms.json; no deletion or application launches. Suspect accumulation
of unreleased global atoms, not proven allocation source. Repeated capture and
preview sessions could have contributed; do not claim they are cleared of blame.
Need clean post-restart baseline and before/after counts per controlled workload
before resuming long capture sessions. Current source inspection found stable
RegisterWindowMessage name in private menu helper, not evidence of global leak.

### Atom guard added while waiting for Windows restart
Global count still16296 (88 free); no fresh baseline yet. Added read-only global
atom scan to tools/private_desktop.py before desktop creation, before resume,
and every5seconds while running. Operational reserve256free; no CLI bypass.
Reports initial count and current count; no names or atom mutations. Applies to
existing Forge/UE/private launchers using this helper. Guard boundary255/256
and preserved physical-RAM check passed. Actual trivial child preflight refused
(resource_guard, guard_stage preflight, no root_pid), atom-guard-preflight.json.
No graphics launched. Save work/restart Windows required before further capture;
then establish baseline and measure one workload at a time. Culprit unproven.

### 2026-09-07 recovered resource baseline and first isolated workload
Fresh global baseline143 (prior16296), user859. Saved atoms-before-forge-20260907.
Forge contact+denoise run completed exit0, peak2.00558GiB, private10FPS, same
existing guards plus atomreserve. Global143 before/after (no retained growth in
this run); user870 afterward. Does not rule out longer/repeated workload leaks.
Added optional --output-tag to capture_forge_environment.py (simple validated
name) so existing preferred images are preserved. New image/report in
recovered/forge-atom-baseline-20260907. Job in native-ear-audit.
Steam normal launch now creates visible UI and logs successful sign-in.
Native private game attempted next, no RenderDoc, no-save option, 240sec,
6GiB cap,8GiB reserves. Failed before capture with game memory-error dialog:
native-error-20260907.png. Reported peakjob6.35312GiB and process6.04486 despite
configured6GiB. Stopped own job immediately; inputdesktop Default. Do not claim
physical VRAM exhausted: job allocation limit may produce generic error.
Mute helper17916 stopped; no audio session was observed, no mute proof.
No native closeup obtained; production/package unchanged. Before another native
attempt inspect lower-memory launch settings; never increase cap speculatively.

### Low-memory native trial 2026-09-07
Direct -launcher route unexpectedly spawned helpers without setup dialog; stopped
owned low-settings-job (no settings changed there). Exact Graphics registry path
verified from retail binary and read under user identity. New supervisor
run_lowmemory_native.py backs up named DWORDs, applies 1280x720 windowed/low
textures/reduced scene settings, retains HairQuality4 and RT off, starts mute,
launches existing guarded private helper, then restores values on return.
Actual log confirms Windowed and Texture Quality Low. Game still fails startup
CreateHeap E_OUTOFMEMORY(0x8007000e); peakjob6.37394GiB,process6.03428 against
6GiB cap. At start VMEMavailable15180MB, at stop physical28.69GiB,commit22.93GiB.
This supports allocation cap as a suspect, not proof physicalGPU memory full.
No scene or ear capture. Existing private focus helper applied after verified
retail hash, Windows input desktop unchanged. No audio session appeared.
Stopped game and mute; lowmemory-settings-result.json restored=true, no
intervening changes. Saved lowmemory-native.log and black-window captures.
Do not repeat lower-quality trials expecting startup allocation to disappear;
no guard changes made. Further native work needs a justified startup memory
budget or verified allocation-reduction option. Fur preferred version preserved.

### Native heap static trace
See NATIVE_HEAP_TRACE.md. Exact error site and direct caller disassembled. Allocation size is descriptor-derived, not fixed6GiB. Reducedtextureheap parser sets3200 but no direct reader found; effect/units unverified, do not launch with guessed override. No game launched or limits changed. Next need failed runtime descriptor and allocation context. Native ear reference remains outstanding.

### Native failed heap descriptor recovered
2026-09-07: one same-cap background probe recovered a 2,046 MiB DEFAULT,
64 KiB-aligned, buffer-only heap request failing with 0x8007000e. Matching
fatal-handler return address and duplicate descriptors in error-dialog thread.
See NATIVE_HEAP_TRACE.md and recovered/native-ear-audit/heap-runtime-20260907.json.
Stopped owned game; settings restored, input desktop Default. No cap increase.
Added unique --tag to run_lowmemory_native.py with refusal to overwrite prior
runs. Probe sources in unreal/fur/probe_native_heap.cpp/.py. Buffer owner/policy
still unknown; exact-size code constant match rejected as unrelated bitmask.
Next recover producer/caller chain before another native trial. Ear contour
and native close-up remain outstanding; preferred fur and package unchanged.

### Global managed buffer owner confirmed
2026-09-07 heap-chain probe: StackWalk64 plus two matching resource descriptors
confirms the failed allocation belongs to global D3DBufferManager instance
0x1465A4260, initialized in renderer startup. Its sizing key is ManagedBuffer,
in reflected SystemMemory table at0x14684BC60. Budget feeds an arena; GPU
length derives from arena+0x500, so original budget value is not yet proven
equal to2,046MiB. Saved matching thread stack13,656bytes for offline analysis.
See managed-buffer-owner.json and updated NATIVE_HEAP_TRACE.md. Job stopped,
settings restored, Default input desktop, unchanged guards. No production fur
change. Next trace serialized SystemMemory source and arena capacity, then
choose a justified memory adjustment; no guessed override or new launch yet.

### Offline budget sizing and config scan completed
Corrected prior arena-capacity uncertainty: 0x1411FA31C stores rounded named
budget directly to manager+0x500, no arena subtraction. Heap rounds it again
to64KiB. Engine hashes verified ManagedBuffer AE669203/SystemMemory F0B87E85.
All1845 d/config assets scanned for names+hashes; no matches. Scan optimized
to decode each archive block once, bounded64MiB. No game launched, no config
or cap change. SystemMemory serialized source still unresolved; optional
EngineDebug/StickyConfig roots do not establish a valid budget override.
Next follow registry0x14684B5F8 population/deserialization or sample actual
loaded budget provenance under existing guards. See NATIVE_HEAP_TRACE.md.


### Sheep lighting mismatch traced and corrected � 2026-09-07
Returned to fur at user's request; native memory/startup investigation parked.
Direct/environment isolation measured 4.64/16.49 RGB8 error. Input probes found
normal, albedo, occlusion and raw diffuse cube sampling close; gloss/specular
were much higher in Forge. Source sheep response is BC1_UNORM_SRGB (72), but
Forge uploaded it as linear DXT1 because it consulted only the texture role.
BC7 sRGB already honored the explicit format. Corrected `_compressed_gl_format`
in external/RCRA-Forge/ui/viewport.py to preserve BC1/2/3 explicit sRGB tags.
Unreal was already correct; no shader intensity adjustment or UE asset change.
Four format regression cases passed (BC1/2/3/7, linear and sRGB role hints).

GPU capture confirms sheep specular binding now35917, control remains33777.
Environment-only MAE16.49 ->2.13; combined12.53 ->3.01 over same567371-pixel
interior mask. Ratchet combined PNG byte-identical before/after; MAE still6.00.
Actual before/corrected/UE visual checked: recovered/sheep-srgb-fix-comparison.png.
Reproduce with verify_sheep_srgb_fix.py; report sheep-srgb-fix-validation.json.
Input isolation reports/scripts retained. Initial environment probe withoutv2
was invalid (substring replacement zeroed both terms); corrected comparison
explicitly uses environment-v2. No native game launched and no package update
required because the correction is in Forge only.

One UE input capture aborted on WinError5 OpenInputDesktop during a Windows
desktop transition. Owned PID40380 absence verified. Archived original job/logs
as environment-sheep-inputs-aborted-20260907-*; stale running report annotated.
Fixed private_desktop.py final reporting to preserve original error even when
final desktop read fails; guard still aborts and kills its owned job. Retry
completed exit0 at4.10GiB, inputDefault; all Forge jobs exited0 below1.96GiB.
Memory/atom/time/focus guards unchanged. No user editor/process touched.

Next: resume remaining ear contour/temporal and scene-lighting parity work.
Sheep's previous large environment mismatch is resolved at the source-format
level; residual raster/temporal differences remain. Preferred UE0.9 preview
unchanged. Do not resume native heap detour unless essential to a specific
remaining fur verification.


### Fur texture fallback consistency and motion audit - 2026-09-07
Continued from the accepted sheep sRGB correction. Closed the same bug in
Forge's decoded RGBA upload branch: explicit sRGB source formats now retain
GPU sRGB decoding even for response roles. Upload cache signatures now include
DXGI format, so identical pixel bytes with changed format metadata re-upload.
Existing base-color hint and linear controls remain unchanged. Compressed
mip-chain and mip0 paths are covered alongside decoded uploads. 23 targeted
pytest cases passed using actual _upload_textures branches with mocked GL
calls; no Qt window or GPU process. Tests:
external/RCRA-Forge/tests/test_compressed_texture_color_space.py.
No new rendered comparison: this extends format handling to fallback paths;
the prior corrected compressed sheep and unchanged Ratchet captures remain
valid for the unchanged compressed mapping. UE preview package unchanged.

Reviewed EAR_CONTOURS.md through native evidence audit; all prior spacing,
count, backdrop and base-removal candidates remain rejected. Native close-up
prerequisite is unresolved; do not imply these texture fixes resolve contours.
Checked installed UE material compiler: HLSLMaterialTranslator.cpp:5278 uses
View.PrevFrameGameTime when compiling previous-frame Time. The production fur
builder uses MaterialExpressionTime with manual override disabled by default.
PreviousFrameSwitch exists for manually supplied history, but no evidence
justifies adding it to the normal clock. Manual override remains documented
for reproducible stills; this source audit is not a motion-vector GPU readback
or a native temporal-quality validation. No game or editor launched this turn.

Next useful animation work: validate actual fur deformation velocity output
and continuous wet/wind transitions, including sheep; keep native ear close-up
as a separate evidence prerequisite. Do not repeat rejected contour tweaks or
restart the game-memory detour merely to fill that reference gap.


### Sheep continuous wind/wetness and velocity control - 2026-09-07
Added private FurViewportProbe.SetVelocityView using the installed editor's
ChangeBufferVisualizationMode("Velocity"); Capture records selected velocity
view and velocity CVars. Built FurValidationEditor successfully with one
compiler worker. These are validation-project changes, not plugin features.

capture_reference_sheep_motion.py completed 37 frames with fixed camera and
live material clock: four still velocity frames, eight wind velocity, six dry
wind, nine wetness steps0..0.8, six wet wind, four final still velocity frames.
All live clock times advanced, camera stayed identical, manual override0,
lit captures use realtime TAA2, and velocity-view selection is verified.
Job exited0, peak3.96958GiB under6GiB cap; no game launched, inputDefault.

Engine velocity visualization is127,127,0 throughout the initial/final still
fur mask (567371 pixels). Wind changes37259..140933 fur pixels per frame,
maximum1RGB8 step; final still returns exactly to baseline. This demonstrates
quantized WPO velocity activity, NOT vector magnitude/direction accuracy or
native temporal parity. An initial >1RGB8 mean threshold was too coarse for
this display; report preserves that threshold result and separately records
actual changed-pixel counts and quantization limit. No material/velocity
setting was altered to manufacture a pass.

Wet transition completes all nine levels; wet-wind mean is5.0559RGB8 darker
than dry-wind over the fixed interior mask (different live wind times). Actual
renders visually show the expected broader wet clumps. No shell shortening
is implied. verify_sheep_motion.py reproduces measurements and creates paused
comparison.html plus overview.png in recovered/sheep-motion-20260907.
The top-right overview is an explicitly amplified difference plot, not a
render. Saved actual PNG frames and report.json are the primary evidence.

Next: quantitative floating-point velocity readback/controlled time comparison
before claiming deformation-vector accuracy. Ear contour native-closeup gap
remains distinct. Existing UE preview package and preferred material unchanged;
this turn validates animation behavior rather than claiming a contour fix.


### Raw sheep velocity readback - 2026-09-07
Private FurVelocityReadback.cpp adds a one-shot scene-view extension, filtered
to the requested editor viewport. PrePostProcessPass obtains scene velocity
through UE::FXRenderingUtils::GetSceneVelocityTexture, declares RDG CopySrc,
and reads FLinearColor with RCM_MinMax and gamma disabled. Stores float32 RGBA
plus dimensions/native format/world time. At most one pending capture; 4096
texture dimension cap. Renderer module dependency added only to FurValidation.
Build succeeded with one worker. No distributed FurAuthoring changes.

capture_reference_sheep_velocity_float.py completed still, wind-a, wind-b,
returned-still. Job exited0 at4.11271GiB under6GiB cap, inputDefault. Initial
command approval timed out and the execution session was lost before files
were written; confirmed state, retried once, then verified build success.
No native game launched. Existing guard settings retained.

Native velocity texture is G16R16, internal render1600x688 (not2191x942 display).
Readback preserved UNORM16 values as float32, not invented float precision.
verify_sheep_velocity_float.py uses installed Common.ush SM5 gamma decoding:
a=(encoded-32767/65535)/(.499*.5); ndc=a*abs(a)*.5;
render pixels=ndc*(width/2,-height/2). Cleared R=0 is invalid and excluded from
valid counts. Known-vector encode/UNORM16/decode roundtrip error1.89e-5NDC.
Prior fixed-camera fur mask resized nearest to render view, aspect checked and
further eroded;296277 pixels. Not a pixel-exact correspondence across TAA frames.

Wind means0.08127/0.16112 render pixels/frame; P95 .27829/.52783; max1.02461/
1.56784. Still/returned maxima .0001813/.0001884, zero pixels above .001.
Wind has255528/258394 pixels above .001,1440/1568 unique encoded R values;
thus prior 8-bit visualization hid meaningful signal. Raw .f32, sidecars,
decoded NPZ, validation.json, magnitude plot and comparison.html saved under
recovered/sheep-velocity-float-20260907. Actual plot visually inspected.
Existing sheep-motion playback links the measurements. No per-vertex ground
truth, direction-accuracy, frame-rate invariance or native parity claim.

Next use a deterministic previous/current deformation reference to evaluate
vector accuracy, rather than only production activity/magnitude. Native ear
closeup prerequisite remains outstanding and separate; avoid speculative
contour edits. Current preview package remains unchanged.


### Independent wind motion-vector accuracy - 2026-09-07
Completed two controlled private fixtures, no production material changes.
First: capture_reference_velocity_calibration.py applies known current/previous
WPO offsets to an owned camera-facing thin cube at99.95cm front depth. Cases:
zero, right0.01cm, right/left/up/down1cm. verify_velocity_calibration.py derives
screen displacement independently from FOV/depth and compares central64x64
raw G16R16 samples. All six pass0.01render-pixel tolerance, worst0.000545pixel.
Subpixel case predicted0.138633px, measured0.138267px. Validates decode, axes,
scale and small values. Calibration job exit0, peak4.04718GiB.

Second: capture_reference_fur_wind_accuracy.py invokes the unmodified production
RFOffset on the same owned plane. PreviousFrameSwitch supplies controlled
current/previous clock pairs1/1,1/.9,2.5/2.4,6.4/6.2. Fixed UV(.37,.61),
shell depth.75, length9cm, control length.5, strength.12, turbulence.2,
phase.1326904,radius1; normal/tangent match camera-facing plane.
verify_fur_wind_accuracy.py implements the scalar wind/interpolation and frame
bend independently in Python/NumPy, taking only the recovered64entry random
constant table from Forge. It projects current/previous displaced points with
perspective and depth change, then compares raw GPU velocity on central64x64.
All four pass0.01px tolerance. Max vector errors .00002884, .00064092,
.00091634, .00062152pixels respectively. Thus controlled production fur wind
previous-frame evaluation agrees with independent prediction to<.001pixel.

Artifacts under recovered/velocity-calibration-20260907 and
recovered/fur-wind-accuracy-20260907: actualraw .f32, sidecars, screenshots,
report.json,validation.json,comparison.html. Source/table and raw hashes saved.
Existing sheep playback/raw-motion pages link the new accuracy report.
This validates controlled uniform inputs and the recovered wind function, not
per-pixel varying mesh inputs, skeletal previous pose, fast-motion disocclusion
or native game parity. No contour fix implied; ear native-closeup gap remains.
No distributable plugin/package change: private diagnostics and verification.

Next important gap: previous-pose skeletal fur deformation under animation,
using these calibrated vector tools. Avoid repeating stationary wind activity
checks now that both magnitude and controlled equation accuracy are verified.


Wind accuracy capture cleanup note: all four readbacks and comparisons passed,
UE log records clean editor shutdown, but an owned helper PID4040 remained.
The original guarded job reached deadline and killed that helper; root exit
code was not sampled by the old runner. Do not label that original job exit0.
Peak4.03563GiB, final inputDefault. Numerical results are complete; job cleanup
is a separate issue. Added optional --exit-with-root to private_desktop.py,
enabled only by run_check.py (direct UE executable). Generic launcher default
still waits for the whole tree. Root completion uses WaitForSingleObject;
finally still kills every owned job helper. No guard bypass or cap increase.
Hidden Python parent/30-second-child regression exited promptly with code0,
remaining helper IDs recorded and verified absent. See
recovered/helper-exit-validation-20260907.json. First helper trial used a
relative executable and was rejected before launch; corrected absolute path.

### Skeletal fur velocity activity and settling - 2026-09-07
Added capture_reference_skeletal_velocity.py and verify_skeletal_velocity.py.
Runs existing tutorial skeletal fixture with production recovered fur material,
16 leader-pose shells, no wind. Live animation enabled for two samples, then
stopped. Final capture hides source component without propagating to followers,
so visible velocity comes from shells. Earlier source-visible trial also passed;
final artifacts replace that trial and are the source-hidden results.

All four activity/settling checks pass. Bone-follow error zero for all shells;
sampled bone motion86.1404cm. Still/stopped have zero pixels above.01render px,
max residual .00018250/.00015517px. Walking has71805/71564 moving pixels,
max155.8464/127.8811px; these are measured values, NOT calibrated skeletal
accuracy or fixed-delta comparisons. Slow private desktop animation timing
varies; independent previous/current vertex prediction remains necessary.
Report, raw float32 readbacks, screenshots, hashes, heatmap and comparison.html
under recovered/skeletal-velocity-20260907. Heatmap visually inspected; white
saturates at5px and black still panels mean no measurable motion, not missing
renders. Native clips, fast-motion ghosting and skeletal vector accuracy remain
unverified. Source hidden only transiently; no production plugin/package change.

Final guarded job exited0, peak4.09839GiB under6GiB, muted inactive desktop.
No retail game launched. Next: controlled previous/current skeletal pose
projection, then combined skeletal+wind temporal quality. No parity claim.

### Controlled skeletal accuracy and combined wind/wetness - 2026-09-07
Completed requested follow-up without native game or foreground graphics.
Private FurSkeletalProbe.cpp adds SaveSkinnedPose (LOD0 world vertices/indices,
engine CPU skin matrices/weights, <=100000 vertices) and FlushPoseUpdates.
One-worker validation-module build succeeded50.98s. Not distributed plugin.

capture_reference_skeletal_accuracy.py isolates one actual production
leader-pose shell with opaque zero-WPO material, source hidden, LOD0 forced,
fixed camera, AA off. Controlled animation positions0,.01,.02,.02. Previous and
current CPU skin geometry is saved before raw G16R16 readback, with explicit
end-of-frame update flush before draw. Independent Python perspective-correct
triangle rasterization/depth selection predicts previous screen coordinates.
Conservative triangle interiors plus erosion select3093-3247 pixels per case.
All passP95<.05px tolerance. Moving P95 errors .00187557/.00192062px,
maximum .00530594/.00622140px; every sampled pixel<.05px. Still/settled
max .00001191px. Prediction uses engine CPU skin matrices, so this validates
GPU skin history/projection relative to CPU reference, not an independent
animation decoder. Wind/fur WPO excluded intentionally for this isolation.
Raw/CPU geometry hashes, NPZ predictions, accuracy.png and comparison.html in
recovered/skeletal-accuracy-20260907. Heatmap visually inspected. Job exited0,
peak4.13518GiB under6GiB.

capture_reference_skeletal_wind.py tests all16 full production fur shells,
source hidden, live tutorial animation and wind, TAA enabled. Eight states:
still,walk-only,walk-wind-a/b,wet-walk-wind-a/b,wind-only,stopped. Bone follow
error zero, finite raw velocities throughout. Active stages all produce motion;
wind-only58426pixels>.01px and max.482156px while skeleton paused. Initial/final
zero pixels>.01px; max .00018565/.00018250px. Wetness parameters verified0/1,
wind0/.12; dry/wet snapshots use different poses and are not controlled color
comparisons. Actual wet fur render visually inspected; tutorial mesh joint
separations visible, no claim of seamless character topology. All activity and
settling checks pass. Artifacts/raw hashes/screenshots/report in
recovered/skeletal-wind-20260907; links controlled accuracy and prior report
links this follow-up. Job exited0, peak4.08695GiB, inputDefault. No lingering
capture session, no game launched, no production package change.

Next remaining temporal gap: fixed-time combined skeletal+wind per-vertex
accuracy and fast-motion/disocclusion sequence quality. Existing tests establish
skeletal accuracy in isolation plus combined activity/settling; do not claim
combined exact accuracy, no ghosting, native clips, or full parity.

### Plain dry fur priority - 2026-09-07
User explicitly requires finishing plain dry fur first. Further wind/wetness
feature work is paused. Added DRY_FUR_COMPLETION.md to keep real completion
gates separate from isolated diagnostic passes; dry fur is NOT finished.

Corrected ASkeletalFurAuthoringActor: RebuildFur normalizes the public requested
shell count to its supported1..32 range, and UpdateParameters binds
RecoveredShellCount from the actual SkeletalShells.Num(), including deferred
Blueprint count edits before rebuild. Existing16/32-shell appearance and depths
are unchanged. Existing validate_skeletal_fur.py now checks64->32 reflected
count, all depth/metadata values, deferred8 request remaining32 until rebuild,
and subsequent8-layer geometry. README documents this behavior and accurately
qualifies the preceding CPU/GPU skeletal accuracy test.

One-worker C++ build succeeded,4actions,255.74s total including build-lock wait.
Editor API regression did NOT run to completion: skeletal-api-job.json reports
deadline_reached at180s during startup, peak1.02994GiB under4GiB. No runtime
pass claimed. Existing preview ZIP preserved rather than mixing new source with
unvalidated release claims.

Prepared capture_reference_dry_motion.py plus sheep wrapper and
verify_dry_motion.py: zero wetness/wind, TAA2,30cm rapid rigid translation,
before+12movement samples+settled image. Measures newly uncovered black
background excluding final geometry with8pixel margin; no assertion of exact
engine-frame cadence. Captures/report/image slider are intended for visual
review, not blanket no-ghosting certification.
First Ratchet launch was stopped by resource reserve: available commit7.639GiB
below8GiB; peakjob.91382GiB, no frames produced. Read-only recheck later found
33.3526GiB available commit and36.0494GiB physical. Limits unchanged.
A second Ratchet capture attempt is in progress at this checkpoint entry; final
status must be read before reporting success. No sheep capture started yet.
No retail game, focus takeover, global temporal blur, or speculative ear fix.
Ear remains pending an applicable native close-up; saved native raster agreement
is not evidence for full close-up visual parity.

Dry-only follow-up outcomes: first Ratchet retry exited0 peak4.02764GiB and
initial sheep capture exited0 peak4.07576GiB. Visual inspection found the
fixture moved only fur-bearing geometry, leaving eyes/helmet behind. Do not
accept those as whole-character motion results. Corrected fixture translates
all imported static character parts with fur by15cm (instead of30cm).
Corrected Ratchet exited0 peak4.08747GiB; actual reduced move-0 image visually
inspected: head/eyes/helmet aligned. Recovered/dry-motion-ratchet-20260907 holds
final corrected report/images and comparison. CPU verifier only accepts the
new15cm whole-character reports, refusing stale initial sheep30cm evidence.
Initial verifier SyntaxError from Windows cp1252 em dash fixed by UTF-8 script
encoding; HTML output now explicitly UTF-8 too.

Corrected sheep job reached300-second deadline during editor startup, peak
1.03584GiB; it produced no new report. Sequential runner stopped on failure,
so the scheduled retry of validate_skeletal_fur.py DID NOT launch. Prior API
180-second timeout remains the only runtime result for the count correction.
No active capture/build session remains. Do not retry launches repeatedly while
startup is stalling, raise resource/time guards, or modify unrelated user apps.
Dry completion remains open: corrected sheep motion, actual count API test,
ear/native-closeup acceptance, broader dry animated silhouette quality and
release validation. Source fix is compiled, NOT runtime-validated or packaged.

### Verified count fix delivery and startup isolation - 2026-09-07
User asked to hurry and get plain dry fur working. Still no full dry-fur
completion claim. Verified installed ProjectDescriptor supports
DisableEnginePluginsByDefault. Minimal private project loaded3engine plugins
instead of247; validate_skeletal_fur.py completed successfully, including
64->32 reflected count and material metadata matching built geometry through a
deferred8-shell request/rebuild. skeletal-api-job exited0, peak1.11061GiB under
4GiB. run_check now requires a fresh skeletal-validation.json and checks Python
errors, avoiding an old report being mistaken for this pass.

Minimal render configuration invalidated material shader cache; its dry sheep
run hit300s while compiling engine material shaders, peak2.32433GiB. Restored
cached full plugin configuration for renders/imports; subsequent sheep startup
still hit300s, peak.89352GiB, no new capture. No further launch loop. Memory,
commit, disk, FPS, private-desktop and deadline guards unchanged. No game or
other user process stopped. Source inspection found platform config preloads,
but no demonstrated safe engine-local switch; engine code not modified.

Persistent ValidationProject.uproject is back to its normal full rendering
plugin configuration (DisableEnginePluginsByDefault=false). run_check uses
minimal plugins only during non-import API checks, full cached configuration
for render/reference import, and restores original project bytes in finally.
This avoids leaving user-visible project startup on a cold shader configuration.
No capture/build process remains active.

Delivered FurAuthoring-UE5.8-shell-count-fix.zip (0.9.1-preview),543056bytes,
39files, SHA2566f5ec59701a05a657327acf620c60bb502d767d34919c1f09fc7691f29ec10e3.
package_shell_count_fix.py verifies original controls-preview SHA and proves
SkeletalFurAuthoringActor.cpp is the ONLY changed plugin C++ source. Patches
that source plus built DLL, descriptor, manifest and explicit maintenance notes.
All previous shader/content bytes preserved. Every archive manifest hash checked
on readback; base preview remains untouched. This is runtime-verified count
maintenance, NOT a finished dry-fur release. Full --dry-maintenance packaging
route prepared separately remains gated on both corrected dry-motion captures;
it has not been run and its gates were not relaxed for the narrow count patch.

Remaining: corrected sheep whole-character motion capture, native-ear closeup
acceptance, general dry animated silhouette/ghosting quality and full dry
release gates. Weather feature work stays paused. Known Ratchet rigid-motion
result remains valid; editor startup has only been resolved for API checks.


## Dry lighting continuation, 2026-09-07
Optional directional fill/rim inputs added to controller and new scene-fur materials using recovered RFSceneDirect. Single-worker C++ build, SM5 compilation and eight NullRHI binding checks passed. Ratchet rendered change passed: rebuild1.248RGB8 MAE; disconnect0.987. Sheep initial rebuild5.148 failed3RGB8 threshold; disconnect1.183. Signed mean change was under0.15RGB8 per channel, suggesting sampling variation. Same-light held frame and scalar/light snapshots added for isolation; no sheep acceptance or new ZIP yet. Previous follow-up was interrupted before output. Guarded follow-up running.
Official native photo-mode closeups acquired and inspected: recovered/published-native-reference-20260907/comparison.html. Forge yaw150/pitch5 inspected; camera/pose/lighting unmatched. No native ear parity claim. Corrected sheep dry-motion attempt left invalid job report after interruption; no accepted new motion result. Other UE5.7 tasks remain untouched.

Sheep follow-up completed: same-light held MAE5.2219, held-to-rebuild5.1779, identical parameters/lights and mean signed change under0.038RGB8. Binding/rebuild accepted relative to control, but static temporal quality remains FAILED; no tolerance raised for that gate. Dry-lighting comparison saved at recovered/dry-lighting-20260907/comparison.html. Corrected sheep dry-motion guarded retry running.

Corrected whole-sheep15cm dry-motion capture completed, exit0, peak3.976GiB; actual moved image inspected and parts aligned. Newly uncovered mask76511 pixels;0..8 above8RGB8 in saved moving samples, settled0. Ratchet remains191360 mask/0 residues. Cadence not frame-locked; no full-motion parity claim. Updated DRY_FUR_COMPLETION.md and dry-motion-verification.json. No owned captures left running. Latest source lighting changes are built/tested, no new ZIP. Next dry gaps: bright wool temporal noise, native ear/scene acceptance.

Dry temporal follow-up: identified 32-frame reset in create_scene_fur versus recovered five-step phase (hairScreenPhase multiplies by0.2). Candidate uses joint period160 with32 Halton values. verify_dry_temporal_schedule.py isolates ideal fractional spatial seeds: mean coverage error2.4731% to0.2111%, max10.5% to0.875%. This is a schedule test, not GPU/native parity. New separate M_DryMultilight_sheep_cycle160_v1 material and dry-cycle160-sheep output are rendering; original material assets unchanged. Production builder edited to160 pending visual acceptance; no ZIP. Recovered HairDenoise requires per-pixel strand, normal, depth and mask before TAA, absent from the current UE unlit-material bridge. Do not call a generic blur the native denoiser.

Temporal160 candidate GPU run completed, exit0, peak4.531GiB; actual image inspected. Same-lit pair MAE5.2185 to4.5599; rebuild4.7320, disconnect1.0400. Mean RGB changed under0.104; no obvious shape/color regression in inspected stills. Single-pair observation, not a generalized13% noise guarantee. Still fails3RGB8 temporal quality gate. Builder retains160 as schedule correctness correction; no binary rebuild needed for Python material generator, no new ZIP or existing asset rewrite. Comparison: recovered/dry-cycle160-sheep/comparison.html. Native hair filter requires missing per-pixel strand/normal/depth/mask path in UE. Next implementation must supply those buffers and filtering before TAA; do not replace with generic blur. No owned jobs running.

Recovered filter implementation: RecoveredFurDenoise.ush arithmetic port, FurDenoise.usf compute shader and AddRecoveredFurDenoisePass RDG API compiled. Seven synthetic GPU checks PASSED (native truncation, non-fur passthrough, directional edge filter, foreground depth rejection, mask exclusion, inactive tiles, invalid inputs), exit0 peak4.492GiB. First private editor launch failed on missing Platform.ush, corrected; subsequent test passed. This is NOT connected to live character surfaces. New MaterialExpressionFurSurfaceOutput exposes decoded normal/strand. Installed UE5.8 MIR emitter functions are not exported to plugins; node uses supported legacy compiler and new data materials disable only their own new-generator flag. Build passed22sec. Optional surface_outputs=True path in create_scene_fur and private sheep compile/render check running. No preview ZIP or parity claim.

Fur surface clean check completed, exit0 peak4.551GiB. Both inputs connected, legacy compiler,24 shader types and737 pixel instructions, no compile errors in clean run. Initial creation errors were intermediate unconnected graph nodes. GetStatistics caused Slate reentrancy and repeated key rows; do not count sequence as clean lighting regression. Harness now keeps busy through stats; material/shader check accepted separately in fur-surface-output-validation.json. Native filter remains unhooked from live characters. No owned jobs running, no new ZIP.
