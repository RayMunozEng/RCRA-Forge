"""Raster-check exact retail post-VS strand geometry against draw pixel deltas."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent
PIPELINE = ROOT / "recovered/native-strand-pipeline"
PIXELS = ROOT / "recovered/ear-strand-audit"
WIDTH, HEIGHT = 1920, 1080


def bbox(mask):
    y, x = np.nonzero(mask)
    return None if not len(x) else [int(x.min()), int(y.min()), int(x.max()), int(y.max())]


postvs = json.loads((PIPELINE / "postvs-report.json").read_text(encoding="utf-8"))
pixel_report = json.loads((PIXELS / "pixel-report.json").read_text(encoding="utf-8"))
if not postvs["completed"] or not pixel_report["completed"]:
    raise RuntimeError("Source extraction is incomplete")

result = {"schema_version": 1, "events": [], "completed": False}
for source in postvs["events"]:
    event = source["event"]
    positions = np.fromfile(PIPELINE / source["clip_file"], dtype="<f4").reshape((-1, 4))
    valid = np.abs(positions[:, 3]) > 1e-12
    screen = np.zeros((len(positions), 2), dtype=np.float64)
    ndc = positions[valid, :2] / positions[valid, 3, None]
    screen[valid, 0] = (ndc[:, 0] * 0.5 + 0.5) * WIDTH
    screen[valid, 1] = (0.5 - ndc[:, 1] * 0.5) * HEIGHT

    image = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(image)
    triangles = 0
    for index in range(2, len(positions)):
        ids = (index - 2, index - 1, index)
        if not all(valid[list(ids)]):
            continue
        points = [tuple(screen[item]) for item in ids]
        area2 = abs(
            (points[1][0] - points[0][0]) * (points[2][1] - points[0][1])
            - (points[1][1] - points[0][1]) * (points[2][0] - points[0][0]))
        if area2 <= 1e-5:
            continue
        draw.polygon(points, fill=255)
        triangles += 1
    geometry = np.asarray(image) != 0
    dilated = np.asarray(image.filter(ImageFilter.MaxFilter(3))) != 0
    native = np.asarray(Image.open(PIXELS / f"{event}-diff-mask.png").convert("L")) > 128
    native_count = int(native.sum())
    contained = int((native & dilated).sum())
    geometry_name = f"e{event}-postvs-raster.png"
    image.save(PIPELINE / geometry_name)
    event_result = {
        "event": event,
        "triangle_strip_non_degenerate_triangles": triangles,
        "geometry_pixels": int(geometry.sum()),
        "geometry_bbox_xyxy": bbox(geometry),
        "native_changed_pixels": native_count,
        "native_changed_bbox_xyxy": bbox(native),
        "native_changed_pixels_inside_1px_geometry": contained,
        "native_changed_containment": contained / max(native_count, 1),
        "geometry_mask": geometry_name,
    }
    event_result["passed"] = (
        native_count > 0 and event_result["native_changed_containment"] >= 0.95)
    result["events"].append(event_result)

result["completed"] = True
result["passed"] = all(row["passed"] for row in result["events"])
(PIPELINE / "postvs-analysis.json").write_text(
    json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
if not result["passed"]:
    raise SystemExit(1)
