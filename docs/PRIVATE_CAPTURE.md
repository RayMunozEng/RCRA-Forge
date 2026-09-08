# Private capture continuation — 2026-09-03

Fresh retail Direct3D 12 captures now record and replay successfully on an
inactive Windows desktop. The existing profile has been loaded and two gameplay
intervals are saved. Ratchet and the exact reconstructed Hair shader are verified
in the G-buffer and isolated lighting output. Full renderer parity remains
unverified; captured indirect-lighting comparison is now in progress.

The original `riftapart-taa_frame7328.rdc` was not found in readable F:/E:
storage, likely C: user folders or relevant task records. Some protected
folders were inaccessible. The user does not know its location; do not ask
again or reuse its point/mask as evidence for a new capture.

## Authorization and isolation

The user explicitly approved the temporary focus adjustment ("you're free to
do so"). The earlier automatic-review rejection is superseded. Both the
approved focus DLL and the documented RenderDoc API controller have been
loaded and tested. No further confirmation is needed for this setup.

`tools/private_desktop.py` creates an `RCRA-Capture-*` desktop, launches with
explicit `STARTUPINFO.lpDesktop`, assigns the suspended root to an owned
kill-on-close job, then resumes it. Deadlines and stop files clean up only
that job. It never switches desktops or sends global input. Default remained
the user's input desktop throughout the tests. Steam's nested CEF jobs need
`--ui-restrictions none`; the successful retail runs also used this option.
Private desktops, deadlines and owned-job cleanup still apply.

Resource thresholds are checked before the private desktop or process exists,
then checked again after the suspended child is assigned to its capped job and
before its first instruction can run. A failed check records `guard_stage` as
`preflight` or `before_resume` and exits through owned cleanup. The same limits
remain active at 0.5-second intervals after resume. High-memory diagnostics
must supply nonzero physical-memory, page-file, disk and job-memory limits.
Use `--priority below-normal` for offline conversion and replay diagnostics so
the whole owned job yields CPU time to foreground applications.

## Three resolved capture blockers

1. **Device creation through Streamline.** Retail uses `sl.interposer.dll` to
   create D3D12, bypassing RenderDoc's normal CreateDevice interception. The
   verified built-in `-noStreamline` flag switches to native D3D12 creation.
   Read-only live evidence confirmed the cached CreateDevice function and
   native fence vtable changed from Streamline/D3D12Core to RenderDoc wrappers.
   `-nolauncher` also works and skips only the launcher on subsequent runs.
2. **Occluded presentation.** A controlled private D3D12 smoke test cleared,
   executed and completed its GPU fences, while Present returned
   `DXGI_STATUS_OCCLUDED` (0x087a0001). Ordinary TriggerCapture stays pending
   without a presentation boundary. `private_renderdoc_control.dll` uses
   documented StartFrameCapture(device, NULL) / EndFrameCapture(device, NULL)
   around a 30 ms interval. These are diagnostic intervals, not guaranteed
   complete presentation-boundary frames. Never overlap them with an ordinary
   pending capture. Empty TargetControl.GetAPI() does not prove D3D12 is unhooked.
3. **Separate title-bar activation state.** The game checks both WM_ACTIVATE
   and WM_NCACTIVATE. The earlier WM_ACTIVATEAPP/WM_SETFOCUS notifications left
   the second state false. Read-only inspection found the movie in state 4
   (paused) at Bink frame 3. Sending WM_NCACTIVATE(TRUE) to the private game HWND
   cleared application pause, changed movie state to 3 and advanced playback.
   This notification is now included in the shim and `--resume` helper.

The earlier suggestion of a stuck GPU fence was disproved: repeated samples
and increasing fence counters show the render loop advances normally.

## Verified build and tools

Game: Rift Apart v3.630.1.0, Steam app 1895880. Executable SHA-256:
`51299faca61866cf10ea9035a15b8f22600a56557dd5ffc1aad390d5a54e6d82`.
RenderDoc: 1.46, commit `e4bd23b671d3d5a747ff5221dbe08a63eb6ca200`.
GPU: RTX 5060 Ti. Native window remained 1920 x 1080 in the tested captures.

Evidence and scratch tools live in the enclosing workspace at
`artifacts/rcra-fur-continuation/capture-tools/`:

- `private_focus.cpp`: only the main module's GetForegroundWindow and GetFocus
  IAT slots (RVAs 0x2e380b0/0x2e380c0) return its own private GameNxApp HWND.
  Process, desktop, window and import locations are checked; the loader also
  verifies the whole executable hash and live owned-job inventory.
- `private_renderdoc_control.cpp`: verifies the wrapped D3D12 device through
  the analyzed native-fence layout and invokes only RenderDoc's public API.
  Change `capture-manual-now` text once per capture. Initial text is ignored.
  Controller lifetime is 20 minutes, with parent-job cleanup still active.
- `renderdoc_game.py`: qrenderdoc startup script, SteamAppId/SteamGameId 1895880,
  -noStreamline -nolauncher. Use `qrenderdoc.exe --python` and exit with
  SystemExit. Its embedded Python lacks working ctypes; Win32 checks run in
  the venv helper and the script binds to a fresh parent report/root PID.
- `read_private_renderer.py`: read-only device, fence, pause and movie evidence.
- `sample_game_threads.cpp`: brief context/stack snapshots; resumes threads
  before offline unwinding. Register snapshots and absolute addresses are
  specific to a live process and must never be reused after restart.
- `private_window_input.py`: messages to a verified owned HWND, without cursor
  movement, SendInput or global activation. `--resume` includes WM_NCACTIVATE.
- `private_dialog_controls.py`: reads native launcher controls and selects an
  exact combo-box value. `private_window_snapshot.py` uses PrintWindow, which
  can be stale/black on an inactive GPU window; use capture replay for proof.
- `inspect_retail_capture.py`: GPU replay, action/texture inventory, PNG export.

## Saved evidence

- `gl-smoke_frame0.rdc` and `renderdoc-smoke-replay.json`: controlled OpenGL
  capture/replay passed, including the expected pixel.
- `private-d3d12-result.txt`: GPU fences pass despite occluded presentation.
- `private-renderer-device-creation.json` / `private-renderer-native.json`:
  Streamline versus wrapped native D3D12 evidence.
- `private-renderer-movies.json` / `private-renderer-ncactivate.json`:
  paused movie and successful activation intervention.
- `riftapart-fresh_capture.rdc` / `_2.rdc`: successful replay of paused startup
  (about 430 MB each), not fur references.
- `riftapart-fresh_capture_3.rdc`: successful replay of the loading indicator.
- `riftapart-fresh_capture_4.rdc`: 2,184,438,772 bytes; replay passed with 671
  actions, final event 7806 and 755 textures. `replay-fourth/ResourceId-538.png`
  verifies profile selection with its rendered 3D background. Profile 1 is the
  existing Sep 1 save. No character/fur reference is established by this menu.

## Current continuation and cleanup

All private game and Steam jobs are now closed through their own stop files,
including `private-game-checkpoint.json`, `private-game-restore-display.json`
and `private-steam-scene.json`. Shader replay/debug jobs are individually bounded;
inspect their fresh reports rather than reusing historical PIDs.

The original **Exclusive Fullscreen / 3440 x 1440** preferences were restored
through the native launcher and verified by reopening Settings. Evidence:
`launcher-restore-before.json` and `launcher-restore-verified.json`. The native
default Enter action applies the dialog; posting mouse coordinates to its parent
does not activate child buttons. WM_KEYUP may report an invalid HWND after Enter
successfully destroys the dialog. No shader or executable file was changed.

Steam synchronized a newer cloud save before capture. The earlier local backup
and hashes are in `save-backup-before-capture/` and `save-backup-hashes.json`.
Do not overwrite the newer synchronized save with that older backup.

The saved event-20572 capture has now been replayed under the guarded helper.
All seven TAA inputs and its post-dispatch UAV were exported in native formats;
the direct RDC history extraction exactly matches replay `t6`. The recovered
main apply reaches 97.5342781 percent exact packed R11G11B10 pixels, with every
red/green value and all but four blue values within one stored code. See
`HAIR_TEMPORAL_RECONSTRUCTION.md` and the enclosing workspace's
`capture-tools/taa-apply-comparison/report.json`. No further game launch is
needed for this validation boundary.

## Raw-input menu continuation

Ordinary posted WM_KEYDOWN/WM_LBUTTONDOWN messages do not navigate the retail
profile menu. The input callback consumes RAWKEYBOARD events. The built-in
`-playthrough_no_save -level i29 -checkpoint CHK_MARKETING_PACKART_RATCHET`
options were verified in the parser and shipped checkpoint table, and the
live process shows playthrough=1/no_save=1, but startup still reaches profile
selection. These options alone have not established a character scene.

`private_menu_input.cpp` now compiles with MSVC /W4 /WX and was loaded after
automatic approval. It installs a WH_GETMESSAGE hook only on the private game's
own UI thread. Commands in `menu-key-now` are `unique-label|enter` (or escape,
space, up, down). The adapter sends paired make/break events through the exact
existing RAWKEYBOARD handler at RVA 0x16c0b60, verifies its code prefix and
input-object vtable, and leaves executable/shader bytes unchanged. Its loader
also verifies the whole executable hash, private desktop and owned PID. No
global keyboard/mouse input is used. It has a 20-minute deadline and an explicit
key allowlist. `private-menu-input.txt` records press/release acknowledgment.
The first Enter pair was acknowledged and `riftapart-checkpoint_capture_2.rdc`
replays the Continue Game menu with Resume selected. A second acknowledged
Enter activated Resume; `_3.rdc` records the resulting scene for inspection.


After Resume, 30 ms captured only compute work; 200 ms captured geometry but
still ended inside one engine frame (53 draws, 11 dispatches, no display target).
`private_renderdoc_frames.cpp` uses the same public API and waits for two changes
of the verified engine frame counter (upper 32 bits of fence target), capped at
ten seconds. Its trigger is `capture-frames-now`, its report is
`private-renderdoc-frames.txt`, and its loader switch is `--capture-frames`.
Do not change the other capture triggers while this controller is in use.
The `_3.rdc` and `_4.rdc` checkpoint recordings are partial pipeline evidence;
they are not complete scene references.

## Gameplay capture and shader evidence

`riftapart-checkpoint_capture_5.rdc` spans two engine frame-counter changes
(1,203 ms), replays 3,540 actions / 874 textures, and contains Ratchet in gameplay.
The final composed export is severely striped, but the G-buffer and isolated
Hair output at event **17544** render coherent Ratchet geometry and fur.
`riftapart-checkpoint_capture_6.rdc` repeats the two-frame interval (1,516 ms),
replays 2,076 actions / 901 textures, and shows the gameplay scene without that
severe striping. It catches a death animation; no-save was verified in the game.
The requested checkpoint name is not proof that startup selected that checkpoint.

Event 17544 uses `CS_ApplyGBufferLighting_Hair`, DXIL SHA-256
`3f207392ea3179871c2fe5ec50f91ec127c102b6290d67553a81654359220bc0`, identical to
the recovered shader (hash `5ff73b6b2aca9640cf18cd78b88ba3c0`). The broad shader
inventory stopped at its six-minute deadline after 1,501 / 3,174 draw/dispatch
records; it must not be presented as a complete inventory.

`hair-event-17544/` exports b0/b6, probe records/lookup, both cube resources,
G-buffer inputs, BRDF array, work queue and Hair outputs. The companion
`hair-event-17544-extra/` exports the remaining light/shadow/AO inputs and the
complete 536,805,376-byte light-grid buffer (SHA-256
`a279cd363c08f9905c59938223f6ea2226c34f142f5ca30f5902785518ac4667`).
The cube resources retain all six authored mips and all 64 local cube slots.
Neither export reports RenderDoc diagnostics.

`debug-hair-17544-ear/` contains a completed 3,148-state offline DXIL trace,
group 59 / lane 29. GPU work-queue append order changes across replays: the
initial requested pixel was (757,675), but the trace actually processed
**(781,683)**. Use traced `_319/_320`, never the pre-trace group-to-pixel lookup.
The traced point is (-300.1943359, 8.3412542, 711.2202759), with this capture's
own constants, vectors and probe mask. No frame-7328 point/mask is reused.
`captured-indirect-17544/` assembles the raw resources and exact intermediate
values into the existing replay schema. Comparison results follow there.

## Captured indirect-lighting validation

`captured-indirect-16/comparison.json` passes 16 captured queries across Ratchet's
head, arms and tail. Its oracle combines the captured DXIL query arithmetic and
weights with all 64 cube samples independently measured on D3D12 using a temporary
replay-only shader. Native BC6U upload gives maximum error 1.1920929e-7 in specular
and visibility; all other reported outputs match exactly. These queries have
full grid fallback and no local diffuse-probe coverage. They do not validate the
remaining direct/shadow/G-buffer/temporal pipeline.

The first apparent large renderer error came from the offline DXIL debugger:
all 32 t33 default-cube samples differ from direct D3D12 hardware (max 0.41015625),
while all 32 t35 local-cube samples match. Native BC6U textures also avoid the
small filtering/rounding differences introduced by decoding into RGB32F. Original
traces and the initial discrepancy report remain intact; corrected hardware
comparisons are explicitly labelled rather than overwriting the raw evidence.

The active record 10 / cube 18 matches cooked runtime probe `F896FB5315175B7C` in
`9C292F5F8A79EEC2` / `tile_zz27_lgt.zone`. Its first 124 bytes match exactly using
the existing builder and an identity matrix, verified against the raw cooked
zone. Camera-dependent Z bins remain separate. Nine other captured records also
match identity placement in the selected inventory. See
`captured-probe-placement-matches.json`. This active probe uses scene draw lists,
not a stored atlas: first-list face counts are 2349/384/1/217/308/886, with current
model resolution 2169/255/0/115/171/692. Do not substitute a nearby baked cube.

`captured-probe-asset-matches.json` verifies all 36 face/mip hashes for cube 5 /
B433EC02270F0C11, cube 38 / 9FB63E36C8C7D0C0, and cube 40 / 837545B07B72296F.
These are mappings for this capture only; old frame-7328 cube indices are unrelated.

## Full Hair comparison and viewport continuation — 2026-09-03

See [HAIR_FULL_REPLAY.md](HAIR_FULL_REPLAY.md). The capture's original DXIL output
replays byte-exactly. Native DXBC replay identifies compiler differences, and the
shared DXIL noise data flow reduces the complete Hair comparison to six one-step
color differences across 11,215 valid pixels. Twenty-three independent D3D12 UAV
stores establish the observed R11G11B10 round-toward-zero conversion.

Sampler inspection, output-format probes, native DXBC replay, and the native
BC6U/noise viewport smoke all ran on bounded private desktops and exited. One
initial viewport smoke used an incorrect `asset_archive` TOC path and exited
without loading the model; the successful retry uses the confirmed game root.
No game/Steam process was started for these replay checks. Original display
preferences remain restored and Default stayed the input desktop.

The later native float probe uses the installed Windows SDK DXIL assembler and
validator. Its unmodified control reproduces the full captured output byte for
byte. Seven replay-only final-store encodings recover every valid Hair RGB float;
all 11,215 quantize back to the captured output. See
`capture-tools/d3d-hair-float-probe-17544/comparison.json`. Initial unsigned
containers were ineffective, so the probe rejects unchanged instrumented output.
Both native-float private jobs exited normally.

## Guarded native TAA capture — 2026-09-04

The official launcher was used on an inactive desktop to select native TAA for
one capture. The game ran with `-nosound`; the exact game PID was also muted by
the process-specific Core Audio watcher. The launcher was then returned to
Anti-Aliasing Off and Upscale Method Off. The user preferences file retained
SHA-256 `0e30185022ed1a71dae29983f8588320b99ec811bcd013333967d708c40940b8`
before and after the session. `launcher-restore-aa-safe-two-final.json` records
the restored controls and `Default` input desktop.

`riftapart-taa-two-frame_capture.rdc` is 2,638,691,664 bytes with SHA-256
`16e03131a6c26cc7ebe8e72922184f8e251bd8c38a61c29d02d2b30219203d72`.
It spans engine boundaries 3654 through 3656. Compute-only replay passed with
3,827 actions, 212 dispatches and 62 distinct compute shaders. Event 20572 is
the sole native `CS_TemporalAaApply`; its DXIL matches the static executable
container exactly. The targeted runtime exporter saved its shader, assembly,
224-byte cbuffer and binding metadata without debug messages. See
`taa-apply-runtime/report.json` and `taa-apply-runtime-analysis/report.json`.

Do not reuse `private_renderdoc_safe_two_frame.dll` until it is audited. Its own
report records available page file below its stated during-capture threshold
without discarding, so source intent and loaded behavior are not considered a
valid guard. The capture itself is complete and needs no repeat game session.

The offline private-desktop helper now supports minimum physical-memory,
page-file and disk thresholds plus a hard per-job memory cap. A raw texture
export attempt used 16/24/20 GiB minimum headroom and a 12 GiB job cap.
RenderDoc reached `E_OUTOFMEMORY` while opening the large capture, spawned its
contained crash reporter, and was terminated with the entire owned job. No raw
texture was exported; the input desktop remained `Default`, and process and
memory checks after cleanup found no game, Steam, qrenderdoc or renderdoccmd
process. Use a reduced capture or measured replay path for the remaining texture
comparison rather than simply raising the cap.

The helper now refuses insufficient headroom before creating a process and
rechecks while the child is suspended inside the capped job before resuming it.
This closes the launch-time window in the earlier helper, where its first
headroom check occurred immediately after resume.
