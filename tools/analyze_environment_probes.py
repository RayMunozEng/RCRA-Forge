"""Inventory installed zone probe textures and runtime scene draw lists."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root', type=Path, required=True)
    parser.add_argument('--hashes', type=Path)
    parser.add_argument('--zone-filter', action='append', required=True,
                        help='Case-insensitive zone path substring; repeat to include more areas')
    parser.add_argument('--include-draw-ids', action='store_true',
                        help='Include per-face scene instance IDs, which can produce a large report')
    parser.add_argument('--resolve-scene-models', action='store_true',
                        help='Match draw IDs to indexed models in the selected zones; includes draw IDs')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    forge_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(forge_root))
    from core.archive import DAT1, TocParser
    from core.environment_probes import parse_zone_environment_probes
    from core.probe_lighting import probe_sort_key
    from core.hashes import HashLookup
    from core.zone import TAG_ACTOR_INSTANCES, TAG_MODEL_INDICES, ZoneParser
    from core.actor import parse_actor_asset

    toc_path = args.game_root / 'toc'
    hashes = args.hashes or forge_root / 'hashes.txt'
    if not toc_path.is_file() or not hashes.is_file():
        parser.error('Both the installed toc and hash list must exist')
    filters = [value.replace('\\', '/').casefold() for value in args.zone_filter]
    toc = TocParser(str(toc_path))
    toc.parse()
    lookup = HashLookup()
    lookup.load(str(hashes))
    installed_ids = set(map(int, toc.entries._ids[:len(toc.entries)]))
    candidates = sorted(
        (asset_id, path) for asset_id, path in lookup._map.items()
        if asset_id in installed_ids and path.casefold().endswith('.zone')
        and any(value in path.replace('\\', '/').casefold() for value in filters)
    )
    zones = []
    errors = []
    sources = Counter()
    scene_zones = []
    requested_scene_ids = set()
    for number, (asset_id, path) in enumerate(candidates, 1):
        if number % 100 == 0:
            print(f'scanning {number}/{len(candidates)}', flush=True)
        try:
            with redirect_stdout(io.StringIO()):
                raw = toc.extract_asset(toc.find_entry(asset_id))
            if args.resolve_scene_models:
                dat1 = DAT1(raw)
                if dat1.get_section(TAG_MODEL_INDICES) or dat1.get_section(TAG_ACTOR_INSTANCES):
                    scene_zones.append((asset_id, path))
            probes = parse_zone_environment_probes(raw)
            if not probes:
                continue
            records = []
            for probe in probes:
                sources[probe.source] += 1
                lists = []
                for draw_list in probe.draw_lists:
                    item = {'face_counts': [len(face) for face in draw_list.faces]}
                    if args.include_draw_ids or args.resolve_scene_models:
                        item['scene_instance_ids'] = [
                            [f'{value:016X}' for value in face] for face in draw_list.faces
                        ]
                    if args.resolve_scene_models:
                        for face in draw_list.faces:
                            requested_scene_ids.update(face)
                    lists.append(item)
                records.append({
                    'index': probe.index,
                    'instance_id': f'{probe.instance_id:016X}',
                    'zone_local_position': probe.position,
                    'zone_local_axes': probe.axes,
                    'half_extents': probe.half_extents,
                    'capture_offset': probe.capture_offset,
                    'falloff_negative': probe.falloff_negative,
                    'falloff_positive': probe.falloff_positive,
                    'proxy_negative': probe.proxy_negative,
                    'proxy_positive': probe.proxy_positive,
                    'volume_shape': probe.volume_shape,
                    'diffuse_flags': probe.diffuse_flags,
                    'priority': probe.priority,
                    'runtime_sort_key_descending': probe_sort_key(probe),
                    'source': probe.source,
                    'texture_index': probe.texture_index,
                    'draw_list_index': probe.draw_list_index,
                    'textures': [{
                        'asset_id': f'{texture.asset_id:016X}',
                        'path': texture.path,
                        'condition_id': (f'{texture.condition_id:08X}'
                                         if texture.condition_id is not None else None),
                        'installed': texture.asset_id in installed_ids,
                    } for texture in probe.textures],
                    'draw_lists': lists,
                })
            zones.append({'asset_id': f'{asset_id:016X}', 'path': path, 'probes': records})
        except Exception as exc:
            errors.append({'asset_id': f'{asset_id:016X}', 'path': path, 'error': str(exc)})
    payload = {
        'zone_filters': args.zone_filter,
        'scanned_zone_count': len(candidates),
        'zone_count_with_probes': len(zones),
        'probe_source_counts': dict(sources),
        'coordinate_space': 'zone_local_before_runtime_zone_transform',
        'draw_id_kind': 'scene_instance_id_not_model_asset_id',
        'zones': zones,
        'errors': errors,
    }
    if args.resolve_scene_models:
        matches = {}
        model_node_count = 0
        model_zone_count = 0
        actor_node_count = 0
        component_binding_count = 0
        actor_cache = {}
        unresolved_actor_models = []
        scene_errors = []
        for number, (asset_id, path) in enumerate(scene_zones, 1):
            if number % 50 == 0:
                print(f'resolving scene zones {number}/{len(scene_zones)}', flush=True)
            try:
                with redirect_stdout(io.StringIO()):
                    raw = toc.extract_asset(toc.find_entry(asset_id))
                zone = ZoneParser(raw, lookup).parse(asset_id, path)
                model_node_count += sum(bool(node.model_id) for node in zone.entries)
                model_zone_count += any(node.model_id for node in zone.entries)
                actor_node_count += sum(bool(node.asset_id) for node in zone.entries)
                component_binding_count += sum(len(node.components) for node in zone.entries)
                model_paths = dict(zip(zone.model_ids, zone.model_paths))
                for node in zone.entries:
                    renderer_id = node.renderer_instance_id
                    if renderer_id not in requested_scene_ids or not renderer_id:
                        continue
                    model_id = node.model_id
                    model_path = model_paths.get(model_id)
                    actor_fields = {}
                    if node.asset_id:
                        if node.asset_id not in actor_cache:
                            entry = toc.find_entry(node.asset_id)
                            with redirect_stdout(io.StringIO()):
                                actor_cache[node.asset_id] = (
                                    parse_actor_asset(toc.extract_asset(entry), lookup) if entry else None)
                        actor = actor_cache[node.asset_id]
                        if actor is None or not actor.model_asset_id:
                            unresolved_actor_models.append({
                                'scene_instance_id': f'{renderer_id:016X}',
                                'zone_asset_id': f'{asset_id:016X}',
                                'actor_asset_id': f'{node.asset_id:016X}',
                                'actor_installed': node.asset_id in installed_ids,
                            })
                            continue
                        model_id, model_path = actor.model_asset_id, actor.model_path
                        actor_fields = {
                            'actor_asset_id': f'{node.asset_id:016X}',
                            'actor_instance_id': f'{node.instance_id:016X}',
                            'actor_path': node.actor_path,
                            'component_override_count': len(node.components),
                        }
                    matches.setdefault(f'{renderer_id:016X}', []).append({
                        'source': 'actor' if node.asset_id else 'model',
                        'zone_asset_id': f'{asset_id:016X}', 'zone_path': path,
                        'scene_offset': node.scene_offset,
                        'model_asset_id': f'{model_id:016X}',
                        'model_path': model_path,
                        'model_installed': model_id in installed_ids,
                        'zone_local_matrix': node.matrix,
                        **actor_fields,
                    })
            except Exception as exc:
                scene_errors.append({'asset_id': f'{asset_id:016X}', 'path': path,
                                     'error': str(exc)})
        requested = {f'{value:016X}' for value in requested_scene_ids}
        payload['scene_model_resolution'] = {
            'coordinate_space': 'zone_local_before_runtime_zone_transform',
            'selection': 'all_matching_cooked_candidates_not_runtime_residency',
            'scene_zone_count': len(scene_zones), 'model_zone_count': model_zone_count,
            'model_node_count': model_node_count, 'actor_node_count': actor_node_count,
            'component_override_count': component_binding_count,
            'requested_unique_scene_ids': len(requested),
            'matched_unique_scene_ids': len(matches),
            'ambiguous_unique_scene_ids': sum(len(values) > 1 for values in matches.values()),
            'unresolved_scene_ids': sorted(requested - matches.keys()),
            'matches': matches, 'unresolved_actor_models': unresolved_actor_models,
            'errors': scene_errors,
        }
        for zone in zones:
            for probe in zone['probes']:
                for draw in probe['draw_lists']:
                    draw['matched_model_counts'] = [
                        sum(value in matches for value in face)
                        for face in draw['scene_instance_ids']
                    ]
        print(f'scene IDs matched={len(matches)}/{len(requested)} '
              f'model nodes={model_node_count} errors={len(scene_errors)}', flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(f'zones={len(zones)} sources={dict(sources)} errors={len(errors)} output={args.output}')
    if errors or (args.resolve_scene_models and scene_errors):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
