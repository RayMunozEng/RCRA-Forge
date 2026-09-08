from pathlib import Path
dry_fixture='sheep'
p=Path(__file__).with_name('capture_reference_dry_motion.py')
exec(compile(p.read_text(),str(p),'exec'),globals())
