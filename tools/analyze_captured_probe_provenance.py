"""Join captured Hair probe identity to cooked level and zone evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level-file', type=Path, required=True)
    parser.add_argument('--zone-directory', type=Path, required=True)
    parser.add_argument('--placement-report', type=Path, required=True)
    parser.add_argument('--asset-match-report', type=Path, required=True)
    parser.add_argument('--scene-bundle', type=Path, required=True)
    parser.add_argument('--dependency-zone-index', action='append', type=int, default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.environment_probes import parse_zone_environment_probes
    from core.level import LevelParser

    level = LevelParser(args.level_file.read_bytes()).parse_info()
    placement = json.loads(args.placement_report.read_text(encoding='utf-8'))
    asset_matches = json.loads(args.asset_match_report.read_text(encoding='utf-8'))
    if placement['capture'] != asset_matches['capture'] or placement['event'] != asset_matches['event']:
        parser.error('Capture and event differ between the two input reports')
    if placement['active_cube'] != asset_matches['active_cube']:
        parser.error('Active cube differs between the two input reports')
    if not placement.get('active_first_124_bytes_exact'):
        parser.error('Placement report does not establish the active record byte match')

    active_record = placement['active_record']
    record_matches = [item for item in placement['records_matching_identity']
                      if item['record'] == active_record]
    if len(record_matches) != 1 or len(record_matches[0]['matches']) != 1:
        parser.error('Active captured probe record is not uniquely matched')
    captured = record_matches[0]
    match = captured['matches'][0]
    if not match.get('byte_exact_before_z_bin'):
        parser.error('Active probe does not have an identity-placement byte match')

    zone_id = int(match['zone_id'], 16)
    catalogue = [zone.table_index for zone in level.zones if zone.asset_id == zone_id]
    if len(catalogue) != 1:
        parser.error(f'Active zone {zone_id:016X} has {len(catalogue)} level catalogue matches')
    zone_index = catalogue[0]
    zone_path = args.zone_directory / f'{zone_id:016X}.dat1'
    probes = parse_zone_environment_probes(zone_path.read_bytes())
    if not 0 <= match['probe_index'] < len(probes):
        parser.error('Active probe index is outside its zone')
    probe = probes[match['probe_index']]
    if probe.instance_id != int(match['instance_id'], 16) or probe.source != match['source']:
        parser.error('Parsed zone probe disagrees with the capture placement match')

    memberships = []
    for region in level.regions:
        if zone_index not in region.zone_indices:
            continue
        parent = level.regions[region.parent_index] if region.parent_index >= 0 else None
        bounds = struct.unpack('<3f3I', region.bounds_data) if region.bounds_data else None
        memberships.append({
            'region_index': region.index,
            'kind': region.kind,
            'name': region.name,
            'parent_index': region.parent_index,
            'kind_4_parent_child_ordinal': (
                parent.child_indices.index(region.index) if parent is not None and parent.kind == 4 else None
            ),
            'bounds_index': region.bounds_index,
            'bounds_float3_uint3': bounds,
        })

    cube_to_baked = {item['cube']: item['matches'] for item in asset_matches['cubes']}
    active_cube = placement['active_cube']
    with np.load(args.scene_bundle, allow_pickle=False) as scene:
        records = np.asarray(scene['probe_records'])
        lookup = np.asarray(scene['probe_lookup'])
    if records.ndim != 2 or records.shape[1] != 128 or records.dtype != np.uint8:
        parser.error('Scene bundle probe table is not an Nx128 uint8 array')
    if not 0 <= active_record < len(records):
        parser.error('Active record is outside the scene bundle probe table')
    bundle_cube = float(records[active_record].view('<f4')[15])
    if bundle_cube != active_cube:
        parser.error(f'Scene bundle record {active_record} selects cube {bundle_cube}, expected {active_cube}')
    word, bit = divmod(active_record, 32)
    if lookup.ndim != 3 or word >= lookup.shape[0] or lookup.dtype != np.uint32:
        parser.error('Scene bundle probe lookup cannot address the active record')
    active_tile_count = int(np.count_nonzero(lookup[word] & np.uint32(1 << bit)))
    if active_tile_count == 0:
        parser.error('Scene bundle tile lookup never selects the active record')
    dependencies = []
    for dependency_index in args.dependency_zone_index:
        if not 0 <= dependency_index < len(level.zones):
            parser.error(f'Invalid dependency zone index {dependency_index}')
        dependency = level.zones[dependency_index]
        dependency_path = args.zone_directory / f'{dependency.asset_id:016X}.dat1'
        dependency_probes = parse_zone_environment_probes(dependency_path.read_bytes())
        captured_textures = []
        for item in dependency_probes:
            for texture in item.textures:
                for cube, matches in cube_to_baked.items():
                    if any(int(candidate['asset_id'], 16) == texture.asset_id for candidate in matches):
                        captured_textures.append({
                            'probe_instance_id': f'{item.instance_id:016X}',
                            'texture_asset_id': f'{texture.asset_id:016X}',
                            'texture_path': texture.path,
                            'condition_id': f'{texture.condition_id:08X}',
                            'captured_cube': cube,
                            'is_active_cube': cube == active_cube,
                        })
        dependencies.append({
            'zone_index': dependency_index,
            'zone_asset_id': f'{dependency.asset_id:016X}',
            'zone_name': dependency.name,
            'captured_baked_textures': captured_textures,
        })

    payload = {
        'scope': 'captured_probe_identity_and_identity_placement_joined_to_cooked_level_topology',
        'capture': placement['capture'],
        'event': placement['event'],
        'evidence': {
            'level_file': {'path': str(args.level_file), 'sha256': sha256(args.level_file)},
            'active_zone_file': {'path': str(zone_path), 'sha256': sha256(zone_path)},
            'placement_report': {'path': str(args.placement_report), 'sha256': sha256(args.placement_report)},
            'asset_match_report': {'path': str(args.asset_match_report), 'sha256': sha256(args.asset_match_report)},
            'scene_bundle': {'path': str(args.scene_bundle), 'sha256': sha256(args.scene_bundle)},
        },
        'active_probe': {
            'record': active_record,
            'cube': active_cube,
            'cube_has_installed_baked_asset_match': active_cube in cube_to_baked,
            'catalogue_zone_index': zone_index,
            'zone_asset_id': f'{zone_id:016X}',
            'zone_name': level.zones[zone_index].name,
            'probe_index': match['probe_index'],
            'probe_instance_id': f'{probe.instance_id:016X}',
            'source': probe.source,
            'zone_local_position': probe.position,
            'identity_zone_placement_byte_exact_before_camera_z_bin': True,
            'scene_bundle_record_cube': bundle_cube,
            'scene_bundle_selecting_tile_count': active_tile_count,
            'scene_bundle_probe_record_sha256': hashlib.sha256(records[active_record].tobytes()).hexdigest(),
            'primary_region_memberships': memberships,
        },
        'dependency_zone_baked_capture_matches': dependencies,
        'remaining_runtime_boundary': [
            'the active cube is generated from runtime draw lists and has no installed baked texture match',
            'the capture proves this frame but cooked data alone does not choose future residency or conditions',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(f'active record {active_record} -> cube {active_cube} -> zone {zone_index} -> '
          f'{len(memberships)} primary region membership(s); output={args.output}')


if __name__ == '__main__':
    main()
