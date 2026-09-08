"""Preserved spatial-isolation captures, without resampling source images."""
import json
from pathlib import Path
from PIL import Image
import numpy as np
root=Path(__file__).resolve().parent/'recovered'
panels=[];metrics={}
for folder,labels in [('ear-boundary',['reference','outer-only','base-only','colored']),
                      ('ear-resampling',['reference32','raw64','normalized64'])]:
    report=json.loads((root/folder/'report.json').read_text())
    assert [r['label'] for r in report]==labels
    assert all(r['resolved_aa_method']==2 and r['draw_realtime'] for r in report)
    for label in labels:
        path=root/folder/(label+'.png')
        im=np.asarray(Image.open(path).convert('RGB'))
        assert im.shape==(942,2191,3)
        if label=='colored':
            roi=im[460:745,1250:1750]
            red=(roi[:,:,0]>100)&(roi[:,:,1]<50)&(roi[:,:,2]<50)
            cyan=(roi[:,:,1]>100)&(roi[:,:,2]>100)&(roi[:,:,0]<50)
            metrics.update(ear_red_pixels=int(red.sum()),ear_cyan_pixels=int(cyan.sum()))
        panels.append(f'<article><h2>{folder}: {label}</h2><div class="crop"><img src="../{folder}/{label}.png" alt="{label}"></div><a href="../{folder}/{label}.png">Full original</a></article>')
out=root/'ear-contours'
(out/'boundary-comparison.html').write_text('''<!doctype html><meta charset="utf-8"><title>Ear boundary isolation</title>
<style>body{background:#181a20;color:#eee;font:16px system-ui;margin:24px}.panels{display:flex;gap:20px;flex-wrap:wrap}h2{font-size:17px}.crop{position:relative;width:500px;height:285px;overflow:hidden;background:black}.crop img{position:absolute;width:2191px;max-width:none;height:942px;left:-1250px;top:-460px}a{color:#9bcaff}p{max-width:1000px}</style>
<h1>Ear boundary isolation</h1><p>Red identifies the base shell; cyan identifies all nonbase shells. Removing the base does not eliminate the rim. The count-normalized test is an authoring experiment, not a recovered native algorithm or an accepted fix.</p>
<div class="panels">'''+''.join(panels)+'</div>',encoding='utf-8')
(out/'boundary-comparison.json').write_text(json.dumps(metrics,indent=2))
print(metrics)
