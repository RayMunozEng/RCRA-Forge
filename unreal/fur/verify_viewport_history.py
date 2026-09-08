"""Reject frozen captures and quantify static coverage noise without filtering images."""
import json
import argparse
from pathlib import Path
import numpy as np
from PIL import Image

parser=argparse.ArgumentParser()
parser.add_argument('--sheep',action='store_true')
args=parser.parse_args()
root=Path(__file__).resolve().parent/('sheep-reference' if args.sheep else 'matched-reference')/'viewport-live'
rows=json.loads((root/'report.json').read_text())
assert len(rows)==24
assert all(r['draw_realtime'] for r in rows)
assert all(r['slate_throttling_disabled'] for r in rows)
assert all(r['resolved_aa_method']==(0 if r['stage']=='no-aa' else 2) for r in rows)
images={stage:np.stack([np.asarray(Image.open(r['image']).convert('RGB'),dtype=np.float32)
    for r in rows if r['stage']==stage]) for stage in ('no-aa','taa','moving','settled')}
shape=images['taa'].shape[1:]
assert all(im.shape[1:]==shape for im in images.values())
# Foreground from the same stationary pose; reject unchanged stale framebuffers.
mask=images['taa'].mean(axis=0).max(axis=2)>25
def variation(seq):
    return float(np.abs(np.diff(seq,axis=0))[:,mask].mean())
variations={stage:variation(seq) for stage,seq in images.items()}
assert variations['no-aa']>.05,variations
assert variations['moving']>variations['settled'],variations
assert variations['taa']<variations['no-aa'],variations
report={'frame_dimensions':list(shape[:2]),'mean_frame_change_rgb8':variations,
        'stationary_change_reduction_percent':100*(1-variations['taa']/variations['no-aa']),
        'limits':'Static coverage stability and camera response only; no skeletal deformation or quantitative ghost-trail test.'}
(root/'validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
