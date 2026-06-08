import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
OpenProcess.restype = wintypes.HANDLE

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

VirtualQueryEx = kernel32.VirtualQueryEx
VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_size_t,
]
VirtualQueryEx.restype = ctypes.c_size_t

ReadProcessMemory = kernel32.ReadProcessMemory
ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
ReadProcessMemory.restype = wintypes.BOOL


def read_memory(handle, address, size):
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = ReadProcessMemory(handle, ctypes.c_void_p(address), buf, size, ctypes.byref(read))
    if not ok or not read.value:
        return b""
    return buf.raw[: read.value]


def main():
    parser = argparse.ArgumentParser(description="Dump the committed readable memory region containing an address.")
    parser.add_argument("pid", type=int)
    parser.add_argument("address", type=lambda s: int(s, 0))
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--max-size", type=lambda s: int(s, 0), default=0x4000000)
    args = parser.parse_args()

    handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, args.pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), f"OpenProcess failed for PID {args.pid}")

    try:
        mbi = MEMORY_BASIC_INFORMATION()
        result = VirtualQueryEx(handle, ctypes.c_void_p(args.address), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not result:
            raise OSError(ctypes.get_last_error(), f"VirtualQueryEx failed at 0x{args.address:08X}")

        base = int(mbi.BaseAddress or 0)
        size = int(mbi.RegionSize or 0)
        if mbi.State != MEM_COMMIT or (mbi.Protect & PAGE_GUARD) or (mbi.Protect & PAGE_NOACCESS):
            raise RuntimeError(f"Region is not readable: state=0x{mbi.State:X} protect=0x{mbi.Protect:X}")
        if size > args.max_size:
            size = args.max_size

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("wb") as f:
            offset = 0
            while offset < size:
                chunk_size = min(1024 * 1024, size - offset)
                data = read_memory(handle, base + offset, chunk_size)
                if data:
                    f.write(data)
                else:
                    f.write(b"\x00" * chunk_size)
                offset += chunk_size

        print(f"base=0x{base:08X}")
        print(f"size=0x{size:X}")
        print(f"protect=0x{mbi.Protect:X}")
        print(f"type=0x{mbi.Type:X}")
        print(f"hit_offset=0x{args.address - base:X}")
        print(f"wrote={output}")
    finally:
        CloseHandle(handle)


if __name__ == "__main__":
    main()
