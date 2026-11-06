# core-sm

Starter package for the `.sm` reversible compression format used by Mellow Smallless.

The native codec lives in `native/sm/`. The CLI wrapper lives in
`src/mellowlang/sm_codec.py` and is exposed through `mellow sm pack`,
`mellow sm inspect`, and `mellow sm unpack`.

New payloads use `sm3-token-native-crc32`, a dependency-free native C reversible
token dictionary format with deterministic size/checksum validation. The Python
wrapper still accepts legacy `SM1` / `sm1-token-zlib` and `SM2` /
`sm2-token-zlib-crc32` payloads.
