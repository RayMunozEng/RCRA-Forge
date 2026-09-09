"""A/B the runtime plugin's opt-in pre-TAA view extension on live Ratchet fur."""

from pathlib import Path

surface_fixture = "ratchet"
surface_filter_mode = "production"
verify_kernel = True
path = Path(__file__).with_name("capture_fur_surface_live.py")
exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), globals())
