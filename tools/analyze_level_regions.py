"""Report cooked level regions/checkpoints and explicit region dependencies."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level-file', type=Path, required=True, help='Extracted level DAT1, with or without its outer header')
    parser.add_argument('--region-index', action='append', type=int, default=[])
    parser.add_argument('--zone-index', action='append', type=int, default=[],
                        help='Catalogue index to map back to declaring regions')
    parser.add_argument('--checkpoint', action='append', default=[], help='Exact checkpoint name; selects its declared region')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.level import LevelParser

    level = LevelParser(args.level_file.read_bytes()).parse_info()
    selected = list(args.region_index)
    for name in args.checkpoint:
        matches = [c for c in level.checkpoints if c.name.casefold() == name.casefold()]
        if len(matches) != 1:
            parser.error(f'Checkpoint {name!r} matched {len(matches)} records; use a region index')
        if matches[0].region_index < 0:
            parser.error(f'Checkpoint {name!r} has no region')
        selected.append(matches[0].region_index)
    try:
        candidates = level.region_zone_candidates(selected)
    except ValueError as exc:
        parser.error(str(exc))
    for index in args.zone_index:
        if not 0 <= index < len(level.zones):
            parser.error(f'Invalid zone catalogue index {index}')

    def region_item(region):
        item = asdict(region)
        item['asset_id'] = f'{region.asset_id:016X}'
        item['raw'] = region.raw.hex()
        item['bounds_data'] = region.bounds_data.hex()
        return item

    def checkpoint_item(checkpoint):
        item = asdict(checkpoint)
        item['checkpoint_id'] = f'{checkpoint.checkpoint_id:016X}'
        item['raw'] = checkpoint.raw.hex()
        return item

    def zone_item(level_info, index):
        zone = level_info.zones[index]
        return {'index': index, 'asset_id': f'{zone.asset_id:016X}', 'name': zone.name}

    payload = {
        'level_file': str(args.level_file),
        'selection': 'declared_primary_dependencies_including_parents_not_runtime_residency',
        'selected_region_indices': selected,
        'zone_count': len(level.zones), 'region_count': len(level.regions), 'checkpoint_count': len(level.checkpoints),
        'zone_candidates': [{'index': index, 'asset_id': f'{level.zones[index].asset_id:016X}',
                             'name': level.zones[index].name} for index in candidates],
        'regions': [region_item(region) for region in level.regions],
        'checkpoints': [checkpoint_item(checkpoint) for checkpoint in level.checkpoints],
    }
    streaming_roots = []
    for root in level.regions:
        if root.kind != 4:
            continue
        zone_refs = [zone for child in root.child_indices for zone in level.regions[child].zone_indices]
        streaming_candidates = level.streaming_region_zone_candidates(root.index)
        streaming_roots.append({
            'region_index': root.index,
            'asset_id': f'{root.asset_id:016X}',
            'name': root.name,
            'child_region_count': len(root.child_indices),
            'child_region_indices': list(root.child_indices),
            'child_primary_zone_reference_count': len(zone_refs),
            'unfiltered_unique_zone_count': len(streaming_candidates),
            'unfiltered_zone_candidates': [
                {'index': index, 'asset_id': f'{level.zones[index].asset_id:016X}',
                 'name': level.zones[index].name}
                for index in streaming_candidates
            ],
            'root_primary_zone_count': len(root.zone_indices),
            'root_primary_list_is_not_streaming_input': True,
        })
    payload['kind_4_streaming'] = {
        'selection': 'child_primary_dependencies_before_two_runtime_bitset_filters_not_runtime_residency',
        'selected_root_indices': [index for index in selected if level.regions[index].kind == 4],
        'roots': streaming_roots,
    }
    dependency_regions = []
    for index in selected:
        region = level.regions[index]
        if region.kind not in (3, 5):
            continue
        dependency_candidates = level.dependency_region_zone_candidates(index)
        dependency_regions.append({
            'region_index': index,
            'asset_id': f'{region.asset_id:016X}',
            'name': region.name,
            'kind': region.kind,
            'immediate_parent_index': region.parent_index,
            'unfiltered_unique_zone_count': len(dependency_candidates),
            'unfiltered_zone_candidates': [
                {'index': zone_index, 'asset_id': f'{level.zones[zone_index].asset_id:016X}',
                 'name': level.zones[zone_index].name}
                for zone_index in dependency_candidates
            ],
        })
    payload['kind_3_5_dependency_selection'] = {
        'selection': 'immediate_parent_then_selected_primary_dependencies_before_runtime_deduplication',
        'regions': dependency_regions,
    }
    zone_memberships = []
    for zone_index in args.zone_index:
        def membership_item(region):
            parent = level.regions[region.parent_index] if region.parent_index >= 0 else None
            return {
                'region_index': region.index,
                'kind': region.kind,
                'asset_id': f'{region.asset_id:016X}',
                'name': region.name,
                'parent_index': region.parent_index,
                'kind_4_parent_child_ordinal': (
                    parent.child_indices.index(region.index) if parent is not None and parent.kind == 4 else None
                ),
                'bounds_index': region.bounds_index,
                'bounds_data': region.bounds_data.hex(),
            }
        zone_memberships.append({
            **zone_item(level, zone_index),
            'primary_regions': [membership_item(region) for region in level.regions
                                if zone_index in region.zone_indices],
            'replacement_regions': [membership_item(region) for region in level.regions
                                    if zone_index in region.replacement_zone_indices],
        })
    payload['zone_memberships'] = zone_memberships
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2)+'\n', encoding='utf-8')
    print(f'{len(level.regions)} regions; {len(level.checkpoints)} checkpoints; '
          f'{len(candidates)} declared zone candidates; output={args.output}')


if __name__ == '__main__':
    main()
