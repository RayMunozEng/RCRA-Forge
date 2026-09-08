"""Serialized component definitions shared by actor and zone assets.

The component loader at 0x140FFD4D0/0x140FFD650 consumes 32-byte records.
Type-specific interpretation and merging actor defaults with zone overrides
remain separate; an empty payload asks the retail factory for default data.
"""
from dataclasses import dataclass, field
import struct

from core.archive import DAT1


@dataclass(frozen=True)
class SceneComponent:
    instance_id: int
    name: str | None
    type_id: int
    flags: int
    data_offset: int
    data: bytes = field(repr=False)
    reserved: int


def parse_component_records(dat1_data: bytes, records) -> tuple[SceneComponent, ...]:
    """Offsets refer to DAT1 byte zero, not the records section or outer header."""
    if len(records) % 32:
        raise ValueError('Malformed component table: expected 32-byte records')
    dat1 = DAT1(dat1_data)
    components = []
    for instance_id, name_offset, type_id, flags, offset, size, reserved in struct.iter_unpack(
            '<Q6I', records):
        if size and (offset > len(dat1_data) or size > len(dat1_data) - offset):
            raise ValueError(f'Truncated component payload at DAT1 byte {offset}')
        components.append(SceneComponent(
            instance_id, dat1.get_string(name_offset), type_id, flags, offset,
            bytes(dat1_data[offset:offset+size]) if size else b'', reserved))
    return tuple(components)
