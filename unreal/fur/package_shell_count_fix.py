"""Deliver only the runtime-verified count fix on top of the existing preview."""
from pathlib import Path
import hashlib,json,zipfile
root=Path(__file__).resolve().parent;plugin=root.parent/'plugins/FurAuthoring'
base=root/'FurAuthoring-UE5.8-controls-preview.zip'
assert hashlib.sha256(base.read_bytes()).hexdigest()=='f0fb550ddb8e092b336065a42f9d3a483d98df4351449dacb2bc0f70a4bdfc6e'
job=json.loads((root/'recovered/skeletal-api-job.json').read_text());assert job['root_exit_code']==0
log=(root/'recovered/skeletal-api.log').read_text(errors='replace');assert 'SKELETAL_FUR_API_OK' in log and 'LogPython: Error:' not in log
api=json.loads((root/'recovered/skeletal-validation.json').read_text())
assert 'material count matches built geometry after deferred edits' in api['checks']
assert 'Result: Succeeded' in (root/'recovered/dry-count-build-20260907.log').read_text(errors='replace')
with zipfile.ZipFile(base) as z:payload={name:z.read(name) for name in z.namelist()}
source='FurAuthoring/Source/FurAuthoring/Private/SkeletalFurAuthoringActor.cpp'
changed=[name for name in payload if name.startswith('FurAuthoring/Source/') and payload[name]!=(root.parent/'plugins'/name).read_bytes()]
assert changed==[source],changed
payload[source]=(root.parent/'plugins'/source).read_bytes()
modules=json.loads((root/'ValidationProject/Binaries/Win64/UnrealEditor.modules').read_text())
old_modules=json.loads(payload['FurAuthoring/Binaries/Win64/UnrealEditor.modules']);assert modules['BuildId']==old_modules['BuildId']
payload['FurAuthoring/Binaries/Win64/UnrealEditor-FurAuthoring.dll']=(root/'ValidationProject/Binaries/Win64/UnrealEditor-FurAuthoring.dll').read_bytes()
descriptor=json.loads(payload['FurAuthoring/FurAuthoring.uplugin']);descriptor.update(Version=10,VersionName='0.9.1-preview',Description='Maintenance preview: skeletal shell count matches built geometry. Visual parity work remains open.')
payload['FurAuthoring/FurAuthoring.uplugin']=json.dumps(descriptor,indent=2).encode()
payload['FurAuthoring/SHELL_COUNT_FIX.md']=b"# Verified shell-count correction\n\nRebuild clamps skeletal Shell Count to1..32 and reflects that count in Details. RecoveredShellCount describes the currently built layers, including after Blueprint changes the requested count before rebuilding. Existing16/32-layer geometry is unchanged.\n\nBuilt for UE5.8.0 build55116800; editor lifecycle/count regression passed. This is a maintenance preview, not a finished dry-fur release. Native ear-contour acceptance, corrected sheep motion capture and general animated silhouette quality remain open. Previous shaders and content are preserved byte-for-byte. Close the editor before replacing a plugin installation.\n"
payload.pop('FurAuthoring/package-manifest.json')
manifest=dict(build_id=modules['BuildId'],scope='Runtime-verified skeletal shell-count correction only. Not full dry-fur completion or native parity.',base_sha256=hashlib.sha256(base.read_bytes()).hexdigest(),files={k:hashlib.sha256(v).hexdigest() for k,v in payload.items()})
payload['FurAuthoring/package-manifest.json']=json.dumps(manifest,indent=2).encode()
out=root/'FurAuthoring-UE5.8-shell-count-fix.zip'
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for k,v in payload.items():z.writestr(k,v)
with zipfile.ZipFile(out) as z:
 for k,h in manifest['files'].items():assert hashlib.sha256(z.read(k)).hexdigest()==h
result=dict(archive=str(out),bytes=out.stat().st_size,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),files=len(payload),readback_hashes_match=True,scope=manifest['scope'])
(root/'recovered/shell-count-fix-package.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
