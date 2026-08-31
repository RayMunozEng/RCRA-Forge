"""Measure the recovered Blizar lava graph against installed game textures.

This is a read-only diagnostic for the isolated model viewer.  It reports how
much variation the shipped world-XZ projection can produce across a model at
the origin, which is important because the retail graph expects the actor's
actual world transform rather than an origin-centred preview mesh.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np


TEXTURES = {
    "fx": "textures/sbs/rock/lava_rock_002_fx.texture",
    "cma": "textures/environment/ground/gnd_lava_rock_01/gnd_lava_rock_01_cma.texture",
    "noise": "textures/effects/noise/fx_noisetile01.texture",
}


def _sample_repeat(image: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Bilinearly sample a 2D image with repeat wrapping."""
    height, width = image.shape[:2]
    position = np.mod(uv, 1.0) * np.array([width, height], dtype=np.float32)
    base = np.floor(position).astype(np.int64)
    fraction = position - base
    x0, y0 = base[:, 0] % width, base[:, 1] % height
    x1, y1 = (x0 + 1) % width, (y0 + 1) % height
    a = image[y0, x0]
    b = image[y0, x1]
    c = image[y1, x0]
    d = image[y1, x1]
    fx = fraction[:, 0, None]
    fy = fraction[:, 1, None]
    return (a * (1.0 - fx) + b * fx) * (1.0 - fy) + \
        (c * (1.0 - fx) + d * fx) * fy


def _smoothstep(edge0: float, edge1: float, value: np.ndarray) -> np.ndarray:
    t = np.clip((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _load_texture(toc, lookup, path: str) -> np.ndarray:
    from core.texture import TextureParser

    asset_id = lookup.asset_id(path)
    entry = toc.find_entry(asset_id) if asset_id is not None else None
    if entry is None:
        raise RuntimeError(f"Installed texture not found: {path}")
    texture = TextureParser(toc.extract_asset(entry)).parse()
    if texture.hd_len > 0 and texture.hd_width > 0 and texture.array_size <= 1:
        candidates = [
            candidate for candidate in toc.find_all_entries(asset_id)
            if candidate.size > entry.size
        ]
        if candidates:
            texture.hd_pixel_data = toc.extract_asset(max(candidates, key=lambda item: item.size))
    print(
        f"{path}: {texture.format_name} array={texture.array_size} "
        f"sd={texture.sd_width}x{texture.sd_height}/{len(texture.pixel_data)} "
        f"hd={texture.hd_width}x{texture.hd_height}/{len(texture.hd_pixel_data)}"
    )
    if texture.fmt in (0x5F, 0x60):
        decoded = texture.decode_to_rgb_float()
        if not decoded:
            raise RuntimeError(f"Could not decode {path}")
        return np.frombuffer(decoded, dtype=np.float32).reshape(
            texture.height, texture.width, 3,
        )
    decoded = texture.decode_to_rgba()
    if not decoded:
        raise RuntimeError(f"Could not decode {path}")
    return np.frombuffer(decoded, dtype=np.uint8).reshape(
        texture.height, texture.width, 4,
    ).astype(np.float32) / 255.0


def _evaluate(projected_position: np.ndarray, timer_seconds: float,
              textures: dict[str, np.ndarray]) -> np.ndarray:
    base_uv = projected_position * 0.075
    noise = _sample_repeat(textures["noise"], base_uv)[:, 0]
    timer = timer_seconds * 0.25
    phase_b = np.mod(noise * 0.10 + timer, 1.0)
    phase_a = np.mod(noise * 0.10 + timer + 0.50, 1.0)
    mapped_uv = base_uv * 0.60
    flow = np.full_like(mapped_uv, -1.0)
    uv_a = mapped_uv + flow * (phase_a[:, None] * 0.20) \
        - (timer - phase_a)[:, None] * 0.10
    uv_b = mapped_uv + flow * (phase_b[:, None] * 0.20) \
        + (timer - phase_b)[:, None] * 0.10
    weight_a = 1.0 - np.abs(1.0 - phase_a * 2.0)
    weight_b = 1.0 - np.abs(1.0 - phase_b * 2.0)
    mask_a = _sample_repeat(textures["cma"], uv_a)[:, 0]
    mask_b = _sample_repeat(textures["cma"], uv_b)[:, 0]
    mask_mix = mask_a * weight_a + mask_b * weight_b
    layer_a = _sample_repeat(textures["fx"], uv_a)[:, :3] * weight_a[:, None]
    layer_b = _sample_repeat(textures["cma"], uv_b)[:, :3] * weight_b[:, None]
    layered = layer_a + layer_b
    curve = np.power(
        np.maximum(1.0 - mask_mix[:, None], 0.000001),
        np.array([0.5, 6.0, 32.0], dtype=np.float32),
    )
    material_mask = 2.0 - mask_mix
    blend = _smoothstep(0.50, 1.25, material_mask)
    return np.clip(layered * (1.0 - blend[:, None]) + curve * blend[:, None], 0.0, 1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--hashes", type=Path, required=True)
    parser.add_argument("--model", type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()

    forge_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(forge_root))
    from core.archive import TocParser
    from core.hashes import HashLookup
    from core.mesh import ModelParser

    toc = TocParser(str(args.game_root / "toc"))
    toc.parse()
    lookup = HashLookup()
    lookup.load(str(args.hashes))
    entry = toc.find_entry(args.model)
    if entry is None:
        raise RuntimeError(f"Installed model not found: {args.model:016X}")
    model = ModelParser(toc.extract_asset(entry)).parse()
    positions = np.array([(v.x, v.y, v.z) for v in model.vertexes], dtype=np.float32)
    textures = {name: _load_texture(toc, lookup, path) for name, path in TEXTURES.items()}

    print(f"bounds min={positions.min(axis=0)} max={positions.max(axis=0)}")
    for projection, axes in (("world XZ", (0, 2)), ("preview XY", (0, 1))):
        axis_min = positions[:, axes].min(axis=0)
        axis_max = positions[:, axes].max(axis=0)
        grid_x, grid_y = np.meshgrid(
            np.linspace(axis_min[0], axis_max[0], 256),
            np.linspace(axis_min[1], axis_max[1], 256),
        )
        projected = np.column_stack((grid_x.ravel(), grid_y.ravel())).astype(np.float32)
        for seconds in (0.0, 1.0, 2.0, 3.0):
            color = _evaluate(projected, seconds, textures)
            print(
                f"{projection:10} t={seconds:.0f} "
                f"p05={np.percentile(color, 5, axis=0)} "
                f"median={np.median(color, axis=0)} "
                f"p95={np.percentile(color, 95, axis=0)} "
                f"near_white={np.mean(np.min(color, axis=1) > 0.85):.3f}"
            )


if __name__ == "__main__":
    main()
