"""Decode UE5.8 SM5 velocity texture readbacks into screen-pixel displacements."""
from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent/'recovered';out=root/'sheep-velocity-float-20260907'
source=Path('F:/Epic Games/UE_5.8/Engine/Shaders/Private/Common.ush')
s=source.read_text();assert '#define VELOCITY_ENCODE_GAMMA 1' in s
assert 'V.xy = (V.xy * abs(V.xy)) * 0.5;' in s
# Independently round-trip known screen-space vectors through native UNORM16.
known=np.array([-2,-1,-.1,-.01,0,.01,.1,1,2],dtype=float)
encoded=np.rint((np.sign(known)*np.sqrt(abs(known))*np.sqrt(2)*(.499*.5)+32767/65535)*65535)/65535
linear=(encoded-32767/65535)/(.499*.5)
decoded=linear*abs(linear)*.5
assert abs(decoded-known).max()<.00013
r=json.loads((out/'report.json').read_text());rows=r['captures'];assert [x['label'] for x in rows]==['still','wind-a','wind-b','returned-still']
read=lambda p:np.asarray(Image.open(p).convert('RGB'),float)
mask=(read(root/'environment-sheep/key-environment.png')-read(root/'environment-sheep/key-only.png')).mean(2)>5
for _ in range(4):
 mask &= np.roll(mask,1,0)&np.roll(mask,-1,0)&np.roll(mask,1,1)&np.roll(mask,-1,1)
 mask[[0,-1],:]=False;mask[:,[0,-1]]=False
width,height=rows[0]['width'],rows[0]['height']
assert all((row['width'],row['height'])==(width,height) for row in rows)
assert abs((width/height)/(mask.shape[1]/mask.shape[0])-1)<.001
mask=np.array(Image.fromarray(mask).resize((width,height),Image.Resampling.NEAREST),copy=True)
# Mask is normalized to the internal render view, not a claimed pixel match.
mask &= np.roll(mask,1,0)&np.roll(mask,-1,0)&np.roll(mask,1,1)&np.roll(mask,-1,1)
result={'source_shader_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'encoding':'SM5 gamma velocity; Common.ush DecodeVelocityFromTexture; current NDC minus previous NDC; render pixel axes right/down','roundtrip_max_ndc_error':float(abs(decoded-known).max()),'captures':[]};magnitudes=[]
for row in rows:
 assert row['width']==width and row['height']==height
 assert row['format'] in ('G16R16','A16B16G16R16','PF_G16R16','PF_A16B16G16R16'),row['format']
 path=Path(row['file']);a=np.fromfile(path,dtype='<f4').reshape(row['height'],row['width'],4).astype(float)
 assert np.isfinite(a[:,:,:2]).all() and a[:,:,:2].min()>=0 and a[:,:,:2].max()<=1
 valid=a[:,:,0]>0
 velocity=(a[:,:,:2]-32767/65535)/(.499*.5);velocity=velocity*abs(velocity)*.5
 velocity*=np.array([row['width']/2,-row['height']/2]);velocity[~valid]=0
 mag=np.linalg.norm(velocity,axis=2);magnitudes.append(mag)
 result['captures'].append({'label':row['label'],'format':row['format'],'world_time':row['world_time'],'wind':row['wind'],
  'valid_fur_pixels':int((valid&mask).sum()),'mask_pixels':int(mask.sum()),'mean_pixels_per_frame':float(mag[mask].mean()),
  'p95_pixels_per_frame':float(np.percentile(mag[mask],95)),'max_pixels_per_frame':float(mag[mask].max()),
  'moving_fur_pixels_above_0_001':int((mag[mask]>.001).sum()),'unique_encoded_r_values_on_fur':len(np.unique(a[:,:,0][mask])),
  'raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 np.savez_compressed(out/(row['label']+'-decoded.npz'),velocity_pixels=velocity.astype(np.float32),valid=valid)
result['render_dimensions']=[width,height]
result['mask_registration']='Existing fixed-camera interior fur mask resized nearest to internal render dimensions; aspect checked, further eroded. Different stochastic raster frames remain.'
result['limits']='Actual pre-postprocess velocity values, converted from native UNORM16 to float32 by D3D11 readback. No invented precision. Live wind times differ; no independently predicted per-vertex ground truth or native game parity. Cleared texels are invalid, displayed with zero displacement.'
(out/'validation.json').write_text(json.dumps(result,indent=2))
scale=max(.001,float(np.percentile(np.maximum(magnitudes[1],magnitudes[2])[mask],99)))
canvas=Image.new('RGB',(1200,600),'#17191e');draw=ImageDraw.Draw(canvas)
for i,(row,mag) in enumerate(zip(rows,magnitudes)):
 x=i%2*600;y=i//2*300;v=np.clip(mag/scale,0,1)
 heat=np.stack([v*255,v**2*230,v**4*180],axis=2).astype(np.uint8);heat[~mask]=0
 draw.text((x+12,y+10),row['label']+f' | white >= {scale:.4f} render pixels/frame',fill='white')
 canvas.paste(Image.fromarray(heat).resize((600,258)),(x,y+34))
canvas.save(out/'velocity-magnitude.png');print(json.dumps(result,indent=2))

