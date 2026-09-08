"""Build original-pixel crops for the spatial-spacing acceptance check."""
from pathlib import Path
import json
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parent/'recovered'
folder=root/'ear-spacing';out=root/'ear-contours'
report=json.loads((folder/'report.json').read_text())
assert [r['spacing'] for r in report]==[0,.5,1]
assert all(r['draw_realtime'] and r['resolved_aa_method']==2 for r in report)
panels=[];rows=[];reference=None
for row in report:
    label=row['label'];pixels=np.asarray(Image.open(folder/(label+'.png')).convert('RGB'),dtype=np.float32)
    assert pixels.shape==(942,2191,3)
    roi=pixels[460:745,1250:1750]
    if reference is None:reference=roi
    rows.append(dict(label=label,ear_roi_mae_rgb8=float(np.abs(roi-reference).mean())))
    panels.append(f'<article><h2>{label}</h2><div class="crop"><img src="../ear-spacing/{label}.png" alt="{label}"></div><a href="../ear-spacing/{label}.png">Full original</a></article>')
(out/'spacing-comparison.html').write_text('''<!doctype html><meta charset="utf-8"><title>Spatial shell spacing</title>
<style>body{font:16px system-ui;background:#181a20;color:#eee;margin:24px}.panels{display:flex;gap:24px;flex-wrap:wrap}.crop{position:relative;width:500px;height:285px;overflow:hidden;background:black}.crop img{position:absolute;max-width:none;width:2191px;height:942px;left:-1250px;top:-460px}a{color:#9bcaff}p{max-width:1000px}</style>
<h1>Spatial shell spacing experiment</h1><p>Original coverage equation, 32 shells. Interior depths vary smoothly across rest-position coordinates; endpoints stay fixed. This is an authoring experiment, not recovered native behavior. Compare for contour removal, roughness, and unwanted patches.</p><div class="panels">'''+''.join(panels)+'</div>',encoding='utf-8')
(out/'spacing-comparison.json').write_text(json.dumps({'rows':rows,'limits':'Mean absolute difference measures change, not improvement.'},indent=2))
print(rows)
