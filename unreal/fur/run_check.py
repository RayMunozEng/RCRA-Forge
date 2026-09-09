"""Run a bounded isolated UE fur check with workspace-local temporary paths."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('script',choices=['inspect_ratchet_tail_textures_unreal.py','import_ratchet_body_private.py','capture_retail_ear_strands.py','capture_synthetic_production_filter.py','validate_production_filter_registration.py','capture_reference_ear_facing.py','capture_fur_surface_ratchet.py','capture_fur_surface_live.py','capture_fur_surface_production.py','capture_fur_surface_production_ratchet.py','capture_fur_surface_outputs.py','capture_denoise_kernel.py','capture_dry_cycle_sheep.py','capture_dry_multilight.py','capture_dry_multilight_sheep.py','validate_dry_multilight.py','capture_reference_dry_motion.py','capture_reference_sheep_dry_motion.py','capture_reference_skeletal_wind.py','capture_reference_skeletal_accuracy.py','capture_reference_skeletal_velocity.py','capture_reference_fur_wind_accuracy.py','capture_reference_velocity_calibration.py','capture_reference_sheep_velocity_float.py','capture_reference_sheep_motion.py','capture_reference_sheep_environment_inputs.py','validate_mapped_fur.py','capture_mapped_fur.py','validate_skeletal_fur.py','capture_skeletal_fur.py','validate_reference_fur.py','capture_reference_fur.py','capture_reference_hair.py','capture_reference_scene.py','validate_reference_sheep.py','capture_reference_sheep.py','capture_reference_viewport.py','capture_reference_sheep_viewport.py','capture_reference_dynamics.py','capture_reference_ratchet_dynamics.py','capture_reference_sheep_dynamics.py','capture_reference_stream.py','capture_reference_shadows.py','capture_reference_filtered_shadows.py','capture_reference_self_shadows.py','capture_reference_environment.py','capture_reference_sheep_environment.py','capture_reference_environment_sampling.py','capture_reference_environment_controls.py','capture_reference_ear_contours.py','capture_reference_ear_sequence.py','capture_reference_ear_boundary.py','capture_reference_ear_resampling.py','capture_reference_ear_spacing.py'])
parser.add_argument('--engine-root',type=Path,help='UE installation root containing Engine/Binaries/Win64')
parser.add_argument('--min-physical-gib',type=float,default=8,
    help='Private runner free-physical-memory floor (default: 8 GiB)')
parser.add_argument('--max-job-memory-gib',type=float,default=6,
    help='Private runner aggregate job-memory ceiling (default: 6 GiB)')
next(action for action in parser._actions if action.dest == 'script').choices.append(
    'capture_ratchet_full_body_registration.py')
next(action for action in parser._actions if action.dest == 'script').choices.extend((
    'capture_ratchet_strand_binding.py', 'capture_ratchet_head_binding.py'))
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
fur = root/'unreal/fur'
render = args.script.startswith('capture_')
reference_import = args.script in (
    'validate_reference_fur.py', 'validate_reference_sheep.py',
    'import_ratchet_body_private.py')
tag = ('reference' if 'reference' in args.script else ('skeletal' if 'skeletal' in args.script else 'maps')) + ('-render' if render else '-api')
if args.script=='capture_reference_hair.py': tag='reference-hair-render'
if args.script=='capture_reference_scene.py': tag='reference-scene-render'
if args.script=='capture_reference_viewport.py': tag='reference-viewport-render'
if 'sheep' in args.script: tag='reference-sheep-'+('render' if render else 'api')
if args.script=='capture_reference_sheep_viewport.py': tag='reference-sheep-viewport-render'
output = fur/'recovered'
output.mkdir(parents=True,exist_ok=True)
marker = None
if 'reference' in args.script:
    marker = fur/'matched-reference'/('import-validation.json' if reference_import else
        ('render-recovered.json' if args.script=='capture_reference_hair.py' else 'render.json'))
old_marker = marker.stat().st_mtime_ns if marker and marker.exists() else 0
if args.script=='validate_skeletal_fur.py':
    marker=output/'skeletal-validation.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_scene.py':
    marker=fur/'matched-reference/scene-render.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if 'sheep' in args.script:
    marker=fur/'sheep-reference'/('scene-render.json' if render else 'import-validation.json')
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
project = fur/'ValidationProject'
if 'viewport' in args.script:
    marker=fur/('sheep-reference' if 'sheep' in args.script else 'matched-reference')/'viewport-live/report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if 'dynamics' in args.script:
    fixture='sheep' if 'sheep' in args.script else ('ratchet' if 'ratchet' in args.script else 'skeletal')
    tag='dynamics-'+fixture
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script in ('capture_reference_stream.py','capture_reference_shadows.py'):
    tag='continuous' if 'stream' in args.script else 'animated-shadows'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script in ('capture_reference_filtered_shadows.py','capture_reference_self_shadows.py'):
    tag='filtered-shadows' if 'filtered' in args.script else 'self-shadows'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if 'environment' in args.script:
    tag='environment-'+('controls' if 'controls' in args.script else ('sampling' if 'sampling' in args.script else ('sheep' if 'sheep' in args.script else 'ratchet')))
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_sheep_environment_inputs.py':
    tag='environment-sheep-inputs'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_sheep_motion.py':
    tag='sheep-motion-20260907'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_sheep_velocity_float.py':
    tag='sheep-velocity-float-20260907'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_velocity_calibration.py':
    tag='velocity-calibration-20260907'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script in ('capture_reference_dry_motion.py','capture_reference_sheep_dry_motion.py'):
    tag='dry-motion-'+('sheep' if 'sheep' in args.script else 'ratchet')+'-20260907'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_skeletal_wind.py':
    tag='skeletal-wind-20260907'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_skeletal_accuracy.py':
    tag='skeletal-accuracy-20260907'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_skeletal_velocity.py':
    tag='skeletal-velocity-20260907'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_fur_wind_accuracy.py':
    tag='fur-wind-accuracy-20260907'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_ear_contours.py':
    tag='ear-contours'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_ear_sequence.py':
    tag='ue-ear-sequence'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_ear_boundary.py':
    tag='ear-boundary'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_ear_resampling.py':
    tag='ear-resampling'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_ear_spacing.py':
    tag='ear-spacing'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script in ('capture_dry_multilight.py','capture_dry_multilight_sheep.py'):
    tag='dry-multilight-'+('sheep' if 'sheep' in args.script else 'ratchet')
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_dry_cycle_sheep.py':
    tag='dry-cycle160-sheep'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_denoise_kernel.py':
    tag='fur-denoise-kernel'
    marker=output/'fur-denoise-kernel.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_reference_ear_facing.py':
    tag='ear-facing-audit'
    marker=output/tag/'capture-report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_retail_ear_strands.py':
    tag='retail-ear-strands'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_ratchet_full_body_registration.py':
    tag='ratchet-full-body-registration'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_ratchet_strand_binding.py':
    tag='ratchet-strand-binding'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_ratchet_head_binding.py':
    tag='ratchet-head-binding'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='import_ratchet_body_private.py':
    tag='ratchet-body-import'
    marker=output/'ratchet-body/ue-import-report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='inspect_ratchet_tail_textures_unreal.py':
    tag='ratchet-tail-texture-roundtrip'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_fur_surface_ratchet.py':
    tag='fur-surface-live-ratchet'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_fur_surface_live.py':
    tag='fur-surface-live-sheep'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_fur_surface_production.py':
    tag='fur-surface-production-sheep'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_fur_surface_production_ratchet.py':
    tag='fur-surface-production-ratchet'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_fur_surface_outputs.py':
    tag='fur-surface-sheep'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='validate_dry_multilight.py':
    tag='dry-multilight-api'
    marker=output/'dry-multilight-validation.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='validate_production_filter_registration.py':
    tag='fur-denoise-production-registration'
    marker=output/'fur-denoise-production-registration.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
if args.script=='capture_synthetic_production_filter.py':
    tag='fur-denoise-production-synthetic'
    marker=output/tag/'report.json'
    old_marker=marker.stat().st_mtime_ns if marker.exists() else 0
engine_candidates=[]
if args.engine_root: engine_candidates.append(args.engine_root)
if os.environ.get('UE_ENGINE_ROOT'): engine_candidates.append(Path(os.environ['UE_ENGINE_ROOT']))
engine_candidates.extend(Path(path) for path in (
    'C:/Program Files/Epic Games/UE_5.8','D:/Epic Games/UE_5.8','E:/Epic Games/UE_5.8','F:/Epic Games/UE_5.8'))
engine=next((path for path in engine_candidates
    if (path/'Engine/Binaries/Win64/UnrealEditor.exe').is_file()),None)
if engine is None: raise SystemExit('UE 5.8 not found; pass --engine-root')
private_desktop=root/'tools/private_desktop.py'
if not private_desktop.is_file(): raise SystemExit('missing private desktop runner: '+str(private_desktop))
argv = [sys.executable,str(private_desktop),
        '--cwd',str(root),'--report',str(output/(tag+'-job.json')),
        '--exit-with-root',
        '--seconds',str(300 if render else 180),'--min-physical-gib',str(args.min_physical_gib),
        '--min-pagefile-gib','8','--min-disk-gib','2',
        '--max-job-memory-gib',str(
            args.max_job_memory_gib
            if render or args.script == 'import_ratchet_body_private.py'
            else min(args.max_job_memory_gib, 4)),
        '--priority','below-normal','--',
        str(engine/'Engine/Binaries/Win64'/('UnrealEditor.exe' if render or reference_import else 'UnrealEditor-Cmd.exe')),
        str(project/'FurValidation.uproject')]
if render:
    if 'reference' in args.script:
        argv += ['/Game/FurReference/MatchedRatchet']
    # A startup exception must close the editor instead of leaving it idle
    # until the job deadline or memory guard. Script callbacks own normal exit.
    entry=output/(tag+'-entry.py')
    entry.write_text('import runpy, traceback, unreal\ntry:\n    runpy.run_path('+repr(str(fur/args.script))+', run_name="__main__")\nexcept Exception:\n    unreal.log_error(traceback.format_exc())\n    unreal.SystemLibrary.execute_console_command(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(), "QUIT_EDITOR")\n')
    argv += ['-ExecutePythonScript='+str(entry),'-d3d11','-sm5','-windowed',
             '-ResX=640','-ResY=480','-NoLiveCoding','-ExecCmds=t.MaxFPS 10']
elif reference_import:
    # StaticMeshEditorSubsystem is not initialized in a commandlet. The full
    # editor with NullRHI provides it without starting a GPU render.
    argv += ['-ExecutePythonScript='+str(fur/args.script)]
    if args.script == 'import_ratchet_body_private.py':
        # UE 5.8 Interchange asserts during full-editor initialization under
        # NullRHI. Keep it on the isolated desktop using the proven SM5 path.
        argv += ['-d3d11', '-sm5', '-windowed', '-ResX=320', '-ResY=240']
    else:
        argv += ['-NullRHI', '-NoShaderCompile']
    argv += ['-NoLiveCoding']
else:
    argv += ['-run=pythonscript','-script='+str(fur/args.script),'-NullRHI','-NoShaderCompile']
argv += ['-unattended','-nosound','-nosplash','-DDC=InstalledNoZenLocalFallback',
         '-LocalDataCachePath='+str(project/'DerivedDataCache'),
         '-ShaderWorkingDir='+str(project/'Intermediate/Shaders/Work'),
         '-abslog='+str(output/(tag+'.log'))]
# API checks use the minimal plugin set. Captures retain the previously
# compiled shader registry; removing shader plugins invalidates that cache.
# Only this private validation project is changed, restored even on failure.
import json
project_file=project/'FurValidation.uproject'
project_original=project_file.read_bytes()
use_cached_plugins=render or reference_import
engine_config=project/'Config/DefaultEngine.ini'
engine_config_original=engine_config.read_bytes() if engine_config.exists() else None
try:
    descriptor=json.loads(project_original)
    descriptor['DisableEnginePluginsByDefault']=not use_cached_plugins
    project_file.write_text(json.dumps(descriptor,indent=2),encoding='utf-8')
    if args.script in ('capture_synthetic_production_filter.py',
                       'capture_fur_surface_production.py',
                       'capture_fur_surface_production_ratchet.py'):
        engine_config.parent.mkdir(parents=True,exist_ok=True)
        with engine_config.open('a',encoding='utf-8') as config:
            config.write('\n[DevOptions.Shaders]\nPercentageUnusedShaderCompilingThreads=100\n'
                         'NumUnusedShaderCompilingThreads=64\n'
                         'NumUnusedShaderCompilingThreadsDuringGame=64\n')
    with (output/(tag+'-launch.log')).open('w') as log:
        subprocess.run(argv,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
finally:
    project_file.write_bytes(project_original)
    if engine_config_original is None:
        engine_config.unlink(missing_ok=True)
    else:
        engine_config.write_bytes(engine_config_original)
# The job wrapper's exit code alone does not indicate UE success.
import json
report = json.loads((output/(tag+'-job.json')).read_text())
print(json.dumps({k:report.get(k) for k in ['status','root_exit_code','job_memory']},indent=2))
if report.get('root_exit_code') != 0:
    raise SystemExit(1)
if marker:
    log_text=(output/(tag+'.log')).read_text(errors='replace')
    # Material nodes are connected incrementally, so Unreal can log temporary
    # compile failures before the final graph exists. The material builder now
    # checks RecompileMaterial's final error list and raises a Python error when
    # that final compile is invalid.
    if 'LogPython: Error:' in log_text:
        raise SystemExit('UE exited, but the reference script failed; inspect '+str(output/(tag+'.log')))
    if not marker.exists() or marker.stat().st_mtime_ns<=old_marker:
        raise SystemExit('Reference completion report was not refreshed: '+str(marker))
