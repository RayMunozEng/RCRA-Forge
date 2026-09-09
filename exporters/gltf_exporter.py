"""
exporters/gltf_exporter.py
Export ModelAsset → glTF 2.0 (.glb)

- Each LOD-0/look-0 sub-mesh exported as a separate named mesh node
- Correct column-major inverse bind matrices
- RCRA skin weights (4 influences per vertex)
- OBJ fallback
"""

import json
import os
import struct
import numpy as np
from typing import Optional

from core.mesh import (
    ModelAsset,
    MeshDefinition,
    mesh_decode_corrections_to_numpy,
    mesh_tangents_to_numpy,
    mesh_to_numpy,
)

GLTF_FLOAT          = 5126
GLTF_UNSIGNED_BYTE  = 5121
GLTF_UNSIGNED_SHORT = 5123
GLTF_UNSIGNED_INT   = 5125
GLTF_ARRAY_BUFFER   = 34962
GLTF_ELEMENT_ARRAY  = 34963

GLB_MAGIC      = 0x46546C67
GLB_JSON_CHUNK = 0x4E4F534A
GLB_BIN_CHUNK  = 0x004E4942

MAX_INFLUENCES = 4


# ── Quaternion helpers (ALERT-compatible) ─────────────────────────────────────

def _qxq(q, p):
    aq,bq,cq,dq = q; ap,bp,cp,dp = p
    return (dq*ap+aq*dp+bq*cp-cq*bp, dq*bp-aq*cp+bq*dp+cq*ap,
            dq*cp+aq*bp-bq*ap+cq*dp, dq*dp-aq*ap-bq*bp-cq*cp)

def _qxv(q, v):
    ax,ay,az,aw = q; bx,by,bz = v
    return (aw*bx+ay*bz-az*by, aw*by-ax*bz+az*bx,
            aw*bz+ax*by-ay*bx, -ax*bx-ay*by-az*bz)

def _rot_v(v, q):
    iq = (-q[0], -q[1], -q[2], q[3])
    t  = _qxq(_qxv(q, v), iq)
    return (t[0], t[1], t[2])

def _quat_to_mat4_colmaj(qx, qy, qz, qw, tx, ty, tz) -> np.ndarray:
    """
    Build a 4×4 transform and return it in glTF column-major layout
    (i.e. transposed from the standard row-major convention).
    """
    # Build row-major first (m[row, col])
    m = np.eye(4, dtype=np.float64)
    m[0,0]=1-2*(qy*qy+qz*qz); m[0,1]=2*(qx*qy-qz*qw); m[0,2]=2*(qx*qz+qy*qw)
    m[1,0]=2*(qx*qy+qz*qw);   m[1,1]=1-2*(qx*qx+qz*qz); m[1,2]=2*(qy*qz-qx*qw)
    m[2,0]=2*(qx*qz-qy*qw);   m[2,1]=2*(qy*qz+qx*qw);   m[2,2]=1-2*(qx*qx+qy*qy)
    m[0,3]=tx; m[1,3]=ty; m[2,3]=tz
    # Transpose to column-major for glTF
    return m.T.astype(np.float32)


class GltfExporter:
    def __init__(self, model: ModelAsset, name: str = "model", lod: int = 0):
        self.model = model
        self.name  = name
        self.lod   = lod
        self._bin:       bytearray = bytearray()
        self._views:     list      = []
        self._accessors: list      = []
        self._meshes:    list      = []
        self._nodes:     list      = []
        self._skins:     list      = []
        self._materials: list      = []

    def export_glb(self, path: str):
        doc = self._build()
        json_bytes = json.dumps(doc, separators=(',',':')).encode('utf-8')
        while len(json_bytes) % 4: json_bytes += b' '
        while len(self._bin)   % 4: self._bin   += b'\x00'
        total = 12 + 8 + len(json_bytes) + 8 + len(self._bin)
        with open(path, 'wb') as f:
            f.write(struct.pack('<III', GLB_MAGIC, 2, total))
            f.write(struct.pack('<II',  len(json_bytes), GLB_JSON_CHUNK))
            f.write(json_bytes)
            f.write(struct.pack('<II',  len(self._bin), GLB_BIN_CHUNK))
            f.write(self._bin)

    def export_gltf(self, path: str):
        bin_path = os.path.splitext(path)[0] + '.bin'
        doc = self._build(bin_uri=os.path.basename(bin_path))
        with open(path, 'w') as f: json.dump(doc, f, indent=2)
        with open(bin_path, 'wb') as f: f.write(self._bin)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self, bin_uri=None):
        self._bin.clear(); self._views.clear(); self._accessors.clear()
        self._meshes.clear(); self._nodes.clear(); self._skins.clear()
        self._materials.clear()

        # Build named materials from model's material list
        mat_names = self.model.material_names
        if mat_names:
            for name in mat_names:
                self._materials.append({
                    "name": name,
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [0.8, 0.8, 0.8, 1.0],
                        "metallicFactor": 0.0, "roughnessFactor": 0.8,
                    }
                })
        else:
            self._materials.append({
                "name": "default",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.8, 0.8, 0.8, 1.0],
                    "metallicFactor": 0.0, "roughnessFactor": 0.8,
                }
            })

        # LOD 0 / look 0 only
        target_meshes = [m for m in self.model.meshes
                         if m.look_index == 0 and m.lod_level == self.lod]
        if not target_meshes:
            target_meshes = self.model.meshes

        has_skeleton = bool(self.model.joints)
        skin_idx = None
        skeleton_scene_root = None
        if has_skeleton:
            skin_idx = self._build_skeleton()   # inserts N bone nodes at 0..N-1
            authored_roots = [i for i, joint in enumerate(self.model.joints)
                              if joint.parent == -1]
            skeleton_scene_root = len(self._nodes)
            self._nodes.append({
                "name": f"{self.name}_SkeletonRoot",
                "children": authored_roots,
            })
            self._skins[skin_idx]["skeleton"] = skeleton_scene_root

        # One mesh node per sub-mesh (matches the importer structure in screenshot 4)
        mesh_node_indices = []
        for si, mesh in enumerate(target_meshes):
            prim = self._build_primitive(mesh)
            if prim is None:
                continue
            mesh_name = f"{self.name}-subset{si}-LOD_{self.lod}"
            mesh_idx  = len(self._meshes)
            self._meshes.append({"name": mesh_name, "primitives": [prim]})

            node: dict = {"name": mesh_name, "mesh": mesh_idx}
            if skin_idx is not None:
                node["skin"] = skin_idx
            node_idx = len(self._nodes)
            self._nodes.append(node)
            mesh_node_indices.append(node_idx)

        # A joint hierarchy must be reachable from the active scene. Merely
        # referencing joint nodes from skins[].joints leaves the hierarchy
        # disconnected and causes strict importers to reject or recurse while
        # trying to synthesize a skeleton root. Include each authored root;
        # nodes without meshes are transforms and do not render in glTF.
        skeleton_roots = ([skeleton_scene_root]
                          if skeleton_scene_root is not None else [])
        scene_nodes = skeleton_roots + list(mesh_node_indices)

        buf: dict = {"byteLength": len(self._bin)}
        if bin_uri: buf["uri"] = bin_uri

        doc: dict = {
            "asset": {"version": "2.0", "generator": "RCRA Forge"},
            "scene": 0,
            "scenes": [{"nodes": scene_nodes}],
            "nodes":  self._nodes,
            "meshes": self._meshes,
            "materials": self._materials,
            "accessors":   self._accessors,
            "bufferViews": self._views,
            "buffers": [buf],
        }
        if self._skins:
            doc["skins"] = self._skins
        return doc

    # ── Skeleton ──────────────────────────────────────────────────────────────

    def _compute_world_transforms(self):
        joints    = self.model.joints
        pos_arr   = self.model.joint_positions
        rot_arr   = self.model.joint_quaternions
        N         = len(joints)
        world     = [None] * N

        def compute(i):
            if world[i] is not None:
                return world[i]
            pos = tuple(pos_arr[i]) if i < len(pos_arr) else (0.0,0.0,0.0)
            rot = tuple(rot_arr[i]) if i < len(rot_arr) else (0.0,0.0,0.0,1.0)
            j   = joints[i]
            if j.parent == -1:
                world[i] = (pos, rot)
            else:
                pp, pq = compute(j.parent)
                rv      = _rot_v(pos, pq)
                new_pos = (pp[0]+rv[0], pp[1]+rv[1], pp[2]+rv[2])
                new_rot = _qxq(pq, rot)
                world[i] = (new_pos, new_rot)
            return world[i]

        for i in range(N): compute(i)
        return world

    def _build_skeleton(self) -> int:
        joints  = self.model.joints
        pos_arr = self.model.joint_positions
        rot_arr = self.model.joint_quaternions
        N       = len(joints)
        world   = self._compute_world_transforms()

        # Pre-insert bone nodes
        for _ in range(N):
            self._nodes.append({})

        for i, joint in enumerate(joints):
            pos = tuple(pos_arr[i]) if i < len(pos_arr) else (0.0,0.0,0.0)
            rot = tuple(rot_arr[i]) if i < len(rot_arr) else (0.0,0.0,0.0,1.0)

            node: dict = {"name": joint.name}
            px,py,pz   = float(pos[0]),float(pos[1]),float(pos[2])
            qx,qy,qz,qw = float(rot[0]),float(rot[1]),float(rot[2]),float(rot[3])
            if px!=0 or py!=0 or pz!=0:
                node["translation"] = [px,py,pz]
            if not (qx==0 and qy==0 and qz==0 and qw==1):
                node["rotation"] = [qx,qy,qz,qw]
            children = [j for j in range(N) if joints[j].parent == i]
            if children:
                node["children"] = children
            self._nodes[i] = node

        # Inverse bind matrices — column-major, inverse of world transform
        ibm_list = []
        for i in range(N):
            wpos, wrot = world[i]
            tx,ty,tz   = float(wpos[0]),float(wpos[1]),float(wpos[2])
            qx,qy,qz,qw = float(wrot[0]),float(wrot[1]),float(wrot[2]),float(wrot[3])
            # Build column-major world matrix
            world_col = _quat_to_mat4_colmaj(qx,qy,qz,qw,tx,ty,tz)
            try:
                inv = np.linalg.inv(world_col).astype(np.float32)
            except np.linalg.LinAlgError:
                inv = np.eye(4, dtype=np.float32)
            ibm_list.append(inv)

        ibm_data = np.stack(ibm_list, axis=0)          # (N, 4, 4)
        ibm_acc  = self._add_accessor(
            ibm_data.reshape(N, 16), "MAT4", GLTF_FLOAT, GLTF_ARRAY_BUFFER
        )
        skin_idx = len(self._skins)
        self._skins.append({
            "name": f"{self.name}_skin",
            "joints": list(range(N)),
            "inverseBindMatrices": ibm_acc,
        })
        return skin_idx

    # ── Primitive ─────────────────────────────────────────────────────────────

    def _build_primitive(self, mesh: MeshDefinition) -> Optional[dict]:
        positions, normals, uvs, indices = mesh_to_numpy(self.model, mesh)
        if positions is None or indices is None or len(positions) == 0:
            return None

        attribs: dict = {}
        attribs["POSITION"] = self._add_accessor(
            positions, "VEC3", GLTF_FLOAT, GLTF_ARRAY_BUFFER, minmax=True)
        if normals is not None:
            attribs["NORMAL"] = self._add_accessor(
                normals, "VEC3", GLTF_FLOAT, GLTF_ARRAY_BUFFER)
        tangents = mesh_tangents_to_numpy(self.model, mesh)
        if (tangents is not None and tangents.shape == (len(positions), 4)
                and np.isfinite(tangents).all()
                and np.all(np.linalg.norm(tangents[:, :3], axis=1) > 1e-8)):
            attribs["TANGENT"] = self._add_accessor(
                tangents, "VEC4", GLTF_FLOAT, GLTF_ARRAY_BUFFER)
        if uvs is not None:
            uvs_flipped = uvs.copy()
            uvs_flipped[:, 1] = 1.0 - uvs_flipped[:, 1]
            attribs["TEXCOORD_0"] = self._add_accessor(
                uvs_flipped, "VEC2", GLTF_FLOAT, GLTF_ARRAY_BUFFER)
        decode_corrections = mesh_decode_corrections_to_numpy(self.model, mesh)
        if (decode_corrections is not None
                and decode_corrections.shape == (len(positions), 1)
                and np.isfinite(decode_corrections).all()
                and np.any(decode_corrections != 0.0)):
            # UE imports float TEXCOORD channels on skeletal meshes. Preserve
            # the retail position-decode correction in UV1.x so recovered fur
            # materials can reproduce the native per-vertex shell budget.
            correction_uv = np.concatenate((
                decode_corrections.astype(np.float32),
                np.zeros_like(decode_corrections, dtype=np.float32),
            ), axis=1)
            attribs["TEXCOORD_1"] = self._add_accessor(
                correction_uv, "VEC2", GLTF_FLOAT, GLTF_ARRAY_BUFFER)

        if self.model.joints and (self.model.rcra_weights or self.model.skin_weights):
            j_arr, w_arr = self._build_skin_arrays(mesh)
            if j_arr is not None:
                attribs["JOINTS_0"]  = self._add_accessor(
                    j_arr, "VEC4", GLTF_UNSIGNED_BYTE, GLTF_ARRAY_BUFFER)
                attribs["WEIGHTS_0"] = self._add_accessor(
                    w_arr, "VEC4", GLTF_FLOAT, GLTF_ARRAY_BUFFER)

        if indices.max() < 65536:
            idx_acc = self._add_accessor(
                indices.astype(np.uint16).reshape(-1,1),
                "SCALAR", GLTF_UNSIGNED_SHORT, GLTF_ELEMENT_ARRAY, is_scalar=True)
        else:
            idx_acc = self._add_accessor(
                indices.astype(np.uint32).reshape(-1,1),
                "SCALAR", GLTF_UNSIGNED_INT, GLTF_ELEMENT_ARRAY, is_scalar=True)

        mat_idx = mesh.material_index if mesh.material_index < len(self._materials) else 0
        return {"attributes": attribs, "indices": idx_acc, "material": mat_idx, "mode": 4}

    def _build_skin_arrays(self, mesh: MeshDefinition):
        use_rcra = bool(mesh.flags & 0x100)
        source = self.model.rcra_weights if use_rcra else self.model.skin_weights
        weight_offset = mesh.first_weight_index if use_rcra else mesh.vertex_start
        vc    = mesh.vertex_count
        total = len(source)

        j_out = np.zeros((vc, MAX_INFLUENCES), dtype=np.uint8)
        w_out = np.zeros((vc, MAX_INFLUENCES), dtype=np.float32)
        for vi in range(vc):
            wi = weight_offset + vi
            if wi >= total: break
            for slot, (bone_idx, weight) in enumerate(source[wi][:MAX_INFLUENCES]):
                j_out[vi,slot] = int(bone_idx) & 0xFF
                w_out[vi,slot] = float(weight)
            s = w_out[vi].sum()
            if s > 0: w_out[vi] /= s
        return j_out, w_out

    # ── Accessor ──────────────────────────────────────────────────────────────

    def _add_accessor(self, arr, acc_type, component_type, target,
                      is_scalar=False, minmax=False) -> int:
        if   component_type == GLTF_FLOAT:          raw,align = arr.astype(np.float32).tobytes(),4
        elif component_type == GLTF_UNSIGNED_SHORT:  raw,align = arr.astype(np.uint16).tobytes(), 2
        elif component_type == GLTF_UNSIGNED_INT:    raw,align = arr.astype(np.uint32).tobytes(), 4
        else:                                        raw,align = arr.astype(np.uint8).tobytes(),  1

        while len(self._bin) % align: self._bin += b'\x00'
        byte_offset = len(self._bin)
        self._bin += raw

        view_idx = len(self._views)
        self._views.append({"buffer":0,"byteOffset":byte_offset,
                             "byteLength":len(raw),"target":target})

        n   = arr.size if is_scalar else arr.shape[0]
        acc = {"bufferView":view_idx,"byteOffset":0,
               "componentType":component_type,"count":n,"type":acc_type}
        if minmax and acc_type=="VEC3" and component_type==GLTF_FLOAT:
            a = arr.astype(np.float32)
            acc["min"] = a.min(axis=0).tolist()
            acc["max"] = a.max(axis=0).tolist()

        idx = len(self._accessors)
        self._accessors.append(acc)
        return idx


# ── OBJ fallback ──────────────────────────────────────────────────────────────

class ObjExporter:
    def __init__(self, model: ModelAsset, name: str = "model", lod: int = 0):
        self.model = model; self.name = name; self.lod = lod

    def export(self, path: str):
        target_meshes = [m for m in self.model.meshes
                         if m.look_index==0 and m.lod_level==self.lod]
        if not target_meshes: target_meshes = self.model.meshes

        lines = [f"# RCRA Forge OBJ export\no {self.name}\n"]
        vo = no = uo = 1
        for mi, mesh in enumerate(target_meshes):
            positions,normals,uvs,indices = mesh_to_numpy(self.model, mesh)
            if positions is None or indices is None: continue
            lines += [f"g mesh_{mi:03d}", f"usemtl mat_{mesh.material_index}"]
            for v in positions: lines.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
            if uvs is not None:
                for uv in uvs: lines.append(f"vt {uv[0]:.6f} {1-uv[1]:.6f}")
            if normals is not None:
                for n in normals: lines.append(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}")
            has_uv,has_n = uvs is not None, normals is not None
            for tri in range(0,len(indices)-2,3):
                a,b,c = int(indices[tri]),int(indices[tri+1]),int(indices[tri+2])
                def fmt(i,_vo=vo,_uo=uo,_no=no):
                    return f"{i+_vo}/{i+_uo if has_uv else ''}/{i+_no if has_n else ''}"
                lines.append(f"f {fmt(a)} {fmt(b)} {fmt(c)}")
            vo+=len(positions)
            if has_uv: uo+=len(uvs)
            if has_n:  no+=len(normals)

        lines.append("")
        with open(path,'w') as f: f.write('\n'.join(lines))
        mtl = os.path.splitext(path)[0]+'.mtl'
        mats = {m.material_index for m in target_meshes}
        with open(mtl,'w') as f:
            for mi in sorted(mats):
                f.write(f"newmtl mat_{mi}\nKd 0.8 0.8 0.8\nKa 0 0 0\nKs 0.2 0.2 0.2\nNs 32\n\n")
