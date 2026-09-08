"""Compare preserved captures; build a static viewer without new GPU work."""
from pathlib import Path
import hashlib
import html
import json
import sys
import numpy as np
from PIL import Image

root = Path(__file__).resolve().parent / 'recovered'
out = root / 'ear-contours'
roi = (1250, 460, 1750, 745)
rows = []
panels = []
base = None
base_report = None
geometry = '--geometry' in sys.argv
temporal = '--temporal' in sys.argv
assert not (geometry and temporal)
modes = (('authored', 'far-background') if temporal else
         ('authored', 'fixed-spacing', 'uniform-length') if geometry else ('none', 'contact', 'denoise', 'both', 'shell-depth'))
for mode in modes:
    folder = ('forge-environment-ratchet-both' + ('' if mode == 'authored' else '-' + mode)
              if geometry or temporal else 'forge-environment-ratchet' + ('' if mode == 'none' else '-' + mode))
    path = root / folder / 'environment.png'
    report = json.loads((path.parent / 'report.json').read_text())
    pixels = np.array(Image.open(path).convert('RGB')).astype(np.float32)
    assert pixels.shape == (942, 2191, 3), pixels.shape
    if base is None:
        base = pixels
        base_report = report
    for key in ('camera', 'model', 'lod', 'viewport_size', 'temporal_sample_count'):
        assert report[key] == base_report[key], key
    meta = report['environment_comparison']
    assert meta['horizontal_fov'] == 60 and meta['background'] == 'black, grid disabled in private process'
    if geometry or temporal:
        assert meta['post_mode'] == 'both'
        if geometry:
            assert report.get('geometry_diagnostic', {'mode': 'authored'})['mode'] == mode
        else:
            assert report.get('temporal_background_diagnostic', {'mode': 'zero'})['mode'] == ('zero' if mode == 'authored' else 'far')
        for key in ('fur_contact_shadow', 'fur_hair_denoise'):
            assert report[key] == base_report[key], key
    elif mode != 'shell-depth':
        assert meta.get('post_mode', 'none') == mode
    row = dict(mode=mode, image=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               actual_post_settings={k: v for k, v in report.items()
                                     if 'contact' in k or 'denoise' in k or 'screen_space_shadow' in k})
    if mode != 'shell-depth':
        diff = np.abs(pixels - base)
        row.update(whole_image_mae_rgb8=float(diff.mean()),
                   ear_rectangle_mae_rgb8=float(diff[roi[1]:roi[3], roi[0]:roi[2]].mean()))
    else:
        row['diagnostic'] = report['shell_depth_diagnostic']
    rows.append(row)
    src = '../' + folder + '/environment.png'
    panels.append(f'<article><h2>{html.escape(mode)}</h2><div class="crop"><img src="{src}" alt="Ear rim: {mode}"></div><a href="{src}">Full original capture</a></article>')

stem = 'temporal-comparison' if temporal else 'geometry-comparison' if geometry else 'post-comparison'
(out / (stem + '.json')).write_text(json.dumps(dict(
    roi_xyxy=roi, limits='MAE measures image change, not contour improvement. False-color view retains lighting and temporal averaging.',
    rows=rows), indent=2))
intro = ('<p>Geometry isolation with contact shadows and denoising enabled in every image. Authored is the reference. Fixed-spacing removes view-dependent shell spacing and rejection. Uniform-length replaces the vertex length texture with 0.5, also affecting curved UV offsets. These are experiments, not proposed fixes.</p>' if geometry else
         '<p>Shell-depth colors: red = base; cyan = shell slice 0–4 (excluding base); green = 4–8; blue = 8–16; magenta = 16–32. This is diagnostic albedo with lighting and temporal averaging still active, so colors can mix.</p>')
if temporal:
    intro = '<p>Stationary temporal-depth isolation: authored preview background uses zero depth; far-background substitutes depth 100 only in the temporal opaque/composed depth producer. Fur geometry and shading are unchanged. This does not add a complete background scene or its motion/scatter inputs.</p>'
(out / ((stem + '.html') if geometry or temporal else 'comparison.html')).write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Ear contour investigation</title><style>
body{background:#181a20;color:#eee;font:16px system-ui;margin:24px}h1{font-size:24px}
.panels{display:flex;flex-wrap:wrap;gap:24px}article{background:#252833;padding:16px}
h2{font-size:18px;margin:0 0 12px}.crop{width:500px;height:285px;overflow:hidden;position:relative;background:black}
.crop img{position:absolute;max-width:none;width:2191px;height:942px;left:-1250px;top:-460px}
a{color:#9bcaff;display:block;margin-top:10px}p{max-width:1000px;line-height:1.5}
</style><h1>Ear rim: preserved Forge captures</h1>
<p>Identical 1:1 pixel crops. Contact shadows and denoising change the shading, but these tests have not demonstrated removal of the contour.</p>
''' + intro + '<div class="panels">' + ''.join(panels) + '</div></html>', encoding='utf-8')
print(json.dumps(rows, indent=2))
