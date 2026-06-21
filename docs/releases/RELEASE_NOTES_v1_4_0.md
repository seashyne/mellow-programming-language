# MellowLang v1.4.0

Release focus: **Standard Library Expansion (Game/AI oriented)** + keep `get()` ergonomics.

## Highlights

### Game-oriented stdlib (pure deterministic helpers)

New allowlisted module: `get("game")` / `lib("game")`

Available functions (call via `call(...)`):

```mellow
g = get("game")

# easing
v = call(g["ease_in_out_quad"], 0.35)

# tween helper (from, to, t, ease_name?)
x = call(g["tween"], 0, 100, 0.5, "out_quad")

# neighbors (x,y,w,h)
ns = call(g["neighbors4"], 3, 3, 10, 10)

# astar(grid, start, goal, diag=false)
grid = [
  [0,0,0,0],
  [1,1,0,1],
  [0,0,0,0],
]
path = call(g["astar"], grid, [0,0], [3,2], false)
```

### Versioning

- v1.x policy preserved: this release **adds** new stdlib capabilities and does not intentionally break existing scripts.

## Notes

- `get("...")` is the ergonomic, allowlisted module accessor (compiled to `sys.get`).
- Network/save/AI modules remain available via existing APIs; v1.4.0 focuses on expanding game-first deterministic utilities.

---

If you hit an issue, run:

```bash
mellow doctor
mellow test
```

---

End of release notes.
