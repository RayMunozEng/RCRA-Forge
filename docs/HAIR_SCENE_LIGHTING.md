# Hair scene lighting integration

Status: 2026-09-04. The perspective HDR viewport can now consume explicitly
supplied scene resources: the resident light grid, per-tile probe lookup,
probe records, native BC6U cubes, key radiance/direction, optional native
key-shadow/cloud/gobo resources, reflection history/velocity, neighboring
denoise masks and an optional native local-light block.
See [HAIR_CONNECTED_REPLAY.md](HAIR_CONNECTED_REPLAY.md) for the exact connected
production lighting/store/denoise comparison. The default asset view retains its isolated environment.
Full composed-frame parity remains unfinished.

## Production path

`core/hair_scene.py` validates the bundle before allocating resources in the
viewport's current GL context. `HairSceneGpu` owns and releases its textures,
buffer textures and comparison sampler. The scene fragment uses GL 4.3 and 18
fragment texture units for the base scene, with auxiliary scene resources
expanding the requirement to at most 23. Cooked cube blocks retain all six authored mip levels
and native seamless filtering. The 128-byte probe records and original resident
grid indices are uploaded without repacking or inferred placement.

`FUR_SCENE_LIGHTING_FRAG` reads the actual packed material targets through the
same separate vector-decode pass as the ordinary preview. It reconstructs world
position, evaluates the shared light-grid/probe kernels and selects lookup bits
at native top-left `pixel >> 3` coordinates. Scene key radiance scales the direct
contribution. Indirect BRDF and secondary-lobe accumulation preserve the native
fused operation order.

The optional 8192 x 8192 D16 atlas uses regular linear/clamp depth sampling and
a separate strict-Less comparison sampler on the same texture. The shared
`hair_key_shadow.glsl` implements cascade selection, stochastic transition,
four-tap attenuation and distant fade. Lighting takes the **minimum** of atlas
and contact visibility before accumulating key radiance. Native reflection
history and its occlusion feed the combined material resolve. The post pass
applies native color precision before denoising.

## Supplying a scene

The scene loader must supply a bundle for the current model placement, camera,
viewport and resident resources. The following API also accepts a regular dict:

```python
with np.load(path, allow_pickle=False) as scene:
    viewport.set_fur_scene_lighting(scene)

viewport.set_fur_scene_lighting(None)  # Release the attached scene resources.
```

Required arrays are `viewport_cbuffer` (480 uint8 bytes), `world_cbuffer` (896
uint8 bytes), `probe_lookup` (uint32 words x ceil(height/8) x ceil(width/8)),
`probe_records`, `grid_lookup`, `grid_data` and the six default/local cube mip
arrays accepted by `validate_replay_bundle`. Distant-GI textures are required
when enabled by the constants. Optional `key_shadow_depth` is the original
8192 x 8192 uint16 atlas. See `HAIR_INDIRECT_REPLAY.md` for the base schema.
When a structured probe buffer includes trailing capacity, supply the optional
integer scalar `probe_record_count`; lookup bits at or above that active count
are rejected rather than treating padding as live records. For a full-view
scene bundle without that scalar, validation derives the smallest effective
record prefix covering every supplied tile bit. Direct point-query replays keep
the buffer-length fallback for compatibility.

Local direct lighting is optional as a complete base pair:
`light_lookup` (uint32 words x ceil(height/8) x ceil(width/8)) and
`light_records` (count x 128 uint8). `light_record_count` may supply the
manager's submitted prefix; otherwise validation derives the smallest prefix
that covers every current lookup bit. `light_volumes` (count x 128 uint8) is
required when a referenced light uses clip, color-volume, gobo or shadow-volume
records. The native packed `gobo_atlas` (2048 x 4096 uint32 R11G11B10) is
required only when one of those referenced records samples it. Referenced
indices and ranges are checked before upload. A referenced local shadow map
also requires `light_volumes` for its per-map transform and the shared
`key_shadow_depth` atlas. The shared volume and atlas resources may also be
supplied without a local-light lookup when key modulation alone references
them. `cloud_shadow` accepts native packed or floating RGB(A) input and is
required when world row 41 enables cloud attenuation. Key gobo and key
shadow-volume ranges are validated against world rows 14--27 before upload.

`core/probe_lookup.py` preserves the exact CPU and integer boundary around
lookup generation. It computes the camera-dependent packed Z-bin
limits at byte 124 from placed record bounds, matches the saved view's 22
effective records and shared scale bit for bit, and expands those inclusive
16-bit limits into the retail Z-bin word texture. It also reproduces front-shell
OR and opaque back-shell AND writes from boolean raster coverage and exposes the
perspective and orthographic coarse-derivative depth predicates.

The same module now reduces a full linear-depth surface into conservative R16F
tile minima/maxima and evaluates the recovered interval relationship
`shellNear <= tileFar && shellFar >= tileNear`. On the saved view, an
unexpanded CPU box model using those bounds matches 712,626/712,800 opaque
lookup decisions and every zero record mask. The module also exposes the exact
36-vertex box stream, the stage-width push calculation, and the recovered
`VS_LightShell` box projection. Applying those boundaries to both lookup passes
raises the saved-view match to 712,774/712,800 decisions (99.9963524 percent),
with IoU 0.99971679. The remaining 26 decisions require exact D3D depth
quantization, triangle ownership and per-primitive coarse derivative helper
lanes. See `probe-triangle-mask-analysis.json`; do not treat this CPU coverage
model as exact hardware rasterization.

The validated saved-view box path is now reusable rather than analysis-only.
`rasterize_probe_screen_lookup` accepts current records, view/projection,
linear depth and the recovered raster constants and emits full/opaque lookup
bitfields. `build_probe_frame_lookup` starts one step earlier: it sorts explicit
`ProbePlacement` entries, derives the six current frustum planes, applies the
resource active/OBB/transition selection, fills camera Z bins, generates their word texture, and rasterizes the
screen lookup. Rebuilding the capture from all 22 matched cooked probes retains
the same 26 boundary decisions, matches every Z-bin word, and selects all 22
captured active probes. The viewport still needs a scene owner to provide
current zone transforms, active-resource lifecycle, cube slots and fades; those
values are not inferred from an isolated model.

Round records now select the exact executable cylinder stream: 16 segments,
192 vertices and 64 outward triangles. Its generated float32 bytes match the
2,304-byte source at `0x1432D3C60` exactly. This establishes topology and the
shared shell projection; no active round probe exists in the saved view for an
output-level raster comparison.

Lookup dimensions must match the physical framebuffer. Camera, framebuffer,
model and LOD changes invalidate the supplied view. The renderer then uses its
default preview lighting until another bundle is attached. Upload replacement
is atomic: an allocation failure retains the old resources and their original
view identity. The loader remains responsible for valid transforms, current
residency, temporal state and refreshed tile lookups; the API does not discover
or manufacture these from an isolated model.

The smoke tool accepts `--fur-scene-bundle PATH` and reports whether the scene
and atlas are active. Do not attach a captured camera's lookup to an unrelated
model placement or orbit and describe the result as native scene parity.

## Local direct-light boundary

`core/local_lights.py` now preserves the Hair shader's local-light input
contract. `LightGpu` and `LightVolumeGpu` are both exact 128-byte layouts from
shader reflection. The local lookup is a `Texture2DArray<uint>` at one texel
per 8x8 full-resolution tile; each slice contributes 32 record bits. Hair
visits slices in ascending order, repeatedly removes the lowest set bit, and
indexes record `slice * 32 + bit`. The active slice count comes from world
constant offset 44. Lookup parsing rejects out-of-range slices, tiles and
record references instead of sampling unrelated buffer capacity.

The retail `CS_LightLookupGenerateZBin` producer is recovered as well. It runs
64 threads per group, reads `LightGpu.m_ZBinMinMax` at byte offset 96, treats
both packed 16-bit limits as inclusive, and writes one bit per active record to
`(record / 32, zBin)`. Its instruction flow is identical to the verified
environment-probe producer after normalizing the source binding and field
offset. `generate_light_z_bin_lookup()` preserves the separate submitted count
because buffer capacity is not an active-record boundary.

The same module implements both recovered light-geometry branches through base
radiance. The zero-radius path covers cone shaping, quartic radius falloff,
cut-on/cut-off ramps, optional bulb push-forward and inverse-distance scaling.
The nonzero-radius Hair path preserves spherical broadening, finite-segment
direction selection, three-lobe averaging, the area metric and distance
correction, including the retail negative-radius compatibility branch. It also
evaluates the ordered clip-volume Boolean chain and flag-2 accumulated-light
color volumes, including box and radial falloff.

Gobo coordinate generation is recovered for flag-32 alternate spherical,
flag-1 spherical RGB and projective RGB modes. It preserves the shader's fast
angle approximations, atlas orientation, projective clamp and edge fade. The
ordered shadow-volume chain preserves all five signed-plane tests, atlas
coordinates and the sampled-color fade-to-white operator. The shared captured
gobo atlas is 4096 x 2048 R11G11B10 with SHA256
`317e2e8b4a214f3d10a3412b3447a987ce4a4e4dc02efcad3a6e3d47fc6672d0`.

`hair_local_lights.glsl` connects those supported branches to the production
Hair material resolve. It fetches exact raw 128-byte rows, walks lookup slices
and lowest bits in native order, applies color volumes to the existing diffuse
and specular accumulators, and adds point/area diffuse, transmission and both
Hair lobes. It also evaluates projective and packed six-face local shadow maps
from the per-map `LightVolumeGpu` transform in the shared depth atlas, including
the strict compare path and the four rotated raw-depth taps. Flag-2 lights then
reuse the exact four-tap screen-contact kernel with the evaluated local-light
direction, shared frame noise and combined linear depth. This order and the
minimum composition with local shadow-map visibility match the recovered Hair
instruction flow.

`hair_key_modulation.glsl` connects the remaining key-radiance modulation in
native order: cloud visibility, periodic key gobo RGB, then the ordered
five-plane key shadow-volume chain. It preserves the cloud diamond projection,
packed atlas transforms, the nonstochastic log2 cascade selector and each
volume's fade-to-white operator. The saved frame disables all three paths, so
the verifier proves their zero-contribution captured behavior and keeps
synthetic coordinate/selector anchors for the otherwise unexecuted branches.

The local screen-lookup producer is now recovered through the manager's
submitted-stream boundary. The executable registers `FillLightLookup` as event
`0x67`; each submitted light owns a prepared float3 triangle stream, rigid
object transform and local AABB outside its `LightGpu` record. Helper
`0x1410B6070` builds the exact 96-byte `LightShellCBuffer`: it copies the matrix,
transforms the AABB midpoint, clamps each local half-extent to `0.001`, writes
the submitted record index and appends the screen-space push. Both
`VS_LightShell` variants then share the recovered probe projection and screen
bitfield operations.

`LightShellPlacement`, `build_light_shell_constants()`,
`rasterize_local_light_screen_lookup()` and `build_local_light_frame_lookup()`
implement that boundary. The frame builder consumes one explicit ordered
`LightGpu`/placement prefix and returns its inclusive Z-bin words plus both full
and opaque per-tile lookup resources. `build_hair_scene_local_lookup()` attaches
the generated opaque lookup, full lookup and Z bins to a current scene view and
updates the world's active word count.

The upstream near-plane path is recovered too. `build_light_shell_near_clip_plane()`
preserves the `1.15 * radius + near` overlap gate, the capped `0.1 * near`
expansion, two-ULP radius floor and internal 3x4 plane transform.
`prepare_light_shell_vertices()` preserves the all-inside reuse/all-outside
rejection split and closes a straddling outward shell through polygon clipping,
intersection-edge assembly, centroid-angle ordering, cap insertion and fan
triangulation. The static verifier pins 14 executable ranges, the event name and
ID, constants, 96-byte cbuffer hash, closed 20-triangle cube cut and four
populated output tiles; its report SHA256 is
`f26ef671151fa063a36019780037e6443dc8c5d5dff27227ca89c6f7bbd8296c`.
The Hair capture did not export manager placements or a prepared-stream byte
oracle. Automatic runtime source-light selection/ownership therefore remains
open; geometry is not inferred from `LightGpu`.

The manager's upstream structured-buffer boundary is now pinned as well.
`InitLightSB` creates five main `LightGpu` tiers with capacities 32, 64, 128,
256 and 512, plus five auxiliary `LightVolumeGpu` tiers with capacities 128,
256, 512, 1024 and 2048. Every tier has a 128-byte stride. The upload selector
clamps the active main count to 512 and maps
`ceil(activeCount / 32) * 32 * 128` bytes. The saved 4,096-byte buffer is the
first 32-record tier.

Executable function `0x1410A9710` is the exact `LightGpu`/`LightVolumeGpu`
packer, and `0x1410B37E2` is its only exact direct call. The base path maps the
runtime 0x170-byte render-light record's axes, position, bulb geometry,
attenuation radius, radiance, cone, depth limits, Z-bin limits and volumetric
fog into the reflected 128-byte output. `LightGpuBaseSource` and
`build_light_gpu_base_record()` implement the strict base path for subtype 1
with no auxiliary volume references. Native mode-1 and mode-2 radiance scaling,
the `1e-5` attenuation-radius floor, float32 Z-bin flooring, inclusive upper
edge, float16 fog packing and both branches of the legacy negative-radius
representation are preserved. Auxiliary-volume allocation remains outside the
base producer.

`light-gpu-producer-validation.json` pins the executable hash, five producer
ranges, the ten tier initializers, the exact call and constants. All eight
populated captured records rebuild byte for byte; their 1,024-byte prefix has
SHA256 `79c2c34c74d87ac272eb0651d923cf0dc8d0a8f730b2fb8e6b3da0e232e12c69`.
The report SHA256 is
`29527e3f0f8b6c49b3b35598503b351222d4c769a55dffaa300ecf14e64eeb20`.
The capture does not include the persistent input records, so this is a static
field-map plus packed-output consistency oracle rather than an independent
runtime input/output capture.

`build_light_gpu_subtype_1_record()` now implements the shared auxiliary-tier
allocation order and its packed low-uint16-index/high-uint16-count references.
It appends primary clip, gobo, up to three shadow-map records and an ordered
shadow-volume list, skipping subsequent allocations individually when the
selected tier is full. Native source constructors cover the primary clip
transpose, both standard and dual-sign gobo atlas mapping, projected and
six-face point shadow maps, the 0x68-byte shadow-volume boundary, and both
subtype-4 color-volume dimension modes. The complete static subtype-3 and
subtype-4 packers add their native affine inverses, subtype-specific field
rewrites, auxiliary allocation order, reference encoding and capacity behavior.
The atlas helper now resolves the valid bit, generation byte and table index
exactly from an explicit manager-table snapshot.
`light-gpu-auxiliary-allocation.json` pins all seven allocation branches plus
eight shared or native helpers and checks independent 128-byte synthetic
digests for subtype 1, subtype 3 and subtype 4. Its SHA256 is
`a3676dd8e7c145761930c9663874965be0ab665b6c530d7e076b10c6bbfced58`.

The CPU-visible manager selection worker is recovered separately. It masks the
runtime flags, applies the enabled, singleton, distance, fade, emission/type
and manager hierarchical-depth gates in native order, and claims candidates in
16-entry chunks. Membership and source order within each chunk are exact. The
optional `completed_chunk_order` input now reproduces the order in which
nonempty chunks reserve output slots and copy their local pointers contiguously;
empty chunks reserve no slots. The frame-specific scheduler completion sequence
remains an explicit input. The per-frame owner now
covers the complete static call chain: it allocates the 0x18a0-byte state,
submits primary and optional secondary spatial queries, schedules the worker,
merges at most 512 pointers, partitions them, ranks priority entries by
`max(boundExtents) * radiusScale / max(centerDistance, 1)`, appends deferred
entries and passes the final list to the persistent/GPU record packer. Equal
scores now follow the exact retail generic-sort permutation: insertion sort
below seven entries, the middle pivot at seven, median-of-three above seven and
pseudomedian-of-nine above forty with Bentley-McIlroy three-way partitioning.
The bounded CPU oracle covers 34 threshold and mixed-key cases through 512
entries (`light-manager-equal-score-sort.json`, SHA256
`52d2f7acced0d798248706155bce3708626e4a28c229589da6ad757ea64fa29f`,
case hash `3022e0729e94fe710df264bd2266ff7fd0b16c92a91db0a6e7eb341aea18c4bb`).
Type 0
uses six weighted record units; other types use one. The secondary merge now
also reproduces ascending squared-center distance, eligibility, the 512-cap
stop and runtime bits 29/30/31. The skip/defer/priority gate sequence now derives
object visibility, resource readiness, type-resource availability, the
auxiliary-volume plane classifier and runtime-bit-21 distance deferral from
explicit snapshots. The common spatial submitter and worker now
pin the 0x100-byte descriptor copy, caller-owned pointer/count/capacity
contract, 1024-pointer local flush boundary and completion signal. The optional
secondary query is populated exactly: its sphere center is manager translation
plus the global forward distance times manager axis Z, its radius is 48.0, and
its 16 planes use six axis normals, eight normalized cube-corner normals and two
repeated +X normals. Retail stores four component-major 4x4 groups totaling
0x100 bytes. The bounded oracle report
`light-manager-secondary-query-descriptor.json` has SHA256
`1db9e9765713354fe7e0e56e155a578b58bdb4839abafbe73a486eb75865d5fe`;
the independent port report has SHA256
`6e41d1d5ec8f3741414c6ecb3c2fb863565eb32d0c73635e8b4cdae5b4eb6a6c`.
The common primary descriptor is exact too. It copies six manager planes and
derives ten more from eight edge points with the retail overflow-safe plane
helper, then packs the same component-major 0x100-byte layout. Its bounded
oracle and independent port reports have SHA256
`0d596d3c4b395c4e24cd615b2792906a636cec6f98daed4491b659eea19a8b47`
and
`028210af8958d9741dfc5106ac7b60b66c3a81338705d6dbb30d189b8f0ead21`.
The view-flag alternate path is exact from owner dispatch through its submitted
bytes. Manager `+0x438` bit 1 selects a 16-plane OBB descriptor from three axes,
three extents and translation; all nine ordinary, nonorthogonal and degenerate
cases match native binary32 values and signed zeros. Its bounded oracle and
independent port reports have SHA256
`bade3470b43bc63b992b4f89d1a2aa6924ba59a40312cb5e51025aee11c555e6`
and
`039244de6a160e7e5fd6cdd5d2de1b895ca4c96eb18d449db6bf08263229e775`.
The optional primary override is also exact: when enabled it replaces planes
11 through 15 from the manager origin, center, axis offset, extents and terminal
normal, then copies zero to two authored tail planes into the final slots.
All four enable/tail-count cases match the bounded oracle and independent port
reports with SHA256
`19f6c490ffecdb37563f308700ad2906ef438fef7f13bc9cf1332bed009f209a`
and
`11a43e678d0a45901ae0b63355f7e283a83e9629597f81f56afee72aa4b1b1c6`.
The basic primary spatial refinement helper at `0x1412B72A0` is now exact too.
It transforms each source center and three OBB half axes, evaluates support
against all 16 component-major planes, and compacts retained pointers in input
order. All 16 sources across five membership, boundary, transformed, tail-plane
and empty cases match retail, including its negative-zero rejection. The native
oracle and independent port reports have SHA256
`cd913360327ab43362e7649acb4a379d672ec13928206b1db5937fdd53fd3a19`
and
`4b2e82fba60065366112b9b771b14bbedf100fee3b2206fd400a4bc065544040`;
the ordered index output hash is
`7c77ceda29740d070eab319827808f2df481a52db8336316ae99bfee7827fae2`.
The optional refinement helper at `0x1412B78B0` repeats primary membership,
then evaluates four component-major planes as an exclusion volume. It removes
only OBBs strictly inside all four planes; boundary contact or crossing any
plane stays visible. All 20 sources across five exclusion, primary-precedence,
transformed and empty cases match native ordered compaction. Its oracle and port
reports have SHA256
`be69572e6145680f590c3c9cf40a8ee21a6fc03812d60f704714f9d984819a5a`
and
`bd8b20e2338c93452b0bf6eb9a7eeacf26bd299b8cb41682335a692893081946`;
the exact ordered output hash is
`97d534c56709b41fb8ee71f436065952d48ff9710f79a7870cfb66a1323cbef2`. The spatial cell front end is now reproduced through its consumed outputs.
Classifier `0x141603A80` returns intersection and full containment for a
center/half-extent AABB, letting the worker skip per-entry coarse tests for
fully contained cells. Helper `0x141603D40` emits intersecting cell indices in
input order at both observed 32- and 48-byte strides. The consumed intersection
output of oriented helper `0x141603FE0` also matches all eight cases. Seven AABB
cases, three batches and eight oriented cases match the native oracle. The
oracle and independent port reports have SHA256
`54a75db361683fdd21f7e804a9016e2ed2a2c6b5864b4805b7e1a30b9a47fed6`
and
`216aca809858c90598a017d28ae0a9a0f465f03127e86adc43d967bd9a321441`.
The oriented helper's query-coverage output evaluates support minus distance across all 16 planes; it and intersection match all eight native cases.
The spatial-bound packer and admissibility gate match 7 and 5 native cases; their oracle and port reports have SHA256 b89305c55d2a9b3f2c971c00e147f79767c40f6289514f5f0e211ca4141aee5d and 5fe4e71938a631909684f5f50d5cc2c507d5c33a4a87c39dbb52a978df6bd95d.
The static spatial-database layout/lifecycle report pins ten retail ranges and recovers eight 0x70-byte owners, 0x30-byte cells, 0x100-byte pages with 15 entries, 0x10-byte packed entries, `(page << 4) | slot` handles, insertion, swap-compacting removal, bound updates and dirty-cell rebuilding; its SHA256 is `66eb7e352db2077435fb6905475c4b9e87a625c92c95ef537c13631ad5dff304`. Live runtime contents and scene membership remain external.
The static tree path is now recovered through exact retail allocation, lookup and subdivision. Nodes are 0x20 bytes with eight uint16 slots; lookup consumes one signed-coordinate bit per depth in x/y/z slot order and distinguishes cells from child nodes with the slot high bit. Subdivision derives child origins, parent links and depths exactly, then redistributes entries in source append order while reusing occupied octants and rebuilding each child bound with the same signed-int16 sphere union. Ten lookup cases, six link-prelude cases and three full redistribution cases covering 16 entries match the bounded native oracles. Native/port report SHA256 pairs are `81b02ec7ff56ffc5af8bf04b0ee5eb2d3280edb47466217ca4d8e5704023adc7` / `85b61894e9499e8098e1b6cef019f6d6045dd98670964607857dcbd92564fdd1`, `44969d03fcd4e628ab2bf6b9d9b14b3d05f5d1e2ab7415c703bc692a25122e12` / `e42ad75baf30befcffe586fa7d2c2c20bb961008ed870d6fc81d8db1d3fe6b88`, and `b1b90db7e8e6af853479e5b0622104136ad6d306199b6260308a87b0f5fa68dd` / `3f34021b52d11f5106072fe218815525f52eddf00d337199971a8fb5b8309698`. The removal tail at `0x141669C7D..0x141669D77` completes static tree symmetry: it clears the released cell slot, retains a node with any occupied sibling, prepends empty ancestors to the free list, repairs the maximum active index only when required and clears the root after releasing the final ancestor. Six sibling-retention, nonmaximum, gap-rescan, two-ancestor and root-release cases match native output exactly. The native and port report SHA256 values are `f30a9a8a69c9011bf3617cea643cd12c1d8615212b444ce6ecb8a9f5663c21a3` and `37f8f6b45e3cf86b5e66484c9b219ded7307b60a4db7aa3eff4e50b5ea21b277`; their shared semantic output SHA256 is `074375c5eb37b244a8c79a7ee701186544e69b6266f66cc7c58e5ca675150e72`.
The dirty-cell rebuild port matches 23 packed entries across five single-page, linked-page and signed-saturation native cases bit for bit. The oracle and independent port reports have SHA256 `0b746abb20109519392e4e42693377930195151819c39a05c60a323e8eec8bfe` and `f6f1b93ceb5a174093e5b83e25d7f48140a8a6d507a01436156b2dad855ed993`; their shared output SHA256 is `1d312100d5abd9e9dfdeecc40c790d15388bb8efd0703951215c4ed21a632824`.
The worker's three-state packed-sphere classifier matches six native direct, ambiguous and rejection cases; its oracle and port reports have SHA256 `d003024e9ad7f504a4ed40b84b445757b9f81004fc6037ae1a28184b04a7f71f` and `357f636f19a321589ba35bf056dc29cad632efa93780be35f342e6727a941723`. The explicit raw-page decoder and newest-to-oldest primary bucketer pass three contract cases in `light-spatial-page-chain-port-validation.json` (SHA256 `b58e0c8d048cf82db9bbbfe0f00726b05c4ef7ee02c51c23d79b22982bdd5e5c`).
The bounded primary resolver prepends direct indices, runs ambiguous indices through the native-verified exact OBB predicate and applies output capacity. Its three native-linked cases pass in `light-spatial-primary-resolution-port-validation.json` (SHA256 `3ca2fc599260dc354ca55748e73dbe15b50a4d018d5be9d1e6f507e53fcaa006`).
The optional worker classifier at `0x1412B8FB0` also matches six native
direct, ambiguous and rejection states. It applies the primary sphere gate,
rejects spheres fully inside the optional exclusion volume, and routes
surviving boundary cases to exact optional OBB refinement. Its oracle and port
reports have SHA256
`7accdfc006f6f20ee81ecc7b97b79dde0cba25c0ac52635dc0e3bad464a78b62`
and
`e1ab7a1a012a6dc01cc57040c2732f4734b6339eeb524767693b40aea79a0086`.
The optional raw-page bucketer and bounded direct-first resolver pass a linked
page case plus three native-refinement/capacity cases; their report SHA256 is
`204784599a701d9037f30d2470f47e0a33960280ad674e16c9f7873a98e75829`.
The worker's midstream and final flush blocks now match seven bounded retail
cases. A bucket flushes only when `count + 15 > 1024`; direct pointers
reserve and copy before exact-refinement output, capacity clips each
reservation, and final cleanup repeats that order. The native oracle and
independent port reports have SHA256
`7b5d2685cc75a6c7531d4d309036fe0edbd34ee373f54796339e0ce72728e19f`
and
`26bcd6b3693230ad8e7cb71a2ef00c54d5c92f195add4e308406851871c61421`;
their exact shared output hash is
`3f2308c237c7630b26b766114fa5bac56062a40c0d17de3efe219e0ec4fac53e`.
The full primary and optional page-stream resolvers now preserve intermediate
flush interleaving as well as final direct-before-refined order.
Frame-specific descriptor inputs remain external.
For every final
source, the frame packer creates one 0x170-byte persistent record and passes the
same source/record pair to the initializer. That initializer stores either its
generated clip/cap output or the authored source stream at persistent `+0x140`,
with the vertex count at `+0x13c`. The downstream `FillLightLookup` loop reads
that persistent pointer from each 16-byte active entry and assigns contiguous
GPU indices in received order. The worker's view filter is a fully reproduced 16-bit hierarchical-depth test.
Its exact wrapper transforms source `+0x40` center and `+0x50` half extents into
the oriented-box query and supplies the retail `0.01` depth bias. Function
`0x14118CE60` projects all eight corners, derives the clamped pixel rectangle and
conservative depth threshold, checks four level-zero corners, chooses a mip from
the rectangle span, rejects from four coarse corners, and otherwise scans the
level-zero rectangle with masked signed-int16 maxima. Ten bounded native cases
cover both early paths, mip rejection, visible and occluded base scans, equality,
the depth cap and inconsistent supplied mips. The native and independent port
reports have SHA256
`993a854927faefe5b32caeab38fcfe3e718b8fb70ded32a1e8fbf70172fb6f75` and
`2d3bc22fc10bf3b7a85fe5fd386f5aacb0373579666cec260527a155ea890714`;
their shared semantic output SHA256 is
`0680e5a4f26a9e629e235b5583b8f1edb40a6f7702770cd5d41d96b889d1c663`.
The live frame's manager values and depth words remain explicit inputs. The resource refresh is now recovered through its raw-CRC
version cache, type dispatch, padded float3 allocation and all four geometry
sources. The box and rounded paths reproduce the authored 36- and 432-vertex
tables exactly. Type 1 and type 2 reproduce the native 216- and 48-vertex
circumscribed cone streams, including the executable's scalar sine/cosine
polynomial bit for bit across the pinned samples. The refresh has one direct
caller at `0x1410BAD85`. It supplies zero or one resolved oriented-box resource
and no camera object to `0x1410B6480`; the box contributes six world-space
planes in X/Y/Z upper/lower order. Retail partitions those planes around the
source origin, or negative local Z for type 3, and inserts the type-specific
lower-Z then upper-Z scalar planes between the partitions. The existing
clip/cap helper applies that ordered list sequentially.

Output helper `0x1410B8CB0` copies exact XYZ values to the persistent float3
stream, writes its AABB and computes a sphere from the AABB midpoint and
farthest vertex. For types other than 3 and 4, refresh updates source center,
radius and half extents through `0x1412B6AA0` only when the new half-extent
volume is below 98 percent of the old bound volume. Five plane cases and the
unit-box and fractional output samples match the bounded Unicorn oracle bit for
bit. `light-manager-selection-validation.json` pins 84 executable ranges, 15
static data ranges and composite clip/output hash
`59f74079f39ef78bcabacbe6c22424b7665d64fff6bf8b0c0ad40fef272ba414`;
its SHA256 is
`9ad136cab3adc0b29bab4ab308d13ce91826910cbb85f18f8630e57f211dc608`.

The upstream type-1 scene-light transfer is pinned separately. The common
converter at `0x14109A1F0` and type dispatcher at `0x14109AF10` map the cooked
record's intensity, attenuation radius, cutoff and cut-on distances, specular
intensity/fade, general fade, cone angles, bulb geometry and shadow cut-on
distance into the runtime light. Serialized `+0xB0` is now proven to be
volumetric-fog intensity: it passes through runtime `+0xB4`, persistent
record `+0xF0`, and the upper half of packed `bit_flags_vfog`. The strict
`SceneLightType1RuntimeTransfer` model reproduces the direct float writes,
the native `0.01` attenuation-override clamp and common/type-1 flag updates.
`scene-light-runtime-transfer-validation.json` hash-gates 17 executable ranges
and verifies the model across the pinned default record plus 21 placed records,
including all 11 native subtype-1 records. The implemented derived stage covers
automatic color radius, the native polynomial cosine/sine pair, cone ramp,
cutoff, cut-on and local culling-shape inputs. The resolved-transform commit
covers handedness, nonuniform-scale and median-axis classification. The source
matrix helper at `0x1402BD1A0` removes scale/shear into an oriented orthonormal
local basis, uses the native degenerate-axis fallbacks and preserves translation.
The full owner-source routine at `0x140FEED30` loads a holder from owner-relative
`+0x10`, dereferences its transform pointer and uses runtime-backed address
`0x146838510` only when that pointer is null; the pointed fallback value is not
pinned by the file image. Constructor `0x140FDFA10` normalizes source-descriptor
byte `+0x3B` into owner-state byte `+0xC6`. Selector `0x140FE5C30` prioritizes an
embedded `+0x60` override, the `+0xC6` already-world fallback, a non-null holder
transform, then the null-holder fallback. The placement loop either keeps the raw
record matrix or computes `record_local * owner_transform` at `0x141627F80`, then
applies it through `0x1412B6BF0`. Four selector cases and four composition cases
match native output bit for bit; their output SHA256 values are
`f896b0d5835c075302996f6b690a9750586efaad37624dfdb00352ed26d0d1ae` and
`6d191d26b08857050303e9d4f7b5dd2fb7a54aadaf7d8a667f0dc04c7a7179ce`.
The full-routine and selector disassembly SHA256 values are
`5008031a69a92a37f4038468151e01c9f87bf58fa51bd3197e93ff8b35dbf8c8` and
`524e057ce2ce8be7a82a23aaf7af0882fb0564bd642eed133fdc180ee3050725`.
The static source audit SHA256 is
`53170f909032cbca6fc2af5e00c6dc69868a1b026dc7ec54aa47f0b8092f15a2`.
The native and port report SHA256 values are
`9f36d5aad10a5bfb0fadce0e5410c87460341a4ea4f3b57eb67bc5c9c7a3daf8`
and `84b79696fc97d3425bae6d5a81fb563d16a948474c75bb2af0a347d8b3f15db8`.
The integrated report SHA256 is
`b3caea75910e954aed6c4f3b569c7e642c22dc9ef84ce9d4a789377d4d73f3e0`.

`hair-local-light-lookup-validation.json` validates the captured inputs rather
than inferring local-light absence from final accumulators. The exported lookup
has 16 slices, while the frame enables exactly one. That slice contains lights
0..7 across 1,414 scene tiles, but all **11,215 Hair pixels** read zero: zero
Hair pixels have a nonzero active word and the shader visits zero local-light
records for Hair. Six active records are zero-radius point lights and two have
nonzero area radii; none references a clip list, gobo, shadow map, shadow
volume or color-volume operator. Exported slice 3 is nonzero but outside the
active word count. The report SHA256 is
`cc034335216d7479875b111e43dea5b9ceee8d74d47f00e2a1ad8936cfe79b6f`.
The same report anchors the extracted producer container at SHA256
`5f29ec24d9625f2682fda7031808f51036b52761e49b6328eb5b6f55dd09c3e1`
and matches an independent scalar oracle across all 65,536 unsigned bins for
the observed contiguous prefix. The dispatch cbuffer that owns the submitted
record count was not part of this export, so the report identifies eight as an
observed screen-lookup prefix rather than claiming the runtime count source.
It also anchors the two shell shader containers and records deterministic
float32 sphere/capsule outputs for active area records 0 and 2. Those outputs
are static fixtures because neither record overlaps a Hair pixel in this frame.

## Verified results

Evidence paths below are relative to the outer workspace's private
`artifacts/rcra-fur-continuation/capture-tools/` directory. Original game exports
and captures remain outside the fork. Native measurements are comparison
outputs, except in the explicitly identified component test.

| Check | Result | Evidence |
| --- | --- | --- |
| Full Hair replay with shared material, scene, key atlas, contact and resolve | **11,215/11,215 stored RGB exact**; native float max 4.94719e-5, RMS 5.25779e-7 | `hair-shared-key-atlas/report.json` |
| Grid/probe upload component using native boundary vectors | All 11,215 indirect-specular RGB values exact; diffuse max 4.76837e-7 | `shared-hair-scene/report.json` |
| Production decode/scene fragment on original packed targets | World/view/normal/strand vectors exact at all 11,215 pixels | `scene-deferred-trace/report.json` |
| Production scene fragment, including reflection-frame preparation | 11,207 indirect-specular RGB values exact; max 2.78503e-5, RMS 2.20222e-7. Diffuse max 3.10183e-4, RMS 2.40607e-6 | `scene-deferred-shadow/report.json` |
| Production key-atlas visibility | 8,605 values exact; max 1.02103e-4, RMS 4.90448e-6 | same report |
| Atlas/contact composition | 4,080 Hair pixels exact, including 2,048 fractional-contact pixels; 16 non-Hair pixels preserved | `preview-contact-behavior/report.json` |
| Dry/wet/fallback previews | Passed; dry/wet preserve non-Hair pixels and native Hair color precision at both stores | `viewport-scene-regression-*.json` / `.png` |
| Live scene API, with and without an atlas | Rendering, camera fallback, clearing textures/samplers and reattachment passed | `viewport-scene-lifecycle.json`, `viewport-scene-shadow-lifecycle.json` |
| Local contact plus key cloud/gobo/shadow-volume static recovery | Captured disabled/white behavior exact across 11,215 Hair pixels; deterministic synthetic coordinate and selector anchors pass | `hair-local-light-lookup-validation.json`; `hair-key-modulation-validation.json` (SHA256 `9ca8ad1a98f703bb385eda6559889c2c6011175e51595b39e549c60e29bbf343`) |
| Local screen-lookup manager boundary | Event `0x67`, 14 executable ranges, near-plane clip/cap chain and 96-byte cbuffer are pinned; transformed full/opaque lookup has four nonzero tiles and agrees with the shared probe route | `light-shell-producer-validation.json` (SHA256 `f26ef671151fa063a36019780037e6443dc8c5d5dff27227ca89c6f7bbd8296c`) |
| Local `LightGpu` upload producer | Five 128-byte main tiers and five auxiliary tiers, exact packer call, constants, negative-radius compatibility and base field map pinned; all eight populated captured records rebuild byte for byte | `light-gpu-producer-validation.json` (SHA256 `29527e3f0f8b6c49b3b35598503b351222d4c769a55dffaa300ecf14e64eeb20`) |
| Local auxiliary light-volume producer | Native allocation order, tier-full skips, atlas-handle resolution and packed range references pinned; full subtype-3/subtype-4 packers and their native volume constructors have byte-stable synthetic oracles | `light-gpu-auxiliary-allocation.json` (SHA256 `a3676dd8e7c145761930c9663874965be0ab665b6c530d7e076b10c6bbfced58`) |
| Local manager candidate selection and shell refresh | Eighty-four executable ranges and 15 static tables pin candidate/query ordering, static tree lookup, subdivision and removal collapse, the full hierarchical-depth projection/mip/base-scan decision, exact secondary plus common and alternate primary descriptors, the optional primary override, both OBB refinement branches, cell classification and ordered compaction, resource CRC/version dispatch, exact 36/48/216/432-vertex sources, resolved-box and scalar clip-plane ordering, persistent float3/AABB/sphere output and the 98-percent source-bound shrink update | `light-manager-selection-validation.json` (SHA256 `9ad136cab3adc0b29bab4ab308d13ce91826910cbb85f18f8630e57f211dc608`) |
| Type-1 scene-light runtime transfer | Seventeen executable ranges pin direct fields, local-basis normalization, scalar derivation, descriptor-to-owner flag normalization, embedded/holder/fallback selection, record-local × owner composition, already-world bypass and resolved-transform classification across 22 extracted records | `scene-light-runtime-transfer-validation.json` (SHA256 `b3caea75910e954aed6c4f3b569c7e642c22dc9ef84ce9d4a789377d4d73f3e0`) |
| CPU suite and offline shader compilation | 593 tests passed; all 53 conventional/native production and recovered shader cases compile | `pytest -q`; `scene-shader-validation/report.json` (SHA256 `b272aeb05a0f139cfdf22d3d9c6ce5bb1537a4fae07755005cbd866f99efae4a`) |

The full replay uses original direct-light/history resources in addition to the
shared kernels. Its exact stored result is distinct from the production fragment
comparison. Small reflection-frame differences still cross a few cube-filter
boundaries in the production fragment; float and complete-frame parity must not
be inferred from the full replay's stored-color result.

The native scene bundle without an atlas has SHA256
`06771b1e6a37fd4b9b08a506bff0c9234195de9632fa1c859cf408abf09dcbbf`.
The bundle including the atlas has SHA256
`16d8fdec31c56643bd38a84c701c73425de76c021dff118c8eaa72f2f36a9d2b`.
They were assembled from verified existing exports by `prepare_hair_scene.py`
(add `--key-shadow` for the second bundle).
The captured base scene plus local lookup/light records has SHA256
`8c95a1dcd6b55c169b89888488de06d6b440b46208947ee13a487fea4e758ed4`;
build it with `--local-lights`. Its active lookup remains zero at all captured
Hair pixels, so this bundle establishes resource/branch availability rather
than an active-light output comparison.

## Remaining parity work

Reflection history and the combined resolve are now connected and verified in
the production chain; see HAIR_CONNECTED_REPLAY.md. The capture's post-key
diffuse/specular/back accumulators equal its final pre-resolve accumulators,
and the independent per-pixel lookup check above now proves why: local direct
lights contribute nothing in this frame.
The capture does contain nonzero reflection history. Other scenes still require
active-Hair output captures for the newly connected local shadow/contact and key
cloud/gobo/volume branches. The local screen-shell producer and near-plane
clip/cap preparation, negative-radius compatibility, base `LightGpu` upload,
subtype-1 auxiliary allocation and native gobo/shadow record construction are implemented
and statically verified, but this frame has neither its manager placements nor
an active Hair pixel with which to validate nontrivial output.

The manager's CPU predicate, query-backed state, spatial worker contract,
resource and volume partition predicates, source-side occlusion OBB preparation,
consolidation order, resource version/refresh dispatch, exact source geometry,
resolved-resource and scalar clip sequence, persistent output bounds, final
frame-source pack boundary and shell-stream association are now recovered.
Still unfinished are live spatial-database contents and scene membership, the populated manager depth hierarchy, captured resolved-resource
inputs, the frame-specific runtime scheduler completion sequence,
captured placement/prepared-stream bytes and concrete frame owner-transform values.
Native raster
origin/depth, opaque and fur motion, temporal rejection/depth history, final TAA
apply and the saved same-frame composed comparison are now connected and
validated. Scene playback uses its supplied native temporal constants and
reflection history. The isolated asset preview retains its own clock and
environment fallback.

All work is local and uncommitted. See `FUR_PARITY_CHECKPOINTS.md` for the saved
source/evidence checkpoints. No game/desktop state changes are needed to inspect
the checkpoint or run the CPU tests.

