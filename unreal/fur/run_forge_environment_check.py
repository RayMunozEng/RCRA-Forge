"""Run the matched Forge capture under the same private-desktop resource guard."""
import json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
fur=root/'unreal/fur';sheep='--sheep' in sys.argv;tag='forge-environment-'+('sheep' if sheep else 'ratchet')
post=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--fur-post=')),'none')
assert post in ('none','contact','denoise','both')
if post!='none':tag+='-'+post
if '--shell-depth' in sys.argv:tag+='-shell-depth'
geometry=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--geometry=')),'authored')
assert geometry in ('authored','fixed-spacing','uniform-length')
if geometry!='authored':tag+='-'+geometry
if '--far-background' in sys.argv:tag+='-far-background'
if '--scene-sequence' in sys.argv:tag+=('-scene' if '--scene-background' in sys.argv else '-empty')+'-sequence'
lighting=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--lighting=')),'combined')
assert lighting in ('combined','direct','environment')
if lighting!='combined':tag+='-'+lighting
probe=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--probe=')),'none')
assert probe in ('none','normal','albedo','response','diffuse')
if probe!='none':tag+='-probe-'+probe
output_tag=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--output-tag=')),None)
if output_tag:
 import re
 assert re.fullmatch(r'[a-z0-9-]+',output_tag)
 tag=output_tag
report=fur/'recovered'/(tag+'-job.json')
marker=fur/'recovered'/tag/'report.json'
previous=marker.stat().st_mtime_ns if marker.exists() else 0
argv=[sys.executable,str(root/'external/RCRA-Forge/tools/private_desktop.py'),'--cwd',str(root),'--report',str(report),
 '--seconds','240','--min-physical-gib','8','--min-pagefile-gib','8','--min-disk-gib','2','--max-job-memory-gib','6','--priority','below-normal','--',
 sys.executable,str(fur/'capture_forge_environment.py')]
argv+=['--lighting='+lighting,'--output-tag='+tag]
argv.append('--probe='+probe)
if sheep:argv+=['--sheep']
if post!='none':argv+=['--fur-post='+post]
if '--reference-camera' in sys.argv:argv+=['--reference-camera']
if '--shell-depth' in sys.argv:argv+=['--shell-depth']
if geometry!='authored':argv+=['--geometry='+geometry]
if '--far-background' in sys.argv:argv+=['--far-background']
if '--scene-sequence' in sys.argv:argv+=['--scene-sequence']
if '--scene-background' in sys.argv:argv+=['--scene-background']
with (fur/'recovered'/(tag+'-launch.log')).open('w') as log:subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,check=True)
r=json.loads(report.read_text());print(json.dumps({k:r.get(k) for k in ['status','root_exit_code','job_memory']},indent=2))
assert r['status']=='exited' and r['root_exit_code']==0
assert marker.is_file() and marker.stat().st_mtime_ns>previous
