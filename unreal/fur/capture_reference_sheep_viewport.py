from pathlib import Path
reference_fixture='sheep'
exec(compile(Path(__file__).with_name('capture_reference_viewport.py').read_text(),
             str(Path(__file__).with_name('capture_reference_viewport.py')),'exec'),globals())
