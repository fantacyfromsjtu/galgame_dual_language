import argparse
import os
import struct
import zlib
from pathlib import Path


HEADER_MAGIC = b"XP3\r\n \n\x1a\x8bg\x01"


def chunk(name, payload):
    return name.encode("ascii") + struct.pack("<Q", len(payload)) + payload


def build_file_chunk(name, offset, original_size, compressed_size, compressed):
    encoded_name = name.encode("utf-16le")
    info = (
        struct.pack("<IQQH", 0, original_size, compressed_size, len(name))
        + encoded_name
    )
    segm = struct.pack(
        "<IQQQ",
        1 if compressed else 0,
        offset,
        original_size,
        compressed_size,
    )
    adlr = struct.pack("<I", 0)
    return chunk("File", chunk("info", info) + chunk("segm", segm) + chunk("adlr", adlr))


def iter_files(root):
    root = Path(root)
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix().replace("/", "\\")
            yield path, rel


def pack_xp3(input_dir, output):
    input_dir = Path(input_dir)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    file_chunks = []
    with output.open("wb") as f:
        f.write(HEADER_MAGIC)
        f.write(struct.pack("<Q", 0))

        for path, rel in iter_files(input_dir):
            data = path.read_bytes()
            compressed = path.suffix.lower() != ".mpg"
            offset = f.tell()
            if compressed:
                packed = zlib.compress(data)
            else:
                packed = data
            f.write(packed)
            file_chunks.append(
                build_file_chunk(
                    rel,
                    offset,
                    len(data),
                    len(packed),
                    compressed,
                )
            )

        index_payload = b"".join(file_chunks)
        index = b"\x00" + struct.pack("<Q", len(index_payload)) + index_payload
        index_offset = f.tell()
        f.write(index)

        f.seek(len(HEADER_MAGIC), os.SEEK_SET)
        f.write(struct.pack("<Q", index_offset))

    print(f"Packed {len(file_chunks)} files: {output}")


def main():
    parser = argparse.ArgumentParser(description="Create a simple Kirikiri XP3 archive.")
    parser.add_argument("input_dir")
    parser.add_argument("output")
    args = parser.parse_args()
    pack_xp3(args.input_dir, args.output)


if __name__ == "__main__":
    main()
