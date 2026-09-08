# Cooked environment probe dependencies

Date: 2026-09-02

The archive work now distinguishes texture-backed environment probes from
probes whose inputs are scene draw lists, and decodes the shipped BC6 probe
atlases into their six faces and six mip levels. Matching those resources to
the captured local cube array and reproducing production spatial blending
remain unfinished. The default environment texture's path does not establish
which zone supplies a captured local probe.

## Executable evidence

The installed `RiftApart.exe` inspected on the second computer has SHA-256
`51299faca61866cf10ea9035a15b8f22600a56557dd5ffc1aad390d5a54e6d82`.
Addresses below are static virtual addresses with image base `0x140000000`.
They are evidence anchors for this binary, not runtime addresses to hardcode.

- `0x1413CC95C` requests DAT1 section `0x557013E9` and divides its size by
  128 before allocating the array identified by the `Zone Env Probe Array`
  diagnostic string.
- `0x1413CD610` consumes those records. Signed 16-bit indices at record
  offsets `0x74` and `0x76` select the zone's probe texture and draw-list
  arrays respectively. `-1` means no resource. Both indices are validated
  before passing their pointers to `0x141087130`.
- `0x141087130` keys probe registration by the 64-bit ID at offset `0x78`.
  The zone loader constructs a transform from the position at `0x00` and
  three axes at `0x0C`, `0x18`, and `0x24`, then applies the owning zone's
  transform. The parser therefore labels these coordinates **zone-local**.
- `0x1413C66AF` requests section `0x027795C5`. Its first two uint32 values
  are the counts of unconditional and condition-dependent texture slots.
  Unconditional 16-byte asset references begin at offset 8. A condition
  block follows them: a uint32 count of zero or five, condition IDs when
  present, padding to eight-byte alignment, and condition-major 16-byte
  references. Each reference contains an asset ID, DAT1 string offset, and
  type word. Runtime slot indices address the unconditional slots first,
  followed by the selected condition's slots.
- `0x1413CD510` requests section `0x2D1E19C6`. It starts with a uint16
  pair count, immediately followed by two face lists per entry. There is no
  padding after that initial count. Each face list contains six uint16
  counts, four reserved bytes, and uint64 scene instance IDs grouped by
  face. `0x1410878C0` sums all six counts; the zone loader advances by
  `16 + 8 * sum(counts)` twice to reach the next pair.

The executable's `EnvProbeDef` descriptions at file offsets
`0x47E6920` through `0x47E6BF0` distinguish baked, runtime, raw, and override
sources. Runtime probes store model-instance draw lists and render their
cubemaps in the game. The adjacent property names include model and impostor
draw lists for all six directions. Numeric face order and the remaining
record fields are deliberately not assigned speculative semantics by the
parser.

## Parser and inventory tool

`core/environment_probes.py` resolves each probe's texture variants and its
two draw lists. It preserves scene instance IDs as 64-bit values; those IDs
must not be treated as model asset IDs in the TOC. Truncated records and
out-of-range resource indices fail explicitly.

For a focused, reproducible installed-asset check:

```powershell
.\.venv\Scripts\python.exe tools\analyze_environment_probes.py `
  --game-root $GameInstallPath `
  --zone-filter malinon_intro_lgt.zone `
  --zone-filter /megalopolis/tile_zz27/ `
  --include-draw-ids `
  --output (Join-Path $TransferOutputPath 'environment-probes.json')
```

The second-computer scan of 231 Megalopolis `_lgt.zone` assets found 84
probes in 41 zones: 55 texture-backed probes and 29 probes referencing runtime
draw lists. The separate Malinon intro lighting zone adds one texture-backed
probe. All these records parse without errors.

A subsequent scan of all 2,192 installed zones matching `/megalopolis/` or
`malinon_intro_lgt.zone` found the same 42 populated zones and 85 probes,
with zero parse errors. No additional probe records were found in the other
zone assets. Reproduce that inventory by replacing the two focused filters
above with `--zone-filter /megalopolis/ --zone-filter malinon_intro_lgt.zone`.

A concrete runtime example is zone `0x9C292F5F8A79EEC2`,
`levels/i29/openarea/megalopolis/tile_zz27/tile_zz27_lgt.zone`:

- probe instance ID `0xF896FB5315175B7C`;
- zone-local position approximately `(-551.4413, 76.1153, 969.3533)`;
- texture index `-1`, draw-list index `0`;
- first face-list counts `(2349, 384, 1, 217, 308, 886)`;
- draw-list section size 33,194 bytes.

This proves that searching texture names alone cannot reconstruct every local
probe. It does **not** identify this example as captured cube 14. Establishing
that connection still requires the captured probe record, zone transform,
instance ID, and resource contents.

## Baked probe atlas layout

`CS_CopyEnvProbe` establishes the shipped texture layout. Its registration
function at `0x140133380` references an IGSH container at `0x143C6C0E0`
(file offset `0x3C6B2E0`, 5,856 bytes). The DXBC container starts 12 bytes
later, is 1,468 bytes long, and has SHA-256
`98ce447a9577874f19a3bf6a6d01fb1ada3572c317dc6d4eb816b198d19683c2`.
It binds `g_CopyEnvProbeSrc` as a `Texture2D<uint4>` at t5 and
`g_CopyEnvProbeDest` as a `RWTexture2DArray<uint4>` at u0. Each uint4 is an
unaltered 16-byte BC6 block.

The local probe-array allocation at `0x141356790` provides independent size
and mip evidence: writes at `0x1413567EF` and `0x1413567FD` set 256 x 256,
`0x141356807` sets six mips, and `0x141356813` sets DXGI 95 (BC6H_UF16).
The array has six layers per cube. The block-copy view divides both dimensions
by four at `0x14135688C` and `0x141356898`; the following loop creates six
mip UAVs. Thus the destination sizes are **256, 128, 64, 32, 16, and 8**.

For source atlases with 1024 x 512 pixels, the uint4 view is 256 x 128
blocks. With `L = log2(destination mip side in blocks)`, the copy shader is:

```text
face   = thread.x >> L
local  = thread.xy & ((1 << L) - 1)
source.x = (local.x - ((4 - (face & 3)) << L) + 256) & 255
source.y = (local.y - ((face < 4 ? 2 : 1) << L) + 128) & 127
destination[local.x, local.y, 6 * cubeIndex + face] = source[source.x, source.y]
```

The header declares one atlas mip, `planes = 4`, `array_size = 1`, and
BC6U format. All 36 destination subresources are packed into that one mip.
There is no projection conversion, face rotation, row flip, or resampling.
The face indices pass directly to the D3D cube-array layers in the order
`+X, -X, +Y, -Y, +Z, -Z`.

The source origins below are in **BC6 blocks**, not pixels:

| Destination side | Face 0 | Face 1 | Face 2 | Face 3 | Face 4 | Face 5 |
| ---: | --- | --- | --- | --- | --- | --- |
| 256 | (0,0) | (64,0) | (128,0) | (192,0) | (0,64) | (64,64) |
| 128 | (128,64) | (160,64) | (192,64) | (224,64) | (128,96) | (160,96) |
| 64 | (192,96) | (208,96) | (224,96) | (240,96) | (192,112) | (208,112) |
| 32 | (224,112) | (232,112) | (240,112) | (248,112) | (224,120) | (232,120) |
| 16 | (240,120) | (244,120) | (248,120) | (252,120) | (240,124) | (244,124) |
| 8 | (248,124) | (250,124) | (252,124) | (254,124) | (248,126) | (250,126) |

Of the 524,288 source bytes, 524,160 supply the cube. Eight blocks in the
bottom-right 4 x 2 block rectangle are unused. Do not invent 4/2/1 pixel mips.

`TextureAsset.compressed_cube_mips()` now extracts this layout while
preserving the existing conventional face-major cube path. Its
`decoded_cube_mips_rgb_half()` representation keeps linear HDR pixels.
The atlas decoder requires the exact recovered resource signature and payload
size; it does not reinterpret general 2D HDR textures.

### Installed-resource verification

All **60 distinct installed texture variants** referenced by the 56
texture-backed probes in the inventory use this layout. Their **2,160
face/mip outputs** matched explicit source block rectangles byte for byte.
Decoding each full atlas independently and cropping those rectangles also
matched every output RGB16F pixel exactly.

The Malinon Day texture `0x837545B07B72296F` supplies one concrete example:

- owner instance: `0xAF6C379F586A797B`;
- asset SHA-256: `8f425d5877fb607016515855fcf75ddee97efd7346bb48110a2189f8e4528686`;
- 524,288-byte BC6 payload SHA-256:
  `80d2c046e37f596b034fb1f80c0f364e6416906b959b7a67704c5a0412897e1d`;
- decoded maximum linear channel value: 195.0, preserved without tone mapping.

The second-computer evidence directory
`artifacts/rcra-fur-continuation/baked-probes/` in the enclosing workspace
contains the extracted shaders, disassembly, `validate_atlases.py`,
`atlas-validation.json` with every subresource hash, and the face preview.
These generated/game-data artifacts remain outside the tracked fork.
`tests/test_probe_atlas.py` uses synthetic distinct-word blocks to verify all
36 rectangles, non-overlap, orientation, payload bounds, active HD data, and
resource classification without requiring the game.

The earlier lat-long/octahedral comparisons of this Malinon texture used an
incorrect layout. Their low correlation rejects those projections; it does
**not** establish or rule out this asset's identity as captured cube 14.
That identity still needs captured resource contents or a matching probe ID
and zone transform. The smoke tool can now use the decoded asset explicitly
with `--fur-environment 0x837545B07B72296F`; the default environment selection
remains `0x8F083136CEB5FB07`.

## Cooked spatial fields and GPU records

The installed executable also contains the exact Hair DXIL hash from frame
7328, `5ff73b6b2aca9640cf18cd78b88ba3c0`. This is the DXIL **HASH chunk**,
not the DXBC container checksum. It occurs at file offset `0x38331CC` in
the DXIL container at `0x38302B0` (47,944 bytes). Its paired DXBC container
starts at `0x381EE4C` and is 70,756 bytes long, with SHA-256
`3eab95cba4145922b545ba3e2644add2c232913e4933aa5ad41ed933de9cf5df`.
Both belong to the IGSH container at `0x381EE40` (118,712 bytes), registered
as `CS_ApplyGBufferLighting_Hair` by `0x140131D90`. Thus the capture is not
needed to recover this shader's code, although its resource contents are
still needed to reproduce that frame.

The registration routine `0x141087130` copies the following additional
fields from the 128-byte cooked record into the 160-byte manager record.
The GPU record builder at `0x141089280` establishes their shader meanings:

| Cooked offset | Type | Meaning / consumer evidence |
| --- | --- | --- |
| `0x30` | 3 x float32 | Half extents; reciprocals at `0x141089688`–`0x1410896AD` |
| `0x3C` | 3 x float32 | Capture offset; added to current position at `0x141089872` |
| `0x48` | 3 x float32 | Negative X/Y/Z falloff distances |
| `0x54` | 3 x float32 | Positive X/Y/Z falloff distances |
| `0x60` | 3 x float16 | Signed negative X/Y/Z proxy bounds |
| `0x66` | 3 x float16 | Positive X/Y/Z proxy bounds |
| `0x6C` | uint8 | Shape: 1 takes the box branch; other values take the cylinder branch |
| `0x6D` | uint8 | Bit 0 enables diffuse contribution (GPU flags bit 1) |
| `0x70` | float32 | Authored sort priority, clamped to at least zero |

The registration routine clamps each falloff distance to at least 0.01.
The GPU builder stores **halfExtent / falloffDistance**, so these are
reciprocals in normalized probe coordinates, not inverse distances in meters.
The six proxy half-floats are expanded at `0x141089723`–`0x14108976E` and
written to the reflected proxy fields at `0x141089843`–`0x14108986B`.

The zone loader multiplies the probe matrix by the owning zone's matrix at
`0x1413CD89D`, using `0x1416280A0`. In row-vector notation,
`probeToWorld = probeToZone * zoneToWorld`; translation is row 3.
`0x14108AA20` updates only position and axes in the manager record. The
capture offset remains unchanged and is subsequently added to the updated
position. The GPU builder stores the first two axes and the sign of the
three-axis determinant; the shader reconstructs axis Z as their cross product
times that sign. Do not normalize or silently replace mirrored transforms.

The GPU `EnvProbeEnv` record is also 128 bytes, but has a **different layout**
from the cooked record:

| GPU offset | Field |
| --- | --- |
| `0x00` / `0x0C` | Axis X / residency fade attenuation |
| `0x10` / `0x1C` | Axis Y / Z handedness sign |
| `0x20` / `0x2C` | World position / uint32 flags |
| `0x30` / `0x3C` | Reciprocal half extents / float cube-array index |
| `0x40` / `0x4C` | Positive normalized reciprocal falloffs / negative proxy X |
| `0x50` / `0x5C` | Negative normalized reciprocal falloffs / negative proxy Y |
| `0x60` / `0x6C` | Positive proxy XYZ / negative proxy Z |
| `0x70` / `0x7C` | World capture position / packed Z-bin limits |

`core/probe_lighting.py` parses and writes this reflected layout and can
construct it from a cooked probe **only with an explicit zone matrix, resident
cube slot, and fade**. It does not infer any of those runtime inputs.

### Z-bin and screen lookup production

The CPU submit routine at `0x14108D200` replaces the builder's initial zero at
GPU offset `0x7C`. For each eligible manager record it reads world position at
manager offset `0x20`, the conservative radius at `0x84`, and the current
world-to-view depth coefficients. In the observed SSE float32 order:

```text
center = (viewY * positionY + viewX * positionX) +
         (viewZ * positionZ + viewTranslation)
minimum = max(center - radius, 0)
maximum = max(center + radius, 0)
scale = 1024 / max(1024, maximum over all records)
packed = floor(scale * minimum) |
         ((floor(scale * maximum) + 1) << 16)
```

The embedded base-depth constant is exactly `1024.0`. `0x14108AA20` updates
the rigid-placement radius as the stable length of the three half extents by
calling `0x1402985F0`; that helper divides by the greatest absolute component
before squaring and restores the scale after the square root. The submit path
computes the lookup word count as `(recordCount + 31) >> 5`.

The count is the compacted submit count, not structured-buffer capacity.
`0x14108D2B0` reads the resource index at manager offset `0x80`, tests the byte
at that index in the job's selection table, preserves manager order for every
nonzero entry, and increments the submitted count.

The selection-table owner is `0x14108BE90`. It allocates one byte for every
resource index through manager `+0x98`, gates entries through the active bitset
at `+0x88`, and tests the manager sphere and oriented box against the six
inward frustum planes at render context `+0x2E0`. It suppresses the two
transition indices at manager `+0x1D9C8/+0x1D9CC`, writes the result at
`0x14108C6AC`, and dispatches event `0x6B` (`FillEnvProbeLookup`) with the table
at payload `+0x08`. This is per-view geometric selection, separate from cube
residency fade.

`core/probe_lookup.py` implements both the record producer and its consumer.
`compact_selected_probe_records()` preserves the recovered submit-time mask
boundary and returns the source manager indices alongside the compacted rows.
`camera_relative_frustum_planes()` derives the D3D zero-to-one planes from the
same view/projection inputs, and `build_probe_frustum_selection_mask()` applies
the active-resource, OBB and transition-index gates.
`populate_probe_z_bin_limits()` derives the rigid-view centers from the
viewport's row-vector `ViewToWorld` matrix and can accept explicit manager
radii for transformed bounds. `compute_probe_z_bin_limits()` keeps centers and
radii explicit. `generate_probe_z_bin_lookup()` reproduces the compute shader's
inclusive low/high comparison and one-bit-per-record packing.

The installed executable (SHA-256
`51299faca61866cf10ea9035a15b8f22600a56557dd5ffc1aad390d5a54e6d82`)
contains exact recovered containers for `CS_EnvProbeLookupGenerateZBin`
(SHA-256 `a560bb2d2031d4a6382ffe562ea62c524410faaa34f2e8737d26f8f9b709e508`),
`PS_InsertLightLookupFront`
(`cce1e333e92f023d548eab624f588770047d5096ae6966fb3f4fff2112734392`),
and `PS_InsertLightLookupBackPerspective`
(`377266f6bf64305d6a3eb32fc6f1f58c17eaa6838a1f1f26d0ca37dda820e5b4`).
The saved-view CPU verifier reproduces all 22 effective record ranges and the
world-cbuffer scale bit for bit (`0x3F20CEFB`), then exhausts all 65,536
unsigned bin indices against an independent scalar shader oracle. Its report
SHA-256 is
`28e6b30693e2ce4a2d436230fe7b9e15753af663ea8ccdcf2ec7840dee150fbe`.
The fixed view proves the effective prefix needed by its lookup bits; it does
not expose the producer's runtime active-count variable, placement/residency
selection, or shell raster coverage.

The depth side of the opaque lookup is now bounded more tightly. The exact
`CS_GenerateEighthResMinDepth` container has SHA-256
`fa143e5c5d7dcf78ed51f6f9793b2c881c5755c662f6d3a72733d8bf73d36610`.
It launches 8x8 threads and performs four point-clamp texture gathers at
offsets `(-1,-1)`, `(1,-1)`, `(-1,1)` and `(1,1)`, then stores the minimum of
all 16 gathered values. `PS_InitLightLookup` (SHA-256
`4e7cf650ac73103e6ca50ab1deed8b038bd0db465a7c4682654c86ec04070633`)
performs the corresponding four-gather minimum into `SV_Depth` and clears
each configured full/opaque lookup word. Because that depth target is reverse
depth, its minimum is the conservative farthest linear-depth bound used by
the front pass. The back shader reads the nearest linear-depth texture.

The screen-shell vertex expansion table at `0x1452F1168` contains `2.0` for
submit mode 4. Helper `0x1410ACEA0` evaluates
`table[mode] * screenToViewX / activeStageWidth`. The saved cbuffer's
horizontal factor is `1.4530850648880005`; the named capture resources prove
the quarter-resolution depth stage is 480x270 and the lookup is 240x135.
Using the 480-wide raster stage gives `m_VertPushScale =
0.006054521072655916`.

The saved 1920x1080 linear depth and 240x135 opaque lookup establish the
conservative bound relationship. The baseline CPU ray/box model using an
R16F-rounded 8x8 **maximum** for the front comparison and an R16F-rounded 8x8
**minimum** for the back comparison matches 712,626 of 712,800 record/pixel
decisions (99.9755892 percent), with IoU 0.99810443. It exactly predicts all
12 zero record masks. Using the minimum or maximum for both comparisons is
materially worse, validating `shellNear <= tileFar && shellFar >= tileNear`.

The exact box stream is 36 non-indexed float3 vertices at `0x1432D3AB0`: 12
outward-wound triangles, two per face. Executing the recovered
`VS_LightShell` transform and the 480-wide pushed edge on those triangles
raises the saved-view result to 712,774/712,800 decisions (99.9963524
percent), with 91,779/91,805 intersection/union and IoU 0.99971679. Both the
front and back passes require the push; mixed pushed/unpushed candidates are
worse. The final 26 decisions depend on exact D3D fixed-function depth
quantization, triangle ownership and per-primitive coarse derivative helper
lanes. This CPU raster remains a validation model rather than hardware-raster
proof.

`reduce_linear_depth_bounds()` exposes the conservative tile bounds and their
R16F storage rounding. `conservative_probe_depth_overlap()` exposes the
validated interval comparison. `LIGHT_SHELL_BOX_VERTICES`,
`light_shell_vertex_push_scale()` and `project_probe_box_shell()` expose the
recovered box-stream and vertex-stage boundary. Reproducible evidence is
`eighth-res-min-depth-static.json`, `probe-box-mask-analysis.json`, and
`probe-triangle-mask-analysis.json` in the outer capture-tools directory. The
triangle report has SHA-256
`d7220d8ab2d111ac8da19eb02f1669990e5ab55721c420b39d399c7502925689`.

The manager sorts descending by:

```text
max(priority, 0) +
  (1 + (instanceId & 0xFFFFFF) * 3.725290742551124e-09) /
  max(1.0625, extentX, extentY, extentZ)
```

This combines the registration key at `0x1410873F9`–`0x14108744E` and the
priority addition at `0x141089370`. The comparator at `0x14159A3B0` and the
positive-result swap at `0x141599503` establish descending order. Equal keys
use the generic sort's exact unstable permutation: insertion below seven,
middle pivot at seven, median-of-three above seven and pseudomedian-of-nine
above forty with Bentley-McIlroy partitioning. The 34-case bounded CPU oracle
through 512 entries is `light-manager-equal-score-sort.json` (SHA256
`52d2f7acced0d798248706155bce3708626e4a28c229589da6ad757ea64fa29f`).
Sorting applies to the manager's current eligible set; sorting all cooked records
does not establish their captured GPU indices. The residency fade byte is
mapped to `t = saturate(byte * 0.003929273225367069)`, then `t*t*(3-2*t)`.
Unready resources are separately gated to zero fade.

## Hair spatial weights and ordered blending

`probe_spatial_weight()` follows the Hair shader's box and elliptical-cylinder
branches. The box branch computes directional boundary penetrations, takes
the larger penetration per axis, and returns
`max(1 - dot(penetration, penetration), 0)^2`. The cylinder branch shifts
and scales its inner ellipse according to the four X/Z falloff distances,
then combines radial and vertical penetrations with the same squared weight.
D3D saturation maps NaNs to zero, including the cylinder's center singularity.
The CPU multiply-add order retains the shader's precision in narrow falloff
bands.

The shader reads the lowest set lookup bit first. For each positive faded
spatial weight `a`, it accumulates `remaining * a` and then subtracts **a**
from remaining coverage. Processing ends once remaining coverage is zero or
negative. Accumulated samples normalize by their sum (floored to `1e-5`),
then blend with the default cube using any positive remaining coverage.
For example, faded weights 0.4 and 0.3 produce accumulated values 0.4 and
0.18, final local sample weights about 0.482759 and 0.217241, and default
weight 0.3. `blend_probe_weights()` preserves this ordering and normalization.
It reports specular sample weights before Hair shading. The sampling helpers
below now also recover parallax directions and the separate diffuse coverage;
connecting these helpers to resident viewport resources remains unfinished.

Use a **raw captured GPU buffer**, not the cooked DAT1 section, to check a
captured point and lookup mask:

```powershell
.\.venv\Scripts\python.exe tools\analyze_probe_buffer.py `
  --buffer $CapturedProbeBuffer `
  --world-point -230.588 9.146 670.816 --lookup-mask 0x40400 `
  --output (Join-Path $TransferOutputPath 'captured-head-probe-weights.json')
```

`$CapturedProbeBuffer` must point to the actual `g_EnvProbeEnvs` bytes exported
from that frame. The tool validates record alignment and lookup bounds, keeps
buffer indices and cube indices distinct, and supports masks spanning more
than one 32-bit word. This computer still lacks that captured buffer.

### Spatial verification

The expanded installed scan again processed 2,192 zones with zero errors:
85 probes in 42 populated zones, including 84 box records, one cylinder
record, and seven records with diffuse contribution enabled. The generated
`spatial-environment-probes.json` includes all decoded spatial fields and
sort keys while retaining the zone-local coordinate label.

An offscreen OpenGL 4.3 compute kernel translated from the paired Hair DXBC
checked **47,229 points** across all 85 installed records and six synthetic
cylinder/reflection cases. CPU and GPU weights were finite everywhere;
maximum absolute difference was **4.887581e-6**, mean **2.651224e-9**.
This used identity zone matrices only to isolate the kernel; it does not
establish actual zone placements. Evidence is in the enclosing workspace's
`artifacts/rcra-fur-continuation/probe-analysis/`, including
`verify_probe_weights_gpu.py`, `hair-probe-weight.comp`, and
`probe-weight-gpu-validation.json`. This verifies the spatial kernel against
an instruction translation, not a complete retail frame render.

The suite now passes 137 tests. New cases cover wire layouts, half-float
bounds, transform composition and reflection, directional/cylinder falloff,
sorting, residency fade, overlapping weights, lookup-word boundaries,
missing resources, and the buffer CLI. The test run used a fresh workspace
`--basetemp` because this sandbox cannot access the existing system pytest
temporary directory.

## Hair parallax, diffuse coverage, and visibility

The same paired DXBC supplies all three local cube fetches (disassembly lines
1168–1215). Let `P` be world position, `C` the record's capture position,
`R` the reconstructed Hair reflection direction, and `N` its reconstructed
anisotropic shading normal. Transform `P - record.position` and the ray into
the record basis. For each axis, choose the negative proxy plane if its ray
component is negative, otherwise the positive plane. The intersection time
is the minimum of `(selectedPlane - localPosition) / localRay` across axes.
Proxy bounds are in local distance units, not normalized influence extents.
This intersection uses a **box even when the influence volume is a cylinder**.

For mean primary/secondary gloss `g = max(meanGloss, 0)`:

```text
t = min(1.5 * g, 1)
captureOffsetScale = t*t*(3 - 2*t)
specularMip = 5 - 5*g
specularDirection = R * intersectionTime(R) + captureOffsetScale * (P - C)
diffuseDirection  = N * intersectionTime(N) + (P - C)
```

The diffuse fetch uses mip 5 and is enabled only by record flag bit 1.
A third fetch uses **uncorrected R at mip 5**, dotted with RGB weights
`(0.25, 0.5, 0.25)`, for the visibility denominator. It uses the specular
blend weights, including the uncorrected default cube where needed.
These vectors remain unnormalized as in the cube-sampling instructions.
No epsilon or positive-time clamp is added to the ray-plane division.
Exactly axial rays with negative-zero components can produce infinities and
NaNs; the low-level helper preserves this behavior. The JSON sampling plan
marks such directions nonfinite and writes null components.

Diffuse-enabled records accumulate the same raw `remaining * fadedWeight`
contributions as specular, but keep their own total `D`. Their final cube
weights are `rawContribution / D * saturate(D)`; the existing light-grid
diffuse color retains weight `1 - saturate(D)`. A full-weight specular-only
probe therefore leaves diffuse entirely on the light grid. It does not
redirect the specular default-cube remainder into diffuse.

After specular normalization/default blending, DXBC lines 1258–1274 apply:

```text
strength = min(1.5 - g, 1)^2
ratio = saturate(0.5 * gridReflection / max(coarseLuminance, 0.000001))
visibility = 1 + strength * (2*ratio - 1)
```

`gridReflection` is the scalar from the light-grid branch (`r27.w`), not its
RGB diffuse result. The environment intensity `cb6[45].w` is applied after
this visibility operation. `hair_probe_specular_visibility()` requires the
real inputs explicitly; it does not invent a light-grid scalar.

`probe_sampling_plan()` and the raw-buffer CLI now expose these fetches and
both blend-weight sets. Add all three arguments to the earlier CLI command:
`--reflection-direction X Y Z --shading-normal X Y Z --average-gloss G`.
Use the Hair shader's reconstructed vectors for that pixel, including its
anisotropic/frame-dependent normal. The CLI does not reconstruct those
vectors from mesh normals, sample the cube, or evaluate the BRDF.

### Viewport correction and GPU validation

The trace also identified an existing viewport error: Hair first sums the two
gloss values, then uses `sum * 0.25 + 0.5` to blend its environment normal
(DXBC lines 504–511). The viewport had halved the sum and still multiplied by
0.25. It now uses `meanGloss * 0.5 + 0.5`, with the variable renamed from
`averageRoughness` to `averageGloss` to match its input.

`probe-analysis/verify_probe_sampling_gpu.py` compares the CPU helpers with an
offscreen GLSL instruction translation and compiles the actual viewport
normal expression. Across 85 distinct installed records and two synthetic
rotated/mirrored records, 22,794 queries checked 45,588 parallax vectors.
45,333 were finite; 255 signed-zero degenerate cases matched the GPU's exact
NaN/signed-infinity classifications. Maximum errors were:

- relative parallax vector: `1.275415e-6`;
- normalized cube direction: `3.576279e-7`;
- viewport environment normal: `2.831221e-6`;
- mip/offset-scale/visibility scalar: `2.384186e-7`.

This used identity zone matrices only to isolate the kernels and is not a
retail frame comparison. The report and compute shader are saved alongside
the script as `probe-sampling-gpu-validation.json` and
`hair-probe-sampling.comp` in the enclosing workspace's evidence directory.

## Owning zone matrix trace

The world manager allocates zone instances with stride `0x270` at
`0x1413CF926`; its instance-array pointer is at manager `+0x120`.
The initializer `0x1413CACE0` writes an identity matrix to instance `+8`
at `0x1413CAE07`–`0x1413CAE34`.

One verified placement override is the zone-loading component path:

- `0x1413CEF00` copies a serialized reference from input `+0x14` to
  component `+0x4C` and a load flag from `+0x20` to `+0x54`.
- `0x1413CF430` resolves/creates that zone through `0x1413D3670`.
- At `0x1413CF49A`–`0x1413CF4B2`, the component's owner pointer at `+0x10`
  supplies the matrix through its first pointer (with a global fallback).
- Setter `0x1413CACB0` copies the four rows into zone instance `+8` and sets
  flag `0x20000` at `+0x188`.
- The previously traced probe loader `0x1413CD610` composes cooked probe
  matrices with that matrix before updating their manager records.

The initializer's identity value alone is **not evidence of a particular
zone's final world placement**. The owning actor's serialized/runtime transform
and its zone association still need to be resolved for the captured scene.
Disassembly is saved in `zone-manager-region.asm.txt` and
`zone-instance-component.asm.txt`; the installed `i29.level` was also extracted
for further static tracing. No automatic world placements were added.

RenderDoc is installed at `C:\Program Files\RenderDoc`, but this workspace
contains neither the original RDC nor a private-desktop capture helper.
`launch_live_game.bat` launches Forge, not the retail game. No retail game was
launched or hooked during this continuation.

## Indexed scene models and probe draw-list resolution

The owner trace reaches a renderer scene node, not a matrix embedded directly
in the gameplay owner. `0x140F17BF0` takes the scene definition from owner
`+0x38` (or actor `+0x40` as a fallback), creates the renderer node through
`0x1412A8430`, resolves its handle through `0x1412B64E0`, and stores its pointer
at owner `+0`. `0x140F17690` independently resolves the owning zone from the
signed zone index at owner `+0x0A` through `0x1413D2920`. This explains the
matrix pointer used by the previously traced zone-loading component.

Following this path exposed incorrect assumptions in Forge's art-zone parser.
The scene section has no 32-byte header, and its mixed node types do not have
one fixed stride. The verified model path is:

| Data | Retail interpretation | Consumer |
| --- | --- | --- |
| `0x06ABCAB2` | Scene definition bytes | `0x1413C6886` stores its descriptor at zone asset `+0x148` |
| `0x6987F172` | `u32[]` byte offsets relative to the scene section start | `0x1413CDDA3`–`0x1413CDEE7` |
| Model definition `+0x00` | Four row-vector matrix rows; translation is `+0x30` | `0x1412A81A0`–`0x1412A81F1` copies prebuilt nodes; `0x1412B6440` copies constructed-node matrices |
| `+0x5F` | Node type, zero for indexed models | Factory dispatch `0x1412A8430` |
| `+0x7C` | Serialized byte size with high prebuilt-node flag | `0x140F1A909`–`0x140F1A964` masks the flag for copying; `0x1412A817E` tests it |
| `+0x100` | Scene instance ID | Renderer registration `0x1412A834A`–`0x1412A838A` |
| `+0x110` | Signed 16-bit model-table index | `0x1413CDEEC`–`0x1413CDF13` |
| `0xC6A5905E` | `n` u64 asset IDs followed by `n` u32 DAT1 string offsets; section size `12*n` | `0x1413C5CAB`–`0x1413C5DDE` |

`core/zone.py` now follows those explicit offsets, preserves the complete matrix
and 64-bit instance ID, and bounds-checks each record and model index. It no
longer estimates model count from the scene size or counts the reference
table's string offsets as asset IDs. Non-model nodes between the offsets are
not interpreted as geometry. `core/level_assembler.py` uses the original matrix
for model exports, retaining all axes, nonuniform scale, and reflections.
The flat row-major sequence for the game's row-vector transform is already the
equivalent glTF column-major sequence; an additional transpose would be wrong.

The owning zone matrix is still separate. Retail applies it to the created
model matrix when zone flag `0x20000` is set at `0x1413CDF2E`–`0x1413CDF8B`.
The parser/export does not infer that runtime matrix from the initializer's
identity value. Indexed actor instances now use their own verified reference
and component tables, described below.

The inventory CLI accepts `--resolve-scene-models` to include draw IDs, find
matching indexed models and actor-bound models among the selected zones, and report all cooked
candidates with model installation status and zone-local matrices. Duplicate
IDs across zones remain multiple candidates; this does not select active
zones or reconstruct runtime residency. Example from the fork:

```powershell
.\.venv\Scripts\python.exe tools/analyze_environment_probes.py `
  --game-root 'F:\SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart' `
  --zone-filter megalopolis --zone-filter malinon --resolve-scene-models `
  --output ../../artifacts/rcra-fur-continuation/probe-analysis/resolved-environment-probes.json
```

The initial direct-model-only raw-section scan covered 2,340 matching installed zones and
177,404 indexed models in 163 zones: 175,208 prebuilt nodes and 2,196 constructed
nodes. All sampled paths and model indices decoded, and all those matrices
were affine. Of 14,526 distinct probe draw IDs, 12,434 matched indexed models;
639 of those IDs had multiple candidates, and 2,092 remained unresolved in
this scope. Those unresolved IDs must not be treated as missing TOC assets:
actor-bound models, other zones, and the second draw-list category need their
own consumers. Two genuinely uninstalled model references were found in 19
zone tables (`AA0FE90AD3F95C21` and `A3752E833A35E226`); missing assets are
distinct from malformed records. Raw validation and the production CLI report
are under `probe-analysis/`, outside the tracked fork.

The direct-model-only production CLI independently completed the same scan with zero parse
errors. All 13,090 matched candidate records agreed exactly with the raw scan
on zone ID, scene offset, model ID, and all 16 matrix components; 45 candidates
refer to uninstalled models and are marked accordingly. The wider `malinon`
filter includes overlays absent from the earlier narrower inventory, yielding
52 probe-bearing zones with 110 texture-source records and the same 29 runtime
records. `scene-model-validation-summary.json` records these checks.

Validation now includes 180 passing tests. The eleven direct-model regressions cover mixed
record sizes and gaps, explicit offset order, both ID kinds, parallel reference
arrays, invalid offsets/types/indices/sizes, and a transformed point under a
rotated, reflected, nonuniformly scaled glTF matrix. No fur shader changed in
this increment; the earlier four controlled fur captures remain its baseline.

## Indexed actors and component definitions

`core/zone.py` now replaces the legacy fixed-stride GP guesses with the actor
instance records consumed by `0x1413CBFD0`. Direct models and actors may
coexist in one zone. Section `0x70682CB8` contains 32-byte records:

| Offset | Field | Consumer |
| --- | --- | --- |
| `+0x00` | s32 name index into `0xDC625B3D`; negative means unnamed | `0x1413CC2F8`–`0x1413CC31A` |
| `+0x04` | s32 actor asset index | `0x1413CC131` |
| `+0x08` | u32 scene-definition byte offset into `0x06ABCAB2` | `0x1413CC13D`–`0x1413CC14B` |
| `+0x0C`, `+0x10` | s32 component start and u32 count in `0x50EDC53D` | `0x1413CC176`–`0x1413CC199` |
| `+0x14` | u16 instance flags | `0x1413CC338`–`0x1413CC33D` |
| `+0x16` | Preserved u16; meaning unestablished | Not interpreted |
| `+0x18` | u64 actor instance ID | `0x1413CC31F`–`0x1413CC326` |

Actor references in `0x78684035` use `n` u64 IDs followed by `n` u32 DAT1
string offsets, as verified at `0x1413C5E08`–`0x1413C5EEE`. Each scene record
retains its complete matrix, node type at `+0x5F`, and masked size at `+0x7C`.
Model-type actors also preserve the renderer ID at scene definition `+0x100`
separately from the actor-record ID. Probe draw lists resolve the renderer ID.

`core/scene_components.py` handles the shared 32-byte `<Q6I>` component layout:
instance ID `+0`, name offset `+8`, type hash `+0x0C`, flags `+0x10`, payload
offset `+0x14`, payload size `+0x18`, and preserved unknown `+0x1C`.
Payload offsets are relative to DAT1 byte zero, excluding any outer asset
header. `0x140FFD4D0`/`0x140FFD650` resolve and copy inline payloads. The path
at `0x1413CC1C0`–`0x1413CC295` uses type-factory defaults for an empty payload;
an empty record is not evidence of an external referenced definition.

Actor loader `0x140F18A20` reads header `0x32FAC8E0`, scene definition
`0x364A6C7C`, and component defaults `0x135832C8`. `core/actor.py` follows the
header's first u32 string offset for model-type scenes instead of choosing
the first `.model` string in the pool. Actor defaults and zone overrides are
exposed separately; type-specific merging has not been reconstructed.

`core/level_assembler.py` resolves each entry's actual actor/model asset. The
old round-robin assignment of available models to unrelated GP nodes has
been removed. Non-model scene types, absent assets, and unresolved references
are reported as skipped. The scene panel separates instance and asset IDs,
and its diagnostic dump uses the same parsed records as export.

The independent scan and production CLI both validated **14,555 actor
instances in 177 zones**, with **5,892 zone component bindings** and no
parsing errors. Scene types were 7,351 model nodes, 6,231 type-2 nodes,
952 type-4 nodes, and 21 type-1 nodes. In this scope the actor and renderer
IDs happened to agree for all 7,351 models, but the parser retains both fields.

The combined scan now has **12,465 matched IDs out of 14,526**, including
**31 newly resolved actor-model IDs** represented by 32 candidates. All
13,090 direct-model candidates remain identical; all 32 actor candidates
match an independent decode on asset IDs, scene offsets, actor IDs, and
matrix components. There are **13,122 candidates, 640 ambiguous IDs, and
2,061 unresolved IDs**; the 45 uninstalled-model candidates remain marked.
All 348 per-face match counts were independently checked. These are cooked
candidates across 290 scene-bearing zones, not a runtime-residency selection.

Evidence: `actor-dependency-validation.json`,
`resolved-actor-environment-probes.json`, and
`actor-model-validation-summary.json` in the enclosing evidence directory.
`scan_actor_dependencies.py` and `complete_actor_validation.py` reproduce the
independent checks. Eleven actor/component/assembly regressions also cover
mixed entries, distinct ID fields, invalid references, payload origins, model
string decoys, and missing/non-model actors.

## Prefab component identity and level catalogue

The previously traced zone-loading component is **`PrefabZoneComponent`**.
Registration at `0x14015AEB0` references its name at `0x1444D31B0` and
constructor `0x1413CF210`. That constructor installs vtable `0x1444D3160`,
whose first entry is the already traced initializer `0x1413CEF00`.
The registered type ID is **`0xF39305D5`**. The executable's CRC routine at
`0x141595870` uses initial state `0xEDB88320`, without a final inversion;
the equivalent Python expression is
`zlib.crc32(name.encode(), 0x12477CDF) ^ 0xFFFFFFFF`.
`DepthOfFieldVolume` independently produces its observed `0xEF9D58BF` ID.

No instance of this type was found in the 5,892 zone bindings or in the
**1,950 default components of all 562 distinct actor assets** referenced by
the 177 actor zones. All 562 assets parsed; none were missing, and no default
scene type differed from its placed instances. This narrows the search but
does not prove the final placement of the lighting zone. Results and the
bounded scan are `prefab-actor-defaults.json` and `scan_prefab_actor_defaults.py`.

The installed `levels/i29/i29.level`, asset **`95A02E80D5D79CF7`**, has type
**`0x587B60A6`**, accepted at `0x14107BEE0`. Forge now recognizes that type and
exposes its zone catalogue through `core/level.py` and the scene panel:

| Data | Verified meaning | Consumer |
| --- | --- | --- |
| `0x7CA7267D + 0x18` | u32 zone-reference count | `0x14107BF40`–`0x14107BF43` |
| `0x4E023760` | 12-byte records: u64 asset ID, s16 name index, preserved u16 | Loader `0x14107BF96`; ID accessor `0x14107D4D0`; 12-byte search `0x14107D500` |
| `0x2BA33702` | u32 DAT1 string offsets, selected by the signed name index | Loader `0x14107C098`; name accessor `0x14107D520` |

All **9,176 catalogue records** agree with the independent raw decode, and
all paths produce their recorded CRC64 IDs. The 133 names absent from
`hashes.txt` are also absent from the installed TOC; they add no installed
zones to the current scan. Malinon lighting zone `81D3F7A27166B843` is at
catalogue index **251**, with name index **183**, resolving to
`levels/i29/instance/Malinon_Intro/Malinon_Intro/malinon_intro_lgt.zone`.
The catalogue supplies membership and names, not an instance matrix or the
active zone set. The level's region/checkpoint consumers are the next static
association trace; header `+0x0C` is the region count, with records at
`0x396F9418`, and header `+0x1C` counts checkpoint records at `0x3395AEC1`.
Those record layouts are now implemented as described below.

Five level regressions cover dispatch, signed/out-of-order name indices,
outer-header handling, and malformed tables. An offscreen Qt check displayed
all 9,176 catalogue entries and switched back to a mixed actor/model zone.
Evidence is `level-catalogue-validation.json`, `continued-14107bee0.asm.txt`,
and `level-accessors-after-load.asm.txt`. The full suite passes **180 tests**.

No serialized reference to Malinon lighting zone `81D3F7A27166B843` was found
in the 2,340 scanned zone blobs. The level catalogue contains the verified
reference above; absence in this subset does not establish its final world
matrix. Continue the level association trace or recover it from a capture.

## Level region and checkpoint dependencies

`core/level.py` now decodes all **1,216 regions** and **860 checkpoints** in
`95A02E80D5D79CF7`. The region table `396F9418` has 36-byte records:
u64 ID at +0, then s16 kind/name/bounds/parent at +8/+A/+C/+E;
child start/count +10/+12; primary-zone list start/count +14/+16;
replacement list start/count +18/+1A; checkpoint start/count +1C/+1E;
property start/count +20/+22. Zone lists index the signed-short table
`95F91E24`, whose values index the level zone catalogue. Replacement lists
allow -1. They are paired substitution candidates, not additional active zones.

Region names use `4130D903`. Bounds use `C30D92B6`, 24 bytes each, preserved
without assigning unverified meanings to their last three words. Checkpoint
records at `3395AEC1` have 48-byte stride: ID +0, name index +1C, region index
+1E, property range +20/+22, and float3 position +24. Names use `2236C47A`.
Unknown fields remain in the raw records. Accessors and the region consumer
at `1419A1A30` establish parent dependencies; `1419A1FD0` handles the paired
primary/replacement lists and runtime property decisions.

`tools/analyze_level_regions.py` accepts explicit region indices or exact
checkpoint names and reports both declared lists and the executable selectors.
The kind-4 builder stores the selected root at runtime state `+0x1158`, walks
the root's children from record `+0x10/+0x12`, and consumes each child's
primary-zone list at `+0x14/+0x16`. It builds one 0x60-byte record per child
(maximum 0x800), filters zones through two 0x780-byte runtime bitsets, and
stores the retained union at manager `+0x20` and partition zero at `+0x7A0`.
The root's own primary list is not read on this path. Megalopolis root 61 has
241 children and 1,848 distinct child-primary inputs; its separate 486-entry
root list has no overlap with them.

The selector at `0x1419A1A30` handles kinds 3 and 5. It visits exactly the
immediate parent first and the selected region second, consumes both primary
lists, and deduplicates them against the supplied runtime bitset. For Malinon
region 21 and parent 20 this yields 29 unfiltered dependencies, including
catalogue index 251. These executable paths are exposed by
`LevelInfo.streaming_region_zone_candidates` and
`LevelInfo.dependency_region_zone_candidates`. Instruction anchors, evidence
hashes, all nine kind-4 roots, reverse zone membership, and independent raw
range checks are preserved in `region-streaming-selection.json`,
`level-region-validation.json`, and `level-region-dependencies.json`.

The saved Hair frame's active probe is now joined end to end. Record 10 stores
cube 18 and uniquely matches runtime draw-list probe `F896FB5315175B7C` in
zone `9C292F5F8A79EEC2` (`tile_zz27_lgt.zone`), catalogue index 3976. That zone
belongs to kind-5 region 184, child ordinal 122 of Megalopolis root 61. Its
captured 124 static record bytes match the cooked record under identity zone
placement, and 29,359 captured screen tiles can select it. Cube 18 has no
installed baked-asset match. Malinon Day texture `837545B07B72296F` instead
matches captured cube 40, which is inactive in this frame. The reproducible
CPU-only join is `tools/analyze_captured_probe_provenance.py`; its report is
`captured-probe-provenance.json`. Runtime child-mask state and scene rendering
for the active draw-list probe remain outside this static proof.

## Light-grid kernel and combined indirect replay

`core/light_grid.py` and `core/hair_light_grid.glsl` recover the matching Hair
shader's complete grid branch. Its eight corners use world coordinates minus
0.5, a 64^3 ring lookup of 16^3 bricks, and x-fastest brick/sample addressing.
Lookup bits 12..31 select the record base. Per-axis interpolation is the mean
of linear and smoothstep weights. Packed occlusion planes and the decoded
surface normal modify the corner weights; each has a minimum of 2^-18.

Each 16-byte record contains three radiance words and one occlusion/scale word.
Radiance words contain positive/negative 16-bit directional samples with 6-bit
luma and two 5-bit chroma codes. Direction-squared weights combine axes before
signed-square chroma reconstruction. The scale nibble becomes a synthesized
half exponent. Reflection uses a separate directional luma value. Diffuse
receives world intensity and the ambient-fill floor; reflection does not.

The branch also includes lookup/record fallback weights, forced fallback beyond
512 units in X/Z from the camera, default-cube sampling, distant height mapping,
four slices of directional GI data, and the transition above the height field.
The exact 559-instruction slice is mechanically translated from the retained
hexadecimal DXBC disassembly for an independent GPU oracle. **4,096 queries**
pass against both implementations; see `light-grid-gpu-validation.json`.

`core/hair_probe_lighting.glsl` is the reusable probe kernel, validated by a
separate 4,096-query comparison. `core/hair_lighting_replay.py` connects both
kernels to explicit texture and buffer resources. A 192-query upload/replay
fixture passes with maximum absolute error **8.9407e-8**. The grid uses decoded
normal r6.xyz; local probe diffuse uses environment normal r21.yzw. These are
separate replay inputs. See [HAIR_INDIRECT_REPLAY.md](HAIR_INDIRECT_REPLAY.md)
for the CLI, input schema, output meanings, and verification scope.

## Cooked brick stream recovered

Malinon day grid `97BE230CA4381B39` has a separate **34,383,747-byte** streamed
span. Its SHA256 is
`0797756f290d97b301065f61544e6fdc5457024d35b7b0e0505c3e65b4ca924a`.
The last asset offset equals that complete stream size. Loader `1410CA910`
binds the 12-byte float3 position records in `27204B67`, the 8-byte header at
`101A2196`, and optional u32 stream offsets at `C72A514C`. There is one more
stream offset than positions.

Worker `1410A6360` invokes `14109DA40` with a 65,536-byte output brick. That
wrapper first calls decoder **1410A06A0**. Each brick begins with 128 little
endian u64 packets containing 4,096 two-bit cell kinds, read high pair first
within each packet. For N kinds 2/3, six N-element halfword planes encode the
three radiance words, followed by N scale bytes. Every kind 3 adds a three-byte
occlusion plane. Exact size is `1024 + 13*N + 3*kind3Count`.

`core/light_grid_assets.py` implements this first decode stage. All **1,796
bricks / 7,356,416 records** consume their byte ranges exactly. Kind counts are
0: **1,762,540**, 1: **3,099,741**, 2: **2,453,839**, 3: **40,296**.
Kinds 0/1 retain sentinel words `83F80000` / `8008003F` and unresolved indices.
They are not final black samples. The wrapper can perform two interpolation
passes and subsequent sentinel filling through `14109DD40`, `14109E880`,
`1410A1200`, `14109E290`, and `14109EC00`. `core/retail_light_grid.py` now executes
that verified path in an isolated Unicorn VM, with Windows CRT expf/logf and
MXCSR 0x1F80. It does not start or attach to the game. Eight varied bricks pass
first-stage byte equality and preserve every authored record through filling.
The optional CLI switch is documented in `HAIR_INDIRECT_REPLAY.md`. Actual
runtime gating, floating-point state and resource binding still
require comparison. See `light-grid-retail-vm-validation.json`,
`malinon-light-grid-decode.json`, and the saved
`continued-1410a06a0.asm.txt` / `continued-14109da40.asm.txt` evidence.

## Inline grids and runtime lookup reconstruction

The scan of all **648 installed grid metadata assets** found one containing
the brick center `(-232,8,664)` derived from the earlier Ratchet coordinate:
`83971B86890068A0`, Sargasso `tile_l25_light_grid_overcast.zonelightbin`, brick
55 of 354. This is a coordinate candidate, not proof of the frame's bound
lighting condition. None of the Megalopolis/Malinon grid assets matches that
center. Evidence: `all-grid-coordinate-candidates.json`.

A separate scan of **1,410 Sargasso zones** found **91 texture-backed probes
in 27 zones**, with no parse errors and no runtime draw-list probe sources.
The eight tile_l25 zones contain no probe records themselves. Nearest stored
probe centers and texture conditions are recorded in
`sargasso-nearest-stored-probes.json`; the complete inventory is
`sargasso-environment-inventory.json`. These do not establish the old capture's
record 10/cube 14 or the active zone transforms.

This asset has compressed inline data. Its 36-byte outer header declares
4,328 metadata bytes and 1,500,473 compressed bytes. Worker **1410A77A0** calls
**1415A29A0** to expand a second DAT1. Its `13F4AF3B` section is the 2,546,228
byte brick stream; `C72A514C` contains 355 offsets ending exactly at that size.
`load_light_grid_asset` handles both storage modes and strictly rejects broken
compressed data and container ranges. All 354 bricks consume their exact byte
ranges. Brick 55 agrees with the original decoder, preserves all 414 authored
cells, and fills 3,682 missing cells. Evidence: `sargasso-l25-light-grid-decode.json`.

The lookup construction is now traced end to end:

- **1410CA910**, specifically `1410CAA1D..25`, sets the grid object's +0x30
  directly to the cooked position section. **1410A1AC0** reads that pointer
  at `1410A1CC0` and copies each float3 at `1410A1D81..8F` into the work list.
  No zone transform is applied on this path.
- **1410A1850** hashes `floor(position / 16) & 63`, with x fastest, into the
  64^3 ring. The stored center above hashes to **167985**, which also addresses
  all eight shader corners for the earlier coordinate. Local sample indices
  are 3720, 3721, 3736, 3737, 3976, 3977, 3992 and 3993.
- **1410A1E20** updates a per-brick byte fade and emits 8-byte upload commands:
  lookup address u32, resident slot u16, operation u8, fade u8.
- **1410A1920** writes `(slot << 12) | ((0xF00F - 0xF1 * fade) >> 6)`.
  Fade 255 means fully present, 0 means fallback. Operation 2 removes the
  entry by writing the manager's fallback slot with low bits `0x3C0`.
  Hair later masks low bits with `0x3FC`; preserve the original unmasked word.
- **1410A3300** creates the permanent fallback brick by initializing a descriptor
  with **1410A13D0**, packing it using **14109EC00**, and repeating the record
  `843F843F 843F843F 843F843F 83F81FC0` 4,096 times.

`core/light_grid_resources.py` and `tools/reconstruct_light_grid.py` expose
explicit reconstruction with compacted replay slots and caller-specified fade.
Position hashing and fade packing pass **4,096 position queries and 1,792
updates** bit for bit against original x86 in the isolated VM, including all
fade values and removal operations. The fallback record also matches.
See `light-grid-lookup-vm-validation.json` and `light-grid-manager-runtime.asm.txt`.
This resolves the coordinate/lookup operations; active assets, state, priority,
streaming residency and the original captured resource remain separate evidence.

The valid-entry collision decision is also recovered: **1410A2160** compares
the current brick's Chebyshev camera distance against **512**, and the new
candidate against float32 **409.6000061035156**. If those inclusion results
differ, the included entry wins. Otherwise strictly higher priority wins;
equal priority preserves the current entry. Without a camera, only priority
is compared. `should_replace_light_grid_brick` reproduces this bounded decision.
**331** isolated original-instruction checks cover all 256 priority pairs,
radius boundaries, missing camera, CPU table metadata and replaced-entry flags.
See `light-grid-selection-vm-validation.json`. Full lifecycle state is not
inferred from this operation.

The entire candidate asset has now been interpolated: **354 bricks**, including
350 distinct encoded payloads, all exact before interpolation and preserving
all authored samples. This fills **1,282,753** cells. At explicit uniform fade
255, `sargasso-l25-grid-reconstructed.npz` contains **1,454,080 uint4 records**
including the permanent fallback. Data SHA256:
`1cab416f92018a19ee410eae3a5550e652f2c7a5c5490532d5cc1425dcfa8164`.
The grid passes 4,096 original-DXBC/CPU/shared-GLSL comparisons using these
installed records and controlled query constants, with maximum absolute error
**4.7684e-7**; 2,562 queries use no fallback, and 2,048 enable controlled distant
GI. The combined replay's actual resource upload passes another 192 queries,
maximum error **1.1921e-7**. See `sargasso-l25-light-grid-gpu-validation.json`
and `sargasso-l25-indirect-validation.json`. This is resource/kernel validation,
not a matched-frame capture comparison.

## Captured manager placement and lookup frame

The saved frame's complete 22-record active prefix is now joined to the 139
cooked probe candidates. Placement-invariant fields uniquely identify 19
records. The three repeated runtime-draw-list definitions are each resolved by
their unique exact identity placement. The result contains 10 zones: seven are
identity placed and three overlay zones have a shared rigid transform recovered
consistently from every probe in that zone. Their translation spread is at most
6.10352e-5 after solving from float32 record values. All 22 records appear in
strictly descending `probe_sort_key` order.

`ProbePlacement` keeps the authored probe, row-vector zone transform, resource
index, resident cube slot and fade separate. `build_selected_probe_shader_records`
sorts manager entries, then applies the nonzero resource-indexed selection mask
without conflating that gate with fade. `build_probe_frame_lookup` connects that
manager boundary to exact camera Z-bin packing/generation and the saved-depth
shell raster candidate. Its full and opaque bitfields can be regenerated
from current matrices and linear depth without replaying or opening the game.

The cooked-to-frame validation preserves captured manager order, matches every
placement-invariant byte, and reconstructs 14/22 first-124-byte records exactly;
the remaining records differ by no more than 6.10352e-5 because the zone matrix
was solved from rounded output records. All 22 camera Z-bin words and the shared
scale are bit exact. The opaque screen result retains the established 26 of
712,800 boundary mismatches and IoU 0.999716791. Evidence is
`captured-probe-invariant-matches.json` (SHA256
`e2a8002f44f961f7e4a7d2f71948785a6b0e147525f65f2e6bcf62e88f7483d6`)
and `cooked-probe-frame-validation.json` (SHA256
`0ffc73c85dde5dcb0fdb7e26164fbbef967caba8b3f8aff92c566ecdd22f62a5`).
The matrix-derived frustum path selects every one of the 22 captured active
probes before reproducing the same Z-bin and screen results.

These recovered transforms describe this capture. Future views still need the
runtime owner that supplies zone transforms, the active-resource lifecycle and
transition indices, condition-specific cube assignment and residency fades. The software lookup
still needs the final fixed-function D3D boundary.

The cylindrical lookup topology is now recovered statically. Record flag bit 0
selects the executable's stream at `0x1432D3C60`: a 16-segment circumscribed
cylinder with 192 vertices, 64 outward triangles, cap centers at Y +/-1, and
float32 ring radius 1.0195910930633545. The generated stream is byte exact to
all 2,304 executable bytes, SHA256
`8fe24507143963629632edf3c199c15a0bc0911d9af08280adf985f777d7cd46`.
`rasterize_probe_screen_lookup` now selects that stream or the 36-vertex box
stream per record. There is no saved active round probe for an output-level
comparison, so this closes topology and shared vertex projection rather than
the D3D fixed-function boundary. See `probe-shell-topology.json`.
For runtime draw-list probes, resolve the indexed scene instances against the
active zone set, render all six faces with production lighting/material state,
then recover filtering and mip generation. Keep explicit texture overrides
distinct from verified reconstruction of the captured local probe array.
