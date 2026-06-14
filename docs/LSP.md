# Mellow Language Server

Mellow LSP เพิ่ม diagnostics, completion, hover, document symbols และ
go-to-definition ให้ไฟล์ `.mellow` และ `.mel`

## 1. ติดตั้ง LSP backend

จาก project checkout:

```powershell
python -m pip install -e ".[lsp]"
mellow doctor
```

ผลของ `mellow doctor` ควรแสดง:

```text
LSP ready     : True
[OK] lsp_runtime: LSP backend ready
```

## 2. ใช้กับ VS Code

ติดตั้ง dependency และสร้าง VSIX:

```powershell
cd vscode-extension
npm install
npx @vscode/vsce package
```

จากนั้นใน VS Code:

1. เปิด Extensions
2. กดเมนู `...`
3. เลือก `Install from VSIX...`
4. เลือกไฟล์ `.vsix` ใน `vscode-extension`
5. เปิดไฟล์ `.mellow`

extension จะเรียก `mellow lsp` ให้อัตโนมัติ ไม่ต้องเปิดคำสั่งนี้แยกใน terminal

หาก `mellow` ไม่อยู่ใน PATH ให้เปิด Settings แล้วกำหนด
`MellowLang: Executable Path` เป็น path เต็มของ `mellow.exe` หรือ `mellow.cmd`

## 3. ตรวจสถานะใน VS Code

- เปิด `View > Output`
- เลือก channel `MellowLang`
- ใช้ Command Palette: `MellowLang: Run Doctor`
- ใช้ Command Palette: `MellowLang: Restart Language Server`

## 4. เปิดจาก terminal

```powershell
mellow lsp
```

คำสั่งนี้ใช้ stdio และจะรอ editor เชื่อมต่อ จึงไม่คืน prompt จนกว่าจะปิด client
หรือกด `Ctrl+C` การค้างอยู่ในสถานะนี้เป็นพฤติกรรมปกติ ไม่ใช่โปรแกรมหยุดทำงาน

ดูคำแนะนำ:

```powershell
mellow lsp --help
```

## 5. แก้ปัญหา

```powershell
mellow doctor --strict
where.exe mellow
python -m pip show mellowlang pygls lsprotocol
```

หาก version ของ launcher และ source ไม่ตรงกัน:

```powershell
python -m pip uninstall mellowlang
python -m pip install -e ".[lsp]"
```
