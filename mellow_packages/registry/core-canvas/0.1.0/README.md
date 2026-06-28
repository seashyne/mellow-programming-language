# core-canvas

Native headless canvas package for the Mellow C runtime.

This package uses the built-in `canvas` native module, so it works without Python at runtime. The first backend writes portable `.ppm` image files; a window/GUI backend can sit on top of the same API later.

```mellow
use canvas as c

img = c.create(160, 120)
c.clear(img, "white")
c.circle(img, 80, 60, 42, "#33ccff")
c.save(img, "circle.ppm")
```

Supported native calls:

- `canvas.create(width, height)` / `c.create(width, height)`
- `canvas.clear(image, color)`
- `canvas.pixel(image, x, y, color)`
- `canvas.line(image, x1, y1, x2, y2, color)`
- `canvas.rect(image, x, y, width, height, color)`
- `canvas.circle(image, cx, cy, radius, color)`
- `canvas.save(image, path)`

Colors can be named values like `"white"`, `"black"`, `"red"`, `"green"`, `"blue"`, `"yellow"`, `"cyan"`, `"magenta"`, or hex strings like `"#33ccff"`.
