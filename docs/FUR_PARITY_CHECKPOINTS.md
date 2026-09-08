# Fur parity checkpoints

## 2026-09-05 01:15 UTC — static spatial-tree population

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260905T011509Z-spatial-tree-population/`

This CPU-only checkpoint closes static tree lookup and population through the
verified subdivision boundary. The retail tree uses 0x20-byte nodes with eight
uint16 slots. Lookup subtracts the signed-int16 root origin once, consumes one
coordinate bit per depth in x/y/z slot order, and distinguishes cells from child
nodes with the slot high bit. Subdivision derives child origins, parent links and
depths, allocates cells and pages on first octant use, preserves source append
order, reuses occupied children and rebuilds every child bound with the existing
signed-int16 sphere union.

Ten lookup cases, six allocation/link-prelude cases and three full redistribution
cases covering 16 entries match the bounded native oracles. Native and port
report SHA256 pairs are
`81b02ec7ff56ffc5af8bf04b0ee5eb2d3280edb47466217ca4d8e5704023adc7` and
`85b61894e9499e8098e1b6cef019f6d6045dd98670964607857dcbd92564fdd1`,
`44969d03fcd4e628ab2bf6b9d9b14b3d05f5d1e2ab7415c703bc692a25122e12` and
`e42ad75baf30befcffe586fa7d2c2c20bb961008ed870d6fc81d8db1d3fe6b88`, and
`b1b90db7e8e6af853479e5b0622104136ad6d306199b6260308a87b0f5fa68dd` and
`3f34021b52d11f5106072fe218815525f52eddf00d337199971a8fb5b8309698`.
The refreshed 83-range composite manager report has SHA256
`8ca01bcd682ce7045f4c9450fd938bb8a359faa22d2639ecb4f1521206770d8e`.

All 590 CPU tests pass; the 198-test local-light module passes independently.
All 53 offline shader cases remain at the checkpoint-17 validated boundary.
The archive contains 157 source files and 20 evidence files, 177 entries total,
and is 14,178,798 bytes. Archive SHA256:

`01b22933fbdb2bec15600c89be17b06eb930826a91c90c5d2923acf654c66e7d`

Manifest SHA256:

`7cd35e4274cca6e4d670c533fbf8f7f975b84d49e8265508cd26e49f68e2f7e5`

The manifest links checkpoint 19 by archive SHA256
`3a0fe9696d642d4388add23dd9485ad2bfc44d54e249fad6b1302da378cc703e`.
Empty-node collapse/removal symmetry, live spatial-database contents and scene
membership, populated manager depth words, resolved-resource inputs, scheduler
completion order and concrete placement values remain external. The game,
RenderDoc, RenderMan and GPU workloads were not launched for this checkpoint.
## 2026-09-05 00:06 UTC — manager hierarchical depth

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260905T000619Z-manager-hierarchical-depth/`

This CPU-only checkpoint closes the static manager hierarchical-depth consumer.
Function `0x14118CE60` projects all eight source OBB corners, computes the
conservative 16-bit object threshold and clamped pixel rectangle, checks four
level-zero corners, chooses a mip from the rectangle span, rejects from four
coarse corners, and otherwise scans the level-zero rectangle with masked
signed-int16 maxima. The production API accepts all frame-owned values and depth
levels as an explicit snapshot and returns the exact bounds, threshold, initial
mip, selected mip, decision path and visibility result.

Ten bounded native cases cover near/camera retention, threshold equality, depth
capping, mip-zero and mip-one rejection, the wide level-three path, visible and
occluded base scans, an inconsistent supplied hierarchy and fractional nonunit
axes. The native and independent port report SHA256 values are
`993a854927faefe5b32caeab38fcfe3e718b8fb70ded32a1e8fbf70172fb6f75` and
`2d3bc22fc10bf3b7a85fe5fd386f5aacb0373579666cec260527a155ea890714`.
Their shared semantic output SHA256 is
`0680e5a4f26a9e629e235b5583b8f1edb40a6f7702770cd5d41d96b889d1c663`.
The refreshed 76-range composite manager report has SHA256
`4a91a4bfe550f6b96f32749530e9a2b95d918a2898afa8a9f241691709f85892`.

All 581 CPU tests pass; the 189-test local-light module passes independently.
All 53 offline shader cases remain at the checkpoint-17 validated boundary.
The archive contains 157 source files and 12 evidence files, 169 entries total,
and is 14,160,415 bytes. Archive SHA256:

`3a0fe9696d642d4388add23dd9485ad2bfc44d54e249fad6b1302da378cc703e`

Manifest SHA256:

`8bf0361fb8448e6f67adc0370c39a1e1a7fbf0c6cabeffd3aca758d3bb20daed`

The manifest links checkpoint 18 by archive SHA256
`0ce3eebcc2f5c66a6d9c2e7bc1804684e249d49ef7c7054f465eb3b50f478068`.
The live frame's manager values and populated depth words, spatial-database
contents and tree population, resolved-resource inputs, scheduler completion
order and concrete placement values remain external. The game, RenderDoc,
RenderMan and GPU workloads were not launched for this checkpoint.
## 2026-09-04 23:10 UTC — scene-light owner-selector provenance

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T231056Z-scene-owner-selector-provenance/`

This CPU-only checkpoint pins the complete external owner-transform source chain.
Constructor `0x140FDFA10` normalizes source-descriptor byte `+0x3B` into
owner-state byte `+0xC6`. Selector `0x140FE5C30` prioritizes the embedded
`+0x60` override, the already-world fallback, a non-null `+0x10` holder
transform, then the null-holder fallback. Its four-case native and production
output SHA256 is
`f896b0d5835c075302996f6b690a9750586efaad37624dfdb00352ed26d0d1ae`.
The existing four-case composition output remains
`6d191d26b08857050303e9d4f7b5dd2fb7a54aadaf7d8a667f0dc04c7a7179ce`.

The static source audit has SHA256
`53170f909032cbca6fc2af5e00c6dc69868a1b026dc7ec54aa47f0b8092f15a2`.
It records nine exact instructions, five unwind fragments, zero direct
file-image references to the placement entry, and 1,932 RIP-relative reads or
address loads of runtime-backed fallback `0x146838510`. The fallback lies in
unbacked `.data`, so this checkpoint does not infer its concrete runtime value.
The native and port report SHA256 values are
`9f36d5aad10a5bfb0fadce0e5410c87460341a4ea4f3b57eb67bc5c9c7a3daf8`
and `84b79696fc97d3425bae6d5a81fb563d16a948474c75bb2af0a347d8b3f15db8`.
The 17-range integrated scene-light report has SHA256
`b3caea75910e954aed6c4f3b569c7e642c22dc9ef84ce9d4a789377d4d73f3e0`.

All 574 CPU tests pass; the 182-test local-light module passes independently.
All 53 offline shader cases remain at the checkpoint-17 validated boundary.
The archive contains 157 source files and 26 evidence files, 183 entries total,
and is 14,217,045 bytes. Archive SHA256:

`0ce3eebcc2f5c66a6d9c2e7bc1804684e249d49ef7c7054f465eb3b50f478068`

Manifest SHA256:

`8d746bd426a2b04a7b1f52c9634541462116dd09d6b4cb1908a0cd689d81ecf0`

The manifest links checkpoint 17 by archive SHA256
`a694b1874be5f1a30152746a09fd67ed465dc7359a90cea370707d704dba8dbb`.
Concrete frame owner-transform values, live spatial contents, the populated
manager depth hierarchy, resolved-resource inputs and scheduler interleaving
remain capture-dependent. The game, RenderDoc, RenderMan and GPU workloads were
not launched for this checkpoint.
## 2026-09-04 22:26 UTC — scene-light owner transform

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T222619Z-scene-owner-transform/`

This CPU-only checkpoint closes the recovered scene-light external-transform
ownership boundary. Placement wrapper `0x140FEEE07` runs subtype dispatch first,
then selects the raw record matrix for its already-resolved flag or computes
`record_local * owner_transform` through `0x141627F80`. Runtime helper
`0x1412B6BF0` applies the selected matrix, canonicalizes its homogeneous column,
and reclassifies or dirties the indexed light only when the transform changes
past the native epsilon. Four bounded native and production cases match bit for
bit; their shared output SHA256 is
`6d191d26b08857050303e9d4f7b5dd2fb7a54aadaf7d8a667f0dc04c7a7179ce`.
The native and port report SHA256 values are
`687f556684665e0664b91bffdcc5a0d62ac463daec8a969b82215bbc99fecadf`
and `8a3686bcdc8ddd605104e83c599eb90a31fb8bda00ebdfc282500930f8a5168d`.
The 15-range integrated scene-light report has SHA256
`0ada9f42234de65ab3576ed4d1899aeb67427505bb1c1045ad1466b2d129cb4e`.

This checkpoint also carries the completed worker intermediate/final flush
ordering introduced after checkpoint 16. Its native and port reports have
SHA256 `7b5d2685cc75a6c7531d4d309036fe0edbd34ee373f54796339e0ce72728e19f`
and `26bcd6b3693230ad8e7cb71a2ef00c54d5c92f195add4e308406851871c61421`.
The composite manager verifier pins 76 executable ranges and 15 data ranges at
SHA256 `fc738c57dffdeb4615ed5fa3914f6e46f8af53f2f1fb3d3f9d7a8421f34d4c59`.
All 572 CPU tests pass; the 182-test local-light module passes independently.

The compact archive contains 157 source files and 22 evidence files. Independent
validation checked CRC, length and SHA256 for all 179 entries, found no
duplicates, and verified the checkpoint 16 predecessor link. The 14,197,586-byte
archive SHA256 is
`a694b1874be5f1a30152746a09fd67ed465dc7359a90cea370707d704dba8dbb`;
the manifest SHA256 is
`87e58fca44b9e8b68c313ece174b8a65fa5f45ae73a0e9939f9f07fcff284555`.

Concrete frame owner-transform values, live spatial contents, the populated
manager depth hierarchy, resolved-resource inputs and scheduler interleaving
remain capture-dependent. The game, RenderDoc, RenderMan and GPU workloads were
not launched for this checkpoint.
## 2026-09-04 21:46 UTC — manager optional spatial resolution

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T214601Z-manager-optional-spatial-resolution/`

This CPU-only checkpoint closes the optional spatial worker's coarse and bounded
resolution paths. Retail block `0x1412B8FB0..0x1412B9108` matches six mask,
primary-sphere, optional-exclusion, direct and ambiguous cases. Explicit raw
0x100-byte pages walk newest to oldest and split source indices into direct and
exact-refinement buckets. The bounded resolver emits direct sources first,
preserves the native optional OBB result order and applies capacity truncation.

The composite manager verifier pins 73 executable ranges and 15 static data
ranges. Its SHA256 is
`ca2e753d40b3aa302dbb3942fdabca53dbdd5fb7b509c7b79d6404d0c0c888cf`.
The optional classifier oracle and port reports have SHA256
`7accdfc006f6f20ee81ecc7b97b79dde0cba25c0ac52635dc0e3bad464a78b62`
and
`e1ab7a1a012a6dc01cc57040c2732f4734b6339eeb524767693b40aea79a0086`.
The optional page/resolution report has SHA256
`204784599a701d9037f30d2470f47e0a33960280ad674e16c9f7873a98e75829`.
All 567 CPU tests pass; the 180-test local-light module passes independently.

The compact archive contains 157 source files and 45 evidence files. Independent
validation checked CRC, length and SHA256 for all 202 entries, found no
duplicates, and verified the checkpoint 15 predecessor link. The 14,218,414-byte
archive SHA256 is
`a7a09fc4b8a5eba3efde4b396ffaf54d69bc100c937d61db1b7b856781f17e47`.

The remaining static worker gap is intermediate 1,024-pointer flush ordering.
Live spatial contents, the populated manager depth hierarchy, frame descriptors,
resource/placement values and scheduler interleaving remain external. The game,
RenderDoc, RenderMan and GPU workloads were not launched for this checkpoint.
## 2026-09-04 19:27 UTC — manager spatial refinement and cells

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T192738Z-manager-spatial-refinement-cells/`

This CPU-only checkpoint closes both in-place primary spatial-refinement
branches. Helper `0x1412B72A0` evaluates source OBB support against all 16
primary planes; `0x1412B78B0` repeats that test and applies the optional
four-plane exclusion descriptor. Five cases and 16 sources match the basic
helper, while five cases and 20 sources match the optional helper, including
boundary sign bits and ordered compaction.

The worker-facing cell front end is recovered too. `0x141603A80` returns AABB
intersection and full-containment flags, `0x141603D40` emits ordered uint16 cell
indices at both observed strides, and the consumed intersection output of
`0x141603FE0` matches all eight oriented cases. The remaining unconsumed output
from that last helper is isolated as the input-OBB-covers-query flag.

All 561 CPU tests pass; the 174-test local-light module passes independently.
Python compilation and `git diff --check` pass, and all 53 offline shader cases
remain green. The manager report pins 56 executable ranges plus seven data
ranges and has SHA256
`7045f042958f8f2c6f83dbbc8026cb724cf41fa5c75492926389716a4cff7ab8`.
The primary and optional refinement port reports have SHA256
`4b2e82fba60065366112b9b771b14bbedf100fee3b2206fd400a4bc065544040`
and
`bd8b20e2338c93452b0bf6eb9a7eeacf26bd299b8cb41682335a692893081946`.
The cell-classifier oracle and port reports have SHA256
`54a75db361683fdd21f7e804a9016e2ed2a2c6b5864b4805b7e1a30b9a47fed6`
and
`a1aec9b5fa1eaaa8456aeb89f10fec875c0868231e5b01968a83649911d87c42`.

The compact archive contains 157 source files and 46 evidence files. Independent
validation read 47,215,268 uncompressed bytes, checked CRC, length and SHA256
for all 205 entries, found no duplicates, and verified the checkpoint 14
predecessor link. The 14,350,196-byte archive SHA256 is
`14e937cf0e01a96f126fcad1c49ae12d6824154a66be391f1b7e56d21caffa6a`.
This ledger entry is the only intentional fork source delta after the immutable
archive.

The live spatial database, manager depth hierarchy, frame descriptors, captured
resource/placement values and runtime scheduler order remain external. The game
and RenderDoc replay were not launched for this checkpoint.

## 2026-09-04 17:11 UTC — manager alternate primary descriptor

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T171146Z-manager-alternate-primary-descriptor/`

This CPU-only checkpoint closes the alternate view-flag primary-query path.
Owner `0x1412155C0..0x1412156DA` selects the common builder or the alternate
builder at `0x1416010A0..0x141602173` from manager `+0x438` bit 1 and
preprocesses its three axes, extents and translation. The alternate builder
emits six signed OBB-axis planes and ten normalized axis-pair planes in the
same component-major 0x100-byte layout. Nine ordinary, nonorthogonal and
degenerate cases reproduce the retail executable bit for bit, including signed
zeros; owner and direct-builder outputs agree in every case.

All 556 CPU tests pass; the 169-test local-light module passes independently.
Python compilation and `git diff --check` pass, and all 53 offline shader cases
remain green. The manager report pins 52 executable ranges plus seven data
ranges and has SHA256
`62a00b753d5881d8a4a85c36f6202e186079cbb909cac079536d418abeed0a13`.
The alternate oracle and independent port reports have SHA256
`bade3470b43bc63b992b4f89d1a2aa6924ba59a40312cb5e51025aee11c555e6`
and
`039244de6a160e7e5fd6cdd5d2de1b895ca4c96eb18d449db6bf08263229e775`;
the nine-case port output hash is
`0bc515edc8156b77c57ba84d93ea2cbbbe71afda578c50a14773617fb9c54da5`.

The compact archive contains 157 source files and 25 evidence files. Independent
validation read 46,718,372 uncompressed bytes, checked CRC, length and SHA256
for all 184 entries, found no duplicates, and verified the checkpoint 13
predecessor link. The 14,266,143-byte archive SHA256 is
`c6aaeaed1c75bc328bd2f4cdcaf05281fc4aec5cd09522ca9e1b5ffe288e1c9b`.
This ledger entry is the only intentional fork source delta after the immutable
archive.

The live spatial database, populated manager depth hierarchy, captured
resolved-resource and placement inputs, runtime scheduler completion order and
active-Hair local-light output validation remain open. The game, GUI and
RenderDoc replay were not launched for this checkpoint.

## 2026-09-04 16:41 UTC — manager primary query descriptors

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T164139Z-manager-primary-query-descriptors/`

This CPU-only checkpoint closes the common primary-query descriptor and its
optional override. The common path copies six manager planes, derives ten more
from eight edge points with the retail overflow-safe plane helper, and packs
the 16 logical planes into the exact component-major 0x100-byte layout. The
optional path replaces planes 11 through 15 from the manager origin, center,
axis offset, extents and terminal normal, then copies zero to two authored tail
planes into the final slots. Two base cases and all four enable/tail-count
override cases match their bounded retail-executable oracles bit for bit.

All 552 CPU tests pass; the 165-test local-light module passes independently.
Python compilation and `git diff --check` pass, and all 53 offline shader
cases remain green. The manager report pins 50 executable ranges plus six data
ranges and has SHA256
`25afe5fd9c8bec9a93dca6c4f37435700ecdbf5ef638d5fd9e1ff0d1519c23a4`.
The common-primary oracle and port reports have SHA256
`0d596d3c4b395c4e24cd615b2792906a636cec6f98daed4491b659eea19a8b47`
and
`028210af8958d9741dfc5106ac7b60b66c3a81338705d6dbb30d189b8f0ead21`.
The override oracle and port reports have SHA256
`19f6c490ffecdb37563f308700ad2906ef438fef7f13bc9cf1332bed009f209a`
and
`11a43e678d0a45901ae0b63355f7e283a83e9629597f81f56afee72aa4b1b1c6`.

The compact archive contains 157 source files and 19 evidence files. Independent
validation read 46,518,782 uncompressed bytes, checked CRC, length and SHA256
for all 178 entries, found no duplicates, and verified the checkpoint 12
predecessor link. The 14,234,083-byte archive SHA256 is
`16e0be5ff72ba08698e97c63f268842d84af100d6913482c3f22cc489e450d1f`.
This ledger entry is the only intentional source delta after the immutable
archive.

The alternate view-flag primary builder at
`0x1416010A0..0x141602E09`, the live spatial database, populated manager
depth hierarchy, captured resolved-resource and placement inputs, and
active-Hair local-light output validation remain open. The game, GUI and
RenderDoc replay were not launched for this checkpoint.

## 2026-09-04 15:41 UTC — exact manager equal-score priority ordering

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T154148Z-manager-native-priority-sort/`

This CPU-only checkpoint closes the manager priority tie-order gap. The exact
retail generic sorter uses insertion sort below seven records, a middle pivot
at seven, median-of-three above seven and pseudomedian-of-nine above forty with
Bentley-McIlroy three-way partitioning. The production port matches 34 bounded
retail-executable oracle cases, including threshold sizes, mixed duplicate
keys, signed zero and the full 512-record manager cap.

All 539 CPU tests pass, Python compilation and `git diff --check` pass, and all
53 offline shader cases remain green. The native sort report has SHA256
`52d2f7acced0d798248706155bce3708626e4a28c229589da6ad757ea64fa29f`
and case-blob SHA256
`3022e0729e94fe710df264bd2266ff7fd0b16c92a91db0a6e7eb341aea18c4bb`.
The independent port-validation report has SHA256
`31e2ffa211233695847eb689bb51ce3ad61c13c8d061b84c9433394e305c0d2c`.
The manager report now pins 44 executable ranges plus two static data ranges and
has SHA256
`4791307d40239f22a5d2c36a927f127dc6d59e9058494c9d2f59f58d1fa6cc2e`.

The compact archive contains 157 source files and 72 evidence files. Independent
validation read 47,973,283 uncompressed bytes, checked CRC, length and SHA256 for
all 231 entries, found no duplicates, and verified the checkpoint 11
predecessor link. The 14,474,657-byte archive SHA256 is
`716657ae3e0709ad6d17e82a22ef26dbfb97568434d306d7ff849acbe1267d4c`.
This ledger entry is the only intentional source delta after the immutable
archive.

The live spatial database and populated query descriptors/depth hierarchy,
captured resolved-resource inputs, parallel chunk completion order, captured
placement/prepared-stream values and active-Hair local-light output validation
remain open. The game, GUI and RenderDoc replay were not launched for this
checkpoint.

## 2026-09-04 15:19 UTC — manager resource clipping and persistent output

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T151920Z-manager-resource-clip-output/`

This CPU-only checkpoint completes the static resource-refresh plane-source and
persistent-output boundary. The sole refresh call is `0x1410BAD85`. An optional
resolved oriented box contributes six world-space planes in native axis/side
order; retail partitions them around the source origin or type-3 negative local
Z and inserts lower-Z then upper-Z type scalars between the partitions. No
camera object is passed at this boundary. The ordered planes feed the existing
clip/cap implementation.

Output helper `0x1410B8CB0` copies exact XYZ values to persistent float3 storage,
writes the AABB and computes its sphere from the midpoint and farthest vertex.
Types other than 3 and 4 update source center, radius and half extents through
`0x1412B6AA0` when the new half-extent volume is below 98 percent of the old
bound volume. Five plane-list cases and the unit-box and fractional output
samples match the bounded retail-executable Unicorn oracle bit for bit.

All 534 CPU tests pass, Python compilation and `git diff --check` pass, and all
53 offline shader cases remain green. The manager report pins 41 executable
ranges plus two static data ranges and has SHA256
`e1c014da50cfdc3ff1a6e81209b136f2b4c0d7b34defc6ed6f8bbce82be700c7`.
Its composite clip/output oracle SHA256 is
`59f74079f39ef78bcabacbe6c22424b7665d64fff6bf8b0c0ad40fef272ba414`.
The independent clip-source report has SHA256
`99cce2ed2d422300cd036281835174e900f5db29d861a123408f14979b12bf52`.
The compact archive contains 157 source files and 68 evidence files. Independent
validation checked the CRC and SHA256 of all 227 entries. The 14,457,176-byte
archive SHA256 is
`be74cf0ede73507125debec68d3f68e0f2a9a60035ca1ab014cc95373741199a`.
This ledger entry is the only intentional source delta after the immutable
archive.

Captured resolved-resource values, the live spatial database and populated
query descriptors/depth hierarchy, equal-score and parallel-chunk ordering,
captured placement/prepared-stream values and active-Hair local-light output
validation remain open. The game, GUI and RenderDoc replay were not launched for
this checkpoint.

## 2026-09-04 14:07 UTC — manager resource refresh and exact shape sources

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T140718Z-manager-resource-shape-sources/`

This CPU-only checkpoint completes the source-owned local-light resource refresh
boundary. It reproduces the raw-CRC version cache, every type dispatch,
zero-count behavior, built-version update and `align4(vertexCount + 1) * 12`
float3 allocation. The four selected geometry paths now emit retail's exact
36-vertex box, 432-vertex rounded shell, 216-vertex type-1 cone and 48-vertex
type-2 cone. The authored static streams match their executable tables bit for
bit. Both procedural streams use the recovered scalar sine/cosine polynomial
and match every XYZ bit in six isolated retail-executable samples.

All 531 CPU tests pass, Python compilation and `git diff --check` pass, and all
53 offline shader cases remain green. The manager report pins 36 executable
ranges plus two static data ranges and has SHA256
`bbdd1db1a4d3e80665349fc8b8c35b00b845913cc8f6adf7fc506984ae42b865`.
The independent shape-source report has SHA256
`3ccf8e561596f4c0bdc3ced6352c214111a64ba2cc0ea3cb85665fe8cca2d553`.
The compact archive contains 157 source files and 62 evidence files. Independent
validation checked the CRC and every one of its 221 entries byte for byte. The
14,420,145-byte archive SHA256 is
`537916897e495b757548cc6fb42b9ba676aad9ab5cead4da89e891b501a431b3`.
This ledger entry is the only intentional source delta after the immutable
archive.

Resolved resource contents, the frame-specific near plane, live spatial
descriptors and depth hierarchy, equal-score/parallel ordering, captured shell
placements and active-Hair local-light output validation remain open. The game,
GUI and RenderDoc replay were not launched for this checkpoint.

## 2026-09-04 13:37 UTC — manager predicates and occlusion query

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T133706Z-manager-occlusion-query/`

This CPU-only checkpoint replaces the manager partition's opaque outcomes with
snapshot-driven implementations for object visibility, resource readiness,
type-resource availability, the 16-plane auxiliary-volume classifier and the
runtime-bit-21 distance gate. It also pins the worker's view filter as a
16-bit hierarchical-depth test. The exact wrapper transforms source `+0x40`
center and `+0x50` half extents into its oriented-box query and supplies the
retail `0.01` depth bias.

All 507 CPU tests pass, Python compilation and `git diff --check` pass, and all
53 offline shader cases remain green. The manager report pins 23 retail
executable ranges and has SHA256
`7b60bf49b894b282d6dd1b72dc306ab650d7993d7bb179ccf06a04e6ee5bd82b`.
The compact archive contains 157 source files and 45 evidence files. Independent
validation checked the CRC and every one of its 204 entries byte for byte. The
14,368,796-byte archive SHA256 is
`29d18679b22cf5ae88ecd37f87c2c84ee26a32f893b82da3b6086b0e54617d40`.
The ledger entry itself is the only intentional source delta after the
immutable archive.

The populated spatial descriptors and depth hierarchy, resource-refresh source
data, equal-score and parallel-chunk permutation, captured placement/stream
values, external zone/world transform ownership and an active-Hair output
capture remain open. The game and GUI were not launched for this checkpoint.

## 2026-09-04 13:14 UTC — manager spatial worker and shell association

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T131441Z-manager-spatial-shell-association/`

This CPU-only checkpoint completes the static manager consolidation boundary.
The secondary query merge, ordered skip/defer/priority partition, spatial query
submitter/worker ownership contract and final source-to-persistent shell-stream
association are pinned. Each accepted final source creates a 0x170-byte record;
its authored or generated float3 stream reaches `+0x140`, its count reaches
`+0x13c`, and the same record pointer is consumed by the full and opaque
`FillLightLookup` shell passes. Live spatial-database contents and callback
producers remain external inputs.

All 500 CPU tests pass, Python compilation and `git diff --check` pass, and all
53 offline shader cases remain green. The manager report pins 15 retail
executable ranges and has SHA256
`8e7462477ef31f4e644251aaf1846075e577e21224accc478cbbbe9fd620a20e`.
The compact archive contains 157 source files and 38 evidence files. Independent
validation checked the CRC and every one of its 197 entries byte for byte. The
14,341,968-byte archive SHA256 is
`46250dc05d8fae9f7edb822899925f923e74cd2285fb3712dc6743460d3e8fc3`.
The ledger entry itself is the only intentional source delta after the
immutable archive.

Populated query-descriptor meanings, optional view/resource callback producers,
equal-score and parallel-chunk permutation, captured placement/stream values,
external zone/world transform ownership and an active-Hair output capture remain
open. The game and GUI were not launched for this checkpoint.

## 2026-09-04 12:59 UTC — manager frame-source order

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T125909Z-manager-frame-source-order/`

This CPU-only checkpoint extends the local-light manager boundary from the
candidate predicate through per-frame ownership and packing. The 0x18a0-byte
state, primary and optional secondary spatial-query outputs, 16-entry worker,
512-pointer merge cap, priority/deferred partition output, descending binary32
projected-bound score, weighted allocation counts and final persistent/GPU
record handoff are now pinned. `core/local_lights.py` exposes the distinct-score
frame order and reports equal-score groups whose unstable native permutation
still needs an oracle.

All 485 CPU tests and all 53 offline shader cases pass. The manager report pins
ten retail executable ranges and has SHA256
`dc1544bb440a130d57688c568572c8b12abd71bbfe66e00bc9b494509ea99ca2`.
The compact archive contains 157 source files and 35 evidence files. Independent
validation checked the CRC and every one of its 194 entries byte for byte. The
14,318,478-byte archive SHA256 is
`7a56efb78d9b2bb4049801c741f58c9e6dbda47a9349be86cf3a040ed9bef5bf`.
The ledger entry itself is the only intentional source delta after the
immutable archive.

Spatial-query semantics, optional view-filter inputs, opaque visibility and
resource partition gates, equal-score and parallel-chunk permutation,
shell/placement association, external zone/world transform ownership and an
active-Hair output capture remain open. The game and GUI were not launched for
this checkpoint.

## 2026-09-04 12:43 UTC — manager selection and local light basis

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T124314Z-manager-local-basis/`

This CPU-only checkpoint adds the manager's exact ordered candidate predicate,
overflow-safe camera distances, fade gate and 16-entry chunk membership. Atlas
handles now resolve from an explicit generation-checked manager-table snapshot.
The type-1 scene-light path includes its scalar derived initializer, native
trigonometric approximation, culling shape, source-matrix local-basis
normalization and final transform classification. The local-basis helper is
hash-gated at `0x1402BD1A0..0x1402BD58F` and verified across all 22 extracted
retail light records.

All 481 CPU tests, all 53 offline shader cases, Python compilation and source
integrity checks pass. The compact archive contains 157 source files and 29
evidence files. Independent validation checked the CRC and every one of its 188
entries byte for byte. The 14,269,860-byte archive SHA256 is
`b23df898da552e664cf498381505ae2620d0b8d9cb4dcef55a2a0244294f60f4`.
The ledger entry itself is the only intentional source delta after the
immutable archive.

Live candidate-list ownership, view-filter inputs, scheduler completion order,
shell/placement association, external zone/world transform ownership and an
active-Hair output capture remain open. The game and GUI were not launched for
this checkpoint.

## 2026-09-04 12:04 UTC — static subtype light packers

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T120415Z-static-subtype-light-packers/`

This CPU-only checkpoint completes the static subtype-3 and subtype-4
`LightGpu` packers. Subtype 3 reproduces the native float32 cofactor and affine
inverse order, its scaled clip-volume transform, position adjustment and raw
inverse-attenuation bits. Subtype 4 reproduces its affine inverse, raw color
rewrite, final color-volume reference and the full-tier path that leaves the
common record unchanged. Both preserve native auxiliary allocation order,
capacity skips and packed reference fields. The auxiliary report hash-gates 15
retail executable ranges and has SHA256
`b2cb15d829b4fe8259feea054e1612ea780e10426b3295bfd305fe7d12dbc645`.

All 451 CPU tests, all 53 offline shader cases, Python compilation and
`git diff --check` pass. The compact archive contains 157 source files and 22
evidence files. Independent validation checked the CRC and every one of its 181
entries byte for byte. The 14,203,876-byte archive SHA256 is
`fcf2c4e8f9158f8880744299f7e0f75daf49c6ae9f81f196fb9a3bb8d47ea894`.
The ledger entry itself is the only intentional source delta after the
immutable archive.

Atlas-handle resolution, transform-dependent runtime initialization, automatic
manager ownership and active-Hair output validation remain open. The game and
GUI were not launched for this checkpoint.

## 2026-09-04 11:47 UTC — native light-volume constructors

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T114731Z-native-light-volume-constructors/`

This CPU-only checkpoint adds the native subtype-1 auxiliary allocation layer:
primary clip, gobo, up to three shadow-map records and the ordered shadow-volume
list use the retail allocation order, low-uint16-index/high-uint16-count range
encoding and individual tier-full skips. Native constructors now cover the
primary clip transpose, standard and dual-sign gobo atlas mapping, projected
and six-face point shadow maps, the 0x68-byte shadow-volume source, and both
subtype-4 color-volume dimension modes. The auxiliary report hash-gates 12
executable ranges and has SHA256
`9298e79dfe950bf04b8872b9dab51e3b0843e936cb5ba7d7f5b25f29956293e7`.

All 442 CPU tests, all 53 offline shader cases, Python compilation and
`git diff --check` pass. The compact archive contains 157 source files and 22
evidence files. Independent validation checked the CRC and every one of its 181
entries byte for byte. The 14,197,665-byte archive SHA256 is
`739263acd661b2801609e808a8d042b6a8caf04a27725bdfe5ab07b6cd41b2bf`.
The ledger entry itself is the only intentional source delta after the
immutable archive.

Atlas handle resolution, subtype-3 native matrix inversion, subtype-4
base-light integration, automatic runtime ownership and active-Hair output
validation remain open. The game and GUI were not launched for this checkpoint.

## 2026-09-04 11:04 UTC — scene-light and LightGpu producer

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T110410Z-light-gpu-producer/`

This CPU-only checkpoint adds the strict serialized scene-light parser and pins
the runtime structured-buffer upload boundary. Retail `InitLightSB` creates five
main and five auxiliary tiers at a 128-byte stride; exact capacity selection,
the only direct packer call, native constants and the 128-byte base field map
are hash guarded. `LightGpuBaseSource` and `build_light_gpu_base_record()`
rebuild all eight populated captured records byte for byte. Their 1,024-byte
prefix SHA256 is
`79c2c34c74d87ac272eb0651d923cf0dc8d0a8f730b2fb8e6b3da0e232e12c69`.

The installed 177-zone scan finds 21 placed type-1 light nodes, none matching
the captured eight-light group. Those captured records are runtime-created
dynamic lights. At checkpoint time, negative-radius packing, auxiliary
`LightVolumeGpu` allocation, runtime source ownership and active-Hair
local-light output remained open and were recorded explicitly in the manifest.
Later continuation implemented negative-radius compatibility and the direct
cooked subtype-1 runtime transfer; those changes are intentionally outside this
immutable archive.

All 413 CPU tests, all 53 offline shader cases, Python compilation and
`git diff --check` pass. The compact archive contains 157 source files and 23
evidence files. Independent validation checked every one of its 182 entries
byte for byte. The 14,170,422-byte archive SHA256 is
`e228db5987d31bf6b8bad470a390d18c39629be501998cb5942a1d97a8d97ba1`.
The archive remains the recovery point for its recorded boundary.

## 2026-09-04 09:22 UTC — scene direct-lighting executable path

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T092214Z-scene-direct-lighting-parity/`

The production Hair resolve now consumes the exact raw local lookup, light and
volume records through point/area geometry, clip and accumulated-color volumes,
all gobo modes, ordered shadow volumes, projective and packed-cube local shadow
maps, and the shared screen-contact kernel. Key radiance now continues through
the recovered cloud projection, periodic key gobo and nonstochastic
five-plane shadow-volume cascade chain. Scene validation accepts and uploads the
shared atlas/volume resources even when no local-light lookup is attached.

The saved frame has zero active local-light references at all 11,215 Hair
pixels and disables the three key-modulation branches. Captured identity output
is exact at all 11,215 pixels; static DXIL boundaries and deterministic CPU
anchors cover the unexecuted coordinates and selectors. This does not establish
active-output parity. Automatic placement/residency and the local screen-shell
lookup producer remain open.

All 392 CPU tests, all 53 offline shader cases, Python compilation and
`git diff --check` pass. The compact archive contains 155 source files and 10
evidence files. Independent validation checked the CRC and every one of its 167
entries byte for byte. The 14,100,200-byte archive SHA-256 is
`e6a82a47b9adbc7386d1bcd1866e04c7af323c31e72d4bb545cc6ec27a87a16f`.
At creation, this ledger entry was the only intentional source delta after the
checkpoint. Later continuation recovered the explicit submitted-stream local
screen-shell producer, conditional near-plane clip/cap chain and current-view
scene adapter; that work is not inside this archive.

## 2026-09-04 05:56 UTC — production TAA and native raster convention

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T055647Z-production-taa-native-raster/`

The production viewport now compiles every shader for one coherent raster
convention. OpenGL 4.5 or `GL_ARB_clip_control` activates upper-left,
zero-to-one clip coordinates with reverse-Z clear and comparison state; the
legacy lower-left path remains available. Perspective and orthographic
matrices both map the right-handed near plane to 1 and the far plane to 0.
Camera disocclusion, temporal jitter, fur shadows, OIT depth weighting,
fur-only culling, and the final Qt presentation boundary follow the selected
convention.

A guarded perspective smoke activated the native path, kept camera history
from temporal age 1 through 9, wrote nonzero opaque velocity in 17,857 pixels
per component, and produced exactly 27,973 hair-category pixels. Its dynamic
last-frame `m_Misc` was
`(0.0625, 0.0022656249348074198, 76.1092758178711, 0.1111111119389534)`.
An independent guarded orthographic smoke was also upright and visually
intact. The two jobs peaked at 1.580 GiB and 1.487 GiB under their 2 GiB hard
limits, kept `Default` as the input desktop, exited with code zero, and left no
process or window.

The production fragment TAA shader was also replayed over the saved 3440x1440
retail frame. Captured runtime inputs reproduce `m_Misc` exactly. Native packed
R11G11B10 output agrees in 97.547460% of pixels; every channel is within one
code in at least 99.999777% of pixels. Only 17 pixels differ by more than one
code, all ordinary low-rejection samples with no border, diagonal-depth,
Catmull-Rom, stencil-128, disocclusion, or accumulated-alpha involvement.

All 291 CPU tests, all 53 legacy/native offline shader cases, Python
compilation, and `git diff --check` pass. The compact archive contains 146
source files and 15 evidence files. Independent validation checked the CRC and
all 163 entries byte for byte. The 14,366,219-byte archive SHA-256 is
`1595a54c47823c1b915b889aaeea04778ec5f80674ea6e592c4a193a793dc979`.
This ledger entry is the only intentional source delta after the checkpoint.

## 2026-09-04 05:14 UTC — live velocity, stencil, and camera motion

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T051453Z-live-velocity-stencil-camera-motion/`

The production viewport now writes ordinary opaque RG16F velocity alongside
the recovered fur velocity and carries category bit 128 in an explicit R8UI
texture shared by the opaque and fur-material framebuffers. Motion blur,
disocclusion, accumulated-alpha half resolve, and final temporal apply select
the correct motion source per pixel. Final apply loads `(stencil & 128)` at the
captured center/closest-diagonal velocity position and applies the recovered
`m_Misc.y` scale. Camera state no longer resets a history that can now reproject
through view changes.

A guarded 600x600 physical smoke stepped camera yaw by 0.25 degrees across
seven frames. Temporal age advanced from 1 to 9, opaque velocity was finite and
nonzero in 20,686 pixels per component, and the stencil contained exactly
331,638 zero pixels and 28,362 bit-128 pixels. Both temporal history slots,
motion scatter, full disocclusion, and accumulated-alpha remained valid. The
saved frame is visually intact; the job peaked at 1.631 GiB under 2 GiB, kept
`Default` as the input desktop, exited with code zero, and left no process or
window.

All 285 CPU tests, all 53 offline shader cases, Python compilation and
`git diff --check` pass. The compact archive contains 146 source files and 8
evidence files. Independent validation checked all 156 entries byte for byte.
The 14,234,113-byte archive SHA-256 is
`40a5d0cb795bfe71230b114b47d9d55a0eb6de5869406d5952d660a6fc3efdb7`.
This ledger entry is the only intentional source delta after the checkpoint.

## 2026-09-04 04:56 UTC — live accumulated-alpha chain

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T045650Z-live-accumulated-alpha-chain/`

The production viewport now snapshots opaque and fur-composed full-resolution
R16F depth, reduces the opaque input to four-texel half-resolution extrema,
builds the explicit event-18687 R8 mask, reruns the event-18704 disocclusion
calculation at its captured `0.6666666865348816` motion threshold, and patches
the four event-18712 half-resolution outputs. Dense mask-discard draws preserve
the recovered sparse queue's observable texture results. The final TAA apply
now consumes the live current-frame mask in the captured `t10` role.

Saved retail resources independently prove the pre-alpha minimum and maximum
reductions bit for bit across all 1,238,400 half-resolution pixels. A guarded
600x600 physical smoke reached seven temporal samples with 2,356 active mask
pixels and 2,350 nonzero half-velocity pixels per component. All targets were
finite, the saved frame was visually intact, and the job peaked at 1.628 GiB
under its 2 GiB cap while leaving `Default` as the input desktop and no owned
process or window.

All 285 CPU tests, all 53 offline shader cases, Python compilation and
`git diff --check` pass. The compact archive contains 146 source files and 14
evidence files. Independent validation checked all 162 entries byte for byte.
The 14,246,235-byte archive SHA-256 is
`f00d070024470ba00c90f39a1878a554d994d4081b14f88e251618252f5d83c0`.
This ledger entry is the only intentional source delta after the checkpoint.

## 2026-09-04 04:38 UTC — live full disocclusion and motion scatter

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T043839Z-live-full-disocclusion-motion-scatter/`

The production viewport now runs the recovered motion-blur downsample,
neighborhood and 40-crossing scatter path before a full-resolution temporal
disocclusion pass. Paired RG8 histories store rejection and camera discrepancy;
paired RG16F histories store composed depth and camera motion. The pass uses the
captured 8.0 depth base, the captured `0x41d70001` depth slope, the exact 1.0
motion threshold and the recovered current-to-previous projection path. The
temporal color pass consumes the live result together with the retained
event-18687 previous-depth mask.

The stable guarded smoke reached nine temporal samples with both history slots
valid, finite depth/motion data and zero false disocclusion. The controlled
moving smoke reached seven samples and activated red-channel disocclusion in
both slots (127 and 774 pixels). Its full velocity reached 0.50146484375, while
the gathered scatter input remained below the exact 0.800000011920929 cutoff,
so both scatter targets correctly remained zero. Both private jobs stayed below
their 2 GiB caps, kept `Default` as the input desktop, exited with code zero and
left no owned process or window.

All 285 CPU tests, all 45 offline shader cases, Python compilation and
`git diff --check` pass. The compact archive contains 146 source files and 42
evidence files. Independent validation checked all 190 entries byte for byte.
The 14,730,724-byte archive SHA-256 is
`cebf9034d0816fcff49a6257a53010cf4a1e579c05192cbcefe1d3857000d90d`.
This ledger entry is the only intentional source delta after the checkpoint.

## 2026-09-04 03:24 UTC — live temporal depth history

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T032400Z-live-temporal-depth-history/`

The production viewport now stores paired full-resolution R16F composed-depth
histories beside native R11G11B10 color history. It applies the verified
event-18687 accumulated-alpha mask from live previous depth: the three retained
gather components form the previous minimum, the exact 0.9980000257492065
threshold detects the depth change, and the result contributes 0.5 rejection
without replacing the final 0.0625 blend floor. Raw OpenGL allocation also
fixes the PyOpenGL packed-R11G11B10 null-upload failure.

A bounded 800x800 private-desktop smoke reached nine temporal samples with
deferred fur lighting, contact, and denoise active. The saved frame is visually
intact. The job peaked at 1.661 GiB under a 2 GiB limit, retained `Default` as
the input desktop, exited with code zero, and left no owned process. A later
proof-only run stopped when physical-memory headroom crossed its 24 GiB reserve;
cleanup left no partial image/report or live owned process.

All 284 CPU tests, all 28 offline shader cases, Python compilation, and
`git diff --check` pass. The compact archive contains 146 source files and 8
evidence files. Independent validation checked all 156 entries byte for byte.
The 14,536,118-byte archive SHA-256 is
`c89bc298a56e9e7f492ae87470184e3ff0d6e883a48bbb087c949e8e06d814e0`.
This ledger entry is the only intentional source delta after the checkpoint.

## 2026-09-04 03:08 UTC — native TAA accumulated-alpha setup parity

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T030842Z-native-taa-alpha-setup-parity/`

The saved resource boundaries now close events 16269, 18687 and 18695 without
another high-memory RenderDoc replay. The base half-resolution disocclusion and
accumulated-alpha mask each match all 1,238,400 R8 pixels bit for bit. The
captured mask predicts exactly 40,940 active packed tiles, and that complete
set equals the 40,940 unique append-buffer entries consumed by event 18704.
Append sequence is scheduler-dependent; its set, count and disjoint tile
effects are exact.

All 284 CPU tests, all 28 offline shader cases, Python compilation and
`git diff --check` pass. The two new private comparisons peaked at 0.926 GiB
and 0.873 GiB under 2 GiB hard limits, kept `Default` as the input desktop and
left no owned process. A stricter 30 GiB pagefile preflight first refused safely
with no child process. The compact archive contains 146 source files and 28
evidence files. Independent validation checked all 176 entries byte for byte.
The 14,021,941-byte archive SHA-256 is
`dbb214d484f3129d7cf8b75b1c22628f370b7bc20fd4c73d088d65725e7e7e49`.
This ledger entry is the only intentional source delta after the checkpoint.

## 2026-09-04 02:43 UTC — native TAA disocclusion-chain parity

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T024335Z-native-taa-disocclusion-chain-parity/`

Guarded events 16262, 18704 and 18712 close the captured full-resolution
disocclusion and accumulated-alpha half-resolution chain. All pre/post resource
links rehash exactly across dispatches. The recovered base shader reproduces
4,953,528 of 4,953,600 RG8 pixels exactly; all 72 residuals are one code in red,
green is exact everywhere and the RG16F depth channel is bit exact. The
event-18704 work-queue reconstruction reproduces the final RG8 output bit for
bit. The event-18712 reconstruction reproduces all four outputs bit for bit
across 1,238,400 pixels.

All 284 CPU tests, all 26 offline shader cases, Python compilation and
`git diff --check` pass. Private replay peaked at 13.648 GiB under its 15.5
GiB hard limit; comparison jobs stayed below their 2 GiB limits. Every job kept
`Default` as the input desktop and left no owned process. The compact archive
contains 146 source files and 19 evidence files. Independent validation checked
all 167 entries byte for byte. The 13,999,497-byte archive SHA-256 is
`2ae3c75039fac694ad5eee5c598b0b4e339f947cfc1c1eaf75cc26446cdaa0a7`.
This ledger entry is the only intentional source delta after the checkpoint.

## 2026-09-04 02:13 UTC — native TAA image parity

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T021320Z-native-taa-image-parity/`

The saved two-boundary capture now closes the native-resolution TAA image
boundary without another game run. All seven event-20572 inputs and the
post-dispatch R11G11B10 UAV were exported. Independently streaming ResourceId
4070 from the original RDC produces the exact replayed `t6` hash. ResourceId
4072's capture-start hash differs from replayed `u0`, proving the comparison
uses the dispatch result rather than old ping-pong contents.

The recovered shader now preserves the native separation between unfloored
rejection and the global final-blend floor, uses the native cross-then-diagonal
accumulation order, and reproduces the 8 x 8 shared current-color tile. Direct
R11G11B10 validation matches 4,831,458 of 4,953,600 packed pixels exactly.
Every red and green channel is within one stored code; all but four blue
channels are within one code. Packed exact agreement is 97.5342781 percent.
The preview temporal pass received the same rejection and accumulation fixes.

All 283 CPU tests, all 24 offline shader cases, Python compilation and
`git diff --check` pass. The guarded comparison peaked at 1.184 GiB under a
2 GiB hard limit, kept `Default` as the input desktop and left no owned process.
The archive contains 146 source files and 22 evidence files. Independent
validation checked all 170 entries byte for byte. The 14,013,858-byte archive
SHA-256 is
`bade0282430a5acef9dc228005a4d12a84b3306680abb3f870d5729580cf9a03`.
This ledger entry is the only intentional source delta after the checkpoint.

## 2026-09-04 00:51 UTC — private desktop pre-resume guard

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T005141Z-private-desktop-pre-resume-guard/`

The bounded private-desktop helper now checks physical-memory, page-file and
disk headroom before it creates a desktop or process. It checks again after the
suspended child is assigned to the capped kill-on-close job and before the
child's first instruction can run. Runtime checks continue every 0.5 seconds.
The controlled refusal used impossible thresholds, reported
`guard_stage=preflight`, created no root PID and left `Default` as the input
desktop. No game or RenderDoc process was launched.

All 283 CPU tests, Python compilation and `git diff --check` pass. The archive
contains 146 source files and four evidence files. Independent validation
checked all 152 entries byte for byte. The 13,953,162-byte archive SHA-256 is
`dab9b8b8e023e69a646262b2cec93113d559532edd7797d0b0ec0e57a5c7d6f7`.
Matched event-20572 texture bytes and output pixels remain the TAA parity
boundary. This ledger entry is the only intentional source delta after the
checkpoint.

## 2026-09-04 00:43 UTC — native TAA runtime contract

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260904T004345Z-native-taa-runtime-contract/`

Guarded capture event 20572 proves the runtime `CS_TemporalAaApply` container,
all eight native bindings, and the complete 224-byte cbuffer. The runtime DXIL
SHA-256 exactly matches the executable extraction. Captured pixel scales,
jitter, filter registers, ordinary rejection, HDR scale, history age, dither
index/phase and disabled flags all agree with the independently decoded builder;
the maximum filter-formula error is `7.4505806e-9`. The fork now exposes a typed
binary cbuffer contract, its scalar/filter producers, and the explicit shader
and binding identity.

All 283 CPU tests and all 24 offline shader cases pass. The runtime analyzer,
Python syntax, and `git diff --check` pass. The archive contains 146 source files
and 22 evidence files. Independent validation checked all 170 entries byte for
byte. The 14,173,500-byte archive SHA-256 is
`20b224ebb3e7a13e6d6302bd6f8913c708b46764e0ce45f3349606ea02a2e75b`.

The two-boundary live controller is retired pending a guard audit. A later raw
resource export hit RenderDoc `E_OUTOFMEMORY` under a hard 12 GiB job cap and
was stopped with zero textures exported; the inactive desktop and owned cleanup
contained the failure. No game, Steam, qrenderdoc or renderdoccmd process
remained. Matched event input/output texture bytes are the remaining TAA parity
boundary. This ledger entry is the only intentional source delta after the
checkpoint.

## 2026-09-03 20:22 UTC — region selection and captured-probe provenance

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260903T202200Z-region-probe-provenance/`

The retail kind-4 selector now has an exact static implementation boundary:
it walks each root child's primary-zone list, partitions zones through two
runtime bitsets, and does not consume the root's own primary list. The separate
kind-3/5 path visits the immediate parent first and selected region second.
Twenty-seven instruction anchors guard both paths. Megalopolis root 61 has 241
children and 1,848 unique child-primary inputs; Malinon region 21 and parent 20
have 29 unique dependencies.

The saved Hair event's active record 10 / cube 18 is joined to runtime draw-list
probe `F896FB5315175B7C`, zone `9C292F5F8A79EEC2`, catalogue index 3976, and
kind-5 region 184 under Megalopolis root 61. Its first 124 static GPU bytes match
under identity zone placement, and 29,359 saved screen tiles can select it.
Cube 18 has no baked-asset match. Malinon Day asset `837545B07B72296F` matches
inactive cube 40 in this frame.

All 278 CPU tests and all 24 offline shader cases pass. Both reports regenerate,
Python syntax and `git diff --check` pass. The archive contains 145 source files
and 15 evidence inputs. Independent validation checked all 162 entries byte for
byte. The 16,636,450-byte archive SHA-256 is
`1571f3fa3dbec7061be56dacaddbf50cad543dd8554e488a873b19ed4ea1e9e4`.
No game, replay, viewport, window, OpenGL context, or GPU workload was opened.
This ledger entry is the only intentional source delta after the checkpoint.

## 2026-09-03 19:54 UTC — native TAA orchestration and precision

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260903T195429Z-native-taa-orchestration-precision/`

The full/seed branch, half-resolution pass, and seed-history fallback now have
exact executable conditions, resource offsets, shader-object globals, cbuffer
writes, and 8x8 dispatch dimensions. The common matrix helper is decoded as a
float64 `first * inverse(second)` operation followed by float32 storage. The
disocclusion report guards 16 ranges totaling 4,719 bytes; the main-apply report
guards nine ranges totaling 3,523 bytes and records the exact half-mask guard.
The preview now rounds current-sample chroma through native f16 precision, uses
explicit LOD 0 history taps, and prevents undefined history storage on frame
zero and resets.

All 278 tests and all 24 offline shader cases pass; both static decoders
regenerate, syntax checks and `git diff --check` pass. The archive contains 143
source files and 64 evidence files. Independent verification matched all 209
manifest entries and the 14,270,862-byte archive SHA-256 is
`777cf030968d26a8bf30a6a4c8a5acb5e505443713e4cee06ae70e1dcda3b20e`.
No game, capture replay, window, OpenGL context, or GPU workload was opened.

## 2026-09-03 19:26 UTC — native TAA response and disocclusion builder

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260903T192631Z-native-taa-response-disocclusion/`

The executable's nonopaque-response fallback is now byte-verified as `0.04f`.
The ordinary apply floor is therefore exactly `0.0625f`, while a separate
runtime flag can raise it to `0.1f`. The production accumulator uploads that
fallback floor separately from reciprocal history warmup. The full-resolution
disocclusion builder is also decoded: pixel scale, zero source scale,
1920-pixel camera normalization, history threshold, prior projection-to-UV
transform, and fuzz predicate are statically fixed. Dynamic transforms, depth
thresholds, flags, and chosen history/scatter resources remain frame inputs.

All 278 tests and all 24 offline shader cases pass; Python syntax and
`git diff --check` pass. The archive contains 143 source files and 63 evidence
files, was read back against every manifest hash, and has SHA-256
`6d865fa392a088c5428ee94c28303df2b2e61ad4b54f6371f48f46f7556497ca`.
No game, capture replay, window, OpenGL context, or GPU workload was opened.

## 2026-09-03 19:12 UTC — native TAA history store and dither

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260903T191234Z-native-taa-history-store/`

The paired production-preview temporal histories now use the captured native
R11G11B10 format. The final apply uses the executable's exact 1,024-byte dither
table, five-frame phase and top-left pixel pattern at that storage boundary.
History warmup is uploaded as the builder's direct float32 reciprocal. The
expanded static report maps all proven main-apply cbuffer writes and exact filter
register packing.

All 277 tests and all 24 offline shader cases pass; Python syntax and
`git diff --check` pass. No game, capture replay, window, OpenGL context, or GPU
workload was opened. Frame-specific disocclusion/history/stencil resources,
dynamic HDR/matrix/response values, native-raster activation, and bounded GPU
validation remain.

## 2026-09-03 19:02 UTC — native TAA cbuffer builder

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260903T190210Z-native-taa-cbuffer-builder/`

The current CPU-only continuation traces the verified executable's
native-resolution TAA cbuffer builder and preserves its bounded disassembly.
Stable 224-byte cbuffer formulas now include the exact jittered Gaussian/Catmull
filter, 0.0625 rejection floor, stencil response, history warmup, and dither
sequence/table. The production preview consumes the exact filter and
center/closest-diagonal depth-selected motion. Dither remains deferred to the
native R11G11B10 storage boundary.

All 274 tests and all 24 offline shader cases pass; Python syntax and
`git diff --check` pass. No game, capture replay, window, OpenGL context, or GPU
workload was opened.

## 2026-09-03 18:38 UTC — native-resolution TAA chain

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260903T183855Z-native-taa-chain/`

This CPU-only checkpoint adds output-equivalent GLSL reconstructions for the
recovered seed-history, full-disocclusion and half-disocclusion stages beside
the existing main TAA apply. The production preview shares the recovered
luma/chroma transforms, HDR transform, five-tap Catmull-Rom history filter,
motion thresholds and neighborhood bounds through `core/hair_temporal.glsl`.

All 273 tests pass. The offline validator passes 24 shader cases, including all
four reconstructed temporal compute stages, the ordinary and native-raster
viewport sets, full scene replay and corrected motion producer. Python syntax
and `git diff --check` pass. No game, capture replay, window, OpenGL context or
GPU workload was opened.

Native-resolution temporal shader-code recovery is complete. Full-frame parity
still needs the frame-specific 224-byte cbuffer, selected history indices,
stencil and matched resources, followed by bounded GPU validation when game
work resumes.

## 2026-09-03 18:23 UTC — native raster preparation and static TAA recovery

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260903T182312Z-native-raster-static-taa/`

This CPU-only checkpoint maps and validates both captured skin-position streams,
adds guarded previous-clip comparison, and prepares the dormant upper-left,
zero-to-one, reverse-Z shader path without activating it in the viewport. The
installed executable also yields the exact `CS_TemporalAaApply` DXIL and eight
neighboring temporal shaders. The main apply has a complete resource/cbuffer
layout and an offline-compiling GLSL reconstruction. Its embedded accumulated-
alpha shader hash exactly matches the saved fresh-capture shader.

All 273 tests pass. Every forward, material, decode, lighting, contact, denoise,
temporal and grid shader set compiles in default and native-raster modes; the
full scene replay, corrected motion producer and recovered main-TAA compute
shader also compile. `git diff --check` passes. No game, capture replay, window,
OpenGL context or GPU workload was opened for this checkpoint.

Full-frame parity remains unfinished. Native raster activation and generated
motion still need bounded GPU validation, and the recovered temporal apply still
needs a same-frame 224-byte cbuffer, selected history indices, stencil and
pre/post resources when game work resumes.

## 2026-09-03 17:39 UTC — offline motion and temporal integration

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260903T173911Z-motion-temporal-offline/`

This CPU-only checkpoint adds the native fifth fur material target to the
production viewport, carries previous camera/wind state through the shell
vertex and geometry stages, and uses the proven current-minus-previous velocity
direction to reproject preview Hair history. The separate captured-draw replay
remains exact in all five targets and hardware depth across 24,226 dry/wet
pixels. The connected lighting/store/denoise chain remains exact at both stored
RGB boundaries for all 11,215 captured Hair pixels.

All 269 tests pass. Forward, material, decode, default lighting, scene lighting,
contact, denoise and temporal shader sets compile and link offline; the full
scene replay shader also compiles. `git diff --check` passes. No game, RenderDoc
replay, window or GPU workload was opened for this checkpoint.

Generated viewport motion and its temporal output still need a bounded GPU
comparison. Retail TAA depth-history/disocclusion rejection, native whole-pipeline
raster coordinates and a same-frame composed comparison remain unfinished. Read
`FUR_MOTION_PATH.md` and `FUR_RASTER_COORDINATES.md` for the evidence boundaries.

## 2026-09-03 15:47 UTC — scene lighting and key-shadow atlas

Continuation checkpoint in the outer workspace:

`artifacts/rcra-fur-continuation/checkpoints/20260903T154730Z-scene-lighting/`

Includes the current source snapshot, working-tree patches, verification reports
and preview images with a checked SHA256 manifest. The earlier material-response
checkpoint below remains intact.

- Explicit per-view grid/probe/cube resources and native key-shadow atlas now
  render through the production viewport. Camera changes invalidate stale
  lookups, and scene clearing releases textures and comparison samplers.
- Full captured Hair replay with the shared scene and atlas kernels still
  matches all 11,215 stored RGB pixels; native-float error is unchanged.
- Native packed-buffer comparisons, fractional atlas/contact composition,
  dry/wet/fallback and live scene lifecycle checks passed. All 260 tests pass.
- Full-frame parity remains unfinished. Next: native reflection history and
  combined light resolve, then matching scene/raster/motion/temporal state.

Read `HAIR_SCENE_LIGHTING.md` for measured float differences and remaining scope.
Restore into a separate directory using the instructions below.

## 2026-09-03 14:42 UTC — native material response

User-requested checkpoint before continuing scene-lighting integration.
Saved in the outer workspace at:

`artifacts/rcra-fur-continuation/checkpoints/20260903T144214Z-native-material-response/`

The checkpoint contains a complete source snapshot (tracked and untracked source
files, excluding ignored local environments), the working-tree patch and Git base,
selected verification reports/screenshots, and a SHA256 manifest. The archive is
read back and checked against every recorded file hash. Original game captures
and exported resources remain in the private evidence directory and are not
duplicated into the source snapshot.

Verified state:

- Full captured Hair replay: 11,215/11,215 stored RGB pixels exact; max native
  float error 4.947185516357422e-5, RMS 5.257787165646732e-7.
- Native material response, reflection frame, diffuse/transmission, occlusion,
  emissive and final resolve are shared with the ordinary viewport.
- Native R11G11B10 storage is applied at lighting and denoise boundaries; all
  11,215 outputs in each captured set and 35 format edge cases match.
- Dry/wet/fallback previews verified; 250 tests pass.

Read `HAIR_MATERIAL_RESPONSE.md`, `FUR_DEFERRED_PREVIEW.md` and
`FUR_RENDERING_HANDOFF.md` for the detailed evidence and limitations. Full-frame
parity is unfinished. Continue with complete scene lighting and matched native
raster, motion/history and final reconstruction.

To inspect or resume the snapshot, extract `source-and-evidence.zip` into a
separate directory and read `manifest.json` first. Its `source/` subtree is the
saved fork. Keep current work intact when comparing or restoring individual
files. This checkpoint is a local archive, not a Git commit or remote push.
