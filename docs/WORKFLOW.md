# Workflow

This document describes the intended end-to-end workflow. Paths are examples; replace them with your own game and work directories.

## 1. Prepare Tools

Required or commonly useful external tools:

- FreeMote: decompile and rebuild M2/KRKR PSB scenario files.
- KrkrDump: dump decrypted resources and path mappings at runtime.
- KrkrPatch: load a custom XP3 patch at runtime.
- Python 3.9 or newer.

This repository does not vendor those binaries.

## 2. Dump Or Extract Original Scenario Files

For protected Kirikiri/Yuzusoft games, direct XP3 extraction may produce encrypted or transformed content. Prefer runtime dumping when direct extraction is not enough.

Typical goals:

- recover logical scenario filenames;
- recover decrypted `.ks.scn` or equivalent scenario files;
- recover useful path/hash mappings from KrkrDump logs.

If KrkrDump produces a log with hashed and logical paths, parse it:

```powershell
python scripts\parse_krkrdump_log.py KrkrDump.log work\krkrdump_mapping.csv
```

## 3. Decompile Scenario Files With FreeMote

Use FreeMote to convert scenario files into JSON. The exact command depends on FreeMote version and scenario type. The result should be one or more FreeMote `.json` files that contain a top-level `scenes` array.

Place JSON files in a directory such as:

```text
work/orig_json/
```

## 4. Extract Original Text Rows

```powershell
python scripts\freemote_extract_texts.py work\orig_json -o work\orig_texts.tsv
```

The output TSV contains stable identifiers used by later steps:

- `source_json`
- `scenario`
- `scene_index`
- `text_id`
- `block_index`
- `speaker`
- `voice`
- `raw_text`
- `plain_text`

## 5. Collect Translated Text

There is no universal method. Common options:

- dump the localized build and extract its scripts;
- scan process memory from the localized build;
- search for known lines and dump nearby process regions;
- parse an existing translation table if one is available.

Memory helpers:

```powershell
python scripts\scan_process_cjk.py <pid> -o work\memory_strings.tsv
python scripts\search_process_text.py <pid> "known translated line" -o work\hits
python scripts\dump_process_region.py <pid> 0x12345678 -o work\region.bin
python scripts\extract_cjk_strings.py work\region.bin -o work\region_strings.tsv
```

The aligner expects translated rows with at least:

- `offset`
- `text`

## 6. Align Original And Translated Rows

```powershell
python scripts\align_memory_strings.py `
  --orig work\orig_texts.tsv `
  --mem-strings work\memory_strings.tsv `
  -o work\aligned.tsv `
  --log-output work\align_log.tsv
```

The output adds:

- `chs_text`
- `chs_offset`
- `align_status`

Despite the `chs_text` column name, this can hold any translated language. The current script started from a Chinese/Japanese prototype and keeps that column name for compatibility.

## 7. Apply Bilingual Text To FreeMote JSON

```powershell
python scripts\freemote_apply_bilingual.py `
  --input-json work\orig_json\scene.ks.json `
  --alignment work\aligned.tsv `
  -o work\bilingual_json\scene.ks.json
```

By default each text block becomes:

```text
original line
translated line
```

Avoid inserting KAG tags such as `[font]` into PSB text until you know the game parser supports them. Some engines use square brackets for ruby or internal text markup.

## 8. Rebuild Scenario Files

Use FreeMote to rebuild JSON back to scenario files. Put rebuilt files in a patch staging directory using the logical path expected by the game:

```text
work/patch_stage/
  scene.ks.scn
  start.ks
  default.tjs
```

Only include files you intend to override.

## 9. Pack XP3 Patch

```powershell
python scripts\xp3_pack.py work\patch_stage work\dual_sub_patch.xp3
```

The packer creates a simple unencrypted XP3 archive. It is intended for runtime patch loaders such as KrkrPatch or for engines configured to accept unencrypted patch archives.

## 10. Configure Runtime Patch Loading

Use `examples/krkrpatch/KrkrPatch.example.json` as a starting point. Typical fields:

- `gameExecutableFile`: original game executable;
- `patchArchives`: your generated patch archive;
- `patchProtocols`: archive protocol search prefixes.

## 11. Verify

Verify in-game, not only by file inspection.

Minimum checks:

- the patch archive is opened by the loader;
- the target scenario file is loaded from the patch archive;
- the first bilingual line appears;
- text wrapping and backlog behavior are acceptable;
- save data does not override important font or text settings.
