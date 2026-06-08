import argparse
import csv
import re
from pathlib import Path


def is_cjk(ch):
    cp = ord(ch)
    return (
        0x3040 <= cp <= 0x30FF
        or 0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF
    )


def is_text_char(ch):
    cp = ord(ch)
    if ch in "\r\n\t":
        return False
    if is_cjk(ch):
        return True
    if 0x20 <= cp <= 0x7E:
        return True
    if 0x3000 <= cp <= 0x303F:
        return True
    if 0xFF00 <= cp <= 0xFFEF:
        return True
    return ch in "，。！？、；：「」『』（）《》“”……—"


def clean_text(text):
    text = text.replace("\x00", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_utf8(data, min_chars, min_cjk):
    # The translated scenario text appears as UTF-8 strings separated by NULs
    # or binary control bytes. Segment first, then decode; this avoids a slow
    # byte-by-byte walk over large arbitrary memory dumps.
    for match in re.finditer(rb"[^\x00-\x1F]{2,}", data):
        decoded = match.group(0).decode("utf-8", errors="ignore")
        buf = []
        cjk_count = 0
        start = match.start()
        span_start = start
        byte_cursor = start
        for ch in decoded:
            if is_text_char(ch):
                buf.append(ch)
                if is_cjk(ch):
                    cjk_count += 1
                byte_cursor += len(ch.encode("utf-8", errors="ignore"))
            else:
                text = clean_text("".join(buf))
                if len(text) >= min_chars and cjk_count >= min_cjk:
                    yield span_start, "utf8", text
                buf = []
                cjk_count = 0
                byte_cursor += len(ch.encode("utf-8", errors="ignore"))
                span_start = byte_cursor

        text = clean_text("".join(buf))
        if len(text) >= min_chars and cjk_count >= min_cjk:
            yield span_start, "utf8", text


def extract_utf16le(data, min_chars, min_cjk):
    for base_shift in (0, 1):
        i = base_shift
        n = len(data) - 1
        while i < n:
            start = i
            buf = []
            cjk_count = 0
            while i < n:
                cp = data[i] | (data[i + 1] << 8)
                ch = chr(cp)
                if not is_text_char(ch):
                    break
                buf.append(ch)
                if is_cjk(ch):
                    cjk_count += 1
                i += 2
            text = clean_text("".join(buf))
            if len(text) >= min_chars and cjk_count >= min_cjk:
                yield start, "utf16le" if base_shift == 0 else "utf16le+1", text
            i = max(i + 2, start + 2)


def main():
    parser = argparse.ArgumentParser(description="Extract CJK-looking strings from a binary file.")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--min-chars", type=int, default=3)
    parser.add_argument("--min-cjk", type=int, default=2)
    parser.add_argument("--max-chars", type=int, default=500)
    parser.add_argument("--encodings", default="utf8,utf16le")
    args = parser.parse_args()

    data = Path(args.input).read_bytes()
    rows = []
    encodings = {value.strip().lower() for value in args.encodings.split(",")}
    if "utf8" in encodings:
        rows.extend(extract_utf8(data, args.min_chars, args.min_cjk))
    if "utf16le" in encodings:
        rows.extend(extract_utf16le(data, args.min_chars, args.min_cjk))

    seen = set()
    output_rows = []
    for offset, encoding, text in sorted(rows, key=lambda row: (row[0], row[1])):
        if len(text) > args.max_chars:
            continue
        key = (encoding, offset, text)
        if key in seen:
            continue
        seen.add(key)
        output_rows.append(
            {
                "offset": f"0x{offset:X}",
                "encoding": encoding,
                "text": text,
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["offset", "encoding", "text"], delimiter="\t")
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"Wrote {len(output_rows)} rows: {output}")


if __name__ == "__main__":
    main()
