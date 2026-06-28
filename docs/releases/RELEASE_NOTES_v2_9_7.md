# Release Notes v2.9.7

v2.9.7 starts the native runtime hardening track. The focus is not broad new
syntax; it is making the C runtime behave more like a real language runtime.

## Native cooperative scheduler

- `spawn(fn)` now creates a real native task instead of only incrementing a
  counter.
- `yield()` saves the current task state and round-robin switches to the next
  runnable task.
- `recv(ch)` on an empty channel implicitly yields when another task can run,
  then retries after a sender wakes the channel.
- Scheduler internals moved into `mellowrt_scheduler.c/.h` so
  `mellowrt_core.c` can stay focused on the opcode loop.

This is still cooperative scheduling. Full preemptive or OS-backed M:N
scheduling remains future runtime-engine work.

## GC and ownership hardening

- `gc_stats()` now reports `heap_bytes`, `heap_blocks`,
  `last_freed_blocks`, and `last_freed_bytes`.
- Channel queue values now clone through the VM heap ownership path.
- Native tests now cover nested string/list/map ownership and repeated GC
  stress collection.

## Native canvas package

- Added the `canvas` native module with `create`, `clear`, `pixel`, `line`,
  `rect`, `circle`, and `save`.
- Added `core-canvas` as an official native starter package and local-registry
  package.
- The first backend is headless and writes portable `.ppm` images, keeping the
  runtime path fully native C while leaving room for a GUI/window backend later.

## Release gates

- The GitHub release pipeline now includes the native sanitizer/fuzzer gate
  before publishing release artifacts.
- Native tests prove task A/B interleaving and channel implicit-yield behavior.
