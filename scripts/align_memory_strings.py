import argparse
import csv
import re
from pathlib import Path


VOICE_RE = re.compile(r"^[a-z]+\d{3}_\d{3}$", re.IGNORECASE)
SCENARIO_RE = re.compile(r"^\d{3}\..*\.ks$")
TEXT_CONTROL_RE = re.compile(r"^(?:%\d+;)+")
PUNCT_ONLY_TEXTS = {
    "\u300c\u2026\u2026\u2026\u300d",
    "\u2026\u2026\u2026",
    "\u2026\u2026",
    "\u2026",
}


def is_voice(text):
    return bool(VOICE_RE.match(text or ""))


def is_scenario_name(text):
    return bool(SCENARIO_RE.match(text or ""))


def is_textish(text):
    if not text:
        return False
    if is_voice(text) or is_scenario_name(text):
        return False
    if text.startswith("*"):
        return False
    if re.match(r"^[A-Za-z0-9_./\\:-]+$", text):
        return False

    quote_chars = {
        "\u300c",
        "\u300d",
        "\u300e",
        "\u300f",
        "\u300a",
        "\u300b",
        "\u201c",
        "\u201d",
    }
    if any(ch in text for ch in quote_chars):
        return True

    sentence_end = {
        "\u3002",  # .
        "\uff01",  # !
        "\uff1f",  # ?
        "!",
        "?",
        "\uff09",
        ")",
        "\u266a",  # music note
        "\u2014",  # em dash
        "\u2026",  # ellipsis
        "\u201d",  # right double quote
        "\u300f",
        "\u300b",
    }
    return text[-1] in sentence_end


def strip_text_controls(text):
    return TEXT_CONTROL_RE.sub("", text or "")


def is_control_duplicate(previous, current):
    if not previous or not current:
        return False
    if not TEXT_CONTROL_RE.match(previous):
        return False
    return strip_text_controls(previous) == current


def remove_control_duplicates(rows):
    cleaned = []
    previous_text = ""
    for row in rows:
        text = row.get("text", "")
        if is_textish(text) and is_control_duplicate(previous_text, text):
            previous_text = text
            continue
        cleaned.append(row)
        if is_textish(text):
            previous_text = text
    return cleaned


def normalize_voice(value):
    return (value or "").split(",")[0].strip()


def next_relevant_index(rows, index):
    j = index
    while j < len(rows) and not is_textish(rows[j]["text"]) and not is_voice(rows[j]["text"]):
        j += 1
    return j


def next_row_voice(orig_rows, index):
    if index + 1 >= len(orig_rows):
        return ""
    return normalize_voice(orig_rows[index + 1].get("voice", ""))


def is_quoted_dialogue(text):
    return (text or "").lstrip().startswith("\u300c")


def read_tsv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path, rows, fieldnames):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def align(orig_rows, mem_rows, start_offset):
    mem_rows = remove_control_duplicates(mem_rows)
    start_index = 0
    if start_offset is not None:
        start_index = next(
            i for i, row in enumerate(mem_rows) if int(row["offset"], 16) >= start_offset
        )
    else:
        start_index = next(i for i, row in enumerate(mem_rows) if is_textish(row["text"]))

    aligned = []
    logs = []
    i = start_index

    for orig_index, orig in enumerate(orig_rows):
        expected_voice = normalize_voice(orig.get("voice", ""))

        while i < len(mem_rows) and not is_textish(mem_rows[i]["text"]) and not is_voice(mem_rows[i]["text"]):
            if is_scenario_name(mem_rows[i]["text"]) and aligned:
                break
            i += 1

        chs = ""
        chs_offset = ""
        status = "matched"

        if i >= len(mem_rows) or is_scenario_name(mem_rows[i]["text"]):
            status = "missing_eof"
        elif is_voice(mem_rows[i]["text"]):
            current_voice = mem_rows[i]["text"]
            if expected_voice and current_voice.lower() == expected_voice.lower():
                status = "omitted_before_voice"
                i += 1
            else:
                status = f"unexpected_voice:{current_voice}"
                logs.append(
                    {
                        "text_id": orig["text_id"],
                        "status": status,
                        "mem_offset": mem_rows[i]["offset"],
                        "mem_text": current_voice,
                    }
                )
        else:
            orig_plain = orig.get("plain_text", "").strip()
            current_visible = strip_text_controls(mem_rows[i]["text"])
            if orig_plain in PUNCT_ONLY_TEXTS and current_visible != orig_plain:
                chs = orig_plain
                status = "filled_same_punctuation"
            else:
                next_voice = next_row_voice(orig_rows, orig_index)
                after_current = next_relevant_index(mem_rows, i + 1)
                if (
                    not expected_voice
                    and next_voice
                    and is_quoted_dialogue(orig.get("plain_text", ""))
                    and len(orig.get("plain_text", "").strip()) <= 5
                    and after_current < len(mem_rows)
                    and is_voice(mem_rows[after_current]["text"])
                    and mem_rows[after_current]["text"].lower() == next_voice.lower()
                ):
                    status = "omitted_unvoiced_dialogue"
                else:
                    chs = current_visible
                    chs_offset = mem_rows[i]["offset"]
                    i += 1

                    if expected_voice:
                        while i < len(mem_rows) and not is_voice(mem_rows[i]["text"]):
                            if is_textish(mem_rows[i]["text"]):
                                break
                            i += 1
                        if i < len(mem_rows) and is_voice(mem_rows[i]["text"]):
                            current_voice = mem_rows[i]["text"]
                            if current_voice.lower() == expected_voice.lower():
                                i += 1
                            else:
                                status = f"voice_mismatch:{current_voice}"
                                logs.append(
                                    {
                                        "text_id": orig["text_id"],
                                        "status": status,
                                        "mem_offset": mem_rows[i]["offset"],
                                        "mem_text": current_voice,
                                    }
                                )

        if not chs and orig.get("plain_text", "").strip() in PUNCT_ONLY_TEXTS:
            chs = orig.get("plain_text", "").strip()
            status = "filled_same_punctuation"

        row = dict(orig)
        row.update(
            {
                "chs_text": chs,
                "chs_offset": chs_offset,
                "align_status": status,
            }
        )
        aligned.append(row)

    return aligned, logs


def main():
    parser = argparse.ArgumentParser(description="Align translated memory strings to original scenario text rows.")
    parser.add_argument("--orig", required=True)
    parser.add_argument("--mem-strings", required=True)
    parser.add_argument("--start-offset", type=lambda value: int(value, 0), default=None)
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--log-output", required=True)
    args = parser.parse_args()

    orig_rows = read_tsv(args.orig)
    mem_rows = read_tsv(args.mem_strings)
    aligned, logs = align(orig_rows, mem_rows, args.start_offset)

    fieldnames = list(orig_rows[0].keys()) + ["chs_text", "chs_offset", "align_status"]
    write_tsv(args.output, aligned, fieldnames)
    write_tsv(args.log_output, logs, ["text_id", "status", "mem_offset", "mem_text"])

    missing = sum(1 for row in aligned if not row["chs_text"])
    statuses = {}
    for row in aligned:
        statuses[row["align_status"]] = statuses.get(row["align_status"], 0) + 1
    print(f"Aligned {len(aligned)} rows; missing Chinese={missing}")
    for key in sorted(statuses):
        print(f"{key}: {statuses[key]}")
    print(f"Wrote: {args.output}")
    print(f"Wrote log: {args.log_output}")


if __name__ == "__main__":
    main()
