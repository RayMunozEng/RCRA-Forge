"""Verify rendered and binding behavior of the environment controller."""
from pathlib import Path
import json
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parent/'recovered'
rows=json.loads((root/'environment-controls/report.json').read_text())
assert len(rows)==8 and all(r['draw_realtime'] and r['resolved_aa_method']==2 for r in rows)
raw={r['label']:np.asarray(Image.open(r['image']).convert('RGB'),dtype=float) for r in rows}
mask=(raw['enabled']-raw['disabled']).mean(axis=2)>5
assert mask.sum()>1000
rebuilt=float(abs(raw['double']-raw['rebuilt'])[mask].mean());assert rebuilt<3,rebuilt
missing=float(abs(raw['disabled']-raw['missing-brdf'])[mask].mean());assert missing<3,missing
assert 'until valid' in rows[5]['status']
assert 'material environment settings' in rows[7]['status']
assert abs(rows[7]['wetness']-.8)<1e-5
expected=[0,.6,1.2,1.2,0,0,.9,.6]
assert all(abs(r['intensity']-v)<1e-5 for r,v in zip(rows,expected))
job=json.loads((root/'environment-controls-job.json').read_text());assert job['root_exit_code']==0 and job['status']=='exited'
result=dict(rebuild_error_rgb8=rebuilt,missing_input_error_rgb8=missing,affected_pixels=int(mask.sum()),intensities=[r['intensity'] for r in rows],peak_job_gib=job['job_memory']['peak_job_gib'])
(root/'environment-controls-validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
