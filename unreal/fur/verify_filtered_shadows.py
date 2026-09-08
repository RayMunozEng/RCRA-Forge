"""Verify continuous PCF algebra and live shadow controls from bounded UE runs."""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parent
out=root/'recovered'
rng=np.random.default_rng(804)
error=0.
for _ in range(10000):
    a=rng.integers(0,2,(4,4));fx,fy=rng.random(2)
    merged=np.sum(a*np.outer([1-fy,1,1,fy],[1-fx,1,1,fx]))/9
    reference=sum(a[y,x]*(1-fx)*(1-fy)+a[y,x+1]*fx*(1-fy)+a[y+1,x]*(1-fx)*fy+a[y+1,x+1]*fx*fy for y in range(3) for x in range(3))/9
    error=max(error,abs(merged-reference))
assert error<1e-12
result={'pcf_max_error':error}
for tag in ['filtered-shadows','self-shadows']:
    rows=json.loads((out/tag/'report.json').read_text())
    assert len(rows)==6 and all(r['draw_realtime'] and r['resolved_aa_method']==2 for r in rows)
    assert all('M_FilteredShadow_ratchet_v1' in r['material'] for r in rows)
    job=json.loads((out/(tag+'-job.json')).read_text())
    assert job['root_exit_code']==0 and job['status']=='exited'
    images={r['label']:np.asarray(Image.open(r['image']).convert('RGB'),dtype=np.float32) for r in rows}
    base=images['unshadowed'];mask=base.max(axis=2)>30
    def diff(a,b):return float(abs(images[a]-images[b])[mask].mean())
    if tag=='filtered-shadows':
        assert rows[1]['captures']==rows[2]['captures'] and rows[3]['captures']>rows[2]['captures']
        assert rows[5]['captures']==rows[4]['captures']
        frozen=diff('pose-a','pose-b-frozen');disabled=diff('disabled','unshadowed')
        changed=int(((abs(images['pose-b-live']-images['pose-b-frozen']).mean(axis=2)>15)&mask).sum())
        assert frozen<3 and disabled<3 and changed>100
        result[tag]={'frozen_error_rgb8':frozen,'disabled_error_rgb8':disabled,'deformation_changed_pixels':changed}
    else:
        assert rows[2]['captures']==rows[3]['captures'] and rows[4]['captures']>rows[3]['captures']
        shadowed=int(((base.mean(axis=2)-images['self-default'].mean(axis=2)>15)&mask).sum())
        changed=int(((abs(images['wind-refreshed']-images['wind-frozen']).mean(axis=2)>15)&mask).sum())
        assert shadowed>100 and changed>100
        result[tag]={'self_shadowed_pixels':shadowed,'wpo_refresh_changed_pixels':changed,'bias_difference_rgb8':diff('self-default','self-low-bias')}
    result[tag]['capture_counts']=[r['captures'] for r in rows]
    result[tag]['peak_job_gib']=job['job_memory']['peak_job_gib']
result['shader_sha256']=hashlib.sha256((root.parent/'plugins/FurAuthoring/Shaders/FurSceneShadow.ush').read_bytes()).hexdigest()
result['limits']='Opaque selected-caster depth comparisons; not volumetric strand transmittance, environment lighting, or native shadow parity. PCF continuity is algebraically verified; no claimed total image-quality percentage.'
(out/'filtered-shadow-validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
