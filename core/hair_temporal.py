"""Stable CPU-side constants recovered from Rift Apart's TAA builder."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import math
import struct


_DITHER_TABLE_BYTES = base64.b64decode(
    "vHTzPpm7ljygiXA/s3tiPwU08T43iUE/SZ2gPu58/z7G3EU/GXOXPozbGD8QWLk9"
    "RrZzPtcSEj/M7lk/x0sXPzC7dz9qvGQ/DeCtPl66KT+HFhk/okUGPwmKPz+qYEQ/"
    "Xdx2Pz55uD6adzw/cM7IPvCFyT6giUA/zqovPzvffz8LJMg+OiMaP8UgsD55WKg+"
    "ZMw9Pwn5ID7A7H4/mN1jP4qO5DxX7E8/vePUPlafqz4BTcQ+taZJP3GsWz9cIME9"
    "VFKHPkHxQz8kKJ4+FD/mPucdJz17FK4+ArwVP44GYD+0yNY+/7K7PsuhxT0PC0U/"
    "qz4XP5zE4D4tsn0/EFi5PmIQGD7ImCs/Ke1NP9qsSj81Xno/jLlrP2Dl8D6NKG0/"
    "Zvd0P18HTj/hC5M9u7hNPwdfaD8W+8s8cvmPPTJ3rT1qTfM8Dk8vPV3cxj2lvcE+"
    "MQgsP7FQ6z1PHmY/hJ4NP68l5D0eFso+si7OPptVXz6lvUE9zF3LPVg5ND9SSV0+"
    "D5xDP6H4ET+itBc/QBMhPnzycD6jAdw+n82qPjeJoT7D9Qg/f2q8PfMfUj1pb5A+"
    "F7dROdV4iT6cxMA+kxgUP4GVYz/67as+1JrmPWaIoz6J0t48B/BmP+2e/D4Xt1E8"
    "W7EvP0XYcD49Clc+eJwiPpp3nD1/+wo/5q4VPzVeGj80gLc7U5bBPqabFD+giTA9"
    "/BjzPj7ouT5MN4k9guIHPn9qfD46I0o/FD92PySX/z1aZBs/VTCKPgrXoz7l0FI/"
    "toT8PkmdAD+4HhU/aCJMP1jKMj9y+V8/cM44P11txT7XNA8/uK8DPzGZij7eAgk/"
    "54w4P8DsPj/D9Rg/PzVuP240AD7NzGw/Vg5tP7KdLz9DHHs/8WPMPrMMYT9Ivy0/"
    "PQoHP15L6D7o2Uw/pb0BP9V4yT6IY10++Q8pPpqZuT50JHc/JCjePoxKyj6b5r0+"
    "cRsdPw4t8j6ze/I7aCJMP1jKMj9WDs0+wTmjPkaUBj/67Ws9000iPm+BND+sHCo/"
    "qoKRPvCnZj/Oqu8+f9l9Pjoj6j5n1Uc/i/3lPWQ7bz8j2/k8xm30PoofEz9FRyI/"
    "ApoIPqH4YT9xrAs/FK7HPrU3uD5YyrI993VQP7n8BzxSST0/wcrhPvwYcz5YOVQ/"
    "5IMePQfwtj4oD4s+bHg6PilcDz35oAc/2htsP6pg1D0gYz4/IR90Pm3nez7SAN4+"
    "K/Z3Pw6+YD+oV8o9R3L5Pl8HDj6QMUc/EhQPPygPCz50JJc924q9Pq7Yvz6At6A+"
    "D5yzPl1tBT4tQ5w9Xf4TP6K0Jz8dyaU+ZojjPcPTyz7dJMY+UI0XPSL91j4Uroc+"
    "Xdw2PzeJ4T4H8HY/tTd4PQ=="
)
DITHER_TABLE_SHA256 = (
    "5747b412a83d10e7430385c2c20b548d5f2b63558993e5b9aa159486f689e328"
)
if len(_DITHER_TABLE_BYTES) != 256 * 4:
    raise RuntimeError("recovered TAA dither table has the wrong size")
if hashlib.sha256(_DITHER_TABLE_BYTES).hexdigest() != DITHER_TABLE_SHA256:
    raise RuntimeError("recovered TAA dither table hash mismatch")

TEMPORAL_DITHER_TABLE = struct.unpack("<256f", _DITHER_TABLE_BYTES)
_DITHER_RED_GREEN = struct.unpack("<f", bytes.fromhex("610b363c"))[0]
_DITHER_BLUE = struct.unpack(
    "<f", struct.pack("<f", _DITHER_RED_GREEN + _DITHER_RED_GREEN)
)[0]
TEMPORAL_NONOPAQUE_RESPONSE_FALLBACK = struct.unpack(
    "<f", bytes.fromhex("0ad7233d")
)[0]
TEMPORAL_MINIMUM_REJECTION_FLOOR = struct.unpack(
    "<f", bytes.fromhex("0000803d")
)[0]
TEMPORAL_CONDITIONAL_REJECTION_FLOOR = struct.unpack(
    "<f", bytes.fromhex("cdcccc3d")
)[0]
TEMPORAL_APPLY_CBUFFER_SIZE = 224
TEMPORAL_APPLY_SHADER_SHA256 = (
    "b892667bfa835a95a7f58c78b30b35d45e5784b48d750bf6543bf557d9956e0f"
)
TEMPORAL_APPLY_BINDINGS = (
    ("t5", "g_TemporalAaCurrentTex", "R11G11B10_FLOAT"),
    ("t6", "g_TemporalAaHistoryTex", "R11G11B10_FLOAT"),
    ("t7", "g_TemporalAaVelocityTex", "R16G16_FLOAT"),
    ("t8", "g_TemporalAaDisocclTex", "R8G8_UNORM"),
    ("t9", "g_TemporalAaStencilTex", "D32S8"),
    ("t10", "g_TemporalAaMaskTex", "R8_UNORM"),
    ("t11", "g_TemporalAaLinearDepth", "R16_FLOAT"),
    ("u0", "g_TemporalAaOutput", "R11G11B10_FLOAT"),
)
TEMPORAL_DISOCCLUSION_SHADER_SHA256 = (
    "5b4710e1aa9806872423d16b5a66bfa8755ee3269bd07685888b808d7b31cc97"
)
TEMPORAL_DISOCCLUSION_BINDINGS = (
    ("t5", "g_TemporalAaDisocclLinearDepth", "R16_FLOAT"),
    ("t6", "g_TemporalAaDisocclVelocityTex", "R16G16_FLOAT"),
    ("t7", "g_TemporalAaDisocclHistDepthTex", "R16G16_FLOAT"),
    ("t8", "g_TemporalAaDisocclScatterTex", "R8_UNORM"),
    ("u0", "g_TemporalAaDisocclFullOutput", "R8G8_UNORM"),
    ("u1", "g_TemporalAaDepthVelOutput", "R16G16_FLOAT"),
)
TEMPORAL_DISOCCLUSION_HALF_SHADER_SHA256 = (
    "afad553b7bdab5011e9acc6a61e7818abb723c06f986243e478239b61740a9a8"
)
TEMPORAL_DISOCCLUSION_HALF_BINDINGS = (
    ("t5", "g_TemporalAaDisocclFullResTex", "R8G8_UNORM"),
    ("u0", "g_TemporalAaDisocclHalfOutput", "R8_UNORM"),
)
TEMPORAL_DISOCCLUSION_CAPTURE_DEPTH_BASE = struct.unpack(
    "<f", bytes.fromhex("00000041")
)[0]
TEMPORAL_DISOCCLUSION_CAPTURE_DEPTH_SLOPE = struct.unpack(
    "<f", bytes.fromhex("0100d741")
)[0]
TEMPORAL_DISOCCLUSION_CAPTURE_MOTION_THRESHOLD = struct.unpack(
    "<f", bytes.fromhex("0000803f")
)[0]
TEMPORAL_ACC_ALPHA_MOTION_THRESHOLD = struct.unpack(
    "<f", bytes.fromhex("abaa2a3f")
)[0]
TEMPORAL_ACC_ALPHA_HALF_MASK_SHADER_SHA256 = (
    "a7f48ebde450132e5eccf52f3161001bd464d74a459ab234fcbe632b641349d7"
)
TEMPORAL_ACC_ALPHA_HALF_MASK_BINDINGS = (
    ("t5", "g_AccAlphaDepthFull", "R16_FLOAT"),
    ("t6", "g_AccAlphaDepthHalf", "R16_FLOAT"),
    ("u0", "g_AccAlphaFlagsOutput", "R8_UNORM"),
)
TEMPORAL_ACC_ALPHA_WORK_QUEUE_SHADER_SHA256 = (
    "4c6def4e3af247418b546dd581cf971bd93fc274e3c1163a892f6ec8da3729b1"
)
TEMPORAL_ACC_ALPHA_WORK_QUEUE_BINDINGS = (
    ("t5", "g_AccAlphaFlagsTex", "R8_UNORM"),
    ("u0", "g_AccAlphaWorkQueue", "APPEND_UINT_BUFFER"),
)
TEMPORAL_ACC_ALPHA_DISOCCLUSION_SHADER_SHA256 = (
    "3325938addce04cf33c1d7d66bc6b22d8c7bd539715ec870a090707d04aee605"
)
TEMPORAL_ACC_ALPHA_DISOCCLUSION_BINDINGS = (
    *TEMPORAL_DISOCCLUSION_BINDINGS[:4],
    ("t9", "g_AccAlphaWorkBuffer", "BUFFER"),
    ("t10", "g_AccAlphaDisocclFlagsTex", "R8_UNORM"),
    *TEMPORAL_DISOCCLUSION_BINDINGS[4:],
)
TEMPORAL_ACC_ALPHA_HALF_SHADER_SHA256 = (
    "f702297bceb7df68c195b3655bf6d24beb75bb9d998a2da3f49644cb911bd5e7"
)
TEMPORAL_ACC_ALPHA_HALF_BINDINGS = (
    ("t9", "g_AccAlphaWorkBuffer", "BUFFER"),
    ("t5", "g_AccAlphaDisocclFullTex", "R8G8_UNORM"),
    ("t6", "g_AccAlphaDepthFullTex", "R16_FLOAT"),
    ("t7", "g_AccAlphaVelocityFullTex", "R16G16_FLOAT"),
    ("u0", "g_AccAlphaDisocclHalfOutput", "R8_UNORM"),
    ("u1", "g_AccAlphaVelHalfOutput", "R16G16_FLOAT"),
    ("u2", "g_AccAlphaMaxDepthOutput", "R16_FLOAT"),
    ("u3", "g_AccAlphaMinDepthOutput", "R16_FLOAT"),
)


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _f32_sum(values: tuple[float, ...] | list[float]) -> float:
    result = _f32(0.0)
    for value in values:
        result = _f32(result + value)
    return result


def _temporal_catmull_weight(distance: float) -> float:
    distance = _f32(abs(_f32(distance)))
    squared = _f32(distance * distance)
    cubed = _f32(squared * distance)
    if distance < 1.0:
        return _f32(_f32(1.0 - _f32(2.5 * squared)) + _f32(1.5 * cubed))
    return _f32(
        _f32(_f32(2.0 - _f32(4.0 * distance)) + _f32(2.5 * squared))
        - _f32(0.5 * cubed)
    )


def temporal_filter_weights(
    offset_pixels: tuple[float, float],
) -> tuple[float, ...]:
    """Return the native float32 Gaussian/Catmull 3x3 filter weights."""
    offset_x, offset_y = (_f32(value) for value in offset_pixels)
    gaussian: list[float] = []
    catmull: list[float] = []
    for y in range(-1, 2):
        dy = _f32(_f32(y) - offset_y)
        for x in range(-1, 2):
            dx = _f32(_f32(x) - offset_x)
            radius = _f32(_f32(dx * dx) + _f32(dy * dy))
            gaussian.append(_f32(math.exp(_f32(_f32(-2.29) * radius))))
            catmull.append(_f32(_temporal_catmull_weight(dx) * _temporal_catmull_weight(dy)))
    gaussian_sum = _f32_sum(gaussian)
    catmull_sum = _f32_sum(catmull)
    weights = []
    for gaussian_value, catmull_value in zip(gaussian, catmull):
        normalized_gaussian = _f32(gaussian_value / gaussian_sum)
        normalized_catmull = _f32(catmull_value / catmull_sum)
        weights.append(
            _f32(
                normalized_gaussian
                + _f32(
                    _f32(normalized_catmull - normalized_gaussian) * _f32(0.8)
                )
            )
        )
    return tuple(weights)


def temporal_filter_registers(
    weights: tuple[float, ...] | list[float],
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Pack row-major weights into the three float4 cbuffer registers."""
    if len(weights) != 9:
        raise ValueError("the temporal filter requires nine weights")
    return (
        (weights[1], weights[3], weights[4], weights[5]),
        (weights[7], 0.0, 0.0, 0.0),
        (weights[0], weights[2], weights[6], weights[8]),
    )


def temporal_pixel_scale(size: tuple[int, int]) -> tuple[float, float, float, float]:
    """Build a native ``(width, height, inverse width, inverse height)`` value."""
    width, height = (int(value) for value in size)
    if width <= 0 or height <= 0:
        raise ValueError("temporal dimensions must be positive")
    return _f32(width), _f32(height), _f32(1.0 / width), _f32(1.0 / height)


def temporal_stencil_rejection(nonopaque_response: float) -> float:
    """Return ``m_Misc.y`` from the runtime nonopaque response."""
    response = temporal_nonopaque_response(nonopaque_response)
    return _f32(min(_f32(response + _f32(0.25)), _f32(1.0)) / _f32(128.0))


def temporal_nonopaque_response(runtime_response: float | None = None) -> float:
    """Select the positive runtime response or the executable's 0.04 fallback."""
    if runtime_response is None:
        return TEMPORAL_NONOPAQUE_RESPONSE_FALLBACK
    response = _f32(runtime_response)
    return (
        response
        if response > _f32(0.0)
        else TEMPORAL_NONOPAQUE_RESPONSE_FALLBACK
    )


def temporal_disocclusion_camera_scale(width: int) -> float:
    """Return the full-pass camera-motion normalization recovered from retail."""
    width = int(width)
    if width <= 0:
        raise ValueError("temporal width must be positive")
    return _f32(_f32(1920.0) / _f32(max(width, 1920)))


def temporal_hdr_scale(runtime_hdr_reference: float | None) -> float:
    """Return ``m_Misc.z`` using the executable's clamp and NaN fallback."""
    reference = (
        float("nan")
        if runtime_hdr_reference is None
        else float(runtime_hdr_reference)
    )
    if math.isnan(reference):
        return _f32(0.25)
    reference = min(max(reference, _f32(0.0001)), _f32(100.0))
    return _f32(1.0 / _f32(_f32(2.0) * _f32(reference)))


@dataclass(frozen=True)
class TemporalAaCBuffer:
    """Decoded 224-byte native ``TemporalAaCBuffer`` contract."""

    view_space_delta: tuple[float, ...]
    screen_to_view: tuple[float, ...]
    pixel_scale: tuple[float, ...]
    source_pixel_scale: tuple[float, ...]
    filter_weights_a: tuple[float, ...]
    filter_weights_b: tuple[float, ...]
    filter_weights_c: tuple[float, ...]
    misc: tuple[float, ...]
    misc2: tuple[float, ...]
    dither_constants: tuple[float, ...]
    fuzz_enabled: int = 0
    screen_capture_enabled: int = 0
    padding: tuple[float, float] = (0.0, 0.0)

    def pack(self) -> bytes:
        groups = (
            ("view_space_delta", self.view_space_delta, 16),
            ("screen_to_view", self.screen_to_view, 4),
            ("pixel_scale", self.pixel_scale, 4),
            ("source_pixel_scale", self.source_pixel_scale, 4),
            ("filter_weights_a", self.filter_weights_a, 4),
            ("filter_weights_b", self.filter_weights_b, 4),
            ("filter_weights_c", self.filter_weights_c, 4),
            ("misc", self.misc, 4),
            ("misc2", self.misc2, 4),
            ("dither_constants", self.dither_constants, 4),
            ("padding", self.padding, 2),
        )
        for name, values, expected in groups:
            if len(values) != expected:
                raise ValueError(f"{name} requires {expected} values")
        float_values = tuple(value for _, values, _ in groups[:-1] for value in values)
        result = struct.pack(
            "<52f2I2f",
            *float_values,
            int(self.fuzz_enabled),
            int(self.screen_capture_enabled),
            *self.padding,
        )
        if len(result) != TEMPORAL_APPLY_CBUFFER_SIZE:
            raise RuntimeError("packed temporal cbuffer has the wrong size")
        return result

    @classmethod
    def unpack(cls, data: bytes) -> "TemporalAaCBuffer":
        if len(data) != TEMPORAL_APPLY_CBUFFER_SIZE:
            raise ValueError("temporal cbuffer must contain exactly 224 bytes")
        return cls(
            view_space_delta=struct.unpack_from("<16f", data, 0),
            screen_to_view=struct.unpack_from("<4f", data, 64),
            pixel_scale=struct.unpack_from("<4f", data, 80),
            source_pixel_scale=struct.unpack_from("<4f", data, 96),
            filter_weights_a=struct.unpack_from("<4f", data, 112),
            filter_weights_b=struct.unpack_from("<4f", data, 128),
            filter_weights_c=struct.unpack_from("<4f", data, 144),
            misc=struct.unpack_from("<4f", data, 160),
            misc2=struct.unpack_from("<4f", data, 176),
            dither_constants=struct.unpack_from("<4f", data, 192),
            fuzz_enabled=struct.unpack_from("<I", data, 208)[0],
            screen_capture_enabled=struct.unpack_from("<I", data, 212)[0],
            padding=struct.unpack_from("<2f", data, 216),
        )


def build_temporal_apply_cbuffer(
    *,
    view_space_delta: tuple[float, ...],
    screen_to_view: tuple[float, ...],
    destination_size: tuple[int, int],
    source_size: tuple[int, int] | None = None,
    filter_offset_pixels: tuple[float, float] = (0.0, 0.0),
    nonopaque_response: float | None = None,
    conditional_floor: bool = False,
    runtime_hdr_reference: float | None = None,
    history_age: int = 0,
    has_history: bool = True,
    dither_enabled: bool = True,
    fuzz_enabled: bool = False,
    screen_capture_enabled: bool = False,
) -> TemporalAaCBuffer:
    """Build all stable native-apply fields from their recovered producers."""
    source_size = source_size or destination_size
    offset_x, offset_y = (_f32(value) for value in filter_offset_pixels)
    filter_a, filter_b, filter_c = temporal_filter_registers(
        temporal_filter_weights((offset_x, offset_y))
    )
    misc = temporal_apply_misc(
        nonopaque_response=nonopaque_response,
        conditional_floor=conditional_floor,
        runtime_hdr_reference=runtime_hdr_reference,
        history_age=history_age,
        has_history=has_history,
    )
    return TemporalAaCBuffer(
        view_space_delta=tuple(_f32(value) for value in view_space_delta),
        screen_to_view=tuple(_f32(value) for value in screen_to_view),
        pixel_scale=temporal_pixel_scale(destination_size),
        source_pixel_scale=temporal_pixel_scale(source_size),
        filter_weights_a=filter_a,
        filter_weights_b=filter_b,
        filter_weights_c=filter_c,
        misc=misc,
        misc2=(0.0, 0.0, offset_x, offset_y),
        dither_constants=temporal_dither_constants(
            history_age,
            enabled=dither_enabled,
        ),
        fuzz_enabled=int(bool(fuzz_enabled)),
        screen_capture_enabled=int(bool(screen_capture_enabled)),
    )


def temporal_dither_constants(
    history_age: int, *, enabled: bool = True,
) -> tuple[float, float, float, float]:
    """Build the four dither values written by the native TAA cbuffer builder."""
    age = max(int(history_age), 0)
    red_green = _DITHER_RED_GREEN if enabled else 0.0
    blue = _DITHER_BLUE if enabled else 0.0
    phase = float((2 * (age % 5)) % 5)
    return red_green, blue, phase, TEMPORAL_DITHER_TABLE[age & 255]


def temporal_history_warmup(history_age: int, *, has_history: bool = True) -> float:
    """Return ``m_Misc.w`` for one preview history age as native float32."""
    if not has_history:
        return 1.0
    age = max(int(history_age), 0)
    value = 1.0 / float(age + 1)
    return struct.unpack("<f", struct.pack("<f", value))[0]


def temporal_minimum_rejection(
    nonopaque_response: float | None = None,
    *, conditional_floor: bool = False,
) -> float:
    """Return native ``m_Misc.x`` for the selected nonopaque response."""
    result = max(
        temporal_nonopaque_response(nonopaque_response),
        TEMPORAL_MINIMUM_REJECTION_FLOOR,
    )
    if conditional_floor:
        result = max(result, TEMPORAL_CONDITIONAL_REJECTION_FLOOR)
    return result


def temporal_apply_misc(
    *,
    nonopaque_response: float | None = None,
    conditional_floor: bool = False,
    runtime_hdr_reference: float | None = None,
    history_age: int = 0,
    has_history: bool = True,
) -> tuple[float, float, float, float]:
    """Build the four native ``m_Misc`` values from their runtime inputs."""
    return (
        temporal_minimum_rejection(
            nonopaque_response,
            conditional_floor=conditional_floor,
        ),
        temporal_stencil_rejection(nonopaque_response),
        temporal_hdr_scale(runtime_hdr_reference),
        temporal_history_warmup(history_age, has_history=has_history),
    )
