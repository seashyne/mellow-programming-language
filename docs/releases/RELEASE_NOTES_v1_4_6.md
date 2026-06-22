# MellowLang v1.4.6 — Release Notes

## ภาพรวม

v1.4.6 แก้ปัญหา Game Module ที่ใช้ยากเกินไป และเพิ่ม AI Module อย่างสมบูรณ์

---

## 🎮 Game Module — ไม่ต้องใช้ `call(g["..."], ...)` อีกต่อไป

### ก่อน (v1.4.5)
```mellow
let g = get("game")
let path = call(g["astar"], grid, [0,0], [3,2], false)
let t = call(g["ease_in_quad"], 0.25)
let wp = call(g["neighbors4"], x, y, 10, 10)
```

### หลัง (v1.4.6)
```mellow
let path = astar(grid, [0,0], [3,2])
let t = ease_in_quad(0.25)
let wp = neighbors4(x, y, 10, 10)
```

### Easing curves ใหม่
| Function | ลักษณะ |
|---|---|
| `ease_in_cubic(t)` | เร่งช้าๆ แรงกว่า quad |
| `ease_out_cubic(t)` | ชะลอช้าๆ แรงกว่า quad |
| `ease_in_out_cubic(t)` | เร่ง-ชะลอ smooth มาก |
| `ease_in_back(t)` | ดึงถอยก่อนแล้วเร่ง |
| `ease_out_back(t)` | ยิงเกินเป้าแล้วดึงกลับ |
| `ease_out_bounce(t)` | กระดอนเหมือนลูกบอล |
| `ease_out_elastic(t)` | สั่นเหมือนสปริง |

---

## 🤖 AI Module — เพิ่มใหม่ทั้งหมด

### Steering Behaviors — ควบคุมการเคลื่อนที่ของ NPC

```mellow
let vel = ai_seek(pos, target, speed)
# คืน [vx, vy] วิ่งตรงหา target

let vel = ai_flee(pos, threat, speed)
# คืน [vx, vy] วิ่งหนีจาก threat

let vel = ai_arrive(pos, target, speed, slow_radius)
# วิ่งหา target แล้วชะลอเมื่อใกล้ถึง
# slow_radius = ระยะที่เริ่มชะลอ (default 50)

let result = ai_wander(pos, current_angle, speed, jitter)
# เดินเตร่แบบ deterministic
# result = {"vel": [vx,vy], "angle": float}
# ต้องเก็บ angle ไว้ใน state ระหว่าง tick

let result = ai_patrol(pos, waypoints, current_idx, speed, threshold)
# เดินวนระหว่าง waypoints
# result = {"vel": [vx,vy], "idx": int}
# ต้องเก็บ idx ไว้ใน state ระหว่าง tick
```

### Perception — การรับรู้ของ NPC

```mellow
ai_in_range(pos, target, radius)
# → bool: target อยู่ในวงกลม radius หรือไม่

ai_in_sight(pos, facing_angle, target, fov_degrees, max_dist)
# → bool: target อยู่ใน field of view หรือไม่
# facing_angle: 0=ขวา, 90=ลง, 180=ซ้าย, 270=ขึ้น
# fov_degrees: มุมมองรวม (90 = ±45 องศา)

ai_nearest(pos, targets)
# → target ที่ใกล้ที่สุด จาก list
# targets: list ของ [x,y] หรือ {"pos":[x,y], ...}

ai_filter_range(pos, targets, radius)
# → list ของ targets ที่อยู่ในระยะ radius
```

### ตัวอย่าง NPC AI ครบวงจร

```mellow
let npc_pos = [100, 100]
let npc_facing = 0.0
let patrol_idx = 0
let patrol_wps = [[0,0],[200,0],[200,200],[0,200]]

# สร้าง enemies list
let enemies = [{"pos": [80,90], "hp": 100}]

# tick ทุก frame
let can_see_enemy = ai_in_sight(npc_pos, npc_facing, [80,90], 120, 150)
let enemy_near = ai_in_range(npc_pos, [80,90], 60)

if can_see_enemy or enemy_near:
    let closest = ai_nearest(npc_pos, enemies)
    let vel = ai_seek(npc_pos, closest["pos"], 3.0)
    print(f"CHASE: vel={vel}")
else:
    let p = ai_patrol(npc_pos, patrol_wps, patrol_idx, 1.5)
    patrol_idx = p["idx"]
    let vel = p["vel"]
    print(f"PATROL: heading to wp {patrol_idx}")
```

### Utility AI / BT / FSM (เหมือนเดิม แต่ตอนนี้มี alias สั้น)

```mellow
# เดิม: import "ai" as a → call(a["utility_choose"], opts)
# ใหม่:
let chosen = ai_utility([
    {"score": 0.9, "value": "attack"},
    {"score": 0.4, "value": "heal"}
])
# → "attack"

let tag = ai_decide("patrol", "no enemy found")
# บันทึกลง --ai-timeline log
```

---

## Backward Compatibility

- ✅ `get("game")` + `call(g["astar"], ...)` ยังใช้ได้เหมือนเดิม
- ✅ `import "ai" as ai` ยังใช้ได้เหมือนเดิม
- ✅ scripts ทุก version ก่อนหน้ารันได้ไม่เปลี่ยนแปลง
