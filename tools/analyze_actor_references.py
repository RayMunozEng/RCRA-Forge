"""Find named asset references inside a shipped RCRA actor DAT1."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys


def _strings(data: bytes, minimum: int = 4) -> list[dict[str, object]]:
    result = []
    start = None
    for index, value in enumerate(data + b"\0"):
        if 0x20 <= value < 0x7F:
            if start is None:
                start = index
        elif start is not None:
            if index - start >= minimum:
                result.append(
                    {
                        "offset": start,
                        "value": data[start:index].decode("ascii", errors="replace"),
                    }
                )
            start = None
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--hashes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("actor_id", type=lambda value: int(value, 0))
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
    entry = toc.find_entry(args.actor_id)
    if entry is None:
        raise RuntimeError(f"No installed actor {args.actor_id:016X}")
    raw = toc.extract_asset(entry)
    dat1 = DAT1(raw)

    references = []
    for offset in range(0, len(raw) - 7, 4):
        value = struct.unpack_from("<Q", raw, offset)[0]
        path = lookup.lookup(value)
        if path:
            references.append(
                {"offset": offset, "asset_id": f"{value:016X}", "path": path}
            )
    result = {
        "asset_id": f"{args.actor_id:016X}",
        "path": lookup.lookup(args.actor_id),
        "size": len(raw),
        "asset_type": f"{dat1.unk1:08X}",
        "sections": [
            {"tag": f"{tag:08X}", "size": len(section)}
            for tag, section in dat1.sections.items()
        ],
        "strings": _strings(raw),
        "aligned_asset_references": references,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
