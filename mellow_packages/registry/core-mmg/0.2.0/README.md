# core-mmg

Mellow Magic Graphics render-core starter package.

This package defines the MMG surface for `.mel` apps and pairs with the `mellow mmg` runtime.

## Features

- scene graph
- sprite and texture metadata
- camera
- frame loop
- input events
- render graph metadata

## Example

```mel
import "pkg:core-mmg" as mmg

keep app = mmg.app(title: "MMG Render Core Demo", width: 960, height: 640, clear: "#0d1117")
mmg.scene(app, "main")
mmg.camera(app, x: 0, y: 0, zoom: 1.0)
mmg.texture(app, "hero", source: "assets/hero.png")
mmg.sprite(app, "hero", x: 120, y: 140, w: 96, h: 96, vx: 1, vy: 0)
mmg.text(app, 24, 24, "MMG Render Core", size: 22)
mmg.on(app, "key", "Escape", "close")
mmg.frame(app, fps: 60)
mmg.run(app)
```
