"""Inspect saved strand shader identities against the installed executable; no game execution."""
from pathlib import Path
import importlib.util,json,hashlib,subprocess,re
root=Path(__file__).resolve().parents[2]
tools=root/'artifacts/rcra-fur-continuation/capture-tools'
spec=importlib.util.spec_from_file_location('embedded',tools/'inventory_embedded_temporal_dxil.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
source=tools/'checkpoint5-compute-inventory/report.json';report=json.loads(source.read_text())
targets={s['sha256']:s for s in report['shaders'].values() if 'ModelStrand' in s.get('entry','')}
out=root/'unreal/fur/recovered/ear-strand-audit';out.mkdir(exist_ok=True)
data=m.DEFAULT_EXE.read_bytes();rows=[]
for c in m.dxbc_containers(data):
 if c['sha256'] not in targets and b'ModelStrand' not in c['blob']:continue
 target=targets.get(c['sha256'],{});name=target.get('entry','embedded_'+str(c['offset']));binary=out/(name+'.dxbc');binary.write_bytes(c['blob'])
 result=subprocess.run([str(m.DEFAULT_DXC),'-dumpbin',str(binary)],capture_output=True,text=True,timeout=30)
 assert result.returncode==0,result.stderr
 (out/(name+'.llvm.txt')).write_text(result.stdout,encoding='utf-8')
 rows.append(dict(entry=name,sha256=c['sha256'],offset=c['offset'],size=c['size'],first_event=target.get('first_event'),recovered_entries=re.findall(r'^define\s+void\s+@([^\s(]+)',result.stdout,re.MULTILINE),resources=result.stdout.split('; Resource Bindings:',1)[-1].split('target datalayout',1)[0][:16000]))
final=dict(source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),executable_sha256=hashlib.sha256(data).hexdigest(),matched=sum(r['sha256'] in targets for r in rows),expected=len(targets),shaders=rows,scope='Exact saved shader identities only. ModelStrand ownership and ear contribution are unproven.')
(out/'report.json').write_text(json.dumps(final,indent=2))
print(json.dumps(dict(capture_identity_matches=sum(r['sha256'] in targets for r in rows),extracted=len(rows),entries=[r['entry'] for r in rows]),indent=2))
