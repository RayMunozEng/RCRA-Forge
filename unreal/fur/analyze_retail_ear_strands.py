"""Quantify strand coverage and dynamics against a duplicate-dry TAA baseline."""

import json
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parent
CAPTURE = ROOT / "recovered/retail-ear-strands"
SOURCE_REPORT = CAPTURE / "report.json"
OUTPUT = CAPTURE / "analysis.json"
NAMES = [
    "shell-only", "combined-dry-a", "combined-dry-b",
    "combined-wind-a", "combined-wind-b", "combined-wind-turned",
    "combined-wet"]

source = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))
if [row["label"] for row in source["captures"]] != NAMES:
    raise RuntimeError("Capture sequence is incomplete or stale")
images = {
    name: np.asarray(Image.open(CAPTURE / (name + ".png")).convert("RGB"), dtype=np.int16)
    for name in NAMES
}


def compare(before, after):
    delta = np.abs(images[before] - images[after])
    maximum = delta.max(axis=2)
    return {
        "before": before,
        "after": after,
        "mean_absolute_rgb8": float(delta.mean()),
        "pixels_over_2": int((maximum > 2).sum()),
        "pixels_over_8": int((maximum > 8).sum()),
        "max_rgb8": int(maximum.max()),
    }


coverage = compare("shell-only", "combined-dry-a")
dry_baseline = compare("combined-dry-a", "combined-dry-b")
wind_on = compare("combined-dry-b", "combined-wind-a")
wind_continuous = compare("combined-wind-a", "combined-wind-b")
wind_turned = compare("combined-wind-b", "combined-wind-turned")
wet = compare("combined-wind-turned", "combined-wet")
response_pairs = [wind_on, wind_turned, wet]
baseline = max(dry_baseline["pixels_over_8"], 1)
analysis = {
    "source_event": source["source_event"],
    "source_buffer_event": source["source_buffer_event"],
    "authored_guides": source["authored_guides"],
    "rendered_ribbons": source["rendered_ribbons"],
    "coverage": coverage,
    "dry_temporal_baseline": dry_baseline,
    "responses": response_pairs,
    "steady_state": wind_continuous,
    "minimum_response_to_baseline_ratio": min(
        row["pixels_over_8"] / baseline for row in response_pairs),
}
analysis["passed"] = (
    coverage["pixels_over_8"] > 1000
    and all(row["pixels_over_8"] > dry_baseline["pixels_over_8"] * 1.25
            for row in response_pairs)
)
OUTPUT.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
print(json.dumps(analysis, indent=2))
if not analysis["passed"]:
    raise SystemExit(1)
