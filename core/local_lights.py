"""Retail local-light records and per-tile lookup iteration.

The Hair lighting compute shader reads a Texture2DArray<uint> lookup at one
texel per 8x8 full-resolution tile.  Each array slice is a 32-light word.  It
visits slices and set bits in ascending order, then indexes the 128-byte
``LightGpu`` buffer with ``slice * 32 + bit``. This module preserves the CPU
boundaries while keeping scene ownership, manager shell constants, enable
flags and filtered texture samples as explicit inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import struct

import numpy as np


LIGHT_GPU_DTYPE = np.dtype({
    'names': (
        'world_axis_x', 'bulb_radius',
        'world_axis_y', 'bulb_length',
        'world_axis_z', 'bulb_push_forward',
        'world_position', 'inverse_attenuation_radius',
        'linear_color', 'specular_intensity',
        'cone_parameters', 'cut_on_depth', 'cut_off_depth',
        'z_bin_min_max', 'bit_flags_vfog', 'mod_id_and_gobo_id',
        'clip_volume_info', 'shadow_map_info', 'shadow_volume_info',
        'reciprocal_cone_sine', 'padding',
    ),
    'formats': (
        ('<f4', 3), '<f4',
        ('<f4', 3), '<f4',
        ('<f4', 3), '<f4',
        ('<f4', 3), '<f4',
        ('<f4', 3), '<f4',
        ('<f4', 2), '<f4', '<f4',
        '<u4', '<u4', '<u4', '<u4', '<u4', '<u4', '<f4', '<f4',
    ),
    'offsets': (
        0, 12, 16, 28, 32, 44, 48, 60, 64, 76, 80, 88, 92,
        96, 100, 104, 108, 112, 116, 120, 124,
    ),
    'itemsize': 128,
})


LIGHT_VOLUME_GPU_DTYPE = np.dtype({
    'names': (
        'transform_matrix', 'atlas_coordinates', 'extents', 'fade',
        'falloff_negative', 'shadow_texel_scale', 'falloff_positive', 'misc',
    ),
    'formats': (
        ('<f4', (4, 4)), ('<f4', 4), ('<f4', 3), '<f4',
        ('<f4', 3), '<f4', ('<f4', 3), '<f4',
    ),
    'offsets': (0, 64, 80, 92, 96, 108, 112, 124),
    'itemsize': 128,
})


LIGHT_SHELL_CBUFFER_DTYPE = np.dtype({
    'names': (
        'object_to_world', 'aabb_center', 'light_gpu_id',
        'aabb_inverse_extents', 'vertex_push_scale',
    ),
    'formats': (
        ('<f4', (4, 4)), ('<f4', 3), '<u4', ('<f4', 3), '<f4',
    ),
    'offsets': (0, 64, 76, 80, 92),
    'itemsize': 96,
})


# Constants read from the pinned retail executable. ``0x1410A9710`` uses the
# radius floor at 0x142EEF9A4 and applies the other two only when byte 0x101 of
# its internal light record is 2.
LIGHT_GPU_ATTENUATION_RADIUS_FLOOR = np.float32(9.999999747378752e-06)
LIGHT_GPU_RADIANCE_COLOR_SCALE = np.float32(0.0009765625)
LIGHT_GPU_RADIANCE_SPECULAR_SCALE = np.float32(1024.0)
LIGHT_SHADOW_VOLUME_ATLAS_X_SCALE = np.float32(1.0 / 4096.0)
LIGHT_SHADOW_VOLUME_ATLAS_Y_SCALE = np.float32(1.0 / 2048.0)
LIGHT_SHADOW_VOLUME_ATLAS_X_HALF_TEXEL = np.float32(1.0 / 8192.0)
LIGHT_MANAGER_PRIORITY_RADIUS_FACTOR = np.float32(0.25)
LIGHT_MANAGER_OCCLUSION_DEPTH_BIAS = np.float32(0.01)

LIGHT_MANAGER_SECONDARY_QUERY_RADIUS = np.float32(48.0)
_LIGHT_MANAGER_SECONDARY_QUERY_COEFFICIENT_BITS = (
    (0x3f800000, 0x00000000, 0x00000000),
    (0xbf800000, 0x00000000, 0x00000000),
    (0x00000000, 0x3f800000, 0x00000000),
    (0x00000000, 0xbf800000, 0x00000000),
    (0x00000000, 0x00000000, 0x3f800000),
    (0x00000000, 0x00000000, 0xbf800000),
    (0x3f13cd36, 0x3f13cd36, 0x3f13cd36),
    (0xbf13cd36, 0x3f13cd36, 0x3f13cd36),
    (0x3f13cd36, 0xbf13cd36, 0x3f13cd36),
    (0xbf13cd36, 0xbf13cd36, 0x3f13cd36),
    (0x3f13cd36, 0x3f13cd36, 0xbf13cd36),
    (0xbf13cd36, 0x3f13cd36, 0xbf13cd36),
    (0x3f13cd36, 0xbf13cd36, 0xbf13cd36),
    (0xbf13cd36, 0xbf13cd36, 0xbf13cd36),
    (0x3f800000, 0x00000000, 0x00000000),
    (0x3f800000, 0x00000000, 0x00000000),
)


# Exact non-indexed unit-box stream shared by retail's local-light and probe
# shell producers. The local-light copy is embedded as float4 records at
# 0x14455FE70; its XYZ lanes match the probe stream at 0x1432D3AB0 bit for bit.
LIGHT_SHELL_BOX_VERTICES = (
    (-1, -1, -1), (-1, -1,  1), (-1,  1,  1),
    (-1,  1,  1), (-1,  1, -1), (-1, -1, -1),
    ( 1, -1, -1), ( 1,  1, -1), ( 1,  1,  1),
    ( 1,  1,  1), ( 1, -1,  1), ( 1, -1, -1),
    (-1, -1, -1), ( 1, -1, -1), ( 1, -1,  1),
    ( 1, -1,  1), (-1, -1,  1), (-1, -1, -1),
    (-1,  1, -1), (-1,  1,  1), ( 1,  1,  1),
    ( 1,  1,  1), ( 1,  1, -1), (-1,  1, -1),
    (-1, -1, -1), (-1,  1, -1), ( 1,  1, -1),
    ( 1,  1, -1), ( 1, -1, -1), (-1, -1, -1),
    (-1, -1,  1), ( 1, -1,  1), ( 1,  1,  1),
    ( 1,  1,  1), (-1,  1,  1), (-1, -1,  1),
)


# The 432-float4 rounded shell at 0x1452F1190 is six latitude bands of
# twelve quads. These four profiles, mirrored about Y, retain every authored
# XYZ bit including the signed zeros without duplicating the triangle stream.
_LIGHT_MANAGER_ROUND_RING_PROFILE_BITS = (
    (
        (0x80000000, 0x80000000), (0x80000000, 0x80000000),
        (0x80000000, 0x80000000), (0x00000000, 0x80000000),
        (0x00000000, 0x80000000), (0x00000000, 0x80000000),
        (0x00000000, 0x00000000), (0x00000000, 0x00000000),
        (0x00000000, 0x00000000), (0x80000000, 0x00000000),
        (0x80000000, 0x00000000), (0x80000000, 0x00000000),
    ),
    (
        (0x3F0930BE, 0x00000000), (0x3EED9E84, 0x3E8930BE),
        (0x3E8930BE, 0x3EED9E84), (0x80000000, 0x3F0930BE),
        (0xBE8930BE, 0x3EED9E84), (0xBEED9E84, 0x3E8930BE),
        (0xBF0930BE, 0x80000000), (0xBEED9E84, 0xBE8930BE),
        (0xBE8930BE, 0xBEED9E84), (0x00000000, 0xBF0930BE),
        (0x3E8930BE, 0xBEED9E84), (0x3EED9E84, 0xBE8930BE),
    ),
    (
        (0x3F6D9E84, 0x00000000), (0x3F4DC91D, 0x3EED9E84),
        (0x3EED9E84, 0x3F4DC91D), (0x80000000, 0x3F6D9E84),
        (0xBEED9E84, 0x3F4DC91D), (0xBF4DC91D, 0x3EED9E84),
        (0xBF6D9E84, 0x80000000), (0xBF4DC91D, 0xBEED9E84),
        (0xBEED9E84, 0xBF4DC91D), (0x00000000, 0xBF6D9E84),
        (0x3EED9E84, 0xBF4DC91D), (0x3F4DC91D, 0xBEED9E84),
    ),
    (
        (0x3F8930BE, 0x00000000), (0x3F6D9E84, 0x3F0930BE),
        (0x3F0930BE, 0x3F6D9E84), (0x80000000, 0x3F8930BE),
        (0xBF0930BE, 0x3F6D9E84), (0xBF6D9E84, 0x3F0930BE),
        (0xBF8930BE, 0x80000000), (0xBF6D9E84, 0xBF0930BE),
        (0xBF0930BE, 0xBF6D9E84), (0x00000000, 0xBF8930BE),
        (0x3F0930BE, 0xBF6D9E84), (0x3F6D9E84, 0xBF0930BE),
    ),
)
_LIGHT_MANAGER_ROUND_RING_PROFILE_INDICES = (0, 1, 2, 3, 2, 1, 0)
_LIGHT_MANAGER_ROUND_RING_Y_BITS = (
    0xBF84840E, 0xBF658644, 0xBF04840E, 0x00000000,
    0x3F04840E, 0x3F658644, 0x3F84840E,
)


# Double constants used by the scalar trigonometric kernels at 0x141639AE0
# and 0x14163A200. Bit construction avoids shortening their authored values.
_LIGHT_MANAGER_TRIG_C1 = struct.unpack(
    '<d', struct.pack('<Q', 0x3FF921FB520817F7))[0]
_LIGHT_MANAGER_TRIG_C3 = struct.unpack(
    '<d', struct.pack('<Q', 0xBFE4ABBC16ACF9CD))[0]
_LIGHT_MANAGER_TRIG_C5 = struct.unpack(
    '<d', struct.pack('<Q', 0x3FB4668AF65619A5))[0]
_LIGHT_MANAGER_TRIG_C7 = struct.unpack(
    '<d', struct.pack('<Q', 0xBF7324CC645B6D0E))[0]
_LIGHT_MANAGER_TRIG_C9 = struct.unpack(
    '<d', struct.pack('<Q', 0x3F23DAF748A890AF))[0]
_LIGHT_MANAGER_TRIG_INVERSE_TAU = struct.unpack(
    '<d', struct.pack('<Q', 0x3FC45F306DC9C883))[0]


@dataclass(frozen=True)
class LightLookupConstants:
    """Fields at offsets 32..47 of the 896-byte GlobalWorld cbuffer."""

    screen_to_lookup: tuple[float, float]
    z_bin_scale: float
    word_count: int


@dataclass(frozen=True)
class PointLightGeometry:
    """Base point-light result before gobo, volume and shadow modulation."""

    direction: np.ndarray
    distance_squared: float
    cone_weight: float
    radial_weight: float
    depth_weight: float
    attenuation: float
    distance_factor: float
    radiance: np.ndarray


@dataclass(frozen=True)
class HairAreaLightGeometry:
    """Hair's nonzero-radius sphere/capsule geometry before modulation."""

    direction: np.ndarray
    lobe_weights: np.ndarray
    distance_squared: float
    source_radius: float
    source_length: float
    area_metric: float
    attenuation: float
    distance_factor: float
    radiance: np.ndarray


@dataclass(frozen=True)
class LightVolumeMultiplier:
    """Color multiplier produced by a flag-2 light-volume record."""

    local_position: np.ndarray
    influence: float
    multiplier: np.ndarray


@dataclass(frozen=True)
class LightShellProjection:
    """Output of the shared retail light-shell vertex shader."""

    clip_positions: np.ndarray
    encoded_light_id: float


@dataclass(frozen=True)
class LightShellPlacement:
    """Explicit manager-owned geometry needed by the local lookup producer.

    Retail stores one arbitrary float3 triangle stream per submitted light.
    The stream and its local bounds are produced before ``FillLightLookup``;
    they are not encoded in the 128-byte ``LightGpu`` shading record.
    """

    vertices: np.ndarray
    object_to_world: np.ndarray
    local_aabb_minimum: np.ndarray
    local_aabb_maximum: np.ndarray


@dataclass(frozen=True)
class LightManagerCandidateSource:
    """Fields read from one runtime-light pointer by manager selection.

    The worker at ``0x1410B9A50`` consumes the transform, bounds, flags, type,
    fade and color fields. Consolidation at ``0x1410BA710`` additionally reads
    the masks, class and auxiliary-resource presence below. The source pointer
    and manager-owned view/filter objects remain outside this value boundary.
    """

    transform_matrix: tuple[tuple[float, float, float, float], ...]
    local_bound_center: tuple[float, float, float]
    bound_radius_scale: float
    bound_extents: tuple[float, float, float]
    runtime_flags: int
    light_type: int
    distance_fade_offset: float
    distance_fade_scale: float
    maximum_camera_distance: float
    linear_color: tuple[float, float, float]
    special_allocation_class: int = 0
    resource_flags: int = 0
    selection_layer_mask: int = 0xffffffff
    priority_layer_mask: int = 0xffffffff
    priority_class: int = 1
    has_auxiliary_resource: bool = False
    auxiliary_resource_count: int = 0
    priority_distance_padding: float = 0.0
    occlusion_half_extents: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class LightManagerSpatialAabb:
    """One spatial cell center and nonnegative half extents."""

    center: tuple[float, float, float]
    half_extents: tuple[float, float, float]


@dataclass(frozen=True)
class LightManagerSpatialAabbClassification:
    """The two outputs written by classifier ``0x141603A80``."""

    intersects: bool
    fully_inside: bool


@dataclass(frozen=True)
class LightManagerSpatialPackedBound:
    """Quantized center and radius stored in one 16-byte spatial entry."""

    center: tuple[int, int, int]
    radius: int


@dataclass(frozen=True)
class LightManagerSpatialTreeNode:
    """One retail 0x20-byte tree node used by spatial lookup."""

    origin: tuple[int, int, int]
    slots: tuple[int, int, int, int, int, int, int, int]
    depth: int = 0x10
    parent_node_index: int = -1
    parent_slot: int = 0
    active_marker: int = 1


@dataclass(frozen=True)
class LightManagerSpatialTreeLookup:
    """The node and octant slot returned by ``0x141669EA0``."""

    node_index: int
    slot_index: int
    entry: int
    levels_descended: int

@dataclass(frozen=True)
class LightManagerSpatialTreeSubdivision:
    """Node allocation and parent link produced before cell redistribution."""

    nodes: tuple[LightManagerSpatialTreeNode, ...]
    child_node_index: int
    free_head_index: int | None
    maximum_active_node_index: int

@dataclass(frozen=True)
class LightManagerSpatialTreeNodeAllocation:
    """Tree-node pool state returned by allocator ``0x141668410``."""

    nodes: tuple[LightManagerSpatialTreeNode, ...]
    allocated_node_index: int | None
    free_head_index: int | None
    free_node_chain: tuple[int, ...]
    maximum_active_node_index: int


@dataclass(frozen=True)
class LightManagerSpatialEntry:
    """The exact 16-byte source record stored in one spatial page."""

    selection_mask: int
    source_index: int
    packed_bound: LightManagerSpatialPackedBound
    reserved: int = 0


@dataclass(frozen=True)
class LightManagerSpatialRebuiltCell:
    """Cell fields rewritten by retail routine 0x14166C240."""

    center: tuple[float, float, float]
    half_extents: tuple[float, float, float]
    radius_weight: int
    state_byte: int


@dataclass(frozen=True)
class LightManagerSpatialCell:
    """Complete semantic state of one retail 0x30-byte spatial cell."""

    center: tuple[float, float, float]
    radius_weight: int
    half_extents: tuple[float, float, float]
    reserved_1c: int
    latest_page_index: int
    entry_count: int
    parent_node_index: int
    parent_slot: int
    state_byte: int
    selection_mask: int


@dataclass(frozen=True)
class LightManagerSpatialCellAllocation:
    """Cell-pool state returned by allocator ``0x141668470``."""

    cells: tuple[LightManagerSpatialCell, ...]
    allocated_cell_index: int | None
    free_head_index: int | None
    free_cell_chain: tuple[int, ...]
    maximum_active_cell_index: int
    active_cell_count: int


@dataclass(frozen=True)
class LightManagerSpatialCellRelease:
    """Cell-pool state returned by release helper 0x14166A0D0."""

    cells: tuple[LightManagerSpatialCell, ...]
    released_cell_index: int
    free_head_index: int
    free_cell_chain: tuple[int, ...]
    maximum_active_cell_index: int
    active_cell_count: int


@dataclass(frozen=True)
class LightManagerSpatialTreeChildCell:
    """One child cell created while redistributing a subdivided cell."""

    slot_index: int
    cell_index: int
    page_index: int
    parent_node_index: int
    depth: int
    metadata: int
    bound: LightManagerSpatialRebuiltCell
    entries: tuple[LightManagerSpatialEntry, ...]
    bound_entries: tuple[LightManagerSpatialEntry, ...]


@dataclass(frozen=True)
class LightManagerSpatialTreeRedistribution:
    """Successful cell redistribution produced by ``0x14166B5E0``."""

    subdivision: LightManagerSpatialTreeSubdivision
    child_cells: tuple[LightManagerSpatialTreeChildCell, ...]
    append_sequence: tuple[tuple[int, int], ...]
    active_cell_delta: int
    remaining_free_cell_indices: tuple[int, ...]
    remaining_free_page_indices: tuple[int, ...]

@dataclass(frozen=True)
class LightManagerSpatialTreeCollapse:
    """Tree/free-list state after retail empty-cell removal collapse."""

    nodes: tuple[LightManagerSpatialTreeNode, ...]
    root_index: int | None
    free_head_index: int | None
    free_node_chain: tuple[int, ...]
    freed_node_indices: tuple[int, ...]
    maximum_active_node_index: int


@dataclass(frozen=True)
class LightManagerSpatialPage:
    """One decoded 0x100-byte page in the newest-to-oldest chain."""

    older_page: int
    newer_page: int
    owning_cell: int
    active_marker: int
    reserved: int
    entries: tuple[LightManagerSpatialEntry, ...]


@dataclass(frozen=True)
class LightManagerSpatialPageAppend:
    """Page/cell state returned by retail helper ``0x141668290``."""

    pages: tuple[LightManagerSpatialPage, ...]
    success: bool
    source_handle: int
    cell_latest_page_index: int
    cell_entry_count: int
    cell_state_byte: int
    free_head_page_index: int | None
    free_page_chain: tuple[int, ...]
    appended_page_index: int | None
    appended_slot: int | None


@dataclass(frozen=True)
class LightManagerSpatialOwnerInsert:
    """Owner/pool state returned by retail insertion 0x141667E00."""

    nodes: tuple[LightManagerSpatialTreeNode, ...]
    cells: tuple[LightManagerSpatialCell, ...]
    pages: tuple[LightManagerSpatialPage, ...]
    success: bool
    source_index: int | None
    source_handle: int
    packed_entry: LightManagerSpatialEntry | None
    root_index: int | None
    free_node_chain: tuple[int, ...]
    maximum_active_node_index: int
    free_cell_chain: tuple[int, ...]
    maximum_active_cell_index: int
    active_cell_count: int
    free_page_chain: tuple[int, ...]
    live_source_count: int
    cell_index: int | None
    appended_page_index: int | None
    appended_slot: int | None
    capacity_growth_requested: bool
    helper_calls: tuple[str, ...]


@dataclass(frozen=True)
class LightManagerSpatialPrimaryQueryBuckets:
    """Worker candidates split before exact source OBB refinement."""

    direct_source_indices: tuple[int, ...]
    refinement_source_indices: tuple[int, ...]
    visited_page_indices: tuple[int, ...]


@dataclass(frozen=True)
class LightManagerSpatialOptionalQueryBuckets:
    """Optional worker candidates split before exact OBB refinement."""

    direct_source_indices: tuple[int, ...]
    refinement_source_indices: tuple[int, ...]
    visited_page_indices: tuple[int, ...]


@dataclass(frozen=True)
class LightManagerSpatialWorkerFlush:
    """One direct or exact-refinement local-bucket flush."""

    kind: str
    input_count: int
    retained_count: int
    copied_count: int
    final: bool


@dataclass(frozen=True)
class LightManagerSpatialPageQueryResolution:
    """One worker's ordered page-query output and flush trace."""

    source_indices: tuple[int, ...]
    visited_page_indices: tuple[int, ...]
    flushes: tuple[LightManagerSpatialWorkerFlush, ...]

@dataclass(frozen=True)
class LightManagerSpatialPackedSphereClassification:
    """The mask and two geometric states from the worker coarse test."""

    mask_matches: bool
    intersects: bool
    center_inside: bool


@dataclass(frozen=True)
class LightManagerSpatialOptionalPackedSphereClassification:
    """The optional worker coarse state before exact OBB refinement."""

    mask_matches: bool
    survives_coarse: bool
    direct: bool


@dataclass(frozen=True)
class LightManagerSpatialObbClassification:
    """The two outputs written by classifier ``0x141603FE0``."""

    intersects: bool
    covers_query: bool


@dataclass(frozen=True)
class LightManagerOcclusionQuery:
    """Oriented-box query assembled by ``0x14118CDC0``.

    The wrapper transforms source ``+0x40`` and ``+0x50`` into the world-space
    center and three half-extent axes consumed by the 16-bit hierarchical-depth
    test at ``0x14118CE60``.  The hierarchy itself is manager-owned frame state.
    """

    world_center: tuple[float, float, float, float]
    half_axis_x: tuple[float, float, float, float]
    half_axis_y: tuple[float, float, float, float]
    half_axis_z: tuple[float, float, float, float]
    depth_bias: float


@dataclass(frozen=True)
class LightManagerHierarchicalDepthSnapshot:
    """Explicit manager-owned inputs consumed by retail function ``0x14118CE60``.

    Each depth level stores the raw signed-16 words used by the CPU hierarchy.
    The first level has ``base_width`` columns; every following level halves
    both dimensions.  Projection and viewport values correspond to manager
    offsets ``+0x18..+0x24`` and ``+0x60..+0xd0``.
    """

    base_width: int
    camera_position: tuple[float, float, float, float]
    projection_rows: tuple[tuple[float, float, float, float], ...]
    depth_cap: float
    distance_scale: float
    near_threshold: float
    depth_scale: float
    screen_scale: tuple[float, float, float, float]
    screen_maximum: tuple[float, float, float, float]
    screen_bias: tuple[float, float, float, float]
    depth_levels: tuple[np.ndarray, ...]


@dataclass(frozen=True)
class LightManagerHierarchicalDepthResult:
    """Observable decision state from retail function ``0x14118CE60``."""

    visible: bool
    reason: str
    pixel_bounds: tuple[int, int, int, int] | None
    query_depth: int | None
    initial_mip_level: int | None
    selected_mip_level: int | None

@dataclass(frozen=True)
class LightManagerSecondaryQueryDescriptor:
    """Sphere and 0x100-byte plane descriptor built for the secondary query."""

    sphere: np.ndarray
    logical_planes: np.ndarray
    packed_planes: np.ndarray


@dataclass(frozen=True)
class LightManagerPrimaryQueryDescriptor:
    """Common six-plane plus ten edge-plane primary query descriptor."""

    base_planes: np.ndarray
    edge_points: np.ndarray
    logical_planes: np.ndarray
    packed_planes: np.ndarray


@dataclass(frozen=True)
class LightManagerPrimaryQueryAlternateDescriptor:
    """View-flag primary descriptor built from three axis extents."""

    axis_extents: np.ndarray
    translation: np.ndarray
    logical_planes: np.ndarray
    packed_planes: np.ndarray



@dataclass(frozen=True)
class LightManagerPrimaryQueryOverrideInputs:
    """Manager-owned inputs consumed by primary override 0x141234450."""

    enabled: bool = False
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    extents: tuple[float, float, float] = (0.0, 0.0, 0.0)
    terminal_normal: tuple[float, float, float] = (0.0, 0.0, 0.0)
    tail_planes: tuple[tuple[float, float, float, float], ...] = ()


@dataclass(frozen=True)
class LightManagerPrimaryQueryOverride:
    """Logical and packed output after the optional primary override."""

    logical_planes: np.ndarray
    packed_planes: np.ndarray


@dataclass(frozen=True)
class LightManagerClipResource:
    """Resolved oriented-box resource consumed by ``0x1410B6480``."""

    transform_matrix: tuple[tuple[float, float, float, float], ...]
    half_extents: tuple[float, float, float]


@dataclass(frozen=True)
class LightManagerResourceShapeInputs:
    """Type-specific source fields hashed and dispatched by shell refresh."""

    parameter_0x120: float = 0.0
    parameter_0x124: float = 0.0
    parameter_0x128: float = 0.0
    parameter_0x12c: float = 0.0
    parameter_0x130: float = 0.0
    parameter_0x134: float = 0.0
    resolved_resource_version: int | None = None
    resolved_clip_resource: LightManagerClipResource | None = None


@dataclass(frozen=True)
class LightManagerResourceVersion:
    """Cached-version result from ``0x141097250``."""

    version: int
    recomputed: bool
    cached_epoch_after: int
    cached_version_after: int


@dataclass(frozen=True)
class LightManagerResourceRefreshDispatch:
    """CPU-visible shell-refresh orchestration from ``0x14109D010``."""

    refresh_required: bool
    computed_version: int
    common_primary_parameter: float | None
    common_secondary_parameter: float | None
    resolved_resource_present: bool
    shape_builder: str | None
    shape_vector: tuple[float, float, float] | None
    shape_scalars: tuple[float, float] | None
    generated_vertex_count: int | None
    stream_allocation_bytes: int | None
    built_version_after: int


@dataclass(frozen=True)
class LightManagerResourceShellOutput:
    """Persistent shell stream and bounds written by ``0x1410B8CB0``."""

    vertices: np.ndarray
    local_aabb_minimum: np.ndarray | None
    local_aabb_maximum: np.ndarray | None
    local_bounding_sphere: np.ndarray | None
    stream_allocation_bytes: int | None
    source_bounds_update_required: bool
    source_bound_center_radius_after: np.ndarray
    source_bound_extents_after: np.ndarray


@dataclass(frozen=True)
class LightManagerSelectionDecision:
    """Exact scalar decision for one candidate before batch append."""

    selected: bool
    rejection: str | None
    normalized_runtime_flags: int
    bounding_sphere_distance: float | None = None
    distance_fade: float | None = None


@dataclass(frozen=True)
class LightManagerFrameSourceOrder:
    """CPU-visible output of manager consolidation ``0x1410BA710``.

    ``priority_indices`` are ordered by the native projected-bound score.
    ``deferred_indices`` retain their partition order and follow the priority
    entries in ``frame_indices``.  Equal-score groups are exposed because the
    retail generic sorter is not stable for every list length.
    """

    priority_indices: tuple[int, ...]
    deferred_indices: tuple[int, ...]
    frame_indices: tuple[int, ...]
    priority_scores: tuple[float, ...]
    weighted_allocation_count: int
    special_allocation_count: int
    equal_score_groups: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class LightManagerSecondaryMerge:
    """Output of the secondary-query merge inside ``0x1410BA710``."""

    merged_indices: tuple[int, ...]
    eligible_secondary_indices: tuple[int, ...]
    processed_secondary_indices: tuple[int, ...]
    appended_secondary_indices: tuple[int, ...]
    duplicate_secondary_indices: tuple[int, ...]
    runtime_flag_updates: tuple[tuple[int, int], ...]
    equal_distance_groups: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class LightManagerResourceReadinessNode:
    """One source/parent node consumed by ``0x1412B7250``.

    ``type_state_flags`` represents byte ``+0x80`` for type 0 and byte
    ``+0x170`` for type 5. Other resource types do not read it.
    """

    resource_flags: int
    resource_type: int
    type_state_flags: int = 0


@dataclass(frozen=True)
class LightManagerObjectVisibilityNode:
    """One resolved handle-chain node consumed by ``0x1412B5010``.

    For type 5, ``type_5_visibility_bits`` is the resolved byte reached through
    the optional object at ``+0x108``. ``None`` represents the native null or
    empty-object path, which does not reject the node.
    """

    resource_flags: int
    resource_type: int
    type_5_visibility_bits: int | None = None


@dataclass(frozen=True)
class LightManagerTypeResourceEntry:
    """One generation-tagged global resource-table entry."""

    generation: int
    resource_type: int
    present: bool = True


@dataclass(frozen=True)
class LightManagerTypeResourceTable:
    """Explicit snapshot consumed by ``0x141099480`` / ``0x1412B6990``."""

    entries: tuple[LightManagerTypeResourceEntry | None, ...]


@dataclass(frozen=True)
class LightManagerPartitionInputs:
    """External callback outcomes consumed by manager frame partitioning."""

    object_visibility_result: bool = True
    object_visibility_chain: tuple[LightManagerObjectVisibilityNode, ...] | None = None
    object_visibility_mask: int = 0xff
    resource_ready_result: bool = True
    resource_readiness_chain: tuple[LightManagerResourceReadinessNode, ...] | None = None
    type_resource_available: bool = True
    type_resource_handle: int | None = None
    type_resource_table: LightManagerTypeResourceTable | None = None
    auxiliary_volume_result: bool = True
    auxiliary_volume_plane_coefficients: object | None = None
    auxiliary_volume_vertices: object | None = None
    runtime_flag_21_defer_result: bool | None = None


@dataclass(frozen=True)
class LightManagerPartitionDecision:
    """Priority, deferred or skipped result for one merged manager source."""

    membership: str
    reason: str | None


@dataclass(frozen=True)
class LightManagerFramePartition:
    """Ordered partition lists and decisions from manager consolidation."""

    priority_indices: tuple[int, ...]
    deferred_indices: tuple[int, ...]
    skipped_indices: tuple[int, ...]
    decisions: tuple[tuple[int, LightManagerPartitionDecision], ...]


@dataclass(frozen=True)
class LightGpuBaseSource:
    """Inputs to the verified no-auxiliary-volume ``LightGpu`` packer path.

    These fields correspond to the persistent 0x170-byte render-light record
    consumed by executable function ``0x1410A9710``. The captured eight-light
    prefix uses subtype 1 and no clip, gobo, shadow or color-volume allocation.
    The unsupported allocation branches stay outside this type so callers
    cannot accidentally manufacture incomplete references.

    ``radiance_mode`` is native byte 0x101. The three neutrally named flag
    fields preserve bytes 0x103..0x105 until their manager-side meanings are
    independently recovered.
    """

    world_axis_x: tuple[float, float, float]
    world_axis_y: tuple[float, float, float]
    world_axis_z: tuple[float, float, float]
    world_position: tuple[float, float, float]
    attenuation_radius: float
    linear_color: tuple[float, float, float]
    specular_intensity: float
    cone_parameters: tuple[float, float]
    cut_on_depth: float
    cut_off_depth: float
    z_bin_min_depth: float
    z_bin_max_depth: float
    reciprocal_cone_sine: float
    bulb_radius: float = 0.0
    bulb_length: float = 0.0
    bulb_push_forward: float = 0.0
    volumetric_fog: float = 0.0
    base_bit_flags: int = 0
    radiance_mode: int = 0
    light_subtype: int = 1
    flag_103_bit0: bool = False
    flag_104: bool = False
    flag_105: bool = False


@dataclass(frozen=True)
class LightVolumeGpuSource:
    """Explicit fields of one native 128-byte auxiliary light record."""

    transform_matrix: tuple[tuple[float, float, float, float], ...]
    atlas_coordinates: tuple[float, float, float, float] = (0, 0, 0, 0)
    extents: tuple[float, float, float] = (0, 0, 0)
    fade: float = 0.0
    falloff_negative: tuple[float, float, float] = (0, 0, 0)
    shadow_texel_scale: float = 0.0
    falloff_positive: tuple[float, float, float] = (0, 0, 0)
    misc: float = 0.0


@dataclass(frozen=True)
class LightShadowVolumeSource:
    """Fields consumed by retail's 0x68-byte shadow-volume constructor.

    ``atlas_origin_texels`` is stored as two signed 16-bit words. The two
    encoded size words reserve bit 15 and use their low 15 bits as the atlas
    width and height. Retail copies the transform and falloff values directly
    while normalizing those four atlas words into ``LightVolumeGpu`` UVs.
    """

    transform_matrix: tuple[tuple[float, float, float, float], ...]
    falloff_negative: tuple[float, float, float]
    shadow_texel_scale: float
    atlas_origin_texels: tuple[int, int]
    atlas_size_words: tuple[int, int]
    misc: float = 0.0
    fade: float = 0.0


@dataclass(frozen=True)
class LightGoboVolumeSource:
    """Fields consumed directly by retail's subtype-1 gobo branch."""

    transform_matrix: tuple[tuple[float, float, float, float], ...]
    atlas_origin_texels: tuple[int, int]
    atlas_size_words: tuple[int, int]


@dataclass(frozen=True)
class LightColorVolumeSource:
    """Fields used by subtype 4's native color-volume constructor."""

    dimensions: tuple[float, float, float]
    negative_falloff_distances: tuple[float, float, float]
    positive_falloff_distances: tuple[float, float, float]
    fade: float = 0.0
    reciprocal_dimensions: bool = False


@dataclass(frozen=True)
class LightSubtype3ClipVolumeSource:
    """Inputs to subtype 3's scaled affine-inverse clip constructor."""

    transform_matrix: tuple[tuple[float, float, float, float], ...]
    axis_scale: tuple[float, float, float]
    map_to_unit_space: bool = False


@dataclass(frozen=True)
class LightAtlasAllocationWords:
    """The four uint16 words returned by retail's atlas-handle lookup."""

    word_0: int
    word_2: int
    word_4: int
    word_6: int


@dataclass(frozen=True)
class LightAtlasHandleTable:
    """Snapshot of retail's 8-byte atlas-allocation table and generation word."""

    generation_word: int
    allocations: tuple[LightAtlasAllocationWords, ...]


@dataclass(frozen=True)
class LightProjectedShadowMapSource:
    """Native source fields for a projected local-light shadow map."""

    transform_matrix: tuple[tuple[float, float, float, float], ...]
    atlas_allocation: LightAtlasAllocationWords
    shadow_texel_numerator: float
    fade: float = 0.0


@dataclass(frozen=True)
class LightPointShadowMapSource:
    """Native source fields for a six-face point-light shadow map."""

    face_atlas_allocations: tuple[LightAtlasAllocationWords, ...]
    projection_tail: tuple[float, float, float, float]
    shadow_texel_numerator: float
    fade: float = 0.0


@dataclass(frozen=True)
class LightGpuSubtype1AuxiliarySources:
    """Prepared native auxiliary records in retail subtype-1 categories.

    The exact gobo and shadow helpers construct these records upstream.  This
    boundary reproduces their allocation order and ``LightGpu`` references.
    """

    clip_volume: LightVolumeGpuSource | None = None
    gobo_volume: LightVolumeGpuSource | LightGoboVolumeSource | None = None
    shadow_map_volumes: tuple[
        LightVolumeGpuSource | LightProjectedShadowMapSource |
        LightPointShadowMapSource, ...
    ] = ()
    shadow_volumes: tuple[LightVolumeGpuSource | LightShadowVolumeSource, ...] = ()


@dataclass(frozen=True)
class LightGpuSubtype3AuxiliarySources:
    """Native auxiliary categories for one subtype-3 light."""

    subtype_3_clip_volume: LightVolumeGpuSource | LightSubtype3ClipVolumeSource
    clip_volume: LightVolumeGpuSource | None = None
    gobo_volume: LightVolumeGpuSource | LightGoboVolumeSource | None = None
    shadow_map_volumes: tuple[
        LightVolumeGpuSource | LightProjectedShadowMapSource |
        LightPointShadowMapSource, ...
    ] = ()
    shadow_volumes: tuple[LightVolumeGpuSource | LightShadowVolumeSource, ...] = ()


@dataclass(frozen=True)
class LightGpuSubtype4AuxiliarySources:
    """Native auxiliary categories for one subtype-4 light."""

    color_volume: LightColorVolumeSource
    clip_volume: LightVolumeGpuSource | None = None
    gobo_volume: LightVolumeGpuSource | LightGoboVolumeSource | None = None
    shadow_map_volumes: tuple[
        LightVolumeGpuSource | LightProjectedShadowMapSource |
        LightPointShadowMapSource, ...
    ] = ()
    shadow_volumes: tuple[LightVolumeGpuSource | LightShadowVolumeSource, ...] = ()


@dataclass(frozen=True)
class PackedLightGpuAuxiliaryResult:
    """One packed light plus the auxiliary records appended by that call."""

    light: np.void
    appended_volumes: np.ndarray
    next_volume_index: int
    skipped_volume_count: int


@dataclass(frozen=True)
class GoboCoordinates:
    """Atlas coordinate and edge weight from Hair's local-light gobo stage."""

    mode: str
    local_direction_or_projection: np.ndarray
    unit_uv: np.ndarray
    atlas_uv: np.ndarray
    edge_weight: float
    monochrome: bool


@dataclass(frozen=True)
class ShadowVolumeCoordinates:
    """One active shadow volume's gobo-atlas coordinate and white fade."""

    volume_index: int
    plane_distances: np.ndarray
    atlas_uv: np.ndarray
    fade_to_white: float


@dataclass(frozen=True)
class ShadowMapCoordinates:
    """One local shadow map's native atlas projection before filtering."""

    volume_index: int
    mode: str
    atlas_uv: np.ndarray
    clamp_minimum: np.ndarray
    clamp_maximum: np.ndarray
    compare_depth: float
    inverse_depth_scale: float


@dataclass(frozen=True)
class ShadowMapSamplePlan:
    """Direct comparison or four raw-depth taps for one local shadow map."""

    volume_index: int
    direct_compare: bool
    sample_uvs: np.ndarray
    compare_depth: float
    inverse_depth_scale: float
    depth_bias: float
    absorption: float


def _parse_records(data: bytes | bytearray | memoryview, dtype: np.dtype,
                   description: str) -> np.ndarray:
    raw = memoryview(data)
    if raw.nbytes % dtype.itemsize:
        raise ValueError(
            f'{description} must contain whole {dtype.itemsize}-byte records')
    return np.frombuffer(raw, dtype=dtype)


def parse_light_gpu_records(data: bytes | bytearray | memoryview) -> np.ndarray:
    """Read the shader's exact 128-byte ``LightGpu`` records."""
    return _parse_records(data, LIGHT_GPU_DTYPE, 'Light buffer')


def parse_light_volume_gpu_records(
        data: bytes | bytearray | memoryview) -> np.ndarray:
    """Read the shader's exact 128-byte ``LightVolumeGpu`` records."""
    return _parse_records(data, LIGHT_VOLUME_GPU_DTYPE, 'Light-volume buffer')


def parse_light_shell_constants(
        data: bytes | bytearray | memoryview) -> np.void:
    """Read exactly one reflected 96-byte ``LightShellCBuffer`` record."""
    records = _parse_records(data, LIGHT_SHELL_CBUFFER_DTYPE,
                             'Light-shell cbuffer')
    if len(records) != 1:
        raise ValueError('Light-shell cbuffer must contain exactly one record')
    return records[0]


def parse_light_lookup_constants(
        world_cbuffer: bytes | bytearray | memoryview) -> LightLookupConstants:
    """Read local-light lookup scale, Z-bin scale and active word count."""
    raw = memoryview(world_cbuffer)
    if raw.nbytes < 48:
        raise ValueError('GlobalWorld cbuffer must contain at least 48 bytes')
    x, y, z_scale, words = struct.unpack_from('<3fI', raw, 32)
    return LightLookupConstants((x, y), z_scale, words)


def light_lookup_word_count(record_count: int) -> int:
    """Return the number of 32-light words written for active records."""
    count = int(record_count)
    if count < 0:
        raise ValueError('Light record count cannot be negative')
    return (count + 31) // 32


def generate_light_z_bin_lookup(
        records, bin_count: int, *, record_count: int | None = None
        ) -> np.ndarray:
    """Pack retail inclusive light ranges as ``(words, bins)`` uint32.

    ``CS_LightLookupGenerateZBin`` launches one thread per requested Z bin,
    reads ``LightGpu.m_ZBinMinMax`` at byte offset 96, and walks the active
    record prefix in buffer order. The low and high 16-bit limits are both
    inclusive. A separate count is required because the structured buffer can
    contain unused capacity after the submitted records.
    """
    table = np.asarray(records)
    if table.ndim != 1 or table.dtype != LIGHT_GPU_DTYPE:
        raise ValueError('records must be parsed LightGpu records')
    count = len(table) if record_count is None else int(record_count)
    if count < 0 or count > len(table):
        raise ValueError('Active light record count exceeds supplied records')
    bins = int(bin_count)
    if bins < 0:
        raise ValueError('Z-bin count cannot be negative')

    output = np.zeros((light_lookup_word_count(count), bins), np.uint32)
    if not count or not bins:
        return output
    indices = np.arange(bins, dtype=np.uint32)
    for record_index, limits in enumerate(table['z_bin_min_max'][:count]):
        packed = np.uint32(limits)
        minimum = packed & np.uint32(0xffff)
        maximum = packed >> np.uint32(16)
        selected = (indices >= minimum) & (indices <= maximum)
        output[record_index >> 5, selected] |= np.uint32(
            1 << (record_index & 31))
    return output


def _float3(value, description: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float32)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError(f'{description} must be a finite float3')
    return result


def _finite_float32(value, description: str) -> np.float32:
    result = np.float32(value)
    if not np.isfinite(result):
        raise ValueError(f'{description} must be finite float32')
    return result


def _light_manager_round_unit_shell_vertices() -> np.ndarray:
    profiles = np.asarray(
        _LIGHT_MANAGER_ROUND_RING_PROFILE_BITS, dtype='<u4').view('<f4')
    y_values = np.asarray(
        _LIGHT_MANAGER_ROUND_RING_Y_BITS, dtype='<u4').view('<f4')
    rings = np.empty((7, 12, 3), dtype=np.float32)
    for ring_index, profile_index in enumerate(
            _LIGHT_MANAGER_ROUND_RING_PROFILE_INDICES):
        rings[ring_index, :, 0] = profiles[profile_index, :, 0]
        rings[ring_index, :, 1] = y_values[ring_index]
        rings[ring_index, :, 2] = profiles[profile_index, :, 1]

    vertices = np.empty((432, 3), dtype=np.float32)
    output_index = 0
    for band_index in range(6):
        lower = rings[band_index]
        upper = rings[band_index + 1]
        for longitude in range(12):
            following = (longitude + 1) % 12
            vertices[output_index:output_index + 6] = (
                lower[longitude], upper[longitude], lower[following],
                lower[following], upper[longitude], upper[following],
            )
            output_index += 6
    return vertices


def build_light_manager_box_shell_vertices(half_extents) -> np.ndarray:
    """Build the exact 36-vertex scaled box from ``0x1415E6D40``."""

    extents = _float3(half_extents, 'Light-manager box half extents')
    if np.any(extents < 0):
        raise ValueError('Light-manager box half extents must be nonnegative')
    source = np.asarray(LIGHT_SHELL_BOX_VERTICES, dtype=np.float32)
    return np.asarray(source * extents, dtype=np.float32)


def build_light_manager_round_shell_vertices(axis_scale) -> np.ndarray:
    """Scale retail's exact authored 432-vertex rounded shell.

    ``0x1410B58B0`` multiplies the float4 table at ``0x1452F1190`` by
    the supplied XYZ vector. Only XYZ reaches the persistent float3 stream.
    """

    scale = _float3(axis_scale, 'Light-manager rounded-shell scale')
    if np.any(scale < 0):
        raise ValueError('Light-manager rounded-shell scale must be nonnegative')
    return np.asarray(
        _light_manager_round_unit_shell_vertices() * scale,
        dtype=np.float32,
    )


def _light_manager_trig(value, *, sine: bool) -> np.float32:
    """Reproduce retail's scalar float sine/cosine polynomial."""

    normalized = float(np.float32(value)) * _LIGHT_MANAGER_TRIG_INVERSE_TAU
    if sine:
        normalized = normalized - 0.25
    whole = math.floor(normalized)
    phase = normalized - float(whole)
    scaled = phase * 4.0
    if 2.0 - scaled >= 0.0:
        reduced = 1.0 - scaled
    else:
        reduced = scaled - 3.0

    squared = reduced * reduced
    c7_term = _LIGHT_MANAGER_TRIG_C7 * reduced
    c5_term = _LIGHT_MANAGER_TRIG_C5 * reduced
    c3_term = _LIGHT_MANAGER_TRIG_C3 * reduced
    c7_term = c7_term * squared
    fourth = squared * squared
    c3_term = c3_term * squared
    c7_and_c5 = c7_term + c5_term
    c1_term = _LIGHT_MANAGER_TRIG_C1 * reduced
    c7_and_c5 = c7_and_c5 * fourth
    c3_and_c1 = c3_term + c1_term
    eighth = fourth * fourth
    c9_term = _LIGHT_MANAGER_TRIG_C9 * reduced
    result = c7_and_c5 + c3_and_c1
    c9_term = c9_term * eighth
    return np.float32(result + c9_term)


def _build_light_manager_conservative_cone_shell(
        distance, angle, *, azimuth_segments: int, polar_divisions: int,
        ) -> np.ndarray:
    """Build the shared circumscribed cone topology of the two native paths."""

    length = _finite_float32(distance, 'Light-manager cone distance')
    sweep = _finite_float32(angle, 'Light-manager cone angle')
    if length < 0 or sweep < 0:
        raise ValueError('Light-manager cone distance and angle must be nonnegative')
    if (azimuth_segments, polar_divisions) == (12, 3):
        polar_step = np.float32(sweep * np.float32(1.0 / 3.0))
        half_polar_step = np.float32(polar_step * np.float32(.5))
        azimuth_start = np.float32(-0.2617993950843811)
        azimuth_step = np.float32(0.5235987901687622)
        azimuth_half_step = np.float32(0.2617993950843811)
    elif (azimuth_segments, polar_divisions) == (4, 2):
        polar_step = np.float32(sweep * np.float32(.5))
        half_polar_step = np.float32(sweep * np.float32(.25))
        azimuth_start = np.float32(-0.7853981852531433)
        azimuth_step = np.float32(1.5707963705062866)
        azimuth_half_step = np.float32(0.7853981852531433)
    else:  # Private callers pin the two layouts emitted by retail.
        raise ValueError('Unsupported light-manager cone tessellation')

    polar_denominator = _light_manager_trig(half_polar_step, sine=False)
    azimuth_denominator = _light_manager_trig(
        azimuth_half_step, sine=False)
    if polar_denominator == 0 or azimuth_denominator == 0:
        raise ValueError('Light-manager cone angle produces an unbounded shell')
    polar_scale = np.float32(np.float32(1) / polar_denominator)
    azimuth_scale = np.float32(polar_scale / azimuth_denominator)
    apex_z = np.float32(polar_scale * length)

    azimuth_cosines = np.empty(azimuth_segments, dtype=np.float32)
    azimuth_sines = np.empty(azimuth_segments, dtype=np.float32)
    azimuth = azimuth_start
    for index in range(azimuth_segments):
        azimuth_cosines[index] = _light_manager_trig(
            azimuth, sine=False)
        azimuth_sines[index] = _light_manager_trig(azimuth, sine=True)
        azimuth = np.float32(azimuth + azimuth_step)

    rings = np.empty(
        (polar_divisions, azimuth_segments, 3), dtype=np.float32)
    half_pi = np.float32(1.5707963705062866)
    for division in range(1, polar_divisions + 1):
        polar_angle = np.float32(
            half_pi - np.float32(np.float32(division) * polar_step))
        vertical = _light_manager_trig(polar_angle, sine=True)
        vertical = np.float32(np.float32(vertical * polar_scale) * length)
        radial = _light_manager_trig(polar_angle, sine=False)
        radial = np.float32(np.float32(radial * azimuth_scale) * length)
        rings[division - 1, :, 0] = np.asarray(
            azimuth_cosines * radial, dtype=np.float32)
        rings[division - 1, :, 1] = np.asarray(
            azimuth_sines * radial, dtype=np.float32)
        rings[division - 1, :, 2] = vertical

    triangles: list[np.ndarray] = []
    apex = np.asarray((0, 0, apex_z), dtype=np.float32)
    origin = np.zeros(3, dtype=np.float32)
    first_ring = rings[0]
    for index in range(azimuth_segments):
        following = (index + 1) % azimuth_segments
        triangles.extend((apex, first_ring[index], first_ring[following]))
    for division in range(polar_divisions - 1):
        upper = rings[division]
        lower = rings[division + 1]
        for index in range(azimuth_segments):
            following = (index + 1) % azimuth_segments
            triangles.extend((
                upper[index], lower[index], upper[following],
                upper[following], lower[index], lower[following],
            ))
    final_ring = rings[-1]
    for index in range(azimuth_segments):
        following = (index + 1) % azimuth_segments
        triangles.extend((final_ring[index], origin, final_ring[following]))
    result = np.asarray(triangles, dtype=np.float32).reshape(-1, 3)
    if not np.isfinite(result).all():
        raise ValueError('Light-manager cone parameters produce nonfinite vertices')
    return result


def build_light_manager_type_1_shell_vertices(distance, angle) -> np.ndarray:
    """Build the 216-vertex shell from ``0x1410B76B0``."""

    return _build_light_manager_conservative_cone_shell(
        distance, angle, azimuth_segments=12, polar_divisions=3)


def build_light_manager_type_2_shell_vertices(distance, angle) -> np.ndarray:
    """Build the 48-vertex shell from ``0x1410B8620``."""

    return _build_light_manager_conservative_cone_shell(
        distance, angle, azimuth_segments=4, polar_divisions=2)


def _native_float3_distance(first, second) -> np.float32:
    """Reproduce the overflow-safe scalar length at ``0x140389950``."""

    left = _float3(first, 'Distance first point')
    right = _float3(second, 'Distance second point')
    delta = np.asarray(left - right, dtype=np.float32)
    maximum = np.maximum(np.abs(delta[2]), np.abs(delta[1]))
    maximum = np.float32(np.maximum(maximum, np.abs(delta[0])))
    if maximum <= np.float32(0):
        return np.float32(0)
    reciprocal = np.float32(np.float32(1) / maximum)
    scaled_x = np.float32(delta[0] * reciprocal)
    scaled_y = np.float32(delta[1] * reciprocal)
    scaled_z = np.float32(delta[2] * reciprocal)
    squared_yx = np.float32(
        np.float32(scaled_y * scaled_y) + np.float32(scaled_x * scaled_x))
    squared = np.float32(squared_yx + np.float32(scaled_z * scaled_z))
    return np.float32(np.float32(np.sqrt(squared)) * maximum)


def _light_manager_world_bound_center(
        source: LightManagerCandidateSource) -> np.ndarray:
    matrix = np.asarray(source.transform_matrix, dtype=np.float32)
    center = _float3(source.local_bound_center, 'Manager local bound center')
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Manager candidate transform must be a finite float4x4')

    world_center = np.empty(3, dtype=np.float32)
    for column in range(3):
        zx = np.float32(
            np.float32(center[2] * matrix[2, column])
            + np.float32(center[0] * matrix[0, column]))
        yt = np.float32(
            np.float32(center[1] * matrix[1, column])
            + matrix[3, column])
        world_center[column] = np.float32(zx + yt)
    return world_center


def build_light_manager_secondary_query_sphere(
        manager_axis_z, manager_translation, forward_distance,
        ) -> np.ndarray:
    """Build the float4 sphere written by retail function 0x1411F2C10.

    Passing None for both manager-owned vectors models the native null-manager
    path. A present manager uses translation + forward_distance * axis_z for
    XYZ and the fixed 48.0 radius for W.
    """

    if manager_axis_z is None or manager_translation is None:
        if manager_axis_z is None and manager_translation is None:
            return np.zeros(4, dtype=np.float32)
        raise ValueError(
            'Manager axis Z and translation must either both be present or '
            'both be None')
    axis_z = _float3(manager_axis_z, 'Manager axis Z')
    translation = _float3(manager_translation, 'Manager translation')
    distance = _finite_float32(
        forward_distance, 'Manager secondary-query forward distance')
    result = np.empty(4, dtype=np.float32)
    for component in range(3):
        result[component] = np.float32(
            np.float32(distance * axis_z[component]) + translation[component])
    result[3] = LIGHT_MANAGER_SECONDARY_QUERY_RADIUS
    return result


def build_light_manager_secondary_query_descriptor(
        sphere) -> LightManagerSecondaryQueryDescriptor:
    """Build the exact SIMD-packed 16-plane descriptor from 0x141602E10.

    The 16 logical float4 planes retain coefficient-table order. Retail stores
    each group of four planes component-major, so packed_planes has shape
    (4, 4, 4) indexed by group, component, then lane and occupies 0x100 bytes.
    """

    values = np.asarray(sphere, dtype=np.float32)
    if values.shape != (4,) or not np.isfinite(values).all():
        raise ValueError(
            'Manager secondary-query sphere must be one finite float4')
    coefficient_bits = np.asarray(
        _LIGHT_MANAGER_SECONDARY_QUERY_COEFFICIENT_BITS, dtype='<u4')
    coefficients = coefficient_bits.view('<f4')
    planes = np.empty((16, 4), dtype='<f4')
    planes[:, :3] = coefficients
    center = values[:3]
    plane_offset = np.float32(values[3])
    for index, coefficient in enumerate(coefficients):
        yx = np.float32(
            np.float32(coefficient[1] * center[1])
            + np.float32(coefficient[0] * center[0]))
        dot = np.float32(
            yx + np.float32(coefficient[2] * center[2]))
        planes[index, 3] = np.float32(plane_offset - dot)
    packed = planes.reshape(4, 4, 4).transpose(0, 2, 1).copy()
    return LightManagerSecondaryQueryDescriptor(
        sphere=values.copy(),
        logical_planes=planes,
        packed_planes=packed,
    )


def _light_manager_normalize_primary_query_vector(values) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float32)
    x, y, z = vector
    maximum = np.float32(np.maximum(np.abs(z), np.abs(y)))
    maximum = np.float32(np.maximum(maximum, np.abs(x)))
    if maximum <= np.float32(0):
        return vector.copy()
    scale = np.float32(np.float32(1) / maximum)
    scaled_y = np.float32(y * scale)
    scaled_z = np.float32(z * scale)
    scaled_x = np.float32(x * scale)
    squared_yx = np.float32(
        np.float32(scaled_y * scaled_y)
        + np.float32(scaled_x * scaled_x))
    squared = np.float32(
        squared_yx + np.float32(scaled_z * scaled_z))
    reciprocal_length = np.float32(
        np.float32(1) / np.sqrt(squared, dtype=np.float32))
    return np.asarray((
        np.float32(reciprocal_length * scaled_x),
        np.float32(reciprocal_length * scaled_y),
        np.float32(reciprocal_length * scaled_z),
    ), dtype=np.float32)


def _build_light_manager_primary_edge_plane(
        first_point, second_point, first_plane, second_plane,
        ) -> np.ndarray:
    first = np.asarray(first_point, dtype=np.float32)
    second = np.asarray(second_point, dtype=np.float32)
    plane_a = np.asarray(first_plane, dtype=np.float32)
    plane_b = np.asarray(second_plane, dtype=np.float32)
    edge = _light_manager_normalize_primary_query_vector(
        np.asarray((
            np.float32(second[0] - first[0]),
            np.float32(second[1] - first[1]),
            np.float32(second[2] - first[2]),
        ), dtype=np.float32))
    plane_sum = _light_manager_normalize_primary_query_vector(
        np.asarray((
            np.float32(plane_a[0] + plane_b[0]),
            np.float32(plane_a[1] + plane_b[1]),
            np.float32(plane_a[2] + plane_b[2]),
        ), dtype=np.float32))
    cross_x = np.float32(
        np.float32(plane_sum[1] * edge[2])
        - np.float32(plane_sum[2] * edge[1]))
    cross_y = np.float32(
        np.float32(plane_sum[2] * edge[0])
        - np.float32(plane_sum[0] * edge[2]))
    cross_z = np.float32(
        np.float32(plane_sum[0] * edge[1])
        - np.float32(edge[0] * plane_sum[1]))
    normal_x = np.float32(
        np.float32(cross_z * edge[1])
        - np.float32(cross_y * edge[2]))
    normal_y = np.float32(
        np.float32(cross_x * edge[2])
        - np.float32(cross_z * edge[0]))
    normal_z = np.float32(
        np.float32(cross_y * edge[0])
        - np.float32(cross_x * edge[1]))
    normal = np.asarray((normal_x, normal_y, normal_z), dtype=np.float32)
    yx = np.float32(
        np.float32(first[1] * normal[1])
        + np.float32(first[0] * normal[0]))
    dot = np.float32(
        yx + np.float32(first[2] * normal[2]))
    result = np.empty(4, dtype='<f4')
    result[:3] = normal
    result.view('<u4')[3] = (
        np.asarray(dot, dtype='<f4').view('<u4')
        ^ np.uint32(0x80000000))
    return result


def build_light_manager_primary_query_base_descriptor(
        base_planes, edge_points) -> LightManagerPrimaryQueryDescriptor:
    """Build the common primary descriptor from 0x141600E30.

    The six input float4 planes are copied directly. Ten further planes are
    derived from the eight float3 edge points and fixed pairs of base planes.
    The packed result uses the same four component-major 4x4 groups as the
    submitted 0x100-byte descriptor.
    """

    base = np.asarray(base_planes, dtype=np.float32)
    points = np.asarray(edge_points, dtype=np.float32)
    if base.shape != (6, 4) or not np.isfinite(base).all():
        raise ValueError(
            'Manager primary base planes must have shape (6, 4) and be finite')
    if points.shape != (8, 3) or not np.isfinite(points).all():
        raise ValueError(
            'Manager primary edge points must have shape (8, 3) and be finite')
    derived_inputs = (
        (0, 4, 3, 1),
        (2, 6, 1, 4),
        (3, 7, 4, 2),
        (1, 5, 2, 3),
        (0, 2, 0, 1),
        (3, 1, 0, 2),
        (4, 6, 5, 1),
        (6, 7, 5, 4),
        (7, 5, 5, 2),
        (5, 4, 5, 3),
    )
    logical = np.empty((16, 4), dtype='<f4')
    logical[:6] = base
    for output_index, (first, second, plane_a, plane_b) in enumerate(
            derived_inputs, start=6):
        logical[output_index] = _build_light_manager_primary_edge_plane(
            points[first], points[second], base[plane_a], base[plane_b])
    packed = logical.reshape(4, 4, 4).transpose(0, 2, 1).copy()
    return LightManagerPrimaryQueryDescriptor(
        base_planes=base.copy(),
        edge_points=points.copy(),
        logical_planes=logical,
        packed_planes=packed,
    )



def _light_manager_float32_sign_flip(value) -> np.float32:
    scalar = np.asarray(np.float32(value), dtype='<f4')
    bits = np.asarray(scalar.view('<u4') ^ np.uint32(0x80000000),
                      dtype='<u4')
    return bits.view('<f4')[()]


def build_light_manager_primary_query_alternate_descriptor(
        axis_extents, translation,
        ) -> LightManagerPrimaryQueryAlternateDescriptor:
    """Build the exact view-flag primary descriptor from its OBB inputs."""

    rows = np.asarray(axis_extents, dtype=np.float32)
    position = _float3(
        translation, 'Manager alternate primary translation')
    if rows.shape != (3, 4) or not np.isfinite(rows).all():
        raise ValueError(
            'Manager alternate primary axis extents must have shape '
            '(3, 4) and be finite')
    axes = rows[:, :3]
    extents = rows[:, 3]
    logical = np.empty((16, 4), dtype='<f4')

    def add(first, second):
        return np.float32(np.float32(first) + np.float32(second))

    def sub(first, second):
        return np.float32(np.float32(first) - np.float32(second))

    def multiply(first, second):
        return np.float32(np.float32(first) * np.float32(second))

    def signed_axis(axis, sign):
        if sign > 0:
            return np.asarray(axis, dtype=np.float32).copy()
        return np.asarray([
            _light_manager_float32_sign_flip(value) for value in axis
        ], dtype=np.float32)

    def dot_yxz(first, second):
        return add(
            add(
                multiply(first[1], second[1]),
                multiply(first[0], second[0]),
            ),
            multiply(first[2], second[2]),
        )

    output_index = 0
    for axis, extent in zip(axes, extents):
        logical[output_index, :3] = axis
        positive_support = np.asarray([
            sub(multiply(extent, axis[lane]), position[lane])
            for lane in range(3)
        ], dtype=np.float32)
        logical[output_index, 3] = dot_yxz(axis, positive_support)
        output_index += 1

        negative = signed_axis(axis, -1)
        logical[output_index, :3] = negative
        negative_support = np.asarray([
            add(multiply(extent, axis[lane]), position[lane])
            for lane in range(3)
        ], dtype=np.float32)
        logical[output_index, 3] = _light_manager_float32_sign_flip(
            dot_yxz(negative, negative_support))
        output_index += 1

    pairs = (
        (1, 2, 1, 1),
        (1, 2, -1, 1),
        (1, 2, 1, -1),
        (1, 2, -1, -1),
        (0, 2, 1, 1),
        (0, 2, 1, -1),
        (0, 2, -1, 1),
        (0, 2, -1, -1),
        (0, 1, 1, 1),
        (0, 1, -1, 1),
    )
    for first_index, second_index, first_sign, second_sign in pairs:
        first = axes[first_index]
        second = axes[second_index]
        first_extent = extents[first_index]
        second_extent = extents[second_index]
        if output_index == 11:
            raw_normal = [
                sub(first[lane], second[lane]) for lane in range(3)
            ]
            support = np.asarray([
                sub(
                    multiply(first_extent, first[lane]),
                    add(
                        multiply(second_extent, second[lane]),
                        position[lane],
                    ),
                )
                for lane in range(3)
            ], dtype=np.float32)
            flip_distance = False
        elif output_index == 12:
            raw_normal = [
                sub(second[lane], first[lane]) for lane in range(3)
            ]
            support = np.asarray([
                add(
                    sub(
                        position[lane],
                        multiply(second_extent, second[lane]),
                    ),
                    multiply(first_extent, first[lane]),
                )
                for lane in range(3)
            ], dtype=np.float32)
            flip_distance = True
        elif first_sign > 0 and second_sign > 0:
            raw_normal = [
                add(first[lane], second[lane]) for lane in range(3)
            ]
            support = np.asarray([
                sub(
                    multiply(second_extent, second[lane]),
                    sub(
                        position[lane],
                        multiply(first_extent, first[lane]),
                    ),
                )
                for lane in range(3)
            ], dtype=np.float32)
            flip_distance = False
        elif first_sign < 0 and second_sign > 0:
            raw_normal = [
                sub(second[lane], first[lane]) for lane in range(3)
            ]
            support = np.asarray([
                sub(
                    multiply(second_extent, second[lane]),
                    add(
                        multiply(first_extent, first[lane]),
                        position[lane],
                    ),
                )
                for lane in range(3)
            ], dtype=np.float32)
            flip_distance = False
        elif first_sign > 0 and second_sign < 0:
            raw_normal = [
                sub(first[lane], second[lane]) for lane in range(3)
            ]
            support = np.asarray([
                add(
                    sub(
                        position[lane],
                        multiply(first_extent, first[lane]),
                    ),
                    multiply(second_extent, second[lane]),
                )
                for lane in range(3)
            ], dtype=np.float32)
            flip_distance = True
        else:
            raw_normal = [
                sub(
                    _light_manager_float32_sign_flip(first[lane]),
                    second[lane],
                )
                for lane in range(3)
            ]
            support = np.asarray([
                add(
                    add(
                        multiply(first_extent, first[lane]),
                        position[lane],
                    ),
                    multiply(second_extent, second[lane]),
                )
                for lane in range(3)
            ], dtype=np.float32)
            flip_distance = True
        normal = _light_manager_normalize_primary_query_vector(raw_normal)
        distance = dot_yxz(normal, support)
        if flip_distance:
            distance = _light_manager_float32_sign_flip(distance)
        logical[output_index, :3] = normal
        logical[output_index, 3] = distance
        output_index += 1

    packed = logical.reshape(4, 4, 4).transpose(0, 2, 1).copy()
    return LightManagerPrimaryQueryAlternateDescriptor(
        axis_extents=rows.copy(),
        translation=position.copy(),
        logical_planes=logical,
        packed_planes=packed,
    )


def _build_light_manager_primary_triangle_plane(
        origin, first_point, second_point) -> np.ndarray:
    base = np.asarray(origin, dtype=np.float32)
    first = np.asarray(first_point, dtype=np.float32)
    second = np.asarray(second_point, dtype=np.float32)
    first_vector = np.asarray((
        np.float32(first[0] - base[0]),
        np.float32(first[1] - base[1]),
        np.float32(first[2] - base[2]),
    ), dtype=np.float32)
    second_vector = np.asarray((
        np.float32(second[0] - base[0]),
        np.float32(second[1] - base[1]),
        np.float32(second[2] - base[2]),
    ), dtype=np.float32)
    cross_x = np.float32(
        np.float32(second_vector[1] * first_vector[2])
        - np.float32(second_vector[2] * first_vector[1]))
    cross_y = np.float32(
        np.float32(second_vector[2] * first_vector[0])
        - np.float32(second_vector[0] * first_vector[2]))
    cross_z = np.float32(
        np.float32(second_vector[0] * first_vector[1])
        - np.float32(second_vector[1] * first_vector[0]))
    normal = _light_manager_normalize_primary_query_vector(
        (cross_x, cross_y, cross_z))
    yx = np.float32(
        np.float32(normal[1] * base[1])
        + np.float32(normal[0] * base[0]))
    dot = np.float32(yx + np.float32(normal[2] * base[2]))
    return np.asarray((
        normal[0], normal[1], normal[2],
        _light_manager_float32_sign_flip(dot),
    ), dtype=np.float32)


def apply_light_manager_primary_query_override(
        descriptor, inputs: LightManagerPrimaryQueryOverrideInputs,
        ) -> LightManagerPrimaryQueryOverride:
    """Apply the exact plane 11-15 override and two-plane tail copy."""

    if isinstance(descriptor, LightManagerPrimaryQueryDescriptor):
        logical = descriptor.logical_planes.copy()
    elif isinstance(descriptor, LightManagerPrimaryQueryOverride):
        logical = descriptor.logical_planes.copy()
    else:
        logical = np.asarray(descriptor, dtype=np.float32)
        if logical.shape == (4, 4, 4):
            logical = logical.transpose(0, 2, 1).reshape(16, 4).copy()
        elif logical.shape == (16, 4):
            logical = logical.copy()
        else:
            raise ValueError(
                'Manager primary descriptor must have shape (16, 4) or '
                'packed shape (4, 4, 4)')
    if logical.shape != (16, 4) or not np.isfinite(logical).all():
        raise ValueError('Manager primary descriptor planes must be finite')
    if not isinstance(inputs, LightManagerPrimaryQueryOverrideInputs):
        raise ValueError(
            'inputs must be LightManagerPrimaryQueryOverrideInputs')
    if not inputs.enabled:
        packed = logical.reshape(4, 4, 4).transpose(0, 2, 1).copy()
        return LightManagerPrimaryQueryOverride(logical, packed)

    origin = _float3(inputs.origin, 'Manager primary override origin')
    center = _float3(inputs.center, 'Manager primary override center')
    axis = _float3(inputs.axis_offset, 'Manager primary override axis offset')
    extents = _float3(inputs.extents, 'Manager primary override extents')
    terminal = _float3(
        inputs.terminal_normal, 'Manager primary override terminal normal')
    tail = np.asarray(inputs.tail_planes, dtype=np.float32)
    if len(inputs.tail_planes) == 0:
        tail = np.empty((0, 4), dtype=np.float32)
    if (tail.ndim != 2 or tail.shape[1:] != (4,)
            or len(tail) > 2 or not np.isfinite(tail).all()):
        raise ValueError(
            'Manager primary override tail must contain zero to two '
            'finite float4 planes')

    def add(first, second):
        return np.float32(np.float32(first) + np.float32(second))

    def sub(first, second):
        return np.float32(np.float32(first) - np.float32(second))

    plus = np.asarray((
        add(center[0], extents[0]),
        add(center[1], extents[1]),
        add(center[2], extents[2]),
    ), dtype=np.float32)
    minus = np.asarray((
        sub(center[0], extents[0]),
        sub(center[1], extents[1]),
        sub(center[2], extents[2]),
    ), dtype=np.float32)
    plus_minus_axis = np.asarray((
        sub(plus[0], axis[0]),
        sub(plus[1], axis[1]),
        sub(plus[2], axis[2]),
    ), dtype=np.float32)
    minus_minus_axis = np.asarray((
        sub(minus[0], axis[0]),
        sub(minus[1], axis[1]),
        sub(minus[2], axis[2]),
    ), dtype=np.float32)
    plus_plus_axis = np.asarray((
        add(axis[0], plus[0]),
        add(axis[1], plus[1]),
        add(axis[2], plus[2]),
    ), dtype=np.float32)
    minus_plus_axis = np.asarray((
        add(axis[0], minus[0]),
        add(axis[1], minus[1]),
        add(axis[2], minus[2]),
    ), dtype=np.float32)

    point_pairs = (
        (minus_minus_axis, plus_minus_axis),
        (plus_minus_axis, plus_plus_axis),
        (plus_plus_axis, minus_plus_axis),
        (minus_plus_axis, minus_minus_axis),
    )
    for plane_index, (first, second) in enumerate(
            point_pairs, start=11):
        logical[plane_index] = _build_light_manager_primary_triangle_plane(
            origin, first, second)

    terminal_yx = np.float32(
        np.float32(terminal[1] * center[1])
        + np.float32(terminal[0] * center[0]))
    terminal_dot = np.float32(
        terminal_yx + np.float32(terminal[2] * center[2]))
    logical[15, :3] = terminal
    logical[15, 3] = _light_manager_float32_sign_flip(terminal_dot)
    if len(tail):
        logical[16 - len(tail):] = tail
    packed = logical.reshape(4, 4, 4).transpose(0, 2, 1).copy()
    return LightManagerPrimaryQueryOverride(logical, packed)


def build_light_manager_occlusion_query(
        source: LightManagerCandidateSource, *,
        depth_bias=LIGHT_MANAGER_OCCLUSION_DEPTH_BIAS,
        ) -> LightManagerOcclusionQuery:
    """Build the exact OBB inputs prepared by wrapper ``0x14118CDC0``.

    Retail multiplies source ``+0x50`` xyz by the respective transform rows,
    then transforms source ``+0x40`` xyz with row 3 translation.  SIMD lanes
    and add order are retained in binary32.  The returned query is the complete
    source-owned input to ``0x14118CE60``; evaluating it also needs the
    manager's current hierarchical-depth snapshot.
    """

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    matrix = np.asarray(source.transform_matrix, dtype=np.float32)
    center = _float3(source.local_bound_center, 'Manager local bound center')
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Manager candidate transform must be a finite float4x4')
    if source.occlusion_half_extents is None:
        raise ValueError(
            'Manager occlusion half extents are required for the view query')
    extents = _float3(
        source.occlusion_half_extents, 'Manager occlusion half extents')
    if np.any(extents < 0):
        raise ValueError('Manager occlusion half extents must be nonnegative')
    bias = _finite_float32(depth_bias, 'Manager occlusion depth bias')

    half_axis_x = np.asarray(
        matrix[0] * np.float32(extents[0]), dtype=np.float32)
    half_axis_y = np.asarray(
        matrix[1] * np.float32(extents[1]), dtype=np.float32)
    half_axis_z = np.asarray(
        matrix[2] * np.float32(extents[2]), dtype=np.float32)
    world_center = np.asarray(
        np.asarray(
            np.asarray(matrix[0] * np.float32(center[0]), dtype=np.float32)
            + matrix[3], dtype=np.float32)
        + np.asarray(matrix[1] * np.float32(center[1]), dtype=np.float32),
        dtype=np.float32)
    world_center = np.asarray(
        world_center
        + np.asarray(matrix[2] * np.float32(center[2]), dtype=np.float32),
        dtype=np.float32)

    def float4(values):
        return tuple(float(value) for value in values)

    return LightManagerOcclusionQuery(
        world_center=float4(world_center),
        half_axis_x=float4(half_axis_x),
        half_axis_y=float4(half_axis_y),
        half_axis_z=float4(half_axis_z),
        depth_bias=float(bias),
    )


def evaluate_light_manager_hierarchical_depth(
        query: LightManagerOcclusionQuery,
        snapshot: LightManagerHierarchicalDepthSnapshot,
        ) -> LightManagerHierarchicalDepthResult:
    """Evaluate retail's CPU hierarchical-depth test at ``0x14118CE60``.

    The routine projects all eight OBB corners, computes a conservative 16-bit
    depth threshold, tests the four base-level corners, chooses a mip from the
    integer rectangle span, and scans the exact base rectangle only when that
    coarse test is inconclusive.  Frame-specific hierarchy contents stay an
    explicit input.
    """

    if not isinstance(query, LightManagerOcclusionQuery):
        raise ValueError('query must be one LightManagerOcclusionQuery')
    if not isinstance(snapshot, LightManagerHierarchicalDepthSnapshot):
        raise ValueError(
            'snapshot must be one LightManagerHierarchicalDepthSnapshot')

    def float4(value, description):
        result = np.asarray(value, dtype=np.float32)
        if result.shape != (4,) or not np.isfinite(result).all():
            raise ValueError(f'{description} must be one finite float4')
        return result

    center = float4(query.world_center, 'Manager occlusion center')
    axes = np.asarray((
        float4(query.half_axis_x, 'Manager occlusion half axis X'),
        float4(query.half_axis_y, 'Manager occlusion half axis Y'),
        float4(query.half_axis_z, 'Manager occlusion half axis Z'),
    ), dtype=np.float32)
    camera = float4(snapshot.camera_position, 'Manager hierarchy camera')
    projection = np.asarray(snapshot.projection_rows, dtype=np.float32)
    if projection.shape != (4, 4) or not np.isfinite(projection).all():
        raise ValueError('Manager hierarchy projection must be a finite float4x4')
    screen_scale = float4(
        snapshot.screen_scale, 'Manager hierarchy screen scale')
    screen_maximum = float4(
        snapshot.screen_maximum, 'Manager hierarchy screen maximum')
    screen_bias = float4(
        snapshot.screen_bias, 'Manager hierarchy screen bias')
    if np.any(screen_maximum < 0):
        raise ValueError('Manager hierarchy screen maximum must be nonnegative')

    depth_cap = _finite_float32(
        snapshot.depth_cap, 'Manager hierarchy depth cap')
    distance_scale = _finite_float32(
        snapshot.distance_scale, 'Manager hierarchy distance scale')
    near_threshold = _finite_float32(
        snapshot.near_threshold, 'Manager hierarchy near threshold')
    depth_scale = _finite_float32(
        snapshot.depth_scale, 'Manager hierarchy depth scale')
    bias = _finite_float32(query.depth_bias, 'Manager occlusion depth bias')
    base_width = _bounded_integer(
        snapshot.base_width, 1, 1 << 30, 'Manager hierarchy base width')
    if base_width & (base_width - 1):
        raise ValueError('Manager hierarchy base width must be a power of two')
    if not snapshot.depth_levels:
        raise ValueError('Manager hierarchy must contain at least one depth level')

    depth_levels = []
    base_height = None
    for level, values in enumerate(snapshot.depth_levels):
        source = np.asarray(values)
        if source.ndim != 2 or not np.issubdtype(source.dtype, np.integer):
            raise ValueError(
                f'Manager hierarchy level {level} must be a 2D integer array')
        if source.size:
            minimum = int(source.min())
            maximum = int(source.max())
            if minimum < -32768 or maximum > 65535:
                raise ValueError(
                    f'Manager hierarchy level {level} words exceed 16 bits')
        raw = np.asarray(source, dtype='<u2')
        signed = raw.view('<i2')
        if level == 0:
            base_height = signed.shape[0]
            if signed.shape[1] != base_width or base_height < 1:
                raise ValueError(
                    'Manager hierarchy base dimensions do not match base_width')
        expected = (max(1, base_height >> level),
                    max(1, base_width >> level))
        if signed.shape != expected:
            raise ValueError(
                f'Manager hierarchy level {level} must have shape {expected}')
        depth_levels.append(signed)
    if (screen_maximum[0] >= base_width
            or screen_maximum[2] >= base_width
            or screen_maximum[1] >= base_height
            or screen_maximum[3] >= base_height):
        raise ValueError('Manager hierarchy screen maximum exceeds level zero')

    # The SIMD routine transposes the three axes, calculates their reciprocal
    # lengths, and obtains the camera distance outside the OBB in that basis.
    lengths_squared = np.asarray(
        np.asarray(axes[:, 2] * axes[:, 2], dtype=np.float32)
        + np.asarray(axes[:, 1] * axes[:, 1], dtype=np.float32),
        dtype=np.float32)
    lengths_squared = np.asarray(
        lengths_squared
        + np.asarray(axes[:, 0] * axes[:, 0], dtype=np.float32),
        dtype=np.float32)
    reciprocal_lengths = np.asarray(
        np.float32(1.0)
        / np.sqrt(np.maximum(lengths_squared, np.float32(1e-6))),
        dtype=np.float32)
    axis_lengths = np.asarray(
        reciprocal_lengths * lengths_squared, dtype=np.float32)
    delta = np.asarray(camera[:3] - center[:3], dtype=np.float32)
    projected_delta = np.asarray(
        np.asarray(delta[1] * axes[:, 1], dtype=np.float32)
        + np.asarray(delta[0] * axes[:, 0], dtype=np.float32),
        dtype=np.float32)
    projected_delta = np.asarray(
        projected_delta
        + np.asarray(delta[2] * axes[:, 2], dtype=np.float32),
        dtype=np.float32)
    projected_delta = np.asarray(
        projected_delta * reciprocal_lengths, dtype=np.float32)
    closest = np.minimum(projected_delta, axis_lengths)
    closest = np.maximum(closest, np.asarray(-axis_lengths, np.float32))
    outside = np.asarray(projected_delta - closest, dtype=np.float32)
    outside_squared = np.asarray(outside * outside, dtype=np.float32)
    distance_squared = np.float32(
        np.float32(outside_squared[1] + outside_squared[0])
        + outside_squared[2])
    distance = np.float32(
        np.sqrt(max(distance_squared, np.float32(1e-6))))
    distance_depth = np.float32(distance * distance_scale)

    minus_x = np.asarray(center - axes[0], dtype=np.float32)
    plus_x = np.asarray(center + axes[0], dtype=np.float32)
    bases = (
        np.asarray(minus_x + axes[1], dtype=np.float32),
        np.asarray(minus_x - axes[1], dtype=np.float32),
        np.asarray(plus_x - axes[1], dtype=np.float32),
        np.asarray(plus_x + axes[1], dtype=np.float32),
    )
    corners = tuple(
        np.asarray(base + signed_z * axes[2], dtype=np.float32)
        for signed_z in (-1, 1) for base in bases)

    projected_corners = []
    for corner in corners:
        value = np.asarray(
            np.asarray(corner[2] * projection[2], dtype=np.float32)
            + projection[3], dtype=np.float32)
        value = np.asarray(
            value + np.asarray(corner[1] * projection[1], dtype=np.float32),
            dtype=np.float32)
        value = np.asarray(
            value + np.asarray(corner[0] * projection[0], dtype=np.float32),
            dtype=np.float32)
        projected_corners.append(value)
    projected_corners = np.asarray(projected_corners, dtype=np.float32)

    effective_depths = np.asarray(
        np.maximum(projected_corners[:, 3], distance_depth) - bias,
        dtype=np.float32)
    if np.any(effective_depths < near_threshold):
        return LightManagerHierarchicalDepthResult(
            True, 'near_or_camera_boundary', None, None, None, None)

    query_depth_value = np.float32(
        min(np.min(effective_depths), depth_cap) * depth_scale)
    query_depth = int(np.trunc(query_depth_value))
    denominators = np.maximum(projected_corners[:, 3], near_threshold)
    normalized_x = np.asarray(
        projected_corners[:, 0] / denominators, dtype=np.float32)
    normalized_y = np.asarray(
        projected_corners[:, 1] / denominators, dtype=np.float32)
    packed_bounds = np.asarray((
        np.min(normalized_x), np.min(normalized_y),
        np.max(normalized_x), np.max(normalized_y),
    ), dtype=np.float32)
    packed_bounds = np.asarray(
        packed_bounds * screen_scale, dtype=np.float32)
    packed_bounds = np.asarray(packed_bounds + screen_bias, dtype=np.float32)
    packed_bounds = np.maximum(packed_bounds, np.float32(0.0))
    packed_bounds = np.minimum(packed_bounds, screen_maximum)
    bounds = tuple(int(value) for value in np.trunc(packed_bounds))
    minimum_x, minimum_y, maximum_x, maximum_y = bounds

    base_signed = depth_levels[0]
    base_unsigned = base_signed.view('<u2')
    base_corners = (
        int(base_unsigned[minimum_y, minimum_x]),
        int(base_unsigned[minimum_y, maximum_x]),
        int(base_unsigned[maximum_y, maximum_x]),
        int(base_unsigned[maximum_y, minimum_x]),
    )
    combined = 0
    for value in base_corners:
        combined |= query_depth - value
    if combined <= 0:
        return LightManagerHierarchicalDepthResult(
            True, 'base_corners', bounds, query_depth, None, None)

    span_x = maximum_x - minimum_x
    span_y = maximum_y - minimum_y
    initial_level = max(
        (span_x | 1).bit_length() - 1,
        (span_y | 1).bit_length() - 1)
    initial_level = min(initial_level, len(depth_levels) - 1)
    scaled_minimum_x = minimum_x >> initial_level
    scaled_minimum_y = minimum_y >> initial_level
    scaled_maximum_x = maximum_x >> initial_level
    scaled_maximum_y = maximum_y >> initial_level
    remaining_levels = len(depth_levels) - initial_level
    residual_span = ((scaled_maximum_x - scaled_minimum_x)
                     | (scaled_maximum_y - scaled_minimum_y))
    extra_level = min(residual_span >> 1, remaining_levels - 1)
    selected_level = initial_level + extra_level
    shift = selected_level - initial_level
    scaled_minimum_x >>= shift
    scaled_minimum_y >>= shift
    scaled_maximum_x >>= shift
    scaled_maximum_y >>= shift

    selected_unsigned = depth_levels[selected_level].view('<u2')
    coarse_corners = (
        int(selected_unsigned[scaled_minimum_y, scaled_minimum_x]),
        int(selected_unsigned[scaled_minimum_y, scaled_maximum_x]),
        int(selected_unsigned[scaled_maximum_y, scaled_maximum_x]),
        int(selected_unsigned[scaled_maximum_y, scaled_minimum_x]),
    )
    combined = 0
    for value in coarse_corners:
        combined |= query_depth - value
    if combined > 0:
        return LightManagerHierarchicalDepthResult(
            False, 'coarse_corners', bounds, query_depth, initial_level, selected_level)

    query_depth_signed = int(np.asarray(query_depth & 0xffff, dtype='<u2').view('<i2'))
    visible = bool(np.any(
        base_signed[minimum_y:maximum_y + 1,
                    minimum_x:maximum_x + 1] >= query_depth_signed))
    return LightManagerHierarchicalDepthResult(
        visible, 'base_scan_visible' if visible else 'base_scan_occluded',
        bounds, query_depth, initial_level, selected_level)

def light_manager_primary_query_source_visible(
        source: LightManagerCandidateSource, packed_planes,
        ) -> bool:
    """Test one source OBB as refinement helper ``0x1412B72A0`` does.

    The helper transforms source ``+0x40`` by its row-major affine matrix,
    projects the three ``+0x50`` half axes onto all 16 component-major planes,
    and retains the source when every signed plane distance plus OBB support
    has a clear sign bit. This intentionally treats negative zero as outside,
    matching the final ``movmskps`` instruction.
    """

    planes = np.asarray(packed_planes, dtype=np.float32)
    if planes.shape != (4, 4, 4) or not np.isfinite(planes).all():
        raise ValueError(
            'Manager primary query planes must have shape (4, 4, 4) '
            'and be finite')
    query = build_light_manager_occlusion_query(source)
    center = np.asarray(query.world_center, dtype=np.float32)
    half_axes = np.asarray((
        query.half_axis_x,
        query.half_axis_y,
        query.half_axis_z,
    ), dtype=np.float32)

    def add(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            + np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    def multiply(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            * np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    support_groups = []
    for group in planes:
        distance = add(
            add(
                add(multiply(center[0], group[0]), group[3]),
                multiply(center[1], group[1]),
            ),
            multiply(center[2], group[2]),
        )
        radius = np.zeros(4, dtype=np.float32)
        for axis in half_axes:
            projection = add(
                add(
                    multiply(axis[0], group[0]),
                    multiply(axis[1], group[1]),
                ),
                multiply(axis[2], group[2]),
            )
            radius = add(radius, np.abs(projection).astype(np.float32))
        support_groups.append(add(distance, radius))

    minimum = np.minimum(support_groups[0], support_groups[1])
    minimum = np.minimum(minimum, support_groups[2])
    minimum = np.minimum(minimum, support_groups[3])
    return not bool(np.signbit(minimum).any())


def filter_light_manager_primary_query_sources(
        sources, packed_planes,
        ) -> tuple[LightManagerCandidateSource, ...]:
    """Compact sources in order like primary refinement ``0x1412B72A0``."""

    candidates = tuple(sources)
    if not all(isinstance(source, LightManagerCandidateSource)
               for source in candidates):
        raise ValueError(
            'Manager primary query sources must be candidate-source values')
    return tuple(
        source for source in candidates
        if light_manager_primary_query_source_visible(source, packed_planes)
    )

def light_manager_optional_query_source_visible(
        source: LightManagerCandidateSource, packed_planes,
        optional_component_planes,
        ) -> bool:
    """Apply optional four-plane refinement helper ``0x1412B78B0``.

    Retail first runs the 16-plane primary OBB test. It then negates the four
    component-major optional planes and evaluates the transformed source OBB.
    A source is rejected only when all four results have set sign bits, which
    removes OBBs strictly inside all four unnegated optional planes. Boundary
    contact and crossing any one plane remain visible.
    """

    optional = np.asarray(optional_component_planes, dtype=np.float32)
    if optional.shape != (4, 4) or not np.isfinite(optional).all():
        raise ValueError(
            'Manager optional query planes must have shape (4, 4) '
            'and be finite')
    if not light_manager_primary_query_source_visible(source, packed_planes):
        return False

    query = build_light_manager_occlusion_query(source)
    center = np.asarray(query.world_center, dtype=np.float32)
    half_axes = np.asarray((
        query.half_axis_x,
        query.half_axis_y,
        query.half_axis_z,
    ), dtype=np.float32)
    negative = np.asarray(
        np.float32(0) - optional, dtype=np.float32)

    def add(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            + np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    def multiply(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            * np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    projected_support = []
    for axis in half_axes:
        projection = add(
            add(
                multiply(axis[1], negative[1]),
                multiply(axis[0], negative[0]),
            ),
            multiply(axis[2], negative[2]),
        )
        projected_support.append(np.abs(projection).astype(np.float32))
    support = add(projected_support[1], projected_support[0])
    support = add(support, projected_support[2])

    distance = add(multiply(center[0], negative[0]), negative[3])
    distance = add(distance, multiply(center[1], negative[1]))
    distance = add(distance, multiply(center[2], negative[2]))
    result = add(support, distance)
    return not bool(np.signbit(result).all())


def filter_light_manager_optional_query_sources(
        sources, packed_planes, optional_component_planes,
        ) -> tuple[LightManagerCandidateSource, ...]:
    """Compact sources in order like optional helper ``0x1412B78B0``."""

    candidates = tuple(sources)
    if not all(isinstance(source, LightManagerCandidateSource)
               for source in candidates):
        raise ValueError(
            'Manager optional query sources must be candidate-source values')
    return tuple(
        source for source in candidates
        if light_manager_optional_query_source_visible(
            source, packed_planes, optional_component_planes)
    )


_LIGHT_MANAGER_SPATIAL_RADIUS_BIAS = np.float32(
    struct.unpack('<f', struct.pack('<I', 0x3feed9e0))[0])
_LIGHT_MANAGER_SPATIAL_COORDINATE_LIMIT = np.float32(16384.0)
_LIGHT_MANAGER_SPATIAL_PACKED_MAX = 32767
_LIGHT_MANAGER_SPATIAL_CVTT_FAILURE = -0x80000000


def _light_manager_spatial_cvtt(value: np.float32) -> int:
    if value >= np.float32(2147483648.0) or value < np.float32(-2147483648.0):
        return _LIGHT_MANAGER_SPATIAL_CVTT_FAILURE
    return int(np.trunc(value))


def _light_manager_spatial_floor(value: np.float32) -> int:
    result = _light_manager_spatial_cvtt(value)
    if result == _LIGHT_MANAGER_SPATIAL_CVTT_FAILURE:
        return result
    if np.float32(result) != value and np.signbit(value):
        result -= 1
    return result


def _light_manager_spatial_low_int16(value: int) -> int:
    return struct.unpack('<h', struct.pack('<H', value & 0xffff))[0]


def allocate_light_manager_spatial_tree_node(
        nodes, *, free_node_chain=(), maximum_active_node_index: int,
        ) -> LightManagerSpatialTreeNodeAllocation:
    """Pop and initialize one 0x20-byte node exactly as ``0x141668410``."""

    values = list(nodes)
    if not values or not all(
            isinstance(node, LightManagerSpatialTreeNode) for node in values):
        raise ValueError("Manager spatial tree must contain tree-node values")
    if not isinstance(maximum_active_node_index, int) or not (
            -1 <= maximum_active_node_index < len(values)):
        raise ValueError(
            "Manager spatial tree maximum active node index is out of range")
    free_chain = list(free_node_chain)
    if any(not isinstance(index, int) or not 0 <= index < len(values)
           for index in free_chain):
        raise ValueError("Manager spatial tree free-node index is out of range")
    if len(set(free_chain)) != len(free_chain):
        raise ValueError("Manager spatial tree free-node chain must be unique")
    if any(values[index].active_marker != 0 for index in free_chain):
        raise ValueError("Manager spatial tree free nodes must be inactive")
    if not free_chain:
        return LightManagerSpatialTreeNodeAllocation(
            nodes=tuple(values), allocated_node_index=None,
            free_head_index=None, free_node_chain=(),
            maximum_active_node_index=maximum_active_node_index)
    index = free_chain.pop(0)
    values[index] = LightManagerSpatialTreeNode(
        origin=(0, 0, 0), slots=(0xffff,) * 8, depth=0,
        parent_node_index=-1, parent_slot=0, active_marker=1)
    return LightManagerSpatialTreeNodeAllocation(
        nodes=tuple(values), allocated_node_index=index,
        free_head_index=free_chain[0] if free_chain else None,
        free_node_chain=tuple(free_chain),
        maximum_active_node_index=max(maximum_active_node_index, index))


def allocate_light_manager_spatial_cell(
        cells, *, free_cell_chain=(), maximum_active_cell_index: int,
        active_cell_count: int = 0,
        ) -> LightManagerSpatialCellAllocation:
    """Pop and initialize one 0x30-byte cell exactly as ``0x141668470``."""

    values = list(cells)
    if not values or not all(
            isinstance(cell, LightManagerSpatialCell) for cell in values):
        raise ValueError("Manager spatial cells must contain cell values")
    if not isinstance(maximum_active_cell_index, int) or not (
            -1 <= maximum_active_cell_index < len(values)):
        raise ValueError(
            "Manager spatial maximum active cell index is out of range")
    if not isinstance(active_cell_count, int) or active_cell_count < 0:
        raise ValueError(
            "Manager spatial active cell count must be nonnegative")
    free_chain = list(free_cell_chain)
    if any(not isinstance(index, int) or not 0 <= index < len(values)
           for index in free_chain):
        raise ValueError("Manager spatial free-cell index is out of range")
    if len(set(free_chain)) != len(free_chain):
        raise ValueError("Manager spatial free-cell chain must be unique")
    if not free_chain:
        return LightManagerSpatialCellAllocation(
            cells=tuple(values), allocated_cell_index=None,
            free_head_index=None, free_cell_chain=(),
            maximum_active_cell_index=maximum_active_cell_index,
            active_cell_count=active_cell_count)
    index = free_chain.pop(0)
    values[index] = LightManagerSpatialCell(
        center=(0.0, 0.0, 1048576.0), radius_weight=0,
        half_extents=(0.0, 0.0, 0.0), reserved_1c=0,
        latest_page_index=-1, entry_count=0, parent_node_index=-1,
        parent_slot=0, state_byte=0x40, selection_mask=0)
    return LightManagerSpatialCellAllocation(
        cells=tuple(values), allocated_cell_index=index,
        free_head_index=free_chain[0] if free_chain else None,
        free_cell_chain=tuple(free_chain),
        maximum_active_cell_index=max(maximum_active_cell_index, index),
        active_cell_count=active_cell_count + 1)

def release_light_manager_spatial_cell(
        cells, *, cell_index: int, free_cell_chain=(),
        maximum_active_cell_index: int, active_cell_count: int,
        ) -> LightManagerSpatialCellRelease:
    """Reset and prepend one cell exactly as 0x14166A0D0."""

    values = list(cells)
    if not values or not all(
            isinstance(cell, LightManagerSpatialCell) for cell in values):
        raise ValueError("Manager spatial cells must contain cell values")
    if not isinstance(cell_index, int) or not 0 <= cell_index < len(values):
        raise ValueError("Manager spatial release cell index is out of range")
    if not isinstance(maximum_active_cell_index, int) or not (
            -1 <= maximum_active_cell_index < len(values)):
        raise ValueError(
            "Manager spatial maximum active cell index is out of range")
    if not isinstance(active_cell_count, int) or active_cell_count <= 0:
        raise ValueError(
            "Manager spatial release requires a positive active cell count")
    free_chain = list(free_cell_chain)
    if any(not isinstance(index, int) or not 0 <= index < len(values)
           for index in free_chain):
        raise ValueError("Manager spatial free-cell index is out of range")
    if len(set(free_chain)) != len(free_chain) or cell_index in free_chain:
        raise ValueError(
            "Manager spatial release free-cell chain must be unique")
    if values[cell_index].state_byte & 0x40 == 0:
        raise ValueError("Manager spatial release cell must be active")

    values[cell_index] = LightManagerSpatialCell(
        center=(0.0, 0.0, 1048576.0), radius_weight=0,
        half_extents=(0.0, 0.0, 0.0), reserved_1c=0,
        latest_page_index=-1, entry_count=0, parent_node_index=-1,
        parent_slot=0, state_byte=0, selection_mask=0)
    free_chain.insert(0, cell_index)
    maximum = maximum_active_cell_index
    if cell_index == maximum:
        while maximum >= 0 and values[maximum].state_byte & 0x40 == 0:
            maximum -= 1
    return LightManagerSpatialCellRelease(
        cells=tuple(values), released_cell_index=cell_index,
        free_head_index=cell_index, free_cell_chain=tuple(free_chain),
        maximum_active_cell_index=maximum,
        active_cell_count=active_cell_count - 1)


def begin_light_manager_spatial_tree_subdivision(
        nodes, *, cell_parent_node_index: int, cell_parent_slot: int,
        cell_depth: int, free_node_index: int | None,
        next_free_node_index: int | None, maximum_active_node_index: int,
        ) -> LightManagerSpatialTreeSubdivision | None:
    """Reproduce allocation/link prelude ``0x14166B5E0..0x14166B749``.

    Retail declines to split cells at depth four or below and also returns
    failure when the tree-node free list is empty. Successful subdivision
    initializes a child node and replaces the parent cell slot with its clear
    high-bit node index. Page redistribution follows after this prelude.
    """

    values = tuple(nodes)
    if not values or not all(
            isinstance(node, LightManagerSpatialTreeNode) for node in values):
        raise ValueError(
            "Manager spatial tree must contain tree-node values")
    for name, value in (
            ("cell parent node index", cell_parent_node_index),
            ("cell parent slot", cell_parent_slot),
            ("cell depth", cell_depth),
            ("maximum active node index", maximum_active_node_index)):
        if not isinstance(value, int):
            raise ValueError(f"Manager spatial tree {name} must be an integer")
    if not 0 <= cell_parent_node_index < len(values):
        raise ValueError("Manager spatial tree parent node index is out of range")
    if not 0 <= cell_parent_slot < 8:
        raise ValueError("Manager spatial tree parent slot must be 0..7")
    if not 0 <= cell_depth <= 0x0f:
        raise ValueError("Manager spatial tree cell depth must be 0..15")
    if maximum_active_node_index < -1:
        raise ValueError(
            "Manager spatial tree maximum active node index must be at least -1")
    for name, value in (
            ("free node index", free_node_index),
            ("next free node index", next_free_node_index)):
        if value is not None and (
                not isinstance(value, int) or not 0 <= value < len(values)):
            raise ValueError(f"Manager spatial tree {name} is out of range")
    if cell_depth <= 4 or free_node_index is None:
        return None
    if free_node_index > 0x7fff:
        raise ValueError("Manager spatial tree child index exceeds 15 bits")
    if free_node_index == cell_parent_node_index:
        raise ValueError("Manager spatial tree cannot allocate its parent node")

    parent = values[cell_parent_node_index]
    if not 1 <= parent.depth <= 0xffff:
        raise ValueError("Manager spatial tree parent depth must be nonzero")
    axis_offset = 1 << cell_depth
    child_origin = tuple(
        _light_manager_spatial_low_int16(
            parent.origin[axis]
            + (((cell_parent_slot >> axis) & 1) * axis_offset))
        for axis in range(3)
    )
    child = LightManagerSpatialTreeNode(
        origin=child_origin,
        slots=(0xffff,) * 8,
        depth=(parent.depth - 1) & 0xffff,
        parent_node_index=cell_parent_node_index,
        parent_slot=cell_parent_slot,
        active_marker=1,
    )
    updated = list(values)
    updated[free_node_index] = child
    parent_slots = list(parent.slots)
    parent_slots[cell_parent_slot] = free_node_index
    updated[cell_parent_node_index] = replace(
        parent, slots=tuple(parent_slots))
    return LightManagerSpatialTreeSubdivision(
        nodes=tuple(updated),
        child_node_index=free_node_index,
        free_head_index=next_free_node_index,
        maximum_active_node_index=max(
            maximum_active_node_index, free_node_index),
    )

def redistribute_light_manager_spatial_tree_cell(
        nodes, entries, *, cell_parent_node_index: int, cell_parent_slot: int,
        cell_depth: int, old_cell_index: int,
        free_node_index: int | None, next_free_node_index: int | None,
        maximum_active_node_index: int, free_cell_indices=(),
        free_page_indices=(), cell_metadata: int = 0,
        ) -> LightManagerSpatialTreeRedistribution | None:
    """Reproduce successful redistribution body ``0x14166B5E0..0x14166BF57``.

    The released source cell becomes the first free cell. Entries are binned by
    one fixed-point xyz bit into up to eight child cells. Each first occupancy
    consumes one cell and one page; later entries append to the same child.
    If either pool is exhausted, retail appends to the first existing child.
    """

    values = tuple(entries)
    if not values or not all(
            isinstance(entry, LightManagerSpatialEntry) for entry in values):
        raise ValueError(
            "Manager spatial subdivision requires spatial-entry values")
    for name, value, maximum in (
            ("old cell index", old_cell_index, 0x7fff),
            ("cell metadata", cell_metadata, 0xffffffff)):
        if not isinstance(value, int) or not 0 <= value <= maximum:
            raise ValueError(
                f"Manager spatial subdivision {name} is out of range")
    free_cells = tuple(free_cell_indices)
    free_pages = tuple(free_page_indices)
    if any(not isinstance(value, int) or not 0 <= value <= 0x7fff
           for value in free_cells):
        raise ValueError(
            "Manager spatial subdivision free cell indices must be 15-bit")
    if any(not isinstance(value, int) or value < 0 for value in free_pages):
        raise ValueError(
            "Manager spatial subdivision free page indices must be nonnegative")
    if len(set((old_cell_index, *free_cells))) != len(free_cells) + 1:
        raise ValueError("Manager spatial subdivision free cells must be unique")
    if len(set(free_pages)) != len(free_pages):
        raise ValueError("Manager spatial subdivision free pages must be unique")

    subdivision = begin_light_manager_spatial_tree_subdivision(
        nodes,
        cell_parent_node_index=cell_parent_node_index,
        cell_parent_slot=cell_parent_slot,
        cell_depth=cell_depth,
        free_node_index=free_node_index,
        next_free_node_index=next_free_node_index,
        maximum_active_node_index=maximum_active_node_index,
    )
    if subdivision is None:
        return None
    child_depth = cell_depth - 1
    child_node_index = subdivision.child_node_index
    child_node = subdivision.nodes[child_node_index]
    intended = [[] for _ in range(8)]
    for entry in values:
        if not isinstance(entry.packed_bound, LightManagerSpatialPackedBound):
            raise ValueError(
                "Manager spatial subdivision entries require packed bounds")
        if len(entry.packed_bound.center) != 3:
            raise ValueError(
                "Manager spatial subdivision packed centers require three axes")
        slot_index = 0
        for axis, coordinate in enumerate(entry.packed_bound.center):
            if (not isinstance(coordinate, int)
                    or not -0x8000 <= coordinate <= 0x7fff):
                raise ValueError(
                    "Manager spatial subdivision packed centers must be int16")
            delta = _light_manager_spatial_low_int16(
                coordinate - child_node.origin[axis])
            slot_index |= ((delta >> child_depth) & 1) << axis
        intended[slot_index].append(entry)

    available_cells = [old_cell_index, *free_cells]
    available_pages = list(free_pages)
    allocated = {}
    assigned = {}
    append_sequence = []
    for entry in values:
        slot_index = 0
        for axis, coordinate in enumerate(entry.packed_bound.center):
            delta = _light_manager_spatial_low_int16(
                coordinate - child_node.origin[axis])
            slot_index |= ((delta >> child_depth) & 1) << axis
        target_slot = slot_index
        if slot_index not in allocated:
            if available_cells and available_pages:
                allocated[slot_index] = (
                    available_cells.pop(0), available_pages.pop(0))
                assigned[slot_index] = []
            else:
                existing = sorted(allocated)
                if not existing:
                    continue
                target_slot = existing[0]
        cell_index = allocated[target_slot][0]
        assigned[target_slot].append(entry)
        append_sequence.append((entry.source_index, cell_index))

    node_slots = list(child_node.slots)
    children = []
    for slot_index in sorted(allocated):
        cell_index, page_index = allocated[slot_index]
        node_slots[slot_index] = 0x8000 | cell_index
        bound_entries = tuple(intended[slot_index])
        children.append(LightManagerSpatialTreeChildCell(
            slot_index=slot_index,
            cell_index=cell_index,
            page_index=page_index,
            parent_node_index=child_node_index,
            depth=child_depth,
            metadata=cell_metadata,
            bound=rebuild_light_manager_spatial_cell_bound(bound_entries),
            entries=tuple(assigned[slot_index]),
            bound_entries=bound_entries,
        ))
    updated_nodes = list(subdivision.nodes)
    updated_nodes[child_node_index] = replace(
        child_node, slots=tuple(node_slots))
    final_subdivision = replace(subdivision, nodes=tuple(updated_nodes))
    return LightManagerSpatialTreeRedistribution(
        subdivision=final_subdivision,
        child_cells=tuple(children),
        append_sequence=tuple(append_sequence),
        active_cell_delta=len(children) - 1,
        remaining_free_cell_indices=tuple(available_cells),
        remaining_free_page_indices=tuple(available_pages),
    )

def collapse_light_manager_spatial_tree_cell(
        nodes, *, cell_parent_node_index: int, cell_parent_slot: int,
        root_index: int | None, free_node_chain=(),
        maximum_active_node_index: int,
        ) -> LightManagerSpatialTreeCollapse:
    """Reproduce empty-node collapse tail ``0x141669C7D..0x141669D77``.

    The caller has already removed the final entry and released its empty cell.
    Retail clears the cell's high-bit leaf slot, returns every now-empty ancestor
    node to the head of the free list, repairs the maximum active index only when
    necessary, and clears the root pointer when the final ancestor is released.
    """

    values = list(nodes)
    if not values or not all(
            isinstance(node, LightManagerSpatialTreeNode) for node in values):
        raise ValueError(
            "Manager spatial tree must contain tree-node values")
    for name, value in (
            ("cell parent node index", cell_parent_node_index),
            ("cell parent slot", cell_parent_slot),
            ("maximum active node index", maximum_active_node_index)):
        if not isinstance(value, int):
            raise ValueError(f"Manager spatial tree {name} must be an integer")
    if root_index is None or not isinstance(root_index, int) or not (
            0 <= root_index < len(values)):
        raise ValueError("Manager spatial tree root index is out of range")
    if not 0 <= cell_parent_node_index < len(values):
        raise ValueError("Manager spatial tree parent node index is out of range")
    if not 0 <= cell_parent_slot < 8:
        raise ValueError("Manager spatial tree parent slot must be 0..7")
    if not 0 <= maximum_active_node_index < len(values):
        raise ValueError(
            "Manager spatial tree maximum active node index is out of range")

    free_chain = list(free_node_chain)
    if any(not isinstance(index, int) or not 0 <= index < len(values)
           for index in free_chain):
        raise ValueError("Manager spatial tree free-node index is out of range")
    if len(set(free_chain)) != len(free_chain):
        raise ValueError("Manager spatial tree free-node chain must be unique")
    if any(values[index].active_marker != 0 for index in free_chain):
        raise ValueError("Manager spatial tree free-node chain must be inactive")
    if values[root_index].active_marker == 0:
        raise ValueError("Manager spatial tree root node must be active")

    current_index = cell_parent_node_index
    current = values[current_index]
    if current.active_marker == 0:
        raise ValueError("Manager spatial tree cell parent must be active")
    target = current.slots[cell_parent_slot]
    if target == 0xffff or target & 0x8000 == 0:
        raise ValueError("Manager spatial tree cell slot must contain a leaf")
    current_slots = list(current.slots)
    current_slots[cell_parent_slot] = 0xffff
    values[current_index] = replace(current, slots=tuple(current_slots))

    freed = []
    maximum = maximum_active_node_index
    result_root = root_index
    while all(slot == 0xffff for slot in values[current_index].slots):
        current = values[current_index]
        parent_index = current.parent_node_index
        parent_slot = current.parent_slot
        values[current_index] = LightManagerSpatialTreeNode(
            origin=(0, 0, 0), slots=(0,) * 8, depth=0,
            parent_node_index=0, parent_slot=0, active_marker=0)
        free_chain.insert(0, current_index)
        freed.append(current_index)

        if current_index == maximum:
            while maximum >= 0 and values[maximum].active_marker == 0:
                maximum -= 1
        if parent_index < 0:
            if current_index != result_root:
                raise ValueError(
                    "Manager spatial tree negative parent must belong to root")
            result_root = None
            break
        if not 0 <= parent_index < len(values):
            raise ValueError("Manager spatial tree ancestor index is out of range")
        parent = values[parent_index]
        if parent.active_marker == 0 or not 0 <= parent_slot < 8:
            raise ValueError("Manager spatial tree ancestor link is invalid")
        if parent.slots[parent_slot] != current_index:
            raise ValueError("Manager spatial tree ancestor slot changed")
        parent_slots = list(parent.slots)
        parent_slots[parent_slot] = 0xffff
        values[parent_index] = replace(parent, slots=tuple(parent_slots))
        if any(slot != 0xffff for slot in parent_slots):
            break
        current_index = parent_index

    return LightManagerSpatialTreeCollapse(
        nodes=tuple(values),
        root_index=result_root,
        free_head_index=free_chain[0] if free_chain else None,
        free_node_chain=tuple(free_chain),
        freed_node_indices=tuple(freed),
        maximum_active_node_index=maximum,
    )

def append_light_manager_spatial_page(
        pages, entry: LightManagerSpatialEntry, *, cell_index: int,
        cell_latest_page_index: int, cell_entry_count: int,
        cell_state_byte: int, free_page_chain=(), source_handle_before: int = -1,
        ) -> LightManagerSpatialPageAppend:
    """Reproduce the page append helper at ``0x141668290``.

    Entries append to the current newest page until its 15-entry capacity is
    reached. A full page consumes and links the head free page, marks the cell
    dirty and appends at slot zero. Exhaustion returns false without mutation.
    """

    values = list(pages)
    if not values or not all(
            isinstance(page, LightManagerSpatialPage) for page in values):
        raise ValueError("Manager spatial pages must contain page values")
    if not isinstance(entry, LightManagerSpatialEntry):
        raise ValueError("Manager spatial append requires a spatial entry")
    for name, value in (
            ("cell index", cell_index),
            ("latest page index", cell_latest_page_index),
            ("cell entry count", cell_entry_count),
            ("cell state byte", cell_state_byte),
            ("source handle", source_handle_before)):
        if not isinstance(value, int):
            raise ValueError(f"Manager spatial append {name} must be an integer")
    if cell_index < 0:
        raise ValueError("Manager spatial append cell index must be nonnegative")
    if not 0 <= cell_latest_page_index < len(values):
        raise ValueError("Manager spatial append latest page index is out of range")
    if cell_entry_count < 0:
        raise ValueError("Manager spatial append entry count must be nonnegative")
    if not 0 <= cell_state_byte <= 0xff:
        raise ValueError("Manager spatial append state byte must be 0..255")

    free_chain = list(free_page_chain)
    if any(not isinstance(index, int) or not 0 <= index < len(values)
           for index in free_chain):
        raise ValueError("Manager spatial append free-page index is out of range")
    if len(set(free_chain)) != len(free_chain):
        raise ValueError("Manager spatial append free-page chain must be unique")
    if cell_latest_page_index in free_chain:
        raise ValueError("Manager spatial append current page cannot be free")
    if any(values[index].active_marker != 0 or values[index].entries
           for index in free_chain):
        raise ValueError("Manager spatial append free pages must be inactive")

    current = values[cell_latest_page_index]
    if current.active_marker == 0 or current.owning_cell != cell_index:
        raise ValueError("Manager spatial append current page ownership changed")
    if current.newer_page >= 0:
        raise ValueError("Manager spatial append current page must be newest")
    slot = len(current.entries)
    if slot > 15:
        raise ValueError("Manager spatial page exceeds its 15-entry capacity")
    if cell_entry_count < slot:
        raise ValueError("Manager spatial cell count is below newest-page count")

    if slot < 15:
        values[cell_latest_page_index] = replace(
            current, entries=current.entries + (entry,))
        handle = (cell_latest_page_index << 4) | slot
        return LightManagerSpatialPageAppend(
            pages=tuple(values), success=True, source_handle=handle,
            cell_latest_page_index=cell_latest_page_index,
            cell_entry_count=cell_entry_count + 1,
            cell_state_byte=cell_state_byte,
            free_head_page_index=free_chain[0] if free_chain else None,
            free_page_chain=tuple(free_chain),
            appended_page_index=cell_latest_page_index,
            appended_slot=slot,
        )

    if not free_chain:
        return LightManagerSpatialPageAppend(
            pages=tuple(values), success=False,
            source_handle=source_handle_before,
            cell_latest_page_index=cell_latest_page_index,
            cell_entry_count=cell_entry_count,
            cell_state_byte=cell_state_byte,
            free_head_page_index=None, free_page_chain=(),
            appended_page_index=None, appended_slot=None,
        )

    new_page_index = free_chain.pop(0)
    values[cell_latest_page_index] = replace(
        current, newer_page=new_page_index)
    values[new_page_index] = LightManagerSpatialPage(
        older_page=cell_latest_page_index, newer_page=-1,
        owning_cell=cell_index, active_marker=1, reserved=0,
        entries=(entry,))
    handle = new_page_index << 4
    return LightManagerSpatialPageAppend(
        pages=tuple(values), success=True, source_handle=handle,
        cell_latest_page_index=new_page_index,
        cell_entry_count=cell_entry_count + 1,
        cell_state_byte=cell_state_byte | 0x80,
        free_head_page_index=free_chain[0] if free_chain else None,
        free_page_chain=tuple(free_chain),
        appended_page_index=new_page_index,
        appended_slot=0,
    )

def lookup_light_manager_spatial_tree(
        nodes, packed_bound: LightManagerSpatialPackedBound, *, root_index: int = 0,
        ) -> LightManagerSpatialTreeLookup:
    """Reproduce the fixed-point octree walk at ``0x141669EA0``.

    The root subtracts its signed-int16 origin once. Each level consumes the
    next high coordinate bit by doubling the three 32-bit deltas. Slot values
    use ``0xffff`` for empty, high-bit values for cells, and low 15-bit values
    for child-node indices.
    """

    values = tuple(nodes)
    if not values or not all(
            isinstance(node, LightManagerSpatialTreeNode) for node in values):
        raise ValueError(
            "Manager spatial tree must contain tree-node values")
    if not isinstance(root_index, int) or not 0 <= root_index < len(values):
        raise ValueError("Manager spatial tree root index is out of range")
    if not isinstance(packed_bound, LightManagerSpatialPackedBound):
        raise ValueError("Manager spatial tree lookup requires a packed bound")

    for node in values:
        if len(node.origin) != 3 or any(
                not isinstance(value, int) or not -0x8000 <= value <= 0x7fff
                for value in node.origin):
            raise ValueError("Manager spatial tree origins must be int16 triples")
        if len(node.slots) != 8 or any(
                not isinstance(value, int) or not 0 <= value <= 0xffff
                for value in node.slots):
            raise ValueError(
                "Manager spatial tree nodes must contain eight uint16 slots")
        if not isinstance(node.depth, int) or not 0 <= node.depth <= 0xffff:
            raise ValueError("Manager spatial tree depth fields must be uint16")
    if len(packed_bound.center) != 3 or any(
            not isinstance(value, int) or not -0x8000 <= value <= 0x7fff
            for value in packed_bound.center):
        raise ValueError("Manager spatial packed centers must be int16 triples")

    root = values[root_index]
    deltas = [
        (coordinate - origin) & 0xffffffff
        for coordinate, origin in zip(packed_bound.center, root.origin)
    ]
    node_index = root_index
    levels_descended = 0
    while True:
        slot_index = (
            ((deltas[0] >> 15) & 1)
            | ((deltas[1] >> 14) & 2)
            | ((deltas[2] >> 13) & 4)
        )
        entry = values[node_index].slots[slot_index]
        if entry & 0x8000:
            return LightManagerSpatialTreeLookup(
                node_index=node_index,
                slot_index=slot_index,
                entry=entry,
                levels_descended=levels_descended,
            )
        child_index = entry & 0x7fff
        if child_index >= len(values):
            raise ValueError(
                "Manager spatial tree child index is out of range")
        levels_descended += 1
        if levels_descended > 32:
            raise ValueError("Manager spatial tree contains a nonterminating path")
        node_index = child_index
        deltas = [(value << 1) & 0xffffffff for value in deltas]

def pack_light_manager_spatial_bound(center_radius) -> LightManagerSpatialPackedBound:
    """Reproduce float4 packing helper 0x14166B4C0."""

    values = np.asarray(center_radius, dtype=np.float32)
    if values.shape != (4,) or not np.isfinite(values).all():
        raise ValueError(
            'Manager spatial bound must be one finite center/radius float4')
    center = []
    for value in values[:3]:
        scaled = np.float32(np.float32(value + value) + np.float32(0.5))
        center.append(_light_manager_spatial_low_int16(
            _light_manager_spatial_floor(scaled)))

    scaled_radius = np.float32(
        np.float32(values[3] + values[3])
        + _LIGHT_MANAGER_SPATIAL_RADIUS_BIAS)
    radius_floor = _light_manager_spatial_floor(scaled_radius)
    if radius_floor == _LIGHT_MANAGER_SPATIAL_CVTT_FAILURE:
        radius_value = min(scaled_radius, np.float32(
            _LIGHT_MANAGER_SPATIAL_PACKED_MAX))
        radius_floor = _light_manager_spatial_cvtt(
            np.float32(radius_value))
    else:
        radius_floor = min(
            radius_floor, _LIGHT_MANAGER_SPATIAL_PACKED_MAX)
    return LightManagerSpatialPackedBound(
        tuple(center), _light_manager_spatial_low_int16(radius_floor))


def light_manager_spatial_bound_admissible(center_radius) -> bool:
    """Reproduce the coordinate/radius gate at 0x14166C360."""

    values = np.asarray(center_radius, dtype=np.float32)
    if values.shape != (4,) or not np.isfinite(values).all():
        raise ValueError(
            'Manager spatial bound must be one finite center/radius float4')
    maximum = np.maximum(
        np.abs(values[1]).astype(np.float32),
        np.abs(values[2]).astype(np.float32))
    maximum = np.maximum(
        maximum, np.abs(values[0]).astype(np.float32))
    return bool(
        maximum <= _LIGHT_MANAGER_SPATIAL_COORDINATE_LIMIT
        and values[3] < _LIGHT_MANAGER_SPATIAL_COORDINATE_LIMIT)


def insert_light_manager_spatial_owner(
        nodes, cells, pages, *, source_byte_offset: int,
        selection_mask: int, center_radius, root_index: int | None = None,
        free_node_chain=(), maximum_active_node_index: int,
        free_cell_chain=(), maximum_active_cell_index: int,
        active_cell_count: int = 0, free_page_chain=(),
        live_source_count: int = 0, source_handle_before: int = -1,
        ) -> LightManagerSpatialOwnerInsert:
    """Compose retail owner insertion 0x141667E00 from pinned primitives.

    If the cell free list is empty, capacity_growth_requested reports the
    retail capacity-growth boundary and this pure state port returns failure.
    """

    node_values = tuple(nodes)
    cell_values = tuple(cells)
    page_values = tuple(pages)
    if not node_values or not all(
            isinstance(node, LightManagerSpatialTreeNode)
            for node in node_values):
        raise ValueError("Manager spatial tree must contain tree-node values")
    if not cell_values or not all(
            isinstance(cell, LightManagerSpatialCell)
            for cell in cell_values):
        raise ValueError("Manager spatial cells must contain cell values")
    if not page_values or not all(
            isinstance(page, LightManagerSpatialPage)
            for page in page_values):
        raise ValueError("Manager spatial pages must contain page values")
    for name, value, limit in (
            ("maximum active node index", maximum_active_node_index,
             len(node_values)),
            ("maximum active cell index", maximum_active_cell_index,
             len(cell_values))):
        if not isinstance(value, int) or not -1 <= value < limit:
            raise ValueError(f"Manager spatial {name} is out of range")
    for name, value in (
            ("source byte offset", source_byte_offset),
            ("selection mask", selection_mask),
            ("active cell count", active_cell_count),
            ("live source count", live_source_count),
            ("source handle", source_handle_before)):
        if not isinstance(value, int):
            raise ValueError(f"Manager spatial insert {name} must be an integer")
    if active_cell_count < 0 or live_source_count < 0:
        raise ValueError(
            "Manager spatial insert owner counts must be nonnegative")

    free_nodes = tuple(free_node_chain)
    free_cells = tuple(free_cell_chain)
    free_pages = tuple(free_page_chain)
    for name, chain, limit in (
            ("node", free_nodes, len(node_values)),
            ("cell", free_cells, len(cell_values)),
            ("page", free_pages, len(page_values))):
        if any(not isinstance(index, int) or not 0 <= index < limit
               for index in chain):
            raise ValueError(
                f"Manager spatial insert free-{name} index is out of range")
        if len(set(chain)) != len(chain):
            raise ValueError(
                f"Manager spatial insert free-{name} chain must be unique")
    if any(node_values[index].active_marker != 0 for index in free_nodes):
        raise ValueError("Manager spatial insert free nodes must be inactive")
    if any(
            page_values[index].active_marker != 0 or page_values[index].entries
            for index in free_pages):
        raise ValueError("Manager spatial insert free pages must be inactive")
    if root_index is not None:
        if not isinstance(root_index, int) or not (
                0 <= root_index < len(node_values)):
            raise ValueError("Manager spatial insert root index is out of range")
        if (root_index in free_nodes or
                node_values[root_index].active_marker == 0):
            raise ValueError("Manager spatial insert root must be active")

    source_index = None
    packed_entry = None
    cell_index = None
    appended_page_index = None
    appended_slot = None
    capacity_growth_requested = False
    helper_calls = []

    def finish(success, source_handle):
        return LightManagerSpatialOwnerInsert(
            nodes=node_values, cells=cell_values, pages=page_values,
            success=success, source_index=source_index,
            source_handle=source_handle, packed_entry=packed_entry,
            root_index=root_index, free_node_chain=free_nodes,
            maximum_active_node_index=maximum_active_node_index,
            free_cell_chain=free_cells,
            maximum_active_cell_index=maximum_active_cell_index,
            active_cell_count=active_cell_count,
            free_page_chain=free_pages,
            live_source_count=live_source_count,
            cell_index=cell_index,
            appended_page_index=appended_page_index,
            appended_slot=appended_slot,
            capacity_growth_requested=capacity_growth_requested,
            helper_calls=tuple(helper_calls))

    pointer_delta = source_byte_offset & 0xffffffffffffffff
    if pointer_delta & 3 or pointer_delta >> 2 > 0xffffffff:
        return finish(False, source_handle_before)
    source_index = pointer_delta >> 2
    helper_calls.append('bound_packer')
    packed_bound = pack_light_manager_spatial_bound(center_radius)
    packed_entry = LightManagerSpatialEntry(
        selection_mask=selection_mask & 0xffff, reserved=0,
        source_index=source_index, packed_bound=packed_bound)
    sphere = np.asarray(center_radius, dtype=np.float32)
    if not light_manager_spatial_bound_admissible(sphere):
        return finish(False, source_handle_before)

    if root_index is None:
        helper_calls.append('node_allocator')
        allocated_node = allocate_light_manager_spatial_tree_node(
            node_values, free_node_chain=free_nodes,
            maximum_active_node_index=maximum_active_node_index)
        node_values = allocated_node.nodes
        free_nodes = allocated_node.free_node_chain
        maximum_active_node_index = (
            allocated_node.maximum_active_node_index)
        root_index = allocated_node.allocated_node_index
        if root_index is None:
            return finish(False, source_handle_before)
        node_values = list(node_values)
        node_values[root_index] = replace(
            node_values[root_index],
            origin=(-0x8000, -0x8000, -0x8000), depth=0x10)
        node_values = tuple(node_values)

    helper_calls.append('tree_lookup')
    lookup = lookup_light_manager_spatial_tree(
        node_values, packed_bound, root_index=root_index)
    if lookup.entry == 0xffff:
        helper_calls.append('cell_allocator')
        allocated_cell = allocate_light_manager_spatial_cell(
            cell_values, free_cell_chain=free_cells,
            maximum_active_cell_index=maximum_active_cell_index,
            active_cell_count=active_cell_count)
        cell_values = allocated_cell.cells
        free_cells = allocated_cell.free_cell_chain
        maximum_active_cell_index = (
            allocated_cell.maximum_active_cell_index)
        active_cell_count = allocated_cell.active_cell_count
        cell_index = allocated_cell.allocated_cell_index
        if cell_index is None:
            capacity_growth_requested = True
            return finish(False, source_handle_before)

        if not free_pages:
            helper_calls.append('cell_release')
            released = release_light_manager_spatial_cell(
                cell_values, cell_index=cell_index,
                free_cell_chain=free_cells,
                maximum_active_cell_index=maximum_active_cell_index,
                active_cell_count=active_cell_count)
            cell_values = released.cells
            free_cells = released.free_cell_chain
            maximum_active_cell_index = (
                released.maximum_active_cell_index)
            active_cell_count = released.active_cell_count
            cell_index = None
            return finish(False, source_handle_before)

        page_index = free_pages[0]
        free_pages = free_pages[1:]
        pages_mutable = list(page_values)
        pages_mutable[page_index] = LightManagerSpatialPage(
            older_page=-1, newer_page=-1, owning_cell=cell_index,
            active_marker=1, reserved=0, entries=())
        page_values = tuple(pages_mutable)
        node = node_values[lookup.node_index]
        state = (
            cell_values[cell_index].state_byte & 0xf0
            | ((node.depth - 1) & 0xff))
        cell_values = list(cell_values)
        cell_values[cell_index] = replace(
            cell_values[cell_index],
            center=tuple(float(value) for value in sphere[:3]),
            half_extents=(float(sphere[3]),) * 3,
            latest_page_index=page_index,
            parent_node_index=lookup.node_index,
            parent_slot=lookup.slot_index,
            state_byte=state)
        cell_values = tuple(cell_values)
        slots = list(node.slots)
        slots[lookup.slot_index] = cell_index | 0x8000
        node_values = list(node_values)
        node_values[lookup.node_index] = replace(node, slots=tuple(slots))
        node_values = tuple(node_values)
    else:
        cell_index = lookup.entry & 0x7fff
        if not 0 <= cell_index < len(cell_values):
            raise ValueError("Manager spatial insert cell index is out of range")
        cell = cell_values[cell_index]
        if cell.state_byte & 0x40 == 0:
            raise ValueError("Manager spatial insert leaf cell must be active")
        old_center = np.asarray(cell.center, dtype=np.float32)
        old_half = np.asarray(cell.half_extents, dtype=np.float32)
        radius = sphere[3]
        lower = np.minimum(
            np.asarray(sphere[:3] - radius, dtype=np.float32),
            np.asarray(old_center - old_half, dtype=np.float32))
        upper = np.maximum(
            np.asarray(sphere[:3] + radius, dtype=np.float32),
            np.asarray(old_center + old_half, dtype=np.float32))
        expanded_center = np.asarray(
            np.asarray(
                np.asarray(upper - lower, dtype=np.float32)
                * np.float32(0.5),
                dtype=np.float32)
            + lower,
            dtype=np.float32)
        expanded_half = np.asarray(
            upper - expanded_center, dtype=np.float32)
        cell_values = list(cell_values)
        cell_values[cell_index] = replace(
            cell,
            center=tuple(float(value) for value in expanded_center),
            half_extents=tuple(float(value) for value in expanded_half))
        cell_values = tuple(cell_values)

    cell = cell_values[cell_index]
    helper_calls.append('page_append')
    appended = append_light_manager_spatial_page(
        page_values, packed_entry, cell_index=cell_index,
        cell_latest_page_index=cell.latest_page_index,
        cell_entry_count=cell.entry_count,
        cell_state_byte=cell.state_byte,
        free_page_chain=free_pages,
        source_handle_before=source_handle_before)
    page_values = appended.pages
    free_pages = appended.free_page_chain
    appended_page_index = appended.appended_page_index
    appended_slot = appended.appended_slot
    cell_values = list(cell_values)
    cell_values[cell_index] = replace(
        cell,
        latest_page_index=appended.cell_latest_page_index,
        entry_count=appended.cell_entry_count,
        state_byte=appended.cell_state_byte)
    cell_values = tuple(cell_values)
    if not appended.success:
        return finish(False, appended.source_handle)
    live_source_count += 1
    return finish(True, appended.source_handle)


def decode_light_manager_spatial_entry(raw) -> LightManagerSpatialEntry:
    """Decode one retail 16-byte spatial page entry."""

    data = bytes(raw)
    if len(data) != 0x10:
        raise ValueError('Manager spatial entry must contain exactly 16 bytes')
    selection_mask, reserved, source_index, x, y, z, radius = (
        struct.unpack('<HHI4h', data))
    return LightManagerSpatialEntry(
        selection_mask=selection_mask,
        source_index=source_index,
        packed_bound=LightManagerSpatialPackedBound((x, y, z), radius),
        reserved=reserved,
    )


def decode_light_manager_spatial_page(raw) -> LightManagerSpatialPage:
    """Decode one retail 0x100-byte page and its active entries."""

    data = bytes(raw)
    if len(data) != 0x100:
        raise ValueError('Manager spatial page must contain exactly 256 bytes')
    (
        older_page,
        newer_page,
        owning_cell,
        entry_count,
        active_marker,
        reserved,
    ) = struct.unpack_from('<iihhhh', data)
    if not 0 <= entry_count <= 15:
        raise ValueError('Manager spatial page entry count must be 0..15')
    entries = tuple(
        decode_light_manager_spatial_entry(
            data[0x10 + index * 0x10:0x20 + index * 0x10])
        for index in range(entry_count)
    )
    return LightManagerSpatialPage(
        older_page=older_page,
        newer_page=newer_page,
        owning_cell=owning_cell,
        active_marker=active_marker,
        reserved=reserved,
        entries=entries,
    )


def _light_manager_spatial_saturate_int16(value: int) -> int:
    return max(-0x8000, min(0x7fff, value))


def rebuild_light_manager_spatial_cell_bound(
        entries, *, state_byte: int = 0x80,
        ) -> LightManagerSpatialRebuiltCell:
    """Reproduce dirty-cell rebuild routine 0x14166C240.

    Retail takes the signed-saturating union of packed entry spheres, converts
    the doubled signed-int16 coordinates back to a center and half extents, and
    clears cell state bit 0x80. Page traversal is storage ownership; callers
    supply its entries here in page-chain order.
    """

    if not isinstance(state_byte, int) or not 0 <= state_byte <= 0xff:
        raise ValueError('Manager spatial cell state byte must be 0..255')
    minimum = [0x7fff, 0x7fff, 0x7fff]
    maximum = [-0x7fff, -0x7fff, -0x7fff]
    radius_weight = 0
    for entry in entries:
        if not isinstance(entry, LightManagerSpatialEntry):
            raise ValueError(
                'Manager spatial cell entries must be spatial-entry values')
        if not 0 <= entry.selection_mask <= 0xffff:
            raise ValueError('Manager spatial entry mask must be uint16')
        if not 0 <= entry.reserved <= 0xffff:
            raise ValueError('Manager spatial entry reserved field must be uint16')
        if not 0 <= entry.source_index <= 0xffffffff:
            raise ValueError('Manager spatial entry source index must be uint32')
        if not isinstance(entry.packed_bound, LightManagerSpatialPackedBound):
            raise ValueError(
                'Manager spatial entry bound must be a packed-bound value')
        packed = (*entry.packed_bound.center, entry.packed_bound.radius)
        if len(entry.packed_bound.center) != 3 or any(
                not isinstance(value, int) or
                value < -0x8000 or value > 0x7fff
                for value in packed):
            raise ValueError(
                'Manager spatial packed center/radius values must be int16')

        radius = entry.packed_bound.radius
        for axis, coordinate in enumerate(entry.packed_bound.center):
            lower = _light_manager_spatial_saturate_int16(
                coordinate - radius)
            upper = _light_manager_spatial_saturate_int16(
                coordinate + radius)
            minimum[axis] = min(minimum[axis], lower)
            maximum[axis] = max(maximum[axis], upper)
        radius_weight = (
            radius_weight + ((3 * radius + 1) >> 1)) & 0xffffffff

    upper = np.asarray(maximum, dtype=np.float32)
    lower = np.asarray(minimum, dtype=np.float32)
    upper_half = np.asarray(upper * np.float32(.5), dtype=np.float32)
    upper_quarter = np.asarray(
        upper_half * np.float32(.5), dtype=np.float32)
    lower_quarter = np.asarray(
        lower * np.float32(.25), dtype=np.float32)
    center = np.asarray(lower_quarter + upper_quarter, dtype=np.float32)
    half_extents = np.asarray(upper_half - center, dtype=np.float32)
    return LightManagerSpatialRebuiltCell(
        center=tuple(float(value) for value in center),
        half_extents=tuple(float(value) for value in half_extents),
        radius_weight=radius_weight,
        state_byte=state_byte & 0x7f,
    )


def classify_light_manager_spatial_packed_sphere(
        entry: LightManagerSpatialEntry, packed_planes,
        *, query_mask: int = 0xffffffff,
        required_mask: int = 0,
        ) -> LightManagerSpatialPackedSphereClassification:
    """Reproduce worker block 0x1412B8D30 through 0x1412B8E40.

    An intersecting packed sphere whose center lies outside at least one plane
    is the native ambiguous state and requires exact source OBB refinement.
    """

    if not isinstance(entry, LightManagerSpatialEntry):
        raise ValueError('Manager spatial packed-sphere input must be an entry')
    if not 0 <= entry.selection_mask <= 0xffff:
        raise ValueError('Manager spatial entry mask must be uint16')
    if not isinstance(query_mask, int) or not 0 <= query_mask <= 0xffffffff:
        raise ValueError('Manager spatial query mask must be uint32')
    if not isinstance(required_mask, int) or not 0 <= required_mask <= 0xffffffff:
        raise ValueError('Manager spatial required mask must be uint32')
    mask_matches = (
        (entry.selection_mask & query_mask) == required_mask)
    if not mask_matches:
        return LightManagerSpatialPackedSphereClassification(
            False, False, False)

    if not isinstance(entry.packed_bound, LightManagerSpatialPackedBound):
        raise ValueError(
            'Manager spatial entry bound must be a packed-bound value')
    packed = (*entry.packed_bound.center, entry.packed_bound.radius)
    if len(entry.packed_bound.center) != 3 or any(
            not isinstance(value, int) or
            value < -0x8000 or value > 0x7fff
            for value in packed):
        raise ValueError(
            'Manager spatial packed center/radius values must be int16')
    decoded = np.asarray(packed, dtype=np.float32)
    decoded = np.asarray(decoded * np.float32(.5), dtype=np.float32)
    center = decoded[:3]
    radius = decoded[3]

    planes = np.asarray(packed_planes, dtype=np.float32)
    if planes.shape != (4, 4, 4) or not np.isfinite(planes).all():
        raise ValueError(
            'Manager spatial query planes must have shape (4, 4, 4) '
            'and be finite')

    def add(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            + np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    def multiply(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            * np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    distances = []
    for group in planes:
        distances.append(add(
            add(
                add(multiply(center[0], group[0]), group[3]),
                multiply(center[1], group[1]),
            ),
            multiply(center[2], group[2]),
        ))
    first = np.minimum(distances[0], distances[3])
    second = np.minimum(distances[1], distances[2])
    minimum = np.minimum(first, second)
    intersects = not bool(np.signbit(add(minimum, radius)).any())
    if not intersects:
        return LightManagerSpatialPackedSphereClassification(
            True, False, False)
    center_inside = not bool(np.signbit(minimum).any())
    return LightManagerSpatialPackedSphereClassification(
        True, True, center_inside)


def classify_light_manager_spatial_optional_packed_sphere(
        entry: LightManagerSpatialEntry, primary_packed_planes,
        optional_component_planes, *, query_mask: int = 0xffffffff,
        required_mask: int = 0,
        ) -> LightManagerSpatialOptionalPackedSphereClassification:
    """Reproduce optional worker block 0x1412B8FB0 through 0x1412B9107."""

    if not isinstance(entry, LightManagerSpatialEntry):
        raise ValueError(
            'Manager optional packed-sphere input must be an entry')
    if not 0 <= entry.selection_mask <= 0xffff:
        raise ValueError('Manager spatial entry mask must be uint16')
    if not isinstance(query_mask, int) or not 0 <= query_mask <= 0xffffffff:
        raise ValueError('Manager spatial query mask must be uint32')
    if not isinstance(required_mask, int) or not 0 <= required_mask <= 0xffffffff:
        raise ValueError('Manager spatial required mask must be uint32')
    mask_matches = (
        (entry.selection_mask & query_mask) == required_mask)
    if not mask_matches:
        return LightManagerSpatialOptionalPackedSphereClassification(
            False, False, False)

    if not isinstance(entry.packed_bound, LightManagerSpatialPackedBound):
        raise ValueError(
            'Manager spatial entry bound must be a packed-bound value')
    packed = (*entry.packed_bound.center, entry.packed_bound.radius)
    if len(entry.packed_bound.center) != 3 or any(
            not isinstance(value, int) or
            value < -0x8000 or value > 0x7fff
            for value in packed):
        raise ValueError(
            'Manager spatial packed center/radius values must be int16')
    decoded = np.asarray(packed, dtype=np.float32)
    decoded = np.asarray(decoded * np.float32(.5), dtype=np.float32)
    center = decoded[:3]
    radius = decoded[3]

    primary = np.asarray(primary_packed_planes, dtype=np.float32)
    if primary.shape != (4, 4, 4) or not np.isfinite(primary).all():
        raise ValueError(
            'Manager primary query planes must have shape (4, 4, 4) '
            'and be finite')
    optional = np.asarray(optional_component_planes, dtype=np.float32)
    if optional.shape != (4, 4) or not np.isfinite(optional).all():
        raise ValueError(
            'Manager optional query planes must have shape (4, 4) '
            'and be finite')

    def add(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            + np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    def subtract(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            - np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    def multiply(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            * np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    distances = []
    for group in primary:
        distances.append(add(
            add(
                add(multiply(center[0], group[0]), group[3]),
                multiply(center[1], group[1]),
            ),
            multiply(center[2], group[2]),
        ))
    first = np.minimum(distances[0], distances[3])
    second = np.minimum(distances[1], distances[2])
    primary_minimum = np.minimum(first, second)
    if bool(np.signbit(add(primary_minimum, radius)).any()):
        return LightManagerSpatialOptionalPackedSphereClassification(
            True, False, False)

    optional_distance = add(
        add(
            add(multiply(center[0], optional[0]), optional[3]),
            multiply(center[1], optional[1]),
        ),
        multiply(center[2], optional[2]),
    )
    optional_fully_inside = not bool(
        np.signbit(subtract(optional_distance, radius)).any())
    if optional_fully_inside:
        return LightManagerSpatialOptionalPackedSphereClassification(
            True, False, False)

    primary_center_inside = not bool(
        np.signbit(primary_minimum).any())
    optional_center_outside = bool(
        np.signbit(optional_distance).any())
    return LightManagerSpatialOptionalPackedSphereClassification(
        True, True, primary_center_inside and optional_center_outside)


def classify_light_manager_spatial_optional_page_chain(
        pages, first_page_index: int, primary_packed_planes,
        optional_component_planes, *, query_mask: int = 0xffffffff,
        required_mask: int = 0,
        ) -> LightManagerSpatialOptionalQueryBuckets:
    """Traverse one optional-query cell's newest-to-oldest page chain."""

    page_values = tuple(pages)
    if not all(isinstance(page, LightManagerSpatialPage)
               for page in page_values):
        raise ValueError(
            'Manager optional page chain must contain spatial-page values')
    if not isinstance(first_page_index, int):
        raise ValueError(
            'Manager optional first-page index must be an integer')
    direct = []
    refinement = []
    visited = []
    seen = set()
    page_index = first_page_index
    while page_index >= 0:
        if page_index in seen:
            raise ValueError('Manager optional page chain contains a cycle')
        if page_index >= len(page_values):
            raise ValueError(
                'Manager optional page-chain index is out of range')
        seen.add(page_index)
        visited.append(page_index)
        page = page_values[page_index]
        for entry in page.entries:
            classification = (
                classify_light_manager_spatial_optional_packed_sphere(
                    entry,
                    primary_packed_planes,
                    optional_component_planes,
                    query_mask=query_mask,
                    required_mask=required_mask,
                ))
            if not classification.mask_matches or (
                    not classification.survives_coarse):
                continue
            if classification.direct:
                direct.append(entry.source_index)
            else:
                refinement.append(entry.source_index)
        page_index = page.older_page
    return LightManagerSpatialOptionalQueryBuckets(
        tuple(direct), tuple(refinement), tuple(visited))


def classify_light_manager_spatial_primary_page_chain(
        pages, first_page_index: int, packed_planes,
        *, cell_fully_inside: bool = False,
        query_mask: int = 0xffffffff,
        required_mask: int = 0,
        ) -> LightManagerSpatialPrimaryQueryBuckets:
    """Traverse one cell's pages like the primary worker path.

    The cell points at its newest page and page +0x00 walks toward older pages.
    Direct candidates and candidates requiring exact source OBB refinement stay
    in their separate native buckets.
    """

    page_values = tuple(pages)
    if not all(isinstance(page, LightManagerSpatialPage)
               for page in page_values):
        raise ValueError(
            'Manager spatial page chain must contain spatial-page values')
    if not isinstance(first_page_index, int):
        raise ValueError('Manager spatial first-page index must be an integer')
    if not isinstance(cell_fully_inside, bool):
        raise ValueError('Manager spatial full-containment flag must be bool')
    if not isinstance(query_mask, int) or not 0 <= query_mask <= 0xffffffff:
        raise ValueError('Manager spatial query mask must be uint32')
    if not isinstance(required_mask, int) or not 0 <= required_mask <= 0xffffffff:
        raise ValueError('Manager spatial required mask must be uint32')

    direct = []
    refinement = []
    visited = []
    seen = set()
    page_index = first_page_index
    while page_index >= 0:
        if page_index in seen:
            raise ValueError('Manager spatial page chain contains a cycle')
        if page_index >= len(page_values):
            raise ValueError('Manager spatial page-chain index is out of range')
        seen.add(page_index)
        visited.append(page_index)
        page = page_values[page_index]
        for entry in page.entries:
            if cell_fully_inside:
                if (entry.selection_mask & query_mask) == required_mask:
                    direct.append(entry.source_index)
                continue
            classification = classify_light_manager_spatial_packed_sphere(
                entry,
                packed_planes,
                query_mask=query_mask,
                required_mask=required_mask,
            )
            if not classification.mask_matches or not classification.intersects:
                continue
            if classification.center_inside:
                direct.append(entry.source_index)
            else:
                refinement.append(entry.source_index)
        page_index = page.older_page
    return LightManagerSpatialPrimaryQueryBuckets(
        tuple(direct), tuple(refinement), tuple(visited))


def resolve_light_manager_spatial_primary_query_indices(
        buckets: LightManagerSpatialPrimaryQueryBuckets,
        source_by_index, packed_planes, *, capacity: int | None = None,
        ) -> tuple[int, ...]:
    """Resolve one bounded worker bucket set against explicit sources.

    Retail flushes a local bucket before adding a page when its count plus 15
    exceeds 1024. This helper covers the no-intermediate-flush regime and keeps
    larger scheduler-dependent output order explicit.
    """

    if not isinstance(buckets, LightManagerSpatialPrimaryQueryBuckets):
        raise ValueError(
            'Manager spatial query buckets must be a primary-bucket value')
    if len(buckets.direct_source_indices) > 1009 or (
            len(buckets.refinement_source_indices) > 1009):
        raise ValueError(
            'Manager spatial query buckets require intermediate worker flushes')
    if capacity is not None and (
            not isinstance(capacity, int) or not 0 <= capacity <= 0xffffffff):
        raise ValueError('Manager spatial query capacity must be uint32 or None')

    def source_for(index):
        if not isinstance(index, int) or not 0 <= index <= 0xffffffff:
            raise ValueError('Manager spatial source index must be uint32')
        try:
            source = source_by_index[index]
        except (IndexError, KeyError, TypeError) as error:
            raise ValueError(
                f'Manager spatial source snapshot lacks index {index}') from error
        if not isinstance(source, LightManagerCandidateSource):
            raise ValueError(
                'Manager spatial source snapshot values must be candidates')
        return source

    direct = tuple(buckets.direct_source_indices)
    for index in direct:
        source_for(index)
    refined = tuple(
        index for index in buckets.refinement_source_indices
        if light_manager_primary_query_source_visible(
            source_for(index), packed_planes)
    )
    result = direct + refined
    if capacity is not None:
        result = result[:capacity]
    return result


def resolve_light_manager_spatial_optional_query_indices(
        buckets: LightManagerSpatialOptionalQueryBuckets,
        source_by_index, primary_packed_planes, optional_component_planes,
        *, capacity: int | None = None,
        ) -> tuple[int, ...]:
    """Resolve optional direct/refinement buckets without a worker flush."""

    if not isinstance(buckets, LightManagerSpatialOptionalQueryBuckets):
        raise ValueError(
            'Manager optional query buckets must be an optional-bucket value')
    if len(buckets.direct_source_indices) > 1009 or (
            len(buckets.refinement_source_indices) > 1009):
        raise ValueError(
            'Manager optional query buckets require intermediate worker flushes')
    if capacity is not None and (
            not isinstance(capacity, int) or not 0 <= capacity <= 0xffffffff):
        raise ValueError('Manager optional query capacity must be uint32 or None')

    def source_for(index):
        if not isinstance(index, int) or not 0 <= index <= 0xffffffff:
            raise ValueError('Manager spatial source index must be uint32')
        try:
            source = source_by_index[index]
        except (IndexError, KeyError, TypeError) as error:
            raise ValueError(
                f'Manager spatial source snapshot lacks index {index}') from error
        if not isinstance(source, LightManagerCandidateSource):
            raise ValueError(
                'Manager spatial source snapshot values must be candidates')
        return source

    direct = tuple(buckets.direct_source_indices)
    for index in direct:
        source_for(index)
    refined = tuple(
        index for index in buckets.refinement_source_indices
        if light_manager_optional_query_source_visible(
            source_for(index),
            primary_packed_planes,
            optional_component_planes,
        )
    )
    result = direct + refined
    if capacity is not None:
        result = result[:capacity]
    return result


def _resolve_light_manager_spatial_worker_flush(
        direct_source_indices, refinement_source_indices,
        refinement_visible, *, existing_source_indices=(),
        capacity: int | None = None, final: bool = False,
        refinement_kind: str = 'primary_refinement'):
    """Apply one retail local-bucket threshold or final flush decision."""

    direct = tuple(direct_source_indices)
    refinement = tuple(refinement_source_indices)
    existing = tuple(existing_source_indices)
    if capacity is not None and (
            not isinstance(capacity, int) or not 0 <= capacity <= 0xffffffff):
        raise ValueError('Manager spatial query capacity must be uint32 or None')
    if capacity is not None and len(existing) > capacity:
        raise ValueError('Manager spatial existing output exceeds capacity')
    if not isinstance(final, bool):
        raise ValueError('Manager spatial final-flush flag must be bool')
    if refinement_kind not in ('primary_refinement', 'optional_refinement'):
        raise ValueError('Manager spatial refinement kind is invalid')

    output = list(existing)
    flushes = []

    def copy_retained(values):
        if capacity is None:
            copied = tuple(values)
        else:
            remaining = max(capacity - len(output), 0)
            copied = tuple(values[:remaining])
        output.extend(copied)
        return copied

    if direct and (final or len(direct) + 15 > 1024):
        copied = copy_retained(direct)
        flushes.append((
            LightManagerSpatialWorkerFlush(
                'direct', len(direct), len(direct), len(copied), final),
            direct,
            copied,
        ))
        direct = ()

    if refinement and (final or len(refinement) + 15 > 1024):
        retained = tuple(
            index for index in refinement if refinement_visible(index))
        copied = copy_retained(retained)
        flushes.append((
            LightManagerSpatialWorkerFlush(
                refinement_kind,
                len(refinement),
                len(retained),
                len(copied),
                final,
            ),
            retained,
            copied,
        ))
        refinement = ()

    return tuple(output), direct, refinement, tuple(flushes)


def _light_manager_spatial_query_source(source_by_index, index):
    if not isinstance(index, int) or not 0 <= index <= 0xffffffff:
        raise ValueError('Manager spatial source index must be uint32')
    try:
        source = source_by_index[index]
    except (IndexError, KeyError, TypeError) as error:
        raise ValueError(
            f'Manager spatial source snapshot lacks index {index}') from error
    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError(
            'Manager spatial source snapshot values must be candidates')
    return source


def _light_manager_spatial_page_order(pages, first_page_index, label):
    page_values = tuple(pages)
    if not all(isinstance(page, LightManagerSpatialPage)
               for page in page_values):
        raise ValueError(
            f'Manager {label} page chain must contain spatial-page values')
    if not isinstance(first_page_index, int):
        raise ValueError(
            f'Manager {label} first-page index must be an integer')
    ordered = []
    seen = set()
    page_index = first_page_index
    while page_index >= 0:
        if page_index in seen:
            raise ValueError(f'Manager {label} page chain contains a cycle')
        if page_index >= len(page_values):
            raise ValueError(
                f'Manager {label} page-chain index is out of range')
        seen.add(page_index)
        ordered.append((page_index, page_values[page_index]))
        page_index = page_values[page_index].older_page
    return tuple(ordered)


def resolve_light_manager_spatial_primary_page_query_indices(
        pages, first_page_index: int, source_by_index, packed_planes,
        *, cell_fully_inside: bool = False,
        query_mask: int = 0xffffffff, required_mask: int = 0,
        capacity: int | None = None,
        ) -> LightManagerSpatialPageQueryResolution:
    """Resolve one primary worker page stream with exact retail flush order."""

    if not isinstance(cell_fully_inside, bool):
        raise ValueError('Manager spatial full-containment flag must be bool')
    ordered = _light_manager_spatial_page_order(
        pages, first_page_index, 'spatial')
    output = ()
    direct = ()
    refinement = ()
    flushes = []
    visited = []

    def visible(index):
        return light_manager_primary_query_source_visible(
            _light_manager_spatial_query_source(source_by_index, index),
            packed_planes,
        )

    for page_index, page in ordered:
        visited.append(page_index)
        page_direct = []
        page_refinement = []
        for entry in page.entries:
            if cell_fully_inside:
                if (entry.selection_mask & query_mask) == required_mask:
                    _light_manager_spatial_query_source(
                        source_by_index, entry.source_index)
                    page_direct.append(entry.source_index)
                continue
            classification = classify_light_manager_spatial_packed_sphere(
                entry,
                packed_planes,
                query_mask=query_mask,
                required_mask=required_mask,
            )
            if not classification.mask_matches or not classification.intersects:
                continue
            if classification.center_inside:
                _light_manager_spatial_query_source(
                    source_by_index, entry.source_index)
                page_direct.append(entry.source_index)
            else:
                page_refinement.append(entry.source_index)
        direct += tuple(page_direct)
        refinement += tuple(page_refinement)
        output, direct, refinement, page_flushes = (
            _resolve_light_manager_spatial_worker_flush(
                direct,
                refinement,
                visible,
                existing_source_indices=output,
                capacity=capacity,
                final=False,
                refinement_kind='primary_refinement',
            ))
        flushes.extend(item[0] for item in page_flushes)

    output, direct, refinement, final_flushes = (
        _resolve_light_manager_spatial_worker_flush(
            direct,
            refinement,
            visible,
            existing_source_indices=output,
            capacity=capacity,
            final=True,
            refinement_kind='primary_refinement',
        ))
    flushes.extend(item[0] for item in final_flushes)
    return LightManagerSpatialPageQueryResolution(
        output, tuple(visited), tuple(flushes))


def resolve_light_manager_spatial_optional_page_query_indices(
        pages, first_page_index: int, source_by_index,
        primary_packed_planes, optional_component_planes,
        *, query_mask: int = 0xffffffff, required_mask: int = 0,
        capacity: int | None = None,
        ) -> LightManagerSpatialPageQueryResolution:
    """Resolve one optional worker page stream with exact retail flush order."""

    ordered = _light_manager_spatial_page_order(
        pages, first_page_index, 'optional')
    output = ()
    direct = ()
    refinement = ()
    flushes = []
    visited = []

    def visible(index):
        return light_manager_optional_query_source_visible(
            _light_manager_spatial_query_source(source_by_index, index),
            primary_packed_planes,
            optional_component_planes,
        )

    for page_index, page in ordered:
        visited.append(page_index)
        page_direct = []
        page_refinement = []
        for entry in page.entries:
            classification = (
                classify_light_manager_spatial_optional_packed_sphere(
                    entry,
                    primary_packed_planes,
                    optional_component_planes,
                    query_mask=query_mask,
                    required_mask=required_mask,
                ))
            if not classification.mask_matches or (
                    not classification.survives_coarse):
                continue
            if classification.direct:
                _light_manager_spatial_query_source(
                    source_by_index, entry.source_index)
                page_direct.append(entry.source_index)
            else:
                page_refinement.append(entry.source_index)
        direct += tuple(page_direct)
        refinement += tuple(page_refinement)
        output, direct, refinement, page_flushes = (
            _resolve_light_manager_spatial_worker_flush(
                direct,
                refinement,
                visible,
                existing_source_indices=output,
                capacity=capacity,
                final=False,
                refinement_kind='optional_refinement',
            ))
        flushes.extend(item[0] for item in page_flushes)

    output, direct, refinement, final_flushes = (
        _resolve_light_manager_spatial_worker_flush(
            direct,
            refinement,
            visible,
            existing_source_indices=output,
            capacity=capacity,
            final=True,
            refinement_kind='optional_refinement',
        ))
    flushes.extend(item[0] for item in final_flushes)
    return LightManagerSpatialPageQueryResolution(
        output, tuple(visited), tuple(flushes))

def classify_light_manager_spatial_aabb(
        cell: LightManagerSpatialAabb, packed_planes,
        ) -> LightManagerSpatialAabbClassification:
    """Classify one cell exactly as ``0x141603A80`` does.

    The first native output says the AABB is fully inside all 16 query planes;
    the second says it intersects them. Plane groups retain their component-major
    SIMD layout and sign-bit boundary behavior.
    """

    if not isinstance(cell, LightManagerSpatialAabb):
        raise ValueError('cell must be one LightManagerSpatialAabb')
    center = _float3(cell.center, 'Manager spatial cell center')
    extents = _float3(
        cell.half_extents, 'Manager spatial cell half extents')
    if np.any(extents < 0):
        raise ValueError('Manager spatial cell half extents must be nonnegative')
    planes = np.asarray(packed_planes, dtype=np.float32)
    if planes.shape != (4, 4, 4) or not np.isfinite(planes).all():
        raise ValueError(
            'Manager spatial query planes must have shape (4, 4, 4) '
            'and be finite')

    def add(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            + np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    def subtract(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            - np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    def multiply(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            * np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    distances = []
    supports = []
    for group in planes:
        distance = add(
            add(
                add(multiply(center[0], group[0]), group[3]),
                multiply(center[1], group[1]),
            ),
            multiply(center[2], group[2]),
        )
        support = add(
            add(
                np.abs(multiply(extents[1], group[1])).astype(np.float32),
                np.abs(multiply(extents[0], group[0])).astype(np.float32),
            ),
            np.abs(multiply(extents[2], group[2])).astype(np.float32),
        )
        distances.append(distance)
        supports.append(support)

    outer = [add(distance, support)
             for distance, support in zip(distances, supports)]
    outer_minimum = np.minimum(outer[0], outer[1])
    outer_minimum = np.minimum(outer_minimum, outer[2])
    outer_minimum = np.minimum(outer_minimum, outer[3])
    intersects = not bool(np.signbit(outer_minimum).any())
    if not intersects:
        return LightManagerSpatialAabbClassification(False, False)

    inner = [subtract(distance, support)
             for distance, support in zip(distances, supports)]
    inner_minimum = np.minimum(inner[0], inner[1])
    inner_minimum = np.minimum(inner_minimum, inner[2])
    inner_minimum = np.minimum(inner_minimum, inner[3])
    fully_inside = not bool(np.signbit(inner_minimum).any())
    return LightManagerSpatialAabbClassification(True, fully_inside)


def select_light_manager_spatial_aabb_indices(cells, packed_planes) -> tuple[int, ...]:
    """Return ordered uint16 cell indices like batch helper ``0x141603D40``."""

    values = tuple(cells)
    if len(values) > 0x10000:
        raise ValueError('Manager spatial AABB batch exceeds uint16 index range')
    if not all(isinstance(cell, LightManagerSpatialAabb) for cell in values):
        raise ValueError('Manager spatial AABB batch must contain cell values')
    return tuple(
        index for index, cell in enumerate(values)
        if classify_light_manager_spatial_aabb(cell, packed_planes).intersects
    )


def classify_light_manager_spatial_query_obb(
        axis_extent_records, center, packed_planes,
        ) -> LightManagerSpatialObbClassification:
    """Reproduce both outputs of oriented classifier ``0x141603FE0``.

    Each input row stores an axis direction in XYZ and its extent in W. The
    helper multiplies those values before evaluating OBB support. The first
    result reports intersection with the query; the second reports that the
    input OBB covers the complete query volume.
    """

    records = np.asarray(axis_extent_records, dtype=np.float32)
    if records.shape != (3, 4) or not np.isfinite(records).all():
        raise ValueError(
            'Manager spatial OBB axes must have shape (3, 4) and be finite')
    origin = _float3(center, 'Manager spatial OBB center')
    planes = np.asarray(packed_planes, dtype=np.float32)
    if planes.shape != (4, 4, 4) or not np.isfinite(planes).all():
        raise ValueError(
            'Manager spatial query planes must have shape (4, 4, 4) '
            'and be finite')
    half_axes = np.asarray(
        records[:, :3] * records[:, 3:4], dtype=np.float32)

    def add(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            + np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    def subtract(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            - np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    def multiply(first, second):
        return np.asarray(
            np.asarray(first, dtype=np.float32)
            * np.asarray(second, dtype=np.float32),
            dtype=np.float32)

    distances = []
    supports = []
    intersection_results = []
    for group in planes:
        distance = add(
            add(
                add(multiply(origin[0], group[0]), group[3]),
                multiply(origin[1], group[1]),
            ),
            multiply(origin[2], group[2]),
        )
        support = np.zeros(4, dtype=np.float32)
        for axis in half_axes:
            projection = add(
                add(
                    multiply(axis[1], group[1]),
                    multiply(axis[0], group[0]),
                ),
                multiply(axis[2], group[2]),
            )
            support = add(support, np.abs(projection).astype(np.float32))
        distances.append(distance)
        supports.append(support)
        intersection_results.append(add(distance, support))

    minimum = np.minimum(intersection_results[0], intersection_results[1])
    minimum = np.minimum(minimum, intersection_results[2])
    minimum = np.minimum(minimum, intersection_results[3])
    intersects = not bool(np.signbit(minimum).any())
    if not intersects:
        return LightManagerSpatialObbClassification(False, False)

    coverage_results = [
        subtract(support, distance)
        for support, distance in zip(supports, distances)
    ]
    minimum = np.minimum(coverage_results[0], coverage_results[1])
    minimum = np.minimum(minimum, coverage_results[2])
    minimum = np.minimum(minimum, coverage_results[3])
    covers_query = not bool(np.signbit(minimum).any())
    return LightManagerSpatialObbClassification(True, covers_query)


def light_manager_spatial_query_obb_intersects(
        axis_extent_records, center, packed_planes,
        ) -> bool:
    """Return the consumed intersection output of ``0x141603FE0``."""

    return classify_light_manager_spatial_query_obb(
        axis_extent_records, center, packed_planes).intersects


def _light_manager_crc32_update(data: bytes, seed: int) -> int:
    """Run the table-equivalent retail CRC loop without final inversion."""

    crc = seed & 0xffffffff
    for value in data:
        crc ^= value
        for _bit in range(8):
            crc = ((crc >> 1) ^ (0xedb88320 if crc & 1 else 0)) & 0xffffffff
    return crc


def _light_manager_resource_shape_values(
        inputs: LightManagerResourceShapeInputs) -> tuple[np.float32, ...]:
    if not isinstance(inputs, LightManagerResourceShapeInputs):
        raise ValueError(
            'shape_inputs must be LightManagerResourceShapeInputs')
    return tuple(
        _finite_float32(getattr(inputs, f'parameter_0x{offset:x}'),
                        f'Manager resource parameter 0x{offset:x}')
        for offset in (0x120, 0x124, 0x128, 0x12c, 0x130, 0x134))


def _light_manager_plane_dot(first, second) -> np.float32:
    """Match the two-pair scalar dot order used by ``0x1410B6480``."""

    left = np.float32(
        np.float32(first[1] * second[1])
        + np.float32(first[0] * second[0]))
    right = np.float32(
        np.float32(first[3] * second[3])
        + np.float32(first[2] * second[2]))
    return np.float32(left + right)


def _light_manager_axis_translation_dot(axis, translation) -> np.float32:
    """Match retail's YX-then-Z affine translation reduction."""

    xy = np.float32(
        np.float32(axis[1] * translation[1])
        + np.float32(axis[0] * translation[0]))
    return np.float32(xy + np.float32(axis[2] * translation[2]))


def _light_manager_world_plane_to_local(plane, transform) -> np.ndarray:
    """Apply the exact row-wise plane transform in ``0x1415E6280``."""

    source = np.asarray(plane, dtype=np.float32)
    matrix = np.asarray(transform, dtype=np.float32)
    if source.shape != (4,) or not np.isfinite(source).all():
        raise ValueError('Manager clip plane must be one finite float4')
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Manager candidate transform must be a finite float4x4')
    result = np.empty(4, dtype=np.float32)
    for row in range(4):
        wz = np.float32(
            np.float32(source[3] * matrix[row, 3])
            + np.float32(source[2] * matrix[row, 2]))
        yx = np.float32(
            np.float32(source[1] * matrix[row, 1])
            + np.float32(source[0] * matrix[row, 0]))
        result[row] = np.float32(wz + yx)
    return result


def build_light_manager_resource_clip_planes(
        source: LightManagerCandidateSource,
        shape_inputs: LightManagerResourceShapeInputs) -> np.ndarray:
    """Build the ordered world-space plane list from ``0x1410B6480``.

    The refresh caller supplies zero or one resolved oriented-box resource and
    no camera object. The resolved box contributes six planes. Type 0 can add
    source ``+0x124`` as a local upper-Z plane; types 1 and 2 can add
    ``+0x12c`` and ``+0x130`` as upper- and lower-Z planes. Retail partitions
    the six box planes around the light origin, or around negative local Z for
    type 3, before inserting the scalar planes.
    """

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    p120, p124, p128, p12c, p130, p134 = (
        _light_manager_resource_shape_values(shape_inputs))
    del p120, p128, p134
    light_type = _bounded_integer(
        source.light_type, 0, 0xff, 'Manager candidate light type')
    matrix = np.asarray(source.transform_matrix, dtype=np.float32)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Manager candidate transform must be a finite float4x4')

    primary = p12c if light_type in (1, 2) else (
        p124 if light_type == 0 else np.float32(0))
    secondary = p130 if light_type in (1, 2) else np.float32(0)
    if light_type == 3:
        sorting_point = np.asarray((
            np.float32(-matrix[2, 0]),
            np.float32(-matrix[2, 1]),
            np.float32(-matrix[2, 2]),
            np.float32(0),
        ), dtype=np.float32)
    else:
        sorting_point = np.asarray((
            matrix[3, 0], matrix[3, 1], matrix[3, 2], np.float32(1),
        ), dtype=np.float32)

    front: list[np.ndarray] = []
    back: list[np.ndarray] = []
    resource = shape_inputs.resolved_clip_resource
    if resource is not None:
        if not isinstance(resource, LightManagerClipResource):
            raise ValueError(
                'resolved_clip_resource must be one LightManagerClipResource')
        resource_matrix = np.asarray(
            resource.transform_matrix, dtype=np.float32)
        if (resource_matrix.shape != (4, 4)
                or not np.isfinite(resource_matrix).all()):
            raise ValueError(
                'Manager clip-resource transform must be a finite float4x4')
        extents = _float3(
            resource.half_extents, 'Manager clip-resource half extents')
        if np.any(extents < 0):
            raise ValueError(
                'Manager clip-resource half extents must be nonnegative')
        translation = resource_matrix[3, :3]
        for axis_index in range(3):
            axis = resource_matrix[axis_index, :3]
            translated = _light_manager_axis_translation_dot(
                axis, translation)
            inverse_translation = np.float32(-translated)
            for direction in (np.float32(-1), np.float32(1)):
                plane = np.empty(4, dtype=np.float32)
                # The affine helper writes +0 into its last column. Retail's
                # multiply-add therefore canonicalizes -0 normal lanes to +0.
                zero = np.float32(extents[axis_index] * np.float32(0))
                for component in range(3):
                    plane[component] = np.float32(
                        np.float32(direction * axis[component]) + zero)
                plane[3] = np.float32(
                    np.float32(direction * inverse_translation)
                    + extents[axis_index])
                if _light_manager_plane_dot(plane, sorting_point) > 0:
                    back.append(plane)
                else:
                    front.append(plane)

    translation = matrix[3, :3]
    local_z = matrix[2, :3]
    scalar_planes: list[np.ndarray] = []
    if secondary > 0:
        translated = _light_manager_axis_translation_dot(
            local_z, translation)
        scalar_planes.append(np.asarray((
            local_z[0], local_z[1], local_z[2],
            np.float32(np.float32(-translated) - secondary),
        ), dtype=np.float32))
    if primary > 0:
        negative_z = np.asarray(-local_z, dtype=np.float32)
        translated = _light_manager_axis_translation_dot(
            negative_z, translation)
        scalar_planes.append(np.asarray((
            negative_z[0], negative_z[1], negative_z[2],
            np.float32(primary - translated),
        ), dtype=np.float32))

    ordered = front + scalar_planes + list(reversed(back))
    if not ordered:
        return np.empty((0, 4), dtype=np.float32)
    return np.asarray(ordered, dtype=np.float32).reshape(-1, 4)


def light_manager_resource_version(
        source: LightManagerCandidateSource,
        shape_inputs: LightManagerResourceShapeInputs, *,
        global_epoch: int, cached_epoch: int, cached_version: int,
        ) -> LightManagerResourceVersion:
    """Reproduce the cached shell-resource version at ``0x141097250``.

    When the unsigned global epoch does not exceed source ``+0xd0``, retail
    returns cached source ``+0xd4``.  Otherwise it hashes the 64-byte transform
    with raw CRC32 seed ``0xedb88320``, folds an optional resolved resource
    version and the type-specific source fields, then updates both cache words.
    """

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    epoch = _bounded_integer(global_epoch, 0, 0xffffffff,
                             'Manager resource global epoch')
    old_epoch = _bounded_integer(cached_epoch, 0, 0xffffffff,
                                 'Manager resource cached epoch')
    old_version = _bounded_integer(cached_version, 0, 0xffffffff,
                                   'Manager resource cached version')
    values = _light_manager_resource_shape_values(shape_inputs)
    if epoch <= old_epoch:
        return LightManagerResourceVersion(
            old_version, False, old_epoch, old_version)

    matrix = np.asarray(source.transform_matrix, dtype='<f4')
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Manager candidate transform must be a finite float4x4')
    light_type = _bounded_integer(
        source.light_type, 0, 0xff, 'Manager candidate light type')
    crc = _light_manager_crc32_update(matrix.tobytes(order='C'), 0xedb88320)
    if shape_inputs.resolved_resource_version is not None:
        resource_version = _bounded_integer(
            shape_inputs.resolved_resource_version, 0, 0xffffffff,
            'Manager resolved resource version')
        crc = _light_manager_crc32_update(
            struct.pack('<I', resource_version), crc)

    p120, _p124, p128, p12c, p130, p134 = values
    if light_type in (1, 2):
        extents = _float3(source.bound_extents, 'Manager bound extents')
        radius_scale = _finite_float32(
            source.bound_radius_scale, 'Manager bound radius scale')
        if radius_scale < 0 or np.any(extents < 0):
            raise ValueError('Manager candidate bound sizes must be nonnegative')
        radius = np.maximum(extents[2], extents[1])
        radius = np.maximum(radius, extents[0])
        radius = np.float32(np.float32(radius) * radius_scale)
        terminal = p128 if light_type == 1 else p120
        for value in (p12c, p130, p134, radius, terminal):
            crc = _light_manager_crc32_update(
                np.asarray(value, dtype='<f4').tobytes(), crc)
    elif light_type == 0:
        crc = _light_manager_crc32_update(
            np.asarray(p128, dtype='<f4').tobytes(), crc)
    elif light_type in (3, 4):
        if source.occlusion_half_extents is None:
            raise ValueError(
                'Manager occlusion half extents are required for this resource type')
        shape_vector = _float3(
            source.occlusion_half_extents, 'Manager occlusion half extents')
        crc = _light_manager_crc32_update(
            np.asarray(shape_vector, dtype='<f4').tobytes(), crc)

    return LightManagerResourceVersion(crc, True, epoch, crc)


def light_manager_resource_stream_allocation_bytes(vertex_count: int) -> int:
    """Return ``align4(vertexCount + 1) * sizeof(float3)`` from refresh."""

    count = _bounded_integer(
        vertex_count, 1, 0x7ffffffa, 'Manager generated vertex count')
    return ((count + 4) & ~3) * 12


def build_light_manager_resource_refresh_dispatch(
        source: LightManagerCandidateSource,
        shape_inputs: LightManagerResourceShapeInputs, *,
        computed_version: int, built_version: int,
        generated_vertex_count: int | None = None,
        ) -> LightManagerResourceRefreshDispatch:
    """Expose the exact type dispatch and allocation boundary in ``0x14109D010``.

    ``generated_vertex_count`` is the selected native shape builder's result.
    Leaving it ``None`` returns the pre-builder dispatch. A zero result leaves
    source ``+0xd8`` unchanged; a positive result updates the built version and
    requests the retail padded float3 allocation.
    """

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    values = _light_manager_resource_shape_values(shape_inputs)
    version = _bounded_integer(computed_version, 0, 0xffffffff,
                               'Manager computed resource version')
    previous = _bounded_integer(built_version, 0, 0xffffffff,
                                'Manager built resource version')
    if generated_vertex_count is not None:
        count = _bounded_integer(
            generated_vertex_count, 0, 0x7ffffffa,
            'Manager generated vertex count')
    else:
        count = None
    if version == previous:
        return LightManagerResourceRefreshDispatch(
            False, version, None, None,
            (shape_inputs.resolved_resource_version is not None
             or shape_inputs.resolved_clip_resource is not None),
            None, None, None, count, None, previous)

    light_type = _bounded_integer(
        source.light_type, 0, 0xff, 'Manager candidate light type')
    flags = _bounded_integer(
        source.runtime_flags, 0, 0xffffffff,
        'Manager candidate runtime flags')
    p120, p124, p128, p12c, p130, _p134 = values
    common_primary = p12c if light_type in (1, 2) else (
        p124 if light_type == 0 else np.float32(0))
    common_secondary = p130 if light_type in (1, 2) else np.float32(0)
    builder = None
    vector = None
    scalars = None
    if light_type == 0:
        builder = '0x1410B58B0'
        vector = (float(p128),) * 3
    elif light_type == 1:
        builder = '0x1410B5AE0'
        scalars = (float(p120), float(p128))
    elif light_type == 2:
        builder = '0x1410B59C0'
        scalars = (float(p128), float(p120))
    elif light_type in (3, 4):
        if source.occlusion_half_extents is None:
            raise ValueError(
                'Manager occlusion half extents are required for this resource type')
        extents = _float3(
            source.occlusion_half_extents, 'Manager occlusion half extents')
        vector = tuple(float(value) for value in extents)
        builder = ('0x1410B58B0' if light_type == 4 and flags & (1 << 8)
                   else '0x1410B57F0')

    if builder is None and count not in (None, 0):
        raise ValueError(
            'Manager generated vertex count must be zero without a shape builder')
    allocation = (
        light_manager_resource_stream_allocation_bytes(count)
        if count is not None and count > 0 else None)
    version_after = version if count is not None and count > 0 else previous
    return LightManagerResourceRefreshDispatch(
        True, version, float(common_primary), float(common_secondary),
        (shape_inputs.resolved_resource_version is not None
         or shape_inputs.resolved_clip_resource is not None),
        builder, vector, scalars, count, allocation, version_after)


def build_light_manager_resource_shell_vertices(
        source: LightManagerCandidateSource,
        shape_inputs: LightManagerResourceShapeInputs, *,
        clip_plane=None, clip_planes=None,
        ) -> np.ndarray:
    """Generate and clip the selected native shell before float3 allocation.

    Without an explicit plane override, the ordered world-space resource and
    scalar planes from ``0x1410B6480`` are transformed into light-local space
    exactly as ``0x1415E6280`` does, then applied in order. ``clip_plane``
    preserves the earlier single local-plane API; ``clip_planes`` accepts an
    explicit local plane array. Allocation and version ownership remain
    explicit in the refresh dispatch result.
    """

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    p120, _p124, p128, _p12c, _p130, _p134 = (
        _light_manager_resource_shape_values(shape_inputs))
    light_type = _bounded_integer(
        source.light_type, 0, 0xff, 'Manager candidate light type')
    flags = _bounded_integer(
        source.runtime_flags, 0, 0xffffffff,
        'Manager candidate runtime flags')

    if light_type == 0:
        vertices = build_light_manager_round_shell_vertices(
            (p128, p128, p128))
    elif light_type == 1:
        vertices = build_light_manager_type_1_shell_vertices(p120, p128)
    elif light_type == 2:
        vertices = build_light_manager_type_2_shell_vertices(p128, p120)
    elif light_type in (3, 4):
        if source.occlusion_half_extents is None:
            raise ValueError(
                'Manager occlusion half extents are required for this resource type')
        if light_type == 4 and flags & (1 << 8):
            vertices = build_light_manager_round_shell_vertices(
                source.occlusion_half_extents)
        else:
            vertices = build_light_manager_box_shell_vertices(
                source.occlusion_half_extents)
    else:
        return np.empty((0, 3), dtype=np.float32)

    if clip_plane is not None and clip_planes is not None:
        raise ValueError('Specify either clip_plane or clip_planes, not both')
    if clip_plane is not None:
        return prepare_light_shell_vertices(vertices, clip_plane)
    if clip_planes is not None:
        return prepare_light_shell_vertices_for_planes(vertices, clip_planes)
    world_planes = build_light_manager_resource_clip_planes(
        source, shape_inputs)
    if len(world_planes):
        local_planes = np.asarray([
            _light_manager_world_plane_to_local(
                plane, source.transform_matrix)
            for plane in world_planes
        ], dtype=np.float32)
        return prepare_light_shell_vertices_for_planes(vertices, local_planes)
    return vertices


def finalize_light_manager_resource_shell_output(
        source: LightManagerCandidateSource,
        vertices: np.ndarray) -> LightManagerResourceShellOutput:
    """Reproduce refresh output packing, bounds and shrink-update decision."""

    stream = np.asarray(vertices, dtype=np.float32)
    if (stream.ndim != 2 or stream.shape[1] != 3 or len(stream) % 3
            or not np.isfinite(stream).all()):
        raise ValueError('Manager resource shell must be finite float3 triangles')
    previous_center = _float3(
        source.local_bound_center, 'Manager local bound center')
    previous_radius = _finite_float32(
        source.bound_radius_scale, 'Manager bound radius scale')
    previous_extents = _float3(
        source.bound_extents, 'Manager bound extents')
    previous_center_radius = np.asarray((
        previous_center[0], previous_center[1], previous_center[2],
        previous_radius,
    ), dtype=np.float32)
    if not len(stream):
        return LightManagerResourceShellOutput(
            stream.copy(), None, None, None, None, False,
            previous_center_radius, previous_extents.copy())

    minimum = np.asarray(np.min(stream, axis=0), dtype=np.float32)
    maximum = np.asarray(np.max(stream, axis=0), dtype=np.float32)
    center = np.asarray(
        np.asarray(maximum + minimum, dtype=np.float32) * np.float32(.5),
        dtype=np.float32)
    radius_squared = np.float32(0)
    for vertex in stream:
        delta = np.asarray(center - vertex, dtype=np.float32)
        squared_yx = np.float32(
            np.float32(delta[1] * delta[1])
            + np.float32(delta[0] * delta[0]))
        squared = np.float32(
            squared_yx + np.float32(delta[2] * delta[2]))
        radius_squared = np.float32(max(radius_squared, squared))
    sphere = np.asarray((
        center[0], center[1], center[2],
        np.float32(np.sqrt(radius_squared)),
    ), dtype=np.float32)

    lengths = np.asarray(maximum - minimum, dtype=np.float32)
    new_extents = np.asarray(lengths * np.float32(.5), dtype=np.float32)
    light_type = _bounded_integer(
        source.light_type, 0, 0xff, 'Manager candidate light type')
    new_xy = np.float32(lengths[0] * lengths[1])
    new_z = np.float32(lengths[2] * np.float32(.125))
    new_volume = np.float32(new_xy * new_z)
    previous_xy = np.float32(previous_extents[1] * previous_extents[0])
    previous_xyz = np.float32(previous_xy * previous_extents[2])
    previous_threshold = np.float32(
        previous_xyz * np.float32(.9800000190734863))
    update = bool(
        light_type not in (3, 4) and new_volume < previous_threshold)
    return LightManagerResourceShellOutput(
        stream.copy(), minimum, maximum, sphere,
        light_manager_resource_stream_allocation_bytes(len(stream)), update,
        sphere.copy() if update else previous_center_radius,
        new_extents if update else previous_extents.copy(),
    )


def build_light_manager_resource_shell_output(
        source: LightManagerCandidateSource,
        shape_inputs: LightManagerResourceShapeInputs, *,
        clip_plane=None, clip_planes=None,
        ) -> LightManagerResourceShellOutput:
    """Build the complete CPU-visible positive-count refresh result."""

    vertices = build_light_manager_resource_shell_vertices(
        source, shape_inputs, clip_plane=clip_plane,
        clip_planes=clip_planes)
    return finalize_light_manager_resource_shell_output(source, vertices)


def light_manager_bounding_sphere_distance(
        source: LightManagerCandidateSource, camera_position) -> np.float32:
    """Return helper ``0x1410B9750``'s camera-to-boundary distance.

    Retail transforms the candidate's local bound center, subtracts the
    camera, evaluates the same overflow-safe length as ``0x140389950``, and
    subtracts ``max(bound_extents) * bound_radius_scale`` with a zero floor.
    """

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    extents = _float3(source.bound_extents, 'Manager bound extents')
    camera = _float3(camera_position, 'Manager camera position')
    radius_scale = _finite_float32(
        source.bound_radius_scale, 'Manager bound radius scale')
    if radius_scale < 0 or np.any(extents < 0):
        raise ValueError('Manager candidate bound sizes must be nonnegative')

    world_center = _light_manager_world_bound_center(source)
    radius = np.maximum(extents[2], extents[1])
    radius = np.maximum(radius, extents[0])
    radius = np.float32(np.float32(radius) * radius_scale)
    return np.float32(max(
        float(np.float32(
            _native_float3_distance(world_center, camera) - radius)), 0.0))


def evaluate_light_manager_candidate(
        source: LightManagerCandidateSource, camera_position, *,
        singleton_restriction_enabled: bool = False,
        singleton_match: bool = True,
        bypass_runtime_flag_4_rejection: bool = False,
        view_filter_result: bool | None = None,
        ) -> LightManagerSelectionDecision:
    """Reproduce one candidate predicate in worker ``0x1410B9A50``.

    The manager occlusion result remains explicit because the current 16-bit
    hierarchical-depth snapshot is absent from the capture. ``None`` models a
    null manager view object. The source-side OBB query is independently
    available through :func:`build_light_manager_occlusion_query`. The returned
    normalized flags include the worker's in-place ``& 0x1fffffff`` operation.
    """

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    flags = _bounded_integer(
        source.runtime_flags, 0, 0xffffffff,
        'Manager candidate runtime flags') & 0x1fffffff
    light_type = _bounded_integer(
        source.light_type, 0, 0xff, 'Manager candidate light type')
    color = _float3(source.linear_color, 'Manager candidate linear color')
    camera = _float3(camera_position, 'Manager camera position')
    fade_offset = _finite_float32(
        source.distance_fade_offset, 'Manager distance-fade offset')
    fade_scale = _finite_float32(
        source.distance_fade_scale, 'Manager distance-fade scale')
    maximum_distance = _finite_float32(
        source.maximum_camera_distance, 'Manager maximum camera distance')
    if maximum_distance < 0:
        raise ValueError('Manager maximum camera distance must be nonnegative')
    for value, description in (
            (singleton_restriction_enabled, 'singleton restriction'),
            (singleton_match, 'singleton match'),
            (bypass_runtime_flag_4_rejection, 'runtime-flag-4 bypass')):
        if not isinstance(value, (bool, np.bool_)):
            raise ValueError(f'Manager {description} must be boolean')
    if view_filter_result is not None and not isinstance(
            view_filter_result, (bool, np.bool_)):
        raise ValueError('Manager view-filter result must be boolean or None')

    def decision(selected: bool, rejection: str | None, *,
                 sphere_distance=None, distance_fade=None):
        return LightManagerSelectionDecision(
            selected, rejection, flags,
            None if sphere_distance is None else float(sphere_distance),
            None if distance_fade is None else float(distance_fade))

    if not flags & (1 << 2):
        return decision(False, 'runtime_flag_2_clear')
    if singleton_restriction_enabled and not singleton_match:
        return decision(False, 'singleton_mismatch')
    if not bypass_runtime_flag_4_rejection and flags & (1 << 4):
        return decision(False, 'runtime_flag_4_set')

    sphere_distance = None
    if flags & (1 << 18):
        sphere_distance = light_manager_bounding_sphere_distance(source, camera)
        if sphere_distance > maximum_distance:
            return decision(
                False, 'maximum_camera_distance',
                sphere_distance=sphere_distance)

    distance_fade = None
    if flags & (1 << 19):
        matrix = np.asarray(source.transform_matrix, dtype=np.float32)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
            raise ValueError(
                'Manager candidate transform must be a finite float4x4')
        point_distance = _native_float3_distance(matrix[3, :3], camera)
        distance_fade = np.float32(
            np.float32(point_distance * fade_scale) + fade_offset)
        distance_fade = np.float32(max(float(distance_fade), 0.0))
        distance_fade = np.float32(min(float(distance_fade), 1.0))
        if distance_fade <= np.float32(0):
            return decision(
                False, 'distance_fade_zero',
                sphere_distance=sphere_distance,
                distance_fade=distance_fade)

    color_sum = np.float32(
        np.float32(color[1] + color[0]) + color[2])
    if color_sum > np.float32(0):
        if light_type == 5:
            return decision(
                False, 'emissive_type_5',
                sphere_distance=sphere_distance,
                distance_fade=distance_fade)
    elif light_type != 4:
        return decision(
            False, 'nonemissive_non_type_4',
            sphere_distance=sphere_distance,
            distance_fade=distance_fade)

    if view_filter_result is not None and not view_filter_result:
        return decision(
            False, 'view_filter', sphere_distance=sphere_distance,
            distance_fade=distance_fade)
    return decision(
        True, None, sphere_distance=sphere_distance,
        distance_fade=distance_fade)


def build_light_manager_selection_batches(
        candidates, camera_position, *, view_filter_results=None,
        singleton_restriction_enabled: bool = False,
        singleton_matches=None,
        bypass_runtime_flag_4_rejection: bool = False,
        completed_chunk_order=None,
        ) -> tuple[tuple[int, ...], ...]:
    """Return exact selected membership for native 16-candidate work batches.

    Each tuple preserves source order within one chunk claimed by the worker.
    With no completion order, tuples remain in source-claim order for static
    inspection.  A supplied order must name every claimed chunk once, including
    empty chunks; the result then reproduces the order in which retail's atomic
    selected-count reservations append their contiguous local pointer blocks.
    """

    items = tuple(candidates)
    if not all(isinstance(item, LightManagerCandidateSource) for item in items):
        raise ValueError(
            'candidates must contain LightManagerCandidateSource entries')

    def optional_values(values, default, description):
        if values is None:
            return (default,) * len(items)
        result = tuple(values)
        if len(result) != len(items):
            raise ValueError(
                f'{description} count must match manager candidates')
        return result

    filter_results = optional_values(
        view_filter_results, None, 'View-filter result')
    matches = optional_values(singleton_matches, True, 'Singleton-match')
    selected = []
    for start in range(0, len(items), 16):
        batch = []
        for index in range(start, min(start + 16, len(items))):
            result = evaluate_light_manager_candidate(
                items[index], camera_position,
                singleton_restriction_enabled=singleton_restriction_enabled,
                singleton_match=matches[index],
                bypass_runtime_flag_4_rejection=(
                    bypass_runtime_flag_4_rejection),
                view_filter_result=filter_results[index],
            )
            if result.selected:
                batch.append(index)
        selected.append(tuple(batch))
    batches = tuple(selected)
    if completed_chunk_order is None:
        return batches

    completion_order = tuple(completed_chunk_order)
    if len(completion_order) != len(batches):
        raise ValueError(
            'Completed chunk order must include every claimed chunk')
    if batches:
        completion_order = tuple(
            _bounded_integer(
                value, 0, len(batches) - 1, 'Completed chunk index')
            for value in completion_order)
    if len(set(completion_order)) != len(completion_order):
        raise ValueError('Completed chunk order entries must be unique')
    return tuple(batches[index] for index in completion_order)


def light_manager_frame_priority(
        source: LightManagerCandidateSource, camera_position) -> np.float32:
    """Return consolidation score from ``0x1410BAEF0..0x1410BB011``.

    The score is the transformed bound radius divided by the camera distance
    to its center.  Retail clamps the denominator to 1.0 and evaluates the
    transform, stable length, maxima, multiply and divide in binary32.
    """

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    extents = _float3(source.bound_extents, 'Manager bound extents')
    radius_scale = _finite_float32(
        source.bound_radius_scale, 'Manager bound radius scale')
    camera = _float3(camera_position, 'Manager camera position')
    if radius_scale < 0 or np.any(extents < 0):
        raise ValueError('Manager candidate bound sizes must be nonnegative')

    world_center = _light_manager_world_bound_center(source)
    radius = np.maximum(extents[2], extents[1])
    radius = np.maximum(radius, extents[0])
    radius = np.float32(np.float32(radius) * radius_scale)
    distance = np.float32(max(
        float(_native_float3_distance(world_center, camera)), 1.0))
    score = np.float32(radius / distance)
    if not np.isfinite(score):
        raise ValueError('Manager frame priority must be finite float32')
    return score


def light_manager_secondary_distance_squared(
        source: LightManagerCandidateSource, camera_position) -> np.float32:
    """Return the direct binary32 score used for secondary-query ordering."""

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    camera = _float3(camera_position, 'Manager camera position')
    delta = np.asarray(
        _light_manager_world_bound_center(source) - camera, dtype=np.float32)
    squared_yx = np.float32(
        np.float32(delta[1] * delta[1])
        + np.float32(delta[0] * delta[0]))
    squared = np.float32(
        squared_yx + np.float32(delta[2] * delta[2]))
    if not np.isfinite(squared):
        raise ValueError(
            'Manager secondary distance squared must be finite float32')
    return squared


def light_manager_runtime_flag_21_defer(
        source: LightManagerCandidateSource,
        manager_reference_position) -> bool:
    """Return the exact distance predicate at ``0x14109A670``.

    Runtime flag 21 enables this test. Retail compares squared distance from
    the source translation to the manager reference position against the
    square of ``max(bound_extents) * bound_radius_scale * 0.25 + source[0xc4]``.
    Equality remains in the priority partition; only a strictly greater
    distance defers the source.
    """

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    reference = _float3(
        manager_reference_position, 'Manager priority reference position')
    matrix = np.asarray(source.transform_matrix, dtype=np.float32)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Manager candidate transform must be a finite float4x4')
    extents = _float3(source.bound_extents, 'Manager bound extents')
    radius_scale = _finite_float32(
        source.bound_radius_scale, 'Manager bound radius scale')
    padding = _finite_float32(
        source.priority_distance_padding, 'Manager priority distance padding')
    if radius_scale < 0 or np.any(extents < 0):
        raise ValueError('Manager candidate bound sizes must be nonnegative')

    flags = _bounded_integer(
        source.runtime_flags, 0, 0xffffffff,
        'Manager candidate runtime flags')
    if not flags & (1 << 21):
        return False

    delta_x = np.float32(matrix[3, 0] - reference[0])
    delta_y = np.float32(matrix[3, 1] - reference[1])
    delta_z = np.float32(matrix[3, 2] - reference[2])
    distance_squared = np.float32(
        np.float32(np.float32(delta_y * delta_y)
                   + np.float32(delta_x * delta_x))
        + np.float32(delta_z * delta_z))
    radius = np.maximum(extents[2], extents[1])
    radius = np.maximum(radius, extents[0])
    radius = np.float32(np.float32(radius) * radius_scale)
    radius = np.float32(radius * LIGHT_MANAGER_PRIORITY_RADIUS_FACTOR)
    radius = np.float32(radius + padding)
    radius_squared = np.float32(radius * radius)
    return bool(distance_squared > radius_squared)


def light_manager_resource_chain_ready(nodes) -> bool:
    """Reproduce resource predicate ``0x1412B7250`` for a resolved chain.

    Retail visits the source and every parent returned by ``0x1412B5FF0``.
    Any node with bits 5..7 set at ``+0x5c`` rejects the source. Type 0 also
    rejects byte ``+0x80`` bit 0, while type 5 rejects byte ``+0x170`` bit 0.
    A null parent ends the walk successfully; callers provide that already
    resolved source-to-root order here.
    """

    chain = tuple(nodes)
    if not chain:
        raise ValueError('Manager resource readiness chain must not be empty')
    for node in chain:
        if not isinstance(node, LightManagerResourceReadinessNode):
            raise ValueError(
                'Manager resource readiness chain contains an invalid node')
        flags = _bounded_integer(
            node.resource_flags, 0, 0xffffffff,
            'Manager resource flags')
        resource_type = _bounded_integer(
            node.resource_type, 0, 0xff,
            'Manager resource type')
        state = _bounded_integer(
            node.type_state_flags, 0, 0xff,
            'Manager resource type-state flags')
        if flags & 0xe0:
            return False
        if resource_type in (0, 5) and state & 1:
            return False
    return True


def light_manager_object_visibility(nodes, visibility_mask: int) -> bool:
    """Reproduce ``0x1412B5010`` for an already resolved handle chain.

    A type-5 node with a populated object requires its visibility byte to
    intersect ``visibility_mask``. Runtime flag bit 11 follows the next
    generation-checked handle; a missing/invalid handle or a node without bit
    11 terminates successfully. The caller supplies the resolved chain because
    the live global handle table is not part of the capture.
    """

    chain = tuple(nodes)
    if not chain:
        raise ValueError('Manager object visibility chain must not be empty')
    mask = _bounded_integer(
        visibility_mask, 0, 0xff, 'Manager object visibility mask')
    for node in chain:
        if not isinstance(node, LightManagerObjectVisibilityNode):
            raise ValueError(
                'Manager object visibility chain contains an invalid node')
        flags = _bounded_integer(
            node.resource_flags, 0, 0xffffffff,
            'Manager object visibility resource flags')
        resource_type = _bounded_integer(
            node.resource_type, 0, 0xff,
            'Manager object visibility resource type')
        visibility = node.type_5_visibility_bits
        if visibility is not None:
            visibility = _bounded_integer(
                visibility, 0, 0xff,
                'Manager type-5 object visibility bits')
        if (resource_type == 5 and visibility is not None
                and not visibility & mask):
            return False
        if not flags & (1 << 11):
            return True
    return True


def light_manager_type_resource_available(
        handle: int, table: LightManagerTypeResourceTable) -> bool:
    """Resolve the type-2 resource handle read from source offset ``+0xc0``.

    The high handle byte is a nonzero generation and the low 24 bits index the
    global 16-byte-entry table. Retail accepts only an in-range, present entry
    with the same generation and resource type 2.
    """

    identifier = _bounded_integer(
        handle, 0, 0xffffffff, 'Manager type-resource handle')
    if not isinstance(table, LightManagerTypeResourceTable):
        raise ValueError('table must be LightManagerTypeResourceTable')
    generation = identifier >> 24
    if identifier == 0 or generation == 0:
        return False
    index = identifier & 0xffffff
    if index >= len(table.entries):
        return False
    entry = table.entries[index]
    if entry is None:
        return False
    if not isinstance(entry, LightManagerTypeResourceEntry):
        raise ValueError('Manager type-resource table contains an invalid entry')
    entry_generation = _bounded_integer(
        entry.generation, 0, 0xff, 'Manager type-resource generation')
    resource_type = _bounded_integer(
        entry.resource_type, 0, 0xff, 'Manager type-resource type')
    if not isinstance(entry.present, (bool, np.bool_)):
        raise ValueError('Manager type-resource presence must be boolean')
    return bool(
        entry.present and generation == entry_generation
        and resource_type == 2)


def light_manager_auxiliary_volume_visible(
        plane_coefficients, source_transform_matrix, vertices) -> bool:
    """Reproduce the 16-plane vertex classifier at ``0x141604440``.

    The input is 16 world-space plane equations, the source's row-major 4x4
    transform and its float3 vertex stream. Retail transforms each plane into
    source-local space using binary32 paired sums. It then ANDs the sign bits
    of all 16 plane distances across vertices. The source is accepted as soon
    as that mask becomes zero; an empty stream or any plane that remains
    negative for every vertex rejects it.
    """

    planes = np.asarray(plane_coefficients, dtype=np.float32)
    matrix = np.asarray(source_transform_matrix, dtype=np.float32)
    points = np.asarray(vertices, dtype=np.float32)
    if planes.shape != (16, 4) or not np.isfinite(planes).all():
        raise ValueError(
            'Manager auxiliary-volume planes must be a finite 16x4 array')
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError(
            'Manager auxiliary-volume transform must be a finite float4x4')
    if (points.ndim != 2 or points.shape[1:] != (3,)
            or not np.isfinite(points).all()):
        raise ValueError(
            'Manager auxiliary-volume vertices must be a finite Nx3 array')
    if not len(points):
        return False

    local_planes = np.empty((16, 4), dtype=np.float32)
    for plane_index in range(16):
        plane = planes[plane_index]
        for row in range(4):
            high = np.float32(
                np.float32(plane[3] * matrix[row, 3])
                + np.float32(plane[2] * matrix[row, 2]))
            low = np.float32(
                np.float32(plane[1] * matrix[row, 1])
                + np.float32(plane[0] * matrix[row, 0]))
            local_planes[plane_index, row] = np.float32(high + low)

    outside_mask = np.ones(16, dtype=np.bool_)
    for point in points:
        negative = np.empty(16, dtype=np.bool_)
        for plane_index, plane in enumerate(local_planes):
            distance = np.float32(
                np.float32(
                    np.float32(
                        np.float32(point[0] * plane[0]) + plane[3])
                    + np.float32(point[1] * plane[1]))
                + np.float32(point[2] * plane[2]))
            negative[plane_index] = np.signbit(distance)
        outside_mask &= negative
        if not np.any(outside_mask):
            return True
    return False


def build_light_manager_secondary_merge(
        candidates, camera_position, *, primary_indices, secondary_indices,
        secondary_layer_bit: int) -> LightManagerSecondaryMerge:
    """Reproduce the distance-ordered secondary merge in ``0x1410BA710``.

    Eligible secondary pointers are sorted by ascending squared center
    distance.  Processed entries receive runtime bit 29. Duplicates receive
    bit 31; new entries receive bit 30 and append until the 512-pointer cap.
    Equal-distance groups expose the remaining native sort permutation.
    """

    items = tuple(candidates)
    if not all(isinstance(item, LightManagerCandidateSource) for item in items):
        raise ValueError(
            'candidates must contain LightManagerCandidateSource entries')
    camera = _float3(camera_position, 'Manager camera position')
    layer_bit = _bounded_integer(
        secondary_layer_bit, 1, 0xffffffff, 'Secondary layer bit')

    def checked_indices(values, description):
        result = tuple(
            _bounded_integer(value, 0, len(items) - 1, description)
            for value in values)
        if len(set(result)) != len(result):
            raise ValueError(f'{description} entries must be unique')
        return result

    primary = checked_indices(primary_indices, 'Primary source index')
    secondary = checked_indices(secondary_indices, 'Secondary source index')
    if len(primary) > 0x200:
        raise ValueError('Primary manager source count exceeds native 512 cap')

    scored = []
    for index in secondary:
        source = items[index]
        score = light_manager_secondary_distance_squared(source, camera)
        flags = _bounded_integer(
            source.runtime_flags, 0, 0xffffffff,
            'Manager candidate runtime flags')
        selection_mask = _bounded_integer(
            source.selection_layer_mask, 0, 0xffffffff,
            'Manager candidate selection layer mask')
        eligible = (
            not flags & 0x01810010
            and bool(flags & (1 << 2))
            and bool(selection_mask & layer_bit)
        )
        if eligible:
            scored.append((index, score))
    scored.sort(key=lambda entry: float(entry[1]))
    eligible = tuple(index for index, _score in scored)

    equal_groups = []
    start = 0
    while start < len(scored):
        end = start + 1
        while end < len(scored) and scored[end][1] == scored[start][1]:
            end += 1
        if end - start > 1:
            equal_groups.append(tuple(index for index, _score in scored[start:end]))
        start = end

    merged = list(primary)
    merged_set = set(primary)
    processed = []
    appended = []
    duplicates = []
    updates = []
    for index in eligible:
        if len(merged) >= 0x200:
            break
        processed.append(index)
        flags = _bounded_integer(
            items[index].runtime_flags, 0, 0xffffffff,
            'Manager candidate runtime flags') | (1 << 29)
        if index in merged_set:
            flags |= 1 << 31
            duplicates.append(index)
        else:
            flags |= 1 << 30
            merged.append(index)
            merged_set.add(index)
            appended.append(index)
        updates.append((index, flags))

    return LightManagerSecondaryMerge(
        merged_indices=tuple(merged),
        eligible_secondary_indices=eligible,
        processed_secondary_indices=tuple(processed),
        appended_secondary_indices=tuple(appended),
        duplicate_secondary_indices=tuple(duplicates),
        runtime_flag_updates=tuple(updates),
        equal_distance_groups=tuple(equal_groups),
    )


def evaluate_light_manager_frame_partition(
        source: LightManagerCandidateSource, *, frame_layer_bit: int,
        callback_inputs: LightManagerPartitionInputs | None = None,
        require_runtime_flag_16_for_priority: bool = False,
        manager_reference_position=None,
        ) -> LightManagerPartitionDecision:
    """Reproduce the priority/deferred/skip gates at ``0x1410BAD40``.

    Calls whose owning view or resource objects are outside the source record
    enter through ``callback_inputs``.  Their placement in the decision order
    is exact even though their producers remain external to this CPU helper.
    """

    if not isinstance(source, LightManagerCandidateSource):
        raise ValueError('source must be one LightManagerCandidateSource')
    inputs = callback_inputs or LightManagerPartitionInputs()
    if not isinstance(inputs, LightManagerPartitionInputs):
        raise ValueError(
            'callback_inputs must be LightManagerPartitionInputs or None')
    for value, description in (
            (inputs.object_visibility_result, 'object visibility result'),
            (inputs.resource_ready_result, 'resource ready result'),
            (inputs.type_resource_available, 'type resource availability'),
            (inputs.auxiliary_volume_result, 'auxiliary volume result'),
            (require_runtime_flag_16_for_priority,
             'runtime-flag-16 priority gate')):
        if not isinstance(value, (bool, np.bool_)):
            raise ValueError(f'Manager {description} must be boolean')
    if (inputs.runtime_flag_21_defer_result is not None
            and not isinstance(inputs.runtime_flag_21_defer_result,
                               (bool, np.bool_))):
        raise ValueError(
            'Manager runtime-flag-21 defer result must be boolean or None')
    if inputs.resource_readiness_chain is not None:
        chain = tuple(inputs.resource_readiness_chain)
        if not chain or not all(
                isinstance(item, LightManagerResourceReadinessNode)
                for item in chain):
            raise ValueError(
                'Manager resource readiness chain must contain valid nodes')
    else:
        chain = None
    if inputs.object_visibility_chain is not None:
        visibility_chain = tuple(inputs.object_visibility_chain)
        if not visibility_chain or not all(
                isinstance(item, LightManagerObjectVisibilityNode)
                for item in visibility_chain):
            raise ValueError(
                'Manager object visibility chain must contain valid nodes')
    else:
        visibility_chain = None
    visibility_mask = _bounded_integer(
        inputs.object_visibility_mask, 0, 0xff,
        'Manager object visibility mask')
    if ((inputs.type_resource_handle is None)
            != (inputs.type_resource_table is None)):
        raise ValueError(
            'Manager type-resource handle and table must be supplied together')
    if ((inputs.auxiliary_volume_plane_coefficients is None)
            != (inputs.auxiliary_volume_vertices is None)):
        raise ValueError(
            'Manager auxiliary-volume planes and vertices must be supplied together')

    layer_bit = _bounded_integer(
        frame_layer_bit, 1, 0xffffffff, 'Manager frame layer bit')
    flags = _bounded_integer(
        source.runtime_flags, 0, 0xffffffff,
        'Manager candidate runtime flags')
    resource_flags = _bounded_integer(
        source.resource_flags, 0, 0xffffffff,
        'Manager candidate resource flags')
    selection_mask = _bounded_integer(
        source.selection_layer_mask, 0, 0xffffffff,
        'Manager candidate selection layer mask')
    priority_mask = _bounded_integer(
        source.priority_layer_mask, 0, 0xffffffff,
        'Manager candidate priority layer mask')
    priority_class = _bounded_integer(
        source.priority_class, 0, 0xff,
        'Manager candidate priority class')
    light_type = _bounded_integer(
        source.light_type, 0, 0xff, 'Manager candidate light type')
    resource_count = _bounded_integer(
        source.auxiliary_resource_count, 0, 0xffffffff,
        'Manager candidate auxiliary resource count')
    if not isinstance(source.has_auxiliary_resource, (bool, np.bool_)):
        raise ValueError(
            'Manager candidate auxiliary-resource presence must be boolean')

    def result(membership, reason):
        return LightManagerPartitionDecision(membership, reason)

    if resource_flags & (1 << 11):
        object_visible = (
            light_manager_object_visibility(visibility_chain, visibility_mask)
            if visibility_chain is not None
            else inputs.object_visibility_result)
        if not object_visible:
            return result('skipped', 'object_visibility')
    resource_ready = (
        light_manager_resource_chain_ready(chain)
        if chain is not None else inputs.resource_ready_result)
    if not resource_ready:
        return result('skipped', 'resource_not_ready')
    if not selection_mask & layer_bit:
        return result('skipped', 'selection_layer_mask')

    bypass_auxiliary = bool(flags & (1 << 31))
    type_resource_available = (
        light_manager_type_resource_available(
            inputs.type_resource_handle, inputs.type_resource_table)
        if inputs.type_resource_table is not None
        else inputs.type_resource_available)
    type_uses_auxiliary = light_type in (1, 2) or type_resource_available
    if (not bypass_auxiliary and type_uses_auxiliary
            and source.has_auxiliary_resource and resource_count):
        if inputs.auxiliary_volume_vertices is not None:
            vertices = np.asarray(
                inputs.auxiliary_volume_vertices, dtype=np.float32)
            if vertices.ndim != 2 or len(vertices) != resource_count:
                raise ValueError(
                    'Manager auxiliary-volume vertex count must match source')
            auxiliary_visible = light_manager_auxiliary_volume_visible(
                inputs.auxiliary_volume_plane_coefficients,
                source.transform_matrix, vertices)
        else:
            auxiliary_visible = inputs.auxiliary_volume_result
        if not auxiliary_visible:
            return result('skipped', 'auxiliary_volume')

    if priority_class == 0:
        return result('deferred', 'priority_class_zero')
    if not priority_mask & layer_bit:
        return result('deferred', 'priority_layer_mask')
    if require_runtime_flag_16_for_priority and not flags & (1 << 16):
        return result('deferred', 'runtime_flag_16_clear')
    if flags & (1 << 21):
        defer_result = inputs.runtime_flag_21_defer_result
        if defer_result is None:
            if manager_reference_position is None:
                raise ValueError(
                    'Manager reference position is required for runtime flag 21')
            defer_result = light_manager_runtime_flag_21_defer(
                source, manager_reference_position)
        if defer_result:
            return result('deferred', 'runtime_flag_21_gate')
    return result('priority', None)


def build_light_manager_frame_partition(
        candidates, merged_indices, *, frame_layer_bit: int,
        callback_inputs=None,
        require_runtime_flag_16_for_priority: bool = False,
        manager_reference_position=None,
        ) -> LightManagerFramePartition:
    """Partition an explicit merged manager list in its native source order."""

    items = tuple(candidates)
    if not all(isinstance(item, LightManagerCandidateSource) for item in items):
        raise ValueError(
            'candidates must contain LightManagerCandidateSource entries')
    indices = tuple(
        _bounded_integer(value, 0, len(items) - 1, 'Merged source index')
        for value in merged_indices)
    if len(set(indices)) != len(indices):
        raise ValueError('Merged source index entries must be unique')
    if len(indices) > 0x200:
        raise ValueError('Merged manager source count exceeds native 512 cap')
    if callback_inputs is None:
        inputs = (LightManagerPartitionInputs(),) * len(indices)
    else:
        inputs = tuple(callback_inputs)
        if len(inputs) != len(indices):
            raise ValueError(
                'Partition callback-input count must match merged sources')

    priority = []
    deferred = []
    skipped = []
    decisions = []
    for index, external in zip(indices, inputs):
        decision = evaluate_light_manager_frame_partition(
            items[index], frame_layer_bit=frame_layer_bit,
            callback_inputs=external,
            require_runtime_flag_16_for_priority=(
                require_runtime_flag_16_for_priority),
            manager_reference_position=manager_reference_position,
        )
        decisions.append((index, decision))
        if decision.membership == 'priority':
            priority.append(index)
        elif decision.membership == 'deferred':
            deferred.append(index)
        else:
            skipped.append(index)
    return LightManagerFramePartition(
        priority_indices=tuple(priority),
        deferred_indices=tuple(deferred),
        skipped_indices=tuple(skipped),
        decisions=tuple(decisions),
    )


def _retail_sort_light_manager_priority_records(records):
    """Return records in the exact finite-float32 order of retail's sorter.

    The native generic sort at ``0x141599440`` uses insertion sort below seven
    records and a Bentley-McIlroy three-way partition otherwise.  Its pivot is
    the middle record at seven, median-of-three above seven, and a
    pseudomedian-of-nine above forty.  Equal records therefore have a
    deterministic but intentionally unstable permutation.
    """

    values = list(records)

    def compare(left, right):
        left_score = np.float32(left[1])
        right_score = np.float32(right[1])
        if right_score > left_score:
            return 1
        if right_score < left_score:
            return -1
        return 0

    def median_of_three(left, middle, right):
        if compare(values[left], values[middle]) < 0:
            if compare(values[middle], values[right]) < 0:
                return middle
            return right if compare(values[left], values[right]) < 0 else left
        if compare(values[middle], values[right]) > 0:
            return middle
        return left if compare(values[left], values[right]) < 0 else right

    def swap_ranges(left, right, count):
        for offset in range(count):
            values[left + offset], values[right + offset] = (
                values[right + offset], values[left + offset])

    def sort_range(begin, count):
        if count < 7:
            end = begin + count
            for current in range(begin + 1, end):
                scan = current
                while (scan > begin and
                       compare(values[scan - 1], values[scan]) > 0):
                    values[scan - 1], values[scan] = (
                        values[scan], values[scan - 1])
                    scan -= 1
            return

        middle = begin + count // 2
        if count > 7:
            left = begin
            right = begin + count - 1
            if count > 40:
                step = count // 8
                left = median_of_three(
                    left, left + step, left + 2 * step)
                middle = median_of_three(
                    middle - step, middle, middle + step)
                right = median_of_three(
                    right - 2 * step, right - step, right)
            middle = median_of_three(left, middle, right)

        values[begin], values[middle] = values[middle], values[begin]
        equal_left = scan_left = begin + 1
        scan_right = equal_right = begin + count - 1
        while True:
            while scan_left <= scan_right:
                result = compare(values[scan_left], values[begin])
                if result > 0:
                    break
                if result == 0:
                    values[equal_left], values[scan_left] = (
                        values[scan_left], values[equal_left])
                    equal_left += 1
                scan_left += 1
            while scan_left <= scan_right:
                result = compare(values[scan_right], values[begin])
                if result < 0:
                    break
                if result == 0:
                    values[scan_right], values[equal_right] = (
                        values[equal_right], values[scan_right])
                    equal_right -= 1
                scan_right -= 1
            if scan_left > scan_right:
                break
            values[scan_left], values[scan_right] = (
                values[scan_right], values[scan_left])
            scan_left += 1
            scan_right -= 1

        left_equal_count = min(
            equal_left - begin, scan_left - equal_left)
        swap_ranges(
            begin, scan_left - left_equal_count, left_equal_count)
        right_equal_count = min(
            equal_right - scan_right,
            begin + count - equal_right - 1,
        )
        swap_ranges(
            scan_left, begin + count - right_equal_count,
            right_equal_count)

        left_count = scan_left - equal_left
        right_count = equal_right - scan_right
        if left_count > 1:
            sort_range(begin, left_count)
        if right_count > 1:
            sort_range(begin + count - right_count, right_count)

    sort_range(0, len(values))
    return values

def build_light_manager_frame_source_order(
        candidates, camera_position, *, priority_indices, deferred_indices,
        count_special_allocation_class_3: bool = True,
        ) -> LightManagerFrameSourceOrder:
    """Build the proven final source order from manager partition outputs.

    Function ``0x1410BA710`` ranks the priority partition by descending
    ``light_manager_frame_priority`` through retail's generic sorter and then
    appends the deferred partition unchanged.  The preceding
    visibility/resource partition remains an explicit input here.
    ``equal_score_groups`` records each group in its exact deterministic native
    permutation.
    """

    items = tuple(candidates)
    if not all(isinstance(item, LightManagerCandidateSource) for item in items):
        raise ValueError(
            'candidates must contain LightManagerCandidateSource entries')
    camera = _float3(camera_position, 'Manager camera position')
    if not isinstance(count_special_allocation_class_3, (bool, np.bool_)):
        raise ValueError(
            'count_special_allocation_class_3 must be boolean')

    def checked_indices(values, description):
        result = tuple(
            _bounded_integer(value, 0, len(items) - 1, description)
            for value in values)
        if len(set(result)) != len(result):
            raise ValueError(f'{description} entries must be unique')
        return result

    priority = checked_indices(priority_indices, 'Priority source index')
    deferred = checked_indices(deferred_indices, 'Deferred source index')
    if set(priority).intersection(deferred):
        raise ValueError('Priority and deferred source indices must be disjoint')
    if len(priority) + len(deferred) > 0x200:
        raise ValueError('Manager frame source count exceeds native 512 cap')

    scored = [
        (index, light_manager_frame_priority(items[index], camera))
        for index in priority
    ]
    scored = _retail_sort_light_manager_priority_records(scored)
    ordered_priority = tuple(index for index, _score in scored)
    ordered_scores = tuple(float(score) for _index, score in scored)

    equal_groups = []
    start = 0
    while start < len(scored):
        end = start + 1
        while end < len(scored) and scored[end][1] == scored[start][1]:
            end += 1
        if end - start > 1:
            equal_groups.append(tuple(index for index, _score in scored[start:end]))
        start = end

    weighted_count = 0
    special_count = 0
    for index in ordered_priority:
        source = items[index]
        light_type = _bounded_integer(
            source.light_type, 0, 0xff, 'Manager candidate light type')
        special_class = _bounded_integer(
            source.special_allocation_class, 0, 0xff,
            'Manager candidate special allocation class')
        weighted_count += 6 if light_type == 0 else 1
        if count_special_allocation_class_3 and special_class == 3:
            special_count += 1

    return LightManagerFrameSourceOrder(
        priority_indices=ordered_priority,
        deferred_indices=deferred,
        frame_indices=ordered_priority + deferred,
        priority_scores=ordered_scores,
        weighted_allocation_count=weighted_count,
        special_allocation_count=special_count,
        equal_score_groups=tuple(equal_groups),
    )


def build_light_gpu_base_record(
        source: LightGpuBaseSource, *, z_bin_scale: float) -> np.void:
    """Pack one exact 128-byte record along retail's verified base path.

    Executable function ``0x1410A9710`` writes these fields to the selected
    mapped ``LightSB`` tier. It can also append ``LightVolumeGpu`` records and
    patch their ranges into this result. This helper intentionally accepts only
    subtype 1 with no auxiliary references. Z limits use the native float32
    multiply/floor rule, with the maximum stored inclusively after adding one.
    """
    if not isinstance(source, LightGpuBaseSource):
        raise ValueError('source must be one LightGpuBaseSource')

    axis_x = _float3(source.world_axis_x, 'LightGpu world axis X')
    axis_y = _float3(source.world_axis_y, 'LightGpu world axis Y')
    axis_z = _float3(source.world_axis_z, 'LightGpu world axis Z')
    position = _float3(source.world_position, 'LightGpu world position')
    color = _float3(source.linear_color, 'LightGpu linear color')
    cone = np.asarray(source.cone_parameters, dtype=np.float32)
    if cone.shape != (2,) or not np.isfinite(cone).all():
        raise ValueError('LightGpu cone parameters must be a finite float2')

    radius = _finite_float32(source.bulb_radius, 'LightGpu bulb radius')
    length = _finite_float32(source.bulb_length, 'LightGpu bulb length')
    push = _finite_float32(
        source.bulb_push_forward, 'LightGpu bulb push-forward')
    attenuation_radius = _finite_float32(
        source.attenuation_radius, 'LightGpu attenuation radius')
    specular = _finite_float32(
        source.specular_intensity, 'LightGpu specular intensity')
    cut_on = _finite_float32(source.cut_on_depth, 'LightGpu cut-on depth')
    cut_off = _finite_float32(source.cut_off_depth, 'LightGpu cut-off depth')
    z_min = _finite_float32(
        source.z_bin_min_depth, 'LightGpu Z-bin minimum depth')
    z_max = _finite_float32(
        source.z_bin_max_depth, 'LightGpu Z-bin maximum depth')
    z_scale = _finite_float32(z_bin_scale, 'LightGpu Z-bin scale')
    reciprocal_cone_sine = _finite_float32(
        source.reciprocal_cone_sine, 'LightGpu reciprocal cone sine')
    fog = _finite_float32(source.volumetric_fog, 'LightGpu volumetric fog')

    if length < 0:
        raise ValueError('LightGpu bulb length must be nonnegative')
    if attenuation_radius < 0:
        raise ValueError('LightGpu attenuation radius must be nonnegative')
    if z_scale <= 0:
        raise ValueError('LightGpu Z-bin scale must be positive')
    if z_max < z_min:
        raise ValueError('LightGpu Z-bin maximum must not precede its minimum')

    subtype = int(source.light_subtype)
    if subtype != 1:
        raise ValueError(
            'LightGpu base packing currently requires captured subtype 1')
    radiance_mode = int(source.radiance_mode)
    if radiance_mode not in (0, 1, 2):
        raise ValueError('LightGpu radiance mode must be 0, 1, or 2')
    base_flags = int(source.base_bit_flags)
    if base_flags < 0 or base_flags > 0xffff:
        raise ValueError('LightGpu base flags must fit the low 16 bits')

    # The legacy negative-radius encoding changes representation only when its
    # diameter exceeds the stored segment length. Retail swaps X/Y, negates the
    # old X axis, stores ``-oldLength / 2`` as the radius, and stores the old
    # diameter as the new length. Otherwise it preserves the negative radius.
    if radius < 0:
        diameter = np.abs(np.float32(radius + radius))
        if diameter > length:
            old_axis_x = axis_x.copy()
            axis_x = axis_y.copy()
            axis_y = np.asarray(-old_axis_x, dtype=np.float32)
            radius = np.float32(length * np.float32(-.5))
            length = diameter

    if radiance_mode == 2:
        color = np.asarray(
            color * LIGHT_GPU_RADIANCE_COLOR_SCALE, dtype=np.float32)
        specular = np.float32(
            specular * LIGHT_GPU_RADIANCE_SPECULAR_SCALE)
    elif radiance_mode == 1:
        specular = np.float32(0)

    # Native cvttss2si plus its negative-fraction correction is floorf. The
    # upper limit is incremented before packing, and both shader comparisons
    # are inclusive afterward.
    minimum = int(np.floor(np.float32(z_scale * z_min)))
    maximum = int(np.floor(np.float32(z_scale * z_max))) + 1
    if minimum < 0 or maximum < 0 or minimum > 0xffff or maximum > 0xffff:
        raise ValueError('LightGpu packed Z-bin limits must fit uint16')

    with np.errstate(over='ignore', invalid='ignore'):
        fog_half = np.float16(fog)
    if not np.isfinite(fog_half):
        raise ValueError('LightGpu volumetric fog must be representable as float16')
    fog_bits = int(np.asarray([fog_half], '<f2').view('<u2')[0])
    low_flags = base_flags
    if bool(source.flag_103_bit0):
        low_flags |= 1 << 2
    if bool(source.flag_105):
        low_flags |= 1 << 6
    if bool(source.flag_104):
        low_flags |= 1 << 4

    result = np.zeros(1, dtype=LIGHT_GPU_DTYPE)
    record = result[0]
    record['world_axis_x'] = axis_x
    record['bulb_radius'] = radius
    record['world_axis_y'] = axis_y
    record['bulb_length'] = length
    record['world_axis_z'] = axis_z
    record['bulb_push_forward'] = push
    record['world_position'] = position
    record['inverse_attenuation_radius'] = np.float32(
        np.float32(1) / np.maximum(
            attenuation_radius, LIGHT_GPU_ATTENUATION_RADIUS_FLOOR))
    record['linear_color'] = color
    record['specular_intensity'] = specular
    record['cone_parameters'] = cone
    record['cut_on_depth'] = cut_on
    record['cut_off_depth'] = cut_off
    record['z_bin_min_max'] = np.uint32((maximum << 16) | minimum)
    record['bit_flags_vfog'] = np.uint32((fog_bits << 16) | low_flags)
    record['mod_id_and_gobo_id'] = np.uint32(0xffffffff)
    record['clip_volume_info'] = np.uint32(0)
    record['shadow_map_info'] = np.uint32(0)
    record['shadow_volume_info'] = np.uint32(0)
    record['reciprocal_cone_sine'] = reciprocal_cone_sine
    record['padding'] = np.float32(0)
    return record


def build_light_volume_gpu_record(source: LightVolumeGpuSource) -> np.void:
    """Pack one exact 128-byte ``LightVolumeGpu`` from explicit fields."""

    if not isinstance(source, LightVolumeGpuSource):
        raise ValueError('source must be one LightVolumeGpuSource')
    matrix = np.asarray(source.transform_matrix, dtype=np.float32)
    atlas = np.asarray(source.atlas_coordinates, dtype=np.float32)
    extents = np.asarray(source.extents, dtype=np.float32)
    negative = np.asarray(source.falloff_negative, dtype=np.float32)
    positive = np.asarray(source.falloff_positive, dtype=np.float32)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('LightVolumeGpu transform must be a finite float4x4')
    if atlas.shape != (4,) or not np.isfinite(atlas).all():
        raise ValueError('LightVolumeGpu atlas coordinates must be a finite float4')
    for value, description in (
            (extents, 'extents'), (negative, 'negative falloff'),
            (positive, 'positive falloff')):
        if value.shape != (3,) or not np.isfinite(value).all():
            raise ValueError(f'LightVolumeGpu {description} must be a finite float3')
    fade = _finite_float32(source.fade, 'LightVolumeGpu fade')
    texel = _finite_float32(
        source.shadow_texel_scale, 'LightVolumeGpu shadow texel scale')
    misc = _finite_float32(source.misc, 'LightVolumeGpu misc')

    result = np.zeros(1, dtype=LIGHT_VOLUME_GPU_DTYPE)
    record = result[0]
    record['transform_matrix'] = matrix
    record['atlas_coordinates'] = atlas
    record['extents'] = extents
    record['fade'] = fade
    record['falloff_negative'] = negative
    record['shadow_texel_scale'] = texel
    record['falloff_positive'] = positive
    record['misc'] = misc
    return record


def build_primary_clip_light_volume_record(
        persistent_affine_columns) -> np.void:
    """Reproduce ``0x1410A9A09..0x1410A9B15``'s clip record.

    The persistent record stores three consecutive float4 columns at
    ``+0x40..+0x6F``. Retail transposes those twelve values into the first
    three columns of the auxiliary float4x4 and leaves every other field zero.
    """

    columns = np.asarray(persistent_affine_columns, dtype=np.float32)
    if columns.shape != (3, 4) or not np.isfinite(columns).all():
        raise ValueError(
            'Primary clip affine columns must be a finite 3x4 float array')
    matrix = np.zeros((4, 4), dtype=np.float32)
    matrix[:, :3] = columns.T
    return build_light_volume_gpu_record(LightVolumeGpuSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
    ))


def _bounded_integer(value, minimum: int, maximum: int,
                     description: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f'{description} must be an integer') from error
    if isinstance(value, (bool, np.bool_)) or result != value:
        raise ValueError(f'{description} must be an integer')
    if result < minimum or result > maximum:
        raise ValueError(
            f'{description} must be in [{minimum}, {maximum}]')
    return result


def _atlas_allocation_words(
        source: LightAtlasAllocationWords) -> tuple[int, int, int, int]:
    if not isinstance(source, LightAtlasAllocationWords):
        raise ValueError('Atlas allocation must be LightAtlasAllocationWords')
    return tuple(_bounded_integer(value, 0, 0xffff,
                                  f'Atlas allocation word {offset}')
                 for offset, value in zip((0, 2, 4, 6), (
                     source.word_0, source.word_2,
                     source.word_4, source.word_6)))


def resolve_light_atlas_handle(
        table: LightAtlasHandleTable, handle: int,
        ) -> LightAtlasAllocationWords:
    """Reproduce the 32-bit atlas-handle lookup at ``0x1410C42B0``.

    Invalid handles return the all-zero allocation written by retail. A valid
    handle whose uint16 index is outside the supplied table violates the native
    manager invariant and is rejected instead of reading beyond Python memory.
    """

    if not isinstance(table, LightAtlasHandleTable):
        raise ValueError('table must be LightAtlasHandleTable')
    generation = _bounded_integer(
        table.generation_word, 0, 0xffffffff,
        'Atlas handle-table generation word')
    identifier = _bounded_integer(handle, 0, 0xffffffff, 'Atlas handle')
    zero = LightAtlasAllocationWords(0, 0, 0, 0)
    if not identifier & 0x80000000:
        return zero
    if ((identifier >> 16) ^ generation) & 0xff:
        return zero
    index = identifier & 0xffff
    if index >= len(table.allocations):
        raise ValueError('Valid atlas handle index is outside the supplied table')
    allocation = table.allocations[index]
    _atlas_allocation_words(allocation)
    return allocation


def _native_positive_divide(numerator: np.float32,
                            denominator: np.float32) -> np.float32:
    """Reproduce ``0x1410C6A20``'s positive-denominator division."""

    if denominator > np.float32(0):
        return np.float32(numerator / denominator)
    return np.float32(0)


def build_projected_shadow_map_light_volume_record(
        source: LightProjectedShadowMapSource) -> np.void:
    """Build the projected branch used by subtype-1 shadow-map slots."""

    if not isinstance(source, LightProjectedShadowMapSource):
        raise ValueError('source must be one LightProjectedShadowMapSource')
    matrix = np.asarray(source.transform_matrix, dtype=np.float32)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Projected-shadow transform must be a finite float4x4')
    word_0, word_2, word_4, word_6 = _atlas_allocation_words(
        source.atlas_allocation)
    numerator = _finite_float32(
        source.shadow_texel_numerator, 'Projected-shadow texel numerator')
    fade = _finite_float32(source.fade, 'Projected-shadow fade')
    atlas = tuple(float(np.float32(np.float32(value)
                                   * LIGHT_SHADOW_VOLUME_ATLAS_X_HALF_TEXEL))
                  for value in (word_0, word_2, word_4, word_4))
    texel = _native_positive_divide(numerator, np.float32(word_6))
    return build_light_volume_gpu_record(LightVolumeGpuSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        atlas_coordinates=atlas,
        fade=float(fade),
        shadow_texel_scale=float(texel),
    ))


def build_point_shadow_map_light_volume_record(
        source: LightPointShadowMapSource) -> np.void:
    """Reproduce ``0x1410CA750`` plus its caller's final field writes."""

    if not isinstance(source, LightPointShadowMapSource):
        raise ValueError('source must be one LightPointShadowMapSource')
    if len(source.face_atlas_allocations) != 6:
        raise ValueError('Point-shadow source must provide exactly six atlas faces')
    tail = np.asarray(source.projection_tail, dtype=np.float32)
    if tail.shape != (4,) or not np.isfinite(tail).all():
        raise ValueError('Point-shadow projection tail must be a finite float4')
    numerator = _finite_float32(
        source.shadow_texel_numerator, 'Point-shadow texel numerator')
    fade = _finite_float32(source.fade, 'Point-shadow fade')

    face_pairs = []
    denominator_sum = np.float32(0)
    valid_count = 0
    for allocation in source.face_atlas_allocations:
        word_0, word_2, word_4, word_6 = _atlas_allocation_words(allocation)
        if word_4:
            half_size = np.float32(
                np.float32(word_4) * LIGHT_SHADOW_VOLUME_ATLAS_X_HALF_TEXEL)
            pair = (
                np.float32(np.float32(word_0) + half_size),
                np.float32(np.float32(word_2) + half_size),
            )
            denominator_sum = np.float32(
                denominator_sum + np.float32(word_6))
            valid_count += 1
        else:
            pair = (
                LIGHT_SHADOW_VOLUME_ATLAS_X_HALF_TEXEL,
                LIGHT_SHADOW_VOLUME_ATLAS_X_HALF_TEXEL,
            )
        face_pairs.extend(pair)
    if valid_count > 1:
        denominator_sum = np.float32(
            denominator_sum / np.float32(valid_count))

    matrix = np.empty((4, 4), dtype=np.float32)
    matrix.reshape(-1)[:12] = np.asarray(face_pairs, dtype=np.float32)
    matrix.reshape(-1)[12:] = tail
    texel = _native_positive_divide(numerator, denominator_sum)
    return build_light_volume_gpu_record(LightVolumeGpuSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        fade=float(fade),
        shadow_texel_scale=float(texel),
    ))


def build_gobo_light_volume_record(source: LightGoboVolumeSource) -> np.void:
    """Reproduce retail's inline gobo constructor at ``0x1410A9C22``."""

    if not isinstance(source, LightGoboVolumeSource):
        raise ValueError('source must be one LightGoboVolumeSource')
    matrix = np.asarray(source.transform_matrix, dtype=np.float32)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Gobo transform must be a finite float4x4')
    origins = tuple(source.atlas_origin_texels)
    sizes = tuple(source.atlas_size_words)
    if len(origins) != 2 or len(sizes) != 2:
        raise ValueError('Gobo atlas origin and size must be integer pairs')
    origin_x = _bounded_integer(origins[0], -0x8000, 0x7fff,
                                'Gobo atlas X origin')
    origin_y = _bounded_integer(origins[1], -0x8000, 0x7fff,
                                'Gobo atlas Y origin')
    size_x_word = _bounded_integer(sizes[0], 0, 0xffff,
                                   'Gobo atlas X size word')
    size_y_word = _bounded_integer(sizes[1], 0, 0xffff,
                                   'Gobo atlas Y size word')
    size_x = size_x_word & 0x7fff
    size_y = size_y_word & 0x7fff
    if not size_x:
        raise ValueError('Gobo atlas X size must be nonzero')

    atlas_x = np.float32(
        np.float32(origin_x) * LIGHT_SHADOW_VOLUME_ATLAS_X_SCALE
        + LIGHT_SHADOW_VOLUME_ATLAS_X_HALF_TEXEL)
    atlas_width = np.float32(
        np.float32(size_x - 1) * LIGHT_SHADOW_VOLUME_ATLAS_X_SCALE)
    if (size_x_word & 0x8000) and (size_y_word & 0x8000):
        atlas_y = np.float32(
            np.float32(np.float32(origin_y + size_y) - np.float32(.5))
            * LIGHT_SHADOW_VOLUME_ATLAS_Y_SCALE)
        atlas_height = np.float32(
            np.float32(size_y - 1) * -LIGHT_SHADOW_VOLUME_ATLAS_Y_SCALE)
    else:
        atlas_y = np.float32(
            np.float32(origin_y) * LIGHT_SHADOW_VOLUME_ATLAS_Y_SCALE
            + LIGHT_SHADOW_VOLUME_ATLAS_X_SCALE)
        atlas_height = np.float32(
            np.float32(size_y - 1) * LIGHT_SHADOW_VOLUME_ATLAS_Y_SCALE)
    return build_light_volume_gpu_record(LightVolumeGpuSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        atlas_coordinates=(
            float(atlas_x), float(atlas_y),
            float(atlas_width), float(atlas_height)),
    ))


def build_color_light_volume_record(source: LightColorVolumeSource) -> np.void:
    """Reproduce subtype 4's auxiliary record at ``0x1410AA21D``."""

    if not isinstance(source, LightColorVolumeSource):
        raise ValueError('source must be one LightColorVolumeSource')
    dimensions = _float3(source.dimensions, 'Color-volume dimensions')
    negative_distances = _float3(
        source.negative_falloff_distances,
        'Color-volume negative falloff distances')
    positive_distances = _float3(
        source.positive_falloff_distances,
        'Color-volume positive falloff distances')
    fade = _finite_float32(source.fade, 'Color-volume fade')
    with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
        if bool(source.reciprocal_dimensions):
            extents = np.asarray(
                np.float32(1) / dimensions, dtype=np.float32)
            negative = np.asarray(
                -(dimensions / negative_distances), dtype=np.float32)
            positive = np.asarray(
                dimensions / positive_distances, dtype=np.float32)
        else:
            extents = dimensions.copy()
            negative = np.asarray(
                np.float32(1) / negative_distances, dtype=np.float32)
            positive = np.asarray(
                np.float32(1) / positive_distances, dtype=np.float32)
    if (not np.isfinite(extents).all() or not np.isfinite(negative).all()
            or not np.isfinite(positive).all()):
        raise ValueError('Color-volume divisors must produce finite float32 values')
    return build_light_volume_gpu_record(LightVolumeGpuSource(
        transform_matrix=((0, 0, 0, 0),) * 4,
        extents=tuple(float(value) for value in extents),
        fade=float(fade),
        falloff_negative=tuple(float(value) for value in negative),
        falloff_positive=tuple(float(value) for value in positive),
    ))


def _native_float32_product(left, right) -> np.float32:
    return np.float32(np.float32(left) * np.float32(right))


def _native_float32_sum(left, right) -> np.float32:
    return np.float32(np.float32(left) + np.float32(right))


def _native_float32_difference(left, right) -> np.float32:
    return np.float32(np.float32(left) - np.float32(right))


def _native_inverse_float3x3(matrix: np.ndarray) -> np.ndarray:
    """Reproduce cofactor helper ``0x1406BCB20..0x1406BCD7C``."""

    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    fb = _native_float32_product(f, b)
    ea = _native_float32_product(e, a)
    dc = _native_float32_product(d, c)
    fa = _native_float32_product(f, a)
    db = _native_float32_product(d, b)
    ec = _native_float32_product(e, c)
    determinant = _native_float32_sum(
        _native_float32_sum(
            _native_float32_product(ea, i),
            _native_float32_product(fb, g)),
        _native_float32_product(dc, h))
    determinant = _native_float32_difference(
        determinant, _native_float32_product(fa, h))
    determinant = _native_float32_difference(
        determinant, _native_float32_product(db, i))
    determinant = _native_float32_difference(
        determinant, _native_float32_product(ec, g))
    if determinant == np.float32(0) or np.isnan(determinant):
        return np.zeros((3, 3), dtype=np.float32)
    reciprocal = np.float32(np.float32(1) / determinant)

    def scaled_difference(left_a, left_b, right_a, right_b) -> np.float32:
        return _native_float32_product(
            _native_float32_difference(
                _native_float32_product(left_a, left_b),
                _native_float32_product(right_a, right_b)),
            reciprocal)

    return np.asarray([
        [scaled_difference(e, i, f, h), scaled_difference(h, c, i, b),
         _native_float32_product(
             _native_float32_difference(fb, ec), reciprocal)],
        [scaled_difference(g, f, i, d), scaled_difference(i, a, g, c),
         _native_float32_product(
             _native_float32_difference(dc, fa), reciprocal)],
        [scaled_difference(d, h, e, g), scaled_difference(g, b, h, a),
         _native_float32_product(
             _native_float32_difference(ea, db), reciprocal)],
    ], dtype=np.float32)


def _native_inverse_affine_matrix(matrix: np.ndarray) -> np.ndarray:
    """Reproduce affine inverse ``0x14162A8B0..0x14162AABD``."""

    inverse = np.zeros((4, 4), dtype=np.float32)
    inverse[:3, :3] = _native_inverse_float3x3(matrix[:3, :3])
    translation_bits = np.asarray(matrix[3, :3], dtype=np.float32).view(np.uint32)
    negative_translation = np.asarray(
        translation_bits ^ np.uint32(0x80000000), dtype=np.uint32,
    ).view(np.float32)
    tx, ty, tz = negative_translation
    basis = inverse[:3, :3]
    for column in range(3):
        value = _native_float32_sum(
            _native_float32_product(ty, basis[1, column]),
            _native_float32_product(tx, basis[0, column]))
        inverse[3, column] = _native_float32_sum(
            value, _native_float32_product(tz, basis[2, column]))
    inverse[3, 3] = np.float32(1)
    if not np.isfinite(inverse).all():
        raise ValueError('Native affine inverse must produce finite float32 values')
    return inverse


def build_subtype_3_clip_light_volume_record(
        source: LightSubtype3ClipVolumeSource) -> np.void:
    """Reproduce subtype 3 helper ``0x1410B9870..0x1410B9A3A``."""

    if not isinstance(source, LightSubtype3ClipVolumeSource):
        raise ValueError('source must be one LightSubtype3ClipVolumeSource')
    matrix = np.asarray(source.transform_matrix, dtype=np.float32)
    scale = _float3(source.axis_scale, 'Subtype-3 clip axis scale')
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Subtype-3 clip transform must be a finite float4x4')
    scaled = matrix.copy()
    for row in range(3):
        scaled[row] = np.asarray(
            scaled[row] * scale[row], dtype=np.float32)
    inverse = _native_inverse_affine_matrix(scaled)
    if bool(source.map_to_unit_space):
        inverse[:, :3] = np.asarray(
            inverse[:, :3] * np.float32(.5), dtype=np.float32)
        inverse[3, :3] = np.asarray(
            inverse[3, :3] + np.float32(.5), dtype=np.float32)
    return build_light_volume_gpu_record(LightVolumeGpuSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in inverse),
        fade=1.0,
    ))


def build_shadow_volume_light_volume_record(
        source: LightShadowVolumeSource) -> np.void:
    """Reproduce retail helper ``0x1410C77A0..0x1410C7895``.

    The helper clears one 128-byte destination, copies the source transform,
    converts its signed atlas origin and masked sizes with the retail atlas
    constants, then transfers fade and the four negative-plane fields.
    """

    if not isinstance(source, LightShadowVolumeSource):
        raise ValueError('source must be one LightShadowVolumeSource')
    matrix = np.asarray(source.transform_matrix, dtype=np.float32)
    negative = np.asarray(source.falloff_negative, dtype=np.float32)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Shadow-volume transform must be a finite float4x4')
    if negative.shape != (3,) or not np.isfinite(negative).all():
        raise ValueError('Shadow-volume negative falloff must be a finite float3')
    origins = tuple(source.atlas_origin_texels)
    sizes = tuple(source.atlas_size_words)
    if len(origins) != 2 or len(sizes) != 2:
        raise ValueError('Shadow-volume atlas origin and size must be integer pairs')
    origin_x = _bounded_integer(
        origins[0], -0x8000, 0x7fff, 'Shadow-volume atlas X origin')
    origin_y = _bounded_integer(
        origins[1], -0x8000, 0x7fff, 'Shadow-volume atlas Y origin')
    size_x_word = _bounded_integer(
        sizes[0], 0, 0xffff, 'Shadow-volume atlas X size word')
    size_y_word = _bounded_integer(
        sizes[1], 0, 0xffff, 'Shadow-volume atlas Y size word')
    texel = _finite_float32(
        source.shadow_texel_scale, 'Shadow-volume shadow texel scale')
    misc = _finite_float32(source.misc, 'Shadow-volume misc')
    fade = _finite_float32(source.fade, 'Shadow-volume fade')

    # Keep each native scalar operation at float32 precision. The encoded size
    # words retain only their low 15 bits before the executable subtracts one.
    atlas = np.asarray([
        np.float32(np.float32(origin_x) * LIGHT_SHADOW_VOLUME_ATLAS_X_SCALE
                   + LIGHT_SHADOW_VOLUME_ATLAS_X_HALF_TEXEL),
        np.float32(np.float32(origin_y) * LIGHT_SHADOW_VOLUME_ATLAS_Y_SCALE
                   + LIGHT_SHADOW_VOLUME_ATLAS_X_SCALE),
        np.float32(np.float32((size_x_word & 0x7fff) - 1)
                   * LIGHT_SHADOW_VOLUME_ATLAS_X_SCALE),
        np.float32(np.float32((size_y_word & 0x7fff) - 1)
                   * LIGHT_SHADOW_VOLUME_ATLAS_Y_SCALE),
    ], dtype=np.float32)
    return build_light_volume_gpu_record(LightVolumeGpuSource(
        transform_matrix=tuple(tuple(float(value) for value in row)
                               for row in matrix),
        atlas_coordinates=tuple(float(value) for value in atlas),
        fade=float(fade),
        falloff_negative=tuple(float(value) for value in negative),
        shadow_texel_scale=float(texel),
        misc=float(misc),
    ))


def build_light_gpu_subtype_1_record(
        source: LightGpuBaseSource, *, z_bin_scale: float,
        auxiliary: LightGpuSubtype1AuxiliarySources | None = None,
        first_volume_index: int = 0, volume_capacity: int = 2048,
        ) -> PackedLightGpuAuxiliaryResult:
    """Pack subtype 1 and append prepared auxiliary records in retail order.

    References use a low-half first index and high-half count.  When the
    shared auxiliary tier is full, retail skips each remaining allocation; the
    returned ``skipped_volume_count`` exposes that condition to the caller.
    """

    if auxiliary is None:
        auxiliary = LightGpuSubtype1AuxiliarySources()
    if not isinstance(auxiliary, LightGpuSubtype1AuxiliarySources):
        raise ValueError(
            'auxiliary must be LightGpuSubtype1AuxiliarySources')
    if len(auxiliary.shadow_map_volumes) > 3:
        raise ValueError('Subtype-1 packing supports at most three shadow maps')
    shadow_map_source_types = (
        LightVolumeGpuSource,
        LightProjectedShadowMapSource,
        LightPointShadowMapSource,
    )
    if (not all(isinstance(item, shadow_map_source_types)
                for item in auxiliary.shadow_map_volumes)
            or not all(isinstance(item, (
                LightVolumeGpuSource, LightShadowVolumeSource))
                       for item in auxiliary.shadow_volumes)):
        raise ValueError(
            'Auxiliary entries must use their supported light-volume source type')
    if (auxiliary.clip_volume is not None
            and not isinstance(auxiliary.clip_volume, LightVolumeGpuSource)):
        raise ValueError('Auxiliary volume entries must be LightVolumeGpuSource')
    if (auxiliary.gobo_volume is not None
            and not isinstance(auxiliary.gobo_volume, (
                LightVolumeGpuSource, LightGoboVolumeSource))):
            raise ValueError('Auxiliary volume entries must be LightVolumeGpuSource')

    start = int(first_volume_index)
    capacity = int(volume_capacity)
    if start < 0 or capacity < 0 or start > capacity or capacity > 0xffff:
        raise ValueError(
            'Light-volume indices must satisfy 0 <= first <= capacity <= 65535')

    light = build_light_gpu_base_record(source, z_bin_scale=z_bin_scale).copy()
    appended = []
    next_index = start
    skipped = 0

    def allocate(item) -> int | None:
        nonlocal next_index, skipped
        if next_index >= capacity:
            skipped += 1
            return None
        index = next_index
        if isinstance(item, LightShadowVolumeSource):
            appended.append(build_shadow_volume_light_volume_record(item))
        elif isinstance(item, LightProjectedShadowMapSource):
            appended.append(build_projected_shadow_map_light_volume_record(item))
        elif isinstance(item, LightPointShadowMapSource):
            appended.append(build_point_shadow_map_light_volume_record(item))
        elif isinstance(item, LightGoboVolumeSource):
            appended.append(build_gobo_light_volume_record(item))
        else:
            appended.append(build_light_volume_gpu_record(item))
        next_index += 1
        return index

    def allocate_range(items) -> tuple[int, int]:
        first = next_index
        count = 0
        for item in items:
            if allocate(item) is not None:
                count += 1
        return first, count

    if auxiliary.clip_volume is not None:
        index = allocate(auxiliary.clip_volume)
        if index is not None:
            light['clip_volume_info'] = np.uint32(index | (1 << 16))

    if auxiliary.gobo_volume is not None:
        index = allocate(auxiliary.gobo_volume)
        if index is not None:
            current = int(light['mod_id_and_gobo_id']) & 0xffff
            light['mod_id_and_gobo_id'] = np.uint32(current | (index << 16))
            if (isinstance(auxiliary.gobo_volume, LightGoboVolumeSource)
                    and int(auxiliary.gobo_volume.atlas_size_words[1]) & 0x8000):
                light['bit_flags_vfog'] = np.uint32(
                    int(light['bit_flags_vfog']) | (1 << 5))

    first, count = allocate_range(auxiliary.shadow_map_volumes)
    if count:
        light['shadow_map_info'] = np.uint32(first | (count << 16))
    first, count = allocate_range(auxiliary.shadow_volumes)
    if count:
        light['shadow_volume_info'] = np.uint32(first | (count << 16))

    records = np.zeros(len(appended), dtype=LIGHT_VOLUME_GPU_DTYPE)
    for index, record in enumerate(appended):
        records[index] = record
    return PackedLightGpuAuxiliaryResult(
        light=light,
        appended_volumes=records,
        next_volume_index=next_index,
        skipped_volume_count=skipped,
    )


def build_light_gpu_subtype_3_record(
        source: LightGpuBaseSource, *, z_bin_scale: float,
        auxiliary: LightGpuSubtype3AuxiliarySources,
        first_volume_index: int = 0, volume_capacity: int = 2048,
        ) -> PackedLightGpuAuxiliaryResult:
    """Pack subtype 3 through its recovered base and auxiliary branches."""

    if not isinstance(source, LightGpuBaseSource) or int(source.light_subtype) != 3:
        raise ValueError('Subtype-3 packing requires LightGpuBaseSource subtype 3')
    if not isinstance(auxiliary, LightGpuSubtype3AuxiliarySources):
        raise ValueError('auxiliary must be LightGpuSubtype3AuxiliarySources')
    if len(auxiliary.shadow_map_volumes) > 3:
        raise ValueError('Subtype-3 packing supports at most three shadow maps')
    shadow_map_source_types = (
        LightVolumeGpuSource,
        LightProjectedShadowMapSource,
        LightPointShadowMapSource,
    )
    if not all(isinstance(item, shadow_map_source_types)
               for item in auxiliary.shadow_map_volumes):
        raise ValueError('Unsupported subtype-3 shadow-map source')
    if not all(isinstance(item, (
            LightVolumeGpuSource, LightShadowVolumeSource))
            for item in auxiliary.shadow_volumes):
        raise ValueError('Unsupported subtype-3 shadow-volume source')
    if (not isinstance(auxiliary.subtype_3_clip_volume, (
            LightVolumeGpuSource, LightSubtype3ClipVolumeSource))
            or (auxiliary.clip_volume is not None
                and not isinstance(auxiliary.clip_volume, LightVolumeGpuSource))
            or (auxiliary.gobo_volume is not None
                and not isinstance(auxiliary.gobo_volume, (
                    LightVolumeGpuSource, LightGoboVolumeSource)))):
        raise ValueError('Unsupported subtype-3 auxiliary source')

    start = int(first_volume_index)
    capacity = int(volume_capacity)
    if start < 0 or capacity < 0 or start > capacity or capacity > 0xffff:
        raise ValueError(
            'Light-volume indices must satisfy 0 <= first <= capacity <= 65535')

    # The common native path is the subtype-1 base producer with a forced
    # non-spot cone pair. Subtype 3 then shifts position by axis Z * 32000 and
    # stores its subtype marker as the raw bits of inverseAttenuationRadius.
    common_source = replace(
        source, light_subtype=1, cone_parameters=(0.0, 1.0))
    light = build_light_gpu_base_record(
        common_source, z_bin_scale=z_bin_scale).copy()
    axis_z = _float3(source.world_axis_z, 'Subtype-3 position axis')
    anchor = _float3(source.world_position, 'Subtype-3 position anchor')
    for component in range(3):
        offset = _native_float32_product(axis_z[component], np.float32(32000))
        light['world_position'][component] = _native_float32_difference(
            anchor[component], offset)
    light['inverse_attenuation_radius'] = np.asarray(
        [np.uint32(3)], dtype='<u4').view('<f4')[0]

    appended = []
    next_index = start
    skipped = 0

    def build_volume(item) -> np.void:
        if isinstance(item, LightShadowVolumeSource):
            return build_shadow_volume_light_volume_record(item)
        if isinstance(item, LightProjectedShadowMapSource):
            return build_projected_shadow_map_light_volume_record(item)
        if isinstance(item, LightPointShadowMapSource):
            return build_point_shadow_map_light_volume_record(item)
        if isinstance(item, LightGoboVolumeSource):
            return build_gobo_light_volume_record(item)
        if isinstance(item, LightSubtype3ClipVolumeSource):
            return build_subtype_3_clip_light_volume_record(item)
        return build_light_volume_gpu_record(item)

    def allocate(item) -> int | None:
        nonlocal next_index, skipped
        if next_index >= capacity:
            skipped += 1
            return None
        index = next_index
        appended.append(build_volume(item))
        next_index += 1
        return index

    clip_first = next_index
    clip_count = 0
    if auxiliary.clip_volume is not None and allocate(auxiliary.clip_volume) is not None:
        clip_count += 1
    if allocate(auxiliary.subtype_3_clip_volume) is not None:
        clip_count += 1
        light['bit_flags_vfog'] = np.uint32(
            int(light['bit_flags_vfog']) | (1 << 3))
    if clip_count:
        light['clip_volume_info'] = np.uint32(
            clip_first | (clip_count << 16))

    if auxiliary.gobo_volume is not None:
        index = allocate(auxiliary.gobo_volume)
        if index is not None:
            current = int(light['mod_id_and_gobo_id']) & 0xffff
            light['mod_id_and_gobo_id'] = np.uint32(current | (index << 16))
            if (isinstance(auxiliary.gobo_volume, LightGoboVolumeSource)
                    and int(auxiliary.gobo_volume.atlas_size_words[1]) & 0x8000):
                light['bit_flags_vfog'] = np.uint32(
                    int(light['bit_flags_vfog']) | (1 << 5))

    def allocate_range(items) -> tuple[int, int]:
        first = next_index
        count = 0
        for item in items:
            if allocate(item) is not None:
                count += 1
        return first, count

    first, count = allocate_range(auxiliary.shadow_map_volumes)
    if count:
        light['shadow_map_info'] = np.uint32(first | (count << 16))
    first, count = allocate_range(auxiliary.shadow_volumes)
    if count:
        light['shadow_volume_info'] = np.uint32(first | (count << 16))

    records = np.zeros(len(appended), dtype=LIGHT_VOLUME_GPU_DTYPE)
    for index, record in enumerate(appended):
        records[index] = record
    return PackedLightGpuAuxiliaryResult(
        light=light, appended_volumes=records,
        next_volume_index=next_index, skipped_volume_count=skipped)


def build_light_gpu_subtype_4_record(
        source: LightGpuBaseSource, *, z_bin_scale: float,
        auxiliary: LightGpuSubtype4AuxiliarySources,
        first_volume_index: int = 0, volume_capacity: int = 2048,
        ) -> PackedLightGpuAuxiliaryResult:
    """Pack subtype 4 through its recovered base and auxiliary branches."""

    if not isinstance(source, LightGpuBaseSource) or int(source.light_subtype) != 4:
        raise ValueError('Subtype-4 packing requires LightGpuBaseSource subtype 4')
    if not isinstance(auxiliary, LightGpuSubtype4AuxiliarySources):
        raise ValueError('auxiliary must be LightGpuSubtype4AuxiliarySources')
    if not isinstance(auxiliary.color_volume, LightColorVolumeSource):
        raise ValueError('Subtype-4 packing requires LightColorVolumeSource')
    if len(auxiliary.shadow_map_volumes) > 3:
        raise ValueError('Subtype-4 packing supports at most three shadow maps')
    shadow_map_source_types = (
        LightVolumeGpuSource,
        LightProjectedShadowMapSource,
        LightPointShadowMapSource,
    )
    if (not all(isinstance(item, shadow_map_source_types)
                for item in auxiliary.shadow_map_volumes)
            or not all(isinstance(item, (
                LightVolumeGpuSource, LightShadowVolumeSource))
                       for item in auxiliary.shadow_volumes)):
        raise ValueError('Unsupported subtype-4 shadow source')
    if (auxiliary.clip_volume is not None
            and not isinstance(auxiliary.clip_volume, LightVolumeGpuSource)):
        raise ValueError('Unsupported subtype-4 clip source')
    if (auxiliary.gobo_volume is not None
            and not isinstance(auxiliary.gobo_volume, (
                LightVolumeGpuSource, LightGoboVolumeSource))):
        raise ValueError('Unsupported subtype-4 gobo source')

    start = int(first_volume_index)
    capacity = int(volume_capacity)
    if start < 0 or capacity < 0 or start > capacity or capacity > 0xffff:
        raise ValueError(
            'Light-volume indices must satisfy 0 <= first <= capacity <= 65535')

    light = build_light_gpu_base_record(
        replace(source, light_subtype=1, cone_parameters=(0.0, 1.0)),
        z_bin_scale=z_bin_scale).copy()
    appended = []
    next_index = start
    skipped = 0

    def build_volume(item) -> np.void:
        if isinstance(item, LightShadowVolumeSource):
            return build_shadow_volume_light_volume_record(item)
        if isinstance(item, LightProjectedShadowMapSource):
            return build_projected_shadow_map_light_volume_record(item)
        if isinstance(item, LightPointShadowMapSource):
            return build_point_shadow_map_light_volume_record(item)
        if isinstance(item, LightGoboVolumeSource):
            return build_gobo_light_volume_record(item)
        return build_light_volume_gpu_record(item)

    def allocate(item) -> int | None:
        nonlocal next_index, skipped
        if next_index >= capacity:
            skipped += 1
            return None
        index = next_index
        appended.append(build_volume(item))
        next_index += 1
        return index

    if auxiliary.clip_volume is not None:
        index = allocate(auxiliary.clip_volume)
        if index is not None:
            light['clip_volume_info'] = np.uint32(index | (1 << 16))

    if auxiliary.gobo_volume is not None:
        index = allocate(auxiliary.gobo_volume)
        if index is not None:
            current = int(light['mod_id_and_gobo_id']) & 0xffff
            light['mod_id_and_gobo_id'] = np.uint32(current | (index << 16))
            if (isinstance(auxiliary.gobo_volume, LightGoboVolumeSource)
                    and int(auxiliary.gobo_volume.atlas_size_words[1]) & 0x8000):
                light['bit_flags_vfog'] = np.uint32(
                    int(light['bit_flags_vfog']) | (1 << 5))

    def allocate_range(items) -> tuple[int, int]:
        first = next_index
        count = 0
        for item in items:
            if allocate(item) is not None:
                count += 1
        return first, count

    first, count = allocate_range(auxiliary.shadow_map_volumes)
    if count:
        light['shadow_map_info'] = np.uint32(first | (count << 16))
    first, count = allocate_range(auxiliary.shadow_volumes)
    if count:
        light['shadow_volume_info'] = np.uint32(first | (count << 16))

    # Retail gates the subtype-4 matrix/color rewrite on successful allocation
    # of its final color-volume record. A full tier leaves the common record.
    if next_index >= capacity:
        skipped += 1
    else:
        color_index = next_index
        native_color_source = replace(
            auxiliary.color_volume,
            reciprocal_dimensions=bool(source.flag_103_bit0))
        appended.append(build_color_light_volume_record(native_color_source))
        next_index += 1
        current = int(light['mod_id_and_gobo_id']) & 0xffff0000
        light['mod_id_and_gobo_id'] = np.uint32(current | color_index)
        affine = np.eye(4, dtype=np.float32)
        affine[0, :3] = _float3(source.world_axis_x, 'Subtype-4 axis X')
        affine[1, :3] = _float3(source.world_axis_y, 'Subtype-4 axis Y')
        affine[2, :3] = _float3(source.world_axis_z, 'Subtype-4 axis Z')
        affine[3, :3] = _float3(source.world_position, 'Subtype-4 position')
        inverse = _native_inverse_affine_matrix(affine)
        light['world_axis_x'] = inverse[0, :3]
        light['world_axis_y'] = inverse[1, :3]
        light['world_axis_z'] = inverse[2, :3]
        light['world_position'] = inverse[3, :3]
        light['linear_color'] = _float3(
            source.linear_color, 'Subtype-4 raw linear color')
        light['bit_flags_vfog'] = np.uint32(
            int(light['bit_flags_vfog']) | (1 << 1))

    records = np.zeros(len(appended), dtype=LIGHT_VOLUME_GPU_DTYPE)
    for index, record in enumerate(appended):
        records[index] = record
    return PackedLightGpuAuxiliaryResult(
        light=light, appended_volumes=records,
        next_volume_index=next_index, skipped_volume_count=skipped)


def _dot3(left, right) -> np.float32:
    a, b = np.asarray(left, np.float32), np.asarray(right, np.float32)
    return np.float32(np.float32(a[0] * b[0] + a[1] * b[1]) + a[2] * b[2])


def _saturate(value) -> np.float32:
    return np.float32(min(max(float(value), 0.0), 1.0))


def build_light_shell_constants(
        placement: LightShellPlacement, light_gpu_id: int, *,
        vertex_push_scale: float) -> np.void:
    """Build the exact 96-byte manager cbuffer for one local-light shell.

    Executable helper ``0x1410B6070`` copies the object matrix, transforms the
    midpoint of the local AABB, clamps each half-extent to 0.001 before taking
    its reciprocal, writes the submitted GPU record index, and appends the
    caller's screen-space push scale. Geometry remains explicit because the
    executable uploads the placement's own float3 stream and vertex count.
    """
    if not isinstance(placement, LightShellPlacement):
        raise ValueError('placement must be one LightShellPlacement')
    vertices = np.asarray(placement.vertices, dtype=np.float32)
    matrix = np.asarray(placement.object_to_world, dtype=np.float32)
    minimum = _float3(placement.local_aabb_minimum, 'Light-shell AABB minimum')
    maximum = _float3(placement.local_aabb_maximum, 'Light-shell AABB maximum')
    identifier = int(light_gpu_id)
    push = np.float32(vertex_push_scale)
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) % 3
            or not len(vertices) or not np.isfinite(vertices).all()):
        raise ValueError('Light-shell vertices must be finite float3 triangles')
    if (matrix.shape != (4, 4) or not np.isfinite(matrix).all()
            or not np.array_equal(matrix[:, 3], np.array((0, 0, 0, 1), np.float32))):
        raise ValueError('Light-shell object_to_world must be a finite affine row matrix')
    if np.any(maximum < minimum):
        raise ValueError('Light-shell AABB maximum must not precede its minimum')
    if identifier < 0 or identifier > 0xffffffff:
        raise ValueError('Light-shell GPU id must fit uint32')
    if not np.isfinite(push) or push < 0:
        raise ValueError('Light-shell vertex push must be finite and nonnegative')

    half = np.float32(.5)
    midpoint = np.asarray((minimum + maximum) * half, dtype=np.float32)
    center = np.empty(3, dtype=np.float32)
    for column in range(3):
        xy = np.float32(
            np.float32(midpoint[1] * matrix[1, column])
            + np.float32(midpoint[0] * matrix[0, column]))
        zt = np.float32(
            np.float32(midpoint[2] * matrix[2, column]) + matrix[3, column])
        center[column] = np.float32(xy + zt)
    local_half_extents = np.asarray(midpoint - minimum, dtype=np.float32)
    inverse_extents = np.asarray(
        np.float32(1) / np.maximum(local_half_extents, np.float32(.001)),
        dtype=np.float32,
    )

    result = np.zeros(1, dtype=LIGHT_SHELL_CBUFFER_DTYPE)
    result[0]['object_to_world'] = matrix
    result[0]['aabb_center'] = center
    result[0]['light_gpu_id'] = np.uint32(identifier)
    result[0]['aabb_inverse_extents'] = inverse_extents
    result[0]['vertex_push_scale'] = push
    return result[0]


def build_light_shell_near_clip_plane(
        world_center, world_radius: float, camera_position, near_clip: float,
        view_plane_rows) -> np.ndarray | None:
    """Recreate the manager's conditional expanded camera-near plane.

    Helper ``0x1410B7330`` skips clipping unless the light sphere overlaps a
    camera-centered radius of ``1.15 * world_radius + near_clip``. On overlap,
    it expands the near distance by the larger of ``min(near * 0.1, 0.001)``
    and a two-ULP radius term, then transforms ``(0, 0, 1, -distance)`` through
    the three supplied plane rows. ``None`` means the original stream is reused.

    ``view_plane_rows`` is the explicit 3x4 block read at manager-view offsets
    0x80..0xAF. Keeping it explicit avoids assigning an unverified public camera
    matrix name to that internal layout.
    """
    center = _float3(world_center, 'Light-shell world center')
    camera = _float3(camera_position, 'Light-shell camera position')
    radius = np.float32(world_radius)
    near = np.float32(near_clip)
    rows = np.asarray(view_plane_rows, dtype=np.float32)
    if (not np.isfinite([radius, near]).all() or radius < 0 or near < 0
            or rows.shape != (3, 4) or not np.isfinite(rows).all()):
        raise ValueError('Light-shell radius, near clip and plane rows must be valid')

    delta = np.asarray(camera - center, dtype=np.float32)
    distance_squared = np.float32(
        np.float32(delta[1] * delta[1] + delta[0] * delta[0])
        + np.float32(delta[2] * delta[2])
    )
    overlap_radius = np.float32(
        np.float32(radius * np.float32(1.15)) + near,
    )
    if distance_squared >= np.float32(overlap_radius * overlap_radius):
        return None

    doubled_radius = np.float32(radius + radius)
    if not np.isfinite(doubled_radius):
        raise ValueError('Light-shell radius is too large for float32 plane expansion')
    doubled_bits = int(doubled_radius.view('<u4'))
    exponent_bits = doubled_bits & 0xFF800000
    exponent_value = np.asarray([exponent_bits], '<u4').view('<f4')[0]
    two_ulp_value = np.asarray([exponent_bits | 2], '<u4').view('<f4')[0]
    radius_step = np.float32(two_ulp_value - exponent_value)
    near_step = np.minimum(
        np.float32(near * np.float32(.1)), np.float32(.001),
    )
    expanded = np.float32(
        near + np.maximum(near_step, radius_step),
    )
    plane_w = np.float32(-expanded)
    plane = np.empty(4, dtype=np.float32)
    for index in range(3):
        plane[index] = np.float32(
            np.float32(plane_w * rows[index, 3]) + rows[index, 2],
        )
    plane[3] = plane_w
    return plane


def prepare_light_shell_vertices(vertices, clip_plane) -> np.ndarray:
    """Clip and close one outward-wound triangle shell against a plane.

    The static ``0x1415E6280`` chain classifies packed float3 source triangles,
    preserves an entirely inside stream, rejects an entirely outside stream,
    clips each straddling polygon, orders the cut boundary around its centroid,
    appends an outward cap, and fan-triangulates the result. Retail currently
    calls it with one camera-near plane. This helper accepts that already
    transformed plane explicitly; camera gating and plane construction remain
    manager work.

    The retained half-space is ``dot(float4(position, 1), clip_plane) >= 0``.
    One convex closed shell is expected, matching the light-manager contract.
    """
    source = np.asarray(vertices, dtype=np.float32)
    plane = np.asarray(clip_plane, dtype=np.float32)
    if (source.ndim != 2 or source.shape[1] != 3 or len(source) % 3
            or not len(source) or not np.isfinite(source).all()):
        raise ValueError('Light-shell source must be finite float3 triangles')
    if (plane.shape != (4,) or not np.isfinite(plane).all()
            or not np.any(plane[:3])):
        raise ValueError('Light-shell clip plane must be one finite nonzero float4')

    distances = np.asarray(
        source @ plane[:3] + plane[3], dtype=np.float32,
    )
    inside = distances >= np.float32(0)
    if bool(np.all(inside)):
        return source.copy()
    if not bool(np.any(inside)):
        return np.empty((0, 3), dtype=np.float32)

    clipped_polygons: list[list[np.ndarray]] = []
    boundary_points: list[np.ndarray] = []
    for triangle_index in range(len(source) // 3):
        first = triangle_index * 3
        polygon = [source[first + index].copy() for index in range(3)]
        signed = [distances[first + index] for index in range(3)]
        output: list[np.ndarray] = []
        intersections: list[np.ndarray] = []
        previous = polygon[-1]
        previous_distance = signed[-1]
        previous_inside = bool(previous_distance >= 0)
        for current, current_distance in zip(polygon, signed):
            current_inside = bool(current_distance >= 0)
            if current_inside != previous_inside:
                denominator = np.float32(previous_distance - current_distance)
                amount = np.float32(previous_distance / denominator)
                intersection = np.asarray(
                    previous + np.asarray(current - previous, np.float32) * amount,
                    dtype=np.float32,
                )
                output.append(intersection)
                intersections.append(intersection)
            if current_inside:
                output.append(current)
            previous = current
            previous_distance = current_distance
            previous_inside = current_inside
        if len(output) >= 3:
            clipped_polygons.append(output)
        if len(intersections) == 2:
            boundary_points.extend(intersections)

    # The retail edge chain removes shared segment endpoints before its centroid
    # sort. Float32 interpolation of the same undirected edge can differ at the
    # last few bits when reached in reverse, so use a scale-relative float32
    # tolerance while retaining authored collinear boundary vertices.
    unique_boundary: list[np.ndarray] = []
    scale = max(1.0, float(np.max(np.abs(source))))
    tolerance = np.float32(np.finfo(np.float32).eps * 8 * scale)
    for point in boundary_points:
        if not any(np.all(np.abs(point - other) <= tolerance)
                   for other in unique_boundary):
            unique_boundary.append(point)

    if len(unique_boundary) >= 3:
        points = np.asarray(unique_boundary, dtype=np.float32)
        center = np.asarray(
            np.sum(points, axis=0, dtype=np.float32) / np.float32(len(points)),
            dtype=np.float32,
        )
        normal = np.asarray(plane[:3], dtype=np.float32)
        normal = np.asarray(
            normal / np.sqrt(np.sum(normal * normal, dtype=np.float32), dtype=np.float32),
            dtype=np.float32,
        )
        axis = np.zeros(3, dtype=np.float32)
        axis[int(np.argmin(np.abs(normal)))] = np.float32(1)
        tangent = np.cross(normal, axis).astype(np.float32)
        tangent = np.asarray(
            tangent / np.sqrt(np.sum(tangent * tangent, dtype=np.float32), dtype=np.float32),
            dtype=np.float32,
        )
        bitangent = np.cross(normal, tangent).astype(np.float32)
        relative = np.asarray(points - center, dtype=np.float32)
        angles = np.arctan2(relative @ bitangent, relative @ tangent)
        # Ascending angles face the retained half-space normal. Reversing makes
        # the cap outward toward the rejected half-space.
        order = np.argsort(angles, kind='stable')[::-1]
        clipped_polygons.append([points[index] for index in order])

    triangles: list[np.ndarray] = []
    for polygon in clipped_polygons:
        for index in range(1, len(polygon) - 1):
            triangles.extend((polygon[0], polygon[index], polygon[index + 1]))
    if not triangles:
        return np.empty((0, 3), dtype=np.float32)
    return np.asarray(triangles, dtype=np.float32).reshape(-1, 3)


def prepare_light_shell_vertices_for_planes(vertices, clip_planes) -> np.ndarray:
    """Apply retail's ordered clip-plane sequence to one closed shell."""

    source = np.asarray(vertices, dtype=np.float32)
    planes = np.asarray(clip_planes, dtype=np.float32)
    if (source.ndim != 2 or source.shape[1] != 3 or len(source) % 3
            or not len(source) or not np.isfinite(source).all()):
        raise ValueError('Light-shell source must be finite float3 triangles')
    if planes.ndim != 2 or planes.shape[1:] != (4,):
        raise ValueError('Light-shell clip planes must be an Nx4 array')
    if (not np.isfinite(planes).all()
            or (len(planes) and np.any(~np.any(planes[:, :3] != 0, axis=1)))):
        raise ValueError('Light-shell clip planes must be finite nonzero float4s')

    result = source.copy()
    for plane in planes:
        if not len(result):
            break
        result = prepare_light_shell_vertices(result, plane)
    return result


def project_light_shell_vertices(
        vertices, constants, view_to_world, camera_world_to_clip, *,
        near_clip: float, clamp_clip_z_nonnegative: bool = False,
        ) -> LightShellProjection:
    """Execute ``VS_LightShell`` for caller-supplied shell vertices.

    The manager owns the object transform and conservative AABB constants;
    keeping them explicit avoids deriving shell bounds from a shading record.
    ``clamp_clip_z_nonnegative`` selects the sole output difference in
    ``VS_LightShellNoFarClip``.
    """
    source = np.asarray(vertices, dtype=np.float32)
    if source.ndim < 2 or source.shape[-1] != 3 or not np.isfinite(source).all():
        raise ValueError('Light-shell vertices must be a finite (..., 3) array')
    try:
        object_to_world = np.asarray(
            constants['object_to_world'], dtype=np.float32)
        center = _float3(constants['aabb_center'], 'Light-shell AABB center')
        inverse_extents = _float3(
            constants['aabb_inverse_extents'],
            'Light-shell AABB inverse extents')
        light_id = int(constants['light_gpu_id'])
        push = np.float32(constants['vertex_push_scale'])
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise ValueError(
            'constants must be one parsed LightShellCBuffer record') from error
    view = np.asarray(view_to_world, dtype=np.float32)
    projection = np.asarray(camera_world_to_clip, dtype=np.float32)
    clip_near = np.float32(near_clip)
    if (object_to_world.shape != (4, 4)
            or view.shape != (4, 4) or projection.shape != (4, 4)
            or not np.isfinite(object_to_world).all()
            or not np.isfinite(view).all()
            or not np.isfinite(projection).all()
            or not np.isfinite([push, clip_near]).all()
            or np.any(inverse_extents <= 0) or push < 0 or clip_near < 0):
        raise ValueError(
            'Light-shell matrices, extents, push and near clip must be valid')
    if not np.array_equal(
            view[:, 3], np.array((0, 0, 0, 1), dtype=np.float32)):
        raise ValueError(
            'view_to_world must be affine with translation in row 3')

    shape = source.shape[:-1]
    flat = source.reshape(-1, 3)
    world = np.asarray(
        flat[:, 0, None] * object_to_world[0, :3]
        + flat[:, 1, None] * object_to_world[1, :3]
        + flat[:, 2, None] * object_to_world[2, :3]
        + object_to_world[3, :3], dtype=np.float32)
    camera = view[3, :3]
    relative = np.asarray(world - camera, dtype=np.float32)
    homogeneous = np.concatenate((
        relative, np.ones((len(flat), 1), dtype=np.float32)), axis=1)
    original = np.asarray(homogeneous @ projection, dtype=np.float32)

    direction = np.asarray((world - center) * inverse_extents,
                           dtype=np.float32)
    length_squared = np.sum(direction * direction, axis=1, dtype=np.float32)
    if np.any(length_squared <= 0):
        raise ValueError('Light-shell vertex lies at the AABB center')
    direction = np.asarray(
        direction / np.sqrt(length_squared, dtype=np.float32)[:, None],
        dtype=np.float32)
    amount = np.asarray(
        push * np.maximum(original[:, 3], np.float32(0)), dtype=np.float32)
    pushed_relative = np.asarray(
        relative + direction * amount[:, None], dtype=np.float32)
    pushed_homogeneous = np.concatenate((
        pushed_relative, np.ones((len(flat), 1), dtype=np.float32)), axis=1)
    pushed = np.asarray(pushed_homogeneous @ projection, dtype=np.float32)
    selected = np.where(
        (pushed[:, 3] > clip_near)[:, None], pushed, original).astype(
            np.float32, copy=False)
    if clamp_clip_z_nonnegative:
        selected[:, 2] = np.maximum(selected[:, 2], np.float32(0))
    return LightShellProjection(
        selected.reshape(shape + (4,)), float(np.float32(light_id) + np.float32(.5)))


def evaluate_point_light(record, world_point) -> PointLightGeometry:
    """Evaluate Hair's base point-light direction and radiance.

    This is the common local-light stage through the inverse-distance factor.
    It deliberately accepts only zero-radius lights; capsule/disk integration,
    clip volumes, gobos and shadows are later branches in the retail shader.
    ``record`` must be one element returned by :func:`parse_light_gpu_records`.
    """
    try:
        position = _float3(record['world_position'], 'Light position')
        axis_z = _float3(record['world_axis_z'], 'Light Z axis')
        color = _float3(record['linear_color'], 'Light color')
        radius = np.float32(record['bulb_radius'])
        inverse_radius = np.float32(record['inverse_attenuation_radius'])
        push_forward = np.float32(record['bulb_push_forward'])
        cone = np.asarray(record['cone_parameters'], dtype=np.float32)
        cut_on = np.float32(record['cut_on_depth'])
        cut_off = np.float32(record['cut_off_depth'])
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise ValueError('record must be one LightGpu structured element') from error
    if radius != 0:
        raise ValueError('Point-light evaluation requires zero bulb radius')
    if (cone.shape != (2,) or not np.isfinite(
            [radius, inverse_radius, push_forward, *cone, cut_on, cut_off]).all()
            or inverse_radius < 0 or np.any(color < 0)):
        raise ValueError('Point-light fields must be finite with nonnegative radius/color')

    point = _float3(world_point, 'World point')
    delta = np.asarray(position - point, dtype=np.float32)
    original_distance_squared = _dot3(delta, delta)
    if original_distance_squared <= 0:
        raise ValueError('World point must not equal the point-light position')
    original_inverse_distance = np.float32(
        np.float32(1) / np.sqrt(original_distance_squared, dtype=np.float32))
    original_direction = np.asarray(
        delta * original_inverse_distance, dtype=np.float32)

    cone_dot = _dot3(original_direction, axis_z)
    cone_weight = _saturate(np.float32(
        cone[1] - np.float32(cone_dot * cone[0])))
    radius_squared = np.float32(inverse_radius * inverse_radius)
    radial_position = _saturate(np.float32(
        radius_squared * original_distance_squared))
    radial_weight = np.float32(1 - np.float32(radial_position * radial_position))
    depth = _dot3(-delta, axis_z)
    cut_on_weight = _saturate(np.float32((depth - cut_on) * np.float32(2)))
    cut_off_weight = _saturate(np.float32((cut_off - depth) * np.float32(2)))
    depth_weight = np.float32(cut_on_weight * cut_off_weight)
    cone_radial = np.float32(cone_weight * radial_weight)
    attenuation = np.float32(
        depth_weight * np.float32(cone_radial * cone_radial))

    if push_forward != 0:
        delta = np.asarray(
            delta + np.asarray(axis_z * push_forward, np.float32),
            dtype=np.float32)
    distance_squared = _dot3(delta, delta)
    if distance_squared <= 0:
        raise ValueError('Bulb push-forward places the light on the world point')
    inverse_distance = np.float32(
        np.float32(1) / np.sqrt(distance_squared, dtype=np.float32))
    direction = np.asarray(delta * inverse_distance, dtype=np.float32)
    finite_radius_gate = _saturate(np.float32(
        inverse_radius * np.float32(1048576.0)))
    distance_factor = np.float32(
        np.float32(1) / np.float32(
            np.float32(finite_radius_gate * distance_squared) + np.float32(1)))
    radiance = np.asarray(
        color * np.float32(attenuation * distance_factor), dtype=np.float32)
    return PointLightGeometry(
        direction, float(distance_squared), float(cone_weight),
        float(radial_weight), float(depth_weight), float(attenuation),
        float(distance_factor), radiance)


def evaluate_hair_area_light(
        record, world_point, lobe_directions, surface_to_camera_direction,
        ) -> HairAreaLightGeometry:
    """Evaluate Hair's spherical or capsule local-light geometry.

    ``lobe_directions`` is the shader's three-row Hair surface triad. The first
    row is also the normal used to reflect the view ray for finite-segment
    selection. ``surface_to_camera_direction`` must be the normalized direction
    used by the Hair shader. The result ends before gobo and shadow modulation.
    """
    try:
        position = _float3(record['world_position'], 'Light position')
        axis_x = _float3(record['world_axis_x'], 'Light X axis')
        axis_z = _float3(record['world_axis_z'], 'Light Z axis')
        color = _float3(record['linear_color'], 'Light color')
        source_radius = np.float32(record['bulb_radius'])
        source_length = np.float32(record['bulb_length'])
        inverse_radius = np.float32(record['inverse_attenuation_radius'])
        push_forward = np.float32(record['bulb_push_forward'])
        cone = np.asarray(record['cone_parameters'], dtype=np.float32)
        cut_on = np.float32(record['cut_on_depth'])
        cut_off = np.float32(record['cut_off_depth'])
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise ValueError('record must be one LightGpu structured element') from error
    triad = np.asarray(lobe_directions, dtype=np.float32)
    view_direction = _float3(
        surface_to_camera_direction, 'Surface-to-camera direction')
    fields = np.asarray((
        source_radius, source_length, inverse_radius, push_forward,
        cone[0] if cone.shape == (2,) else np.nan,
        cone[1] if cone.shape == (2,) else np.nan, cut_on, cut_off,
    ), dtype=np.float32)
    if (source_radius == 0 or source_length < 0 or inverse_radius < 0
            or triad.shape != (3, 3) or not np.isfinite(triad).all()
            or not np.isfinite(fields).all() or np.any(color < 0)):
        raise ValueError(
            'Area-light fields need nonzero radius, nonnegative length/range '
            'and finite Hair directions')

    point = _float3(world_point, 'World point')
    delta = np.asarray(position - point, dtype=np.float32)
    original_distance_squared = _dot3(delta, delta)
    if original_distance_squared <= 0:
        raise ValueError('World point must not equal the area-light position')
    original_inverse_distance = np.float32(
        np.float32(1) / np.sqrt(original_distance_squared, dtype=np.float32))
    original_direction = np.asarray(
        delta * original_inverse_distance, dtype=np.float32)

    cone_dot = _dot3(original_direction, axis_z)
    cone_weight = _saturate(np.float32(
        cone[1] - np.float32(cone_dot * cone[0])))
    inverse_radius_squared = np.float32(inverse_radius * inverse_radius)
    radial_position = _saturate(np.float32(
        inverse_radius_squared * original_distance_squared))
    radial_weight = np.float32(1 - np.float32(radial_position * radial_position))
    depth = _dot3(-delta, axis_z)
    cut_on_weight = _saturate(np.float32((depth - cut_on) * np.float32(2)))
    cut_off_weight = _saturate(np.float32((cut_off - depth) * np.float32(2)))
    depth_weight = np.float32(cut_on_weight * cut_off_weight)
    cone_radial = np.float32(cone_weight * radial_weight)
    attenuation = np.float32(
        depth_weight * np.float32(cone_radial * cone_radial))

    if push_forward != 0:
        delta = np.asarray(
            delta + np.asarray(axis_z * push_forward, np.float32),
            dtype=np.float32)
    distance_squared = _dot3(delta, delta)
    if distance_squared <= 0:
        raise ValueError('Bulb push-forward places the light on the world point')
    inverse_distance = np.float32(
        np.float32(1) / np.sqrt(distance_squared, dtype=np.float32))
    direction = np.asarray(delta * inverse_distance, dtype=np.float32)
    raw_lobe_dots = np.asarray(
        [_dot3(row, direction) for row in triad], dtype=np.float32)
    finite_radius_gate = _saturate(np.float32(
        inverse_radius * np.float32(1048576.0)))
    distance_factor = np.float32(
        np.float32(1) / np.float32(
            np.float32(finite_radius_gate * distance_squared) + np.float32(1)))

    radius = source_radius
    length = source_length
    if radius < 0:
        attenuation = np.float32(
            attenuation * abs(float(_dot3(direction, axis_z))))
        radius = np.abs(radius)
        length = np.maximum(
            np.float32(length - np.float32(
                radius * np.float32(1.7724499702453613))), np.float32(0))

    radius_over_distance = np.float32(radius * inverse_distance)
    disk_term = _saturate(np.float32(
        np.float32(.5) * np.float32(
            radius_over_distance * radius_over_distance)))
    disk_denominator = np.float32(
        np.float32(1) + disk_term)
    disk_denominator = np.float32(
        np.float32(1) / np.float32(
            disk_denominator * disk_denominator))
    lobe_weights = np.asarray([
        _saturate(np.float32(
            np.float32(disk_term + value) * disk_denominator))
        for value in raw_lobe_dots
    ], dtype=np.float32)
    chosen_inverse_distance = inverse_distance
    area_metric = radius_over_distance

    if length > 0:
        half_segment = np.asarray(
            axis_x * np.float32(length * np.float32(.5)), dtype=np.float32)
        endpoint_negative = np.asarray(delta - half_segment, dtype=np.float32)
        endpoint_positive = np.asarray(delta + half_segment, dtype=np.float32)
        negative_squared = _dot3(endpoint_negative, endpoint_negative)
        positive_squared = _dot3(endpoint_positive, endpoint_positive)
        if negative_squared <= 0 or positive_squared <= 0:
            raise ValueError('Area-light segment endpoint meets the world point')
        negative_inverse = np.float32(
            np.float32(1) / np.sqrt(negative_squared, dtype=np.float32))
        positive_inverse = np.float32(
            np.float32(1) / np.sqrt(positive_squared, dtype=np.float32))
        inverse_product = np.float32(negative_inverse * positive_inverse)
        endpoint_cosine = np.float32(
            np.float32(.5) + np.float32(
                np.float32(.5) * np.float32(
                    inverse_product * _dot3(
                        endpoint_negative, endpoint_positive))))
        segment_denominator = np.float32(endpoint_cosine + inverse_product)
        if segment_denominator == 0:
            raise ValueError('Area-light segment factor is degenerate')
        segment_factor = np.float32(inverse_product / segment_denominator)
        negative_dots = np.asarray([
            _dot3(row, endpoint_negative) for row in triad], dtype=np.float32)
        positive_dots = np.asarray([
            _dot3(row, endpoint_positive) for row in triad], dtype=np.float32)
        for index in range(3):
            negative_weight = _saturate(np.float32(
                np.float32(
                    negative_dots[index] * negative_inverse + disk_term)
                * disk_denominator))
            positive_weight = _saturate(np.float32(
                np.float32(
                    positive_dots[index] * positive_inverse + disk_term)
                * disk_denominator))
            lobe_weights[index] = np.float32(
                np.float32(
                    negative_weight + lobe_weights[index] + positive_weight)
                * np.float32(1 / 3))

        incident = np.asarray(-view_direction, dtype=np.float32)
        reflected = np.asarray(
            incident - np.float32(
                np.float32(2) * _dot3(incident, triad[0])) * triad[0],
            dtype=np.float32)
        projected = _dot3(reflected, half_segment)
        segment_vector = np.asarray(
            reflected * projected - half_segment, dtype=np.float32)
        closest_denominator = np.float32(
            np.float32(length * length) - np.float32(projected * projected))
        if closest_denominator == 0:
            raise ValueError('Area-light closest segment direction is degenerate')
        closest_amount = _saturate(np.float32(
            _dot3(endpoint_negative, segment_vector) / closest_denominator))
        closest = np.asarray(
            endpoint_negative + closest_amount * half_segment,
            dtype=np.float32)
        closest_squared = _dot3(closest, closest)
        if closest_squared <= 0:
            raise ValueError('Area-light closest point meets the world point')
        chosen_inverse_distance = np.float32(
            np.float32(1) / np.sqrt(closest_squared, dtype=np.float32))
        direction = np.asarray(
            closest * chosen_inverse_distance, dtype=np.float32)
        distance_squared = closest_squared
        circle = np.sqrt(np.maximum(
            np.float32(1) - np.float32(endpoint_cosine * endpoint_cosine),
            np.float32(0)), dtype=np.float32)
        area_metric = np.sqrt(np.maximum(
            np.float32(circle + radius_over_distance)
            * radius_over_distance, np.float32(0)), dtype=np.float32)
        distance_factor = segment_factor

    radius_at_distance = np.float32(chosen_inverse_distance * radius)
    radius_at_distance = np.minimum(radius_at_distance, np.float32(1))
    if radius_at_distance <= 0:
        raise ValueError('Area-light radius at distance is degenerate')
    area_boost = _saturate(np.float32(
        np.float32(2.5) - np.float32(
            np.float32(1) / radius_at_distance)))
    area_boost = np.float32(
        np.float32(1) + np.float32(
            area_boost * np.float32(.15000000596046448)))
    distance_factor = np.float32(area_boost * distance_factor)
    radiance = np.asarray(
        color * np.float32(attenuation * distance_factor), dtype=np.float32)
    return HairAreaLightGeometry(
        direction, lobe_weights, float(distance_squared), float(radius),
        float(length), float(area_metric), float(attenuation),
        float(distance_factor), radiance)


def _fast_acos_unit(value) -> np.float32:
    coordinate = np.float32(value)
    magnitude = np.abs(coordinate)
    if not np.isfinite(coordinate) or magnitude > np.float32(1.000001):
        raise ValueError('Gobo direction cosine must be finite and normalized')
    magnitude = np.minimum(magnitude, np.float32(1))
    angle = np.float32(
        np.float32(np.float32(1.5707963705062866)
                   - np.float32(.1565829962491989) * magnitude)
        * np.sqrt(np.float32(1) - magnitude, dtype=np.float32))
    if coordinate < 0:
        angle = np.float32(np.float32(3.1415927410125732) - angle)
    return angle


def _fast_atan2(numerator, denominator) -> np.float32:
    first, second = np.float32(numerator), np.float32(denominator)
    absolute_first, absolute_second = np.abs(first), np.abs(second)
    greatest = np.maximum(absolute_first, absolute_second)
    if not np.isfinite([first, second]).all() or greatest == 0:
        raise ValueError('Gobo longitude direction must be finite and nonzero')
    ratio = np.float32(np.minimum(absolute_first, absolute_second) / greatest)
    squared = np.float32(ratio * ratio)
    polynomial = np.float32(
        np.float32(
            np.float32(np.float32(.08729290217161179) * squared)
            + np.float32(-.30189499258995056)) * squared
        + np.float32(1))
    angle = np.float32(polynomial * ratio)
    if absolute_first > absolute_second:
        angle = np.float32(np.float32(1.5707963705062866) - angle)
    if second < 0:
        angle = np.float32(np.float32(3.1415927410125732) - angle)
    if first < 0:
        angle = np.float32(-angle)
    return angle


def _fraction(value) -> np.float32:
    number = np.float32(value)
    return np.float32(number - np.floor(number))


def light_gobo_coordinates(
        record, volumes, world_point, original_light_direction,
        ) -> GoboCoordinates:
    """Return Hair's exact gobo atlas coordinate before texture sampling.

    Flag bit 32 selects the alternate spherical layout, bit 1 selects the
    standard spherical layout, and the remaining path uses projective volume
    coordinates. The high half of ``mod_id_and_gobo_id`` selects the
    ``LightVolumeGpu`` atlas record; ``0xffff`` means no gobo.
    """
    table = _volume_array(volumes)
    index = _record_uint(record, 'mod_id_and_gobo_id') >> 16
    if index == 0xffff:
        raise ValueError('Light record does not select a gobo')
    if index >= len(table):
        raise ValueError('Gobo volume index exceeds supplied records')
    flags = _record_uint(record, 'bit_flags_vfog')
    point = _float3(world_point, 'World point')
    original_direction = _float3(
        original_light_direction, 'Original light direction')
    volume = table[index]
    atlas = np.asarray(volume['atlas_coordinates'], dtype=np.float32)
    if atlas.shape != (4,) or not np.isfinite(atlas).all():
        raise ValueError('Gobo atlas coordinates must be finite')

    if flags & 32 or flags & 1:
        axis_x = _float3(record['world_axis_x'], 'Light X axis')
        axis_y = _float3(record['world_axis_y'], 'Light Y axis')
        axis_z = _float3(record['world_axis_z'], 'Light Z axis')
        source = np.asarray(-original_direction, dtype=np.float32)
        local = np.asarray((
            _dot3(source, axis_x), _dot3(source, axis_y),
            _dot3(source, axis_z)), dtype=np.float32)
        if flags & 32:
            latitude = np.float32(
                _fast_acos_unit(local[2])
                * np.float32(.31830987334251404))
            longitude = _fraction(np.float32(
                _fast_atan2(local[0], local[1])
                * np.float32(.15915493667125702) + np.float32(.5)))
            if atlas[3] < 0:
                uv = np.asarray((longitude, latitude), dtype=np.float32)
            else:
                uv = np.asarray((latitude, longitude), dtype=np.float32)
            mode, monochrome = 'alternate_spherical', True
        else:
            longitude = _fraction(np.float32(
                _fast_atan2(local[2], local[0])
                * np.float32(.15915493667125702) + np.float32(.5)))
            latitude = np.float32(
                _fast_acos_unit(local[1])
                * np.float32(.31830987334251404))
            uv = np.asarray((longitude, latitude), dtype=np.float32)
            mode, monochrome = 'spherical', False
        edge_weight = np.float32(1)
        local_or_projection = local
    else:
        matrix = np.asarray(volume['transform_matrix'], dtype=np.float32)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
            raise ValueError('Gobo projective transform must be finite')
        homogeneous = np.asarray((point[0], point[1], point[2], 1),
                                 dtype=np.float32)
        projected = np.asarray(homogeneous @ matrix, dtype=np.float32)
        if projected[3] == 0:
            raise ValueError('Gobo projective W must be nonzero')
        projected_xy = np.asarray(
            projected[:2] / projected[3], dtype=np.float32)
        uv = np.asarray((
            _saturate(np.float32(1 - projected_xy[0])),
            _saturate(np.float32(1 - projected_xy[1])),
        ), dtype=np.float32)
        centered = np.abs(np.float32(2) * uv - np.float32(1))
        edge_weight = _saturate(np.float32(
            np.float32(20) - np.float32(
                np.float32(20.25) * np.max(centered))))
        local_or_projection = projected
        mode, monochrome = 'projective', False

    atlas_uv = np.asarray(
        atlas[:2] + uv * atlas[2:4], dtype=np.float32)
    return GoboCoordinates(
        mode, local_or_projection, uv, atlas_uv,
        float(edge_weight), monochrome)


def apply_light_gobo_sample(
        record, coordinates: GoboCoordinates, sample) -> np.ndarray:
    """Multiply light color by a sampled gobo value and projective edge mask."""
    color = _float3(record['linear_color'], 'Light color')
    value = np.asarray(sample, dtype=np.float32)
    if value.ndim != 1 or value.size < 1 or not np.isfinite(value).all():
        raise ValueError('Gobo sample must be a finite color vector')
    if coordinates.monochrome:
        modulation = np.full(3, value[0], dtype=np.float32)
    else:
        if value.size < 3:
            raise ValueError('RGB gobo mode requires a three-channel sample')
        modulation = value[:3]
    return np.asarray(
        color * modulation * np.float32(coordinates.edge_weight),
        dtype=np.float32)


def light_shadow_volume_coordinates(
        record, volumes, world_point, *, enabled: bool = True,
        ) -> tuple[ShadowVolumeCoordinates, ...]:
    """Evaluate Hair's ordered five-plane shadow-volume inclusion chain.

    The low/high halves of ``shadow_volume_info`` contain the first record and
    count. The retail world flag gates the whole branch; callers pass that
    state as ``enabled``. Only volumes whose five signed plane distances are
    strictly positive sample the shared gobo atlas.
    """
    if not enabled:
        return ()
    table = _volume_array(volumes)
    point = _float3(world_point, 'World point')
    info = _record_uint(record, 'shadow_volume_info')
    first, count = info & 0xffff, info >> 16
    if first + count > len(table):
        raise ValueError('Light shadow-volume range exceeds supplied records')
    result = []
    for offset in range(count):
        index = first + offset
        volume = table[index]
        matrix = np.asarray(volume['transform_matrix'], dtype=np.float32)
        fifth = np.asarray((
            volume['falloff_negative'][0],
            volume['falloff_negative'][1],
            volume['falloff_negative'][2],
            volume['shadow_texel_scale'],
        ), dtype=np.float32)
        atlas = np.asarray(volume['atlas_coordinates'], dtype=np.float32)
        fade = np.float32(volume['fade'])
        misc = np.float32(volume['misc'])
        if (matrix.shape != (4, 4) or atlas.shape != (4,)
                or not np.isfinite(matrix).all()
                or not np.isfinite(fifth).all()
                or not np.isfinite(atlas).all()
                or not np.isfinite([fade, misc]).all()):
            raise ValueError('Shadow-volume fields must be finite')
        distances = np.asarray((
            _dot3(matrix[0, :3], point) + matrix[0, 3],
            _dot3(matrix[1, :3], point) + matrix[1, 3],
            _dot3(matrix[2, :3], point) + matrix[2, 3],
            _dot3(matrix[3, :3], point) + matrix[3, 3],
            _dot3(fifth[:3], point) + fifth[3],
        ), dtype=np.float32)
        if np.min(distances) <= 0:
            continue
        u = np.float32(
            atlas[0] + np.float32(
                distances[0] / np.float32(distances[0] + distances[1]))
            * atlas[2])
        v = np.float32(
            atlas[1] + np.float32(
                distances[2] / np.float32(distances[2] + distances[3]))
            * atlas[3])
        plane_fade = _saturate(np.float32(
            np.float32(1) - np.float32(misc * distances[4])))
        fade_to_white = _saturate(np.float32(
            np.float32(plane_fade * plane_fade) + fade))
        result.append(ShadowVolumeCoordinates(
            index, distances, np.asarray((u, v), dtype=np.float32),
            float(fade_to_white)))
    return tuple(result)


def apply_light_shadow_volume_samples(
        radiance, coordinates, samples) -> np.ndarray:
    """Apply sampled RGB shadow-volume values in retail record order."""
    result = _float3(radiance, 'Light radiance').copy()
    entries = tuple(coordinates)
    values = np.asarray(samples, dtype=np.float32)
    if (values.shape != (len(entries), 3) or not np.isfinite(values).all()):
        raise ValueError(
            'Shadow-volume samples must have shape (active volumes, 3)')
    for entry, sample in zip(entries, values):
        fade = np.float32(entry.fade_to_white)
        multiplier = np.asarray(
            sample + fade * (np.float32(1) - sample), dtype=np.float32)
        result = np.asarray(result * multiplier, dtype=np.float32)
    return result


def light_shadow_map_coordinates(
        record, volumes, world_point) -> tuple[ShadowMapCoordinates, ...]:
    """Project Hair's ordered local shadow-map records into the shared atlas.

    The low/high halves of ``shadow_map_info`` select the first volume and
    count. Flag bit 1 chooses the six-face packed point-light mapping; the
    other path uses the volume's homogeneous projective transform.
    """
    table = _volume_array(volumes)
    point = _float3(world_point, 'World point')
    info = _record_uint(record, 'shadow_map_info')
    first, count = info & 0xffff, info >> 16
    if first + count > len(table):
        raise ValueError('Light shadow-map range exceeds supplied records')
    flags = _record_uint(record, 'bit_flags_vfog')
    position = _float3(record['world_position'], 'Light position')
    epsilon = np.float32(0.00006103515625)
    result = []
    for index in range(first, first + count):
        volume = table[index]
        matrix = np.asarray(volume['transform_matrix'], dtype=np.float32)
        atlas = np.asarray(volume['atlas_coordinates'], dtype=np.float32)
        if (matrix.shape != (4, 4) or atlas.shape != (4,)
                or not np.isfinite(matrix).all()
                or not np.isfinite(atlas).all()):
            raise ValueError('Shadow-map transform and atlas fields must be finite')
        if flags & 1:
            delta = np.asarray(point - position, dtype=np.float32)
            absolute = np.abs(delta)
            if absolute[0] >= absolute[1] and absolute[0] >= absolute[2]:
                face, major, minor_a, minor_b = (
                    matrix[0], delta[0], delta[2], delta[1])
            elif absolute[1] > absolute[2]:
                face, major, minor_a, minor_b = (
                    matrix[1], delta[1], delta[0], delta[2])
            else:
                face, major, minor_a, minor_b = (
                    matrix[2], delta[2], delta[1], delta[0])
            if major == 0:
                raise ValueError('Point shadow-map direction is degenerate')
            base = np.asarray(
                face[:2] if major < 0 else face[2:4], dtype=np.float32)
            integer = np.floor(base).astype(np.float32)
            atlas_offset = np.asarray(integer * np.float32(.125),
                                      dtype=np.float32)
            atlas_scale = np.float32(base[0] - integer[0])
            signed_minor_b = np.float32(-minor_b if major < 0 else minor_b)
            major_abs = np.abs(np.float32(major))
            unit = np.asarray((
                _saturate(np.float32(
                    np.float32(major_abs + minor_a)
                    * np.float32(.5) / major_abs)),
                _saturate(np.float32(
                    np.float32(major_abs - signed_minor_b)
                    * np.float32(.5) / major_abs)),
            ), dtype=np.float32)
            uv = np.asarray(
                atlas_offset + unit * atlas_scale, dtype=np.float32)
            depth_scale = np.float32(matrix[3, 0])
            if depth_scale == 0:
                raise ValueError('Point shadow-map depth scale is zero')
            depth = np.float32(
                major_abs * depth_scale + np.float32(matrix[3, 1]))
            inverse_scale = np.float32(1) / depth_scale
            clamp_minimum = np.asarray(atlas_offset + epsilon, np.float32)
            clamp_maximum = np.asarray(
                atlas_offset + atlas_scale - epsilon, np.float32)
            mode = 'point_cube_face'
        else:
            projected = np.asarray(
                point[0] * matrix[0] + point[1] * matrix[1]
                + point[2] * matrix[2] + matrix[3], dtype=np.float32)
            if projected[3] == 0:
                raise ValueError('Projective shadow-map W is zero')
            unit = np.clip(
                projected[:2] / projected[3], 0, 1).astype(np.float32)
            uv = np.asarray(atlas[:2] + unit * atlas[2:4], np.float32)
            depth_length_squared = np.float32(
                matrix[0, 2] * matrix[0, 2]
                + matrix[1, 2] * matrix[1, 2]
                + matrix[2, 2] * matrix[2, 2])
            if depth_length_squared <= 0:
                raise ValueError('Projective shadow-map depth axis is degenerate')
            inverse_scale = np.float32(
                np.float32(1) / np.sqrt(depth_length_squared,
                                        dtype=np.float32))
            depth = np.float32(projected[2])
            clamp_minimum = np.asarray(atlas[:2] + epsilon, np.float32)
            clamp_maximum = np.asarray(
                atlas[:2] + atlas[2:4] - epsilon, np.float32)
            mode = 'projective'
        result.append(ShadowMapCoordinates(
            index, mode, uv, clamp_minimum, clamp_maximum,
            float(depth), float(inverse_scale)))
    return tuple(result)


def light_shadow_map_sample_plan(
        coordinates: ShadowMapCoordinates, transmission_code: int,
        noise_direction) -> ShadowMapSamplePlan:
    """Build Hair's direct compare or four-tap local shadow filter plan."""
    code = int(transmission_code)
    if code < 0 or code > 127:
        raise ValueError('Hair transmission code must be in 0..127')
    direction = np.asarray(noise_direction, dtype=np.float32)
    if (direction.shape != (2,) or not np.isfinite(direction).all()
            or not np.isclose(np.dot(direction, direction), 1, atol=2e-5)):
        raise ValueError('Shadow noise direction must be a normalized float2')
    uv = np.asarray(coordinates.atlas_uv, dtype=np.float32)
    minimum = np.asarray(coordinates.clamp_minimum, dtype=np.float32)
    maximum = np.asarray(coordinates.clamp_maximum, dtype=np.float32)
    depth = np.float32(coordinates.compare_depth)
    inverse_scale = np.float32(coordinates.inverse_depth_scale)
    if (uv.shape != (2,) or minimum.shape != (2,) or maximum.shape != (2,)
            or not np.isfinite([*uv, *minimum, *maximum, depth,
                                inverse_scale]).all()
            or inverse_scale == 0 or np.any(minimum > maximum)):
        raise ValueError('Shadow-map coordinates must be finite and ordered')
    radius = np.float32(
        np.float32(code) * np.float32(1.537893695058301e-05)
        + np.float32(0.000244140625))
    depth_bias = np.float32(radius * inverse_scale)
    absorption = np.float32(
        np.float32(4) - np.float32(
            np.float32(code) * np.float32(0.06299212574958801)))
    absorption = np.float32(absorption * absorption + np.float32(1))
    direct = bool(depth < depth_bias)
    if direct:
        sample_uvs = uv.reshape(1, 2).copy()
    else:
        sample_uvs = []
        distance_squared = np.float32(.125)
        current = direction.copy()
        for _ in range(4):
            offset = np.asarray(
                radius * current
                * np.sqrt(distance_squared, dtype=np.float32), np.float32)
            sample_uvs.append(np.clip(uv + offset, minimum, maximum))
            current = np.asarray((
                np.float32(current[0] * np.float32(-.7373688220977783)
                           - current[1] * np.float32(.6754903793334961)),
                np.float32(current[0] * np.float32(.6754903793334961)
                           + current[1] * np.float32(-.7373688220977783)),
            ), dtype=np.float32)
            distance_squared = np.float32(distance_squared + np.float32(.25))
        sample_uvs = np.asarray(sample_uvs, np.float32)
    return ShadowMapSamplePlan(
        coordinates.volume_index, direct, sample_uvs, float(depth),
        float(inverse_scale), float(depth_bias), float(absorption))


def resolve_light_shadow_map_sample(plan: ShadowMapSamplePlan, samples) -> float:
    """Resolve caller-supplied comparison or raw atlas-depth samples."""
    values = np.asarray(samples, dtype=np.float32)
    if plan.direct_compare:
        if values.shape not in ((), (1,)) or not np.isfinite(values).all():
            raise ValueError('Direct shadow comparison requires one finite sample')
        visibility = np.float32(values.reshape(-1)[0])
    else:
        if values.shape != (4,) or not np.isfinite(values).all():
            raise ValueError('Filtered local shadow requires four finite depths')
        distance_squared = np.asarray((.125, .375, .625, .875), np.float32)
        separation = np.asarray(
            (np.float32(plan.compare_depth) - values)
            * np.float32(plan.inverse_depth_scale)
            - distance_squared * np.float32(plan.depth_bias), np.float32)
        optical = np.asarray(
            np.maximum(separation, np.float32(0))
            * np.float32(plan.absorption), np.float32)
        visibility = np.mean(np.exp2(
            optical * np.float32(-50.494327545166016)), dtype=np.float32)
    if visibility < 0 or visibility > 1:
        raise ValueError('Shadow visibility sample must be in 0..1')
    return float(visibility)


def _volume_array(volumes) -> np.ndarray:
    result = np.asarray(volumes)
    if result.ndim != 1 or result.dtype != LIGHT_VOLUME_GPU_DTYPE:
        raise ValueError('volumes must be parsed LightVolumeGpu records')
    return result


def _record_uint(record, name: str) -> int:
    try:
        return int(record[name])
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise ValueError('record must be one LightGpu structured element') from error


def _transform_light_point(record, point) -> np.ndarray:
    axis_x = _float3(record['world_axis_x'], 'Light X axis')
    axis_y = _float3(record['world_axis_y'], 'Light Y axis')
    axis_z = _float3(record['world_axis_z'], 'Light Z axis')
    translation = _float3(record['world_position'], 'Light translation')
    # Preserve the shader's y, x, z multiply/add sequence.
    local = np.asarray(np.float32(point[1]) * axis_y, dtype=np.float32)
    local = np.asarray(
        np.float32(point[0]) * axis_x + local, dtype=np.float32)
    local = np.asarray(
        np.float32(point[2]) * axis_z + local, dtype=np.float32)
    return np.asarray(local + translation, dtype=np.float32)


def _transform_volume_point(volume, point) -> np.ndarray:
    matrix = np.asarray(volume['transform_matrix'], dtype=np.float32)
    if matrix.shape != (4, 4) or not np.isfinite(matrix[:, :3]).all():
        raise ValueError('Light-volume transform must be finite')
    local = np.asarray(np.float32(point[1]) * matrix[1, :3], dtype=np.float32)
    local = np.asarray(
        np.float32(point[0]) * matrix[0, :3] + local, dtype=np.float32)
    local = np.asarray(
        np.float32(point[2]) * matrix[2, :3] + local, dtype=np.float32)
    return np.asarray(local + matrix[3, :3], dtype=np.float32)


def light_clip_rejected(record, volumes, world_point) -> bool:
    """Evaluate the ordered clip-volume Boolean chain at offset 108.

    The low half of ``clip_volume_info`` is the first volume and the high half
    is its count. The first and nonzero-fade entries OR their outside test into
    the chain; later zero-fade entries AND it. A true final value rejects the
    light before attenuation or shading.
    """
    table = _volume_array(volumes)
    point = _float3(world_point, 'World point')
    info = _record_uint(record, 'clip_volume_info')
    first, count = info & 0xffff, info >> 16
    if first + count > len(table):
        raise ValueError('Light clip-volume range exceeds supplied records')
    rejected = False
    for offset in range(count):
        volume = table[first + offset]
        local = _transform_volume_point(volume, point)
        outside = bool(np.max(np.abs(local)) >= np.float32(1))
        fade = np.float32(volume['fade'])
        if not np.isfinite(fade):
            raise ValueError('Light-volume fade must be finite')
        if offset != 0 and fade == 0:
            rejected = rejected and outside
        else:
            rejected = rejected or outside
    return rejected


def evaluate_light_volume_multiplier(
        record, volumes, world_point) -> LightVolumeMultiplier:
    """Evaluate Hair's flag-2 accumulated-light color-volume operator.

    Flag bit 2 selects this branch and bit 4 selects radial rather than box
    falloff. The low half of ``mod_id_and_gobo_id`` names its volume record.
    """
    flags = _record_uint(record, 'bit_flags_vfog')
    if not flags & 2:
        raise ValueError('Light record does not select the light-volume branch')
    table = _volume_array(volumes)
    index = _record_uint(record, 'mod_id_and_gobo_id') & 0xffff
    if index >= len(table):
        raise ValueError('Light-volume index exceeds supplied records')
    point = _float3(world_point, 'World point')
    local = _transform_light_point(record, point)
    volume = table[index]
    extents = _float3(volume['extents'], 'Light-volume extents')
    falloff_negative = _float3(
        volume['falloff_negative'], 'Light-volume negative falloff')
    falloff_positive = _float3(
        volume['falloff_positive'], 'Light-volume positive falloff')
    color = _float3(record['linear_color'], 'Light-volume color')
    fade = np.float32(volume['fade'])
    if not np.isfinite(fade):
        raise ValueError('Light-volume fade must be finite')

    if flags & 4:
        scaled = np.asarray(extents * local, dtype=np.float32)
        length_squared = _dot3(scaled, scaled)
        if length_squared <= 0:
            raise ValueError('Radial light-volume position is degenerate')
        reciprocal_length = np.float32(
            np.float32(1) / np.sqrt(length_squared, dtype=np.float32))
        direction = np.asarray(scaled * reciprocal_length, dtype=np.float32)
        edge = np.maximum(falloff_negative * direction,
                          falloff_positive * direction)
        directional_falloff = _dot3(edge, np.abs(direction))
        shell_weight = _saturate(np.float32(
            1 - _dot3(scaled, direction)))
        influence = _saturate(np.float32(
            directional_falloff * shell_weight))
    else:
        positive = np.asarray(
            falloff_negative * (extents + local), dtype=np.float32)
        negative = np.asarray(
            falloff_positive * (extents - local), dtype=np.float32)
        influence = _saturate(np.min(np.minimum(positive, negative)))
    influence = np.float32(influence * fade)
    multiplier = np.asarray(
        np.float32(influence) * (color - np.float32(1)) + np.float32(1),
        dtype=np.float32)
    return LightVolumeMultiplier(local, float(influence), multiplier)


def _lookup_array(lookup) -> np.ndarray:
    result = np.asarray(lookup)
    if (result.ndim != 3 or result.dtype.kind != 'u'
            or result.dtype.itemsize != 4):
        raise ValueError(
            'Light lookup must have shape (word_count, height, width), '
            'dtype uint32')
    return result


def light_lookup_indices(lookup, tile_x: int, tile_y: int, *,
                         word_count: int | None = None,
                         record_count: int | None = None) -> np.ndarray:
    """Return one tile's selected record indices in retail visitation order."""
    words = _lookup_array(lookup)
    x, y = int(tile_x), int(tile_y)
    if x < 0 or y < 0 or x >= words.shape[2] or y >= words.shape[1]:
        raise ValueError('Light-lookup tile is outside the supplied texture')
    count = words.shape[0] if word_count is None else int(word_count)
    if count < 0 or count > words.shape[0]:
        raise ValueError('Active light-lookup word count exceeds texture slices')
    if record_count is not None and int(record_count) < 0:
        raise ValueError('Light record count must be nonnegative')

    selected: list[int] = []
    for word_index in range(count):
        bits = int(words[word_index, y, x])
        while bits:
            lowest = bits & -bits
            bit = lowest.bit_length() - 1
            index = word_index * 32 + bit
            if record_count is not None and index >= int(record_count):
                raise ValueError('Light lookup references a missing light record')
            selected.append(index)
            bits ^= lowest
    return np.asarray(selected, dtype=np.uint32)


def light_lookup_indices_at_pixel(lookup, pixel_x: int, pixel_y: int, *,
                                  tile_size: int = 8,
                                  word_count: int | None = None,
                                  record_count: int | None = None) -> np.ndarray:
    """Map a full-resolution pixel to its tile and return selected lights."""
    x, y, size = int(pixel_x), int(pixel_y), int(tile_size)
    if x < 0 or y < 0:
        raise ValueError('Pixel coordinates must be nonnegative')
    if size <= 0:
        raise ValueError('Light-lookup tile size must be positive')
    return light_lookup_indices(
        lookup, x // size, y // size,
        word_count=word_count, record_count=record_count)


def light_lookup_words_at_pixels(lookup, pixels, *, tile_size: int = 8,
                                  word_count: int | None = None) -> np.ndarray:
    """Gather active lookup words for an ``(N,2)`` array of pixel ``x,y``."""
    words = _lookup_array(lookup)
    points = np.asarray(pixels)
    if points.ndim != 2 or points.shape[1] != 2 or points.dtype.kind not in 'iu':
        raise ValueError('Pixels must have shape (count, 2), integer dtype')
    size = int(tile_size)
    if size <= 0:
        raise ValueError('Light-lookup tile size must be positive')
    count = words.shape[0] if word_count is None else int(word_count)
    if count < 0 or count > words.shape[0]:
        raise ValueError('Active light-lookup word count exceeds texture slices')
    if np.any(points < 0):
        raise ValueError('Pixel coordinates must be nonnegative')
    tiles = points.astype(np.int64, copy=False) // size
    if (np.any(tiles[:, 0] >= words.shape[2])
            or np.any(tiles[:, 1] >= words.shape[1])):
        raise ValueError('Pixel maps outside the supplied light lookup')
    return words[:count, tiles[:, 1], tiles[:, 0]].T.copy()
