# Project Libraries (template)

โฟลเดอร์นี้ตั้งไว้เพื่อรองรับ "project libraries" ในอนาคต (sandbox + allowlist + cache)

แนวคิด:
- system modules: ใช้ `get/lib/import` แบบ allowlist ของ VM
- project libs: จะถูกโหลดจากที่นี่ผ่าน manifest (ไม่ใช่ path อิสระ)

ตอนนี้ VM ยังไม่ได้เปิดโหลดไฟล์ .frlib อัตโนมัติ (เพื่อความปลอดภัย) แต่โครงสร้างนี้ช่วยให้โปรเจกต์จัดระเบียบได้ตั้งแต่แรก
