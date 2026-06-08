# Patch Stage Example

Put rebuilt scenario files and per-game override scripts here before packing.

Example layout:

```text
patch-stage/
  001.example.ks.scn
  start.ks
  default.tjs
  main.xp3/
    config.tjs
```

The relative path inside this directory becomes the path inside the generated XP3 archive. Keep only files that should override the original game.
