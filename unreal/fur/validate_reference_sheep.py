from pathlib import Path
reference_fixture='sheep'
path=Path(__file__).resolve().parent/'validate_reference_fur.py'
exec(compile(path.read_text(),str(path),'exec'),globals())
