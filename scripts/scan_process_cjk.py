import argparse
import ctypes
import csv
import re
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


def is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x3040 <= cp <= 0x30FF
        or 0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF
    )


def is_string_char(ch: str) -> bool:
    cp = ord(ch)
    if ch in "\t\r\n":
        return False
    if is_cjk(ch):
        return True
    if 0x20 <= cp <= 0x7E:
        return True
    if 0x3000 <= cp <= 0x303F:
        return True
    if 0xFF00 <= cp <= 0xFFEF:
        return True
    return ch in "、。！？「」『』（）【】《》…—·"


def extract_cjk_strings(text: str, min_chars: int, min_cjk: int):
    buf = []
    cjk_count = 0
    for ch in text:
        if is_string_char(ch):
            buf.append(ch)
            if is_cjk(ch):
                cjk_count += 1
        else:
            if len(buf) >= min_chars and cjk_count >= min_cjk:
                yield "".join(buf)
            buf = []
            cjk_count = 0
    if len(buf) >= min_chars and cjk_count >= min_cjk:
        yield "".join(buf)


def readable(mbi: MEMORY_BASIC_INFORMATION) -> bool:
    if mbi.State != MEM_COMMIT:
        return False
    if mbi.Protect & PAGE_GUARD:
        return False
    if mbi.Protect & PAGE_NOACCESS:
        return False
    return True


def read_region(handle, base: int, size: int, chunk_size: int):
    offset = 0
    overlap = 16
    prev_tail = b""
    while offset < size:
        to_read = min(chunk_size, size - offset)
        buf = ctypes.create_string_buffer(to_read)
        read = ctypes.c_size_t(0)
        ok = ReadProcessMemory(handle, ctypes.c_void_p(base + offset), buf, to_read, ctypes.byref(read))
        if ok and read.value:
            data = prev_tail + buf.raw[: read.value]
            yield base + offset - len(prev_tail), data
            prev_tail = data[-overlap:]
        else:
            prev_tail = b""
        offset += max(to_read, 1)


def scan_process(pid: int, args):
    handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), f"OpenProcess failed for PID {pid}")

    keywords = [k for k in args.contains if k]
    seen = set()
    rows = []
    try:
        address = 0x10000
        max_address = args.max_address
        mbi = MEMORY_BASIC_INFORMATION()
        while address < max_address:
            result = VirtualQueryEx(handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi))
            if not result:
                address += 0x10000
                continue

            base = int(mbi.BaseAddress or 0)
            size = int(mbi.RegionSize or 0)
            if size <= 0:
                address += 0x10000
                continue

            if readable(mbi):
                for chunk_base, data in read_region(handle, base, size, args.chunk_size):
                    decoded_variants = []
                    decoded_variants.append(("utf8", data.decode("utf-8", errors="ignore")))
                    decoded_variants.append(("gbk", data.decode("gbk", errors="ignore")))
                    decoded_variants.append(("utf16le", data.decode("utf-16le", errors="ignore")))
                    decoded_variants.append(("utf16le+1", data[1:].decode("utf-16le", errors="ignore")))

                    for encoding, text in decoded_variants:
                        for value in extract_cjk_strings(text, args.min_chars, args.min_cjk):
                            value = re.sub(r"\s+", " ", value).strip()
                            if len(value) > args.max_chars:
                                continue
                            if keywords and not any(k in value for k in keywords):
                                continue
                            key = (encoding, value)
                            if key in seen:
                                continue
                            seen.add(key)
                            rows.append(
                                {
                                    "encoding": encoding,
                                    "region_base": f"0x{base:08X}",
                                    "chunk_base": f"0x{max(chunk_base, 0):08X}",
                                    "text": value,
                                }
                            )
                            if len(rows) >= args.limit:
                                return rows

            next_address = base + size
            if next_address <= address:
                next_address = address + 0x10000
            address = next_address
    finally:
        CloseHandle(handle)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Scan a Windows process for CJK strings in UTF-8/GBK/UTF-16LE memory.")
    parser.add_argument("pid", type=int)
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--contains", action="append", default=[], help="Only keep strings containing this keyword; can repeat")
    parser.add_argument("--min-chars", type=int, default=4)
    parser.add_argument("--min-cjk", type=int, default=2)
    parser.add_argument("--max-chars", type=int, default=300)
    parser.add_argument("--limit", type=int, default=20000)
    parser.add_argument("--chunk-size", type=int, default=1024 * 1024)
    parser.add_argument("--max-address", type=lambda s: int(s, 0), default=0xFFFFFFFF)
    args = parser.parse_args()

    rows = scan_process(args.pid, args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["encoding", "region_base", "chunk_base", "text"], delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows: {output}")


if __name__ == "__main__":
    main()
