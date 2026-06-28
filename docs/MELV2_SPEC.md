# MELV2 Native Container

MELV2 is Mellow's dependency-free video asset container. It is designed for
simple native runtimes, deterministic validation, and patent-safe implementation
inside Mellow-owned code.

## Scope

MELV2 does not import MP4, H.264, HEVC, AV1, GIF, or other external media
formats. Those workflows belong to optional bridge commands. The native MELV2
surface starts from raw RGB frame data and currently uses PPM P6 as the CLI
input/output interchange format.

## File Layout

All integer fields are unsigned little-endian 32-bit values.

```text
offset  size  field
0       5     magic: "MELV2"
5       4     format_version: 1
9       4     width
13      4     height
17      4     fps_num
21      4     fps_den
25      4     frame_count
29      ...   repeated frame records
```

Each frame record is:

```text
size  field
4     payload_length
N     mellow-rgb-rle payload
```

## Codec: mellow-rgb-rle

The current native codec is `mellow-rgb-rle`. The uncompressed frame is RGB24:
three bytes per pixel in row-major order.

The payload is a sequence of 4-byte runs:

```text
byte 0  run length, 1..255 pixels
byte 1  red
byte 2  green
byte 3  blue
```

Decoders must reject:

- run length `0`
- payloads whose length is not divisible by `4`
- decoded byte counts that do not equal `width * height * 3`
- truncated frame payloads
- unsupported `format_version`

## CLI

Native path:

```bash
mellow melv pack-frames frame000.ppm frame001.ppm -o demo.melv --fps 24
mellow melv inspect demo.melv
mellow melv validate demo.melv
mellow melv extract-native demo.melv -o frames/
```

Optional bridge path:

```bash
mellow melv import-video input.mp4 -o bridge.melv
mellow melv export-video bridge.melv -o output.mp4
```

`encode` and `decode` remain aliases for the bridge path for compatibility.
