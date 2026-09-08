# Native heap failure: static trace

2026-09-07. Read-only executable analysis; no game launch or changed limits.
Verified retail SHA256:
`51299faca61866cf10ea9035a15b8f22600a56557dd5ffc1aad390d5a54e6d82`.

The exact logged error string leads to routine `0x1412839F0`. Exact MSVC
dumpbin disassembly confirms a device call at `0x141283AE5`, followed by
the HRESULT check and matching error string. The descriptor is assembled
from caller-supplied resource and heap properties. In one resource branch,
size comes from allocation-info output; in the buffer branch it comes from
the descriptor at `r9+0x10`, aligned to 64 KiB. It is not a fixed 6 GiB
allocation literal. Static code cannot recover the failed runtime request.

One candidate direct caller was found and confirmed at `0x14128428E`, in
routine `0x141283FA0`. This is a resource-creation path; it forwards the
descriptor to the heap routine. No claim that it identifies the specific
startup asset or allocator budget.

Command parser evidence:

- `-reducedtextureheap` and `-reduced_texture_heap` both store 3200 at
  `0x146255F24` via `0x141017ADC`.
- `-forcetextureheap` and `-force_texture_heap` parse the following value and
  store it at the same location via `0x141017AD2`.
- Scans for direct RIP-relative references (including one- and four-byte
  trailing immediates) found the two parser writes, no reader. This does not
  exclude indirect access, but the flags' effect and units remain unverified.
  Do not treat these as proven memory-reduction controls or try guessed values.

Evidence in `recovered/native-ear-audit`: `heap-static.json`,
`heap-options.asm.txt`, `heap-create.asm.txt`, `heap-caller.asm.txt`,
`heap-value-references.json`, and `heap-callers.json`.
`trace_native_heap_static.py` reproduces the string/reference inventory.

The two previous startup runs reached the configured 6 GiB job-memory limit
and failed with E_OUTOFMEMORY. That makes the cap a plausible contributor;
it does not establish the game's required budget or prove VRAM exhaustion.
Next missing evidence is the failed runtime heap descriptor (size, heap type,
flags) and allocation context. Preserve the cap until evidence supports a
concrete change; do not perform another quality-only startup retry.

## Runtime descriptor captured 2026-09-07

One guarded 1280x720 low-settings run, same 6 GiB cap and resource reserves,
no RenderDoc or focus injection. `probe_native_heap.py` verifies the live owned
inactive game window and retail hash before invoking a bounded C++ stack sampler.
Threads are resumed immediately after context/stack read (maximum 64 KiB each).
The error-dialog thread 50680 contains return RVA `0x1283b31`; its two local
heap descriptor copies match in their first 40 bytes. HRESULT is `0x8007000e`.

- Size: 2,145,386,496 bytes = **2,046 MiB**.
- Heap type: 1 (`D3D12_HEAP_TYPE_DEFAULT`).
- Alignment: 65,536 bytes.
- Flags: 0xc0 (`D3D12_HEAP_FLAG_ALLOW_ONLY_BUFFERS`).
- Creation/visible node masks: 1/1; CPU page property and pool preference: 0/0.

Enum names verified against installed Windows SDK 10.0.26100.0 d3d12.h.
This identifies a large buffer-only request, not a texture heap. Its owning
subsystem and sizing policy are still unknown. Exact size-byte search found
one executable-code match at 0x141592CEF, but disassembly shows a bitmask test,
not an allocation constant; do not treat that as the producer. Other byte
matches are not validated references.

Evidence: `heap-runtime-20260907.txt` and `.json`, `heap-size-constants.json`,
`heap-size-constant.asm.txt`, `heap-probe-20260907-native.log`, and matching
job/settings reports in recovered/native-ear-audit. This is a stack-pattern
recovery, not a symbolic unwind. Matching return site, duplicate descriptors,
and HRESULT provide strong evidence, but do not identify the buffer owner.

Owned game stopped immediately after sampling; input desktop remained Default;
settings restored=true, no intervening changes. Peak job 6.38381 GiB reported
against configured 6 GiB; global atoms 152 at stop. No ear reference captured.
Do not infer the final required memory budget by simply adding 2,046 MiB to
this peak; charging and failed-allocation behavior have not been established.

Next: recover the resource-creation caller chain and buffer sizing policy;
then select an evidence-backed memory reduction or bounded budget adjustment.
No speculative cap increase, production fur change, or package repack performed.

## Buffer owner and named budget recovered

Second focused probe (`heap-chain-20260907`) added StackWalk64 using the bounded
stack snapshot and saved only the matching thread's 13,656-byte stack. The
unwound allocation frame has RBP 0xc0fd4fd611 and R15 0xc0fd4fd6c0, confirming
the previous stack-pattern interpretation. Two decoded resource descriptors
both specify a 2,145,386,496-byte buffer, row-major layout, resource flags 0.
Caller chain: 1283b31 -> 1284293 -> 1290723 -> 12915c7 -> 129cca3 ->
11fb1b9 -> 11fac33 -> 12225ec (RVAs, outward from the error).

Renderer startup at 0x1412225E7 initializes global instance 0x1465A4260 via
0x1411FA9D0, with R8=0 selecting the non-raytracing manager. That calls
0x1411FAC70. The actual GPU allocation at 0x1411FB1B4 carries the debug label
`D3DBufferManager::InitBuffer`, verified from string VA 0x1432F0750.

Sizing path: 0x1411FA1C0 selects string `ManagedBuffer` at 0x1432F0610 for
this manager. Lookup 0x14160ACD0 hashes the name and searches 24-byte records
at global 0x14684BC60, returning the record's 64-bit value at +0x10. Reflection
record 0x14551C238 names this table `SystemMemory`. The size is rounded using
allocator granularity at 0x144562370 (file value 4096), used to initialize an
arena; GPU buffer size then comes from manager/arena member +0x500. Do not
claim the table budget itself equals 2,046 MiB: arena initialization and
usable-capacity accounting still need tracing. Separate named raytracing
budgets exist, but are not selected by this startup call.

Evidence: managed-buffer-owner.json, heap-chain-resource-descriptors.json,
heap-chain-20260907.txt and .txt.stack.bin; heap-chain-*.asm.txt,
heap-owner-sizing.asm.txt, heap-sizing-*.asm.txt, heap-budget-lookup.asm.txt,
managed-budget-object-refs.json. Some disassembly ranges extend beyond a
single function or begin/end at unwind fragments; use verified call sites
and instruction boundaries, not filenames, to determine semantics.

Game stopped, settings restored=true, input desktop Default. Guards unchanged;
peak job 6.38312 GiB reported against 6 GiB configured. No more launches in
this step. No proven override found in loose game configuration files or
Forge's hash-name dictionary. Next trace the SystemMemory table's serialized
source and arena capacity calculation before changing any budget.

## Sizing correction and source inventory (offline continuation)

Completed the missing unwind fragment after 0x1411FA304. At 0x1411FA31C,
manager+0x500 is assigned RBX: the previously calculated budget page count
multiplied by allocator granularity. The arena initializer does not change
RBX (callee-saved); this is NOT a usable-capacity subtraction. GPU creation
reads that same manager field. Formula: heap size = round_up(round_up(named
ManagedBuffer value, allocator granularity), 65536). File granularity is4096;
the original table value and live granularity were not directly sampled.
Thus no evidence supports a supposed2MiB allocator deduction from2GiB.
Evidence: heap-arena-size-store.asm.txt; managed-buffer-owner.json updated.

Decoded the engine name hash using its actual CRC table and initial seed
0xEDB88320, no final complement: ManagedBuffer=0xAE669203;
SystemMemory=0xF0B87E85. The latter agrees with reflected schema metadata.
Its sole code-byte hit is a type hash comparison, not a settings loader.

New scan_memory_config.py bounds expansion to64MiB and decompresses each
archive block once. It scanned all1845 d/config assets (11,687,800bytes with
headers): neither plaintext names nor these two engine hashes matched.
Initial per-asset scan stopped at its4MiB asset bound; replaced with the
bounded archive-level implementation after inventory showed total11.6MiB.
Completed report memory-config-scan.json supersedes that incomplete attempt.
No changes to installed game files. TOC itself also has no matching terms.

Settings reflection registration leads to root registry at0x14684B5F8 and
array0x14684B600 (memory-settings-registration.asm.txt, registry and refs).
EngineDebug.json and StickyConfig.json are separate optional serialized
objects with different roots; merely finding those filenames is NOT proof
that either accepts the SystemMemory budget. No speculative JSON written.
Windows resource inventory showed mostly images/dialogs and one BINARY
resource; no claim that this is the source. SystemMemory serialized source
remains unresolved. Next follow settings registry population/deserialization
or inspect the loaded budget record/provenance in one targeted owned run.
No game launch or resource-limit change during this continuation.
