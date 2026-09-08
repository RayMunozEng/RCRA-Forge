"""Validate the asset-independent production filter lifetime and public control."""

import json
from pathlib import Path

import unreal


output = Path(__file__).resolve().parent / "recovered"
output.mkdir(parents=True, exist_ok=True)
initial = unreal.FurDenoiseLibrary.is_recovered_fur_denoise_enabled()
registered = unreal.FurDenoiseLibrary.is_recovered_fur_denoise_registered()
enabled = unreal.FurDenoiseLibrary.set_recovered_fur_denoise_enabled(True)
observed_enabled = unreal.FurDenoiseLibrary.is_recovered_fur_denoise_enabled()
disabled = unreal.FurDenoiseLibrary.set_recovered_fur_denoise_enabled(False)
observed_disabled = not unreal.FurDenoiseLibrary.is_recovered_fur_denoise_enabled()
if initial:
    unreal.FurDenoiseLibrary.set_recovered_fur_denoise_enabled(True)

report = {
    "status": "complete" if all((registered, enabled, observed_enabled, disabled, observed_disabled)) else "failed",
    "registered_after_engine_init": registered,
    "initially_enabled": initial,
    "enable_call_succeeded": enabled,
    "enabled_state_observed": observed_enabled,
    "disable_call_succeeded": disabled,
    "disabled_state_observed": observed_disabled,
    "initial_state_restored": unreal.FurDenoiseLibrary.is_recovered_fur_denoise_enabled() == initial,
}
(output / "fur-denoise-production-registration.json").write_text(
    json.dumps(report, indent=2) + "\n", encoding="utf-8"
)
if report["status"] != "complete" or not report["initial_state_restored"]:
    raise RuntimeError(report)
unreal.log("FUR_DENOISE_PRODUCTION_REGISTRATION_OK")
