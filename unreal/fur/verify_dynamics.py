"""Validate live material/pose evidence and measure weather response."""
import json
from pathlib import Path
import numpy as np
from PIL import Image

root=Path(__file__).resolve().parent/'recovered'
results={}
for fixture in ('skeletal','ratchet','sheep'):
    folder=root/('dynamics-'+fixture)
    report=json.loads((folder/'report.json').read_text())
    rows=report['captures']
    assert len(rows)==(18 if fixture=='skeletal' else 4)
    assert all(r['draw_realtime'] and r['resolved_aa_method']==2 for r in rows)
    images={r['label']:np.asarray(Image.open(r['image']).convert('RGB'),dtype=np.float32) for r in rows}
    a,b,wet=(images[k] for k in ('wind-a','wind-b','wet-wind'))
    assert a.shape==b.shape==wet.shape
    mask=a.max(axis=2)>30
    change=float(abs(a-b)[mask].mean())
    wet_change=float(abs(b-wet)[mask].mean())
    darkening=float((b-wet)[mask].mean())
    assert change>.1,(fixture,change)
    assert wet_change>1,(fixture,wet_change)
    result=dict(wind_time_change_rgb8=change,wet_change_rgb8=wet_change,wet_mean_darkening_rgb8=darkening)
    if fixture=='skeletal':
        assert report['bone_motion_cm']>1
        assert max(r.get('bone_follow_error_cm',0) for r in rows)<.001
        motion=[float(abs(images['walk-'+str(i+1)]-images['walk-'+str(i)]).mean()) for i in range(11)]
        assert min(motion)>.1,motion
        result.update(bone_motion_cm=report['bone_motion_cm'],minimum_walk_frame_change_rgb8=min(motion))
        # Examine pixels vacated by the pose jump, away from its final silhouette.
        # This measures one captured jump only, not native motion-vector parity.
        vacated=(images['walk-11'].max(axis=2)>30)&(images['pose-settled'].max(axis=2)<5)
        interior=vacated.copy()
        for axis in (0,1):
            for offset in (-2,-1,1,2):interior &= np.roll(vacated,offset,axis=axis)
        count=int(interior.sum())
        assert count>100,count
        residual=images['pose-change'].max(axis=2)[interior]
        result['pose_jump_vacated_pixels']=count
        result['pose_jump_residual_mean_rgb8']=float(residual.mean())
        result['pose_jump_bright_residual_pixels']=int((residual>10).sum())
    else:
        baseline=Path(__file__).resolve().parent/('matched-reference' if fixture=='ratchet' else 'sheep-reference')/'viewport-live/taa-3.png'
        old=np.asarray(Image.open(baseline).convert('RGB'),dtype=np.float32)
        dry=images['dry'];assert old.shape==dry.shape
        reference_error=float(abs(old-dry)[old.max(axis=2)>30].mean())
        assert reference_error<3,(fixture,reference_error)
        result['zero_wind_reference_difference_rgb8']=reference_error
    results[fixture]=result
results['limits']='Image changes include residual TAA variation. The vacated-pixel residual covers one pose jump. Sampled walk and fixed wind times do not establish native velocity or general ghost-trail parity.'
(root/'dynamics-validation.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
