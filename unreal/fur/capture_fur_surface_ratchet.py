from pathlib import Path
surface_fixture='ratchet'
verify_kernel=True
p=Path(__file__).with_name('capture_fur_surface_live.py')
exec(compile(p.read_text(encoding='utf-8'),str(p),'exec'),globals())
