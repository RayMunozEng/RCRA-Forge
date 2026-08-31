# Character Fur Rendering Handoff

Date: 2026-08-31  
Branch: `main`  
Fork: `https://github.com/RayMunozEng/RCRA-Forge`  
Status: **experimental; not retail parity and not visually accepted**

## User-visible state

The viewer now discovers and decodes the special fur material textures used by
Ratchet and similarly authored characters. It also renders a procedural GPU
strand pass. The strand pass runs, but the user correctly rejected its visual
quality. Do not describe the current output as correct or retail parity.

The latest public verification image is:

`docs/verification/ratchet-fur.png`

That image is evidence of the current failure mode, not an approved target.
It was captured from the head-only Ratchet bangle at LOD1 because the smoke
test deliberately switches from LOD0 to LOD1 to verify texture rebinding.

## Commits in this work

- `c0b4ccc` — parse and load shipped fur material textures
- `a20bc37` — remove incorrect generated shells and hide untextured composite helpers
- `2da9dd7` — add the current experimental geometry-shader strand pass
- `38f1a45` — update the public verification capture

## Confirmed asset evidence

### Models

- Full Ratchet: `0xADE5909F821E9DDE`
  - `characters/hero/hero_ratchet/hero_ratchet.model`
- Ratchet head bangle used for the focused smoke test: `0xAA4A5371E9C251F7`
  - `characters/hero/hero_ratchet/bangle_set/bangle_head_default/hero_ratchet_bangle_head_default.model`

### LOD0 head geometry

In the head bangle:

- Fur-root surface, material index 2:
  - 18,630 vertices
  - 35,888 triangles
  - 9 connected components
- Ordinary head surface, material index 4:
  - 6,202 vertices
  - 11,664 triangles
- Composite-shell helper, material index 5:
  - 6,519 vertices
  - 11,872 triangles
  - no decoded albedo of its own

The fur geometry is a dense connected surface, not exported individual hair
cards. The separate `compositeshell` mesh must not be drawn as an ordinary
opaque material; doing so caused the large flat pink/white patches seen in an
earlier capture.

### Special material format

Ordinary materials use DAT1 section `0xF5260180`. Fur materials instead use
section `0xD9B12454`, with a 36-byte settings header followed by DAT1 string
offsets. Ratchet's head material resolves four textures:

1. `hero_ratchet_Head_c.texture`
2. `hero_ratchet_Head_n.texture`
3. `hero_ratchet_Head_g.texture`
4. `hero_ratchet_head_fur_control.texture`

The observed raw header values include `0.03`, `16.0`, `1.0`, `1.0`, `1.0`,
and `0.1`, but their meanings have **not** been reverse-engineered. Do not
assume that `0.03` is retail strand length or that `16.0` is a shell count.

Ratchet also has special fur-format materials for limbs and tail whose paths
do not include the word `fur`. Detection must therefore remain based on the
`fur_control` binding, not solely on material-name keywords.

## What is implemented

### Material parsing and texture loading

Files:

- `core/material.py`
- `core/asset_loader.py`
- `exporters/texture_exporter.py`

The parser recognizes `0xD9B12454`, resolves its string-pool offsets, assigns
the `fur_control` role, and sends base color, normal, specular, and control maps
through the normal progressive texture-loading path. This portion worked in
the live app for Ratchet's head, limbs, and tail.

### Viewport rendering

File: `ui/viewport.py`

The viewport:

- uploads `fur_control` as a dedicated GPU texture;
- treats the control binding as the authoritative fur-material signal;
- hides composite-shell helpers from the shaded pass;
- draws the ordinary textured fur-root surface;
- then runs `FUR_VERT_SRC`, `FUR_GEOM_SRC`, and `FUR_FRAG_SRC`.

The geometry stage currently emits three camera-facing ribbon fibers per
source triangle. This is a synthetic approximation, not recovered retail
strand data.

## Known problems in the current strand pass

These issues are confirmed by code inspection and the live capture:

1. **Invented root distribution** — exactly three fibers are emitted at fixed
   barycentric positions per triangle, so density follows mesh triangulation.
2. **Unverified channel semantics** — the shader assumes fur-control RG is comb
   direction, B is length, and A is density. That mapping is plausible from
   channel statistics but has not been decoded from the retail shader.
3. **Arbitrary dimensions** — strand length and width constants are hand-tuned,
   not read from confirmed material parameters.
4. **Incorrect shading model** — fibers use basic diffuse lighting only. There
   is no anisotropic specular response, backscatter, self-shadowing, roughness,
   or strand normal model.
5. **Transparency artifacts** — camera-facing ribbons use ordinary alpha
   blending with depth writes disabled and no order-independent transparency.
6. **Aliasing** — texture sampling is forced to mip 0 in the geometry shader,
   and there is no alpha-to-coverage, strand-aware antialiasing, or temporal
   stabilization.
7. **LOD sensitivity** — root count changes with model triangulation. The
   published capture is LOD1 and therefore does not prove LOD0 quality.
8. **Performance unmeasured** — the full Ratchet model has multiple fur
   materials. The head-only model was tested, but full-character strand cost
   has not been profiled.

Lighting contributes to the bad look, but it is not the root cause. The larger
problems are synthetic geometry, unverified control interpretation, arbitrary
strand dimensions, and inadequate transparency/antialiasing.

## Verification already run

- `python -m pytest -q`
  - 72 tests passed after the strand pass was added.
- Live Windows/PyQt/OpenGL smoke test on asset `0xAA4A5371E9C251F7`
  - valid OpenGL context;
  - geometry shader linked successfully;
  - base color and `fur_control` reached the GPU;
  - LOD texture rebinding completed;
  - screenshot captured successfully.

These checks prove that the code path runs. They do **not** prove visual parity.

## Recommended next steps

1. Treat `2da9dd7` as an experiment, not a parity implementation. Consider
   placing the geometric strand pass behind an explicit experimental toggle or
   temporarily disabling it while reverse engineering continues.
2. Extract and inspect the retail shader/permutation selected by special fur
   materials. Resolve the exact meaning of `0xD9B12454` fields and each
   `fur_control` channel before tuning constants.
3. Determine whether additional strand/root data exists in currently unparsed
   model vertex streams or other DAT1 sections. The current model parser only
   exposes position, normal, and UV inputs to the fur pass.
4. Capture a close LOD0 retail reference and a matching viewer angle. Use that
   as the visual acceptance oracle for silhouette length, density, direction,
   color, and lighting.
5. Once data semantics are known, implement the correct root distribution and
   a strand-appropriate lighting/transparency path. Add screen-space LOD and
   antialiasing before testing the full character.
6. Extend the GPU smoke report with fur-specific evidence: fur material count,
   bound control textures, active fur program, chosen LOD, and strand/root
   counts. Do not rely only on a screenshot.
7. Validate at least Ratchet, Rivet, and one non-hero fur asset before claiming
   generic support.

## Local-only files to preserve

The following files are intentionally untracked and should not be committed or
deleted:

- `hashes.txt.cache`
- `launch_live_game.bat`

`launch_live_game.bat` contains a machine-specific Steam installation path.

