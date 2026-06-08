# Case Study: Cafe Stella Prototype

This repository was extracted from a prototype that built a first-chapter bilingual text patch for a KirikiriZ/Yuzusoft visual novel.

Sanitized summary:

- The original executable used KirikiriZ/TVP.
- Scenario scripts were runtime-dumped in decrypted form.
- The first scenario was FreeMote-compatible M2/KRKR PSB.
- Original text rows were extracted from FreeMote JSON.
- Translated text was collected from a localized build and aligned to original rows.
- The bilingual scenario was rebuilt and packed into an unencrypted XP3 archive.
- KrkrPatch loaded the custom archive and overrode the first scenario file.
- A small per-game font/startup patch was needed for acceptable Chinese glyph rendering.

The important lesson is that the high-level pipeline is reusable, while the final patch stage is game-specific. File names, startup scripts, font variables, and patch loader configuration should be treated as adapters.

No game files or translated lines from that prototype are included in this repository.
