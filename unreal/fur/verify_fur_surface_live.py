"""Inspect actual fur MRT readback; no claim of final filtered image parity."""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
import sys
fixture=sys.argv[1] if len(sys.argv)>1 else 'sheep'
assert fixture in ('sheep','ratchet')
root=Path(__file__).resolve().parent/'recovered'/('fur-surface-live-'+fixture)
meta=json.loads((root/'surface.json').read_text(encoding='utf-8-sig'))
h,w=meta['height'],meta['width']
n=np.fromfile(root/'surface-normal.f32',dtype='<f4').reshape(h,w,4)
s=np.fromfile(root/'surface-strand.f32',dtype='<f4').reshape(h,w,4)
mask=n[...,3]>0
count=int(mask.sum())
assert count>1000 and count<h*w*.8,(count,h*w)
assert np.isfinite(n).all() and np.isfinite(s).all()
assert (s[...,3][mask]>0).all()
full_depth=s[...,3][mask]
assert np.count_nonzero(full_depth!=full_depth.astype(np.float16).astype(np.float32))>1000,'Depth was rounded before native conversion'
lengths={name:np.linalg.norm(data[...,:3][mask],axis=-1) for name,data in [('normal',n),('strand',s)]}
assert all(((v>.8)&(v<1.2)).all() for v in lengths.values())
assert np.count_nonzero(s[~mask])==0
assert np.count_nonzero(n[...,:3][mask]!=n[...,:3][mask].astype(np.float16).astype(np.float32))>1000,'Normal vector was rounded to half'
report=dict(status='passed',surface_format='RGBA32F normal/mask and strand/depth; no intermediate half rounding',submitted_batches=meta['submitted_batches'],dimensions=[w,h],fur_pixels=count,
 depth_meters=[float(s[...,3][mask].min()),float(s[...,3][mask].max())],
 vector_lengths={name:[float(v.min()),float(v.max())] for name,v in lengths.items()},
 limits=['One '+fixture+' static view only.','Opaque scene depth equality used; binary surviving-sample mask.','Pre-TAA filtering is connected in the private validation fixture; not yet a shipped plugin feature.'])
a=np.fromfile(root/'surface-color.f32',dtype='<f4').reshape(h,w,4)
b=np.fromfile(root/'surface-filtered.f32',dtype='<f4').reshape(h,w,4)
assert np.isfinite(a).all() and np.isfinite(b).all()
assert np.array_equal(a[~mask],b[~mask]),'Non-fur colors changed'
assert np.array_equal(a[...,3],b[...,3]),'Alpha changed'
changed=np.any(a!=b,axis=-1)
assert int(changed[mask].sum())>1000
# Distinguish a working gather from color-format truncation alone.
v=np.maximum(a[...,:3]/meta['pre_exposure'],0).astype(np.float32)
quant=np.empty_like(v)
for c in range(3):
 q=v[...,c].copy();bits=q.view(np.uint32)&np.uint32(0xfffc0000 if c==2 else 0xfffe0000)
 factor=524288 if c==2 else 1048576
 quant[...,c]=np.where(q<2**-14,np.floor(q*factor)/factor,bits.view(np.float32))
quant=(quant*meta['pre_exposure']).astype(np.float16).astype(np.float32)
filtered_beyond_store=int(np.any(abs(b[...,:3]-quant)>0.0001,axis=-1)[mask].sum())
assert filtered_beyond_store>1000
report['filter']={'non_fur_pixels_changed':0,'alpha_changed':False,'fur_pixels_changed':int(changed[mask].sum()),'pixels_changed_beyond_color_truncation':filtered_beyond_store,'pre_exposure':meta['pre_exposure']}
frames=json.loads((root/'report.json').read_text())['frames']
assert [x['label'] for x in frames]==['unfiltered-a','unfiltered-b','filtered-a','filtered-b']
assert all(x['draw_realtime'] and x['resolved_aa_method']==2 for x in frames)
photos={x['label']:np.asarray(Image.open(root/(x['label']+'.png')).convert('RGB'),dtype=float) for x in frames}
quality_mask=photos['unfiltered-b'].max(2)>30;quality_mask[:150]=False
quality={mode:float(abs(photos[mode+'-a']-photos[mode+'-b'])[quality_mask].mean()) for mode in ['unfiltered','filtered']}
report['static_pair_mae_rgb8']=quality
report['static_quality_pass']=quality['filtered']<3
report['limits'].append('One unregistered temporal pair per mode; not a frame-locked comparison or native parity proof.')
job=json.loads((root.parent/('fur-surface-live-'+fixture+'-job.json')).read_text())
assert job['root_exit_code']==0
report['peak_job_gib']=job['job_memory']['peak_job_gib']
(root/'validation.json').write_text(json.dumps(report,indent=2))
imgs=[]
for label,data in [('NORMAL',n),('STRAND',s)]:
 rgb=np.zeros((h,w,3),dtype=np.uint8)
 rgb[mask]=np.uint8(np.clip(data[...,:3][mask]*.5+.5,0,1)*255)
 im=Image.fromarray(rgb);im.thumbnail((640,420));imgs.append((label,im))
canvas=Image.new('RGB',(1280,465),(16,20,25));draw=ImageDraw.Draw(canvas)
for i,(label,im) in enumerate(imgs):
 canvas.paste(im,(i*640,32));draw.text((i*640+14,10),label,fill='white')
draw.text((14,445),'Actual Unreal fur-data buffers. Diagnostic colors; visible fur is still unfiltered.',fill='white')
canvas.save(root/'buffers.jpg',quality=92)
beauty=Image.new('RGB',(1280,350),(16,20,25));draw=ImageDraw.Draw(beauty)
for i,(name,label) in enumerate([('unfiltered-b','Filter off: settled TAA'),('filtered-b','Recovered filter on: settled TAA')]):
 im=Image.fromarray(photos[name].astype(np.uint8));im.thumbnail((640,300));beauty.paste(im,(i*640,32));draw.text((i*640+12,10),label,fill='white')
draw.text((12,330),'Actual UE captures. Same material, camera and key/fill/rim lights; different temporal frames.',fill='white')
beauty.save(root/'settled-review.jpg',quality=94)
(root/'comparison.html').write_text('<!doctype html><meta charset="utf-8"><title>Live fur filter</title><body style="background:#101419;color:#ddd;font:18px system-ui;padding:24px"><h1>Recovered fur filter running before TAA</h1><p>Actual '+fixture+' captures under key/fill/rim lighting. The filter is connected in the private validation fixture.</p><img style="max-width:100%" src="settled-review.jpg"><p>Unchanged-frame MAE (RGB8): off '+format(quality['unfiltered'],'.3f')+', on '+format(quality['filtered'],'.3f')+'. These are separate temporal pairs, not frame-locked native comparisons.</p><p>Zero non-fur pixels changed in the saved same-frame GPU check. Fur surface vectors and depths validated.</p><img style="max-width:100%" src="buffers.jpg"><p>Full dry fur parity remains incomplete. The plugin still needs its production integration and Ratchet edge/motion validation.</p></body>')
print(json.dumps(report,indent=2))
