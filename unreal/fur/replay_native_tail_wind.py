"""CPU replay of captured CS_ModelStrandSimulateWind event 24762."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import struct

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "unreal/fur/recovered/native-strand-pipeline"
OUTPUT = SOURCE / "tail-wind-cpu-replay.json"
F = np.float32


def f(value):
    return F(value)


def frac(value):
    return f(value - np.floor(value))


def sat(value):
    return f(np.clip(value, f(0), f(1)))


def mad(a, b, c):
    """Round one exact float32 multiply-add to float32, matching DXIL mad."""
    return f(float(a) * float(b) + float(c))


def signed16(value):
    return value - 65536 if value & 0x8000 else value


def unpack_position(raw, index, meters_per_unit):
    xy, z_flags = struct.unpack_from("<II", raw, index * 8)
    return np.asarray((signed16(xy & 0xffff), signed16(xy >> 16),
                       signed16(z_flags & 0xffff)), dtype=np.float32) * meters_per_unit


def unpack_normal(raw, index):
    _, z_flags = struct.unpack_from("<II", raw, index * 8)
    a = f(((z_flags >> 16) & 255) * f(.00784314) - f(1))
    b = f(((z_flags >> 24) & 255) * f(.00784314) - f(1))
    z = f(1 - abs(a) - abs(b))
    fold = sat(-z)
    x = f(a + (-fold if a >= 0 else fold))
    y = f(b + (-fold if b >= 0 else fold))
    return x, z, y


def pack(position, normal, meters_per_unit):
    q = [int(f(component / meters_per_unit)) for component in position]
    xy = (q[0] & 0xffff) | ((q[1] & 0xffff) << 16)
    x, y, z = normal
    divisor = f(1 / f(abs(x) + abs(y) + abs(z)))
    ox, oy, oz = f(x * divisor), f(y * divisor), f(z * divisor)
    if oy >= 0:
        a, b = ox, oz
    else:
        a = f((1 - abs(oz)) * (1 if ox > 0 else (-1 if ox < 0 else 0)))
        b = f((1 - abs(ox)) * (1 if oz > 0 else (-1 if oz < 0 else 0)))
    pa = int(f(a * f(127.5) + f(128)))
    pb = int(f(b * f(127.5) + f(128)))
    z_flags = (q[2] & 0xffff) | ((pa << 16) & 0xff0000) | ((pb << 24) & 0xff000000)
    return struct.pack("<II", xy & 0xffffffff, z_flags & 0xffffffff)


def packed_components(raw, index):
    xy, z_flags = struct.unpack_from("<II", raw, index * 8)
    return (signed16(xy & 0xffff), signed16(xy >> 16),
            signed16(z_flags & 0xffff), (z_flags >> 16) & 255,
            (z_flags >> 24) & 255)


model_cb = (SOURCE / "e24762-Compute-b5.bin").read_bytes()
world_cb = (SOURCE / "e24762-Compute-b6.bin").read_bytes()
scene_raw = (SOURCE / "e24762-SceneObjectGpu.bin").read_bytes()
dynamic_raw = (SOURCE / "e24762-DynamicObjectGpu.bin").read_bytes()
strand_raw = (SOURCE / "e24762-Compute-t5-StrandBuffer.bin").read_bytes()
base_raw = (SOURCE / "e24762-Compute-t6-StrandCVBuffer.bin").read_bytes()
previous_raw = (SOURCE / "e24762-Compute-t11-StrandCVBufferPrev.bin").read_bytes()
expected_raw = (SOURCE / "e24762-Compute-u0-StrandCVBufferOutput.bin").read_bytes()
pre_dispatch_raw = (SOURCE / "e24762-pre-Compute-u0-StrandCVBufferOutput.bin").read_bytes()

camera = np.asarray(struct.unpack_from("<3f", model_cb, 0), dtype=np.float32)
previous_camera = np.asarray(struct.unpack_from("<3f", model_cb, 16), dtype=np.float32)
meters_per_unit = f(struct.unpack_from("<f", model_cb, 32)[0])
wind_strength, turbulence = map(f, struct.unpack_from("<2f", model_cb, 40))
strand_start, strand_count = struct.unpack_from("<2I", model_cb, 56)
_, stiffness_inverse_length, stiffness_power, drag = map(
    f, struct.unpack_from("<4f", model_cb, 144))
timer = f(struct.unpack_from("<f", world_cb, 0)[0])
wind_vector = np.asarray(struct.unpack_from("<3f", world_cb, 16), dtype=np.float32)
scene = np.asarray(struct.unpack_from("<12f", scene_raw, 0), dtype=np.float32).reshape(3, 4)
dynamic = np.asarray(struct.unpack_from("<12f", dynamic_raw, 0), dtype=np.float32).reshape(3, 4)
anim_force = f(struct.unpack_from("<e", scene_raw, 94)[0])
radius = f(struct.unpack_from("<f", scene_raw, 116)[0])

shader_text = (SOURCE / "CS_ModelStrandSimulateWind.txt").read_text(encoding="utf-8")
match = re.search(r"g_RandomVecs_v_1dim_0 = internal constant float\[256\] \[(.*?)\], align", shader_text)
if not match:
    raise RuntimeError("Could not parse captured random-vector table")
random_values = np.asarray(
    [float(value) for value in re.findall(r"float ([+\-0-9.eE]+)", match.group(1))],
    dtype=np.float32)
if len(random_values) != 256:
    raise RuntimeError(f"Expected 256 random-vector scalars, found {len(random_values)}")


def inverse_transform_wind():
    a, b, c = scene[:, :3]
    c00, c01, c02 = f(c[2] * b[1] - c[1] * b[2]), f(c[0] * b[2] - c[2] * b[0]), f(c[1] * b[0] - c[0] * b[1])
    c10, c11, c12 = f(c[1] * a[2] - c[2] * a[1]), f(c[2] * a[0] - c[0] * a[2]), f(c[0] * a[1] - c[1] * a[0])
    c20, c21, c22 = f(b[2] * a[1] - b[1] * a[2]), f(b[0] * a[2] - b[2] * a[0]), f(b[1] * a[0] - b[0] * a[1])
    determinant = f(c21 * c[1] + c20 * c[0] + c[2] * c22 - c[0] * c12 - c[1] * c11)
    inverse_det = f(1 / determinant)
    return np.asarray((
        f(inverse_det * f(wind_vector[0] * c00 + wind_vector[1] * c10 + wind_vector[2] * c20)),
        f(inverse_det * f(wind_vector[0] * c01 + wind_vector[1] * c11 + wind_vector[2] * c21)),
        f(inverse_det * f(wind_vector[0] * c02 + wind_vector[1] * c12 + wind_vector[2] * c22)),
    ), dtype=np.float32)


local_wind = inverse_transform_wind()


def wind_noise(u, v):
    frequency0 = f(turbulence * f(20) + f(10))
    frequency1 = f(turbulence * f(100) + f(50))
    mixed = f(np.sin(f(frequency0 * u)) + np.sin(f(frequency0 * v)))
    mixed = f(mixed + f(f(np.sin(f(frequency1 * u)) + np.sin(f(frequency1 * v))) * f(.5)))
    return f(mixed * f(.125))


def replay(current_raw):
    output = bytearray(expected_raw)
    drag_scale = f(drag * f(-.95))
    drag_base = f(drag + f(.001))
    drag_velocity = f(f(1 - drag) * f(500))
    for strand in range(strand_start, strand_start + strand_count):
        word0, word1, _ = struct.unpack_from("<III", strand_raw, strand * 12)
        count, start = word0 >> 24, word0 & 0xffffff
        u = f((word1 & 0xffff) * f(1.52590e-05))
        v = f((word1 >> 16) * f(1.52590e-05))
        noise = wind_noise(u, v)
        phase_time = f(f(timer + f(.125) + f(noise * f(.125))) * f(turbulence * f(10) + f(5)))
        phase_fraction = frac(phase_time)
        weights = np.asarray((
            f(-phase_fraction + f(2) * phase_fraction ** 2 - phase_fraction ** 3),
            f(1 - f(2) * phase_fraction ** 2 + phase_fraction ** 3),
            f(phase_fraction + phase_fraction ** 2 - phase_fraction ** 3),
            f(-phase_fraction ** 2 + phase_fraction ** 3),
        ), dtype=np.float32)
        table_position = f(phase_time * f(.0163934))
        table_index = int(f(frac(table_position) * f(61)))
        random_vector = np.zeros(3, dtype=np.float32)
        for knot in range(4):
            base_index = (table_index + knot) * 4
            random_vector = np.asarray([
                f(random_vector[axis] + f(random_values[base_index + axis] * weights[knot]))
                for axis in range(3)], dtype=np.float32)
        timer_fraction = frac(f(timer * f(.159155)))
        force = f(anim_force * f(.9) + f(.05) + f(noise * f(.05)))
        blend_numerator = f(f(.6625) - f(force * f(.4375)))
        blend_denominator = f(f(1.925) - f(force * f(.875)))
        blend = f(0) if blend_denominator <= 0 else sat(f(blend_numerator / blend_denominator))
        blend = f(blend * blend * f(3 - f(2) * blend))
        wave = f(np.sin(f(f(force + timer_fraction) * f(6.28319))))
        scalar_wind = f(f(f(f(1 - blend) * force) + blend + f(1)) * wave - f(1))
        scalar_wind = f(scalar_wind * wind_strength)
        max_force = f(min(f(blend * f(force * f(.0125) + f(.0375))), f(radius * f(.1))))
        field = np.asarray((
            f(scalar_wind + f(local_wind[0] * max_force)),
            f(f(local_wind[1] * max_force) - wind_strength),
            f(scalar_wind + f(local_wind[2] * max_force)),
        ), dtype=np.float32)
        cumulative = f(0)
        root_current = root_base = previous_output = previous_base = None
        for index in range(count):
            cv = start + index
            current = unpack_position(current_raw, cv, meters_per_unit)
            previous = unpack_position(previous_raw, cv, meters_per_unit)
            base = unpack_position(base_raw, cv, meters_per_unit)
            if index == 0:
                root_current = current.copy()
                root_base = base.copy()
                previous_output = current.copy()
                previous_base = base.copy()
            delta = np.asarray([f(current[axis] - previous_output[axis]) for axis in range(3)], dtype=np.float32)
            cumulative = f(cumulative + f(np.sqrt(f(np.dot(delta, delta)))))
            current_world = np.asarray([
                f(scene[row, 3] - camera[row] + f(np.dot(current, scene[row, :3])) + camera[row])
                for row in range(3)], dtype=np.float32)
            previous_world = np.asarray([
                f(dynamic[row, 3] - previous_camera[row] + f(np.dot(previous, dynamic[row, :3])) + previous_camera[row])
                for row in range(3)], dtype=np.float32)
            world_delta = np.asarray([f(current_world[i] - previous_world[i]) for i in range(3)], dtype=np.float32)
            velocity = np.asarray([
                mad(world_delta[2], scene[2, axis],
                    mad(world_delta[1], scene[1, axis],
                        f(world_delta[0] * scene[0, axis])))
                for axis in range(3)
            ], dtype=np.float32)
            along = f(index / count)
            stiffness_limit = f(min(f(.25 + f(.75) * along), abs(f(stiffness_inverse_length * cumulative))))
            stiffness = sat(f(2 ** f(np.log2(stiffness_limit) * stiffness_power))) if stiffness_limit > 0 else f(0)
            denominator = f(drag_base + f(drag_velocity * f(np.dot(velocity, velocity))))
            candidate = np.asarray([
                f(current[axis] + f(velocity[axis] * f(drag_scale * stiffness) / denominator))
                for axis in range(3)], dtype=np.float32)
            if f(stiffness * wind_strength) > 0:
                wind_candidate = []
                for axis in range(3):
                    accumulated = f(candidate[axis] * f(30))
                    random_field = f(field[axis] + f(random_vector[axis] * wind_strength))
                    accumulated = f(accumulated + f(random_field * stiffness))
                    wind_candidate.append(f(accumulated / f(30)))
                candidate = np.asarray(wind_candidate, dtype=np.float32)
            vector = np.asarray([
                f(candidate[axis] - root_current[axis] - f(f(previous_output[axis] - root_current[axis]) * f(.5)))
                for axis in range(3)], dtype=np.float32)
            vector_squared = f(np.dot(vector, vector))
            corrected = candidate
            if vector_squared > 0:
                target_vector = np.asarray([
                    f(base[axis] - root_base[axis] - f(f(previous_base[axis] - root_base[axis]) * f(.5)))
                    for axis in range(3)], dtype=np.float32)
                target_length = f(np.sqrt(f(np.dot(target_vector, target_vector))))
                vector_length = f(np.sqrt(vector_squared))
                correction = f((target_length - vector_length) * f(1 / np.sqrt(vector_squared)))
                corrected = np.asarray([
                    f(candidate[axis] + f(vector[axis] * correction)) for axis in range(3)
                ], dtype=np.float32)
            output[cv * 8:(cv + 1) * 8] = pack(corrected, unpack_normal(previous_raw, cv), meters_per_unit)
            previous_output = corrected
            previous_base = base
    return bytes(output)


candidates = {
    "skinning_current_u0": SOURCE / "e24743-Compute-u0-StrandCVBufferOutput.bin",
    "skinning_previous_u1": SOURCE / "e24743-Compute-u1-StrandCVBufferPrevOutput.bin",
}
rows = []
for label, path in candidates.items():
    result = replay(path.read_bytes())
    component_deltas = []
    signed_position_deltas = []
    position_mismatch_components = 0
    normal_mismatch_components = 0
    for index in range(len(result) // 8):
        actual = packed_components(result, index)
        expected = packed_components(expected_raw, index)
        component_deltas.extend(abs(a - b) for a, b in zip(actual[:3], expected[:3]))
        signed_position_deltas.extend(e - a for a, e in zip(actual[:3], expected[:3]) if a != e)
        position_mismatch_components += sum(a != b for a, b in zip(actual[:3], expected[:3]))
        normal_mismatch_components += sum(a != b for a, b in zip(actual[3:], expected[3:]))
    changed_bytes = sum(a != b for a, b in zip(result, expected_raw))
    changed_vertices = sum(
        result[index:index + 8] != expected_raw[index:index + 8]
        for index in range(0, len(result), 8))
    rows.append({
        "input": label,
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(result).hexdigest(),
        "expected_sha256": hashlib.sha256(expected_raw).hexdigest(),
        "changed_bytes": changed_bytes,
        "changed_vertices": changed_vertices,
        "position_mismatch_components": position_mismatch_components,
        "normal_mismatch_components": normal_mismatch_components,
        "maximum_packed_position_delta": max(component_deltas),
        "signed_position_delta_histogram": {
            str(delta): signed_position_deltas.count(delta)
            for delta in sorted(set(signed_position_deltas))
        },
        "exact_position_component_percent": 100 * (
            1 - position_mismatch_components / (len(result) // 8 * 3)),
        "exact": result == expected_raw,
    })
    if label == "skinning_current_u0":
        (SOURCE / "tail-wind-cpu-replay.bin").write_bytes(result)

report = {
    "event": 24762,
    "constants": {
        "delta_time": struct.unpack_from("<f", model_cb, 12)[0],
        "meters_per_unit": float(meters_per_unit),
        "wind_strength": float(wind_strength),
        "turbulence": float(turbulence),
        "stiffness_inverse_length": float(stiffness_inverse_length),
        "stiffness_power": float(stiffness_power),
        "drag": float(drag),
        "timer": float(timer),
        "wind_vector": wind_vector.tolist(),
        "scene_object": struct.unpack_from("<I", model_cb, 28)[0],
    },
    "candidates": rows,
    "fixture_validation": {
        "pre_dispatch_sha256": hashlib.sha256(pre_dispatch_raw).hexdigest(),
        "inferred_skinning_sha256": hashlib.sha256(
            candidates["skinning_current_u0"].read_bytes()).hexdigest(),
        "pre_dispatch_matches_inferred_skinning": pre_dispatch_raw
            == candidates["skinning_current_u0"].read_bytes(),
        "acceptance": "normals exact; >=98% packed position components exact; maximum residual <=2 units",
        "passed": rows[0]["normal_mismatch_components"] == 0
            and rows[0]["exact_position_component_percent"] >= 98
            and rows[0]["maximum_packed_position_delta"] <= 2,
    },
    "completed": True,
}
OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
