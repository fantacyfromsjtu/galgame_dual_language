import argparse
import csv
import json
import re
import shutil
from collections import Counter
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path.cwd()

RUBY_RE = re.compile(r"\[([^\]]+)\]([^\[]?)")
TEXT_CONTROL_RE = re.compile(r"^(?:%\d+;)+")
FONT_TAG_RE = re.compile(r"\[(?:font|resetfont)\b[^\]]*\]", re.IGNORECASE)


def assert_safe_clean_path(path: Path):
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise ValueError(f"Refusing to delete unsafe output directory: {resolved}")


def strip_ruby(text):
    return RUBY_RE.sub(lambda match: match.group(2), text or "")


def strip_font_tags(text):
    return FONT_TAG_RE.sub("", text or "")


def strip_controls(text):
    return TEXT_CONTROL_RE.sub("", text or "")


def best_plain_text(block):
    if isinstance(block, list) and len(block) >= 5 and isinstance(block[4], str):
        return block[4]
    if isinstance(block, list) and len(block) >= 2 and isinstance(block[1], str):
        return strip_ruby(block[1])
    return ""


def visible_len(raw_text, chs_text):
    visible = strip_ruby(strip_font_tags(strip_controls(raw_text or "")))
    if chs_text:
        visible += "\n" + strip_font_tags(chs_text)
    return len(visible)


def extract_voice(voice_field):
    if not isinstance(voice_field, list):
        return ""
    voices = []
    for item in voice_field:
        if isinstance(item, dict) and item.get("voice"):
            voices.append(str(item["voice"]))
    return ",".join(voices)


def iter_text_rows(data, source_json):
    scenario_name = data.get("name") or Path(source_json).stem
    for scene_index, scene in enumerate(data.get("scenes", [])):
        scene_label = scene.get("label", "")
        texts = scene.get("texts") or []
        for text_id, record in enumerate(texts, start=1):
            if not isinstance(record, list) or len(record) < 2:
                continue
            speaker = record[0] if isinstance(record[0], str) else ""
            voice = extract_voice(record[2] if len(record) >= 3 else None)
            blocks = record[1] if isinstance(record[1], list) else []
            for block_index, block in enumerate(blocks):
                if not isinstance(block, list) or len(block) < 2 or not isinstance(block[1], str):
                    continue
                if not block[1]:
                    continue
                yield {
                    "source_json": str(source_json),
                    "scenario": scenario_name,
                    "scene_index": scene_index,
                    "scene_label": scene_label,
                    "text_id": text_id,
                    "block_index": block_index,
                    "speaker": speaker,
                    "display_name": block[0] if isinstance(block[0], str) else "",
                    "voice": voice,
                    "raw_text": block[1],
                    "plain_text": best_plain_text(block),
                    "block": block,
                }


def read_map(map_path):
    with map_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return sorted(rows, key=lambda row: row.get("json_name", ""))


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_tsv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_overrides(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def join_text(left, right):
    left = left or ""
    right = right or ""
    if not left:
        return right
    if not right:
        return left
    return left + "\n" + right


def merge_block_text(target_block, extra_block):
    if not isinstance(target_block, list) or not isinstance(extra_block, list):
        return
    for index in (1, 3, 4):
        if len(extra_block) > index and isinstance(extra_block[index], str):
            while len(target_block) <= index:
                target_block.append("")
            if isinstance(target_block[index], str):
                target_block[index] = join_text(target_block[index], extra_block[index])
    if len(target_block) > 2 and isinstance(target_block[2], int):
        target_block[2] = len(strip_ruby(strip_controls(target_block[1] if len(target_block) > 1 else "")))


def apply_overrides(data, scenario_name, overrides):
    applied = []
    for override in overrides:
        prefix = override.get("scenario_prefix", "")
        if prefix and not scenario_name.startswith(prefix):
            continue
        scene_index = int(override["scene_index"])
        text_ids_value = override.get("translated_text_ids") or override.get("chs_text_ids") or ""
        text_ids = [int(item.strip()) for item in text_ids_value.split(",") if item.strip()]
        if len(text_ids) < 2:
            continue
        scenes = data.get("scenes", [])
        if scene_index >= len(scenes):
            raise ValueError(f"Override scene out of range for {scenario_name}: {scene_index}")
        texts = scenes[scene_index].get("texts") or []
        indexes = [text_id - 1 for text_id in text_ids]
        if any(index < 0 or index >= len(texts) for index in indexes):
            raise ValueError(f"Override text id out of range for {scenario_name}: {text_ids}")
        target = texts[indexes[0]]
        if not isinstance(target, list) or len(target) < 2:
            raise ValueError(f"Override target is not a text record for {scenario_name}: {text_ids[0]}")
        target_blocks = target[1] if isinstance(target[1], list) else []
        for extra_index in indexes[1:]:
            extra = texts[extra_index]
            extra_blocks = extra[1] if isinstance(extra, list) and len(extra) > 1 and isinstance(extra[1], list) else []
            if len(target_blocks) == 1 and len(extra_blocks) == 1:
                merge_block_text(target_blocks[0], extra_blocks[0])
            else:
                target_blocks.extend(extra_blocks)
        for extra_index in sorted(indexes[1:], reverse=True):
            del texts[extra_index]
        applied.append(override.get("note", "") or f"merged chs text ids {text_ids}")
    return applied


def compare_scenario(map_row, orig_dir, translated_dir, overrides):
    json_name = map_row["json_name"] + ".json"
    orig_path = orig_dir / json_name
    chs_path = translated_dir / json_name
    rows = []
    errors = []

    if not orig_path.exists():
        return rows, [f"missing_orig_json:{json_name}"], None, None, None
    if not chs_path.exists():
        return rows, [f"missing_translated_json:{json_name}"], None, None, None

    orig_data = load_json(orig_path)
    chs_data = load_json(chs_path)
    override_notes = apply_overrides(chs_data, map_row["json_name"], overrides)
    orig_rows = list(iter_text_rows(orig_data, orig_path))
    chs_rows = list(iter_text_rows(chs_data, chs_path))

    if len(orig_rows) != len(chs_rows):
        errors.append(f"row_count_mismatch:{len(orig_rows)}!={len(chs_rows)}")

    for index in range(max(len(orig_rows), len(chs_rows))):
        orig = orig_rows[index] if index < len(orig_rows) else None
        chs = chs_rows[index] if index < len(chs_rows) else None
        status = "ok"
        severity = "ok"
        notes = []
        key = None

        if orig:
            key = (orig["scene_index"], orig["text_id"], orig["block_index"])
        if chs:
            chs_key = (chs["scene_index"], chs["text_id"], chs["block_index"])
            if key is None:
                key = chs_key
            elif key != chs_key:
                status = "key_mismatch"
                severity = "fatal"
                notes.append(f"chs_key={chs_key}")

        if orig is None or chs is None:
            status = "missing_row"
            severity = "fatal"
        elif orig["voice"] != chs["voice"]:
            status = "voice_mismatch"
            severity = "fatal"
            notes.append(f"chs_voice={chs['voice']}")
        elif not chs["plain_text"]:
            status = "empty_translation"
            severity = "warn"
        elif orig["plain_text"] == chs["plain_text"]:
            status = "same_text"
            severity = "warn"
        elif orig["speaker"] != chs["speaker"]:
            status = "speaker_diff"
            severity = "warn"
            notes.append(f"chs_speaker={chs['speaker']}")
        elif orig["display_name"] != chs["display_name"]:
            status = "display_name_diff"
            severity = "info"
            notes.append(f"chs_display={chs['display_name']}")

        row = {
            "scenario": map_row["json_name"],
            "storage_name": map_row.get("storage_name", ""),
            "row_index": index,
            "scene_index": key[0] if key else "",
            "text_id": key[1] if key else "",
            "block_index": key[2] if key else "",
            "severity": severity,
            "status": status,
            "orig_speaker": orig["speaker"] if orig else "",
            "chs_speaker": chs["speaker"] if chs else "",
            "orig_display_name": orig["display_name"] if orig else "",
            "chs_display_name": chs["display_name"] if chs else "",
            "orig_voice": orig["voice"] if orig else "",
            "chs_voice": chs["voice"] if chs else "",
            "orig_text": orig["plain_text"] if orig else "",
            "chs_text": chs["plain_text"] if chs else "",
                "notes": ";".join(notes + override_notes),
        }
        rows.append(row)

    return rows, errors, orig_data, chs_data, orig_path


def append_bilingual(orig_data, chs_data):
    changed = 0
    skipped = 0
    select_changed = 0
    chs_by_key = {
        (row["scene_index"], row["text_id"], row["block_index"]): row["plain_text"]
        for row in iter_text_rows(chs_data, "<chs>")
    }

    for row in iter_text_rows(orig_data, "<orig>"):
        key = (row["scene_index"], row["text_id"], row["block_index"])
        chs_text = (chs_by_key.get(key) or "").strip()
        block = row["block"]
        if not chs_text or not isinstance(block, list) or len(block) < 3:
            skipped += 1
            continue
        raw = block[1]
        bilingual_raw = raw if raw.endswith("\n" + chs_text) else raw + "\n" + chs_text
        block[1] = bilingual_raw
        if isinstance(block[2], int):
            block[2] = visible_len(raw, chs_text)
        for extra_index in (3, 4):
            if len(block) > extra_index and isinstance(block[extra_index], str):
                extra = block[extra_index]
                block[extra_index] = extra if extra.endswith("\n" + chs_text) else extra + "\n" + chs_text
        changed += 1

    orig_scenes = orig_data.get("scenes", [])
    chs_scenes = chs_data.get("scenes", [])
    for scene_index, orig_scene in enumerate(orig_scenes):
        if scene_index >= len(chs_scenes):
            continue
        chs_scene = chs_scenes[scene_index]
        orig_selects = orig_scene.get("selects") or []
        chs_selects = chs_scene.get("selects") or []
        if not orig_selects or not chs_selects or len(orig_selects) != len(chs_selects):
            continue
        for orig_sel, chs_sel in zip(orig_selects, chs_selects):
            if not isinstance(orig_sel, dict) or not isinstance(chs_sel, dict):
                continue
            for key in ("selidx", "storage", "target", "tag"):
                if orig_sel.get(key) != chs_sel.get(key):
                    break
            else:
                chs_text = chs_sel.get("text")
                if isinstance(chs_text, str) and chs_text and orig_sel.get("text") != chs_text:
                    orig_sel["text"] = chs_text
                    select_changed += 1

    return changed, skipped, select_changed


def main():
    parser = argparse.ArgumentParser(description="Audit and apply bilingual text using original/translated FreeMote JSON.")
    parser.add_argument("--map", default=str(TOOL_ROOT / "work" / "scenario_map.tsv"))
    parser.add_argument("--orig-json-dir", default=str(TOOL_ROOT / "work" / "orig_json"))
    parser.add_argument("--translated-json-dir", default=str(TOOL_ROOT / "work" / "translated_json"))
    parser.add_argument("--chs-json-dir", help="Deprecated alias for --translated-json-dir.")
    parser.add_argument("--report", default=str(TOOL_ROOT / "work" / "full_json_alignment.tsv"))
    parser.add_argument("--summary", default=str(TOOL_ROOT / "work" / "full_json_alignment_summary.tsv"))
    parser.add_argument("--overrides", default=str(TOOL_ROOT / "work" / "json_alignment_overrides.tsv"))
    parser.add_argument("--output-json-dir", default=str(TOOL_ROOT / "work" / "bilingual_json"))
    parser.add_argument("--write-bilingual-json", action="store_true")
    parser.add_argument("--force", action="store_true", help="Write output even if fatal mismatches are present.")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    map_rows = read_map(Path(args.map))
    orig_dir = Path(args.orig_json_dir)
    chs_dir = Path(args.chs_json_dir or args.translated_json_dir)
    output_dir = Path(args.output_json_dir)
    overrides = read_overrides(Path(args.overrides))

    all_rows = []
    summary_rows = []
    fatal_errors = []
    loaded = []

    for map_row in map_rows:
        rows, errors, orig_data, chs_data, orig_path = compare_scenario(map_row, orig_dir, chs_dir, overrides)
        all_rows.extend(rows)
        counter = Counter(row["status"] for row in rows)
        fatal_count = sum(1 for row in rows if row["severity"] == "fatal") + len(errors)
        warn_count = sum(1 for row in rows if row["severity"] == "warn")
        info_count = sum(1 for row in rows if row["severity"] == "info")
        summary_rows.append(
            {
                "scenario": map_row["json_name"],
                "storage_name": map_row.get("storage_name", ""),
                "rows": len(rows),
                "fatal": fatal_count,
                "warn": warn_count,
                "info": info_count,
                "ok": counter.get("ok", 0),
                "statuses": json.dumps(dict(sorted(counter.items())), ensure_ascii=False),
                "errors": ";".join(errors),
            }
        )
        if fatal_count:
            fatal_errors.extend([map_row["json_name"] + ":" + error for error in errors])
            fatal_errors.extend(
                f"{map_row['json_name']}:row{row['row_index']}:{row['status']}"
                for row in rows
                if row["severity"] == "fatal"
            )
        if orig_data is not None and chs_data is not None and orig_path is not None:
            loaded.append((map_row, orig_data, chs_data, orig_path))

    report_fields = [
        "scenario",
        "storage_name",
        "row_index",
        "scene_index",
        "text_id",
        "block_index",
        "severity",
        "status",
        "orig_speaker",
        "chs_speaker",
        "orig_display_name",
        "chs_display_name",
        "orig_voice",
        "chs_voice",
        "orig_text",
        "chs_text",
        "notes",
    ]
    summary_fields = ["scenario", "storage_name", "rows", "fatal", "warn", "info", "ok", "statuses", "errors"]
    write_tsv(Path(args.report), all_rows, report_fields)
    write_tsv(Path(args.summary), summary_rows, summary_fields)

    total_counter = Counter(row["status"] for row in all_rows)
    print(f"Scenarios: {len(summary_rows)}; rows: {len(all_rows)}; fatal: {len(fatal_errors)}")
    for status, count in sorted(total_counter.items()):
        print(f"  {status}: {count}")
    print(f"Wrote report: {args.report}")
    print(f"Wrote summary: {args.summary}")

    if fatal_errors and not args.force:
        print("Fatal mismatches found; not writing bilingual JSON.")
        for item in fatal_errors[:30]:
            print(f"  {item}")
        if len(fatal_errors) > 30:
            print(f"  ... {len(fatal_errors) - 30} more")
        raise SystemExit(2)

    if not args.write_bilingual_json:
        return

    if args.clean and output_dir.exists():
        assert_safe_clean_path(output_dir)
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    changed_total = 0
    skipped_total = 0
    select_changed_total = 0
    for map_row, orig_data, chs_data, _orig_path in loaded:
        changed, skipped, select_changed = append_bilingual(orig_data, chs_data)
        changed_total += changed
        skipped_total += skipped
        select_changed_total += select_changed
        out_path = output_dir / (map_row["json_name"] + ".json")
        out_path.write_text(json.dumps(orig_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"Wrote bilingual JSON: {output_dir}")
    print(f"Changed blocks: {changed_total}; skipped blocks: {skipped_total}")
    print(f"Changed select captions: {select_changed_total}")


if __name__ == "__main__":
    main()
