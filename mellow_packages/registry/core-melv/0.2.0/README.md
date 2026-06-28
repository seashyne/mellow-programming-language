# core-melv

Official Mellow Video package for dependency-free `.melv` assets.

The native backend is MELV2 with the `mellow-rgb-rle` codec. It is designed and
implemented by Mellow and does not require FFmpeg, OpenCV, zlib, or external
video codecs.

```bash
mellow melv pack-frames frame000.ppm frame001.ppm -o demo.melv --fps 24
mellow melv inspect demo.melv
mellow melv validate demo.melv
mellow melv extract-native demo.melv -o frames/
```

Legacy bridge commands (`import-video` / `export-video`) for common video files
remain optional and are not the native backend.
