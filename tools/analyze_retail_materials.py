"""Inventory the exact material instances used by selected shipped models."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys

import numpy as np


DEFAULT_MODELS = (
    0x90A10567FBDF8DF4,  # moving lava platform
    0x8DB99222DDA9D6FB,  # lava rock 01
    0xAF87E6B24E567DE9,  # lavafall 01
)


def _strings(data: bytes, minimum: int = 4) -> list[str]:
    result: list[str] = []
    start = None
    for index, value in enumerate(data + b"\0"):
        if 0x20 <= value < 0x7F:
            if start is None:
                start = index
        elif start is not None:
            if index - start >= minimum:
                result.append(data[start:index].decode("ascii", errors="replace"))
            start = None
    return result


def _params(dat1) -> list[dict[str, object]]:
    section = dat1.get_section(0xF5260180)
    if section is None or len(section) < 40:
        return []
    data = bytes(section)
    _, count, _, _, params_end = struct.unpack_from("<IIIII", data, 0)
    if count > 128 or params_end < 40 + count * 8 or params_end > len(data):
        return []
    keys = data[40:40 + count * 8]
    raw_values = data[40 + count * 8:params_end]
    result: list[dict[str, object]] = []
    for index in range(count):
        offset, size, key = struct.unpack_from("<HHI", keys, index * 8)
        raw = raw_values[offset:offset + size]
        item: dict[str, object] = {
            "index": index,
            "key": f"{key:08X}",
            "offset": offset,
            "size": size,
            "hex": raw.hex(),
        }
        if size and size % 4 == 0:
            item["float32"] = list(struct.unpack(f"<{size // 4}f", raw))
            item["uint32"] = list(struct.unpack(f"<{size // 4}I", raw))
        result.append(item)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--hashes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "models", nargs="*", type=lambda value: int(value, 0), default=DEFAULT_MODELS
    )
    args = parser.parse_args()

    forge_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(forge_root))
    os.chdir(forge_root)

    from core.archive import DAT1, TocParser
    from core.asset_loader import _resolve_mat_name
    from core.hashes import HashLookup
    from core.material import parse_material_asset
    from core.mesh import ModelParser
    from core.texture import TextureParser

    toc = TocParser(str(args.game_root / "toc"))
    toc.parse()
    lookup = HashLookup()
    lookup.load(str(args.hashes))
    output: dict[str, object] = {"models": []}

    for model_id in args.models:
        entry = toc.find_entry(model_id)
        if entry is None:
            raise RuntimeError(f"No installed model {model_id:016X}")
        raw = toc.extract_asset(entry)
        model_dat1 = DAT1(raw)
        model = ModelParser(raw).parse()
        material_section = model_dat1.get_section(0x3250BB80)
        material_indices = sorted({mesh.material_index for mesh in model.meshes})
        model_info: dict[str, object] = {
            "asset_id": f"{model_id:016X}",
            "path": lookup.lookup(model_id),
            "materials": [],
        }
        for material_index in material_indices:
            path = _resolve_mat_name(model_dat1, material_section, material_index)
            material_info: dict[str, object] = {
                "index": material_index,
                "path": path,
            }
            material_id = lookup.asset_id(path) if path else None
            if material_id is None:
                material_info["error"] = "unresolved material path"
                model_info["materials"].append(material_info)
                continue
            material_entry = toc.find_entry(material_id)
            if material_entry is None:
                material_info["error"] = "material absent from installed TOC"
                model_info["materials"].append(material_info)
                continue
            material_raw = toc.extract_asset(material_entry)
            material_dat1 = DAT1(material_raw)
            parsed = parse_material_asset(material_raw)
            texture_metadata = []
            for slot in parsed.slots:
                texture_id = lookup.asset_id(slot.path)
                texture_entry = toc.find_entry(texture_id) if texture_id is not None else None
                if texture_entry is None:
                    continue
                texture = TextureParser(toc.extract_asset(texture_entry)).parse()
                metadata = {
                    "role": slot.role,
                    "path": slot.path,
                    "format": texture.format_name,
                    "format_code": texture.fmt,
                    "sd_width": texture.sd_width,
                    "sd_height": texture.sd_height,
                    "hd_width": texture.hd_width,
                    "hd_height": texture.hd_height,
                }
                preview_rgba = texture.decode_to_rgba()
                if preview_rgba:
                    preview = np.frombuffer(preview_rgba, dtype=np.uint8).reshape((-1, 4))
                    metadata["preview_mean"] = preview.mean(axis=0).tolist()
                    metadata["preview_p99"] = np.percentile(preview, 99, axis=0).tolist()
                float_rgb = texture.decode_to_rgb_float()
                if float_rgb:
                    values = np.frombuffer(float_rgb, dtype=np.float32).reshape((-1, 3))
                    metadata["float_min"] = values.min(axis=0).tolist()
                    metadata["float_median"] = np.median(values, axis=0).tolist()
                    metadata["float_p99"] = np.percentile(values, 99, axis=0).tolist()
                    metadata["float_max"] = values.max(axis=0).tolist()
                    try:
                        import imagecodecs
                        blocks_w = max(1, (texture.sd_width + 3) // 4)
                        blocks_h = max(1, (texture.sd_height + 3) // 4)
                        raw_decoded = imagecodecs.bcn_decode(
                            texture.pixel_data[:blocks_w * blocks_h * 16],
                            format=6,
                            shape=(texture.sd_height, texture.sd_width, 3),
                        )
                        metadata["decoder_dtype"] = str(raw_decoded.dtype)
                        metadata["decoder_shape"] = list(raw_decoded.shape)
                    except Exception:
                        pass
                texture_metadata.append(metadata)
            material_info.update(
                {
                    "asset_id": f"{material_id:016X}",
                    "graph_path": parsed.graph_path,
                    "strings": _strings(material_raw),
                    "parameters": _params(material_dat1),
                    "slots": [
                        {
                            "index": slot.index,
                            "path": slot.path,
                            "asset_id_lo": f"{slot.asset_id_lo:08X}",
                            "role": slot.role,
                        }
                        for slot in parsed.slots
                    ],
                    "texture_metadata": texture_metadata,
                    "sections": [
                        {"tag": f"{tag:08X}", "size": len(section)}
                        for tag, section in material_dat1.sections.items()
                    ],
                }
            )
            model_info["materials"].append(material_info)
        output["models"].append(model_info)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
