# Script Reference

This repository is organized around a pipeline, not a single executable. The scripts below are intentionally small so each game can replace the game-specific parts while keeping the reusable steps.

## Recommended Path

Use this path when both original and translated scenarios can be decompiled to FreeMote JSON:

```powershell
python scripts\freemote_batch.py decompile --input-dir work\orig_scn --output-dir work\orig_json
python scripts\freemote_batch.py decompile --input-dir work\translated_scn --output-dir work\translated_json
python scripts\freemote_align_json.py --map work\scenario_map.tsv --orig-json-dir work\orig_json --translated-json-dir work\translated_json
python scripts\freemote_align_json.py --map work\scenario_map.tsv --orig-json-dir work\orig_json --translated-json-dir work\translated_json --write-bilingual-json --clean
python scripts\freemote_batch.py build --input-dir work\bilingual_json --output-dir work\bilingual_scn
python scripts\xp3_pack.py work\patch_stage work\dual_sub_patch.xp3
```

The bilingual embedding step edits FreeMote JSON text blocks. A block like:

```text
original line
```

becomes:

```text
original line
translated line
```

The script also updates the block length field used by the scenario format.

## FreeMote Helpers

### `freemote_batch.py`

Batch wrapper for FreeMote.

Use it to:

- decompile many `.ks.scn` files into `.ks.json`;
- rebuild many `.ks.json` files back into `.ks.scn`.

Examples:

```powershell
python scripts\freemote_batch.py decompile --input-dir work\orig_scn --output-dir work\orig_json --clean
python scripts\freemote_batch.py build --input-dir work\bilingual_json --output-dir work\bilingual_scn --clean
```

### `freemote_extract_texts.py`

Extracts text rows from FreeMote scenario JSON into a TSV table. This is useful for review, manual alignment, or memory-string alignment.

```powershell
python scripts\freemote_extract_texts.py work\orig_json -o work\orig_texts.tsv
```

### `freemote_align_json.py`

Compares original and translated FreeMote JSON files by scenario, scene, text id, block id, and voice id. It writes an audit report first, then can generate bilingual JSON when fatal mismatches are zero.

Inputs:

- `--map`: TSV with `json_name` and `storage_name` columns.
- `--orig-json-dir`: original FreeMote JSON directory.
- `--translated-json-dir`: translated FreeMote JSON directory.
- `--overrides`: optional TSV for small known row splits/merges.

Outputs:

- `full_json_alignment.tsv`: row-level audit.
- `full_json_alignment_summary.tsv`: scenario-level summary.
- `bilingual_json/`: original JSON with translated lines appended.

Examples:

```powershell
python scripts\freemote_align_json.py --map work\scenario_map.tsv --orig-json-dir work\orig_json --translated-json-dir work\translated_json
python scripts\freemote_align_json.py --map work\scenario_map.tsv --orig-json-dir work\orig_json --translated-json-dir work\translated_json --write-bilingual-json --clean
```

### `freemote_apply_bilingual.py`

Applies an existing alignment TSV to one FreeMote JSON file. This is the fallback path when translation data came from memory scanning or a custom text table instead of translated JSON.

```powershell
python scripts\freemote_apply_bilingual.py --input-json work\orig_json\scene.ks.json --alignment work\aligned.tsv -o work\bilingual_json\scene.ks.json
```

## Alignment And Memory Helpers

### `align_memory_strings.py`

Aligns translated strings found in process memory to original text rows extracted from FreeMote JSON.

```powershell
python scripts\align_memory_strings.py --orig work\orig_texts.tsv --mem-strings work\memory_strings.tsv -o work\aligned.tsv --log-output work\align_log.tsv
```

### `scan_process_cjk.py`

Scans a Windows process for CJK-looking UTF-8, GBK, and UTF-16LE strings.

```powershell
python scripts\scan_process_cjk.py <pid> -o work\memory_strings.tsv
```

### `search_process_text.py`

Searches process memory for exact text terms and dumps nearby bytes for inspection.

```powershell
python scripts\search_process_text.py <pid> "known translated line" -o work\hits
```

### `dump_process_region.py`

Dumps the readable committed memory region containing an address.

```powershell
python scripts\dump_process_region.py <pid> 0x12345678 -o work\region.bin
```

### `extract_cjk_strings.py`

Extracts CJK-looking strings from a binary dump.

```powershell
python scripts\extract_cjk_strings.py work\region.bin -o work\region_strings.tsv
```

## XP3 Helpers

### `xp3_pack.py`

Packs a directory into a simple unencrypted XP3 archive.

```powershell
python scripts\xp3_pack.py work\patch_stage work\dual_sub_patch.xp3
```

### `xp3_replace_entry.py`

Replaces one uncompressed XP3 entry in place. This is for game-specific experiments such as temporarily replacing a startup script during runtime dumping. Use with backups.

```powershell
python scripts\xp3_replace_entry.py patch.xp3 work\replacement.tjs --entry-name hashed_entry_name --backup work\patch.xp3.before_replace
```

### `parse_krkrdump_log.py`

Extracts useful mapping rows from KrkrDump logs.

```powershell
python scripts\parse_krkrdump_log.py KrkrDump.log work\krkrdump_mapping.csv
```

## Example Files

- `examples/scenario_map.example.tsv`: minimal map for direct JSON alignment.
- `examples/json_alignment_overrides.example.tsv`: row-merge override format.
- `examples/alignment.example.tsv`: minimal alignment table for `freemote_apply_bilingual.py`.
- `examples/build_patch.ps1`: PowerShell helper for packing and optionally installing a patch archive.
- `examples/krkrpatch/KrkrPatch.example.json`: runtime patch loader configuration example.
