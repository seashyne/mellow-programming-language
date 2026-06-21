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

`.melv` is a zipped video container with a manifest plus JPEG frame sequence.
It can be created from common video files and converted back out again.

### CLI

```bash
mellow melv encode input.mp4 -o demo.melv
mellow melv inspect demo.melv
mellow melv decode demo.melv -o roundtrip.mp4
mellow melv extract demo.melv -o frames/
```

The current implementation uses OpenCV for encode/decode.
