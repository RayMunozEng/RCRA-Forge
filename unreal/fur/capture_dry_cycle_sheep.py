from pathlib import Path
fixture='sheep'
dry_material='M_DryMultilight_sheep_cycle160_v1'
dry_output='dry-cycle160-sheep'
p=Path(__file__).with_name('capture_dry_multilight.py')
exec(compile(p.read_text(encoding='utf-8'),str(p),'exec'),globals())
