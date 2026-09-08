"""Keep the original point-PCF evidence while checking continuous PCF."""
from pathlib import Path
dynamics_material='M_FilteredShadow_ratchet_v1'
shadow_output='filtered-shadows'
script=Path(__file__).with_name('capture_reference_shadows.py')
exec(compile(script.read_text(),str(script),'exec'),globals())
