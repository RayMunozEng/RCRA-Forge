# Fur Rendering Computer Transfer

Date: 2026-09-02

Repository: `https://github.com/RayMunozEng/RCRA-Forge`

Branch: `main`

Source of truth: the commit containing this document

This is the operating handoff for continuing the Rift Apart fur renderer on a
second Windows computer that has its own installed copy of the game. The
detailed reverse-engineering record is in
[`FUR_RENDERING_HANDOFF.md`](FUR_RENDERING_HANDOFF.md).

## Current outcome

The active viewport uses the retail shell-fur architecture, not the retired
camera-facing ribbon prototype:

- exact procedural `Default Fur Shells` 128 x 128 x 32 R8 volume and integer
  mip chain;
- authored per-material layer count, length, density, offset, gloss,
  specular, transmittance, and turbulence;
- decoded tangent frame and handedness from the cooked vertex stream;
- fur-control RG grooming, B extrusion/contact/wind gate, and independent A
  material interpolation;
- recovered shell availability, projected stochastic coverage, wetness,
  reciprocal-depth contact, HairDenoise gather, Hair direct lobes, default
  environment cube, and exact Hair BRDF lookup;
- captured retail wind field with configurable time, strength, direction, and
  object phase;
- off-desktop, non-activating screenshot verification.

This is evidence-backed progress toward retail parity, not a parity claim.
Production local-probe reconstruction, the full deferred/G-buffer integration,
and production temporal history behavior remain incomplete. Sheep uses the
same retail shell pipeline as Lombaxes but retains its distinct authored curly
surface and 9 cm / density 3 material; it must not receive a fabricated
Lombax-style preset.

## Files that carry the implementation

- `core/material.py`: special fur material parsing and authored settings.
- `core/mesh.py`: packed tangent-frame and handedness decoding.
- `core/texture.py`: authored mip handling and BC6 cube decode.
- `core/fur_resources.py`: exact shell volume and embedded exact Hair BRDF.
- `core/asset_loader.py`: fur texture/environment background loading.
- `ui/main_window.py`: fur environment handoff into the viewport.
- `ui/viewport.py`: shell geometry, grooming, wind, water, Hair lighting,
  contact, denoise, and temporal accumulation.
- `tools/analyze_material_headers.py`: installed-material evidence scanner.
- `tools/smoke_fur_viewport.py`: off-desktop GPU verification harness.
- `tests/test_material_resolution.py`, `tests/test_parsers.py`, and
  `tests/test_viewport_textures.py`: regression coverage.

## First setup on the second computer

Open PowerShell and clone the fork:

```powershell
git clone https://github.com/RayMunozEng/RCRA-Forge.git
Set-Location RCRA-Forge
git switch main
git pull --ff-only
```

Create the environment without launching a foreground window:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
```

If `py` is unavailable, install Python 3.10 or newer or use that machine's
Python executable. `run.bat` performs equivalent one-time dependency setup but
also launches the application.

Set a machine-local game path. Do not commit this path:

```powershell
$GameInstallPath = 'D:\SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart'
Test-Path -LiteralPath (Join-Path $GameInstallPath 'toc')
```

The test must print `True`. The repository already contains the tracked
`hashes.txt`. The parser may generate `hashes.txt.cache`; it is intentionally
ignored and can be regenerated on either computer.

## Required verification before changing the renderer

Run the complete automated suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Then run a head-only LOD0 GPU smoke capture. This window is deliberately
off-desktop and non-activating:

```powershell
$GameInstallPath = 'D:\SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart'
$TransferOutputPath = Join-Path $env:TEMP 'rcra-fur-transfer'
New-Item -ItemType Directory -Force -Path $TransferOutputPath | Out-Null
.\.venv\Scripts\python.exe tools\smoke_fur_viewport.py `
  --game-root $GameInstallPath `
  --hashes .\hashes.txt `
  --model 0xAA4A5371E9C251F7 `
  --lod 0 `
  --samples 5 `
  --converge-samples 32 `
  --width 1024 `
  --height 1024 `
  --output (Join-Path $TransferOutputPath 'ratchet-head.png') `
  --report (Join-Path $TransferOutputPath 'ratchet-head.json')
```

Acceptance evidence is both the PNG and JSON report. The report must show a
valid OpenGL context, active fur material(s), rendered shell instances, and
`recovered_procedural_128x128x32` as the layer source. A screenshot alone is
not sufficient.

To exercise the exact captured weather state:

```powershell
.\.venv\Scripts\python.exe tools\smoke_fur_viewport.py `
  --game-root $GameInstallPath `
  --hashes .\hashes.txt `
  --model 0xAA4A5371E9C251F7 `
  --lod 0 `
  --samples 5 `
  --converge-samples 32 `
  --fur-wind-strength 0.030973274260759354 `
  --fur-wind-vector -0.9966111779 0 0.0822560638 `
  --fur-wind-time 104.03866577148438 `
  --fur-wind-object-phase 0.1326904296875 `
  --output (Join-Path $TransferOutputPath 'ratchet-head-wind.png') `
  --report (Join-Path $TransferOutputPath 'ratchet-head-wind.json')
```

The full Ratchet asset is `0xADE5909F821E9DDE`. Use it after the focused head
test passes; it is materially heavier and exercises the head, limb, and tail
fur materials together.

To regenerate the installed-material correlation evidence on the second
computer:

```powershell
.\.venv\Scripts\python.exe tools\analyze_material_headers.py `
  --game-root $GameInstallPath `
  --hashes .\hashes.txt `
  --output (Join-Path $TransferOutputPath 'material-header-correlation.json')
```

## Retail evidence that is not in Git

The following items are intentionally excluded because they are large,
machine-specific, generated, or redistributable game/capture data:

- the installed Rift Apart game and its archives;
- RenderDoc 1.46 portable binaries;
- `work/fur-analysis/captures/riftapart-taa_frame7328.rdc` (about 5 GB);
- extracted frame-7328 textures, buffers, shader disassembly, and JSON reports;
- generated PNG comparisons under the workspace `outputs` directory;
- `hashes.txt.cache` and `hashes.txt.cache.cache`.

The renderer does not require those artifacts. Copy the capture/research
workspace separately only if the second machine must continue exact retail
frame analysis. Otherwise create a fresh capture from that machine's own game
installation. Never launch or hook the retail game on the user's active
desktop during automated work: use the established private-desktop/background
capture path so mouse focus and input remain untouched.

The most useful local visual evidence from the originating machine is:

- `outputs/retail-frame7328-ratchet-crop.png`: retail reference crop;
- `outputs/ratchet-retail-local14-wind-v88.png`: focused dry/wind viewer result;
- `outputs/ratchet-full-local14-rear-close-v89.png`: full-character rear result;
- `outputs/ratchet-retail-local14-wet-v90.png`: recovered wetness-path result.

Captured local cube 14 is valid only for the recorded frame/location. It may be
injected into the smoke harness with `--fur-environment-dds-dir` and
`--fur-environment-cube 14` after copying the extracted DDS directory, but it
must not become a generic default or be presented as archive reconstruction.
The normal application path loads the installed default environment probe and
embedded exact BRDF automatically.

## Evidence anchors

- Hair compute event 68471, shader hash
  `5ff73b6b2aca9640cf18cd78b88ba3c0`.
- HairDenoise event 68478, shader hash
  `d1bd89676f0e3560ee38fd16c950de23`.
- TAA apply shader hash `4e1b2693fbe9696f3f1eb1d6ac577a01`.
- Default environment asset `0x8F083136CEB5FB07`, a 1024 BC6 cube with six
  faces and six mips.
- Exact 64 x 64 RG16F Hair BRDF slice SHA-256
  `4fa9755a296ec4c8c11d19e62598217eedd8625814bb75128c947ca325038672`.
- Captured Ratchet head center `(-230.588, 9.146, 670.816)` selected local
  probe record 10 / cube-array index 14 at full weight.

## Next evidence-backed work

1. Reconstruct production local-probe arrays and spatial blending from archive
   data. The installed Malinon candidate `0x837545B07B72296F` was tested and
   rejected (best correlation 0.09; relative MAE above 0.92), so do not reuse
   it as cube 14.
2. Match the production deferred Hair/G-buffer composition, light-grid,
   shadows, GI, and screen-space occlusion using resource captures and shader
   disassembly rather than visual tuning.
3. Recover production TAA reprojection, rejection, and history weighting for
   stochastic shells. The current 32-sample editor accumulator is practical
   reconstruction, not the retail temporal implementation.
4. Re-run controlled, matched-camera comparisons for Ratchet, Rivet, and Sheep
   after each isolated change. Record shader/resource evidence, report data,
   and image deltas before accepting it.
5. Keep wind and water attached to authored grooming and shell data. Do not
   substitute a character-specific fake or reinterpret control alpha as fur
   length; the live draw proved extrusion uses control blue.

## Commit discipline on the second machine

Before publishing more work:

```powershell
git status --short
git diff --check
.\.venv\Scripts\python.exe -m pytest -q
```

Stage explicit source, tests, tools, and documentation paths. Do not stage
captures, game files, generated comparisons, virtual environments, or cache
files. Record the exact smoke command and JSON evidence in the detailed
handoff when behavior changes.
