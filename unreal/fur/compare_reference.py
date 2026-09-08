"""Measure fixed interior fur regions; deliberately not a whole-image parity score."""
import json
from pathlib import Path
import numpy as np
from PIL import Image

root=Path(__file__).resolve().parent/'matched-reference'
regions={'ear_interior':[350,265,430,310],'cheek_interior':[205,342,230,367]}
def compare(reference,candidate):
    a=np.asarray(Image.open(root/reference).convert('RGB'),dtype=float)
    b=np.asarray(Image.open(root/candidate).convert('RGB'),dtype=float)
    assert a.shape==b.shape==(600,600,3)
    results={}
    for name,rect in regions.items():
        x0,y0,x1,y1=rect
        aa=a[y0:y1,x0:x1];bb=b[y0:y1,x0:x1]
        results[name]={'rectangle_xyxy':rect,'mae_rgb8':float(abs(aa-bb).mean()),
            'forge_mean_rgb8':aa.mean((0,1)).tolist(),'ue_mean_rgb8':bb.mean((0,1)).tolist()}
    return results
scope='Fixed interior fur regions in display-space images; excludes non-fur shading, silhouettes, shadows and environment.'
unlit={'scope':scope,'regions':compare('forge-unlit.png','ue-unlit.png')}
lighting={'scope':scope,'default_lit':compare('forge-lit.png','ue-default-lit.png'),
          'recovered':compare('forge-lit.png','ue-recovered-key.png')}
(root/'unlit-comparison.json').write_text(json.dumps(unlit,indent=2))
(root/'lighting-comparison.json').write_text(json.dumps(lighting,indent=2))
print(json.dumps({'unlit':unlit,'lighting':lighting},indent=2))
