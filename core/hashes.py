"""
core/hashes.py
Asset ID → path name lookup table.

Loads the hashes.txt file from Overdrive/ALERT which maps
64-bit CRC64 asset IDs to their original path strings.

Format (CSV, 384k+ entries):
  80000DCC5F02623C,cinematics/corv_cine/.../foo.animclip,1

The third column is a game version indicator (1=MSMR/MM, 2=RCRA etc.)
We load all entries since many assets are shared across games.
"""

import os
import struct
import re
from typing import Optional


class HashLookup:
    """
    Fast asset ID → path lookup.
    Loads hashes.txt once and keeps it in memory as a dict.
    """

    def __init__(self):
        self._map: dict[int, str] = {}
        self._loaded = False
        self._path: Optional[str] = None

    def load(self, hashes_path: str) -> int:
        """
        Load a hashes.txt file. Returns number of entries loaded.
        Saves a binary cache (.hashes_cache) next to the file for fast
        subsequent loads — first load ~1s, subsequent loads ~0.1s.
        """
        if self._loaded and self._path == hashes_path:
            return len(self._map)

        self._map.clear()
        if hasattr(self, '_reverse_map'):
            del self._reverse_map
        self._loaded = False
        self._path = hashes_path

        cache_path = hashes_path + '.cache'

        # Try loading from binary cache first
        try:
            if os.path.exists(cache_path):
                txt_mtime   = os.path.getmtime(hashes_path)
                cache_mtime = os.path.getmtime(cache_path)
                if cache_mtime >= txt_mtime:
                    import pickle
                    with open(cache_path, 'rb') as f:
                        self._map = pickle.load(f)
                    self._loaded = True
                    return len(self._map)
        except Exception:
            pass  # Cache corrupt or unreadable — fall through to full parse

        # Full parse from text file
        try:
            with open(hashes_path, 'rb') as f:
                raw = f.read()

            text  = raw.decode('utf-8', errors='replace')
            del raw
            lines = text.splitlines()
            del text

            result = {}
            for line in lines:
                if not line:
                    continue
                c1 = line.find(',')
                if c1 < 0:
                    continue
                c2 = line.find(',', c1 + 1)
                try:
                    result[int(line[:c1], 16)] = \
                        line[c1+1:c2 if c2 > 0 else None].replace('\\', '/')
                except ValueError:
                    continue

            self._map    = result
            self._loaded = True

            # Save binary cache for next time
            try:
                import pickle
                with open(cache_path, 'wb') as f:
                    pickle.dump(self._map, f, protocol=pickle.HIGHEST_PROTOCOL)
            except Exception:
                pass  # Cache write failed — not critical

        except Exception as e:
            print(f"[HashLookup] Failed to load {hashes_path}: {e}")

        return len(self._map)

    def lookup(self, asset_id: int) -> Optional[str]:
        """Return the path string for an asset ID, or None if not found."""
        return self._map.get(asset_id)

    def name(self, asset_id: int) -> str:
        """
        Return a short display name for an asset ID.
        Falls back to the hex ID if not found.
        e.g. 'npc_zurkon_jr.model' instead of '94A4B69B67D5CC42'
        """
        path = self._map.get(asset_id)
        if path:
            return os.path.basename(path)
        return f"{asset_id:016X}"

    def full_path(self, asset_id: int) -> str:
        """Return full path or hex ID fallback."""
        return self._map.get(asset_id, f"{asset_id:016X}")

    def asset_id(self, path: str) -> Optional[int]:
        """
        Reverse lookup: given a path string, return the asset ID (CRC64 hash).
        Case-insensitive — hashes.txt stores lowercase paths.
        """
        def _normalize(value: str) -> str:
            return re.sub(r'/+', '/', value.replace('\\', '/')).casefold().lstrip('/')

        if not hasattr(self, '_reverse_map'):
            self._reverse_map = {_normalize(v): k for k, v in self._map.items()}
        return self._reverse_map.get(_normalize(path))

    def is_loaded(self) -> bool:
        return self._loaded

    def __len__(self) -> int:
        return len(self._map)

    @staticmethod
    def find_hashes_file(game_root: str) -> Optional[str]:
        """
        Search for hashes.txt near the game folder.
        Checks the game folder itself and common Overdrive/ALERT locations.
        """
        candidates = [
            # Same folder as the game
            os.path.join(game_root, 'hashes.txt'),
            # One level up (Steam library root)
            os.path.join(os.path.dirname(game_root), 'hashes.txt'),
            # Overdrive install locations
            os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming',
                         'Overstrike', 'hashes.txt'),
            # Next to the RCRA Forge exe
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hashes.txt'),
        ]
        return next((p for p in candidates if os.path.exists(p)), None)


# Global singleton
_lookup = HashLookup()


def get_lookup() -> HashLookup:
    return _lookup


def try_load_from_game_root(game_root: str) -> bool:
    """Try to find and load hashes.txt relative to the game folder."""
    path = HashLookup.find_hashes_file(game_root)
    if path:
        count = _lookup.load(path)
        print(f"[HashLookup] Loaded {count:,} hashes from {path}")
        return True
    return False
