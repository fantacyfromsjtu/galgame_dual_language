import argparse
import csv
import json
import re
from pathlib import Path


RUBY_RE = re.compile(r"\[([^\]]+)\]([^\[]?)")
TEXT_CONTROL_RE = re.compile(r"^(?:%\d+;)+")
FONT_TAG_RE = re.compile(r"\[(?:font|resetfont)\b[^\]]*\]", re.IGNORECASE)


def strip_ruby(text):
    return RUBY_RE.sub(lambda match: match.group(2), text or "")


def strip_font_tags(text):
    return FONT_TAG_RE.sub("", text or "")


def visible_len(raw_text, chs_text):
    visible = strip_ruby(strip_font_tags(TEXT_CONTROL_RE.sub("", raw_text or "")))
    if chs_text:
        visible += "\n" + strip_font_tags(chs_text)
    return len(visible)


def font_wrap(text, face):
    if not face:
        return text
    return f"[font face='{face}']{text}[resetfont]"


def bilingual(original, chs, chs_font_face=None):
    if not chs:
        return original
    wrapped_chs = font_wrap(chs, chs_font_face)
    if original.endswith("\n" + wrapped_chs):
        return original
    return original + "\n" + wrapped_chs


def read_alignment(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    result = {}
    for row in rows:
        key = (int(row["scene_index"]), int(row["text_id"]), int(row["block_index"]))
        result[key] = row.get("chs_text", "").strip()
    return result


def apply_patch_to_json(input_json, alignment, output_json, chs_font_face=None):
    data = json.loads(Path(input_json).read_text(encoding="utf-8-sig"))
    changed = 0
    skipped = 0

    for scene_index, scene in enumerate(data.get("scenes", [])):
        texts = scene.get("texts") or []
        for text_id, record in enumerate(texts, start=1):
            if not isinstance(record, list) or len(record) < 2:
                continue
            blocks = record[1] if isinstance(record[1], list) else []
            for block_index, block in enumerate(blocks):
                key = (scene_index, text_id, block_index)
                chs = alignment.get(key, "")
                if not chs:
                    skipped += 1
                    continue
                if not isinstance(block, list) or len(block) < 3 or not isinstance(block[1], str):
                    skipped += 1
                    continue

                raw = block[1]
                block[1] = bilingual(raw, chs, chs_font_face)
                if isinstance(block[2], int):
                    block[2] = visible_len(raw, chs)
                for extra_index in (3, 4):
                    if len(block) > extra_index and isinstance(block[extra_index], str):
                        block[extra_index] = bilingual(block[extra_index], chs, chs_font_face)
                changed += 1

    output = Path(output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Changed {changed} text blocks; skipped {skipped}; wrote {output}")


def main():
    parser = argparse.ArgumentParser(description="Apply aligned Chinese text to a FreeMote scenario JSON as bilingual text.")
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--alignment", required=True)
    parser.add_argument("--chs-font-face", default="", help="Optional KAG font face used only for appended Chinese lines.")
    parser.add_argument("-o", "--output-json", required=True)
    args = parser.parse_args()

    alignment = read_alignment(args.alignment)
    apply_patch_to_json(args.input_json, alignment, args.output_json, args.chs_font_face or None)


if __name__ == "__main__":
    main()
