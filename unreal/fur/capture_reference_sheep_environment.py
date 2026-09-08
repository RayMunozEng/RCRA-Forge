from pathlib import Path
environment_fixture='sheep'
p=Path(__file__).with_name('capture_reference_environment.py')
exec(compile(p.read_text(),str(p),'exec'),globals())
