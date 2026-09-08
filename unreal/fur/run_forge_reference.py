"""One bounded Forge comparison job, on an inactive desktop."""
import json
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[2]
sheep='--sheep' in sys.argv
out=root/'unreal/fur'/('sheep-reference' if sheep else 'matched-reference')
mode=sys.argv[1]
assert mode in ('unlit','lit')
report=out/('forge-'+mode+'-job.json')
argv=[sys.executable,str(root/'external/RCRA-Forge/tools/private_desktop.py'),
      '--cwd',str(root),'--report',str(report),'--seconds','200',
      '--min-physical-gib','8','--min-pagefile-gib','8','--min-disk-gib','2',
      '--max-job-memory-gib','3','--priority','below-normal','--',
      sys.executable,str(root/'unreal/fur/capture_forge_reference.py'),mode]
if sheep: argv+=['--sheep']
with (out/('forge-'+mode+'-launch.log')).open('w') as log:
    subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,check=True)
result=json.loads(report.read_text())
print(json.dumps({k:result.get(k) for k in ('status','root_exit_code','job_memory')},indent=2))
assert result['root_exit_code']==0
