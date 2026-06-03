# Mellow v2.3.1 MMG + Smallless + MELV Pack

This release extends the GPU-native MMG starter with the next practical pieces that can be shipped today in-repo:

- MMG GPU export/runtime metadata prepared for sprite batching and callback bindings
- optional PNG/JPG texture loading path for target builds that provide `SDL2_image`
- Mellow Smallless `.sm` reversible compression tools
- Mellow Video `.melv` encode / inspect / decode / extract tools backed by OpenCV
- starter package entries for `core-sm` and `core-melv`

## Honest status

What works in this pack now:

- `.sm` round-tripping for text files
- `.melv` wrap / inspect / decode / extract flows
- CLI subcommands for `sm` and `melv`
- native MMG source updated to be friendlier for later shader/batch work

What is still a foundation step rather than finished parity:

- sprite batching and shader pipeline are prepared at the scene/export/source level, but not fully compiled and validated in this environment
- PNG texture loading depends on target-machine native graphics dependencies
- `.melv` is a Mellow-owned container format, not a low-level custom hardware decoder
