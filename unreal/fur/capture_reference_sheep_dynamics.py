from pathlib import Path
dynamics_fixture='sheep'
exec(compile(Path(__file__).with_name('capture_reference_dynamics.py').read_text(),
             str(Path(__file__).with_name('capture_reference_dynamics.py')),'exec'),globals())
