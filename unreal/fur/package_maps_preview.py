"""Package the independently validated map-authoring preview; preserve v0.1 ZIP."""
import hashlib
import json
from pathlib import Path
import zipfile
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--skeletal',action='store_true')
parser.add_argument('--lighting',action='store_true')
parser.add_argument('--dynamics',action='store_true')
parser.add_argument('--animated',action='store_true')
parser.add_argument('--filtered',action='store_true')
parser.add_argument('--environment',action='store_true')
parser.add_argument('--controls',action='store_true')
parser.add_argument('--dry-maintenance',action='store_true')
args = parser.parse_args()
args.controls = args.controls or args.dry_maintenance
args.environment = args.environment or args.controls
args.filtered = args.filtered or args.environment
args.animated = args.animated or args.filtered
args.dynamics = args.dynamics or args.animated
args.lighting = args.lighting or args.dynamics
assert not (args.skeletal and args.lighting)
prefix = 'animated' if args.animated else ('dynamics' if args.dynamics else ('lighting' if args.lighting else ('skeletal' if args.skeletal else 'maps')))

if args.filtered: prefix='filtered'
if args.environment: prefix='environment'
if args.controls: prefix='controls'
if args.dry_maintenance: prefix='dry-maintenance'

root = Path(__file__).resolve().parent
plugin = root.parent/'plugins/FurAuthoring'
results = root/'recovered'
tags=['reference-api','reference-sheep-api','reference-scene-render','reference-sheep-render'] if args.lighting else [prefix+'-api',prefix+'-render']
if args.dry_maintenance:
    tags += ['skeletal-api','dry-motion-ratchet-20260907','dry-motion-sheep-20260907']
    api=json.loads((results/'skeletal-validation.json').read_text())
    assert 'material count matches built geometry after deferred edits' in api['checks']
    for fixture in ('ratchet','sheep'):
        folder=results/('dry-motion-'+fixture+'-20260907')
        raw=json.loads((folder/'report.json').read_text())
        check=json.loads((folder/'validation.json').read_text())
        assert raw['translation_cm']==15 and len(raw['captures'])==14
        assert all(row['wetness']==0 and row['wind']==0 and row['resolved_aa_method']==2 for row in raw['captures'])
        assert check['settled_background_clean']
        assert all(hashlib.sha256((folder/(row['label']+'.png')).read_bytes()).hexdigest()==row['image_sha256'] for row in check['captures'])
if args.controls:
    tags += ['environment-controls']
    checked=json.loads((results/'environment-controls-validation.json').read_text())
    assert checked['rebuild_error_rgb8']<3 and checked['missing_input_error_rgb8']<3
if args.environment:
    tags += ['environment-ratchet','environment-sheep','environment-sampling']
    checked=json.loads((results/'environment-validation.json').read_text())
    assert all(1.85<checked[f]['intensity_linear_ratio']<2.15 for f in ('ratchet','sheep'))
    sampling=json.loads((results/'environment-sampling-validation.json').read_text())
    assert sampling['maximum_cube_error_rgb8']<3 and sampling['maximum_brdf_error_rgb8']<3
if args.filtered:
    tags += ['filtered-shadows','self-shadows']
    checked=json.loads((results/'filtered-shadow-validation.json').read_text())
    assert checked['shader_sha256']==hashlib.sha256((plugin/'Shaders/FurSceneShadow.ush').read_bytes()).hexdigest()
    assert checked['self-shadows']['wpo_refresh_changed_pixels']>100
if args.animated:
    tags += ['continuous','animated-shadows']
    checked=json.loads((results/'stream-shadow-validation.json').read_text())
    assert checked['continuous']['frames']==16
    assert checked['shadows']['changed_deformation_pixels']>100
if args.dynamics:
    tags += ['dynamics-skeletal','dynamics-ratchet','dynamics-sheep']
    validation=json.loads((results/'dynamics-validation.json').read_text())
    assert all(k in validation for k in ('skeletal','ratchet','sheep'))
    assert validation['skeletal']['minimum_walk_frame_change_rgb8']>.1
    for fixture in ('skeletal','ratchet','sheep'):
        report=json.loads((results/('dynamics-'+fixture)/'report.json').read_text())
        assert len(report['captures'])==(18 if fixture=='skeletal' else 4)
        assert all(row['draw_realtime'] and row['resolved_aa_method']==2 for row in report['captures'])
for tag in tags:
    report = json.loads((results/(tag+'-job.json')).read_text())
    assert report.get('root_exit_code')==0, tag
    log=(results/(tag+'.log')).read_text(errors='replace')
    assert 'Failed to compile Material' not in log
    assert 'LogPython: Error:' not in log
if args.lighting:
    for fixture in ('matched-reference','sheep-reference'):
        render=json.loads((root/fixture/'scene-render.json').read_text())
        assert len(render['screenshots'])==3 and len(render['checks'])==3
        # These screenshots verify lighting only; a settings label is not
        # evidence of effective TAA. viewport-live holds the temporal tests.
        assert '32 Halton' in render['aa']
        assert render['checks'][2]['shadow_enabled']==1
        assert all(Path(p).is_file() for p in render['screenshots'])
else:
    render = json.loads((results/(prefix+'-render.json')).read_text())
    assert len(render['screenshots'])==(2 if args.skeletal else 3)
    if args.skeletal:
        assert render['maximum_bone_motion_cm']>1 and render['maximum_follow_error_cm']<.001
required = ['Materials/M_FurAuthoringMaps.uasset','Demo/FurMaps.umap',
            'Textures/T_DefaultFurShells.uasset','Textures/Authoring/T_White.uasset']
assert all((plugin/'Content'/p).is_file() for p in required)
if args.skeletal:
    assert (plugin/'Content/Materials/M_FurSkeletal.uasset').is_file()
    assert (plugin/'Content/Demo/FurSkeletal.umap').is_file()
binary = root/'ValidationProject/Binaries/Win64'
modules = json.loads((binary/'UnrealEditor.modules').read_text())
modules['Modules'] = {'FurAuthoring':modules['Modules']['FurAuthoring']}
payload = {}
for path in sorted(plugin.rglob('*')):
    if not path.is_file() or any(p in path.parts for p in ['Intermediate','Binaries','__pycache__']):
        continue
    payload['FurAuthoring/'+path.relative_to(plugin).as_posix()] = path.read_bytes()
descriptor = json.loads(payload['FurAuthoring/FurAuthoring.uplugin'])
descriptor.update(Version=2,VersionName='0.2.0-preview',Description='Static-mesh fur with length, density and groom maps, wind and wetness.')
if args.skeletal:
    descriptor.update(Version=3,VersionName='0.3.0-preview',Description='Static and pose-sharing skeletal fur with imported maps, wind and wetness.')
if args.lighting:
    descriptor.update(Version=4,VersionName='0.4.0-preview',Description='Fur authoring with recovered directional-light response, bounded caster shadows and temporal coverage.')
if args.dynamics:
    descriptor.update(Version=5,VersionName='0.5.0-preview',Description='Recovered scene-lit static and skeletal fur with wind bending and wet response.')
if args.animated:
    descriptor.update(Version=6,VersionName='0.6.0-preview',Description='Scene-lit fur with live wind, skeletal playback and scheduled animated-caster shadows.')
if args.filtered:
    descriptor.update(Version=7,VersionName='0.7.0-preview',Description='Scene-lit fur with continuous shadow filtering and tested shell self-occlusion.')
if args.environment:
    descriptor.update(Version=8,VersionName='0.8.0-preview',Description='Recovered fur lighting with optional authored environment cube and BRDF lookup.')
if args.controls:
    descriptor.update(Version=9,VersionName='0.9.0-preview',Description='Fur environment setup through Details and Blueprint with input status and rebuild rebinding.')
if args.dry_maintenance:
    descriptor.update(Version=10,VersionName='0.9.1-preview',Description='Fur authoring maintenance: skeletal shell counts match built geometry; dry rigid-motion checks validated.')
payload['FurAuthoring/FurAuthoring.uplugin'] = json.dumps(descriptor,indent=2).encode()
payload['FurAuthoring/Binaries/Win64/UnrealEditor-FurAuthoring.dll'] = (binary/'UnrealEditor-FurAuthoring.dll').read_bytes()
payload['FurAuthoring/Binaries/Win64/UnrealEditor.modules'] = json.dumps(modules,indent=2).encode()
manifest = {'build_id':modules['BuildId'],'scope':'Static-mesh fur with imported maps; no in-editor brush, skeletal support or native lighting parity',
            'files':{name:hashlib.sha256(data).hexdigest() for name,data in payload.items()}}
if args.skeletal:
    manifest['scope'] = 'Static and pose-sharing skeletal fur; editor deformation validated, native lighting/velocity parity and runtime performance unverified'
if args.lighting:
    manifest['scope']='Recovered one-directional-light bridge and selected-caster shadows; static Ratchet/sheep fixtures validated outside package. No VSM/Lumen/probes, moving temporal parity or game assets.'
    assert all('FurReference' not in name and 'sheep-reference' not in name for name in payload)
if args.dynamics:
    manifest['scope']='Recovered scene-lit static/skeletal material builder; sampled engine walk and Ratchet/sheep fixed wet/wind snapshots validated privately. Native velocity, fast-motion ghosting, deforming shadows and full lighting parity remain unverified. No game assets.'
if args.animated:
    manifest['scope']='Continuous editor playback/live-time wind and one selected animated skeletal caster validated privately. Native velocity, general ghosting, WPO self-shadowing, full scene lighting and runtime performance remain unverified. No game assets.'
if args.filtered:
    manifest['scope']='Bilinear comparison filtering and static Ratchet shell self-occlusion/WPO recapture validated privately. Opaque depth shadows, no strand transmittance. Environment lighting, native velocity, general ghosting and runtime performance remain unverified. No game assets.'
if args.environment:
    manifest['scope']='Optional linear authored-cube and BRDF environment response; Ratchet/sheep controls and cube sampling validated privately. Requires user-supplied environment assets. No native Skylight/Lumen/probe integration or game assets.'
if args.controls:
    manifest['scope']='Environment cube/BRDF setup in the Fur Lighting Controller Details and Blueprint. Rebuild, disable, missing-input and parent-default behavior validated. Compatible material and user-supplied lighting assets required; no automatic Skylight/Lumen or game assets.'
if args.dry_maintenance:
    manifest['scope']='Verified skeletal shell-count consistency and dry whole-character rigid-motion background checks. Existing environment authoring features retained. Ear/native-closeup parity, general animated silhouette quality and full dry-fur completion remain open. No game assets.'
payload['FurAuthoring/package-manifest.json'] = json.dumps(manifest,indent=2).encode()
output = root/('FurAuthoring-UE5.8-'+prefix+'-preview.zip')
with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for name,data in payload.items():
        archive.writestr(name,data)
with zipfile.ZipFile(output) as archive:
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(archive.read(name)).hexdigest()==digest
report = {'archive':str(output),'bytes':output.stat().st_size,'files':len(payload),
          'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'readback_hashes_match':True}
(results/(prefix+'-package.json')).write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
