"""Match captured EnvProbeEnv records to cooked zone probe definitions.

The GPU table omits authored instance IDs.  Match fields that placement,
residency, and camera Z-bin generation cannot change, then solve the row-vector
zone transform implied by each remaining candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


STATIC_RANGES = ((44, 60), (64, 112))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _probe_from_report(item):
    from core.environment_probes import ZoneEnvironmentProbe

    return ZoneEnvironmentProbe(
        item['index'], int(item['instance_id'], 16),
        tuple(item['zone_local_position']),
        tuple(tuple(axis) for axis in item['zone_local_axes']),
        item['texture_index'], item['draw_list_index'], (), (),
        tuple(item['half_extents']), tuple(item['capture_offset']),
        tuple(item['falloff_negative']), tuple(item['falloff_positive']),
        tuple(item['proxy_negative']), tuple(item['proxy_positive']),
        item['volume_shape'], item['diffuse_flags'], item['priority'],
    )


def _static_bytes(data: bytes) -> bytes:
    return b''.join(data[start:end] for start, end in STATIC_RANGES)


def _solve_zone_transform(probe, captured):
    """Return the affine row-vector transform implied by a captured record."""
    from core.probe_lighting import ProbeShaderRecord, build_probe_shader_record

    record = ProbeShaderRecord.from_bytes(captured)
    captured_axes = np.stack((
        np.asarray(record.axis_x, dtype=np.float32),
        np.asarray(record.axis_y, dtype=np.float32),
        np.cross(np.asarray(record.axis_x, dtype=np.float32),
                 np.asarray(record.axis_y, dtype=np.float32)) * np.float32(record.z_sign),
    ))
    authored_axes = np.asarray(probe.axes, dtype=np.float32)
    try:
        linear = np.linalg.solve(authored_axes.astype(np.float64),
                                 captured_axes.astype(np.float64)).astype(np.float32)
    except np.linalg.LinAlgError:
        return None
    authored_position = np.asarray(probe.position, dtype=np.float32)
    captured_position = np.asarray(record.position, dtype=np.float32)
    translation = np.asarray(
        captured_position.astype(np.float64)
        - authored_position.astype(np.float64) @ linear.astype(np.float64),
        dtype=np.float32,
    )
    matrix = np.eye(4, dtype=np.float32)
    matrix[:3, :3] = linear
    matrix[3, :3] = translation
    rebuilt = build_probe_shader_record(
        probe, matrix, cube_index=int(record.cube_index), fade=record.fade,
    ).to_bytes()
    captured_values = np.frombuffer(captured[:124], dtype='<f4')
    rebuilt_values = np.frombuffer(rebuilt[:124], dtype='<f4')
    finite = np.isfinite(captured_values) & np.isfinite(rebuilt_values)
    value_error = np.abs(captured_values[finite].astype(np.float64)
                         - rebuilt_values[finite].astype(np.float64))
    gram = linear.astype(np.float64) @ linear.astype(np.float64).T
    capture_delta = (
        np.asarray(record.capture_position, dtype=np.float32)
        - np.asarray(record.position, dtype=np.float32)
    )
    offset_error = np.max(np.abs(
        capture_delta.astype(np.float64)
        - np.asarray(probe.capture_offset, dtype=np.float32).astype(np.float64)
    ))
    return {
        'zone_to_world': matrix.tolist(),
        'determinant': float(np.linalg.det(linear.astype(np.float64))),
        'rigid_orthogonality_max_abs_error': float(np.max(np.abs(gram - np.eye(3)))),
        'capture_offset_max_abs_error': float(offset_error),
        'rebuilt_first_124_bytes_exact': rebuilt[:124] == captured[:124],
        'rebuilt_first_124_max_abs_float_error': (
            float(np.max(value_error)) if value_error.size else 0.0
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-inputs', type=Path, required=True)
    parser.add_argument('--probe-report', type=Path, required=True)
    parser.add_argument('--active-count', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    forge_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(forge_root))
    from core.probe_lighting import ProbeShaderRecord, build_probe_shader_record

    with np.load(args.capture_inputs, allow_pickle=False) as capture:
        records = np.asarray(capture['probe_records'])
    if records.dtype != np.uint8 or records.ndim != 2 or records.shape[1] != 128:
        parser.error('probe_records must be an Nx128 uint8 array')
    if not 0 <= args.active_count <= len(records):
        parser.error('active count is outside the captured probe table')

    report = json.loads(args.probe_report.read_text(encoding='utf-8'))
    candidates = []
    for zone in report['zones']:
        for item in zone['probes']:
            probe = _probe_from_report(item)
            identity = build_probe_shader_record(
                probe, np.eye(4, dtype=np.float32), cube_index=0, fade=0,
            ).to_bytes()
            candidates.append((zone, item, probe, _static_bytes(identity)))

    matched_records = []
    for index in range(args.active_count):
        captured = records[index].tobytes()
        gpu = ProbeShaderRecord.from_bytes(captured)
        matches = []
        for zone, item, probe, static in candidates:
            if static != _static_bytes(captured):
                continue
            transform = _solve_zone_transform(probe, captured)
            matches.append({
                'zone_asset_id': zone['asset_id'],
                'zone_path': zone['path'],
                'probe_index': item['index'],
                'instance_id': item['instance_id'],
                'source': item['source'],
                'runtime_sort_key_descending': item['runtime_sort_key_descending'],
                **transform,
            })
        exact_identity = [
            match for match in matches
            if match['rebuilt_first_124_bytes_exact']
            and np.array_equal(
                np.asarray(match['zone_to_world'], dtype=np.float32),
                np.eye(4, dtype=np.float32),
            )
        ]
        if len(matches) == 1:
            selected_match = matches[0]
            selection_basis = 'unique_placement_invariant_authored_fields'
        elif len(exact_identity) == 1:
            selected_match = exact_identity[0]
            selection_basis = 'unique_exact_identity_placement'
        else:
            selected_match = None
            selection_basis = None
        matched_records.append({
            'record': index,
            'cube': gpu.cube_index,
            'fade': gpu.fade,
            'flags': gpu.flags,
            'candidate_count': len(matches),
            'selection_basis': selection_basis,
            'selected_match': selected_match,
            'matches': matches,
        })

    resolved = [item['selected_match'] for item in matched_records]
    sort_keys = [item['runtime_sort_key_descending'] for item in resolved if item]
    zone_groups = {}
    for item in resolved:
        if item is None:
            continue
        zone_groups.setdefault(item['zone_asset_id'], []).append(
            np.asarray(item['zone_to_world'], dtype=np.float32)
        )
    placement_groups = []
    identity = np.eye(4, dtype=np.float32)
    for zone_asset_id, matrices in zone_groups.items():
        stack = np.stack(matrices)
        identity_rows = [matrix for matrix in matrices if np.array_equal(matrix, identity)]
        representative = identity_rows[0] if identity_rows else stack[0]
        placement_groups.append({
            'zone_asset_id': zone_asset_id,
            'record_count': len(matrices),
            'identity_placement': bool(identity_rows),
            'linear_max_spread': float(np.max(np.ptp(stack[:, :3, :3], axis=0))),
            'translation_max_spread': float(np.max(np.ptp(stack[:, 3, :3], axis=0))),
            'representative_zone_to_world': representative.tolist(),
        })
    payload = {
        'scope': 'active_capture_records_matched_by_placement_invariant_authored_fields',
        'evidence': {
            'capture_inputs': {'path': str(args.capture_inputs), 'sha256': _sha256(args.capture_inputs)},
            'probe_report': {'path': str(args.probe_report), 'sha256': _sha256(args.probe_report)},
        },
        'active_count': args.active_count,
        'candidate_probe_count': len(candidates),
        'static_byte_ranges': [list(item) for item in STATIC_RANGES],
        'records': matched_records,
        'validation': {
            'resolved_record_count': sum(item is not None for item in resolved),
            'all_active_records_resolved': all(item is not None for item in resolved),
            'strictly_descending_retail_sort_keys': all(
                left > right for left, right in zip(sort_keys, sort_keys[1:])
            ),
            'selected_zone_count': len(zone_groups),
            'placement_groups': placement_groups,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    counts = [item['candidate_count'] for item in matched_records]
    print(f'matched {len(matched_records)} active records against {len(candidates)} probes; '
          f'candidate counts={counts}; output={args.output}')


if __name__ == '__main__':
    main()
