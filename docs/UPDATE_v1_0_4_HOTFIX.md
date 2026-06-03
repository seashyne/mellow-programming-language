# v1.0.4 Hotfix: examples + storage compatibility

This hotfix includes:
- Updated examples to avoid standalone `end` terminators (blocks end by indentation/dedent).
- Fixed bytecode VM opcode `SAVE_VAL` argument order.
- StorageCore now accepts both save orders and normalizes automatically:
  - save(data, filename)
  - save(filename, data)
