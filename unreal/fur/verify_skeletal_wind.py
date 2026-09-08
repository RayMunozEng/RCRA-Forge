"""Check raw skeletal velocity activity and settling; generate a visual report."""
from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image,ImageDraw
out=Path(__file__).resolve().parent/'recovered/skeletal-wind-20260907'
report=json.loads((out/'report.json').read_text());rows=[];heatmaps=[]
for row in report['captures']:
 p=Path(row['file']);w,h=row['width'],row['height']
 a=np.fromfile(p,dtype='<f4').reshape(h,w,4).astype(float)
 assert np.isfinite(a).all() and row['format'] in ('G16R16','PF_G16R16')
 valid=a[:,:,0]>0
 v=(a[:,:,:2]-32767/65535)/(.499*.5);v=v*abs(v)*.5*np.array([w/2,-h/2])
 mag=np.linalg.norm(v,axis=2);mag[~valid]=0
 rows.append(dict(label=row['label'],valid_pixels=int(valid.sum()),moving_pixels=int((mag>.01).sum()),max_pixels=float(mag.max()),p95_valid_pixels=float(np.percentile(mag[valid],95)),bone_follow_error_cm=row['bone_follow_error_cm'],wind=row['wind'],wetness=row['wetness'],raw_sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 heatmaps.append(mag)
poses=[np.array(r['bone_positions']) for r in report['captures']]
motion=float(np.linalg.norm(poses[1]-poses[2],axis=1).max())
checks=dict(bones_move=motion>1,followers_match=all(r['bone_follow_error_cm']<.001 for r in rows),active_states_have_velocity=all(r['moving_pixels']>100 for r in rows[1:7]),still_and_stopped_settle=all(rows[i]['moving_pixels']==0 for i in (0,7)))
checks['weather_states']=all((r['wind']>0)==(2<=i<=6) and (r['wetness']>0)==(i in (4,5)) for i,r in enumerate(rows))
result=dict(checks=checks,passed=all(checks.values()),maximum_sampled_bone_motion_cm=motion,captures=rows,limits='Source-hidden full production shells with live tutorial animation, wind, wetness and TAA. Activity, finite values, pose sharing and final settling only; combined per-pixel accuracy, fast-motion ghosting and retail parity remain unverified.')
(out/'validation.json').write_text(json.dumps(result,indent=2))
canvas=Image.new('RGB',(1000,1120),'#17191e');d=ImageDraw.Draw(canvas)
for i,(row,mag) in enumerate(zip(rows,heatmaps)):
 x=i%2*500;y=i//2*280
 t=np.clip(mag/5,0,1);rgb=np.stack([t*255,t*t*230,t**4*180],axis=2).astype('uint8')
 canvas.paste(Image.fromarray(rgb).resize((500,215)),(x,y+40))
 d.text((x+10,y+8),row['label']+' | '+str(row['moving_pixels'])+' pixels moving >0.01px',fill='white')
canvas.save(out/'velocity-magnitude.png')
parts=['<!doctype html><meta charset="utf-8"><title>Skeletal fur with wind and wetness</title><style>body{background:#17191e;color:#eee;font:17px system-ui;margin:30px}img{max-width:100%}section{display:inline-block;width:48%}a{color:#8cf}</style><h1>Skeletal fur with wind and wetness</h1>', '<p>Activity and settling checks: '+('PASS' if result['passed'] else 'FAIL')+'. Heatmap white = 5 render pixels/frame; poses and live time differ across samples.</p><img src="velocity-magnitude.png">']
for row in rows:parts.append('<section><h2>'+row['label']+'</h2><img src="'+row['label']+'.png"></section>')
parts.append('<p><a href="../skeletal-accuracy-20260907/comparison.html">Controlled skeletal accuracy</a></p>')
parts.append('<p>'+result['limits']+'</p><a href="validation.json">Measurements</a>')
(out/'comparison.html').write_text(''.join(parts));print(json.dumps(result,indent=2))
assert result['passed'],checks
