"""Validate the retail region selectors and report their cooked inputs.

This is a read-only static decoder. It checks exact instruction anchors in a
saved executable disassembly, then combines that evidence with an extracted
level DAT1. Runtime bitset contents and the current runtime region are outside
the cooked file and are deliberately left unresolved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


SELECTION_ANCHORS = {
    'selected_region_must_be_kind_4': '14199d110: cmp eax, 4',
    'child_count_accessor': '14199d123: call 0x14107cff0',
    'child_start_accessor': '14199d149: call 0x14107d030',
    'runtime_record_stride_0x60': '14199d285: add r14, 0x60',
    'child_record_constructor': '14199d1ee: call 0x14199cdd0',
    'aggregate_retained_mask_offset_0x20': '14199d225: mov rax, qword ptr [rdi + rax*8 + 0x20]',
    'aggregate_new_mask_offset_0x7a0': '14199d267: mov rcx, qword ptr [rdx + 0x7a0]',
    'runtime_selected_region_source_0x1158': '14199dce2: mov ebx, dword ptr [rax + 0x1158]',
}

CONSTRUCTOR_ANCHORS = {
    'first_filter_mask_test': '14199cf3b: test qword ptr [rdi + rax*8], r9',
    'second_filter_mask_test': '14199cf41: test qword ptr [rbx + rax*8], r9',
    'first_partition_test': '14199cf8d: test qword ptr [rdi + rax*8], r8',
    'second_partition_exclusion': '14199cf93: test qword ptr [rbx + rax*8], r8',
}

ACCESSOR_ANCHORS = {
    'kind_field_s16_at_0x08': '14107d454: movsx eax, word ptr [rax + rdx*4 + 8]',
    'child_start_field_s16_at_0x10': '14107d044: movsx eax, word ptr [rax + rdx*4 + 0x10]',
    'child_count_field_s16_at_0x12': '14107d008: movsx r9d, word ptr [rax + rdx*4 + 0x12]',
    'primary_zone_start_field_s16_at_0x14': '14107d4b4: movsx r8, word ptr [rax + rdx*4 + 0x14]',
    'primary_zone_count_field_s16_at_0x16': '14107d484: movsx r9d, word ptr [rax + rdx*4 + 0x16]',
}

DEPENDENCY_ANCHORS = {
    'resolve_region_from_input': '1419a1ac0: call 0x14107d190',
    'kind_3_or_5_gate_begin': '1419a1adb: add eax, -3',
    'kind_3_or_5_gate_mask': '1419a1ade: test eax, 0xfffffffd',
    'immediate_parent_accessor': '1419a1aef: call 0x14107d310',
    'parent_first': '1419a1af4: mov dword ptr [rsp + 0x20], eax',
    'selected_second': '1419a1af8: mov dword ptr [rsp + 0x24], ebx',
    'primary_zone_count_accessor': '1419a1b27: call 0x14107d470',
    'primary_zone_list_accessor': '1419a1b36: call 0x14107d4a0',
    'existing_mask_test': '1419a1b86: bt rax, rdx',
    'two_region_limit': '1419a1bed: cmp ebp, 2',
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_anchors(text: str, anchors: dict[str, str], source: Path) -> None:
    missing = [name for name, instruction in anchors.items() if instruction not in text]
    if missing:
        raise ValueError(f'{source}: missing static evidence anchors: {", ".join(missing)}')


def zone_item(level, index: int) -> dict:
    zone = level.zones[index]
    return {'index': index, 'asset_id': f'{zone.asset_id:016X}', 'name': zone.name}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level-file', type=Path, required=True)
    parser.add_argument('--selection-asm', type=Path, required=True)
    parser.add_argument('--constructor-asm', type=Path, required=True)
    parser.add_argument('--accessor-asm', type=Path, required=True)
    parser.add_argument('--dependency-asm', type=Path, required=True)
    parser.add_argument('--root-index', action='append', type=int, default=[])
    parser.add_argument('--region-index', action='append', type=int, default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    selection_text = args.selection_asm.read_text(encoding='utf-8')
    constructor_text = args.constructor_asm.read_text(encoding='utf-8')
    accessor_text = args.accessor_asm.read_text(encoding='utf-8')
    dependency_text = args.dependency_asm.read_text(encoding='utf-8')
    verify_anchors(selection_text, SELECTION_ANCHORS, args.selection_asm)
    verify_anchors(constructor_text, CONSTRUCTOR_ANCHORS, args.constructor_asm)
    verify_anchors(accessor_text, ACCESSOR_ANCHORS, args.accessor_asm)
    verify_anchors(dependency_text, DEPENDENCY_ANCHORS, args.dependency_asm)

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.level import LevelParser

    level = LevelParser(args.level_file.read_bytes()).parse_info()
    available = [region.index for region in level.regions if region.kind == 4]
    selected = args.root_index or available
    for index in selected:
        if not 0 <= index < len(level.regions):
            parser.error(f'Invalid root region index {index}')
        if level.regions[index].kind != 4:
            parser.error(f'Region {index} is kind {level.regions[index].kind}, not kind 4')
    for index in args.region_index:
        if not 0 <= index < len(level.regions):
            parser.error(f'Invalid dependency region index {index}')
        if level.regions[index].kind not in (3, 5):
            parser.error(f'Region {index} is kind {level.regions[index].kind}, not kind 3 or 5')

    roots = []
    for index in selected:
        root = level.regions[index]
        child_refs = [zone for child in root.child_indices for zone in level.regions[child].zone_indices]
        candidates = level.streaming_region_zone_candidates(index)
        root_zones, child_zones = set(root.zone_indices), set(candidates)
        roots.append({
            'region_index': index,
            'asset_id': f'{root.asset_id:016X}',
            'name': root.name,
            'child_region_count': len(root.child_indices),
            'child_primary_zone_reference_count': len(child_refs),
            'unique_unfiltered_child_zone_count': len(candidates),
            'duplicate_child_zone_reference_count': len(child_refs) - len(candidates),
            'root_primary_zone_count': len(root.zone_indices),
            'root_child_zone_overlap_count': len(root_zones & child_zones),
            'children': [
                {
                    'ordinal': ordinal,
                    'region_index': child_index,
                    'kind': level.regions[child_index].kind,
                    'asset_id': f'{level.regions[child_index].asset_id:016X}',
                    'name': level.regions[child_index].name,
                    'primary_zone_indices': list(level.regions[child_index].zone_indices),
                }
                for ordinal, child_index in enumerate(root.child_indices)
            ],
            'unfiltered_zone_candidates': [zone_item(level, zone) for zone in candidates],
        })

    dependency_regions = []
    for index in args.region_index:
        region = level.regions[index]
        candidates = level.dependency_region_zone_candidates(index)
        dependency_regions.append({
            'region_index': index,
            'asset_id': f'{region.asset_id:016X}',
            'name': region.name,
            'kind': region.kind,
            'immediate_parent_index': region.parent_index,
            'unfiltered_unique_zone_count': len(candidates),
            'unfiltered_zone_candidates': [zone_item(level, zone) for zone in candidates],
        })

    payload = {
        'scope': 'static_kind_4_child_primary_lists_before_runtime_bitset_filters',
        'evidence': {
            'level_file': {'path': str(args.level_file), 'sha256': sha256(args.level_file)},
            'selection_disassembly': {
                'path': str(args.selection_asm), 'sha256': sha256(args.selection_asm),
                'anchors': SELECTION_ANCHORS,
            },
            'record_constructor_disassembly': {
                'path': str(args.constructor_asm), 'sha256': sha256(args.constructor_asm),
                'anchors': CONSTRUCTOR_ANCHORS,
            },
            'accessor_disassembly': {
                'path': str(args.accessor_asm), 'sha256': sha256(args.accessor_asm),
                'anchors': ACCESSOR_ANCHORS,
            },
            'dependency_disassembly': {
                'path': str(args.dependency_asm), 'sha256': sha256(args.dependency_asm),
                'anchors': DEPENDENCY_ANCHORS,
            },
        },
        'proven_runtime_layout': {
            'selected_root_kind': 4,
            'selected_root_source_offset': 'runtime state +0x1158',
            'runtime_record_stride_bytes': 0x60,
            'aggregate_retained_bitset_offset': 'manager +0x20',
            'aggregate_new_bitset_offset': 'manager +0x7A0',
            'bitset_bytes': 0x780,
            'bitset_zone_capacity': 0x780 * 8,
        },
        'proven_filter': {
            'input': 'each selected kind-4 root child region primary zone list',
            'partition_0': 'zone absent from both runtime masks',
            'partition_1': 'zone present in first runtime mask and absent from second runtime mask',
            'excluded': 'zone present in second runtime mask',
            'aggregate_retained': 'partition_0 union partition_1',
            'aggregate_new': 'partition_0',
            'root_primary_zone_list_is_not_read_by_this_builder': True,
        },
        'proven_kind_3_5_dependency_path': {
            'input': 'immediate parent primary list followed by selected region primary list',
            'accepted_selected_region_kinds': [3, 5],
            'filter': 'omit zone indices already present in a supplied runtime bitset',
            'runtime_selected_region_is_not_stored_in_the_cooked_level': True,
        },
        'runtime_unknowns': [
            'current selected kind-4 region value at runtime state +0x1158',
            'contents and higher-level names of the two pre-existing zone masks',
            'post-filter active residency and zone transforms',
        ],
        'available_kind_4_root_indices': available,
        'decoded_roots': roots,
        'decoded_dependency_regions': dependency_regions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    anchor_count = len(SELECTION_ANCHORS) + len(CONSTRUCTOR_ANCHORS) + len(ACCESSOR_ANCHORS) + len(DEPENDENCY_ANCHORS)
    print(f'validated {anchor_count} static anchors; decoded {len(roots)} kind-4 roots and '
          f'{len(dependency_regions)} kind-3/5 dependency regions; output={args.output}')


if __name__ == '__main__':
    main()
