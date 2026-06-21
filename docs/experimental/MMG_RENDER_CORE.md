# MMG Render Core

Mellow v2.2.0 introduces the first MMG render-core layer. It is still cross-platform and CPU/canvas-backed, but the runtime surface is now organized around graphics-engine concepts rather than only immediate-mode drawing.

## Added concepts

- scenes
- sprites
- textures
- camera
- frame loop
- input events
- render graph metadata

## Example

```mel
import "pkg:core-mmg" as mmg

keep app = mmg.app(title: "MMG Render Core Demo", width: 960, height: 640, clear: "#0d1117")
mmg.scene(app, "main")
mmg.camera(app, x: 0, y: 0, zoom: 1.0, follow: "hero")
mmg.texture(app, "hero", source: "assets/hero.png")
mmg.sprite(app, "hero", x: 120, y: 140, w: 96, h: 96, vx: 1, vy: 0, fill: "#7c3aed")
mmg.on(app, "key", "Escape", "close")
mmg.frame(app, fps: 60)
mmg.run(app)
```

## Current reality

The runtime is not a GPU-native replacement for OpenGL yet. In this pack the goal is to establish the MMG render model and runtime contracts so later packs can swap in native backends.
