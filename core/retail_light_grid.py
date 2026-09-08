"""Isolated execution of the verified build's cooked light-grid decoder.

Unicorn interprets copies of PE instructions in guest memory. This module
does not launch, attach to, inject into, or natively execute the game. Only
the system CRT's expf/logf are called on the host. All other external calls,
unmapped guest memory and excessive execution fail explicitly.

This optional evidence tool requires Windows and unicorn 2.1.4. It does not
establish scene residency/placement or equality with a captured GPU resource.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

import numpy as np

from core.light_grid_assets import decode_light_grid_brick


SUPPORTED_EXE_SHA256 = '51299faca61866cf10ea9035a15b8f22600a56557dd5ffc1aad390d5a54e6d82'


@dataclass(frozen=True)
class RetailLightGridBrick:
    records: np.ndarray
    fallback_scale: float
    changed_cells: int
    first_stage_exact: bool


class RetailLightGridDecoder:
    """Reusable bounded VM for one verified installed executable build."""
    STACK = 0x10000000
    OUTPUT = 0x20000000
    INPUT = 0x21000000
    INDICES = 0x22000000
    SCALAR = 0x22002000
    STOP = 0x23000000

    def __init__(self, executable: str | Path):
        try:
            import unicorn as uc
            import unicorn.x86_const as x86
        except ImportError as error:
            raise RuntimeError('Retail brick interpolation requires the optional unicorn package') from error
        if not hasattr(ctypes, 'WinDLL'):
            raise RuntimeError('This evidence decoder requires the Windows CRT')
        self.image = Path(executable).read_bytes()
        if hashlib.sha256(self.image).hexdigest() != SUPPORTED_EXE_SHA256:
            raise ValueError('Executable differs from the build verified for this decoder')
        pe = struct.unpack_from('<I', self.image, 0x3C)[0]
        section_count = struct.unpack_from('<H', self.image, pe + 6)[0]
        optional_size = struct.unpack_from('<H', self.image, pe + 20)[0]
        self.base = struct.unpack_from('<Q', self.image, pe + 24 + 24)[0]
        table = pe + 24 + optional_size
        self.sections = []
        for i in range(section_count):
            row = table + i * 40
            name = self.image[row:row + 8].rstrip(b'\0')
            _, rva, raw_size, raw_offset = struct.unpack_from('<4I', self.image, row + 8)
            self.sections.append((name, rva, raw_size, raw_offset))
        self.uc, self.x86 = uc, x86
        self.vm = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_64)
        self.errors = []
        self.crt = ctypes.WinDLL('ucrtbase.dll')
        self.math_functions = {}
        for name in ('expf', 'logf'):
            fn = getattr(self.crt, name)
            fn.argtypes = [ctypes.c_float]
            fn.restype = ctypes.c_float
            self.math_functions[name] = fn
        read_write = uc.UC_PROT_READ | uc.UC_PROT_WRITE
        self.vm.mem_map(self.STACK, 0x400000, read_write)
        for address, size in ((self.OUTPUT, 0x10000), (self.INPUT, 0x20000), (self.INDICES, 0x3000)):
            self.vm.mem_map(address, size, read_write)
        self.vm.mem_map(self.STOP, 0x1000, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        self.vm.hook_add(uc.UC_HOOK_MEM_UNMAPPED, self._unmapped)
        self.vm.hook_add(uc.UC_HOOK_CODE, self._stack_probe, begin=0x142D200C0, end=0x142D200C0)
        self.vm.hook_add(uc.UC_HOOK_CODE, self._math_thunk, begin=0x142D27B50, end=0x142D27C70)

    def _offset(self, va):
        for _, rva, size, offset in self.sections:
            if rva <= va - self.base < rva + size:
                return offset + va - self.base - rva
        raise ValueError(f'Guest address outside file-backed PE sections: {va:#x}')

    def _unmapped(self, vm, access, address, size, value, user):
        if access not in (self.uc.UC_MEM_READ_UNMAPPED, self.uc.UC_MEM_FETCH_UNMAPPED):
            self.errors.append(f'Unexpected guest memory write: {address:#x}')
            return False
        page = address & ~4095
        try:
            offset = self._offset(page)
            name = next(s[0] for s in self.sections if s[1] <= page - self.base < s[1] + s[2])
            protection = self.uc.UC_PROT_READ | (self.uc.UC_PROT_EXEC if name == b'.text' else 0)
            vm.mem_map(page, 4096, protection)
            vm.mem_write(page, self.image[offset:offset + 4096])
            return True
        except Exception as error:
            self.errors.append(str(error))
            return False

    def _return(self):
        stack = self.vm.reg_read(self.x86.UC_X86_REG_RSP)
        target = struct.unpack('<Q', self.vm.mem_read(stack, 8))[0]
        self.vm.reg_write(self.x86.UC_X86_REG_RSP, stack + 8)
        self.vm.reg_write(self.x86.UC_X86_REG_RIP, target)

    def _stack_probe(self, vm, address, size, user):
        # __chkstk needs no host operation: the complete guest stack is mapped.
        self._return()

    def _math_thunk(self, vm, address, size, user):
        offset = self._offset(address)
        if self.image[offset:offset + 2] != b'\xff\x25':
            raise RuntimeError(f'Unexpected CRT thunk at {address:#x}')
        slot = address + 6 + struct.unpack_from('<i', self.image, offset + 2)[0]
        rva = struct.unpack_from('<Q', self.image, self._offset(slot))[0]
        name_offset = self._offset(self.base + rva) + 2
        name = self.image[name_offset:name_offset + 80].split(b'\0')[0].decode()
        if name not in self.math_functions:
            raise RuntimeError(f'Unsupported decoder external call: {name}')
        argument = struct.unpack('<f', struct.pack('<I', vm.reg_read(self.x86.UC_X86_REG_XMM0) & 0xFFFFFFFF))[0]
        result = self.math_functions[name](argument)
        vm.reg_write(self.x86.UC_X86_REG_XMM0, struct.unpack('<I', struct.pack('<f', result))[0])
        self._return()

    def _execute(self, entry, rcx, rdx=0, r8=0):
        vm, x = self.vm, self.x86
        self.errors.clear()
        stack = self.STACK + 0x400000 - 0x108
        vm.mem_write(stack, struct.pack('<Q', self.STOP))
        vm.reg_write(x.UC_X86_REG_RSP, stack)
        vm.reg_write(x.UC_X86_REG_MXCSR, 0x1F80)
        vm.reg_write(x.UC_X86_REG_RCX, rcx)
        vm.reg_write(x.UC_X86_REG_RDX, rdx)
        vm.reg_write(x.UC_X86_REG_R8, r8)
        try:
            vm.emu_start(entry, self.STOP, timeout=60000000, count=50000000)
        except Exception as error:
            address = vm.reg_read(x.UC_X86_REG_RIP)
            raise RuntimeError(f'Guest decoder stopped at {address:#x}: {error}; {self.errors}') from error
        if vm.reg_read(x.UC_X86_REG_RIP) != self.STOP:
            raise RuntimeError('Guest decoder exceeded its execution budget')

    def _run(self, raw, interpolate):
        if len(raw) > 0x20000:
            raise ValueError('Brick exceeds the guest input allocation')
        vm, x = self.vm, self.x86
        vm.mem_write(self.INPUT, raw)
        vm.mem_write(self.OUTPUT, bytes(65536))
        vm.mem_write(self.INDICES, bytes(0x3000))
        self._execute(0x14109DA40, self.OUTPUT, self.INPUT, int(interpolate))
        result = bytes(vm.mem_read(self.OUTPUT, 65536))
        scalar_bits = vm.reg_read(x.UC_X86_REG_XMM0) & 0xFFFFFFFF
        return np.frombuffer(result, dtype='<u4').reshape(4096, 4).copy(), struct.unpack('<f', struct.pack('<I', scalar_bits))[0]

    def default_record(self) -> np.ndarray:
        """Exact initialization used for the manager's permanent fallback brick.

        0x1410A3300 initializes a descriptor with 0x1410A13D0, packs it with
        0x14109EC00 (R8=0), and repeats this record across 4096 cells.
        """
        self.vm.mem_write(self.INPUT, bytes(128))
        self.vm.mem_write(self.OUTPUT, bytes(16))
        self._execute(0x1410A13D0, self.INPUT)
        self._execute(0x14109EC00, self.INPUT, self.OUTPUT, 0)
        return np.frombuffer(bytes(self.vm.mem_read(self.OUTPUT, 16)), dtype='<u4').copy()

    def decode(self, raw: bytes) -> RetailLightGridBrick:
        first = decode_light_grid_brick(raw)
        direct, direct_scalar = self._run(raw, False)
        if not np.array_equal(direct, first.records):
            raise RuntimeError('Independent first-stage decoder disagrees with retail instructions')
        filled, scalar = self._run(raw, True)
        if scalar != direct_scalar or not np.isfinite(scalar):
            raise RuntimeError('Unexpected interpolation fallback scalar')
        # The retail wrapper only fills source kinds 0/1; authored cells survive.
        if not np.array_equal(filled[first.cell_kinds >= 2], direct[first.cell_kinds >= 2]):
            raise RuntimeError('Retail interpolation unexpectedly changed authored samples')
        return RetailLightGridBrick(filled, scalar, int(np.any(filled != direct, axis=1).sum()), True)
