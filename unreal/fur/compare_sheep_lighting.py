"""Reproduce sheep lighting isolation with capture provenance checks."""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent;out=root/'recovered'
ue=out/'environment-sheep'
rows={r['label']:r for r in json.loads((ue/'report.json').read_text())}
def read(p): return np.asarray(Image.open(p).convert('RGB'),dtype=float)
mask=(read(ue/'key-environment.png')-read(ue/'key-only.png')).mean(axis=2)>5
for _ in range(4):
    mask &= np.roll(mask,1,0)&np.roll(mask,-1,0)&np.roll(mask,1,1)&np.roll(mask,-1,1)
    mask[[0,-1],:]=False;mask[:,[0,-1]]=False
assert mask.sum()>1000
cube=hashlib.sha256((out/'environment-inputs/StudioCube.dds').read_bytes()).hexdigest()
camera=json.loads((root/'sheep-reference/inputs.json').read_text())['camera']['forge']
result={};panel=Image.new('RGB',(1200,620),'#17191e');draw=ImageDraw.Draw(panel)
for i,(mode,tag,label) in enumerate([
 ('direct','sheep-lighting-direct-20260907','key-only'),
 ('environment','sheep-lighting-environment-v2-20260907','environment-only')]):
    folder=out/tag;report=json.loads((folder/'report.json').read_text())
    meta=report['environment_comparison'];actual=report['camera']
    assert meta['lighting_mode']==mode and meta['cube_sha256']==cube
    assert meta['horizontal_fov']==60 and meta['post_mode']=='none'
    for k in ('distance','target','yaw','pitch'): assert np.allclose(actual[k],camera[k],atol=1e-6,rtol=0),k
    assert rows[label]['resolved_aa_method']==2
    paths=[folder/'environment.png',ue/(label+'.png')]
    a,b=map(read,paths);assert a.shape==b.shape==(942,2191,3)
    result[mode]={'pixels':int(mask.sum()),'mean_abs_rgb8':float(abs(a-b)[mask].mean()),
      'forge_mean':a[mask].mean(0).tolist(),'ue_mean':b[mask].mean(0).tolist(),
      'images':[str(p) for p in paths],'sha256':[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]}
    for j,(name,p) in enumerate(zip(('Forge','Unreal'),paths)):
        draw.text((j*600+12,i*310+10),f'{name} | {mode} only',fill='white')
        panel.paste(Image.open(p).convert('RGB').resize((600,258)),(j*600,i*310+35))
result['limits']='Interior UE fur-response mask; different raster/temporal paths. Diagnostic isolation, not native parity. Initial environment capture without v2 is invalid (both lighting terms zeroed).'
result['cube_sha256']=cube
p=out/'sheep-lighting-isolation-20260907'
p.with_suffix('.json').write_text(json.dumps(result,indent=2));panel.save(p.with_suffix('.png'))
print(json.dumps({k:v['mean_abs_rgb8'] for k,v in result.items() if isinstance(v,dict)}))
