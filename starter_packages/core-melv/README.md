# core-melv

Official Mellow Video package for dependency-free `.melv` assets.

The stable native path is MELV2 with the `mellow-rgb-rle` codec:

```bash
mellow melv pack-frames frame000.ppm frame001.ppm -o demo.melv --fps 24
mellow melv inspect demo.melv
mellow melv validate demo.melv
mellow melv extract-native demo.melv -o frames/
```

`mellow melv import-video` and `mellow melv export-video` are optional legacy
bridge commands for common video files. They are not the native codec backend.
