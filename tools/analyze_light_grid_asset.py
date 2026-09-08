"""Validate/decode cooked light-grid bricks from inline or streamed assets."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', type=Path, required=True, help='Extracted zonelightbin DAT1, outer header allowed')
    parser.add_argument('--stream', type=Path, help='Separate span with the same asset ID; omit for inline assets')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--brick-index', type=int)
    parser.add_argument('--brick-output', type=Path, help='NPZ of one brick, optionally interpolated in isolation')
    parser.add_argument('--interpolate-with-executable', type=Path,
                        help='Use the verified game build in an isolated VM to fill the selected brick')
    args = parser.parse_args()
    if (args.brick_index is None) != (args.brick_output is None):
        parser.error('--brick-index and --brick-output must be supplied together')
    if args.interpolate_with_executable is not None and args.brick_index is None:
        parser.error('Retail interpolation requires a selected brick and output path')
    paths = [args.asset, args.output] + ([args.brick_output] if args.brick_output else [])
    if args.stream is not None:
        paths.append(args.stream)
    if args.interpolate_with_executable is not None:
        paths.append(args.interpolate_with_executable)
    if len({p.resolve() for p in paths}) != len(paths):
        parser.error('Input and output files must be distinct')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.light_grid_assets import load_light_grid_asset, decode_light_grid_brick
    try:
        asset = load_light_grid_asset(args.asset.read_bytes(),
                                     args.stream.read_bytes() if args.stream is not None else None)
    except ValueError as error:
        parser.error(str(error))
    index, raw = asset.index, asset.stream
    if args.brick_index is not None and not 0 <= args.brick_index < len(index.positions):
        parser.error('Brick index is outside the position table')
    totals = Counter()
    hashes = hashlib.sha256()
    authored_range = []
    interpolation = None
    for i in range(len(index.positions)):
        block = raw[int(index.stream_offsets[i]):int(index.stream_offsets[i + 1])]
        brick = decode_light_grid_brick(block)
        totals.update({str(kind): int(count) for kind, count in enumerate(np.bincount(brick.cell_kinds, minlength=4))})
        hashes.update(brick.records.astype('<u4', copy=False).tobytes())
        authored_range.append(brick.authored_count)
        if i == args.brick_index:
            values = dict(records=brick.records, cell_kinds=brick.cell_kinds,
                          unresolved_indices=brick.unresolved_indices, position=index.positions[i])
            if args.interpolate_with_executable is not None:
                from core.retail_light_grid import RetailLightGridDecoder, SUPPORTED_EXE_SHA256
                result = RetailLightGridDecoder(args.interpolate_with_executable).decode(block)
                values.update(records=result.records, fallback_scale=np.float32(result.fallback_scale))
                values['source_missing_indices'] = values.pop('unresolved_indices')
                interpolation = {'brick_index': i, 'executable_sha256': SUPPORTED_EXE_SHA256,
                                 'first_stage_exact': result.first_stage_exact, 'changed_cells': result.changed_cells,
                                 'fallback_scale': result.fallback_scale,
                                 'method': 'isolated x86 emulation, system CRT expf/logf, MXCSR 0x1F80'}
            args.brick_output.parent.mkdir(parents=True, exist_ok=True)
            with args.brick_output.open('wb') as output:
                np.savez_compressed(output, **values)
    report = {
        'asset': str(args.asset.resolve()),
        'stream': str(args.stream.resolve()) if args.stream is not None else None,
        'storage': asset.storage,
        'stream_sha256': hashlib.sha256(raw).hexdigest(), 'stream_bytes': len(raw),
        'brick_count': len(index.positions), 'decoded_record_count': len(index.positions) * 4096,
        'decoded_records_sha256_before_interpolation': hashes.hexdigest(),
        'header_words': index.header_words, 'cell_kind_counts': dict(sorted(totals.items())),
        'authored_samples_per_brick': [min(authored_range, default=0), max(authored_range, default=0)],
        'all_brick_bytes_consumed': True,
        'all_bricks_interpolated': False, 'runtime_world_placement_verified': False,
        'selected_brick_interpolation': interpolation,
        'bounds_of_stored_positions': ([index.positions.min(axis=0).tolist(), index.positions.max(axis=0).tolist()]
                                      if len(index.positions) else None),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    suffix = 'selected brick interpolated in isolation' if interpolation else 'before runtime interpolation'
    print(f"Decoded {report['brick_count']} bricks; cell kinds {report['cell_kind_counts']}; {suffix}")


if __name__ == '__main__':
    main()
