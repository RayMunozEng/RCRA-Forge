"""
core/level_assembler.py
Level assembly pipeline for RCRA Forge.

Given a parsed ZoneDef (indexed models and actors with zone-local transforms),
resolves each node's actor → model → mesh and assembles them into
a combined GLB export preserving those placements. Owning runtime zone
transforms are separate and are not inferred here.

Pipeline per SceneNode:
  1. SceneNode.asset_id  → find actor entry in TOC
  2. Parse actor          → get model path string
  3. Resolve model path   → model asset_id via HashLookup
  4. Find + extract model → parse mesh geometry
  5. Apply world transform (rotation matrix + position)
  6. Combine into GLB scene

Limitations:
  - Actors without a .model reference (nav volumes, triggers) are skipped
  - Models not in hashes.txt cannot be resolved by path (skipped)
  - Very large zones may have hundreds of actors — use max_nodes to limit
"""

from dataclasses import dataclass
from typing import Optional

from core.actor  import parse_actor_asset
from core.zone   import ZoneDef, SceneNodeEntry
from core.mesh   import ModelParser

# Re-exported for backwards-compatibility — implementation in exporters/zone_exporter.py
from exporters.zone_exporter import export_zone_glb, zone_short  # noqa: F401


@dataclass
class AssembledNode:
    """One successfully resolved scene node ready for export."""
    entry:       SceneNodeEntry   # original zone entry
    model_path:  str              # resolved .model path
    model_asset_id: int           # TOC asset id of the model
    model:       object           # parsed ModelAsset
    world_matrix: tuple           # 4×4 column-major transform (for GLB)


@dataclass
class AssembledZone:
    """Result of assembling a zone — list of placed model instances."""
    zone:        ZoneDef
    nodes:       list             # list of AssembledNode
    skipped:     list             # list of (SceneNodeEntry, reason) for skipped nodes

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def skip_count(self) -> int:
        return len(self.skipped)


class LevelAssembler:
    """
    Resolves zone scene nodes to model assets and retains zone-local transforms.

    Usage:
        assembler = LevelAssembler(toc_parser, lookup)
        result = assembler.assemble_zone(zone, max_nodes=50)
        # result.nodes → list of AssembledNode ready for GLB export
    """

    def __init__(self, toc_parser, lookup):
        self.toc    = toc_parser
        self.lookup = lookup
        self._model_cache = {}   # asset_id → ModelAsset (avoid re-parsing)
        self._actor_cache = {}   # asset_id → ActorAsset

    def assemble_zone(self, zone: ZoneDef,
                      max_nodes: Optional[int] = None,
                      progress_cb=None) -> AssembledZone:
        """Resolve each entry's actual model or actor reference, preserving order."""
        entries = zone.entries[:max_nodes] if max_nodes else zone.entries
        nodes, skipped = [], []
        for index, entry in enumerate(entries):
            if progress_cb:
                progress_cb(index + 1, len(entries))
            try:
                model_id = entry.model_id
                model_path = self.lookup.name(model_id) if self.lookup and model_id else ''
                if not model_id:
                    if not entry.asset_id:
                        skipped.append((entry, 'no actor or model asset reference'))
                        continue
                    # Non-model scene types must not borrow another actor's model.
                    if entry.node_type != 0:
                        skipped.append((entry, f'actor scene type {entry.node_type} is not a model'))
                        continue
                    if entry.asset_id not in self._actor_cache:
                        actor_entry = self.toc.find_entry(entry.asset_id)
                        if actor_entry is None:
                            skipped.append((entry, f'actor not in TOC ({entry.asset_id:#018x})'))
                            continue
                        self._actor_cache[entry.asset_id] = parse_actor_asset(
                            self.toc.extract_asset(actor_entry), self.lookup)
                    actor = self._actor_cache[entry.asset_id]
                    if actor is None or not actor.has_model or not actor.model_asset_id:
                        skipped.append((entry, 'actor has no resolved model reference'))
                        continue
                    model_id, model_path = actor.model_asset_id, actor.model_path
                if model_id not in self._model_cache:
                    model_entry = self.toc.find_entry(model_id)
                    if model_entry is None:
                        skipped.append((entry, f'model not in TOC ({model_id:#018x})'))
                        continue
                    self._model_cache[model_id] = ModelParser(
                        self.toc.extract_asset(model_entry)).parse()
                nodes.append(AssembledNode(
                    entry=entry, model_path=model_path, model_asset_id=model_id,
                    model=self._model_cache[model_id], world_matrix=_build_matrix(entry)))
            except Exception as exc:
                skipped.append((entry, f'asset resolution failed: {exc}'))
        return AssembledZone(zone=zone, nodes=nodes, skipped=skipped)


def _build_matrix(entry: SceneNodeEntry) -> tuple:
    """
    Build a column-major 4×4 transform matrix from a SceneNodeEntry.
    Returns a 16-element tuple of plain Python floats for glTF node.matrix.

    GP zones:  entry.rot = full 9-float row-major 3×3 rotation matrix
    Retail model nodes supply the full row-vector matrix. Its flat row-major
    sequence is already the equivalent column-major glTF matrix: retain all
    three axes, nonuniform scale, reflection and translation without transposing.
    Other callers without a matrix retain the legacy rotation fallback.
    """
    if entry.matrix:
        return tuple(float(value) for value in entry.matrix)
    x, y, z = float(entry.x), float(entry.y), float(entry.z)

    # Check if rot is a valid 3×3 (all values in [-1, 1] range)
    # Art zone rot[3..8] contain position/scale data (large values) — detect this
    r = [float(v) for v in entry.rot]
    x, y, z = float(entry.x), float(entry.y), float(entry.z)

    if all(abs(v) <= 1.001 for v in r):
        # Full valid 3×3 rotation — GP zone (row-major → column-major 4×4)
        return (
            r[0], r[3], r[6], 0.0,
            r[1], r[4], r[7], 0.0,
            r[2], r[5], r[8], 0.0,
            x,    y,    z,    1.0,
        )
    else:
        # Art zone: only rot[0..2] = [cos θ, 0, sin θ] = row 0 of Y-axis rotation
        # Reconstruct full 3×3 Y-axis rotation matrix:
        #   row0 = [ cos θ,  0, sin θ]
        #   row1 = [   0,    1,   0  ]
        #   row2 = [-sin θ,  0, cos θ]
        import math
        # Normalise row 0 in case of floating point drift
        c = float(r[0])   # cos θ
        s = float(r[2])   # sin θ  (r[1] is always 0 for Y-axis rotation)
        length = math.sqrt(c*c + s*s)
        if length > 1e-6:
            c /= length
            s /= length
        else:
            c, s = 1.0, 0.0   # identity fallback

        # Full Y-axis rotation matrix (row-major):
        #   [c,  0,  s]
        #   [0,  1,  0]
        #   [-s, 0,  c]
        # Convert row-major → column-major for glTF:
        return (
            c,   0.0,  -s,  0.0,   # col 0
            0.0, 1.0,  0.0, 0.0,   # col 1
            s,   0.0,  c,   0.0,   # col 2
            x,   y,    z,   1.0,   # col 3
        )

