"""Reconstruct one explicitly selected cooked grid for diagnostic GPU replay.

This uses the verified retail decoder in an isolated VM. It chooses every brick
from the supplied asset, compacts slots, and applies the requested uniform fade.
It does not reconstruct a captured frame's residency or lighting condition.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', type=Path, required=True)
    parser.add_argument('--stream', type=Path, help='Required only for separately streamed assets')
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--fade', type=int, required=True, help='Explicit uniform fade, 0 through 255')
    parser.add_argument('--output', type=Path, required=True, help='Reconstructed lookup/data NPZ')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.fade <= 255:
        parser.error('--fade must be between 0 and 255')
    paths = [args.asset, args.executable, args.output, args.report]
    if args.stream is not None:
        paths.append(args.stream)
    if len({p.resolve() for p in paths}) != len(paths):
        parser.error('Input and output files must be distinct')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.light_grid_assets import load_light_grid_asset
    from core.light_grid_resources import build_light_grid_resources, light_grid_lookup_address
    from core.retail_light_grid import RetailLightGridDecoder, SUPPORTED_EXE_SHA256

    raw_asset = args.asset.read_bytes()
    asset = load_light_grid_asset(raw_asset, args.stream.read_bytes() if args.stream is not None else None)
    index = asset.index
    addresses = [light_grid_lookup_address(p) for p in index.positions]
    if len(set(addresses)) != len(addresses):
        parser.error('This whole asset has ring collisions; an explicit brick selection is required')
    start = time.perf_counter()
    decoder = RetailLightGridDecoder(args.executable)
    cache, bricks, summaries = {}, [], []
    for i in range(len(index.positions)):
        block = asset.stream[int(index.stream_offsets[i]):int(index.stream_offsets[i + 1])]
        digest = hashlib.sha256(block).hexdigest()
        cached = digest in cache
        if not cached:
            cache[digest] = decoder.decode(block)
        brick = cache[digest]
        bricks.append(brick.records)
        summaries.append({'index': i, 'encoded_sha256': digest, 'reused_identical_block': cached,
                          'first_stage_exact': brick.first_stage_exact, 'changed_cells': brick.changed_cells,
                          'fallback_scale': brick.fallback_scale})
        if (i + 1) % 20 == 0 or i + 1 == len(index.positions):
            print(f'Interpolated {i + 1}/{len(index.positions)} bricks; {len(cache)} distinct blocks', flush=True)
    records = np.stack(bricks) if bricks else np.empty((0, 4096, 4), np.uint32)
    fallback = decoder.default_record()
    fades = np.full(len(bricks), args.fade, np.uint8)
    resources = build_light_grid_resources(index.positions, records, fades, fallback)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('wb') as output:
        np.savez_compressed(output, grid_lookup=resources.lookup, grid_data=resources.data,
                            brick_positions=index.positions, brick_fades=fades,
                            brick_lookup_addresses=resources.brick_lookup_addresses,
                            fallback_slot=np.uint32(resources.fallback_slot), fallback_record=fallback)
    report = {'asset': str(args.asset.resolve()), 'asset_sha256': hashlib.sha256(raw_asset).hexdigest(),
              'storage': asset.storage, 'stream_sha256': hashlib.sha256(asset.stream).hexdigest(),
              'executable_sha256': SUPPORTED_EXE_SHA256, 'brick_count': len(bricks),
              'distinct_encoded_bricks': len(cache), 'all_bricks_interpolated': True,
              'uniform_fade': args.fade, 'slots_compacted_for_replay': True,
              'fallback_record': [f'{int(v):08X}' for v in fallback],
              'grid_lookup_sha256': hashlib.sha256(resources.lookup.astype('<u4').tobytes()).hexdigest(),
              'grid_data_sha256': hashlib.sha256(resources.data.astype('<u4').tobytes()).hexdigest(),
              'output': str(args.output.resolve()), 'elapsed_seconds': time.perf_counter() - start,
              'captured_frame_comparison': False,
              'selection': 'Every brick of the explicitly supplied asset; runtime residency is not inferred',
              'bricks': summaries}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(resources.data)} records and the full lookup ring for explicit replay', flush=True)


if __name__ == '__main__':
    main()
