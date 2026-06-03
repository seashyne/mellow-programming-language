# Mellow v2.1.6 — Project Templates + Presets Pack

## Added

- Real `mellow new --preset ...` project presets:
  - app
  - automation
  - ai-agent
  - gamekit
  - api-webhook
- New starter package: `core-window`
- Desktop host commands:
  - `mellow desktop status`
  - `mellow desktop run <file.mel>`
- App preset companion files for desktop and webhook presets.

## Notes

- Desktop windows are hosted through a Tkinter-backed desktop host.
- The desktop host parses a supported declarative subset from `.mel` source.
- This pack focuses on bootstrap and real local usability for new projects.
