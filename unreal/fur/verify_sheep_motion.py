"""Verify a private sheep velocity/wet/wind sequence and create paused playback."""
from pathlib import Path
from collections import defaultdict
import json,hashlib
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent/'recovered';out=root/'sheep-motion-20260907'
report=json.loads((out/'report.json').read_text());rows=report['captures'];groups=defaultdict(list)
assert len(rows)==37
camera=rows[0]['camera']
for r in rows:
 assert r['camera']==camera and r['manual_clock']==0 and r['draw_realtime']
 assert r['velocity_view']==r['stage'].startswith('velocity')
 if not r['velocity_view']:assert r['resolved_aa_method']==2
 groups[r['stage']].append(r)
assert all(b['world_time']>a['world_time'] for a,b in zip(rows,rows[1:]))
assert [round(r['wetness'],3) for r in groups['wet-transition']]==[round(i*.1,3) for i in range(9)]
def read(p):return np.asarray(Image.open(p).convert('RGB'),float)
mask=(read(root/'environment-sheep/key-environment.png')-read(root/'environment-sheep/key-only.png')).mean(2)>5
for _ in range(4):
 mask &= np.roll(mask,1,0)&np.roll(mask,-1,0)&np.roll(mask,1,1)&np.roll(mask,-1,1)
 mask[[0,-1],:]=False;mask[:,[0,-1]]=False
result={'frames':len(rows),'fixed_camera':True,'live_clock':True,'pixels':int(mask.sum()),'stages':{}}
arrays={}
for label,rr in groups.items():
 a=np.stack([read(r['image']) for r in rr]);arrays[label]=a
 result['stages'][label]={'frames':len(rr),'mean_rgb8':a[:,mask].mean((0,1)).tolist(),
  'temporal_stddev_rgb8':float(a[:,mask].std(0).mean()),'world_time_range':[rr[0]['world_time'],rr[-1]['world_time']]}
base=arrays['velocity-still'].mean(0)
wind=float(abs(arrays['velocity-wind']-base)[:,mask].mean());settled=float(abs(arrays['velocity-still-final']-base)[:,mask].mean())
result.update(wind_velocity_visualization_change_rgb8=wind,returned_still_change_rgb8=settled,
 velocity_mean_exceeds_one_rgb8=wind>settled+1,
 dry_to_wet_mean_darkening_rgb8=float(arrays['dry-wind'][:,mask].mean()-arrays['wet-wind'][:,mask].mean()),
 limits=report['limits']+' RGB differences measure visualization activity, not vector magnitude or accuracy. Wet/dry frames have different wind times.')
changed=[int(np.count_nonzero(np.max(abs(frame-base),axis=2)[mask])) for frame in arrays['velocity-wind']]
result['velocity_changed_fur_pixels_per_frame']=changed
result['velocity_maximum_delta_rgb8']=float(abs(arrays['velocity-wind']-base)[:,mask].max())
result['velocity_conclusion']='Quantized velocity activity during wind, with exact return to stationary baseline; vector magnitudes and deformation accuracy unverified.' if all(changed) and settled==0 else 'Inconclusive velocity control.'
result['limits']+=' Wind velocity signal is only one RGB8 step; do not infer accurate magnitudes from this visualization.'
(out/'validation.json').write_text(json.dumps(result,indent=2))
selected=['velocity-still','velocity-wind','dry-wind','wet-wind']
canvas=Image.new('RGB',(1200,600),'#17191e');draw=ImageDraw.Draw(canvas)
for i,label in enumerate(selected):
 x=i%2*600;y=i//2*300
 draw.text((x+12,y+10),label,fill='white');canvas.paste(Image.open(groups[label][-1]['image']).convert('RGB').resize((600,258)),(x,y+34))
# Show a clearly labelled difference plot; do not present this as a render.
difference=np.max(abs(arrays['velocity-wind'][-1]-base),axis=2)
heat=np.zeros((*difference.shape,3),dtype=np.uint8)
heat[:,:,0]=np.clip(difference*255,0,255).astype(np.uint8)
heat[:,:,1]=np.clip(difference*160,0,255).astype(np.uint8)
canvas.paste(Image.fromarray(heat).resize((600,258)),(600,34))
draw.rectangle((600,0,1200,33),fill='#17191e')
draw.text((612,10),'Wind velocity difference x255 (diagnostic)',fill='white')
canvas.save(out/'overview.png')
frames=[{'image':Path(r['image']).name,'label':r['stage']+' '+str(r['index']),'wetness':round(r['wetness'],2),'time':r['world_time']} for r in rows]
html='''<!doctype html><meta charset="utf-8"><title>Sheep wind and wetness</title><style>body{background:#15171c;color:#eee;font:16px system-ui;margin:24px}img{max-width:100%;display:block}button,input{margin:8px}p{max-width:1000px}</style><h1>Sheep wind and wetness</h1><p>Actual Unreal captures. First and final stages show the engine velocity visualization; the middle shows dry and wet wind. Fixed camera, live wind clock. Playback is paused by default.</p><button id="play">Play</button><input id="slider" type="range" min="0" max="36" value="0"><span id="label"></span><img id="image"><p>Velocity colors are a visualization, not measured motion-vector magnitudes. This does not establish native game parity.</p><script>const frames=FRAMES;let index=0,timer=null;const slider=document.querySelector('#slider'),label=document.querySelector('#label'),picture=document.querySelector('#image'),play=document.querySelector('#play');function show(){slider.value=index;let f=frames[index];label.textContent=f.label+' | wetness '+f.wetness;picture.src=f.image}function stop(){clearInterval(timer);timer=null;play.textContent='Play'}play.onclick=()=>{if(timer)stop();else{timer=setInterval(()=>{index=(index+1)%frames.length;show()},200);play.textContent='Pause'}};slider.oninput=()=>{stop();index=+slider.value;show()};document.addEventListener('visibilitychange',()=>{if(document.hidden)stop()});show();</script>'''.replace('FRAMES',json.dumps(frames))
if (root/'sheep-velocity-float-20260907/validation.json').exists():
 html=html.replace('<h1>Sheep wind and wetness</h1>','<h1>Sheep wind and wetness</h1><p><a style="color:#8dd2ff" href="../sheep-velocity-float-20260907/comparison.html">New: raw motion-vector measurements</a></p>')
(out/'comparison.html').write_text(html,encoding='utf-8')
print(json.dumps(result,indent=2))
