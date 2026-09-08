"""Evaluate retail Hair probe weights and fetches from a raw EnvProbeEnv buffer."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--buffer', type=Path, required=True,
                        help='Raw g_EnvProbeEnvs contents; 128 bytes per record')
    parser.add_argument('--world-point', type=float, nargs=3, required=True)
    parser.add_argument('--lookup-mask', type=lambda value: int(value, 0), required=True,
                        help='Combined lookup words: word 0 in the lowest 32 bits')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reflection-direction', type=float, nargs=3)
    parser.add_argument('--shading-normal', type=float, nargs=3,
                        help="Hair's reconstructed world normal, including anisotropic jitter")
    parser.add_argument('--average-gloss', type=float,
                        help='Mean of the primary and secondary Hair gloss values')
    args = parser.parse_args()
    sampling = (args.reflection_direction, args.shading_normal, args.average_gloss)
    if any(value is not None for value in sampling) and not all(value is not None for value in sampling):
        parser.error('Sampling requires --reflection-direction, --shading-normal, and --average-gloss together')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.probe_lighting import parse_probe_shader_buffer, blend_probe_weights, probe_sampling_plan

    raw = args.buffer.read_bytes()
    records = parse_probe_shader_buffer(raw)
    if args.reflection_direction is None:
        result = blend_probe_weights(records, args.world_point, args.lookup_mask)
    else:
        result = probe_sampling_plan(
            records, args.world_point, args.lookup_mask,
            reflection_direction=args.reflection_direction, shading_normal=args.shading_normal,
            average_gloss=args.average_gloss,
        )
    report = {
        'input_buffer': str(args.buffer.resolve()),
        'buffer_sha256': hashlib.sha256(raw).hexdigest(),
        'record_count': len(records),
        'world_point': args.world_point,
        'lookup_mask': hex(args.lookup_mask),
        'result_kind': ('hair_probe_sampling_plan_before_texture_fetch_and_shading'
                        if args.reflection_direction is not None else 'hair_probe_sample_weights'),
        'reflection_direction': args.reflection_direction,
        'shading_normal': args.shading_normal,
        'average_gloss': args.average_gloss,
        **result,
        'masked_records': {
            str(i): asdict(record) for i, record in enumerate(records)
            if (args.lookup_mask >> i) & 1
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
