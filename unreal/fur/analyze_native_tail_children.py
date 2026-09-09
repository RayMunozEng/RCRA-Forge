"""Solve retail tail child-clump and stray coefficients from captured post-VSS."""

import json
from pathlib import Path
import struct

import numpy as np


ROOT = Path(__file__).resolve().parent
PIPELINE = ROOT / "recovered/native-strand-pipeline"
GUIDES = json.loads(
    (PIPELINE / "ratchet-tail-guides-bind-visible.json").read_text(encoding="utf-8"))

guide_count = 463
children = 35
tessellation = 11
vertices_per_child = tessellation * 4
expected_vertices = guide_count * children * vertices_per_child

matrix = np.fromfile(
    PIPELINE / "e24825-Vertex-b0.bin", dtype="<f4", count=16, offset=64).reshape(4, 4)
clips = np.fromfile(PIPELINE / "e24825-postvs-clip-float4.bin", dtype="<f4").reshape(-1, 4)
assert len(clips) == expected_vertices, (len(clips), expected_vertices)
inverse = np.linalg.inv(matrix.astype(np.float64))
scene = np.fromfile(
    PIPELINE / "e24762-SceneObjectGpu.bin", dtype="<f4", count=12).reshape(3, 4)
strand_buffer = (
    PIPELINE / "e24825-Vertex-t5-StrandBuffer.bin").read_bytes()
cv_buffer = (
    PIPELINE / "e24825-Vertex-t6-StrandCVBuffer.bin").read_bytes()
model_cbuffer = (
    PIPELINE / "e24825-Vertex-b5.bin").read_bytes()
meters_per_unit = struct.unpack_from("<f", model_cbuffer, 32)[0]
world_h = clips.astype(np.float64) @ inverse
valid = np.isfinite(clips[:, 3]) & (np.abs(clips[:, 3]) > 1.0e-10)
world_h[valid] /= world_h[valid, 3][:, None]
world = world_h[:, :3].reshape(guide_count, children, tessellation, 4, 3)
valid_layout = valid.reshape(guide_count, children, tessellation, 4)
assert valid_layout[:, :, 1:-1, :].all()
assert not valid_layout[:, :, 0, :].any()
assert not valid_layout[:, :, -1, :].any()

child_i = np.arange(children, dtype=np.int32)
child = child_i.astype(np.float32)
angle = np.float32(child * np.float32(2.39996))
radius = np.sqrt(
    np.float32((child + np.float32(1.0)) / np.float32(children)),
    dtype=np.float32)
radial_cos = np.float32(np.cos(angle) * radius).astype(np.float64)
radial_sin = np.float32(np.sin(angle) * radius).astype(np.float64)


def oct_decode(x_byte, y_byte):
    x = x_byte * (2.0 / 255.0) - 1.0
    y = y_byte * (2.0 / 255.0) - 1.0
    z = 1.0 - abs(x) - abs(y)
    fold = max(-z, 0.0)
    x += -fold if x >= 0.0 else fold
    y += -fold if y >= 0.0 else fold
    vector = np.asarray((x, z, y), dtype=np.float64)
    return vector / np.linalg.norm(vector)


def signed16(value):
    return value - 65536 if value & 0x8000 else value


def unpack_position(index):
    xy, z_flags = struct.unpack_from("<II", cv_buffer, index * 8)
    return np.asarray((signed16(xy & 0xffff), signed16(xy >> 16),
                       signed16(z_flags & 0xffff)), dtype=np.float64) * meters_per_unit


def sample_guide(source_index, along):
    word0, _, _ = struct.unpack_from("<III", strand_buffer, source_index * 12)
    count, start = word0 >> 24, word0 & 0xffffff
    position = np.clip(along, 0.0, 1.0) * (count - 1)
    knot = int(np.floor(position))
    t = position - knot
    indices = [min(max(knot + delta, 0), count - 1) + start
               for delta in (-1, 0, 1, 2)]
    p0, p1, p2, p3 = [unpack_position(index) for index in indices]
    t2, t3 = t * t, t * t * t
    spline = (p0 * (1 - 3*t + 3*t2 - t3)
              + p1 * (4 - 6*t2 + 3*t3)
              + p2 * (1 + 3*t + 3*t2 - 3*t3)
              + p3 * t3) / 6.0
    end_weight = 1.0 - np.clip(count - position, 0.0, 1.0)
    end_corrected = spline * (1.0 - end_weight) + (
        p0 * (1.0 - t) + p1 * t) * end_weight
    start_weight = 1.0 - np.clip(position, 0.0, 1.0)
    return end_corrected * (1.0 - start_weight) + (
        p1 * (1.0 - t) + p2 * t) * start_weight

rows = []
constrained_scales = []
frame_alignments = []
center_replay_errors = {"scene_row_dot": [], "scene_column_dot": []}
for guide_index, guide in enumerate(GUIDES["guides"]):
    source_index = int(guide["source_strand_index"])
    # Preserve the DXIL shader's float32 rounding at every operation. This
    # hash is intentionally chaotic enough that a float64 rewrite produces a
    # different child distribution even though the source formula looks equal.
    hash_base = np.float32(
        np.float32(source_index + child_i) * np.float32(0.318310)
        + np.float32(0.1))
    hash_base = np.float32(hash_base - np.floor(hash_base))
    hash_times_three = np.float32(hash_base * np.float32(3.0))
    stray_random = np.float32(hash_base * hash_base)
    stray_random = np.float32(stray_random * np.float32(83521.0))
    stray_random = np.float32(stray_random * hash_base)
    stray_random = np.float32(stray_random * hash_times_three)
    stray_random = np.float32(stray_random - np.floor(stray_random))
    with np.errstate(divide="ignore"):
        stray_hash = np.exp2(np.float32(
            np.log2(stray_random) * np.float32(4.481430530548096)),
            dtype=np.float32)
    stray_hash = np.where(stray_random > 0.0, stray_hash, 0.0).astype(np.float64)
    # Use the post-skinning axes consumed by this draw, not the bind-pose axes
    # exported in the durable UE fixture. The shader's octahedral decode emits
    # (x, z, y), exactly as reproduced here.
    _, _, packed_axes = struct.unpack_from(
        "<III", strand_buffer, source_index * 12)
    normal_forge = oct_decode(packed_axes & 0xff, (packed_axes >> 8) & 0xff)
    frame_y_forge = oct_decode(
        (packed_axes >> 16) & 0xff, (packed_axes >> 24) & 0xff)
    frame_x = scene[:, :3] @ normal_forge
    frame_y = scene[:, :3] @ frame_y_forge
    frame_x /= np.linalg.norm(frame_x)
    frame_y /= np.linalg.norm(frame_y)
    design = np.column_stack((
        np.ones(children), radial_cos, radial_sin,
        radial_cos * stray_hash, radial_sin * stray_hash))
    for step in range(1, tessellation - 1):
        along = (step - 1) / (tessellation - 3)
        centers = world[guide_index, :, step].mean(axis=1)
        guide_center = sample_guide(source_index, along)
        # The regression intercept removes the analytically varying child
        # clump/stray distribution; a raw child mean is biased because the
        # finite golden-angle disk does not sum to zero.
        center_coefficients, _, _, _ = np.linalg.lstsq(design, centers, rcond=None)
        observed_center = center_coefficients[0]
        for label, transformed in (
                ("scene_row_dot", scene[:, :3] @ guide_center + scene[:, 3]),
                ("scene_column_dot", guide_center @ scene[:, :3] + scene[:, 3])):
            # Translation cancels when comparing shape relative to each
            # guide's first sample, avoiding any camera-origin ambiguity.
            if step == 1:
                guide["_observed_root"] = observed_center
                guide["_predicted_root_" + label] = transformed
            observed_delta = observed_center - guide["_observed_root"]
            predicted_delta = transformed - guide["_predicted_root_" + label]
            center_replay_errors[label].append(float(
                np.linalg.norm(observed_delta - predicted_delta)))
        simple = 0.015 * along * 3.0
        if simple > 0.0:
            for axis_name, frame, coefficient_index in (
                    ("x", frame_x, 3), ("y", frame_y, 4)):
                projected = centers @ frame
                # Include both clump-frame components in one solve; fitting a
                # single projected radial term aliases the other axis whenever
                # the captured object transform is not perfectly orthogonal.
                oriented_design = design.copy()
                oriented_coefficients, _, _, _ = np.linalg.lstsq(
                    oriented_design, projected, rcond=None)
                oriented_prediction = oriented_design @ oriented_coefficients
                constrained_scales.append({
                    "guide": guide_index,
                    "step": step,
                    "axis": axis_name,
                    "scale": float(oriented_coefficients[coefficient_index] / simple),
                    "maximum_residual": float(
                        np.max(np.abs(projected - oriented_prediction))),
                })
        coefficients, _, _, _ = np.linalg.lstsq(design, centers, rcond=None)
        predicted = design @ coefficients
        residual = np.linalg.norm(centers - predicted, axis=1)
        base_x = float(np.linalg.norm(coefficients[1]))
        base_y = float(np.linalg.norm(coefficients[2]))
        stray_x = float(np.linalg.norm(coefficients[3]))
        stray_y = float(np.linalg.norm(coefficients[4]))
        for label, coefficient, frame in (
                ("base_x", coefficients[1], frame_x),
                ("base_y", coefficients[2], frame_y),
                ("stray_x", coefficients[3], frame_x),
                ("stray_y", coefficients[4], frame_y)):
            magnitude = np.linalg.norm(coefficient)
            if magnitude > 1.0e-12:
                frame_alignments.append({
                    "label": label,
                    "step": step,
                    "cosine": float(np.dot(coefficient, frame) / magnitude),
                })
        divided_x = simple / max(base_x, 1.0e-10)
        divided_y = simple / max(base_y, 1.0e-10)
        rows.append({
            "guide": guide_index,
            "source_strand_index": source_index,
            "step": step,
            "along": along,
            "base_x": base_x,
            "base_y": base_y,
            "stray_x": stray_x,
            "stray_y": stray_y,
            "simple_expected": simple,
            "divided_x_expected": divided_x,
            "divided_y_expected": divided_y,
            "maximum_fit_residual": float(residual.max()),
        })

active = [row for row in rows if row["along"] > 0.0]
simple_errors = np.array([
    abs(row[axis] - row["simple_expected"])
    for row in active for axis in ("stray_x", "stray_y")])
divided_errors = np.array([
    abs(row[axis] - row[expected])
    for row in active
    for axis, expected in (("stray_x", "divided_x_expected"),
                           ("stray_y", "divided_y_expected"))])
scale_values = np.asarray([row["scale"] for row in constrained_scales])
alignment_summary = {}
for label in ("base_x", "base_y", "stray_x", "stray_y"):
    values = np.asarray([
        row["cosine"] for row in frame_alignments if row["label"] == label])
    alignment_summary[label] = [
        float(value) for value in np.quantile(values, [0.1, 0.5, 0.9])]
center_replay_summary = {
    label: {
        "median_metres": float(np.median(values)),
        "p90_metres": float(np.quantile(values, 0.9)),
        "maximum_metres": float(np.max(values)),
    }
    for label, values in center_replay_errors.items()
}
report = {
    "schema_version": 1,
    "source_event": 24825,
    "source_postvs_sha256": "02794becfbd8d9034d22951727fa5892b9910c81802c2179c9921dbded0fb7ef",
    "guide_work_items": guide_count,
    "children_per_guide": children,
    "tessellation": tessellation,
    "projectable_vertices": int(valid.sum()),
    "simple_candidate_median_absolute_error": float(np.median(simple_errors)),
    "divided_candidate_median_absolute_error": float(np.median(divided_errors)),
    "simple_candidate_mean_absolute_error": float(np.mean(simple_errors)),
    "divided_candidate_mean_absolute_error": float(np.mean(divided_errors)),
    "maximum_regression_residual": max(row["maximum_fit_residual"] for row in rows),
    "frame_constrained_stray_scale_median": float(np.median(scale_values)),
    "frame_constrained_stray_scale_quantiles": [
        float(value) for value in np.quantile(scale_values, [0.1, 0.5, 0.9])],
    "frame_constrained_maximum_residual": max(
        row["maximum_residual"] for row in constrained_scales),
    "frame_alignment_cosine_quantiles": alignment_summary,
    "guide_center_replay": center_replay_summary,
    "winner": "simple" if np.median(simple_errors) < np.median(divided_errors) else "divided",
    "samples": rows,
}
(PIPELINE / "tail-child-offset-analysis.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key != "samples"}, indent=2))
