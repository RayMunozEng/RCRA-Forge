from pathlib import Path
fixture='sheep'
fur_surface_outputs=True
dry_material='M_FurSurface_sheep_v1'
dry_output='fur-surface-sheep'
p=Path(__file__).with_name('capture_dry_multilight.py')
exec(compile(p.read_text(encoding='utf-8'),str(p),'exec'),globals())
