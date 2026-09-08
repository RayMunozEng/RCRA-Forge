# Matched fur comparison

Both renderers use the same studio cube, recovered BRDF, dry fur, key direction,
60-degree horizontal field of view and black background. Forge and Unreal use
different temporal and raster paths. Eyes, helmet and other non-fur materials
are outside this comparison.

| Fixture | Interior fur mean absolute difference (RGB8) | Finding |
| --- | ---: | --- |
| Ratchet | 6.00 | Mean color is close; local texture/highlight differences remain. |
| Sheep | 3.01 | Corrected Forge BC1 sRGB upload; previous difference was 12.53. |

## Ratchet — Forge
![Forge Ratchet](F:/Cloud-Drive_rmunoz1994@gmail.com/Github/gem-shader/unreal/fur/recovered/forge-environment-ratchet/environment.png)

## Ratchet — Unreal
![Unreal Ratchet](F:/Cloud-Drive_rmunoz1994@gmail.com/Github/gem-shader/unreal/fur/recovered/environment-ratchet/key-environment.png)

## Sheep — Forge
![Forge sheep](F:/Cloud-Drive_rmunoz1994@gmail.com/Github/gem-shader/unreal/fur/recovered/sheep-combined-srgb-fixed-20260907/environment.png)

## Sheep — Unreal
![Unreal sheep](F:/Cloud-Drive_rmunoz1994@gmail.com/Github/gem-shader/unreal/fur/recovered/environment-sheep/key-environment.png)

2026-09-07: traced the sheep mismatch to Forge dropping the explicit BC1 sRGB
format on its gloss/specular texture. Unreal's source color-space handling was
already correct. BC1/2/3 now preserve authored sRGB tags like the BC7 path.
The captured sheep response binding changed from linear DXT1 (33777) to sRGB
DXT1 (35917); control stays linear. No lighting intensity or material tuning.

Environment-only difference fell from 16.49 to 2.13 (87% reduction); combined
lighting fell from 12.53 to 3.01 (76%). Ratchet's before/after PNG hashes are
identical. Four BC-format regression cases passed. See
`recovered/sheep-srgb-fix-validation.json` and `verify_sheep_srgb_fix.py`.

![Before, corrected, Unreal](F:/Cloud-Drive_rmunoz1994@gmail.com/Github/gem-shader/unreal/fur/recovered/sheep-srgb-fix-comparison.png)

Remaining work: ear silhouette/temporal differences and native scene-lighting
parity. This controlled comparison does not establish complete retail parity.
The existing Unreal preview package needs no change for this Forge upload fix.


Follow-up: decoded RGBA fallback uploads now preserve explicit source sRGB
formats too, and format changes invalidate the upload cache. 23 targeted
format/upload regressions pass, covering compressed mip chains, mip0,
decoded responses, source-format changes, albedo and linear controls. This
follow-up used mocked GPU calls; the rendered comparisons above validate the
compressed path from the preceding checkpoint.
