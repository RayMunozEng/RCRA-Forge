"""Known-displacement calibration of raw Unreal velocity decoding."""
from pathlib import Path
import json,math,hashlib
import numpy as np
root=Path(__file__).resolve().parent/'recovered/velocity-calibration-20260907'
r=json.loads((root/'report.json').read_text());assert len(r['captures'])==6
result={'cases':[],'tolerance_pixels':.01,'limits':r['limits']}
for row in r['captures']:
 w,h=row['width'],row['height'];assert row['format']=='G16R16'
 a=np.fromfile(row['file'],dtype='<f4').reshape(h,w,4).astype(float)
 # The central 64x64 is safely inside the flat front face in every case.
 a=a[h//2-32:h//2+32,w//2-32:w//2+32,:2]
 assert (a[:,:,0]>0).all() and np.isfinite(a).all()
 v=(a-32767/65535)/(.499*.5);v=v*abs(v)*.5*np.array([w/2,-h/2])
 focal=w/(2*math.tan(math.radians(row['horizontal_fov'])/2))
 dx,dy=row['delta_camera_right_up_cm'];expected=np.array([dx,-dy])*focal/row['front_depth_cm']
 error=np.linalg.norm(v-expected,axis=2)
 result['cases'].append({'label':row['label'],'expected_pixels_xy':expected.tolist(),'measured_mean_pixels_xy':v.mean((0,1)).tolist(),
  'max_vector_error_pixels':float(error.max()),'p95_vector_error_pixels':float(np.percentile(error,95)),
  'passed':bool(error.max()<.01),'raw_sha256':hashlib.sha256(Path(row['file']).read_bytes()).hexdigest()})
result['passed']=all(c['passed'] for c in result['cases'])
(root/'validation.json').write_text(json.dumps(result,indent=2))
rows=''.join('<tr><td>'+c['label']+'</td><td>'+str([round(x,5) for x in c['expected_pixels_xy']])+'</td><td>'+str([round(x,5) for x in c['measured_mean_pixels_xy']])+'</td><td>'+format(c['max_vector_error_pixels'],'.6f')+'</td></tr>' for c in result['cases'])
(root/'comparison.html').write_text('''<!doctype html><meta charset="utf-8"><title>Velocity calibration</title><style>body{font:16px system-ui;background:#17191e;color:#eee;margin:24px}td,th{text-align:left;padding:12px;border-bottom:1px solid #555}p{max-width:1000px}a{color:#8dd2ff}</style><h1>Known-displacement velocity calibration</h1><p>An owned flat surface supplies exact current and previous WPO positions. Expected screen displacement is calculated independently from camera projection, surface depth, and centimeter offsets.</p><table><tr><th>Case</th><th>Expected X,Y pixels</th><th>Measured X,Y pixels</th><th>Maximum vector error</th></tr>'''+rows+'''</table><p>Tolerance: 0.01 render pixels. Measurements use the central 64 x 64 face pixels. This validates readback, decoding, axes, and scaling; the fur wind equation needs its own independent reference.</p><a href="../sheep-velocity-float-20260907/comparison.html">Sheep motion-vector measurements</a>''',encoding='utf-8')
print(json.dumps(result,indent=2))
if not result['passed']:raise SystemExit('Known-displacement calibration failed; inspect before making accuracy claims')
