"""
tests/dummy_data.py
Generate synthetic test assets using the new ModelAsset/Vertex API.
No legacy WAD/MESH lump format — tests now work against the real ALERT-based parsers.
"""

import math
import struct
from core.mesh import ModelAsset, MeshDefinition, Vertex
from core.texture import TextureAsset
from core.skeleton import Skeleton, Bone
from core.archive import AssetEntry, DAT1, DAT1_MAGIC


def make_sphere_model(radius=1.0, rings=8, sectors=12) -> ModelAsset:
    vertexes = []
    for r in range(rings + 1):
        phi = math.pi * r / rings
        for s in range(sectors + 1):
            theta = 2 * math.pi * s / sectors
            x = math.sin(phi) * math.cos(theta) * radius
            y = math.cos(phi) * radius
            z = math.sin(phi) * math.sin(theta) * radius
            nx, ny, nz = (x/radius, y/radius, z/radius) if radius > 0 else (0,1,0)
            vertexes.append(Vertex(x=x, y=y, z=z, nx=nx, ny=ny, nz=nz,
                                   u=s/sectors, v=r/rings))
    indices = []
    for r in range(rings):
        for s in range(sectors):
            a = r * (sectors + 1) + s
            b, c, d = a+1, (r+1)*(sectors+1)+s, (r+1)*(sectors+1)+s+1
            indices += [a, c, b, b, c, d]
    mesh = MeshDefinition(mesh_id=0, vertex_start=0, vertex_count=len(vertexes),
                          index_start=0, index_count=len(indices), flags=0x10,
                          material_index=0, first_skin_batch=0,
                          skin_batches_count=0, first_weight_index=0)
    return ModelAsset(vertexes=vertexes, meshes=[mesh], indexes=indices)


def make_cube_model() -> ModelAsset:
    corners = [
        (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1),
        (1,-1,-1),(-1,-1,-1),(-1,1,-1),(1,1,-1),
        (-1,1,1),(1,1,1),(1,1,-1),(-1,1,-1),
        (-1,-1,-1),(1,-1,-1),(1,-1,1),(-1,-1,1),
        (1,-1,1),(1,-1,-1),(1,1,-1),(1,1,1),
        (-1,-1,-1),(-1,-1,1),(-1,1,1),(-1,1,-1),
    ]
    normals = [(0,0,1),(0,0,-1),(0,1,0),(0,-1,0),(1,0,0),(-1,0,0)]
    uvs = [(0,0),(1,0),(1,1),(0,1)]
    vertexes = []
    for fi in range(6):
        nx, ny, nz = normals[fi]
        for vi in range(4):
            x, y, z = corners[fi*4+vi]
            u, v = uvs[vi]
            vertexes.append(Vertex(x=x,y=y,z=z,nx=nx,ny=ny,nz=nz,u=u,v=v))
    indices = []
    for fi in range(6):
        b = fi*4
        indices += [b,b+1,b+2, b,b+2,b+3]
    mesh = MeshDefinition(mesh_id=1, vertex_start=0, vertex_count=24,
                          index_start=0, index_count=36, flags=0x10,
                          material_index=0, first_skin_batch=0,
                          skin_batches_count=0, first_weight_index=0)
    return ModelAsset(vertexes=vertexes, meshes=[mesh], indexes=indices)


def make_checkerboard_texture(size=64) -> TextureAsset:
    tile = max(1, size // 8)
    pixels = bytearray()
    for y in range(size):
        for x in range(size):
            if (x//tile + y//tile) % 2 == 0:
                pixels += bytes([200, 80, 20, 255])
            else:
                pixels += bytes([30, 30, 50, 255])
    return TextureAsset(sd_len=len(pixels), sd_width=size, sd_height=size, sd_mips=1,
                        hd_len=0, hd_width=size, hd_height=size, hd_mips=1,
                        fmt=0x1C, array_size=1, planes=1, pixel_data=bytes(pixels))


def make_demo_skeleton() -> Skeleton:
    return Skeleton(bones=[
        Bone(index=0, parent=-1, name="root",  position=(0,0,0),   rotation=(0,0,0,1)),
        Bone(index=1, parent=0,  name="spine", position=(0,1,0),   rotation=(0,0,0,1)),
        Bone(index=2, parent=1,  name="chest", position=(0,1,0),   rotation=(0,0,0,1)),
        Bone(index=3, parent=2,  name="neck",  position=(0,0.5,0), rotation=(0,0,0,1)),
        Bone(index=4, parent=3,  name="head",  position=(0,0.4,0), rotation=(0,0,0,1)),
    ])


def make_fake_toc_dat1() -> bytes:
    """
    Build a minimal valid DAT1 blob that TocParser can accept.
    Contains fake archives/asset IDs/sizes sections with RCRA layout.
    """
    # We'll build: DAT1 header + 3 sections (archives, asset_ids, sizes)
    # Section tags:
    TAG_ARCHIVES  = 0x398ABFF0
    TAG_ASSET_IDS = 0x506D7B8A
    TAG_SIZES     = 0x65BCF461

    # Build archives section: 1 archive, 66 bytes
    arc_filename = b'archive_000.dat' + b'\x00' * (40 - len(b'archive_000.dat'))
    arc_entry    = arc_filename + struct.pack('<QQIHI', 0, 0, 0, 0, 0)  # 40+26=66B
    arc_data     = arc_entry

    # Build asset IDs section: 4 fake 64-bit IDs
    fake_ids = [0x8000000000000001, 0x8000000000000002,
                0x8000000000000003, 0x8000000000000004]
    ids_data = struct.pack('<4Q', *fake_ids)

    # Build sizes section: 4 entries, 16 bytes each (RCRA RcraSizeEntry)
    sizes_data = b''
    for i in range(4):
        sizes_data += struct.pack('<IIIi', 1024, 0, i * 1024, -1)

    # Assemble DAT1
    MODEL_UNK1   = 0x51B8E006  # toc
    section_count = 3
    header_size   = 16 + section_count * 12  # DAT1 header + section dir

    # String table (empty)
    string_table = b'\x00'
    # Align sections to 16
    def align16(n): return (n + 15) & ~15

    str_end     = align16(header_size + len(string_table))
    arc_off     = str_end
    ids_off     = align16(arc_off + len(arc_data))
    sizes_off   = align16(ids_off + len(ids_data))
    total_size  = align16(sizes_off + len(sizes_data))

    header = struct.pack('<III', DAT1_MAGIC, MODEL_UNK1, total_size)
    header += struct.pack('<HH', section_count, 0)
    header += struct.pack('<III', TAG_ARCHIVES, arc_off,   len(arc_data))
    header += struct.pack('<III', TAG_ASSET_IDS, ids_off,  len(ids_data))
    header += struct.pack('<III', TAG_SIZES,    sizes_off, len(sizes_data))

    dat1 = bytearray(total_size)
    dat1[:len(header)]      = header
    dat1[header_size:header_size+len(string_table)] = string_table
    dat1[arc_off:arc_off+len(arc_data)]     = arc_data
    dat1[ids_off:ids_off+len(ids_data)]     = ids_data
    dat1[sizes_off:sizes_off+len(sizes_data)] = sizes_data
    return bytes(dat1)


def make_actor_asset(model_path: str | None = None) -> bytes:
    """Build a minimal actor DAT1 with an optional linked model path."""
    from core.actor import ACTOR_TYPE, TAG_ACTOR_HEADER, TAG_ACTOR_SCENE
    from core.archive import DAT1_MAGIC

    strings = [b"Actor Built File"]
    if model_path:
        strings.append(model_path.encode("utf-8"))
    pool = b"\x00".join(strings) + b"\x00"

    section_count = 2 if model_path else 1
    header_size = 16 + section_count * 12
    section_offset = (header_size + len(pool) + 15) & ~15
    model_offset = header_size + len(strings[0]) + 1 if model_path else 0
    section_data = struct.pack('<I', model_offset)
    scene = bytearray(0x140 if model_path else 0)
    if scene:
        struct.pack_into('<16f', scene, 0, 1, 0, 0, 0, 0, 1, 0, 0,
                         0, 0, 1, 0, 0, 0, 0, 1)
        struct.pack_into('<I', scene, 0x7C, len(scene))
    total_size = section_offset + len(section_data) + len(scene)

    data = bytearray(total_size)
    header = struct.pack('<IIIHH', DAT1_MAGIC, ACTOR_TYPE, total_size, section_count, 0)
    header += struct.pack('<III', TAG_ACTOR_HEADER, section_offset, len(section_data))
    if scene:
        header += struct.pack('<III', TAG_ACTOR_SCENE, section_offset + len(section_data), len(scene))
    data[:len(header)] = header
    data[header_size:header_size + len(pool)] = pool
    data[section_offset:section_offset + len(section_data)] = section_data
    if scene:
        data[section_offset + len(section_data):] = scene
    return bytes(data)
