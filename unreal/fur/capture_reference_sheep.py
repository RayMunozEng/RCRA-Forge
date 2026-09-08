from pathlib import Path
reference_fixture='sheep'
path=Path(__file__).resolve().parent/'capture_reference_scene.py'
exec(compile(path.read_text(),str(path),'exec'),globals())
