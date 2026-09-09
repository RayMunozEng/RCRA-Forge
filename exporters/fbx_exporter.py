"""
exporters/fbx_exporter.py
Export ModelAsset → Binary FBX 7.4

Binary FBX — supported by Blender, Maya, 3ds Max, Substance Painter, Unity.
No external dependencies required.

Node record layout (FBX 7.4):
  Uint32  EndOffset        — absolute byte offset of next sibling from file start
  Uint32  NumProperties
  Uint32  PropertyListLen
  Uint8   NameLen
  char[]  Name
  byte[]  Properties
  byte[]  NestedList       — present only when node has children
  byte[13] NULL-record     — 13 zero bytes, terminates nested list
"""

from __future__ import annotations

import io
import math
import struct
import time
import zlib
import numpy as np
from typing import Any

from core.mesh import ModelAsset, MeshDefinition, mesh_to_numpy
from exporters.gltf_exporter import _qxq, _rot_v, _quat_to_mat4_colmaj


# ── Long integer wrapper (FBX type 'L' = int64, required for UIDs) ────────────

class FbxLong:
    """Wraps an int to force FBX type 'L' (64-bit signed) instead of 'I' (32-bit)."""
    __slots__ = ('val',)
    def __init__(self, v: int): self.val = v


# ── Binary helpers ────────────────────────────────────────────────────────────

def _write_prop(buf: io.BytesIO, val: Any):
    """Write one property to buf with its type code prefix."""
    if isinstance(val, bool):
        buf.write(b'C')
        buf.write(struct.pack('<B', int(val)))
    elif isinstance(val, FbxLong):
        buf.write(b'L')
        buf.write(struct.pack('<q', val.val))
    elif isinstance(val, int):
        buf.write(b'I')
        buf.write(struct.pack('<i', val))
    elif isinstance(val, float):
        buf.write(b'D')
        buf.write(struct.pack('<d', val))
    elif isinstance(val, str):
        b = val.encode('utf-8')
        buf.write(b'S')
        buf.write(struct.pack('<I', len(b)))
        buf.write(b)
    elif isinstance(val, bytes):
        buf.write(b'R')
        buf.write(struct.pack('<I', len(val)))
        buf.write(val)
    elif isinstance(val, np.ndarray):
        _write_array_prop(buf, val)
    else:
        raise TypeError(f"Unsupported prop type: {type(val)}")


def _write_array_prop(buf: io.BytesIO, arr: np.ndarray):
    """Write a numpy array as an FBX array property (compressed if beneficial)."""
    if arr.dtype in (np.float32, np.float64):
        tcode = b'd'
        raw   = arr.astype(np.float64).tobytes()
    else:
        tcode = b'i'
        raw   = arr.astype(np.int32).tobytes()

    compressed = zlib.compress(raw, 1)
    if len(compressed) < len(raw):
        buf.write(tcode)
        buf.write(struct.pack('<III', len(arr), 1, len(compressed)))
        buf.write(compressed)
    else:
        buf.write(tcode)
        buf.write(struct.pack('<III', len(arr), 0, len(raw)))
        buf.write(raw)


# ── FBX Node (two-pass encoder) ───────────────────────────────────────────────

class FbxNode:
    NULL_RECORD = b'\x00' * 13

    def __init__(self, name: str, *props):
        self.name     = name
        self.props    = list(props)
        self.children: list[FbxNode] = []

    def add(self, *props) -> 'FbxNode':
        self.props.extend(props)
        return self

    def child(self, name: str, *props) -> 'FbxNode':
        n = FbxNode(name, *props)
        self.children.append(n)
        return n

    def encode(self, buf: io.BytesIO):
        """
        Encode this node to buf.
        EndOffset is absolute from file start so we write a placeholder,
        encode properties + children, then seek back to patch it.
        """
        name_b = self.name.encode('utf-8')

        # Build property block
        prop_buf = io.BytesIO()
        for p in self.props:
            _write_prop(prop_buf, p)
        prop_bytes = prop_buf.getvalue()

        # Write header with placeholder EndOffset (patched after)
        header_start = buf.tell()
        buf.write(struct.pack('<III', 0, len(self.props), len(prop_bytes)))
        buf.write(bytes([len(name_b)]))
        buf.write(name_b)
        buf.write(prop_bytes)

        # Write children
        for child in self.children:
            child.encode(buf)
        if self.children:
            buf.write(self.NULL_RECORD)

        # Patch EndOffset = current position (absolute)
        end_pos = buf.tell()
        buf.seek(header_start)
        buf.write(struct.pack('<I', end_pos))
        buf.seek(end_pos)


# ── UID generator ─────────────────────────────────────────────────────────────

_uid_counter = 100_000_000

def _uid() -> FbxLong:
    global _uid_counter
    _uid_counter += 1
    return FbxLong(_uid_counter)


# ── Quaternion → Euler XYZ (degrees) ─────────────────────────────────────────

def _euler_deg(qx, qy, qz, qw):
    sinr = 2*(qw*qx + qy*qz);  cosr = 1 - 2*(qx*qx + qy*qy)
    rx   = math.degrees(math.atan2(sinr, cosr))
    sinp = max(-1.0, min(1.0, 2*(qw*qy - qz*qx)))
    ry   = math.degrees(math.asin(sinp))
    siny = 2*(qw*qz + qx*qy);  cosy = 1 - 2*(qy*qy + qz*qz)
    rz   = math.degrees(math.atan2(siny, cosy))
    return rx, ry, rz


# ── Main exporter ─────────────────────────────────────────────────────────────

class FbxExporter:
    def __init__(self, model: ModelAsset, name: str = "model", lod: int = 0):
        self.model = model
        self.name  = name
        self.lod   = lod

    def _mesh_weights(self, mesh: MeshDefinition):
        if mesh.flags & 0x100:
            return self.model.rcra_weights, mesh.first_weight_index
        return self.model.skin_weights, mesh.vertex_start

    def export(self, path: str):
        global _uid_counter
        _uid_counter = 100_000_000

        target_meshes = [m for m in self.model.meshes
                         if m.look_index == 0 and m.lod_level == self.lod]
        if not target_meshes:
            target_meshes = self.model.meshes

        has_skel  = bool(self.model.joints)

        # Pre-assign UIDs
        root_uid     = _uid()
        bone_uids    = [_uid() for _ in self.model.joints]
        mesh_uids    = [(_uid(), _uid()) for _ in target_meshes]
        mat_uid_map  = {m.material_index: _uid() for m in target_meshes}
        skin_uids    = [_uid() for _ in target_meshes]
        cluster_uids: dict[tuple, int] = {}

        for si, mesh in enumerate(target_meshes):
            source, ws = self._mesh_weights(mesh)
            bone_set: set[int] = set()
            for vi in range(mesh.vertex_count):
                wi = ws + vi
                if wi >= len(source): break
                for bi, w in source[wi]:
                    if w > 0: bone_set.add(int(bi))
            for bi in bone_set:
                cluster_uids[(si, bi)] = _uid()

        # ── Build node tree ───────────────────────────────────────────────────
        nodes: list[FbxNode] = []

        # Binary FBX object name format: "ActualName\x00\x01ClassName"
        def fn(name: str, cls: str) -> str:
            return f"{name}\x00\x01{cls}"

        # -- FBXHeaderExtension
        hdr = FbxNode("FBXHeaderExtension")
        hdr.child("FBXHeaderVersion", 1003)
        hdr.child("FBXVersion",       7400)
        ct = hdr.child("CreationTimeStamp")
        ct.child("Version",     1000)
        ct.child("Year",        int(time.strftime("%Y")))
        ct.child("Month",       int(time.strftime("%m")))
        ct.child("Day",         int(time.strftime("%d")))
        ct.child("Hour",        int(time.strftime("%H")))
        ct.child("Minute",      int(time.strftime("%M")))
        ct.child("Second",      int(time.strftime("%S")))
        ct.child("Millisecond", 0)
        hdr.child("Creator", "RCRA Forge v0.5.1")
        nodes.append(hdr)

        fi = FbxNode("FileId")
        fi.add(b'\x28\xb3\x2a\xeb\xb3\x24\xcd\xc8\xb8\x69\xb0\x27\x2b\x00\x29\x9c')
        nodes.append(fi)
        nodes.append(FbxNode("CreationTime", time.strftime("%Y-%m-%d %H:%M:%S:000")))
        nodes.append(FbxNode("Creator", "RCRA Forge v0.5.1"))

        # -- GlobalSettings
        gs = FbxNode("GlobalSettings")
        gs.child("Version", 1000)
        p70 = gs.child("Properties70")
        def gp(nm, tp, lb, fl, *vs):
            n = p70.child("P", nm, tp, lb, fl)
            for v in vs: n.add(v)
        gp("UpAxis",                   "int",    "Integer", "", 1)
        gp("UpAxisSign",               "int",    "Integer", "", 1)
        gp("FrontAxis",                "int",    "Integer", "", 2)
        gp("FrontAxisSign",            "int",    "Integer", "", 1)
        gp("CoordAxis",                "int",    "Integer", "", 0)
        gp("CoordAxisSign",            "int",    "Integer", "", 1)
        gp("UnitScaleFactor",          "double", "Number",  "", 100.0)
        gp("OriginalUnitScaleFactor",  "double", "Number",  "", 100.0)
        nodes.append(gs)

        # -- Documents
        docs = FbxNode("Documents")
        docs.child("Count", 1)
        doc = docs.child("Document", FbxLong(1), "", "Scene")
        dp  = doc.child("Properties70")
        dp.child("P", "SourceObject", "object", "", "")
        dp.child("P", "ActiveAnimStackName", "KString", "", "", "")
        doc.child("RootNode", FbxLong(0))
        nodes.append(docs)
        nodes.append(FbxNode("References"))

        # -- Definitions
        defs = FbxNode("Definitions")
        defs.child("Version", 100)
        n_model = len(target_meshes) + 1 + (len(self.model.joints) if has_skel else 0)
        total   = 1 + n_model + len(target_meshes) + len(mat_uid_map) + len(skin_uids) + len(cluster_uids)
        defs.child("Count", total)
        def deftype(tp, cnt):
            ot = defs.child("ObjectType", tp)
            ot.child("Count", cnt)
        deftype("GlobalSettings", 1)
        deftype("Model",    n_model)
        deftype("Geometry", len(target_meshes))
        deftype("Material", len(mat_uid_map))
        deftype("Deformer", len(skin_uids) + len(cluster_uids))
        nodes.append(defs)

        # -- Objects
        objs = FbxNode("Objects")

        # Root null
        rn = objs.child("Model", root_uid, fn(self.name, "Model"), "Null")
        rn.child("Version", 232)
        rp = rn.child("Properties70")
        rp.child("P", "RotationActive", "bool", "", "", 1)
        rp.child("P", "InheritType",    "enum", "", "", 1)
        rn.child("Shading", "Y")
        rn.child("Culling", "CullingOff")

        # Bones
        if has_skel:
            for i, joint in enumerate(self.model.joints):
                pos = self.model.joint_positions[i]   if i < len(self.model.joint_positions)   else (0,0,0)
                rot = self.model.joint_quaternions[i] if i < len(self.model.joint_quaternions) else (0,0,0,1)
                tx,ty,tz    = float(pos[0]),float(pos[1]),float(pos[2])
                qx,qy,qz,qw = float(rot[0]),float(rot[1]),float(rot[2]),float(rot[3])
                ex,ey,ez    = _euler_deg(qx,qy,qz,qw)
                ntype       = "LimbNode" if joint.parent != -1 else "Null"

                bn = objs.child("Model", bone_uids[i], fn(joint.name, "Model"), ntype)
                bn.child("Version", 232)
                bp = bn.child("Properties70")
                bp.child("P", "RotationActive",  "bool", "", "", 1)
                bp.child("P", "InheritType",      "enum", "",              "", 1)
                t = bp.child("P", "Lcl Translation", "Lcl Translation", "", "A")
                t.add(tx, ty, tz)
                r = bp.child("P", "Lcl Rotation",    "Lcl Rotation",    "", "A")
                r.add(ex, ey, ez)
                bn.child("Shading", "Y")
                bn.child("Culling", "CullingOff")

        # Materials
        for mat_idx, mat_uid in mat_uid_map.items():
            mname = (self.model.material_names[mat_idx]
                     if mat_idx < len(self.model.material_names)
                     else f"material_{mat_idx}")
            mn = objs.child("Material", mat_uid, fn(mname, "Material"), "")
            mn.child("Version", 102)
            mn.child("ShadingModel", "Phong")
            mn.child("MultiLayer",   0)
            mp = mn.child("Properties70")
            dc = mp.child("P", "DiffuseColor", "Color", "", "A")
            dc.add(0.8, 0.8, 0.8)

        # Mesh geometry
        for si, (mesh, (node_uid, geo_uid)) in enumerate(zip(target_meshes, mesh_uids)):
            positions, normals, uvs, indices = mesh_to_numpy(self.model, mesh)
            if positions is None or indices is None:
                continue

            mname   = f"{self.name}-subset{si}-LOD_{self.lod}"
            n_tris  = len(indices) // 3

            # Model node
            mm = objs.child("Model", node_uid, fn(mname, "Model"), "Mesh")
            mm.child("Version", 232)
            mmp = mm.child("Properties70")
            mmp.child("P", "RotationActive",        "bool",    "", "", 1)
            mmp.child("P", "InheritType",            "enum",    "", "", 1)
            mmp.child("P", "DefaultAttributeIndex",  "int", "Integer", "", 0)
            mm.child("Shading", "Y")
            mm.child("Culling", "CullingOff")

            # Geometry
            gn = objs.child("Geometry", geo_uid, fn(mname, "Geometry"), "Mesh")

            gn.child("Vertices", positions.flatten().astype(np.float64))

            # FBX poly index: negate last vertex of each triangle
            fbx_idx          = np.empty(n_tris * 3, dtype=np.int32)
            fbx_idx[0::3]    = indices[0::3].astype(np.int32)
            fbx_idx[1::3]    = indices[1::3].astype(np.int32)
            fbx_idx[2::3]    = -(indices[2::3].astype(np.int32) + 1)
            gn.child("PolygonVertexIndex", fbx_idx)

            if normals is not None:
                en = gn.child("LayerElementNormal", 0)
                en.child("Version",                   101)
                en.child("Name",                      "")
                en.child("MappingInformationType",    "ByVertice")
                en.child("ReferenceInformationType",  "Direct")
                en.child("Normals", normals.flatten().astype(np.float64))

            if uvs is not None:
                eu = gn.child("LayerElementUV", 0)
                eu.child("Version",                  101)
                eu.child("Name",                     "UVMap")
                eu.child("MappingInformationType",   "ByPolygonVertex")
                eu.child("ReferenceInformationType", "IndexToDirect")
                uvs_flipped = uvs.copy()
                uvs_flipped[:, 1] = 1.0 - uvs_flipped[:, 1]
                eu.child("UV", uvs_flipped.flatten().astype(np.float64))
                uv_idx = np.where(fbx_idx < 0, -(fbx_idx + 1), fbx_idx).astype(np.int32)
                eu.child("UVIndex", uv_idx)

            em = gn.child("LayerElementMaterial", 0)
            em.child("Version",                  101)
            em.child("Name",                     "")
            em.child("MappingInformationType",   "AllSame")
            em.child("ReferenceInformationType", "IndexToDirect")
            em.child("Materials", np.array([0], dtype=np.int32))

            lay = gn.child("Layer", 0)
            lay.child("Version", 100)
            if normals is not None:
                le = lay.child("LayerElement")
                le.child("Type",       "LayerElementNormal")
                le.child("TypedIndex", 0)
            if uvs is not None:
                le = lay.child("LayerElement")
                le.child("Type",       "LayerElementUV")
                le.child("TypedIndex", 0)
            le = lay.child("LayerElement")
            le.child("Type",       "LayerElementMaterial")
            le.child("TypedIndex", 0)

        # Skin deformers + clusters
        if has_skel and (self.model.rcra_weights or self.model.skin_weights):
            for si, mesh in enumerate(target_meshes):
                mname    = f"{self.name}-subset{si}-LOD_{self.lod}"
                skin_uid = skin_uids[si]

                sn = objs.child("Deformer", skin_uid, fn(mname, "Deformer"), "Skin")
                sn.child("Version",            101)
                sn.child("Link_DeformAcuracy", 50.0)

                # Per-bone vertex/weight arrays
                source, ws   = self._mesh_weights(mesh)
                bv:  dict[int, list[int]]   = {}
                bw:  dict[int, list[float]] = {}
                for vi in range(mesh.vertex_count):
                    wi = ws + vi
                    if wi >= len(source): break
                    for bi, w in source[wi]:
                        if w > 0:
                            bv.setdefault(int(bi), []).append(vi)
                            bw.setdefault(int(bi), []).append(float(w))

                for bone_idx, verts in bv.items():
                    if bone_idx >= len(self.model.joints): continue
                    cl_uid = cluster_uids.get((si, bone_idx))
                    if cl_uid is None: continue
                    joint  = self.model.joints[bone_idx]

                    wpos, wrot  = self._world_transform(bone_idx)
                    tx,ty,tz    = float(wpos[0]),float(wpos[1]),float(wpos[2])
                    qx,qy,qz,qw = float(wrot[0]),float(wrot[1]),float(wrot[2]),float(wrot[3])
                    world_mat   = _quat_to_mat4_colmaj(qx,qy,qz,qw,tx,ty,tz).T  # row-major
                    try:    inv_mat = np.linalg.inv(world_mat)
                    except: inv_mat = np.eye(4, dtype=np.float64)

                    cn = objs.child("Deformer", cl_uid, fn(joint.name, "SubDeformer"), "Cluster")
                    cn.child("Version",       100)
                    cn.child("UserData",      "", "")
                    cn.child("Indexes",       np.array(verts,    dtype=np.int32))
                    cn.child("Weights",       np.array(bw[bone_idx], dtype=np.float64))
                    cn.child("Transform",     inv_mat.flatten().astype(np.float64))
                    cn.child("TransformLink", world_mat.flatten().astype(np.float64))

        nodes.append(objs)

        # -- Connections
        conns = FbxNode("Connections")
        def conn(src, dst):
            # Connections: C: "OO", src_uid (L), dst_uid (L)
            src_l = src if isinstance(src, FbxLong) else FbxLong(src)
            dst_l = dst if isinstance(dst, FbxLong) else FbxLong(dst)
            conns.child("C", "OO", src_l, dst_l)

        conn(root_uid, FbxLong(0))
        if has_skel:
            for i, joint in enumerate(self.model.joints):
                parent = bone_uids[joint.parent] if joint.parent != -1 else root_uid
                conn(bone_uids[i], parent)

        for si, (mesh, (node_uid, geo_uid)) in enumerate(zip(target_meshes, mesh_uids)):
            conn(node_uid, root_uid)
            conn(geo_uid,  node_uid)
            mat_uid = mat_uid_map.get(mesh.material_index)
            if mat_uid: conn(mat_uid, node_uid)
            if has_skel:
                conn(skin_uids[si], geo_uid)
                source, ws = self._mesh_weights(mesh)
                bone_set = set()
                for vi in range(mesh.vertex_count):
                    wi = ws + vi
                    if wi >= len(source): break
                    for bi, w in source[wi]:
                        if w > 0: bone_set.add(int(bi))
                for bone_idx in bone_set:
                    if bone_idx >= len(self.model.joints): continue
                    cl_uid = cluster_uids.get((si, bone_idx))
                    if cl_uid:
                        conn(cl_uid, skin_uids[si])
                        conn(cl_uid, bone_uids[bone_idx])

        nodes.append(conns)

        # ── Write file ────────────────────────────────────────────────────────
        buf = io.BytesIO()

        # 27-byte magic header
        buf.write(b'Kaydara FBX Binary  \x00\x1a\x00')
        buf.write(struct.pack('<I', 7400))

        for node in nodes:
            node.encode(buf)

        # Top-level NULL record (13 zero bytes)
        buf.write(b'\x00' * 13)

        # Footer padding to 16-byte boundary
        pos = buf.tell()
        buf.write(b'\x00' * ((16 - (pos % 16)) % 16))

        # Required magic footer bytes
        buf.write(bytes([
            0xfa,0xbc,0xab,0x09,0xd0,0xc8,0xd4,0x66,0xb1,0x76,0xfb,0x83,0x1c,0xf7,0x26,0x7e,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0xe8,0x1c,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        ]))

        with open(path, 'wb') as f:
            f.write(buf.getvalue())

    def _world_transform(self, bone_idx: int):
        joints    = self.model.joints
        pos_arr   = self.model.joint_positions
        rot_arr   = self.model.joint_quaternions
        cache: dict = {}

        def compute(i):
            if i in cache: return cache[i]
            pos = tuple(pos_arr[i]) if i < len(pos_arr) else (0.0,0.0,0.0)
            rot = tuple(rot_arr[i]) if i < len(rot_arr) else (0.0,0.0,0.0,1.0)
            j   = joints[i]
            if j.parent == -1:
                cache[i] = (pos, rot)
            else:
                pp, pq = compute(j.parent)
                rv     = _rot_v(pos, pq)
                cache[i] = ((pp[0]+rv[0], pp[1]+rv[1], pp[2]+rv[2]), _qxq(pq, rot))
            return cache[i]

        return compute(bone_idx)
