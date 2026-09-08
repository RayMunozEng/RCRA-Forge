"""Independent scalar/NumPy wind and projection reference for production RFOffset."""
from pathlib import Path
import json,math,re,hashlib
import numpy as np
root=Path(__file__).resolve().parents[2];out=root/'unreal/fur/recovered/fur-wind-accuracy-20260907'
source=root/'external/RCRA-Forge/ui/viewport.py';text=source.read_text(encoding='utf-8')
start=text.index('const vec4 RETAIL_WIND_RANDOM[64]');end=text.index('\n);',start)
table=np.array([[float(x.strip()) for x in v.split(',')] for v in re.findall(r'vec4\(([^)]+)\)',text[start:end])]);assert table.shape==(64,4)
def normalize(v):return v/np.linalg.norm(v)
def frac(v):return v-np.floor(v)
def offset(clock,basis):
 uv=np.array([.37,.61]);turb=.2;strength=.12;phase=.1326904;radius=1
 spatial=np.sin((turb*20+10)*uv).sum()+.5*np.sin((turb*100+50)*uv).sum()
 envelope=phase*.9+.05+spatial*.05;denominator=1.925-envelope*.875
 ramp=0 if denominator<=0 else np.clip((.6625-envelope*.4375)/denominator,0,1)
 smooth=ramp*ramp*(3-2*ramp)
 wave=((1-smooth)*envelope+smooth+1)*math.sin((envelope+frac(clock*.15915493667125702))*6.2831854820251465)-1
 cap=min(smooth*(envelope*.0125+.0375),radius*.1)
 noise_time=(clock+.125+spatial*.125)*(turb*10+5);f=frac(noise_time);f2=f*f;f3=f2*f
 weights=np.array([-f+2*f2-f3,1-2*f2+f3,f+f2-f3,-f2+f3])
 index=int(frac(noise_time*.016393441706895828)*61)
 random=weights@table[index:index+4,:3]
 swap=[0,2,1];n=normalize(-basis['forward'][swap]);t=normalize(basis['right'][swap]);w=basis['right'][swap]
 wind=(random*strength+np.array([wave,-1,wave])*strength+w*cap)/30
 b=normalize(np.cross(t,n));frame=t*np.dot(t,wind)+b*np.dot(b,wind)
 gate=np.clip((.5*.09-.0075)*50,0,1)
 shell=normalize(n+frame*gate*(.75*.75+.4*.75)/.09)
 return shell[swap]*(9*.5*.75)
r=json.loads((out/'report.json').read_text());assert len(r['captures'])==4
result={'source_table_sha256':hashlib.sha256(table.tobytes()).hexdigest(),'adapter_sha256':hashlib.sha256((root/'unreal/plugins/FurAuthoring/Shaders/RecoveredFurAdapter.ush').read_bytes()).hexdigest(),'cases':[],'tolerance_render_pixels':.01}
for row in r['captures']:
 w,h=row['width'],row['height'];assert row['format']=='G16R16'
 a=np.fromfile(row['file'],dtype='<f4').reshape(h,w,4)[h//2-32:h//2+32,w//2-32:w//2+32,:2].astype(float)
 assert np.isfinite(a).all() and (a[:,:,0]>0).all()
 v=(a-32767/65535)/(.499*.5);v=v*abs(v)*.5*np.array([w/2,-h/2])
 basis={k:np.array(value) for k,value in row['basis'].items()};current,previous=[offset(t,basis) for t in row['times']]
 axes=np.stack([basis['right'],basis['up'],basis['forward']]);delta=axes@(current-previous)
 depth=row['front_depth_cm']+np.dot(basis['forward'],current)
 xx,yy=np.meshgrid(np.arange(w//2-32,w//2+32)+.5,np.arange(h//2-32,h//2+32)+.5)
 ndc=np.stack([2*xx/w-1,1-2*yy/h],axis=2)
 tan_h=math.tan(math.radians(row['horizontal_fov'])/2);scale=np.array([tan_h,tan_h*h/w])
 current_xy=ndc*scale*depth
 previous_ndc=(current_xy-delta[:2])/(depth-delta[2])/scale
 predicted=(ndc-previous_ndc)*np.array([w/2,-h/2])
 error=np.linalg.norm(v-predicted,axis=2)
 result['cases'].append({'label':row['label'],'times':row['times'],'current_offset_cm':current.tolist(),'previous_offset_cm':previous.tolist(),
  'predicted_mean_pixels_xy':predicted.mean((0,1)).tolist(),'measured_mean_pixels_xy':v.mean((0,1)).tolist(),
  'max_vector_error_pixels':float(error.max()),'p95_vector_error_pixels':float(np.percentile(error,95)),
  'passed':bool(error.max()<.01),'raw_sha256':hashlib.sha256(Path(row['file']).read_bytes()).hexdigest()})
result['passed']=all(c['passed'] for c in result['cases'])
result['limits']='Production RFOffset with constant UV/frame/depth inputs on an owned planar fixture, controlled previous/current clocks. CPU double-precision equations are implemented separately using the recovered table. Prediction includes depth changes and perspective; raster jitter and GPU floating rounding remain small residuals. This does not cover varying sheep mesh inputs, skeletal deformation, fast motion, or native game parity.'
(out/'validation.json').write_text(json.dumps(result,indent=2))
rows=''.join('<tr><td>'+c['label']+'</td><td>'+str([round(x,5) for x in c['predicted_mean_pixels_xy']])+'</td><td>'+str([round(x,5) for x in c['measured_mean_pixels_xy']])+'</td><td>'+format(c['max_vector_error_pixels'],'.6f')+'</td></tr>' for c in result['cases'])
(out/'comparison.html').write_text('''<!doctype html><meta charset="utf-8"><title>Fur wind accuracy</title><style>body{font:16px system-ui;background:#17191e;color:#eee;margin:24px}td,th{text-align:left;padding:12px;border-bottom:1px solid #555}p{max-width:1000px}a{color:#8dd2ff}</style><h1>Fur wind motion-vector accuracy</h1><p>The production fur wind function runs at controlled current and previous times. An independent CPU implementation predicts deformation and perspective displacement.</p><table><tr><th>Case</th><th>Predicted X,Y pixels</th><th>Measured X,Y pixels</th><th>Maximum vector error</th></tr>'''+rows+'''</table><p>Acceptance tolerance: 0.01 render pixels. Uniform-input planar fixture only; this is not complete sheep mesh or native game parity.</p><a href="../velocity-calibration-20260907/comparison.html">Readback calibration</a>''',encoding='utf-8')
print(json.dumps(result,indent=2))
if not result['passed']:raise SystemExit('Wind accuracy gate failed; investigate before claiming accuracy')
