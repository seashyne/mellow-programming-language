# Mellow v2.3.2 MMG Native Pipeline Pack

This pack pushes MMG native rendering closer to a real runtime path.

What was added:
- sprite batching metadata exported into `.mmgscene` v2
- shader pipeline flag with fixed-function fallback
- input callback export for key/mouse actions
- state bootstrap export for native runtime
- C-side scene structures for pipeline/state/event metadata

Important note:
The native backend source is included, but building it still requires SDL2/OpenGL dev packages on the target machine. In this container I validated the Python export path and tests, but could not compile the native binary because SDL2 headers are not installed here.
