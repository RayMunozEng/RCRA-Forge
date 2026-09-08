# Fur Authoring for Unreal Engine 5.8

A static-mesh fur authoring plugin. Choose a mesh, adjust the fur in the Details panel, and drive weather from Blueprint. The original source mesh is not edited. No Ratchet, sheep, or other game assets are included.

## Use

1. Extract the `FurAuthoring` folder into your project's `Plugins` directory and enable it. The release ZIP includes a Win64 editor binary for UE **5.8.0 build 55116800**. For another build or platform, rebuild your project's Editor target from the included source.
2. Enable **Show Plugin Content** in the Content Browser. Open **Fur Authoring Content / Demo / FurMaps** for the mapped fur example. The old **FurDemo** remains available for comparison.
3. To use your mesh, place a **Fur Actor**, assign **Source Mesh**, then click **Use Mapped Fur** in Details. This selects `M_FurAuthoringMaps` and enables the **Fur / Maps** controls. The mesh needs UV0 and usable vertex normals. All its material slots receive the fur material; use a separated mesh for fur-only regions.
4. Try **Short Fur Preset** or **Wool Preset**, then adjust Length, Shell Count, Root/Tip Color and Roughness. Under **Maps**, set **Recovered Density** and **Groom Strength**. Assign optional Length, Density and Groom maps as described below. Shell count is synchronized automatically. The older Density, Strand Width and world Groom controls belong to the legacy material.
5. Enable viewport Realtime to preview wind. **Wind Direction**, **Wind Strength**, **Wind Speed**, and **Wetness** are editable. Blueprint **Set Weather** updates wetness and wind strength without rebuilding the shells. After setting other Blueprint properties, call **Rebuild Fur**.

If rebuilding the material from source, enable Unreal's Python Editor Script Plugin and execute `Content/Python/create_fur_material.py` in the editor. It preserves an existing material rather than overwriting artist edits. The builder uses [Custom Material Expressions](https://dev.epicgames.com/documentation/unreal-engine/custom-material-expressions-in-unreal-engine) to call the plugin's shader include.

## Control maps

Use linear textures: disable sRGB and use uncompressed RGBA (Vector Displacementmap compression). Do not use normal-map compression for grooming; it changes the stored channels. The tool does not modify your texture settings automatically.

| Map | Channels | Meaning |
| --- | --- | --- |
| Length Map | R | Black gives zero fur length; white gives the actor's full Length. |
| Density Map | R | Black removes fur coverage; white keeps full coverage. The base surface remains visible. |
| Groom Map | RG | UV tangent-space direction, with (0.5, 0.5) neutral. Groom Strength controls its influence. |

Unset maps use full length, full coverage and neutral grooming. Clearing a map restores those defaults. Maps wrap in UV0. Length changes are limited by source vertex spacing, so use sufficient mesh resolution for detailed masks. Density masks affect coverage rather than changing the pattern's UV scale. Imported maps are supported; there is no in-editor paint brush yet.

Blueprint **Set Fur Maps** changes all three bindings without rebuilding shells. Call **Use Mapped Fur** first. After changing other actor properties from Blueprint, call **Rebuild Fur**. Wetness and wind remain available through **Set Weather**.

## Animated meshes

Place a **Skeletal Fur Actor** and set **Animation / Pose Source** to the
character's skinned mesh component. In Blueprint, call **Set Pose Source** with
your character's Mesh component. **Use Mapped Fur** selects `M_FurSkeletal` on
this actor. The static Source Mesh field is unused.

The layers share the source's evaluated bone pose, rather than running separate
animation graphs. They attach to its component and inherit its movement. The
same maps, color and weather controls apply. Defaults are16 layers; skeletal fur
is capped at32. Rebuild clamps the displayed count to that limit. Material
shell-count metadata always describes the currently built layers; a deferred
Blueprint count edit takes effect when Rebuild Fur is called. Rebuild after
changing layer count or material. Removing the
source removes the generated layers; rebuilding replaces rather than accumulates
them. Changes to the source mesh are detected on tick.

The original mesh remains under your control. To hide it beneath the fur, hide
the source component without propagating visibility to its children, and set
its Visibility Based Anim Tick Option to **Always Tick Pose and Refresh Bones**.
Otherwise hidden-source animation can stop updating. The supplied editor demo
**FurSkeletal** uses Unreal's tutorial character with these settings. Enable
viewport Realtime to preview animation. No game character assets are bundled.
If an inactive or paused editor viewport has not evaluated the selected pose,
click **Refresh Preview Pose**. This evaluates the current source animation for
an editor snapshot; it does not drive animation in game worlds.

This is a pose-sharing preview with repeated skeletal draws. Morph targets,
cloth, large crowds, nonuniform scale, runtime performance, skeletal LOD
transitions and fast-motion ghosting have not been validated. Controlled
zero-WPO skeletal motion matched CPU-skinned surface projection within
0.0063 render pixels at sampled triangle interiors in UE5.8/D3D11. This
is an isolated skinning check, not full dry-fur temporal or native parity.

## Rendering scope

The mapped material uses the recovered procedural layer array, grooming, wet coverage and wind equations with instanced static-mesh shells. Unreal's Default Lit material supplies scene lighting. The original `M_FurAuthoring` material uses the earlier procedural-cell prototype. Neither is the complete Rift Apart renderer or Unreal Groom strand hair. The Wool preset does not reconstruct sheep's authored curly base surface.

In-editor painting, shell LOD, native fur lighting/triangle rejection and matched temporal velocity remain future work. The recovered pre-TAA denoiser is available for materials created with Fur Surface Data; enable it with `r.FurAuthoring.Denoise 1` or the Blueprint-callable `Set Recovered Fur Denoise Enabled` function. Query `Is Recovered Fur Denoise Registered` after engine initialization when diagnosing setup. It is disabled by default while fractional native mask composition and broader viewport/platform coverage remain incomplete. UV seams/stretching affect fur. Long shells can show layering at low shell counts. Each shell repeats the source triangles; start with modest meshes and 16–32 shells. Keep gameplay collision on the source actor. Use non-Nanite source meshes for the validated path. Extreme actor scaling requires inspection.

## Validation

The isolated `unreal/fur/ValidationProject` is the UE 5.8 build and editor test harness. `unreal/fur/validate_in_editor.py` creates the material and demo map and checks shell counts, presets, weather clamping, and source removal. Fresh results are recorded in `unreal/fur/editor-validation.json` when that script completes. Do not interpret source creation as a successful engine build or rendered result; see the accompanying checkpoint for the completed gates.
# Recovered material experiment

The workspace now also contains `M_FurRecovered`, a separate transfer of the
verified Forge shell-volume, grooming, wet coverage and wind kernels. See
`unreal/fur/recovered/README.md` in the repository for evidence and remaining
boundaries. Versioned preview archives preserve the earlier checkpoints.

The actor now synchronizes `RecoveredShellCount`. With **Use Map Controls**
disabled, existing recovered material instances retain their density/groom
parameters. With it enabled, actor Recovered Density and Groom Strength drive
those values. The prototype's Density, Strand Width and world Groom controls do
not drive this new path. It uses fixed-depth static shells and UE Default Lit.
Do not treat it as complete native parity or a finished authoring workflow.

## Recovered scene-lighting preview

`Content/Python/create_scene_fur.py` provides `create_scene_fur(name, albedo,
control, specular_response, settings=None, skeletal=False)` for user-owned textures. It creates
a masked recovered-fur material under `/Game/FurAuthoring/Materials`, preserving
existing assets. Control is linear RG comb direction, B length and A occlusion;
response RG supplies gloss/specular in the texture's declared color space.
Optional settings are `length` (cm), `density`, `offset` and `transmittance`.
The recovered 32-slice procedural field remains shared plugin content.

Assign this material and a non-Nanite source mesh to a **Fur Actor**. Match its
Length to the desired centimeters. Enable **Use Map Controls** to drive
Recovered Density and Groom Strength (offset scale) from the actor. This path
uses the supplied packed control texture; the separate length/density/groom
map slots belong to the earlier mapped material. Wind Strength, Wind Speed and
Wind Direction now drive the recovered shell-bending function in this material.
Wetness drives the recovered coverage, color and gloss response; it does not
shorten shells. Scene-material length remains measured in world centimeters.

For a **Skeletal Fur Actor**, create the material with `skeletal=True`. This
variant reads each component's ShellDepth instead of static-instance data;
assign it to the actor and set its pose source as usual. The same lighting
controller can target the skeletal actor. Existing material names are preserved:
use a new name to opt into the new wind/skeletal graph instead of overwriting
an authored material. Earlier preview materials remain available.

Wind normally uses Unreal material time. `UseWindTimeOverride` defaults to zero;
the private tests set it to one and use `WindTimeOverride` for reproducible
snapshots. These test controls should stay disabled for ordinary animated wind.

Place a **Fur Lighting Controller**, select a directional **Key Light**, and add
the fur actors to **Targets**. Direction, linear color, temperature and intensity
update from that Unreal light. The bridge evaluates the recovered direct-light
equations; it does not replace the engine's deferred shading model. One controller
should own a target's lighting parameters. A missing/disabled key produces no
direct light. The directional bridge uses intensity/pi to match the unit-key
reference. World exposure still applies normally outside the diagnostic scenes.

Enable TAA and viewport Realtime for the validated temporal path. Unreal falls
back to FXAA in a non-Realtime viewport even when the TAA CVar is set.
Use the viewport's Realtime control: in this UE 5.8 build, Python's
`editor_set_viewport_realtime(True)` only removes its own disabling override;
it does not turn a non-Realtime viewport on. An inactive editor can also leave
its framebuffer unchanged. The private validation project uses a temporary
positive Realtime override and explicitly advances its viewport without focus.
Coverage uses 32 fractional Halton
phases plus the separate recovered noise cycle. Integer-only phase increments
are ineffective inside the shader's fractional hash. The phase sequence is
verified. A persistent-viewport comparison measured 76% less stationary
frame-to-frame variation with TAA on Ratchet and 85% on sheep. Slow camera movement and settling
also produced live frames. This does not establish skeletal animation quality
or the absence of ghost trails. Earlier high-resolution screenshots incorrectly
reported requested Realtime settings as effective state and are not temporal
validation evidence.

For shadows, add selected occluding actors to **Shadow Casters** and enable
shadows. The controller renders a 512x512 orthographic depth map with bilinearly filtered 3x3 PCF
(16 merged depth comparisons);
Shadow Width controls its coverage and Shadow Bias controls depth comparison.
Light/caster transforms trigger refresh. Use **Refresh Lighting** after mesh,
visibility or deforming-caster changes. The saved private tests contain a
capture-only cube for toggling a clearly observable shadow. No ambient/fill
light is injected, so a fully occluded surface is black with only this key.

This first bridge covers one directional light and explicit depth-map casters.
Point/spot lights, VSM/Lumen/probes, volumetric fur shadows, camera-dependent
shell LOD, moving temporal history and complete native parity remain open.
Actual Ratchet/sheep fixtures live outside the plugin; no game assets ship here.


The continuous PCF filter blends comparison results at texel centers, rather
than interpolating depth across separate surfaces. The map resolution remains
512x512; this reduces texel snapping but does not eliminate resolution limits.

To test self-occlusion, add the fur actor itself to **Shadow Casters**. Start
with the default 0.5 cm bias; smaller values can cause excessive self-darkening.
This uses opaque masked depth, not strand-density transmission. The private
Ratchet check covers static shell self-occlusion and a fixed wind deformation
followed by **Refresh Lighting**. It does not establish animated skeletal
self-shadow quality or equivalence to the game's shadows.

Enable **Refresh Animated Casters** for periodic deformation updates, with
**Shadow Updates Per Second** between 1 and 30 (default 10). It is off by
default. Transform changes and manual refreshes are immediate and are not
limited by that periodic rate. Continuous skeletal playback and a separate
animated skeletal caster have private validation evidence. Environment/probe
lighting remains a separate integration task.

### Optional authored environment

`create_scene_fur` accepts `environment=texture_cube` and
`environment_brdf=texture_2d`. Supply both or neither, in linear color. The BRDF
lookup must be clamp-addressed, with RG coefficients indexed by absolute
normal/view cosine (U) and average gloss (V). Cubemap mips must already contain
the intended roughness filtering; importing an arbitrary cube does not generate
physically correct prefiltering for this model.

New materials expose `EnvironmentIntensity` (default 0.6),
`EnvironmentMaxMip` (default 5) and `EnvironmentRecoveredAxes` (default 0).
Set the last parameter to 1 only for cubes authored in the recovered Forge
coordinate system. Ordinary Unreal cube directions use the default 0. Setting
intensity to zero disables the environment term. Materials created without
these optional textures retain the direct-only graph. Use a new material name
to adopt this graph; existing assets are preserved by the builder.

The response uses the recovered anisotropic environment frame, primary and
secondary Fresnel response and diffuse/specular resolve. Environment light is
added separately from the selected directional caster shadow. This is an
explicit authored-cube bridge, not automatic Unreal Skylight, reflection-probe
or Lumen integration. The plugin does not include an extracted game cube/LUT.

### Environment controls in Details and Blueprint

On **Fur Lighting Controller**, expand **Fur Lighting / Environment** and turn
on **Override Environment**. Assign **Environment Cube** and **Environment BRDF**,
then adjust **Environment Intensity** and **Environment Max Mip**. **Enable
Environment** turns the contribution off without losing the assigned assets.
The visible **Environment Status** explains missing/invalid inputs or target
materials that do not have environment support. No material-instance parameter
editing is required after assigning a compatible scene-fur material.

Blueprint **Set Environment(Cube, BRDF, Intensity)** enables the override and
updates bindings immediately. Details edits and fur material rebuilds rebind on
editor/game ticks. **Refresh Lighting** also applies the settings when Realtime
is paused. A missing cube/LUT, sRGB data, or non-clamped LUT disables the
contribution until corrected; the tool does not change your texture settings.

Turning **Override Environment** off restores the parent material's environment
parameters, leaving weather and shape alone. It restores parent defaults, not
previous manual dynamic-instance edits. Existing controllers default to no
override, so prior material-driven environment workflows remain available.
Targets still need a material created with the optional environment inputs;
this controller does not rewrite existing artist materials or generate a LUT.

### Dry fill and rim lighting

New scene-fur materials accept **Key Light**, **Fill Light**, and **Rim Light**
from the Fur Lighting Controller. Each assigned directional light uses its
rotation, linear color, intensity and color temperature with the recovered
hair response. Fill and rim are additive and unshadowed; the existing depth
capture remains attached to the key. Repeated assignments are counted once.
Disconnecting or hiding an additional light removes its contribution.

Create a material with a new name using `create_scene_fur` and assign it to the
fur actor to obtain the new inputs. Existing material assets are preserved and
are not automatically upgraded. Changes and rebuilds rebind in editor/game
Ticks; use **Refresh Lighting** when editor Realtime is off. When using several
directional lights, set a unique highest Forward Shading Priority on the key
for Unreal's separate forward/atmosphere light selection.

This bridge supports three explicitly selected directional lights. It does
not provide native scene probe selection, point/spot lights, fill/rim shadows,
or complete Rift Apart visual parity.
