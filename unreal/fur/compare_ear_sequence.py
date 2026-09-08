"""Compare synchronized camera sequences and held-camera pixel variation."""
import json
import hashlib
import sys
from pathlib import Path
import numpy as np
from PIL import Image

root=Path(__file__).resolve().parent/'recovered'
out=root/'ear-contours'
rows=[]
paths={}
reference=None
edge_mask=None
ue='--ue' in sys.argv
for mode in ('empty','scene'):
    folder=root/('ue-ear-sequence' if ue else f'forge-environment-ratchet-both-{mode}-sequence')
    report=json.loads((folder/('report.json' if ue else 'sequence.json')).read_text())
    frames=([dict(r,file=r['image'],temporal_age=r['index']) for r in report['captures'] if r['mode']==mode]
            if ue else report['frames'])
    if ue:
        assert all(r['resolved_aa_method']==2 and r['draw_realtime'] for r in frames)
    else:assert report['background']==(mode=='scene')
    if mode=='scene' and not ue:
        probes=report['background_probes']
        assert len(probes)==3 and all(p['linear_depth']>0 for p in probes)
        assert any(max(abs(v) for v in p['velocity'])>.01 for p in probes)
    assert len(frames)==24 and all(r['phase']=='held' for r in frames[12:])
    schedule=[(r['yaw'],r['temporal_age'],r['phase']) for r in frames]
    if reference is None:reference=schedule
    assert schedule==reference, 'Camera or temporal phases differ'
    assert len({r['yaw'] for r in frames[12:]})==1
    crops=[]
    for row in frames[12:]:
        im=np.asarray(Image.open(row['file']).convert('RGB'))
        assert im.shape==(942,2191,3)
        crops.append(im[460:745,1250:1750].astype(np.float32))
    stack=np.stack(crops)
    if edge_mask is None:
        occupancy=stack[-1].max(axis=2)>5
        edge_mask=np.zeros(occupancy.shape,dtype=bool)
        for x in range(occupancy.shape[1]):
            ys=np.flatnonzero(occupancy[:,x])
            if len(ys) and ys[-1]<occupancy.shape[0]-5:
                y=int(ys[-1]);edge_mask[max(0,y-8):y+5,x]=True
        assert edge_mask.sum()>100
    rows.append({'mode':mode,'held_frames':12,'ear_roi_xyxy':[1250,460,1750,745],
                 'mean_temporal_std_rgb8':float(stack.std(axis=0).mean()),
                 'mean_consecutive_change_rgb8':float(np.abs(np.diff(stack,axis=0)).mean()),
                 'lower_rim_temporal_std_rgb8':float(stack.std(axis=0)[edge_mask].mean()),
                 'lower_rim_mask_pixels':int(edge_mask.sum()),
                 'last_frame_sha256':hashlib.sha256(Path(frames[-1]['file']).read_bytes()).hexdigest()})
    paths[mode]=['../'+folder.name+'/'+(mode if ue else 'sequence')+'/'+Path(r['file']).name for r in frames]

stem='ue-sequence-comparison' if ue else 'sequence-comparison'
(out/(stem+'.json')).write_text(json.dumps({'rows':rows,'schedule':reference,
    'limits':'Held-camera temporal variation in a fixed rectangle; not a native-parity score or registered moving-edge metric.'},indent=2))
page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Ear edge in motion</title>
<style>body{background:#181a20;color:#eee;font:16px system-ui;margin:24px}h1{font-size:24px}.panels{display:flex;gap:24px;flex-wrap:wrap}.crop{width:500px;height:285px;overflow:hidden;position:relative;background:black}.crop img{position:absolute;max-width:none;width:2191px;height:942px;left:-1250px;top:-460px}button,input{margin:12px}p{max-width:1000px;line-height:1.5}</style>
<h1>Ear edge: empty background versus world-space plane</h1>
<p>Both use authored fur, contact shadows and denoising. Frames 1–12 move the camera; frames 13–24 hold it still. The black plane writes opaque depth and camera velocity. These are real frame captures, shown at 1:1 pixels.</p>
<button id="play">Play</button><input id="frame" aria-label="Frame" type="range" min="0" max="23" value="0"><span id="label"></span>
<div class="panels"><article><h2>Empty background</h2><div class="crop"><img id="empty" alt="Empty background ear"></div></article><article><h2>World-space plane</h2><div class="crop"><img id="scene" alt="Plane background ear"></div></article></div>
<p>Held-camera measurements describe pixel variation, not contour removal or native parity.</p><pre id="metrics"></pre>
<script>const paths='''+json.dumps(paths)+''',metrics='''+json.dumps(rows)+''';const slider=document.getElementById('frame');let timer=null;
function render(){let i=+slider.value;for(const mode of ['empty','scene'])document.getElementById(mode).src=paths[mode][i];document.getElementById('label').textContent=`Frame ${i+1}: ${i<12?'moving':'held'}`;}
function stop(){clearInterval(timer);timer=null;document.getElementById('play').textContent='Play';}
slider.oninput=render;document.getElementById('play').onclick=()=>{if(timer){stop();return;}document.getElementById('play').textContent='Pause';timer=setInterval(()=>{slider.value=(+slider.value+1)%24;render();},100);};document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});document.getElementById('metrics').textContent=JSON.stringify(metrics,null,2);render();</script></html>'''
if ue:
    page=page.replace('Ear edge: empty','Unreal ear edge: empty').replace('Both use authored fur, contact shadows and denoising.', 'Both use authored fur and UE TAA2 with the same lighting. Forge contact/denoise is not present.').replace('The black plane writes opaque depth and camera velocity.', 'The backdrop is a thin opaque cube at the mapped Forge plane position. UE cadence and temporal phases differ from Forge; compare within this engine.')
(out/(stem+'.html')).write_text(page,encoding='utf-8')
print(json.dumps(rows,indent=2))
