"""Compare decoded sheep lighting inputs; measurements exclude non-fur parts."""
from pathlib import Path
import json
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent/'recovered'
ue=root/'environment-sheep-inputs'
def read(p):return np.asarray(Image.open(p).convert('RGB'),dtype=float)
mask=(read(root/'environment-sheep/key-environment.png')-read(root/'environment-sheep/key-only.png')).mean(2)>5
for _ in range(4):
 mask &= np.roll(mask,1,0)&np.roll(mask,-1,0)&np.roll(mask,1,1)&np.roll(mask,-1,1)
 mask[[0,-1],:]=False;mask[:,[0,-1]]=False
rows=json.loads((ue/'report.json').read_text());assert len(rows)==5
result={};panel=Image.new('RGB',(1200,4*300),'#17191e');draw=ImageDraw.Draw(panel)
for i,probe in enumerate(('normal','albedo','response','diffuse')):
 folder=root/('sheep-probe-'+probe+'-20260907')
 meta=json.loads((folder/'report.json').read_text())
 assert meta['environment_comparison']['probe']==probe
 assert rows[i+1]['label']==probe and rows[i+1]['parameters']['LightingProbe']==i+1
 paths=[folder/'environment.png',ue/(probe+'.png')]
 a,b=map(read,paths);assert a.shape==b.shape==(942,2191,3)
 # Both validation paths output gamma 2.2. Invert for input-domain errors.
 linear_a=(a/255)**2.2;linear_b=(b/255)**2.2
 result[probe]={'mean_abs_rgb8':float(abs(a-b)[mask].mean()),
  'mean_abs_linear_channels':abs(linear_a-linear_b)[mask].mean(0).tolist(),
  'forge_mean_linear':linear_a[mask].mean(0).tolist(),'unreal_mean_linear':linear_b[mask].mean(0).tolist()}
 for j,(name,p) in enumerate(zip(('Forge','Unreal'),paths)):
  draw.text((j*600+12,i*300+8),name+' | '+probe,fill='white')
  panel.paste(Image.open(p).convert('RGB').resize((600,258)),(j*600,i*300+30))
a=read(ue/'combined.png');b=read(root/'environment-sheep/key-environment.png')
result['fresh_vs_cached_combined_rgb8']=float(abs(a-b)[mask].mean())
result['limits']='Decoded display values approximate linear shader outputs (8-bit gamma capture and different temporal/raster paths). Response RGB = gloss, specular code, occlusion; normal = decoded normal*.5+.5. Raw diffuse is the cube at mip5 times .6, without material response.'
(root/'sheep-lighting-input-comparison.json').write_text(json.dumps(result,indent=2));panel.save(root/'sheep-lighting-input-comparison.png')
print(json.dumps(result,indent=2))
