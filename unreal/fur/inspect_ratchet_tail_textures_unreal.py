"""Export UE-imported tail textures for round-trip pixel verification."""

import json
from pathlib import Path

import unreal


root = Path(__file__).resolve().parent
out = root / "recovered/ratchet-tail-texture-roundtrip"
out.mkdir(exist_ok=True)
rows = []
for role in ("base_color", "fur_control", "specular_color", "normal"):
    asset_path = "/Game/FurValidation/RatchetTail/Textures/T_Tail_" + role + "_rgba_v2"
    texture = unreal.load_asset(asset_path)
    if not isinstance(texture, unreal.Texture2D):
        raise RuntimeError("Missing imported tail texture: " + asset_path)
    filename = out / (role + "-unreal.png")
    task = unreal.AssetExportTask()
    task.set_editor_property("object", texture)
    task.set_editor_property("filename", str(filename))
    task.set_editor_property("automated", True)
    task.set_editor_property("prompt", False)
    task.set_editor_property("replace_identical", True)
    task.set_editor_property("exporter", unreal.TextureExporterPNG())
    if not unreal.Exporter.run_asset_export_task(task) or not filename.is_file():
        raise RuntimeError("Could not export imported texture: " + asset_path)
    rows.append({
        "role": role,
        "asset": texture.get_path_name(),
        "width": texture.blueprint_get_size_x(),
        "height": texture.blueprint_get_size_y(),
        "srgb": texture.get_editor_property("srgb"),
        "compression_settings": str(texture.get_editor_property("compression_settings")),
        "mip_gen_settings": str(texture.get_editor_property("mip_gen_settings")),
        "png": filename.name,
    })

(out / "report.json").write_text(json.dumps({"textures": rows}, indent=2), encoding="utf-8")
print(json.dumps({"textures": rows}, indent=2))
