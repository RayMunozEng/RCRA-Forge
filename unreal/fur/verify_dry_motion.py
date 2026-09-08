"""Measure trails in newly uncovered background after dry fur translation."""
from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent/'recovered'
results={}
for fixture in ('ratchet','sheep'):
 out=root/('dry-motion-'+fixture+'-20260907')
 if not (out/'report.json').exists():continue
 report=json.loads((out/'report.json').read_text())
 if report.get('translation_cm')!=15:
  results[fixture]={'status':'pending corrected whole-character capture'};continue
 rows=report['captures']
 imgs=[np.asarray(Image.open(out/(r['label']+'.png')).convert('RGB')) for r in rows]
 before=imgs[0].max(2)>15;after=imgs[-1].max(2)>3
 # Dilate the final occupied region by eight display pixels; erode prior
 # occupied region. Avoid silhouette fringes and low-contrast foreground.
 for _ in range(8):after |= np.roll(after,1,0)|np.roll(after,-1,0)|np.roll(after,1,1)|np.roll(after,-1,1)
 for _ in range(3):before &= np.roll(before,1,0)&np.roll(before,-1,0)&np.roll(before,1,1)&np.roll(before,-1,1)
 mask=before&~after;mask[:10]=False;mask[-10:]=False;mask[:,:10]=False;mask[:,-10:]=False
 assert mask.sum()>1000,mask.sum()
 records=[]
 for r,im in zip(rows[1:],imgs[1:]):
  v=im.max(2)[mask].astype(float)
  records.append(dict(label=r['label'],elapsed=r['elapsed'],mean_rgb8=float(v.mean()),p95_rgb8=float(np.percentile(v,95)),pixels_above_8=int((v>8).sum()),image_sha256=hashlib.sha256((out/(r['label']+'.png')).read_bytes()).hexdigest()))
 result=dict(fixture=fixture,background_mask_pixels=int(mask.sum()),captures=records,settled_background_clean=records[-1]['pixels_above_8']==0,limits='Newly uncovered background behind the recorded rigid translation. Eight-pixel margin excludes final object. TAA capture cadence is not locked to engine frames; first captured sample may include old render state. This is a diagnostic, not proof of no skeletal trails or native parity.')
 (out/'validation.json').write_text(json.dumps(result,indent=2));results[fixture]=result
 canvas=Image.new('RGB',(1000,640),'#17191e');draw=ImageDraw.Draw(canvas)
 for j,k in enumerate((0,1,3,13)):
  x=j%2*500;y=j//2*320;canvas.paste(Image.fromarray(imgs[k]).resize((500,215)),(x,y+35));draw.text((x+10,y+8),rows[k]['label'],fill='white')
 canvas.save(out/'overview.png')
 labels=[r['label'] for r in rows]
 html='<!doctype html><meta charset="utf-8"><style>body{background:#17191e;color:#eee;font:17px system-ui;margin:30px}img{max-width:100%}a{color:#8cf}</style><h1>Dry '+fixture+' — rapid movement</h1><p>Dry fur only: wind=0, wetness=0. Rigid translation (distance recorded in report.json); actual captured samples, not frame-locked playback.</p><input id="frame" type="range" min="0" max="13" value="0"><span id="label">before</span><br><img id="image" src="before.png"><p>'+result['limits']+'</p><a href="validation.json">Background measurements</a><br><img src="overview.png"><script>const names='+json.dumps(labels)+';document.getElementById("frame").oninput=e=>{const name=names[+e.target.value];document.getElementById("label").textContent=name;document.getElementById("image").src=name+".png";};</script>'
 (out/'comparison.html').write_text(html,encoding='utf-8')
print(json.dumps(results,indent=2))
