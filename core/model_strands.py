"""Capture-derived Ratchet ModelStrand ribbon reconstruction.

The private fixtures are validation evidence from a user-owned retail capture.
They are loaded only for Ratchet's known model and are never required for other
Forge assets.  Coordinates are converted back from the decoder's UE-centimetre
diagnostic convention to Forge metres.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import struct

import numpy as np


RATCHET_MODEL_TOKEN = "hero_ratchet"


@dataclass(frozen=True)
class StrandProfile:
    name: str
    children: int
    tessellation: int
    reflectance: float
    strand: tuple[tuple[float, float], ...]
    clump_x: tuple[tuple[float, float], ...]
    clump_y: tuple[tuple[float, float], ...]
    stray_power: float
    stray_strength: float


PROFILES = {
    "ears": StrandProfile(
        "ears", 2, 8, 0.2140340954065323,
        ((0.0, 0.0), (0.23989396, 0.0010498867),
         (0.67051762, 0.00059640512), (1.0, 0.0)),
        ((0.0, 0.005), (0.16185364, 0.005),
         (0.59183431, 0.0029285715), (1.0, 0.001)),
        ((0.0, 0.005), (0.16185364, 0.005),
         (0.59183431, 0.0027142859), (1.0, 0.0012857143)),
        100.0, 0.0,
    ),
    "head-sparse": StrandProfile(
        "head-sparse", 11, 11, 0.21768173575401306,
        ((0.0, 0.0), (0.30419964, 0.00090624543),
         (0.67051762, 0.00053067307), (1.0, 0.0)),
        ((0.0, 0.008), (0.16248856, 0.008),
         (0.60707247, 0.008), (1.0, 0.008)),
        ((0.0, 0.008), (0.16248856, 0.008),
         (0.60707247, 0.008), (1.0, 0.008)),
        100.0, 0.0,
    ),
    "tail": StrandProfile(
        "tail", 35, 11, 0.18269199132919312,
        ((0.0, 0.0019955141), (0.30419964, 0.0018866096),
         (0.67051762, 0.0010605373), (1.0, 0.0)),
        ((0.0, 0.015), (0.16185364, 0.015),
         (0.53277129, 0.0083571430), (1.0, 0.0006428574)),
        ((0.0, 0.015), (0.16185364, 0.015),
         (0.53277129, 0.0083571430), (1.0, 0.0008571431)),
        4.481430530548096, 3.0,
    ),
}


FIXTURES = {
    "tail": "ratchet-tail-guides-bind-visible.json",
    "head-sparse": "ratchet-head-sparse-guides-bind-visible.json",
    "ears": "ratchet-ear-guides-bind-visible.json",
}

CAPTURED_WIND_BUFFERS = {
    "tail": ("e24743-Compute-u0-StrandCVBufferOutput.bin",
             "e24762-Compute-u0-StrandCVBufferOutput.bin"),
    "head-sparse": ("e24748-Compute-u0-StrandCVBufferOutput.bin",
                    "e24767-Compute-u0-StrandCVBufferOutput.bin"),
    "ears": ("e24756-Compute-u0-StrandCVBufferOutput.bin",
             "e24775-Compute-u0-StrandCVBufferOutput.bin"),
}
CAPTURED_WIND_STRENGTH = 0.03709043934941292
CAPTURED_WIND_TIME = 981.7157592773438
PACKED_METRES = 0.000244140625


def _curve(points: tuple[tuple[float, float], ...], value: float) -> float:
    value = min(max(float(value), 0.0), 1.0)
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            q = (value - x0) / max(x1 - x0, 1e-12)
            return y0 + (y1 - y0) * q
    return points[-1][1]


def _sample_guide(points: np.ndarray, fraction: float) -> np.ndarray:
    """Match StrandGroomActor's endpoint-corrected uniform cubic B-spline."""
    count = len(points)
    if count == 1:
        return points[0].copy()
    position = min(max(float(fraction), 0.0), 1.0) * (count - 1)
    knot = int(np.floor(position))
    t = position - knot
    p0 = points[min(max(knot - 1, 0), count - 1)]
    p1 = points[min(max(knot, 0), count - 1)]
    p2 = points[min(max(knot + 1, 0), count - 1)]
    p3 = points[min(max(knot + 2, 0), count - 1)]
    t2, t3 = t * t, t * t * t
    spline = (
        p0 * (1.0 - 3.0 * t + 3.0 * t2 - t3)
        + p1 * (4.0 - 6.0 * t2 + 3.0 * t3)
        + p2 * (1.0 + 3.0 * t + 3.0 * t2 - 3.0 * t3)
        + p3 * t3
    ) / 6.0
    end_weight = 1.0 - min(max(count - position, 0.0), 1.0)
    end_corrected = spline * (1.0 - end_weight) + (p0 * (1.0 - t) + p1 * t) * end_weight
    start_weight = 1.0 - min(max(position, 0.0), 1.0)
    return end_corrected * (1.0 - start_weight) + (p1 * (1.0 - t) + p2 * t) * start_weight


def _ue_to_forge_position(values) -> np.ndarray:
    x, y, z = values
    return np.asarray((x, z, y), dtype=np.float32) * 0.01


def _ue_to_forge_vector(values) -> np.ndarray:
    x, y, z = values
    result = np.asarray((x, z, y), dtype=np.float32)
    length = float(np.linalg.norm(result))
    return result / length if length > 1e-12 else result


def _packed_position(raw: bytes, index: int) -> np.ndarray:
    xy, z_flags = struct.unpack_from("<II", raw, index * 8)
    values = (xy & 0xFFFF, xy >> 16, z_flags & 0xFFFF)
    signed = [value - 65536 if value & 0x8000 else value for value in values]
    return np.asarray(signed, dtype=np.float32) * PACKED_METRES


@lru_cache(maxsize=3)
def _captured_wind_inputs(profile_name: str) -> tuple[bytes, bytes, bytes]:
    root = fixture_directory()
    skinned_name, wind_name = CAPTURED_WIND_BUFFERS[profile_name]
    strand_name = {
        "tail": "e24743-Compute-t5-StrandBuffer.bin",
        "head-sparse": "e24748-Compute-t5-StrandBuffer.bin",
        "ears": "e24756-Compute-t5-StrandBuffer.bin",
    }[profile_name]
    return (
        (root / skinned_name).read_bytes(),
        (root / wind_name).read_bytes(),
        (root / strand_name).read_bytes(),
    )


def _captured_wind_delta(profile_name: str, guide: dict) -> list[np.ndarray]:
    """Exact captured wind-only delta, excluding the gameplay skeletal pose."""
    skinned, wind, strand = _captured_wind_inputs(profile_name)
    # The decoded guide retains the authored source record index. Its word0
    # provides the global CV start used by both post-skinning and wind buffers.
    source_index = int(guide["source_strand_index"])
    word0 = struct.unpack_from("<I", strand, source_index * 12)[0]
    cv_start = word0 & 0x00FFFFFF
    count = (word0 >> 24) & 0x7F
    if count != len(guide["control_vertices_cm"]):
        raise ValueError("Captured ModelStrand CV count changed between evidence buffers")
    return [
        _packed_position(wind, cv_start + index)
        - _packed_position(skinned, cv_start + index)
        for index in range(count)
    ]


def fixture_directory() -> Path:
    return Path(__file__).resolve().parents[1] / "unreal/fur/recovered/native-strand-pipeline"


def ratchet_strand_fixtures_available(source_path: str) -> bool:
    return (
        RATCHET_MODEL_TOKEN in (source_path or "").lower()
        and all((fixture_directory() / name).is_file() for name in FIXTURES.values())
    )


def build_group(profile_name: str, *, captured_wind: bool = False) -> tuple[np.ndarray, np.ndarray, dict]:
    """Return interleaved ribbon vertices, indices, and an evidence summary.

    Vertex layout is 22 float32 values:
    position3, root-normal3, curve-tangent3, frame-y3, root-uv2,
    curve(thickness/clump-x/clump-y/along)4, ids(child/guide/side/width)4.
    """
    profile = PROFILES[profile_name]
    path = fixture_directory() / FIXTURES[profile_name]
    document = json.loads(path.read_text(encoding="utf-8"))
    guides = document["guides"]
    live_sample_count = profile.tessellation - 2
    vertices_per_render_guide = profile.tessellation * 4
    render_guides = len(guides) * profile.children
    vertices = np.empty((render_guides * vertices_per_render_guide, 22), np.float32)
    # Retail is one non-indexed triangle strip. Its zero-W endpoint sentinels
    # terminate each child ribbon. OpenGL zero-W behavior is undefined, so use
    # fixed-index primitive restart for the same strip partition explicitly.
    indices = np.empty((render_guides * (vertices_per_render_guide + 1) - 1,), np.uint32)
    vertex_cursor = index_cursor = render_guide = 0
    for guide_index, guide in enumerate(guides):
        points = np.asarray([
            _ue_to_forge_position(point) for point in guide["control_vertices_cm"]
        ], dtype=np.float32)
        if captured_wind:
            points += np.asarray(_captured_wind_delta(profile_name, guide), np.float32)
        normal = _ue_to_forge_vector(guide["root_normal"])
        frame_y = _ue_to_forge_vector(guide["root_frame_y"])
        root_uv = np.asarray(guide["packed_uv_or_seed"], dtype=np.float32)
        samples = []
        for step in range(live_sample_count):
            along = step / (live_sample_count - 1)
            delta = 1.0 / (live_sample_count - 1)
            position = _sample_guide(points, along)
            before = _sample_guide(points, max(0.0, along - delta))
            after = _sample_guide(points, min(1.0, along + delta))
            tangent = after - before
            tangent /= max(float(np.linalg.norm(tangent)), 1e-12)
            samples.append((along, position, tangent, False))
        # The captured VS emits four invocations for two endpoint sentinels in
        # addition to the tessellation-2 spatial samples.
        samples = [(*samples[0][:3], True), *samples, (*samples[-1][:3], True)]
        for child in range(profile.children):
            base = render_guide * vertices_per_render_guide
            for step, (along, position, tangent, sentinel) in enumerate(samples):
                curve_values = (
                    0.0 if sentinel else _curve(profile.strand, along),
                    _curve(profile.clump_x, along),
                    _curve(profile.clump_y, along),
                    along,
                )
                for _pair in range(2):
                    for side in range(2):
                        vertices[vertex_cursor] = np.concatenate((
                            position, normal, tangent, frame_y, root_uv,
                            np.asarray(curve_values, np.float32),
                            np.asarray((child, guide_index, side, 1.0), np.float32),
                        ))
                        vertex_cursor += 1
            indices[index_cursor:index_cursor + vertices_per_render_guide] = np.arange(
                base, base + vertices_per_render_guide, dtype=np.uint32,
            )
            index_cursor += vertices_per_render_guide
            if render_guide + 1 < render_guides:
                indices[index_cursor] = np.uint32(0xFFFFFFFF)
                index_cursor += 1
            render_guide += 1
    summary = {
        "group": profile_name,
        "guides": len(guides),
        "children": profile.children,
        "tessellation": profile.tessellation,
        "draw_vertices": int(len(vertices)),
        "live_projectable_vertices": int(
            render_guides * live_sample_count * 4
        ),
        "ribbon_indices": int(len(indices)),
        "source_event": document.get("source_event"),
        "source_capture_sha256": document.get("source_capture_sha256"),
        "dynamics": (
            "captured_wind_only_delta_excluding_gameplay_skinning"
            if captured_wind else "bind_pose"
        ),
    }
    return vertices, indices, summary
