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


def readable(mbi):
    return (
        mbi.State == MEM_COMMIT
        and not (mbi.Protect & PAGE_GUARD)
        and not (mbi.Protect & PAGE_NOACCESS)
    )


def read_memory(handle, address, size):
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = ReadProcessMemory(handle, ctypes.c_void_p(address), buf, size, ctypes.byref(read))
    if not ok or not read.value:
        return b""
    return buf.raw[: read.value]


def iter_regions(handle, max_address):
    address = 0x10000
    mbi = MEMORY_BASIC_INFORMATION()
    while address < max_address:
        result = VirtualQueryEx(handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not result:
            address += 0x10000
            continue

        base = int(mbi.BaseAddress or 0)
        size = int(mbi.RegionSize or 0)
        if size > 0 and readable(mbi):
            yield base, size

        next_address = base + max(size, 0x10000)
        if next_address <= address:
            next_address = address + 0x10000
        address = next_address


def make_needles(terms):
    encodings = ["utf-8", "gbk", "utf-16le"]
    needles = []
    for term in terms:
        for enc in encodings:
            try:
                data = term.encode(enc)
            except UnicodeEncodeError:
                continue
            needles.append((term, enc, data))
    return needles


def decode_context(data):
    variants = []
    for enc in ["utf-8", "gbk", "utf-16le"]:
        try:
            text = data.decode(enc, errors="replace")
        except Exception:
            continue
        text = text.replace("\x00", "\\0")
        variants.append((enc, text))
    return variants


def main():
    parser = argparse.ArgumentParser(description="Search process memory for exact text byte patterns.")
    parser.add_argument("pid", type=int)
    parser.add_argument("terms", nargs="+")
    parser.add_argument("-o", "--output-dir", default="_dual_sub_work/extract/memory_hits")
    parser.add_argument("--context", type=int, default=0x4000)
    parser.add_argument("--chunk-size", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-address", type=lambda s: int(s, 0), default=0xFFFFFFFF)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, args.pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), f"OpenProcess failed for PID {args.pid}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    needles = make_needles(args.terms)
    hits = []

    try:
        for base, size in iter_regions(handle, args.max_address):
            overlap = max((len(n[2]) for n in needles), default=1) + args.context
            offset = 0
            tail = b""
            while offset < size:
                to_read = min(args.chunk_size, size - offset)
                data = read_memory(handle, base + offset, to_read)
                if not data:
                    tail = b""
                    offset += max(to_read, 1)
                    continue

                chunk_base = base + offset - len(tail)
                haystack = tail + data
                for term, enc, needle in needles:
                    pos = haystack.find(needle)
                    while pos >= 0:
                        address = chunk_base + pos
                        hit = (term, enc, address)
                        if hit not in hits:
                            hits.append(hit)
                            start = max(0, pos - args.context)
                            end = min(len(haystack), pos + len(needle) + args.context)
                            context = haystack[start:end]
                            stem = f"hit_{len(hits):03d}_{address:08X}_{enc}"
                            (out_dir / f"{stem}.bin").write_bytes(context)
                            with (out_dir / f"{stem}.txt").open("w", encoding="utf-8", newline="") as f:
                                f.write(f"term={term}\nencoding={enc}\naddress=0x{address:08X}\n")
                                for dec_enc, text in decode_context(context):
                                    f.write(f"\n--- decode:{dec_enc} ---\n{text}\n")
                            print(f"HIT {len(hits)} term={term!r} enc={enc} address=0x{address:08X}")
                            if len(hits) >= args.limit:
                                return
                        pos = haystack.find(needle, pos + 1)

                tail = haystack[-overlap:]
                offset += max(to_read, 1)
    finally:
        CloseHandle(handle)

    print(f"Total hits: {len(hits)}")


if __name__ == "__main__":
    main()
