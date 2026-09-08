"""Compare matched camera/cube captures over an interior UE fur-response mask."""
from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parent;out=root/'recovered'
result={}
for fixture in ['ratchet','sheep']:
    forge=out/('forge-environment-'+fixture)
    report=json.loads((forge/'report.json').read_text())
    inputs=json.loads((root/('matched-reference' if fixture=='ratchet' else 'sheep-reference')/'inputs.json').read_text())
    assert report['environment_comparison']['background'].startswith('black')
    expected=inputs['camera']['forge'];actual=report['camera']
    assert abs(actual['distance']-expected['distance'])<1e-6
    assert np.max(abs(np.asarray(actual['target'])-expected['target']))<1e-6
    assert actual['yaw']==expected['yaw'] and actual['pitch']==expected['pitch']
    def read(path):return np.asarray(Image.open(path).convert('RGB'),dtype=float)
    a=read(forge/'environment.png');b=read(out/('environment-'+fixture)/'key-environment.png')
    baseline=read(out/('environment-'+fixture)/'key-only.png')
    assert a.shape==b.shape==(942,2191,3)
    mask=(b-baseline).mean(axis=2)>5
    for _ in range(4):
        mask=mask & np.roll(mask,1,0)&np.roll(mask,-1,0)&np.roll(mask,1,1)&np.roll(mask,-1,1)
        mask[[0,-1],:]=False;mask[:,[0,-1]]=False
    assert mask.sum()>1000
    result[fixture]={'interior_fur_pixels':int(mask.sum()),'mean_absolute_rgb8_difference':float(abs(a-b)[mask].mean()),
        'forge_mean_rgb8':a[mask].mean(axis=0).tolist(),'unreal_mean_rgb8':b[mask].mean(axis=0).tolist(),
        'camera_verified':True,'horizontal_fov':60,'dimensions':[2191,942]}
result['cube_sha256']=hashlib.sha256((out/'environment-inputs/StudioCube.dds').read_bytes()).hexdigest()
result['scope']='Both captures use the same synthetic studio cube, recovered BRDF, unit key and gamma2.2. Forge cube face pairs Y/Z swapped to match UE coordinates. The stock Forge report resource label is not authoritative for this process-local override; capture_forge_environment.py defines the supplied bytes.'
result['limits']='Different temporal/raster/material-import paths; non-fur materials differ; background is now matched black. Measurements use an eroded UE environment-response mask, not complete game-renderer parity or an objective perceptual score.'
(out/'forge-environment-comparison.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
