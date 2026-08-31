"""Extract and inventory shipped RCRA material-graph shader containers.

This tool is intentionally read-only with respect to the installed game.  It
resolves materialgraph paths through RCRA Forge's hash dictionary, extracts the
corresponding DAT1 assets, and writes decoded metadata plus individual DXBC
containers into a repository-local output directory for disassembly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import struct
import sys


DEFAULT_GRAPHS = (
    "required/materials/basic_normal_gloss.materialgraph",
    "materialgraph/environment/blizarprime/ground/blz_gbl_lava_01_flow/"
    "blz_gbl_lava_01_flow.materialgraph",
)


def _normalized(value: str) -> str:
    return value.replace("\\", "/").casefold().lstrip("/")


def _strings(data: bytes, minimum: int = 4) -> list[str]:
    result: list[str] = []
    start = None
    for index, value in enumerate(data + b"\0"):
        if 0x20 <= value < 0x7F:
            if start is None:
                start = index
        elif start is not None:
            if index - start >= minimum:
                result.append(data[start:index].decode("ascii", errors="replace"))
            start = None
    return result


def _dxbc_containers(data: bytes) -> list[dict[str, object]]:
    containers: list[dict[str, object]] = []
    cursor = 0
    while True:
        offset = data.find(b"DXBC", cursor)
        if offset < 0:
            break
        cursor = offset + 4
        if offset + 32 > len(data):
            continue
        one, total_size, chunk_count = struct.unpack_from("<III", data, offset + 20)
        if one != 1 or total_size < 32 or offset + total_size > len(data):
            continue
        table_end = offset + 32 + chunk_count * 4
        if chunk_count == 0 or chunk_count > 128 or table_end > offset + total_size:
            continue
        chunk_offsets = struct.unpack_from(f"<{chunk_count}I", data, offset + 32)
        chunks: list[dict[str, object]] = []
        valid = True
        for chunk_offset in chunk_offsets:
            absolute = offset + chunk_offset
            if absolute + 8 > offset + total_size:
                valid = False
                break
            tag = data[absolute:absolute + 4].decode("ascii", errors="replace")
            size = struct.unpack_from("<I", data, absolute + 4)[0]
            if absolute + 8 + size > offset + total_size:
                valid = False
                break
            chunks.append({"tag": tag, "size": size, "offset": chunk_offset})
        if not valid:
            continue
        payload = data[offset:offset + total_size]
        containers.append(
            {
                "offset": offset,
                "size": total_size,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "chunks": chunks,
                "data": payload,
            }
        )
    return containers


def _parameter_table(dat1) -> list[dict[str, object]]:
    keys = dat1.get_section(0x45C4F4C0)
    values = dat1.get_section(0xA59F667B)
    if keys is None or values is None:
        return []
    value_bytes = bytes(values)
    parameters: list[dict[str, object]] = []
    for index in range(len(keys) // 8):
        offset, size, key = struct.unpack_from("<HHI", keys, index * 8)
        raw = value_bytes[offset:offset + size]
        item: dict[str, object] = {
            "index": index,
            "key": f"{key:08X}",
            "offset": offset,
            "size": size,
            "hex": raw.hex(),
        }
        if size and size % 4 == 0:
            item["float32"] = list(struct.unpack(f"<{size // 4}f", raw))
            item["uint32"] = list(struct.unpack(f"<{size // 4}I", raw))
        parameters.append(item)
    return parameters


def _texture_table(dat1) -> list[dict[str, object]]:
    section = dat1.get_section(0x1CAFE804)
    if section is None:
        return []
    textures: list[dict[str, object]] = []
    for index in range(len(section) // 16):
        string_offset, a, b, slot_hash, texture_hash = struct.unpack_from(
            "<IHHII", section, index * 16
        )
        textures.append(
            {
                "index": index,
                "name": dat1.get_string(string_offset),
                "a": a,
                "b": b,
                "slot_hash": f"{slot_hash:08X}",
                "texture_hash": f"{texture_hash:08X}",
            }
        )
    return textures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--hashes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fxc", type=Path)
    parser.add_argument("--dxc", type=Path)
    parser.add_argument("graphs", nargs="*", default=DEFAULT_GRAPHS)
    args = parser.parse_args()

    forge_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(forge_root))
    os.chdir(forge_root)

    from core.archive import DAT1, TocParser
    from core.hashes import HashLookup

    toc = TocParser(str(args.game_root / "toc"))
    toc.parse()
    lookup = HashLookup()
    lookup.load(str(args.hashes))
    reverse = {_normalized(path): asset_id for asset_id, path in lookup._map.items()}

    args.output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"graphs": []}
    seen: set[str] = set()

    for requested_path in args.graphs:
        normalized = _normalized(requested_path)
        asset_id = reverse.get(normalized)
        if asset_id is None:
            suffix_matches = [
                (path, candidate_id)
                for path, candidate_id in reverse.items()
                if path.endswith(normalized)
            ]
            if len(suffix_matches) == 1:
                normalized, asset_id = suffix_matches[0]
        if asset_id is None:
            raise RuntimeError(f"No hash entry for {requested_path}")
        entry = toc.find_entry(asset_id)
        if entry is None:
            raise RuntimeError(f"No installed TOC entry for {requested_path}")

        raw = toc.extract_asset(entry)
        dat1 = DAT1(raw)
        graph_dir = args.output / f"{asset_id:016X}"
        graph_dir.mkdir(parents=True, exist_ok=True)
        (graph_dir / "asset.dat1").write_bytes(raw)

        graph_info: dict[str, object] = {
            "path": lookup.lookup(asset_id) or normalized,
            "asset_id": f"{asset_id:016X}",
            "asset_type": f"{dat1.unk1:08X}",
            "size": len(raw),
            "parameters": _parameter_table(dat1),
            "textures": _texture_table(dat1),
            "sections": [],
            "containers": [],
        }
        for tag, section_view in dat1.sections.items():
            section = bytes(section_view)
            graph_info["sections"].append(
                {
                    "tag": f"{tag:08X}",
                    "size": len(section),
                    "strings": _strings(section)[:200],
                }
            )
            for container in _dxbc_containers(section):
                digest = str(container["sha256"])
                if digest in seen:
                    continue
                seen.add(digest)
                filename = (
                    f"{tag:08X}-{int(container['offset']):08X}-"
                    f"{digest[:12]}.dxbc"
                )
                (graph_dir / filename).write_bytes(container.pop("data"))
                chunk_tags = {chunk["tag"] for chunk in container["chunks"]}
                disassembler = args.dxc if "DXIL" in chunk_tags else args.fxc
                if disassembler:
                    command = (
                        [str(disassembler), "-dumpbin", str(graph_dir / filename)]
                        if "DXIL" in chunk_tags
                        else [
                            str(disassembler),
                            "/dumpbin",
                            "/nologo",
                            str(graph_dir / filename),
                        ]
                    )
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                    )
                    assembly_name = Path(filename).with_suffix(".asm.txt").name
                    (graph_dir / assembly_name).write_text(
                        result.stdout + result.stderr, encoding="utf-8"
                    )
                    container["disassembly"] = assembly_name
                    container["disassembler_exit_code"] = result.returncode
                container["section"] = f"{tag:08X}"
                container["file"] = filename
                graph_info["containers"].append(container)
        manifest["graphs"].append(graph_info)

    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(manifest_path)
    for graph in manifest["graphs"]:
        print(
            f"{graph['asset_id']} {graph['path']}: "
            f"{len(graph['containers'])} unique DXBC containers"
        )


if __name__ == "__main__":
    main()
