"""Validate the BC sRGB upload correction against saved UE lighting captures."""
from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent;out=root/'recovered'
def read(p):return np.asarray(Image.open(p).convert('RGB'),float)
def mask_for(fixture):
 ue=out/('environment-'+fixture)
 mask=(read(ue/'key-environment.png')-read(ue/'key-only.png')).mean(2)>5
 for _ in range(4):
  mask &= np.roll(mask,1,0)&np.roll(mask,-1,0)&np.roll(mask,1,1)&np.roll(mask,-1,1)
  mask[[0,-1],:]=False;mask[:,[0,-1]]=False
 return mask
cases=[('sheep environment','sheep','sheep-lighting-environment-v2-20260907','sheep-environment-srgb-fixed-20260907','environment-only'),
 ('sheep combined','sheep','forge-environment-sheep','sheep-combined-srgb-fixed-20260907','key-environment'),
 ('ratchet combined','ratchet','forge-environment-ratchet','ratchet-combined-srgb-fixed-20260907','key-environment')]
result={};panel=Image.new('RGB',(1500,3*250),'#17191e');draw=ImageDraw.Draw(panel)
for i,(label,fixture,before,after,reference) in enumerate(cases):
 paths=[out/before/'environment.png',out/after/'environment.png',out/('environment-'+fixture)/(reference+'.png')]
 reports=[json.loads((out/tag/'report.json').read_text()) for tag in (before,after)]
 assert reports[0]['camera']==reports[1]['camera']
 assert reports[0]['environment_comparison']['cube_sha256']==reports[1]['environment_comparison']['cube_sha256']
 assert reports[1]['environment_comparison']['probe']=='none'
 if fixture=='sheep':assert reports[1]['meshes'][0]['gpu_texture_formats']['specular_color']==0x8C4D
 else:assert reports[0]['meshes'][0]['gpu_texture_formats']==reports[1]['meshes'][0]['gpu_texture_formats']
 a,b,c=map(read,paths);assert a.shape==b.shape==c.shape==(942,2191,3)
 mask=mask_for(fixture);old=float(abs(a-c)[mask].mean());new=float(abs(b-c)[mask].mean())
 result[label]={'pixels':int(mask.sum()),'before_mae_rgb8':old,'after_mae_rgb8':new,
  'reduction_percent':100*(1-new/old),'before_after_mae_rgb8':float(abs(a-b)[mask].mean()),
  'image_sha256':[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths],
  'after_gpu_formats':[r.get('gpu_texture_formats') for r in reports[1]['meshes']]}
 for j,(title,p) in enumerate(zip(('Forge before','Forge corrected','Unreal'),paths)):
  draw.text((j*500+10,i*250+8),label+' | '+title,fill='white')
  panel.paste(Image.open(p).convert('RGB').resize((500,215)),(j*500,i*250+30))
result['cause']='Forge mapped BC1/2/3 sRGB formats to linear unless the role was base color. Explicit BC7 sRGB was already preserved. Sheep response texture is BC1_UNORM_SRGB (72), and its GPU binding was linear DXT1 (33777); corrected binding is sRGB DXT1 (35917). Unreal already preserved source color space.'
result['limits']='Same authored cube and camera, interior UE response masks. Different temporal/raster paths remain. This validates cross-renderer texture format consistency, not complete retail fur/lighting parity.'
(out/'sheep-srgb-fix-validation.json').write_text(json.dumps(result,indent=2));panel.save(out/'sheep-srgb-fix-comparison.png')
print(json.dumps(result,indent=2))
