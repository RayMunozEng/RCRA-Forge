"""
core/mesh.py
Ratchet & Clank: Rift Apart PC — model/mesh parser.

Written from ALERT source (dat1lib/types/sections/model/):
  geo.py      — VertexesSection, IndexesSection, x6B855EED_Section
  meshes.py   — MeshesSection, MeshDefinition
  skin.py     — xCCBAFF15_Section (RCRA weights)
  joints.py   — JointsSection, xDCC88A19_Section (transforms)

Key facts:
  - The asset is a DAT1 container (see core/archive.py)
  - DAT1 unk1 = 0x98906B9F  →  'model'
  - Vertex format for RCRA: 16 bytes per vertex, section 0xA98BE69B
      <4h I 2h>   X Y Z W  NXYZ(packed R10G10B10A2)  U V
      positions are fixed-point / 4096.0
      normal XY, tangent X, and both Z signs are packed in NXYZ;
      tangent Y and handedness are packed in W (see the frame decoders below)
      UVs are int16 / 32768.0
  - Index buffer: uint16 values, section 0x0859863D (NOT delta-encoded for RCRA)
  - Second UV channel: section 0x6B855EED, 2×int16 per vertex / 32768.0
  - Vertex colours: section 0x5CBA9DE9, uint32 RGBA per vertex
  - Mesh definitions: section 0x78D9CBDE, 64 bytes each
  - RCRA skin weights: section 0xCCBAFF15, 8 bytes each
    <B B B B  B B B B>  = bone0 bone1 bone2 bone3 weight0 weight1 weight2 weight3
  - Joint definitions: section 0x15DF9D3B, 16 bytes each
  - Joint transforms: section 0xDCC88A19 (3×4 + 4×4 float matrices)
"""

import math
import struct
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from core.archive import DAT1, ASSET_TYPE_NAMES

# ── DAT1 section tags for model assets ───────────────────────────────────────
TAG_INDEXES         = 0x0859863D   # Model Index        — uint16 array
TAG_VERTEXES        = 0xA98BE69B   # Model Std Vert     — 16B per vertex
TAG_UV1             = 0x6B855EED   # Model UV1 Vert     — 4B per vertex (2×int16)
TAG_COLORS          = 0x5CBA9DE9   # Model Col Vert     — 4B per vertex (uint32)
TAG_MESHES          = 0x78D9CBDE   # Model Subset       — 64B each
TAG_LOOK            = 0x06EB7EFC   # Model Look         — LOD/look table (confirmed from ALERT)
TAG_SKIN_BATCH      = 0xC61B1FF5   # Model Skin Batch   — 16B each
TAG_SKIN_DATA       = 0xDCA379A2   # Model Skin Data    — variable
TAG_RCRA_WEIGHTS    = 0xCCBAFF15   # RCRA weights       — 8B per vertex
TAG_JOINTS          = 0x15DF9D3B   # Model Joint        — 16B each
TAG_JOINT_XFORMS    = 0xDCC88A19   # Joint transforms   — (3×4 + 4×4) floats each
TAG_BUILT           = 0x283D0383   # Model Built        — UV scale etc.
TAG_MATERIALS       = 0x3250BB80   # Material name string offsets


# ── Normal decoding (from ALERT geo.py _decode_normal) ────────────────────────

def _decode_normal(norm: int) -> tuple:
    """
    Decode a 32-bit packed normal into (nx, ny, nz).
    Encoding: bits[0:10]=nx, bits[10:20]=ny, bits[20:32]=nz(12b), bit[31]=flip
    From ALERT dat1lib/types/sections/model/geo.py _decode_normal().
    """
    norm = norm & 0xFFFFFFFF
    nx = float(norm & 0x3FF) * 0.00276483595 - math.sqrt(2)
    ny = float((norm >> 10) & 0x3FF) * 0.00276483595 - math.sqrt(2)
    flip = (norm >> 31) == 0

    nxxyy = nx * nx + ny * ny
    nw = 0.0
    try:
        nw = math.sqrt(max(0.0, 1.0 - 0.25 * nxxyy))
    except Exception:
        pass

    nx = nx * nw
    ny = ny * nw
    nz = 1.0 - 0.5 * nxxyy
    if flip:
        nz = -nz

    return (nx, ny, nz)


def _decode_tangent(position_w: int, norm: int) -> tuple:
    """Decode the authored tangent and handedness used by the retail VS.

    The recovered fur vertex shader reads the standard position stream's
    signed W component and the same R10G10B10A2_UNORM value used for normals:
    ``NXYZ[20:30]`` is tangent X, ``abs(W) & 0x3ff`` is tangent Y,
    ``NXYZ[30]`` selects tangent Z's sign, and W's sign is handedness.
    Tangent XYZ uses the same equal-area sphere reconstruction as the normal.
    """
    norm &= 0xFFFFFFFF
    packed_w = abs(int(position_w))
    tx = float((norm >> 20) & 0x3FF) * 0.00276483595 - math.sqrt(2)
    ty = float(packed_w & 0x3FF) * 0.00276483595 - math.sqrt(2)

    txxyy = tx * tx + ty * ty
    tw = math.sqrt(max(0.0, 1.0 - 0.25 * txxyy))
    tx *= tw
    ty *= tw
    tz = 1.0 - 0.5 * txxyy
    if ((norm >> 30) & 1) == 0:
        tz = -tz

    handedness = 1.0 if position_w >= 0 else -1.0
    return (tx, ty, tz, handedness)


def _decode_position_correction(position_w: int) -> float:
    """Decode the small position-quantization term used by the retail VS."""
    exponent = abs(int(position_w)) & 0x7C00
    scaled = float(exponent) * 0.000032
    return 1.0 / (scaled * scaled) if scaled > 0.0 else 0.0


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Vertex:
    x: float; y: float; z: float       # world-space position
    nx: float; ny: float; nz: float    # decoded normal
    u: float;  v: float                # UV channel 0
    tx: float = 1.0; ty: float = 0.0   # decoded authored tangent
    tz: float = 0.0; tw: float = 1.0   # tangent Z + frame handedness
    tq: float = 0.0                     # retail position decode correction
    u1: float = 0.0; v1: float = 0.0  # UV channel 1 (if present)
    r: int = 255; g: int = 255         # vertex colour
    b: int = 255; a: int = 255


@dataclass
class MeshDefinition:
    """One sub-mesh within a model. From ALERT MeshesSection (MSMR/RCRA variant)."""
    mesh_id:           int
    vertex_start:      int
    vertex_count:      int
    index_start:       int
    index_count:       int
    flags:             int    # 0x10 = indices are relative (not offset by vertex_start)
    material_index:    int
    first_skin_batch:  int
    skin_batches_count: int
    first_weight_index: int
    lod_level:         int = 0   # LOD index (0 = highest detail), populated by _parse_look
    look_index:        int = 0   # Look index (0 = primary/default look)

    @property
    def indices_are_relative(self) -> bool:
        return bool(self.flags & 0x10)


@dataclass
class JointDef:
    parent:  int    # -1 = root
    index:   int
    name:    str
    hash:    int


@dataclass
class ModelAsset:
    vertexes:   list[Vertex]
    meshes:     list[MeshDefinition]
    indexes:    list[int]
    joints:     list[JointDef]           = field(default_factory=list)
    # joint transforms: list of (scale3, quat4, pos3) from matrixes34
    joint_positions:  list[tuple] = field(default_factory=list)
    joint_quaternions: list[tuple] = field(default_factory=list)
    joint_scales:     list[tuple] = field(default_factory=list)   # per-bone scale from m34[0:3]
    rcra_weights:     list         = field(default_factory=list)  # per-vertex list of (bone, weight) pairs
    lod_count:        int          = 1    # number of LOD levels detected from Look section
    skin_data:        Optional[bytes] = None
    skin_batches:     list = field(default_factory=list)
    material_names:   list[str]    = field(default_factory=list)  # short name per material index
    source_path:      str          = ''  # resolved asset path, populated by asset_loader


# ── Parser ────────────────────────────────────────────────────────────────────

class ModelParser:
    """
    Parse a raw model asset blob (DAT1 container) into a ModelAsset.

    Usage:
        data = toc_parser.extract_asset(entry)
        model = ModelParser(data).parse()
    """

    def __init__(self, data: bytes):
        self.dat1 = DAT1(data)

    def parse(self) -> ModelAsset:
        dat1 = self.dat1

        uv_scale   = self._read_uv_scale(dat1)
        vertexes   = self._parse_vertexes(dat1, uv_scale)
        indexes    = self._parse_indexes(dat1)
        meshes     = self._parse_meshes(dat1)
        joints, jpos, jquat, jscales = self._parse_joints(dat1)
        rcra_w     = self._parse_rcra_weights(dat1)
        skin_data  = dat1.get_section(TAG_SKIN_DATA)
        skin_batch = self._parse_skin_batches(dat1)

        # Overlay UV1 channel if present
        # UV1 raw int16 values use the same uv_scale as the base vertex channel
        uv1_data = dat1.get_section(TAG_UV1)
        if uv1_data:
            for i in range(min(len(vertexes), len(uv1_data) // 4)):
                u_raw, v_raw = struct.unpack_from('<hh', uv1_data, i * 4)
                vertexes[i].u1 = u_raw * uv_scale
                vertexes[i].v1 = v_raw * uv_scale
            # Only promote UV1 to primary channel if vertex buffer UVs appear absent
            # (all zero), which happens for some environment/prop models but NOT for
            # skinned character models which store primary UVs in the vertex buffer.
            all_zero = all(vertexes[i].u == 0.0 and vertexes[i].v == 0.0
                          for i in range(min(len(vertexes), 16)))
            if all_zero:
                for i in range(min(len(vertexes), len(uv1_data) // 4)):
                    vertexes[i].u = vertexes[i].u1
                    vertexes[i].v = vertexes[i].v1

        # Vertex colours
        col_data = dat1.get_section(TAG_COLORS)
        if col_data:
            for i in range(min(len(vertexes), len(col_data) // 4)):
                rgba = struct.unpack_from('<BBBB', col_data, i * 4)
                vertexes[i].r, vertexes[i].g, vertexes[i].b, vertexes[i].a = rgba

        # Parse Look section → assign lod_level to each MeshDefinition
        lod_count      = self._parse_look(dat1, meshes)
        material_names = self._parse_material_names(dat1)

        return ModelAsset(
            vertexes          = vertexes,
            meshes            = meshes,
            indexes           = indexes,
            joints            = joints,
            joint_positions   = jpos,
            joint_quaternions = jquat,
            joint_scales      = jscales,
            rcra_weights      = rcra_w,
            skin_data         = skin_data,
            skin_batches      = skin_batch,
            lod_count         = lod_count,
            material_names    = material_names,
        )

    # ── Vertexes (section 0xA98BE69B) ─────────────────────────────────────────

    def _parse_vertexes(self, dat1: DAT1, uv_scale: float) -> list[Vertex]:
        data = dat1.get_section(TAG_VERTEXES)
        if not data:
            return []

        SCALE    = 1.0 / 4096.0
        UV_SCALE = uv_scale
        vertexes = []

        n_verts = len(data) // 16
        for i in range(n_verts):
            off = i * 16
            X, Y, Z, W = struct.unpack_from('<4h', data, off)
            NXYZ        = struct.unpack_from('<I',  data, off + 8)[0]
            nx, ny, nz  = _decode_normal(NXYZ)
            tx, ty, tz, tw = _decode_tangent(W, NXYZ)
            tq = _decode_position_correction(W)
            U, V        = struct.unpack_from('<2h', data, off + 12)

            vertexes.append(Vertex(
                x  = X * SCALE, y  = Y * SCALE, z  = Z * SCALE,
                nx = nx,        ny = ny,        nz = nz,
                u  = U * UV_SCALE,
                v  = V * UV_SCALE,
                tx = tx, ty = ty, tz = tz, tw = tw, tq = tq,
            ))
        return vertexes

    def _read_uv_scale(self, dat1: DAT1) -> float:
        """
        Read the UV scale from TAG_BUILT section (0x283D0383).
        Formula confirmed from ALERT dat1lib/types/sections/model/unknowns.py:
          float_val = float32 at byte offset 0x30
          iuvscale  = reinterpret float bits as int32
          uv_scale  = (1 << (iuvscale & 0xF)) / 16384.0

        This scale is applied directly to raw UV int16 values (both base vertex
        and UV1 section) to get final UV coordinates.
        Default fallback: 1/16384.0 (nibble=0, i.e. (1<<0)/16384)
        """
        try:
            built = dat1.get_section(TAG_BUILT)
            if not built or len(built) < 0x34:
                return 1.0 / 16384.0
            float_val = struct.unpack_from('<f', built, 0x30)[0]
            iuvscale = struct.unpack('<i', struct.pack('<f', float_val))[0]
            uv_scale = (1 << (iuvscale & 0xF)) / 16384.0
            return uv_scale
        except Exception as ex:
            print(f"[mesh] UV scale read failed: {ex}, using default")
            return 1.0 / 16384.0

    # ── Indexes (section 0x0859863D) ──────────────────────────────────────────

    def _parse_indexes(self, dat1: DAT1) -> list[int]:
        data = dat1.get_section(TAG_INDEXES)
        if not data:
            return []
        # RCRA uses plain uint16 (NOT delta-encoded, unlike MSMR)
        count = len(data) // 2
        return list(struct.unpack_from(f'<{count}H', data))

    # ── Mesh definitions (section 0x78D9CBDE) ─────────────────────────────────

    def _parse_meshes(self, dat1: DAT1) -> list[MeshDefinition]:
        data = dat1.get_section(TAG_MESHES)
        if not data:
            return []
        meshes = []
        ENTRY_SIZE = 64
        for i in range(len(data) // ENTRY_SIZE):
            base = i * ENTRY_SIZE
            # MSMR/RCRA variant (not SO):
            # <I Q H H H H>  = unk, mesh_id, ?, ?, ?, ?   (20B)
            _, mesh_id, _, _, _, _ = struct.unpack_from('<IQHHHH', data, base)
            # <I I I I>  = vertexStart, indexStart, indexCount, vertexCount  (16B)
            vs, ix_s, ix_c, vc = struct.unpack_from('<IIII', data, base + 20)
            # <H H H H>  = flags, material_index, first_skin_batch, skin_batches_count  (8B)
            flags, mat, fsb, sbc = struct.unpack_from('<HHHH', data, base + 36)
            # (8B unknowns2)
            # <I I>  = first_weight_index, unknown3  (8B)
            fwi, _ = struct.unpack_from('<II', data, base + 56)

            meshes.append(MeshDefinition(
                mesh_id            = mesh_id,
                vertex_start       = vs,
                vertex_count       = vc,
                index_start        = ix_s,
                index_count        = ix_c,
                flags              = flags,
                material_index     = mat,
                first_skin_batch   = fsb,
                skin_batches_count = sbc,
                first_weight_index = fwi,
            ))
        return meshes

    def _parse_look(self, dat1: DAT1, meshes: list) -> int:
        """
        Parse the Look section (TAG_LOOK = 0x06EB7EFC).

        Format confirmed from ALERT look.py:
          The section contains N 'looks' (render variants — e.g. default, damaged).
          Each look contains 8 LOD entries (for RCRA; 4 for SO).
          Each LOD entry is <HH> = (start: uint16, count: uint16)
            start = first mesh index for this LOD
            count = number of meshes in this LOD

          Total section size = N_looks × 8_lods × 4_bytes

        We assign lod_level to each MeshDefinition based on which LOD slot it
        falls into within look[0] (the default/primary look).
        Returns the number of active LOD levels in look[0].
        """
        data = dat1.get_section(TAG_LOOK)
        if not data:
            return self._lod_heuristic(meshes)

        data = bytes(data)
        LODS_PER_LOOK = 8   # always 8 for RCRA
        ENTRY_SIZE    = 4   # 2× uint16 per LOD entry
        LOOK_SIZE     = LODS_PER_LOOK * ENTRY_SIZE  # 32 bytes per look

        if len(data) < LOOK_SIZE:
            return self._lod_heuristic(meshes)

        n_looks = len(data) // LOOK_SIZE
        print(f"[mesh] Look section: {n_looks} looks, {LODS_PER_LOOK} LOD slots each")

        # Mark all meshes as unassigned initially
        for m in meshes:
            m.look_index = -1
            m.lod_level  = 0

        # Process looks in reverse order so look[0] always wins (overwrites later looks).
        # This handles the case where multiple looks reference the same mesh indices —
        # e.g. bangle models where look[0] and look[1] are identical.
        for look_idx in range(n_looks - 1, -1, -1):
            look_off = look_idx * LOOK_SIZE
            for lod_idx in range(LODS_PER_LOOK):
                off = look_off + lod_idx * ENTRY_SIZE
                start, count = struct.unpack_from('<HH', data, off)
                if count == 0:
                    continue
                for mi in range(start, min(start + count, len(meshes))):
                    meshes[mi].look_index = look_idx
                    meshes[mi].lod_level  = lod_idx

        # Meshes still unclaimed get look 0 / lod 0 as fallback
        for m in meshes:
            if m.look_index == -1:
                m.look_index = 0

        # Count active LODs in look[0]
        active_lods = 0
        for lod_idx in range(LODS_PER_LOOK):
            off = lod_idx * ENTRY_SIZE
            start, count = struct.unpack_from('<HH', data, off)
            if count > 0:
                active_lods = lod_idx + 1

        print(f"[mesh] Look[0]: {active_lods} active LOD levels")
        return max(1, active_lods)

    def _lod_heuristic(self, meshes: list) -> int:
        """
        Fallback LOD detection when no Look section is present.
        Detects LOD boundaries by finding where the material_index sequence resets.
        """
        if not meshes or len(meshes) <= 3:
            return 1
        first_mat = meshes[0].material_index
        lod_starts = [0]
        for i in range(1, len(meshes)):
            if meshes[i].material_index == first_mat and i > lod_starts[-1] + 1:
                lod_starts.append(i)
                if len(lod_starts) >= 8:
                    break
        if len(lod_starts) > 1:
            for lod_idx, start in enumerate(lod_starts):
                end = lod_starts[lod_idx + 1] if lod_idx + 1 < len(lod_starts) else len(meshes)
                for mi in range(start, end):
                    meshes[mi].lod_level = lod_idx
            print(f"[mesh] No Look section — heuristic detected {len(lod_starts)} LODs")
            return len(lod_starts)
        return 1

    # ── Joints (section 0x15DF9D3B) ───────────────────────────────────────────

    def _parse_joints(self, dat1: DAT1):
        joints_data = dat1.get_section(TAG_JOINTS)
        xform_data  = dat1.get_section(TAG_JOINT_XFORMS)
        if not joints_data:
            return [], [], [], []

        ENTRY_SIZE = 16
        joints = []
        for i in range(len(joints_data) // ENTRY_SIZE):
            base = i * ENTRY_SIZE
            parent, index, unk1, unk2, hash_val, str_off = struct.unpack_from('<hHHHII', joints_data, base)
            name = dat1.get_string(str_off) or f"bone_{i}"
            joints.append(JointDef(parent=parent, index=index, name=name, hash=hash_val))

        positions  = []
        quaternions = []
        scales      = []
        if xform_data:
            # Each entry: 12 floats (3×4 matrix) + 16 floats (4×4 matrix)
            ENTRY1 = 12 * 4   # 48B
            ENTRY2 = 16 * 4   # 64B
            count  = len(joints)
            for i in range(count):
                m34 = struct.unpack_from('<12f', xform_data, i * ENTRY1)
                # scale = m34[0:3], quaternion = m34[4:8], position = m34[8:11]
                scales.append(m34[0:3])
                positions.append(m34[8:11])
                quaternions.append(m34[4:8])

            # 4×4 matrices start after all 3×4 matrices
            off44 = ENTRY1 * count
            align = off44 % ENTRY2
            if align != 0:
                off44 += ENTRY2 - align

        return joints, positions, quaternions, scales

    # ── RCRA skin weights (section 0xCCBAFF15) ────────────────────────────────

    def _parse_rcra_weights(self, dat1: DAT1) -> list:
        data = dat1.get_section(TAG_RCRA_WEIGHTS)
        if not data:
            return []
        weights = []
        for i in range(len(data) // 8):
            b1, b2, b3, b4, w1, w2, w3, w4 = struct.unpack_from('<8B', data, i * 8)
            sm = w1 + w2 + w3 + w4
            entries = {}
            for bone, w in [(b1,w1),(b2,w2),(b3,w3),(b4,w4)]:
                if w > 0:
                    entries[bone] = entries.get(bone, 0) + w
            if sm > 0:
                result = [(b, w/sm) for b, w in entries.items()]
            else:
                result = []
            weights.append(sorted(result, key=lambda x: -x[1]))
        return weights

    # ── Skin batches (section 0xC61B1FF5) ─────────────────────────────────────

    def _parse_skin_batches(self, dat1: DAT1) -> list:
        data = dat1.get_section(TAG_SKIN_BATCH)
        if not data:
            return []
        batches = []
        for i in range(len(data) // 16):
            offset, z1, z2, unk1, vertex_count, first_vertex = \
                struct.unpack_from('<IIHHHH', data, i * 16)
            batches.append({
                'offset': offset, 'vertex_count': vertex_count,
                'first_vertex': first_vertex
            })
        return batches

    # ── Material names (section 0x3250BB80) ──────────────────────────────────

    def _parse_material_names(self, dat1: DAT1) -> list:
        """
        Parse material names from TAG_MATERIALS (0x3250BB80).

        Format confirmed from the official Rift Apart importer (io_mesh_riftapart):
          Each entry is two uint64 string offsets (16 bytes total):
            uint64  path_string_offset  — full .material path
            uint64  name_string_offset  — short display name
          Only the first half of the section is read (MaterialInfoSize // 2).

        mesh.material_index is a direct index into the resulting list.
        """
        data = dat1.get_section(TAG_MATERIALS)
        if not data:
            return []
        data      = bytes(data)
        half_size = len(data) // 2
        names     = []
        offset    = 0
        while offset + 16 <= half_size:
            path_off, = struct.unpack_from('<Q', data, offset)
            name_off, = struct.unpack_from('<Q', data, offset + 8)
            offset   += 16
            name = dat1.get_string(name_off) or ''
            if not name:
                # Fallback: derive from path
                path = dat1.get_string(path_off) or ''
                name = path.replace('\\', '/').split('/')[-1]
                if name.endswith('.material'):
                    name = name[:-9]
            names.append(name or f"material_{len(names)}")
        return names

    # ── String table helper ───────────────────────────────────────────────────

    @staticmethod
    def _read_string(dat1: DAT1, offset: int) -> Optional[str]:
        """Read a null-terminated UTF-8 string from the DAT1 string table."""
        # String table is between end of header directory and first section
        # We search from byte 0 of the dat1 data at the given absolute offset
        d = dat1.data
        if offset >= len(d):
            return None
        end = d.find(b'\x00', offset)
        if end < 0:
            end = len(d)
        try:
            return d[offset:end].decode('utf-8', errors='replace')
        except Exception:
            return None


# ── Convenience: build per-mesh numpy arrays for the exporter ─────────────────

def mesh_to_numpy(model: ModelAsset, mesh: MeshDefinition):
    """
    Return (positions, normals, uvs, indices) as numpy arrays for one sub-mesh.
    Handles both relative and vertex-offset index modes.
    """
    vs = mesh.vertex_start
    vc = mesh.vertex_count
    verts = model.vertexes[vs:vs + vc]
    if not verts:
        return None, None, None, None

    positions = np.array([(v.x, v.y, v.z) for v in verts], dtype=np.float32)
    normals   = np.array([(v.nx, v.ny, v.nz) for v in verts], dtype=np.float32)
    uvs       = np.array([(v.u, v.v) for v in verts], dtype=np.float32)

    raw_idx = model.indexes[mesh.index_start:mesh.index_start + mesh.index_count]
    if not raw_idx:
        return positions, normals, uvs, None

    offset = 0 if mesh.indices_are_relative else mesh.vertex_start
    indices = np.array([max(0, i - offset) for i in raw_idx], dtype=np.uint32)

    return positions, normals, uvs, indices


def mesh_tangents_to_numpy(model: ModelAsset, mesh: MeshDefinition):
    """Return authored tangent XYZ and handedness for one sub-mesh."""
    vs = mesh.vertex_start
    vc = mesh.vertex_count
    verts = model.vertexes[vs:vs + vc]
    if not verts:
        return None
    return np.array(
        [(v.tx, v.ty, v.tz, v.tw) for v in verts], dtype=np.float32,
    )


def mesh_decode_corrections_to_numpy(model: ModelAsset, mesh: MeshDefinition):
    """Return the retail position-decode correction for one sub-mesh."""
    vs = mesh.vertex_start
    vc = mesh.vertex_count
    verts = model.vertexes[vs:vs + vc]
    if not verts:
        return None
    return np.array([(v.tq,) for v in verts], dtype=np.float32)
