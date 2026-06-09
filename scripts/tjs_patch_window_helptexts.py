#!/usr/bin/env python3
"""Patch a Kirikiri/Yuzusoft default.tjs windowHelpTexts table from TSV."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path


WINDOW_BLOCK_RE = re.compile(
    r"(?P<head>\.windowHelpTexts\s*=\s*%\[\r?\n)"
    r"(?P<body>.*?)"
    r"(?P<tail>\r?\n\s*\];)",
    re.DOTALL,
)

HELP_LINE_RE = re.compile(
    r'^(?P<indent>\s*)(?P<key>[A-Za-z0-9_]+)\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"\s*,(?P<suffix>.*)$'
)


def detect_text_encoding(path: Path) -> tuple[str, str]:
    """Return read/write encodings, preserving BOM-style script encodings."""
    head = path.read_bytes()[:4]
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        return "utf-16", "utf-16"
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", "utf-8-sig"
    return "utf-8", "utf-8"


def detect_newline(source: str) -> str:
    return "\r\n" if "\r\n" in source else "\n"


def escape_tjs_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def load_translations(path: Path, key_col: str, text_col: str) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if reader.fieldnames is None:
            raise SystemExit(f"{path}: missing TSV header")
        missing = [name for name in (key_col, text_col) if name not in reader.fieldnames]
        if missing:
            raise SystemExit(f"{path}: missing column(s): {', '.join(missing)}")

        out: dict[str, str] = {}
        for row_no, row in enumerate(reader, start=2):
            raw_key = (row.get(key_col) or "").strip()
            text = (row.get(text_col) or "").strip()
            if not raw_key or not text:
                continue
            key = raw_key.split(".")[-1]
            if key in out and out[key] != text:
                raise SystemExit(f"{path}:{row_no}: duplicate key with different text: {raw_key}")
            out[key] = text
        return out


def patch_window_helptexts(source: str, translations: dict[str, str]) -> tuple[str, set[str]]:
    match = WINDOW_BLOCK_RE.search(source)
    if not match:
        raise SystemExit("Could not find .windowHelpTexts = %[ ... ]; block")

    newline = detect_newline(source)
    used: set[str] = set()
    patched_lines: list[str] = []
    for line in match.group("body").splitlines():
        line_match = HELP_LINE_RE.match(line)
        if line_match and line_match.group("key") in translations:
            key = line_match.group("key")
            used.add(key)
            patched_lines.append(
                f'{line_match.group("indent")}{key}:\t\t"{escape_tjs_string(translations[key])}",'
                f'{line_match.group("suffix")}'
            )
        else:
            patched_lines.append(line)

    patched_body = newline.join(patched_lines)
    patched = (
        source[: match.start()]
        + match.group("head")
        + patched_body
        + match.group("tail")
        + source[match.end() :]
    )
    return patched, used


def patch_draw_text_fontface(source: str, draw_param: str, fontface: str) -> str:
    pattern = re.compile(
        rf'("{re.escape(draw_param)}"\s*=>\s*%\[(?P<body>[^\]]*)\])'
    )

    def repl(match: re.Match[str]) -> str:
        body = match.group("body")
        if "fontface" in body:
            body = re.sub(r'fontface\s*:\s*"[^"]*"', f'fontface:"{escape_tjs_string(fontface)}"', body)
        else:
            sep = "" if body.rstrip().endswith(",") or not body.strip() else ","
            body = f'{body}{sep} fontface:"{escape_tjs_string(fontface)}"'
        return f'"{draw_param}"  => %[{body}]'

    patched, count = pattern.subn(repl, source, count=1)
    if count == 0:
        raise SystemExit(f'Could not find draw text param "{draw_param}"')
    return patched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--default-tjs", required=True, type=Path, help="Path to default.tjs to patch.")
    parser.add_argument("--translations", required=True, type=Path, help="TSV with key/text columns.")
    parser.add_argument("--key-col", default="key", help="TSV key column. Default: key")
    parser.add_argument("--text-col", default="zh", help="TSV text column. Default: zh")
    parser.add_argument("--draw-param", default=None, help='Optional drawTextParamMapTable key, e.g. "quickmenu.help".')
    parser.add_argument("--fontface", default=None, help="Font face to set for --draw-param.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without writing.")
    args = parser.parse_args()

    translations = load_translations(args.translations, args.key_col, args.text_col)
    if not translations:
        raise SystemExit("No translations loaded")

    read_encoding, write_encoding = detect_text_encoding(args.default_tjs)
    source = args.default_tjs.read_text(encoding=read_encoding)
    patched, used = patch_window_helptexts(source, translations)
    if args.draw_param or args.fontface:
        if not (args.draw_param and args.fontface):
            raise SystemExit("--draw-param and --fontface must be used together")
        patched = patch_draw_text_fontface(patched, args.draw_param, args.fontface)

    unused = sorted(set(translations) - used)
    print(
        f"loaded={len(translations)} patched={len(used)} unused={len(unused)} "
        f"encoding={write_encoding}"
    )
    if unused:
        print("unused keys: " + ", ".join(unused), file=sys.stderr)

    if not args.dry_run and patched != source:
        args.default_tjs.write_text(patched, encoding=write_encoding, newline="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
