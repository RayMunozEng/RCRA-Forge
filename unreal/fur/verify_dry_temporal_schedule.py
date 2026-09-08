"""Isolate periodic coverage bias; does not replace a GPU visual test."""
from pathlib import Path
import json
import numpy as np
frames=np.arange(160,dtype=np.uint32)
halton=np.array([int(f'{int(i%32)+1:032b}'[::-1],2)*2**-32 for i in frames],np.float32)
seeds=np.arange(1024,dtype=np.float32)/1024
coverage=np.arange(1,100,dtype=np.float32)/100
results={}
for period in (32,160):
 cycle=(frames%period).astype(np.float32)
 phase=np.mod((cycle[:,None]+np.mod(seeds[None,:]+halton[:,None],1))*np.float32(.2),1)
 rate=(phase[:,:,None]<=coverage).mean(axis=0)
 error=rate-coverage
 results[str(period)]={'coverage_mae':float(abs(error).mean()),'coverage_max_error':float(abs(error).max()),'mean_bias':float(error.mean())}
assert results['160']['coverage_mae']<.003
assert results['160']['coverage_max_error']<.01
report={'results':results,'scope':'Isolates temporal periods using ideal fractional spatial seeds. Excludes amplified sine/hash precision, temporal reconstruction and GPU filtering. Not native pixel parity.'}
(Path(__file__).parent/'recovered/dry-temporal-schedule.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
