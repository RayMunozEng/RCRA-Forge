"""Perspective-correct CPU skin projection versus raw GPU skeletal velocity."""
from pathlib import Path
import json,math,hashlib
import numpy as np
from PIL import Image,ImageDraw
out=Path(__file__).resolve().parent/'recovered/skeletal-accuracy-20260907'
r=json.loads((out/'report.json').read_text());results=[];pictures=[]
for row in r['captures']:
 label=row['label'];w,h=row['width'],row['height']
 previous=json.loads((out/(label+'-previous.json')).read_text());current=json.loads((out/(label+'-current.json')).read_text())
 indices=np.array(current['indices']).reshape(-1,3)
 assert previous['indices']==current['indices']
 basis=np.array([row['basis'][k] for k in ('right','up','forward')]);eye=np.array(row['eye'])
 a=(np.array(current['vertices'])-eye)@basis.T;b=(np.array(previous['vertices'])-eye)@basis.T
 f=w/(2*math.tan(math.radians(row['horizontal_fov']/2)))
 screen=a[:,:2]/a[:,2,None]*[f,-f]+[w/2,h/2]
 depth=np.full((h,w),np.inf);pred=np.zeros((h,w,2));interior=np.zeros((h,w),bool)
 for ids in indices:
  t=screen[ids];z=a[ids,2]
  if z.min()<=0:continue
  lo=np.maximum(np.floor(t.min(0)).astype(int),0);hi=np.minimum(np.ceil(t.max(0)).astype(int),[w-1,h-1])
  if (lo>hi).any():continue
  det=(t[1,1]-t[2,1])*(t[0,0]-t[2,0])+(t[2,0]-t[1,0])*(t[0,1]-t[2,1])
  if abs(det)<1e-8:continue
  yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];x=xx+.5;y=yy+.5
  u=((t[1,1]-t[2,1])*(x-t[2,0])+(t[2,0]-t[1,0])*(y-t[2,1]))/det
  v=((t[2,1]-t[0,1])*(x-t[2,0])+(t[0,0]-t[2,0])*(y-t[2,1]))/det
  bary=np.stack([u,v,1-u-v],axis=-1);weights=bary/z;inv=weights.sum(-1)
  ok=(bary.min(-1)>=0)&(inv>0)
  d=1/np.maximum(inv,1e-20);ok &= d<depth[yy,xx]
  if not ok.any():continue
  weights/=np.maximum(inv[...,None],1e-20)
  prev=weights@b[ids];ps=prev[...,:2]/prev[...,2,None]*[f,-f]+[w/2,h/2]
  depth[yy[ok],xx[ok]]=d[ok];pred[yy[ok],xx[ok]]=np.stack([x,y],-1)[ok]-ps[ok]
  interior[yy[ok],xx[ok]]=bary.min(-1)[ok]>.12
 raw=np.fromfile(out/(label+'.f32'),dtype='<f4').reshape(h,w,4).astype(float)
 velocity=(raw[:,:,:2]-32767/65535)/(.499*.5);velocity=velocity*abs(velocity)*.5*[w/2,-h/2]
 mask=interior&(raw[:,:,0]>0)
 # Exclude silhouette neighbors to avoid disagreements from raster coverage.
 for _ in range(2):mask &= np.roll(mask,1,0)&np.roll(mask,-1,0)&np.roll(mask,1,1)&np.roll(mask,-1,1)
 err=np.linalg.norm(velocity-pred,axis=2)
 assert mask.sum()>100
 stats=dict(label=label,pixels=int(mask.sum()),predicted_p95=float(np.percentile(np.linalg.norm(pred[mask],axis=1),95)),measured_p95=float(np.percentile(np.linalg.norm(velocity[mask],axis=1),95)),median_error=float(np.median(err[mask])),p95_error=float(np.percentile(err[mask],95)),max_error=float(err[mask].max()),within_0_05_fraction=float((err[mask]<.05).mean()),raw_sha256=hashlib.sha256((out/(label+'.f32')).read_bytes()).hexdigest())
 stats['pose_sha256']={k:hashlib.sha256((out/(label+'-'+k+'.json')).read_bytes()).hexdigest() for k in ('previous','current')}
 stats['passed']=stats['p95_error']<.05
 results.append(stats)
 np.savez_compressed(out/(label+'-comparison.npz'),prediction=pred.astype('float32'),measured=velocity.astype('float32'),mask=mask)
 t=np.clip(err/.05,0,1);heat=np.stack([t*255,(1-t)*180,np.zeros_like(t)],-1).astype('uint8');heat[~mask]=0;pictures.append(heat)
result=dict(passed=all(x['passed'] for x in results),captures=results,limits='CPU uses engine skin matrices and skin weights, independently rasterized/projected in Python. Opaque zero-WPO production leader-pose follower; no fur deformation in this accuracy isolation. No native animation parity claim.')
(out/'validation.json').write_text(json.dumps(result,indent=2))
canvas=Image.new('RGB',(1000,560),'#17191e');d=ImageDraw.Draw(canvas)
for i,(row,heat) in enumerate(zip(results,pictures)):
 x=i%2*500;y=i//2*280;canvas.paste(Image.fromarray(heat).resize((500,215)),(x,y+40));d.text((x+10,y+8),row['label']+f" | P95 error {row['p95_error']:.5f}px",fill='white')
canvas.save(out/'accuracy.png')
(out/'comparison.html').write_text('<!doctype html><meta charset="utf-8"><style>body{background:#17191e;color:white;font:17px system-ui;margin:30px}img{max-width:100%}a{color:#8cf}</style><h1>Skeletal motion accuracy: '+('PASS' if result['passed'] else 'NEEDS INVESTIGATION')+'</h1><p>Green: agreement. Red: error at or above 0.05 render pixels. Black: excluded pixels.</p><img src="accuracy.png"><p>'+result['limits']+'</p><a href="validation.json">Measurements</a>')
print(json.dumps(result,indent=2))

assert result['passed'], 'Skeletal projection accuracy exceeded tolerance'
