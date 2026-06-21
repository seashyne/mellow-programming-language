# MellowLang v1.2.0 — Release Notes

> Goal: **DX & Debugging Release** — “Dev รู้สึกว่าภาษานี้ดูแลเขา”

## New: CLI Debugger (เบื้องต้น)

- `--trace` : แสดงการรันแบบ line-by-line
- `--step` : โหมด step (interactive เมื่อรันผ่าน TTY)
- `--break 12,20-25` : breakpoint ตามเลขบรรทัด
- `--watch hp,pos,target` : แสดงค่า variable ระหว่าง trace/step

## New: AI Decision Timeline (jsonl)

- `--ai-timeline ai.jsonl` : บันทึก event ของ `ai.decide(...)` เป็น timeline (deterministic)
- `import "ai" as ai` + `call(ai["decide"], label, reason)`

## New: AI Helpers (sandbox-first)

- `ai.utility_choose([...])` : เลือกตัวเลือกที่ score สูงสุด (tie = ตัวแรก)
- `ai.bt_tick(tree, ctx)` : Behavior Tree tick (selector/sequence/condition/action)
- `ai.fsm_tick(fsm, ctx)` : FSM tick แบบเล็ก (state->on_tick syscall)

> หมายเหตุ: action/condition จะเรียก host syscall ที่ระบุใน node (`sys`)

## New: Project Manifest

- รองรับ `mellow.json` (project mode)
- `mellow run <project_dir>` จะอ่าน `mellow.json` เพื่อหา `entry` + defaults

## New: Error Explain

- `mellow explain E001` (ฐานข้อมูลเริ่มต้น สามารถขยายเพิ่มได้)

## Tests

- เพิ่ม test สำหรับ AI timeline jsonl
