"""Replay Hair indirect lighting from an explicit NPZ resource/query bundle.

See docs/HAIR_INDIRECT_REPLAY.md for required arrays and capture semantics.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if len({args.input.resolve(), args.output.resolve(), args.report.resolve()}) != 3:
        parser.error('Input, output and report must be distinct paths')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.hair_lighting_replay import replay_hair_lighting
    with np.load(args.input, allow_pickle=False) as bundle:
        result = replay_hair_lighting(bundle)
        cube_formats = {prefix: 'BC6U' if f'{prefix}_bc6_mip0' in bundle else 'RGB32F'
                        for prefix in ('default', 'local')}
    renderer = result.pop('renderer')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('wb') as target:
        np.savez_compressed(target, **result)
    with args.input.open('rb') as source:
        hasher = hashlib.sha256()
        for block in iter(lambda: source.read(1024 * 1024), b''):
            hasher.update(block)
        digest = hasher.hexdigest()
    report = {'input': str(args.input.resolve()),
              'input_sha256': digest,
              'query_count': len(result['visibility']), 'renderer': renderer,
              'cube_formats': cube_formats,
              'output': str(args.output.resolve()),
              'scope': 'Hair light grid and environment probes before BRDF/direct/deferred/TAA composition',
              'capture_parity_established': False,
              'ranges': {name: [float(value.min()), float(value.max())] for name, value in result.items()}}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"Replayed {report['query_count']} Hair indirect-lighting queries on {renderer}")


if __name__ == '__main__':
    main()
