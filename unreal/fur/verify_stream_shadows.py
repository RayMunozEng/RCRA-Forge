"""Check real playback clocks and the controlled frozen/live shadow comparison."""
import json
from pathlib import Path
import numpy as np
from PIL import Image

root=Path(__file__).resolve().parent/'recovered'
def read(path):return np.asarray(Image.open(path).convert('RGB'),dtype=np.float32)
rows=json.loads((root/'continuous/report.json').read_text())
assert len(rows)==16
assert all(r['manual_wind_clock']==0 and r['resolved_aa_method']==2 and r['draw_realtime'] for r in rows)
assert rows[-1]['world_time']-rows[0]['world_time']>1
assert len({round(r['animation_position'],3) for r in rows})>4
images=[read(r['image']) for r in rows]
changes=[float(abs(b-a).mean()) for a,b in zip(images,images[1:])]
assert min(changes)>.1,changes
motion=max(float(np.linalg.norm(np.asarray(r['bones'])-np.asarray(rows[0]['bones']),axis=1).max()) for r in rows[1:])
assert motion>1
result={'continuous':dict(frames=len(rows),world_seconds=rows[-1]['world_time']-rows[0]['world_time'],
                         minimum_frame_change_rgb8=min(changes),maximum_bone_motion_cm=motion)}
rows=json.loads((root/'animated-shadows/report.json').read_text())
assert len(rows)==6
images={r['label']:read(r['image']) for r in rows}
assert rows[1]['captures']==rows[2]['captures']
assert rows[3]['captures']>rows[2]['captures']
assert rows[5]['captures']==rows[4]['captures']
bone_motion=float(np.linalg.norm(np.asarray(rows[1]['bones'])-np.asarray(rows[2]['bones']),axis=1).max())
assert bone_motion>1
mask=images['unshadowed'].max(axis=2)>30
shadowed=int(((images['unshadowed'].mean(axis=2)-images['pose-a'].mean(axis=2)>15)&mask).sum())
changed=int(((abs(images['pose-b-live']-images['pose-b-frozen']).mean(axis=2)>15)&mask).sum())
frozen_error=float(abs(images['pose-a']-images['pose-b-frozen'])[mask].mean())
disabled_error=float(abs(images['disabled']-images['unshadowed'])[mask].mean())
assert shadowed>100,shadowed
assert changed>100,changed
assert frozen_error<3,frozen_error
assert disabled_error<3,disabled_error
result['shadows']=dict(shadowed_pixels=shadowed,changed_deformation_pixels=changed,
    frozen_control_difference_rgb8=frozen_error,disabled_difference_rgb8=disabled_error,
    caster_bone_motion_cm=bone_motion,capture_counts=[r['captures'] for r in rows])
result['limits']='Continuous editor playback and one selected skeletal caster; native velocity, all-speed ghosting, WPO self-shadowing and full lighting parity are unverified.'
(root/'stream-shadow-validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
