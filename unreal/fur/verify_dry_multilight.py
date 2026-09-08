"""Check visible dry light contributions and material lifecycle stability."""
from pathlib import Path
import json
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent/'recovered'
results={}
for fixture in ('ratchet','sheep'):
 p=root/('dry-multilight-'+fixture)
 rows=json.loads((p/'report.json').read_text(encoding='utf-8'))
 labels=['key','key-fill','key-fill-rim']+(['held'] if any(x['label']=='held' for x in rows) else [])+['rebuilt','disconnected']
 assert [r['label'] for r in rows]==labels
 assert all(r['draw_realtime'] and r['resolved_aa_method']==2 and r['wetness']==0 and r['wind']==0 for r in rows)
 job=json.loads((root/(p.name+'-job.json')).read_text());assert job['status']=='exited' and job['root_exit_code']==0
 a={n:np.array(Image.open(p/(n+'.png')).convert('RGB'),dtype=float) for n in labels}
 mask=a['key-fill-rim'].max(2)>30;mask[:150]=False
 r={'affected_fill_pixels':int((abs(a['key-fill']-a['key']).max(2)[mask]>8).sum()),'affected_rim_pixels':int((abs(a['key-fill-rim']-a['key-fill']).max(2)[mask]>8).sum()),'rebuild_mae_rgb8':float(abs(a['rebuilt']-a['key-fill-rim'])[mask].mean()),'disconnect_mae_rgb8':float(abs(a['disconnected']-a['key'])[mask].mean()),'peak_job_gib':job['job_memory']['peak_job_gib'],'scope':'Rendered contribution and lifecycle stability; not native image parity.'}
 assert r['affected_fill_pixels']>1000 and r['affected_rim_pixels']>1000
 assert r['disconnect_mae_rgb8']<3
 if 'held' in labels:
  indexed={x['label']:x for x in rows}
  assert indexed['key-fill-rim']['parameters']==indexed['held']['parameters']==indexed['rebuilt']['parameters']
  assert indexed['key-fill-rim']['lights']==indexed['held']['lights']==indexed['rebuilt']['lights']
  r['unchanged_frame_mae_rgb8']=float(abs(a['held']-a['key-fill-rim'])[mask].mean())
  r['held_to_rebuilt_mae_rgb8']=float(abs(a['rebuilt']-a['held'])[mask].mean())
  r['rebuild_mean_bias_rgb8']=(a['rebuilt']-a['held'])[mask].mean(0).tolist()
  assert r['held_to_rebuilt_mae_rgb8']<=r['unchanged_frame_mae_rgb8']+1
  assert max(abs(v) for v in r['rebuild_mean_bias_rgb8'])<1
  r['static_temporal_quality_pass']=r['unchanged_frame_mae_rgb8']<3
  r['scope']='Light binding/rebuild stable relative to unchanged-frame sampling. Static temporal quality is a separate gate; not native parity.'
 else:
  assert r['rebuild_mae_rgb8']<3
 (p/'validation.json').write_text(json.dumps(r,indent=2),encoding='utf-8');results[fixture]=r
 o=Image.new('RGB',(1500,290),'#11151b');d=ImageDraw.Draw(o)
 for i,(name,label) in enumerate(zip(labels,['Key only','Key + cool fill','Key + fill + warm rim'])):
  im=Image.open(p/(name+'.png')).convert('RGB');im.thumbnail((500,245));o.paste(im,(i*500,40));d.text((i*500+12,12),label,fill='white')
 o.save(p/'review.jpg',quality=94)
(root/'dry-multilight-verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
