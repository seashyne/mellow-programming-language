# Mellow Smallless (`.sm`) and Mellow Video (`.melv`)

## `.sm`

`.sm` is a reversible container optimized for Mellow source and text-like assets.
The current codec is `sm1-token-zlib`:

1. scan repeated tokens and indentation patterns
2. build a small token dictionary
3. encode the token stream
4. compress with zlib

Round-tripping is lossless.

### CLI

```bash
mellow sm pack src/main.mel -o src/main.mel.sm
mellow sm inspect src/main.mel.sm
mellow sm unpack src/main.mel.sm -o restored.mel
```

## `.melv`

`.melv` has two tracks:

1. **Native MELV2** is the dependency-free Mellow-owned path. It stores PPM P6
   frames using the `mellow-rgb-rle` codec. The codec is intentionally simple:
   RGB pixels are encoded as run-length records, so Mellow can inspect, validate,
   pack, and extract frames without FFmpeg, OpenCV, zlib, or patented video
   codecs.
2. **Legacy bridge MELV1** is a zip/JPEG sequence path for importing or exporting
   common video workflows. It is optional and uses OpenCV only when users call the
   bridge commands.

### CLI

```bash
mellow melv pack-frames frame000.ppm frame001.ppm -o demo.melv --fps 24
mellow melv inspect demo.melv
mellow melv validate demo.melv
mellow melv extract-native demo.melv -o frames/
```

Optional legacy bridge commands:

```bash
mellow melv import-video input.mp4 -o demo.melv
mellow melv inspect demo.melv
mellow melv export-video demo.melv -o roundtrip.mp4
mellow melv extract demo.melv -o frames/
```

`encode` and `decode` remain compatibility aliases for the bridge path.

The native path is the recommended package/runtime surface. The bridge path is
for interoperability only.
