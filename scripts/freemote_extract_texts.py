import argparse
import csv
import json
import re
from pathlib import Path


RUBY_RE = re.compile(r"\[([^\]]+)\]([^\[]?)")


def strip_ruby(text: str) -> str:
    return RUBY_RE.sub(lambda m: m.group(2), text or "")


def best_plain_text(block):
    # FreeMote/M2 scenario text blocks usually look like:
    # [display_name_override, raw_text_with_ruby, char_count, kana_text?, plain_text?]
    if isinstance(block, list) and len(block) >= 5 and isinstance(block[4], str):
        return block[4]
    if isinstance(block, list) and len(block) >= 2 and isinstance(block[1], str):
        return strip_ruby(block[1])
    return ""


def extract_voice(voice_field):
    if not isinstance(voice_field, list):
        return ""
    voices = []
    for item in voice_field:
        if isinstance(item, dict) and item.get("voice"):
            voices.append(str(item["voice"]))
    return ",".join(voices)


def iter_text_rows(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    scenario_name = data.get("name") or path.stem

    for scene_index, scene in enumerate(data.get("scenes", [])):
        scene_label = scene.get("label", "")
        texts = scene.get("texts") or []
        for text_index, record in enumerate(texts, start=1):
            if not isinstance(record, list) or len(record) < 2:
                continue

            speaker = record[0] if isinstance(record[0], str) else ""
            blocks = record[1] if isinstance(record[1], list) else []
            voice = extract_voice(record[2] if len(record) >= 3 else None)

            for block_index, block in enumerate(blocks):
                if not isinstance(block, list) or len(block) < 2:
                    continue

                display_name = block[0] if isinstance(block[0], str) else ""
                raw_text = block[1] if isinstance(block[1], str) else ""
                if not raw_text:
                    continue

                yield {
                    "source_json": str(path),
                    "scenario": scenario_name,
                    "scene_index": scene_index,
                    "scene_label": scene_label,
                    "text_id": text_index,
                    "block_index": block_index,
                    "speaker": speaker,
                    "display_name": display_name,
                    "voice": voice,
                    "raw_text": raw_text,
                    "plain_text": best_plain_text(block),
                }


def find_json_inputs(inputs):
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            for json_path in sorted(path.rglob("*.json")):
                if not json_path.name.endswith(".resx.json"):
                    yield json_path
        elif path.suffix.lower() == ".json" and not path.name.endswith(".resx.json"):
            yield path


def main():
    parser = argparse.ArgumentParser(description="Extract text rows from FreeMote-decompiled M2/KRKR PSB scenario JSON.")
    parser.add_argument("inputs", nargs="+", help="JSON files or directories containing FreeMote .ks.json files")
    parser.add_argument("-o", "--output", required=True, help="Output TSV path")
    args = parser.parse_args()

    rows = []
    for json_path in find_json_inputs(args.inputs):
        rows.extend(iter_text_rows(json_path))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source_json",
        "scenario",
        "scene_index",
        "scene_label",
        "text_id",
        "block_index",
        "speaker",
        "display_name",
        "voice",
        "raw_text",
        "plain_text",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows: {output}")


if __name__ == "__main__":
    main()
