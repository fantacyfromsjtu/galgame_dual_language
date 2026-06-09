# Case Study: Cafe Stella Prototype

This repository was extracted from a prototype that built a full-scenario bilingual text patch for a KirikiriZ/Yuzusoft visual novel.

Sanitized summary:

- The original executable used KirikiriZ/TVP.
- Scenario scripts were runtime-dumped in decrypted form.
- The scenario files were FreeMote-compatible M2/KRKR PSB.
- Original and translated text rows were extracted from FreeMote JSON.
- Most rows aligned directly by scenario/scene/text/block order plus voice id checks.
- One translated scenario had a deliberate split/expanded line; an override merged the translated rows before alignment.
- The bilingual scenarios were rebuilt and packed into an unencrypted XP3 archive.
- KrkrPatch loaded the custom archive and overrode the scenario files.
- A small per-game font/startup patch was needed for acceptable Chinese glyph rendering.

The important lesson is that the high-level pipeline is reusable, while the final patch stage is game-specific. File names, startup scripts, font variables, and patch loader configuration should be treated as adapters.

No game files or translated lines from that prototype are included in this repository.
