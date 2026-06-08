# Limitations

## Not Universal

This repository provides scripts and a workflow, not a universal visual novel patcher. Each game can differ in:

- engine version;
- XP3 encryption or filters;
- script bytecode format;
- text renderer behavior;
- font handling;
- save-data system variables;
- file naming and hash mapping.

## Best Fit

The workflow fits best when:

- the game uses Kirikiri/KirikiriZ;
- scenario scripts are FreeMote-compatible M2/KRKR PSB files;
- scenario files can be dumped in decrypted form;
- translated text can be collected in roughly the same order as original text;
- runtime patch loading can override individual files.

## Weak Fit

The workflow is weak when:

- the engine is unrelated to Kirikiri;
- scenario text is generated dynamically;
- translated text is stored in a custom encrypted table that cannot be recovered;
- the game rejects unencrypted patch archives;
- the renderer cannot display two-line text without deeper UI changes.

## Font Handling

Font behavior is highly game-specific. A default font setting may be ignored if:

- save data has already stored a previous font face;
- the message layer uses a prerendered font;
- scenario bytecode includes text renderer state;
- the engine uses fallback fonts per glyph.

Treat font patches as per-game adapters, not as part of the generic pipeline.

## Legal Boundary

Do not publish commercial game resources, extracted scripts, translations, fonts, audio, images, screenshots, or generated patches unless you have the rights to distribute them. Keep public repositories limited to tooling, documentation, and synthetic examples.
