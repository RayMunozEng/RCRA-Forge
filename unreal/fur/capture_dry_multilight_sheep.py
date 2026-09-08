from pathlib import Path
fixture='sheep'
p=Path(__file__).with_name('capture_dry_multilight.py')
exec(compile(p.read_text(encoding='utf-8'),str(p),'exec'),globals())
