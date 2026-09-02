"""Correlate RCRA material-header words with graph strings and asset paths."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import struct
import sys


TAG_MATERIAL_HEADER = 0xE1275683
TAG_FUR_MATERIAL = 0xD9B12454


def header_record(asset_id: int, path: str, raw: bytes) -> dict[str, object]:
    from core.archive import DAT1
    from core.material import parse_material_asset

    dat1 = DAT1(raw)
    section = dat1.get_section(TAG_MATERIAL_HEADER)
    if section is None:
        words: tuple[int, ...] = ()
    else:
        data = bytes(section)
        words = struct.unpack_from(f"<{len(data) // 4}I", data)
    parsed = parse_material_asset(raw)
    return {
        "asset_id": f"{asset_id:016X}",
        "path": path.replace("\\", "/"),
        "asset_type": dat1.asset_type,
        "header_size": len(section) if section is not None else 0,
        "header_words": [f"{word:08X}" for word in words],
        "word3_string": dat1.get_string(words[3]) if len(words) > 3 else None,
        "word4_string": dat1.get_string(words[4]) if len(words) > 4 else None,
        "graph_path": parsed.graph_path,
        "is_fur": TAG_FUR_MATERIAL in dat1.sections,
        "section_tags": [f"{tag:08X}" for tag in dat1.sections],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--game-root", type=Path, required=True,
        help="Rift Apart installation directory containing toc",
    )
    parser.add_argument(
        "--hashes", type=Path,
        help="Hash list; defaults to the repository hashes.txt",
    )
    parser.add_argument("--scan-all", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    forge_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(forge_root))
    from core.archive import TocParser
    from core.hashes import HashLookup

    hashes = args.hashes or forge_root / "hashes.txt"
    output = args.output or forge_root / "material-header-correlation.json"
    toc_path = args.game_root / "toc"
    if not toc_path.is_file():
        parser.error(f"game root does not contain toc: {args.game_root}")
    if not hashes.is_file():
        parser.error(f"hash list does not exist: {hashes}")
    lookup = HashLookup()
    lookup.load(str(hashes))
    toc = TocParser(str(toc_path))
    toc.parse()

    known_paths = {
        "material/character/npc/npc_sheep/npc_sheep_fur.material",
        "material/characters/hero/hero_ratchet_head/hero_ratchet_head_fur.material",
        "material/characters/hero/hero_ratchet_head/hero_ratchet_head_fur_ear_l.material",
        "material/characters/hero/hero_ratchet_head/hero_rivet_head_fur.material",
        "material/characters/npc/npc_schrodinger_critter/npc_schrodinger_critter_fur.material",
        "material/characters/hero/hero_shared_mouth/hero_shared_mouth.material",
        "material/characters/hero/hero_ratchet_cowl/hero_ratchet_cowl.material",
    }
    candidates = {
        asset_id: path
        for asset_id, path in lookup._map.items()
        if path.casefold().endswith(".material")
        and (args.scan_all or path.replace("\\", "/").casefold() in known_paths)
    }
    toc_ids = toc.entries._ids[: len(toc.entries)]
    installed = [
        (index, int(asset_id), candidates[int(asset_id)])
        for index, asset_id in enumerate(toc_ids)
        if int(asset_id) in candidates
    ]
    if args.limit:
        installed = installed[: args.limit]
    print(f"candidates={len(candidates)} installed={len(installed)}", flush=True)

    records: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for number, (index, asset_id, path) in enumerate(installed, 1):
        try:
            # Archive extraction logs compression details per asset. Suppress
            # that mechanical noise so long correlation scans expose progress.
            with redirect_stdout(io.StringIO()):
                raw = toc.extract_asset(toc.entries[index])
            records.append(header_record(asset_id, path, raw))
        except Exception as exc:
            errors.append({"asset_id": f"{asset_id:016X}", "path": path, "error": str(exc)})
        if args.scan_all and number % 500 == 0:
            print(f"scanned {number}/{len(installed)}", flush=True)

    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for record in records:
        words = record["header_words"]
        key = (words[3], words[4]) if len(words) >= 5 else ("", "")
        groups[key].append(record)
    group_summary = []
    for key, members in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        group_summary.append(
            {
                "word3": key[0],
                "word4": key[1],
                "count": len(members),
                "fur_count": sum(bool(member["is_fur"]) for member in members),
                "graph_paths": dict(Counter(str(member["graph_path"]) for member in members)),
                "examples": [member["path"] for member in members[:12]],
            }
        )

    payload = {
        "candidate_count": len(candidates),
        "installed_count": len(installed),
        "record_count": len(records),
        "groups": group_summary,
        "records": records,
        "errors": errors,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for record in records:
        words = record["header_words"]
        pair = "/".join(words[3:5]) if len(words) >= 5 else "missing"
        print(f"{pair} fur={int(record['is_fur'])} graph={record['graph_path']} {record['path']}")
        print(f"  word3_string={record['word3_string']!r} word4_string={record['word4_string']!r}")
    print(f"records={len(records)} errors={len(errors)} output={output}")


if __name__ == "__main__":
    main()
