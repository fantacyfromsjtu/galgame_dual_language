import argparse
import shutil
import struct
import zlib
from pathlib import Path


HEADER_MAGIC = b"XP3\r\n \n\x1a\x8bg\x01"
INDEX_ENCODE_MASK = 0x07
INDEX_RAW = 0
INDEX_ZLIB = 1
INDEX_CONTINUE = 0x80


def read_u64(f):
    data = f.read(8)
    if len(data) != 8:
        raise EOFError("Unexpected EOF while reading u64")
    return struct.unpack("<Q", data)[0]


def read_index(path):
    with Path(path).open("rb") as f:
        if f.read(len(HEADER_MAGIC)) != HEADER_MAGIC:
            raise ValueError("Not an XP3 archive")

        while True:
            pointer_pos = f.tell()
            index_offset = read_u64(f)
            f.seek(index_offset)

            flag_pos = f.tell()
            flags = f.read(1)[0]
            index_size = read_u64(f)

            if flags & INDEX_CONTINUE:
                if (flags & INDEX_ENCODE_MASK) != INDEX_RAW or index_size != 0:
                    raise ValueError("Unsupported XP3 continuation index")
                continue

            method = flags & INDEX_ENCODE_MASK
            if method == INDEX_ZLIB:
                original_size = read_u64(f)
                compressed = f.read(index_size)
                index_data = bytearray(zlib.decompress(compressed))
                if len(index_data) != original_size:
                    raise ValueError("XP3 index size mismatch after decompression")
            elif method == INDEX_RAW:
                index_data = bytearray(f.read(index_size))
            else:
                raise ValueError(f"Unsupported XP3 index encoding: {method}")

            return {
                "pointer_pos": pointer_pos,
                "index_offset": index_offset,
                "flag_pos": flag_pos,
                "flags": flags,
                "index": index_data,
            }


def iter_chunks(buf, start=0, end=None):
    if end is None:
        end = len(buf)
    pos = start
    while pos + 12 <= end:
        chunk_type = bytes(buf[pos:pos + 4])
        chunk_len = struct.unpack_from("<Q", buf, pos + 4)[0]
        payload_start = pos + 12
        payload_end = payload_start + chunk_len
        if payload_end > end:
            raise ValueError(f"Chunk {chunk_type!r} overruns buffer")
        yield pos, chunk_type, payload_start, payload_end
        pos = payload_end
    if pos != end:
        raise ValueError("Trailing bytes after XP3 chunks")


def find_file_entry(index_data, entry_name):
    for file_pos, chunk_type, payload_start, payload_end in iter_chunks(index_data):
        if chunk_type != b"File":
            continue

        info = None
        segm = None
        adlr = None
        for sub_pos, sub_type, sub_start, sub_end in iter_chunks(index_data, payload_start, payload_end):
            if sub_type == b"info":
                name_len = struct.unpack_from("<H", index_data, sub_start + 20)[0]
                name_start = sub_start + 22
                name_end = name_start + name_len * 2
                name = bytes(index_data[name_start:name_end]).decode("utf-16le")
                info = {
                    "pos": sub_start,
                    "name": name,
                    "name_len": name_len,
                }
            elif sub_type == b"segm":
                segm = {"pos": sub_start, "end": sub_end}
            elif sub_type == b"adlr":
                adlr = {"pos": sub_start}

        if info and info["name"].lower() == entry_name.lower():
            return {
                "file_pos": file_pos,
                "payload_start": payload_start,
                "payload_end": payload_end,
                "info": info,
                "segm": segm,
                "adlr": adlr,
            }

    return None


def replace_entry(xp3_path, replacement_path, entry_name, output_path=None, backup_path=None):
    xp3_path = Path(xp3_path)
    replacement_path = Path(replacement_path)
    output_path = Path(output_path) if output_path else xp3_path

    if output_path.resolve() != xp3_path.resolve():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(xp3_path, output_path)
    elif backup_path:
        backup_path = Path(backup_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        if not backup_path.exists():
            shutil.copy2(xp3_path, backup_path)

    parsed = read_index(output_path)
    index_data = parsed["index"]
    entry = find_file_entry(index_data, entry_name)
    if not entry:
        raise ValueError(f"Entry not found in XP3 index: {entry_name}")
    if not entry["segm"]:
        raise ValueError(f"Entry has no segment chunk: {entry_name}")

    replacement = replacement_path.read_bytes()
    new_size = len(replacement)

    seg_pos = entry["segm"]["pos"]
    first_seg = struct.unpack_from("<IQQQ", index_data, seg_pos)
    seg_flags, seg_offset, old_original_size, old_archive_size = first_seg
    if seg_flags != 0:
        raise ValueError("Compressed or encrypted replacement target is not supported by this script")
    if new_size > old_archive_size:
        raise ValueError(
            f"Replacement is larger than the original segment: {new_size} > {old_archive_size}"
        )

    info_pos = entry["info"]["pos"]
    info_flags, info_original_size, info_archive_size = struct.unpack_from("<IQQ", index_data, info_pos)

    struct.pack_into("<QQ", index_data, info_pos + 4, new_size, new_size)
    struct.pack_into("<QQ", index_data, seg_pos + 12, new_size, new_size)

    checksum = zlib.adler32(replacement) & 0xFFFFFFFF
    if entry["adlr"]:
        struct.pack_into("<I", index_data, entry["adlr"]["pos"], checksum)

    compressed_index = zlib.compress(bytes(index_data))

    with output_path.open("r+b") as f:
        f.seek(seg_offset)
        f.write(replacement)
        pad = old_archive_size - new_size
        if pad:
            f.write(b"\x00" * pad)

        f.seek(0, 2)
        new_index_offset = f.tell()
        f.write(bytes([INDEX_ZLIB]))
        f.write(struct.pack("<Q", len(compressed_index)))
        f.write(struct.pack("<Q", len(index_data)))
        f.write(compressed_index)

        f.seek(parsed["pointer_pos"])
        f.write(struct.pack("<Q", new_index_offset))

    print(f"Patched {entry_name}")
    print(f"  target: {output_path}")
    print(f"  segment offset: {seg_offset}")
    print(f"  old info size: {info_original_size}/{info_archive_size}")
    print(f"  old seg size: {old_original_size}/{old_archive_size}")
    print(f"  new size: {new_size}")
    print(f"  new index offset: {new_index_offset}")
    print(f"  adler32: {checksum:08x}")


def main():
    parser = argparse.ArgumentParser(description="Replace one uncompressed hashed entry in an XP3 archive.")
    parser.add_argument("xp3")
    parser.add_argument("replacement")
    parser.add_argument("--entry-name", required=True)
    parser.add_argument("--output")
    parser.add_argument("--backup")
    args = parser.parse_args()

    replace_entry(
        args.xp3,
        args.replacement,
        args.entry_name,
        output_path=args.output,
        backup_path=args.backup,
    )


if __name__ == "__main__":
    main()
