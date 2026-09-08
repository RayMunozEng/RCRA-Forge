"""Bundle the tested UE 5.8 editor plugin, source and assets; omit caches/PDBs."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
plugin = root.parent/'plugins/FurAuthoring'
binary = root/'ValidationProject/Binaries/Win64'
editor = json.loads((root/'editor-validation.json').read_text())
render = json.loads((root/'render-validation.json').read_text())
job = json.loads((root/'render-validation-job.json').read_text())
assert job['root_exit_code'] == 0
assert (plugin/'Content/Materials/M_FurAuthoring.uasset').is_file()
assert (plugin/'Content/Demo/FurDemo.umap').is_file()
modules = json.loads((binary/'UnrealEditor.modules').read_text())
modules['Modules'] = {'FurAuthoring':modules['Modules']['FurAuthoring']}
payload = {}
for path in sorted(plugin.rglob('*')):
    if not path.is_file() or any(x in path.parts for x in ['Intermediate','Binaries','__pycache__']):
        continue
    payload['FurAuthoring/'+path.relative_to(plugin).as_posix()] = path.read_bytes()
payload['FurAuthoring/Binaries/Win64/UnrealEditor-FurAuthoring.dll'] = (binary/'UnrealEditor-FurAuthoring.dll').read_bytes()
payload['FurAuthoring/Binaries/Win64/UnrealEditor.modules'] = json.dumps(modules,indent=2).encode()
manifest = {'engine':editor['engine'],'build_id':modules['BuildId'],
    'scope':'Static-mesh shell-fur authoring prototype; Win64 editor binary, source included',
    'files':{name:hashlib.sha256(data).hexdigest() for name,data in payload.items()}}
payload['FurAuthoring/package-manifest.json'] = json.dumps(manifest,indent=2).encode()
output = root/'FurAuthoring-UE5.8.zip'
with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for name,data in payload.items(): archive.writestr(name,data)
with zipfile.ZipFile(output) as archive:
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(archive.read(name)).hexdigest()==digest
(root/'package-validation.json').write_text(json.dumps({
    'archive':str(output),'bytes':output.stat().st_size,'files':len(payload),
    'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
    'readback_hashes_match':True},indent=2))
print(str(output))
