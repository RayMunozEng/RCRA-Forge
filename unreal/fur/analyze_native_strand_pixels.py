"""Turn native strand draw G-buffer exports into exact pre/post pixel evidence."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "unreal" / "fur" / "recovered" / "ear-strand-audit"
REPORT_PATH = AUDIT / "draw-report.json"
OUTPUT_PATH = AUDIT / "pixel-report.json"


def read_rgba(path: Path, width: int, height: int) -> np.ndarray:
    raw = np.fromfile(path, dtype=np.uint8)
    expected = width * height * 4
    if raw.size != expected:
        raise ValueError(f"{path.name}: expected {expected} bytes, got {raw.size}")
    return raw.reshape((height, width, 4))


def bbox(mask: np.ndarray) -> list[int] | None:
    rows, columns = np.nonzero(mask)
    if not len(rows):
        return None
    return [int(columns.min()), int(rows.min()), int(columns.max()), int(rows.max())]


def save_rgba(path: Path, pixels: np.ndarray) -> None:
    Image.fromarray(pixels, mode="RGBA").save(path)


source = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
report = {
    "schema_version": 1,
    "capture_sha256": source["capture_sha256"],
    "events": [],
}

for event in source["events"]:
    before_meta = event.get("before_albedo")
    after_meta = event.get("albedo")
    if not before_meta or not after_meta:
        continue
    if (before_meta["width"], before_meta["height"], before_meta["format"]) != (
        after_meta["width"],
        after_meta["height"],
        after_meta["format"],
    ):
        raise ValueError(f"event {event['event']}: pre/post target layouts differ")

    width, height = after_meta["width"], after_meta["height"]
    before = read_rgba(AUDIT / before_meta["file"], width, height)
    after = read_rgba(AUDIT / after_meta["file"], width, height)
    delta = np.abs(after.astype(np.int16) - before.astype(np.int16)).astype(np.uint8)
    mask = np.any(delta != 0, axis=2)
    rgb_mask = np.any(delta[:, :, :3] != 0, axis=2)
    alpha_mask = delta[:, :, 3] != 0
    changed = int(mask.sum())

    event_id = event["event"]
    mask_rgba = np.zeros_like(after)
    mask_rgba[:, :, :3] = np.where(mask[:, :, None], 255, 0)
    mask_rgba[:, :, 3] = 255
    amplified = np.minimum(delta.astype(np.uint16) * 8, 255).astype(np.uint8)
    amplified[:, :, 3] = 255
    highlighted = after.copy()
    highlighted[:, :, :3] = np.where(
        mask[:, :, None],
        after[:, :, :3],
        after[:, :, :3] // 8,
    )
    highlighted[:, :, 3] = 255

    save_rgba(AUDIT / f"{event_id}-after.png", after)
    save_rgba(AUDIT / f"{event_id}-diff-mask.png", mask_rgba)
    save_rgba(AUDIT / f"{event_id}-diff-amplified.png", amplified)
    save_rgba(AUDIT / f"{event_id}-diff-highlight.png", highlighted)

    nonzero_delta = delta[mask]
    report["events"].append(
        {
            "event": event_id,
            "previous_event": event["previous_event"],
            "action": event["action"],
            "strand_count": next(
                buffer["strand_count"]
                for stage in event["stages"]
                for buffer in stage["buffers"]
            ),
            "scene_object_gpu": next(
                buffer["scene_object_gpu"]
                for stage in event["stages"]
                for buffer in stage["buffers"]
            ),
            "changed_pixels": changed,
            "changed_fraction": changed / (width * height),
            "rgb_changed_pixels": int(rgb_mask.sum()),
            "alpha_changed_pixels": int(alpha_mask.sum()),
            "bbox_xyxy": bbox(mask),
            "max_abs_delta_rgba": delta.reshape((-1, 4)).max(axis=0).tolist(),
            "mean_abs_delta_rgba_changed": (
                nonzero_delta.mean(axis=0).tolist() if changed else [0.0] * 4
            ),
            "artifacts": {
                "after": f"{event_id}-after.png",
                "mask": f"{event_id}-diff-mask.png",
                "amplified": f"{event_id}-diff-amplified.png",
                "highlight": f"{event_id}-diff-highlight.png",
            },
        }
    )

report["completed"] = True
OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
