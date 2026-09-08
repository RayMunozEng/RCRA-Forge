# Production fur filter checkpoint - 2026-09-08

Production integration is implemented and built, but retail parity and the ear
contour remain incomplete. No preview ZIP or release was produced.

## Completed on the receiving computer

- Runtime `FFurDenoiseViewExtension` runs the recovered surface/active-tile/
  denoise chain before TAA for `RecoveredFurSurface` tagged materials.
- The feature defaults off at `r.FurAuthoring.Denoise=0`. Blueprint can enable
  it and query both enabled and registered state.
- Plugin shader mapping resolves through the plugin base directory, and view
  extension creation is deferred until post-engine-init.
- UE 5.8 `FurValidationEditor` single-worker build succeeded.
- Asset-independent lifecycle check passed, exit 0, peak 1.112 GiB.
- Repository-owned synthetic render check passed, exit 0, peak 4.312 GiB.
  It used the exact recovered layer DDS SHA-256
  `c495993561a2a7cd8a608bd465f7e77898bf958873c9cd65ad342537a928215f`,
  32 shells, TAA2, and false/false/true/true production enable states.
- Render-thread evidence: `Production pre-TAA fur denoise executed: 1 tagged
  batches, 1017x554 view.`
- Verifier metrics: 101,805 subject pixels; 89,253 off-to-on subject pixels
  changed; off-pair MAE 1.926 RGB8; on-pair MAE 1.951 RGB8. This fixture proves
  integration only. It does not show a synthetic temporal-quality improvement.

## Reproduce locally

```powershell
.\.venv\Scripts\python.exe unreal\fur\export_recovered_core.py
.\.venv\Scripts\python.exe unreal\fur\create_map_fixtures.py
.\.venv\Scripts\python.exe unreal\fur\run_check.py validate_production_filter_registration.py --engine-root 'C:\Program Files\Epic Games\UE_5.8'
.\.venv\Scripts\python.exe unreal\fur\run_check.py capture_synthetic_production_filter.py --engine-root 'C:\Program Files\Epic Games\UE_5.8'
.\.venv\Scripts\python.exe unreal\fur\verify_synthetic_production_filter.py
```

`run_check.py` uses the repository-owned private desktop runner. The synthetic
capture temporarily constrains shader compilation to one worker and restores
the project descriptor/configuration afterward. Keep the 6 GiB aggregate job
cap and default 8 GiB free-memory floor when the destination machine has normal
headroom. The completed receiving-computer run used a temporary 2 GiB floor
because unrelated processes held 23.6 GiB; it stayed at 4.312 GiB under the job
cap. Do not terminate unrelated user processes or raise the hard cap to make a
capture fit.

## Required next work on the asset-bearing computer

1. Build this source on the same UE 5.8 installation.
2. Run `capture_fur_surface_production.py` against the imported sheep fixture,
   inspect the production render-thread marker and images, and run the existing
   surface/live verifier without changing its acceptance gates.
3. Add/run the equivalent production wrapper for Ratchet. Compare both against
   the existing private continuous-filter evidence; do not infer parity from the
   synthetic sphere.
4. Restore the saved retail capture and `ear-strand-audit` inputs, then run
   `audit_native_strand_draws.py` under the existing inactive-desktop and resource
   guards. Establish which pixels/scene object the ModelStrand draws affect
   before implementing any ear-specific path.
5. Only after those character and retail checks pass should a preview archive
   be built. Keep sheep wool and Ratchet/ear grooming as distinct acceptance
   cases; do not apply one generic fur technique to all of them.

The legacy `CHECKPOINT.md` was preserved byte-for-byte because it contains a
non-UTF-8 historical byte. This dedicated UTF-8 checkpoint is the continuation
source for the production-filter work.
