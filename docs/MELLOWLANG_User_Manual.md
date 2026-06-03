# MellowLang v1.4.0 — คู่มือการใช้งาน (Stable)

MellowLang คือภาษา scripting สำหรับเกม/AI ที่เน้น:
- **Sandbox** (ปลอดภัยสำหรับ modding)
- **Deterministic** (record → replay ได้ผลเดิม)
- **Tooling UX** (check / fmt / doctor / explain)

---

## 1) CLI พื้นฐาน

```bash
mellow --version
mellow <script.mellow>

mellow run <script-or-project>
mellow check <script-or-project>
mellow fmt -w <files...>
mellow doctor
mellow explain E001
mellow init <dir>
```

---

## 2) Dev mode vs Project mode (มาตรฐาน v1.3.x)

### Dev mode (เหมือนภาษาอื่น)
- เกิดเมื่อ **ไม่พบ** `mellow.json`
- path แบบ relative ยึดตามโฟลเดอร์ที่คุณรันคำสั่ง (CWD)
- เหมาะกับการทดลอง/ทำ tool

### Project mode (ปลอดภัย)
- เกิดเมื่อ **พบ** `mellow.json` (ในโฟลเดอร์นี้หรือโฟลเดอร์แม่)
- `file_*` จะเขียนภายใต้ sandbox (`sandbox_root`)
- การเข้าถึง filesystem ของเครื่องให้ใช้ `fs_*` และต้องถูกอนุญาตใน `permissions`

ตัวอย่าง `mellow.json`:
```json
{
  "name": "MyGame",
  "entry": "scripts/main.mellow",
  "sandbox_root": "saves",
  "permissions": [
    "storage",
    "fs.read:./assets",
    "fs.write:./exports"
  ]
}
```

---

## 3) Syntax พื้นฐาน

### ตัวแปร
```mellow
let hp = 100
hp = hp - 1
```

### พิมพ์ค่า (print/show)
รองรับหลายค่า:
```mellow
print("hp =", hp)
show("pos =", pos)
```

### เงื่อนไข
```mellow
if hp <= 0:
    print("dead")
else:
    print("alive")
```

### วนลูป
```mellow
for i in range(0, 5):
    print(i)

while hp > 0:
    hp = hp - 1
```

### ฟังก์ชัน (skill)
```mellow
def add(a, b):
    return a + b

print(add(2, 3))
```

### คอลเลกชัน
```mellow
let a = [1, 2, 3]
let m = {"name": "mellow", "score": 99}
print(len(a))
print(m["score"])
```

### try/catch
```mellow
try:
    let x = 1 / 0
catch err:
    print("error:", err)
```

---

## 4) Storage & Files

### Game/AI storage (แนะนำ)
ใช้ `file_*` / `save_data` / `load_data` สำหรับข้อมูลเกม/AI (อยู่ใน sandbox)
```mellow
save_data("profile", {"hp": 10})
let d = load_data("profile")
print("loaded =", d)

file_write("notes.txt", "hello\n", mode="w")
file_append("notes.txt", "world\n", mode="a")
print(file_read("notes.txt", mode="r"))
```

### Secure Save (encrypted) — v1.3.4 (แนะนำสำหรับข้อมูลผู้เล่น)

ใช้เมื่ออยากให้ save อยู่ "นอกโปรเจกต์" และไม่อยากให้ผู้เล่นแก้ไฟล์ได้ง่าย ๆ (ไฟล์ถูกแก้ → ตรวจเจอ)

```mellow
save_init("afternoon.today")

save_set("player.hp", 120)
save_set("wallet.gems", 350)
save_set("progress.stage", 3)

save_commit("slot1")
```

โหลดกลับ:

```mellow
save_init("afternoon.today")

if save_load("slot1"):
    let hp = save_get("player.hp", 100)
    print("hp =", hp)
else:
    print("no save")
```

> ถ้าไฟล์ถูกแก้จากภายนอก `save_load()` จะ error ด้วย `SAVE_TAMPERED`.

### Always-online + Hybrid Save (Level C) — v1.3.5+

> v1.4.0 เพิ่ม `get("game")` (allowlisted) สำหรับเครื่องมือเกมแบบ deterministic (easing, tween step, grid neighbors, A*).

สำหรับเกมที่ **ต้องออนไลน์ตลอด** (เช่น กาชา/เศรษฐกิจ/leaderboard):

- เก็บ **ข้อมูลสำคัญ** (เงิน, ไอเท็ม, reward, pity) ไว้ที่ **server เป็นตัวจริง (authoritative)**
- เก็บ **ข้อมูลไม่สำคัญ** (settings, UI state) ไว้ local ด้วย `save_commit()`
- ถ้าต้องการตรวจจับการแก้ local save ให้ใช้ **server-signed save snapshot**

เปิด permission ใน `mellow.json`:

```json
{
  "entry": "main.mellow",
  "permissions": [
    "save",
    "net",
    "net.http:https://api.example.com/",
    "net.ws:wss://ws.example.com/",
    "net.max_bytes:262144",
    "net.timeout_s:10"
  ]
}
```

**Signed save** (server ให้ signature แล้วค่อยเขียนไฟล์):

```mellow
save_init("my.game")
save_set("ui.language", "th")
save_set("player.level", 7)

# sign_url ต้องตอบกลับ JSON: {"signature_b64":"..."}
save_commit_signed("slot1", "https://api.example.com/save/sign", PUBKEY_B64)
```

โหลดแบบตรวจ signature:

```mellow
save_init("my.game")
if save_load_signed("slot1", PUBKEY_B64):
    print(save_get("player.level", 1))
```

**HTTP / WebSocket**:

```mellow
let profile = net_http_get("https://api.example.com/profile")
print(profile)

let cid = net_ws_connect("wss://ws.example.com/")
net_ws_send(cid, {"type":"hello"})
print(net_ws_recv(cid, 1.0))
```

### Host filesystem (dev/export)
ใช้ `fs_*` และต้องอนุญาตใน `mellow.json`:
```mellow
fs_write("./exports/out.txt", "build\n")
print(fs_read("./exports/out.txt"))
```

---

## 5) Deterministic replay

บันทึก:
```bash
mellow run main.mellow --record run.jsonl --seed 123
```
เล่นซ้ำ:
```bash
mellow run main.mellow --replay run.jsonl
```

---

## 6) Debugging (CLI)

- `--trace` แสดงบรรทัดที่รัน
- `--step` โหมดทีละก้าว (interactive)
- `--break 12,20-25` ตั้ง breakpoint
- `--watch hp,pos,target` ดูค่าตัวแปร
- `--ai-timeline out.jsonl` เขียน timeline ของ `ai.decide`

---

## 7) Tooling UX

- `mellow check` ตรวจ syntax/lint
- `mellow fmt` ฟอร์แมตโค้ด
- `mellow doctor` ตรวจสภาพแวดล้อม + โปรเจกต์
- `mellow explain <ID>` อธิบาย error เป็นภาษาคน

---

## 8) หมายเหตุเรื่องความปลอดภัย

- Project mode จะเน้น deny-by-default
- แนะนำให้ใช้ `storage` เป็นหลักสำหรับข้อมูลเกม/AI
- ใช้ `fs_*` เฉพาะ export/tooling และประกาศ permission ให้ชัด

