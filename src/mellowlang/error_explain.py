from __future__ import annotations

"""Error Explain database (v1.2.0)

This is intentionally small and stable. We can expand over time without breaking.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorExplain:
    id: str
    title: str
    what: str
    why: str
    fix: str
    example_bad: str
    example_good: str


DB: dict[str, ErrorExplain] = {
    "E001": ErrorExplain(
        id="E001",
        title="SYNTAX: Unknown statement / invalid indentation",
        what="Parser ไม่เข้าใจบรรทัดนั้น หรือ indentation ไม่ตรงกับ block ที่เปิดไว้",
        why="มักเกิดจากพิมพ์ keyword ผิด, ลืม ':' หลัง if/for/while/def หรือย่อหน้าไม่ตรงกัน",
        fix="ตรวจ ':' และระดับ indent ให้ถูก; ถ้าเป็น call ให้ใช้รูปแบบ statement ที่รองรับ",
        example_bad='''
if x > 0
    print(x)
''',
        example_good='''
if x > 0:
    print(x)
''',
    ),
    "E101": ErrorExplain(
        id="E101",
        title="RUNTIME: Unknown variable",
        what="อ้างถึงตัวแปรที่ยังไม่ถูกประกาศ/กำหนดค่าใน scope",
        why="มักเกิดจากสะกดชื่อผิด หรือประกาศตัวแปรอยู่คนละ scope",
        fix="ตรวจสะกดชื่อ; ใช้ let/var/keep; หรือส่งค่าเข้า function ให้ถูก",
        example_bad='''
print(plaeyr)
''',
        example_good='''
let player = "hero"
print(player)
''',
    ),
    "E201": ErrorExplain(
        id="E201",
        title="SANDBOX: syscall not allowed / budget exceeded",
        what="เรียก host syscall ที่ไม่ได้ถูก allowlist หรือใช้ syscall เกิน budget",
        why="เพื่อความปลอดภัย (modding) และป้องกันสคริปต์ spam",
        fix="ตรวจชื่อ syscall / module allowlist; ลดความถี่การเรียก; เพิ่ม syscall_budget",
        example_bad='''
call("os.system", "rm -rf /")
''',
        example_good='''
let math = get("math")
print(call(math["abs"], -3))
''',
    ),
}


def explain(error_id: str) -> ErrorExplain | None:
    key = (error_id or "").strip().upper()
    return DB.get(key)
