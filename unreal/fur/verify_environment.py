"""Check optional environment controls and independent shadow/environment response."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parent/'recovered'
result={}
for fixture in ['ratchet','sheep']:
    tag='environment-'+fixture
    rows=json.loads((root/tag/'report.json').read_text())
    assert len(rows)==8 and all(r['draw_realtime'] and r['resolved_aa_method']==2 for r in rows)
    job=json.loads((root/(tag+'-job.json')).read_text());assert job['status']=='exited' and job['root_exit_code']==0
    raw={r['label']:np.asarray(Image.open(r['image']).convert('RGB'),dtype=np.float32) for r in rows}
    linear={k:(v/255)**2.2 for k,v in raw.items()}
    delta=raw['key-environment']-raw['key-only']
    mask=delta.mean(axis=2)>5
    assert mask.sum()>1000
    disabled=float(abs(raw['disabled-return']-raw['key-only'])[mask].mean());assert disabled<3,disabled
    # Exclude saturated output; infer affected fur from the environment delta.
    scale_mask=mask&(raw['environment-double'].max(axis=2)<250)
    a=linear['environment-only'][scale_mask];b=linear['environment-double'][scale_mask]
    ratio=float(b.mean()/a.mean());assert 1.85<ratio<2.15,ratio
    d1=linear['key-environment']-linear['key-only']
    d2=linear['shadow-environment']-linear['shadow-key-only']
    independent=float(abs(d1-d2)[mask].mean());assert independent<.025,independent
    wet=float(abs(raw['wet-environment']-raw['environment-only'])[mask].mean());assert wet>1,wet
    result[fixture]=dict(affected_pixels=int(mask.sum()),disabled_error_rgb8=disabled,
        intensity_linear_ratio=ratio,shadow_independence_error_linear=independent,wet_change_rgb8=wet,peak_job_gib=job['job_memory']['peak_job_gib'])
result['limits']='Controlled synthetic cube and private recovered BRDF. Not native UE Skylight/Lumen integration or full game lighting parity. Image-linear measurements use the fixed viewport gamma 2.2.'
(root/'environment-validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
