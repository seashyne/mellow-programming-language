# คู่มือ Syntax Mellow Programming Language v2.9.0

เอกสารนี้เป็นคู่มือรวม syntax ทั้ง Core, Extended และ Compatibility ที่ compiler
รองรับ สำหรับข้อกำหนดแบบบังคับและ syntax ที่ล็อกแล้วของ v2.9 ให้ยึด
[`LANGUAGE_SPEC_2_9.md`](LANGUAGE_SPEC_2_9.md) เป็นหลัก หากเอกสารสองฉบับขัดกัน
language specification มีลำดับสูงกว่า

## 1. เริ่มต้น

ไฟล์ Mellow ใช้นามสกุล `.mellow`

```mellow
let message = "Hello, Mellow!"
print(message)
```

ตรวจและรัน:

```powershell
mellow check hello.mellow
mellow run hello.mellow
```

เลือก engine:

```powershell
mellow run hello.mellow --engine=py
mellow run hello.mellow --engine=c
mellow run hello.mellow --engine=c --native-required
```

`--engine=c` เป็นค่าเริ่มต้นและยอม fallback ไป Python หาก feature ยังไม่มี native
parity เช่น debugger, events และ record/replay ส่วน `--engine=py` ใช้บังคับ Python
VM และ `--engine=auto` ยังรองรับเพื่อ compatibility ถ้าต้องการให้ล้มทันทีเมื่อ C
runtime ไม่รองรับ ให้ใช้ `--native-required`

## 2. รูปแบบไฟล์และ block

Mellow แยก block ด้วย indentation แนะนำ 4 spaces และไม่ควรผสม tab กับ space

```mellow
if score >= 10:
    print("win")
    score = score + 1

print("done")
```

expression ที่อยู่ใน `()`, `[]` หรือ `{}` เขียนหลายบรรทัดได้:

```mellow
let profile = {
    "name": "Mellow",
    "skills": [
        "games",
        "tools",
        "data"
    ]
}
```

`end` และ `do ... end` ยังอ่านได้เพื่อรองรับโค้ดแบบ Lua เดิม แต่โค้ดใหม่ควรใช้
indentation อย่างเดียว

## 3. Comment

ใช้ `#` หรือ `//` ได้ทั้งบรรทัดและท้ายคำสั่ง:

```mellow
# comment แบบแนะนำ
let hp = 100  # inline comment

// compatibility comment
print("https://example.com")  // comment ไม่ตัด // ใน string
```

Mellow v2.9.0 ยังไม่มี block comment

## 4. ชื่อและ keyword

ชื่อ variable และ function:

- เริ่มด้วยตัวอักษรหรือ `_`
- ตัวถัดไปเป็นตัวอักษร ตัวเลข หรือ `_`
- ตัวพิมพ์เล็กและใหญ่ถือเป็นคนละชื่อ
- แนะนำ `snake_case`

```mellow
let player_name = "Mali"
let MAX_SCORE = 100
let _internal_value = 5
```

keyword หลัก:

```text
let var keep
def fn function skill return
if elif else check also
for while loop repeat until break continue
try catch finally
true false none null
and or not
import use need as get call
print show precision wait stop save load put into on do end
```

## 5. Variable และ assignment

ประกาศ variable ด้วย `let`:

```mellow
let score = 0
let name = "Mellow"
```

เปลี่ยนค่าโดยไม่ต้องเขียน `let` ซ้ำ:

```mellow
score = score + 10
```

ประกาศหรือกำหนดหลายค่าแบบขนาน:

```mellow
let x, y = 10, 20
x, y = y, x
```

`var` และ `keep` เป็น alias ของ `let`:

```mellow
var lives = 3
keep display_name = "supported"
```

Mellow เป็นภาษา dynamic typing จึงไม่ต้องประกาศ type แต่ควรรักษาชนิดข้อมูลของ
variable ให้สม่ำเสมอเพื่อให้อ่านง่าย

## 6. ชนิดข้อมูลพื้นฐาน

### Number

```mellow
let count = 42
let price = 19.95
let negative = -7
```

มี integer และ floating-point number ไม่มี suffix ระบุชนิด

### String

ใช้ single quote หรือ double quote:

```mellow
let a = "hello"
let b = 'world'
```

escape ที่รองรับ:

```mellow
let text = "line 1\nline 2\t\"quoted\""
let unicode_text = "\u0E44\u0E17\u0E22"
```

escape หลักคือ `\n`, `\r`, `\t`, `\\`, `\"`, `\'` และ `\uXXXX`

### Boolean และค่าว่าง

```mellow
let enabled = true
let finished = false
let result = none
let also_empty = null
```

`none` และ `null` คือค่าเดียวกัน

### List

```mellow
let scores = [10, 20, 30]
let mixed = [1, "two", true, none]

print(scores[0])
print(scores[-1])
```

index เริ่มจาก `0` และ index ติดลบนับจากท้าย list

### Map

```mellow
let player = {
    "name": "Mali",
    "score": 20
}

print(player["name"])
```

key และ value เป็น expression ได้ แต่แนะนำ string key สำหรับข้อมูลทั่วไป

## 7. String interpolation

ใช้ f-string เพื่อแทรก expression:

```mellow
let name = "Mali"
let score = 42
print(f"{name} has {score + 8} points")
```

ใช้ `}}` เมื่อต้องการแสดง `}` เป็นตัวอักษร:

```mellow
print(f"value: {score}}}")
```

## 8. Operator และลำดับการคำนวณ

จากความสำคัญต่ำไปสูง:

| ระดับ | Operator |
| --- | --- |
| 1 | `or` |
| 2 | `and` |
| 3 | `== != < <= > >=` |
| 4 | `+ -` |
| 5 | `* / %` |
| 6 | `**` |
| unary | `not`, `-` |

```mellow
let total = 2 + 3 * 4
let power = 2 ** 3
let allowed = score >= 10 and enabled
let blocked = not allowed
```

ใช้วงเล็บเมื่ออยากให้เจตนาชัด:

```mellow
let result = (2 + 3) * 4
```

Mellow v2.9.0 ยังไม่มี `+=`, `-=`, `++`, ternary operator หรือ chained
comparison เช่น `0 < x < 10`

## 9. Output, precision, input, wait และ stop

### Output

```mellow
print("score:", score)
show "output:", score
```

`show` เป็น compatibility alias ของ `print`

### Precision

```mellow
precision 2
print(10 / 3)
```

ใช้กำหนดรูปแบบการแสดงเลขทศนิยม

### Input

```mellow
let name = input("Name: ")
print(f"Hello {name}")
```

input ถูกปิดใน sandbox โดยค่าเริ่มต้นบางโหมด เปิดด้วย:

```powershell
mellow run form.mellow --allow-ask
```

`ask(...)` เป็นชื่อเดิมของ `input(...)`

### Wait และ stop

```mellow
wait 0.5
stop
```

`wait` อาจถูกปิดด้วย `--no-wait` หรือ sandbox profile ส่วน `stop` จบโปรแกรมทันที

## 10. Condition

รูปแบบแนะนำ:

```mellow
if score >= 80:
    print("great")
elif score >= 50:
    print("pass")
else:
    print("retry")
```

ใช้วงเล็บได้:

```mellow
if (score >= 50 and enabled):
    print("accepted")
```

รูปแบบเดิมที่ยังรองรับ:

```mellow
check score >= 80:
    show "great"
also score >= 50:
    show "pass"
else:
    show "retry"
```

ค่าที่ใช้เป็น condition จะถูกประเมินตาม truthiness ของ runtime ควรใช้ boolean
expression โดยตรงเพื่อให้โค้ดชัดเจน

## 11. Loop

### for-in

```mellow
for item in ["a", "b", "c"]:
    print(item)
```

### range

```mellow
for i in range(0, 5):
    print(i)
```

`range(start, stop)` ไม่รวมค่า `stop`

### tuple unpacking

```mellow
for index, value in enumerate(["a", "b"]):
    print(index, value)
```

ใช้ตัวแปรได้ 1 หรือ 2 ตัว

### while

```mellow
let i = 0
while i < 3:
    print(i)
    i = i + 1
```

### break และ continue

```mellow
for i in range(0, 10):
    if i == 2:
        continue
    if i == 5:
        break
    print(i)
```

### repeat-until

body ทำงานอย่างน้อยหนึ่งครั้ง:

```mellow
let attempts = 0
repeat:
    attempts = attempts + 1
until attempts >= 3
```

### count loop

```mellow
loop 3 times:
    print(count)
```

ภายใน block มี variable `count` เริ่มจาก `0`

### compatibility loop

```mellow
loop hp > 0:
    hp = hp - 1

loop item in items:
    print(item)

for i = 1, 5 do
    print(i)
end
```

numeric `for` แบบ Lua รวมปลายทางและรองรับ `start, end, step` แต่โค้ดใหม่ควรใช้
`for ... in range(...)`

## 12. Function

ประกาศด้วย `def`, รับ parameter และคืนค่าด้วย `return`:

```mellow
def add(a, b):
    return a + b

let answer = add(2, 3)
print(answer)
```

function ที่ไม่มี `return` คืน `none`

### Default parameter

```mellow
def greet(name, greeting="Hello"):
    return greeting + " " + name

print(greet("Mali"))
print(greet("Mali", "Hi"))
```

### Named argument

```mellow
file_write("notes.txt", "hello", mode="w")
```

named arguments รองรับใน direct call รูปแบบ `name=value` การรองรับของแต่ละ built-in
ขึ้นกับ API นั้น

### First-class function

```mellow
def double(value):
    return value * 2

let operation = double
print(operation(5))

let operations = [double]
print(operations[0](6))
```

### Inline lambda

```mellow
let square = skill(x): x * x
let add_tax = fn(value, rate=0.07): value * (1 + rate)

print(square(5))
```

lambda เป็น expression บรรทัดเดียว รูปแบบ `skill`, `fn`, `lambda`, `def` และ
`function` ใช้ได้ แต่แนะนำ `skill(...)` เพื่อแยกจาก function declaration

### Compatibility function

```mellow
skill add(a, b):
    return a + b
```

`skill`, `fn` และ `function` เป็น alias ของ `def` เมื่อใช้ประกาศ function แบบ block

## 13. List ขั้นสูง

### Slice

```mellow
let values = [0, 1, 2, 3, 4]
print(values[1:4])
print(values[:2])
print(values[2:])
```

ใช้กับ string ได้ด้วย:

```mellow
print("mellow"[0:3])
```

หมายเหตุ: parser รับรูปแบบ `[start:stop:step]` แต่ compiler v2.9.0 ยังไม่ใช้ค่า
`step` จึงยังไม่ควรพึ่งพารูปแบบนี้

### Spread

```mellow
let middle = [2, 3]
let values = [1, *middle, 4]
```

### List comprehension

```mellow
let doubled = [x * 2 for x in [1, 2, 3]]
let evens = [x for x in range(0, 7) if x % 2 == 0]
```

comprehension รองรับ loop variable เดียวและ `if` ได้หนึ่งเงื่อนไข

### List helper

```mellow
let values = [1, 2]
put 3 into values
print(values)
```

`put value into list_name` เป็น statement compatibility สำหรับเพิ่มสมาชิก
โค้ดใหม่สามารถใช้ `list_push(values, 3)` ได้

## 14. Error handling

```mellow
try:
    let value = 10 / 0
catch err:
    print("error:", err)
finally:
    print("cleanup")
```

เขียน `catch:` โดยไม่ตั้งชื่อได้ โดย runtime จะใช้ชื่อ `err`:

```mellow
try:
    risky_call()
catch:
    print(err)
```

รองรับ `try + catch`, `try + finally` หรือทั้งสามส่วน ไม่มี syntax `raise` ใน
stable core v2.9.0 ข้อผิดพลาดมาจาก runtime หรือ built-in

## 15. Module และ import

### Allowlisted module

รูปแบบแนะนำ:

```mellow
import math as math
print(math.sqrt(81))

import money as money
print(money.format(money.of("12.34", "THB")))
```

เรียกแบบ explicit ได้:

```mellow
let root = get math.sqrt(81)
call math.sqrt(16)
```

`get` และ `call` ทำงานเหมือนกันใน expression ส่วน statement form จะทิ้งค่าที่คืนมา

### Local file

```mellow
import "mathlib.mellow" as mathlib
print(mathlib.add(2, 3))
```

### Package

```mellow
import "core-math" as core_math
use core-math as core_math
need "core-math" as core_math
```

`import`, `use` และ `need` ต้องมี `as alias` เสมอ package import ต้องผ่าน project
resolver/lockfile ส่วน local file ลงท้าย `.mellow`

ดู module ที่มีใน environment:

```powershell
mellow modules
mellow modules --json
```

## 16. Built-in ที่ใช้บ่อย

รายการนี้เป็น API มาตรฐาน ไม่ใช่ keyword ของ grammar:

```mellow
len(value)
range(start, stop)
enumerate(list)
zip(list_a, list_b)

str(value)
int(value)
float(value)
bool(value)
type(value)

list_push(items, value)
list_pop(items)
list_map(items, skill(x): x * 2)
list_filter(items, skill(x): x > 0)
list_reduce(items, skill(a, b): a + b)

map_get(data, "key", none)
map_set(data, "key", value)
map_keys(data)

string_upper(text)
string_lower(text)
string_split(text, ",")
string_join(items, ",")

json_encode(value)
json_decode(text)
```

ใช้ `mellow modules --json` เป็นรายการ API ของ module ที่ตรงกับ installation ปัจจุบัน

## 17. Money

ห้ามใช้ float ธรรมดากับกฎการเงินที่ต้องการความแน่นอน ให้สร้าง money จาก string:

```mellow
let subtotal = money("0.10", "THB")
let fee = money("0.20", "THB")
let total = money_add(subtotal, fee)

print(money_format(total))
print(money_amount(total))
print(money_currency(total))
```

API:

```text
money(value, currency="USD")
money_of(value, currency="USD")
money_add(a, b)
money_sub(a, b)
money_mul(money_value, scalar)
money_div(money_value, scalar)
money_quantize(value, scale?)
money_format(value)
money_amount(value)
money_currency(value)
money_eq(a, b)
money_lt(a, b)
money_gt(a, b)
```

money คนละสกุลเงินไม่สามารถบวก ลบ หรือเปรียบเทียบกันโดยตรง

สำหรับ rule script ที่ต้องการ sandbox เข้ม:

```powershell
mellow run rules.mellow --sandbox=finance
```

## 18. Data processing

อ่าน JSONL/CSV เป็น batch เพื่อจำกัด memory:

```mellow
let stream = data_open_jsonl("records.jsonl", 100)
let rows = data_next(stream)

while len(rows) > 0:
    let sales = data_where(rows, "kind", "==", "sale")
    let selected = data_project(sales, ["id", "amount"])
    print(data_sum(selected, "amount"))
    rows = data_next(stream)

data_close(stream)
```

API:

```text
data_open_jsonl(path, batch_size=100)
data_open_csv(path, batch_size=100)
data_next(stream)
data_close(stream)
data_cancel(stream)
data_info(stream)
data_project(rows, fields)
data_where(rows, field, operator, expected)
data_sum(rows, field)
data_sqlite_open(path=":memory:", readonly=false)
data_sqlite_query(database_or_path, sql, params=[], limit?)
data_sqlite_execute(database_or_path, sql, params=[])
data_sqlite_close(database)
```

operator ของ `data_where` คือ `==`, `!=`, `>`, `>=`, `<`, `<=`, `contains`

ใช้ parameterized SQL เสมอ:

```mellow
let rows = data_sqlite_query(
    "app.db",
    "SELECT name FROM users WHERE id = ?",
    [user_id],
    10
)
```

รันแบบอ่านข้อมูล:

```powershell
mellow run report.mellow --sandbox=data
```

การเขียน SQLite ต้องเปิดอย่างชัดเจน:

```powershell
mellow run import.mellow --sandbox=data --data-write
```

## 19. Immutable ledger

Ledger Core เก็บรายการบัญชีแบบ double-entry, immutable และมี hash chain:

```mellow
let empty_book = ledger_create("THB")
let book = ledger_post(
    empty_book,
    "sale-001",
    [
        {"account": "cash", "amount": "100.00"},
        {"account": "revenue", "amount": "-100.00"}
    ],
    "cash sale",
    {"order_id": "A-100"}
)

print(len(ledger_entries(empty_book)))
print(money_format(ledger_balance(book, "cash")))
print(ledger_verify(book)["ok"])
```

API:

```text
ledger_create(currency="USD")
ledger_post(ledger, transaction_id, postings, memo="", metadata={})
ledger_verify(ledger)
ledger_balance(ledger, account)
ledger_entries(ledger)
```

ผลลัพธ์ของ `ledger_post` เป็น ledger ใหม่ ตัวเดิมไม่ถูกแก้ การ post ต้องมีอย่างน้อย
2 rows, ผลรวมต้องเป็น `0.00` และ transaction id ต้องไม่ซ้ำ

Ledger Core ช่วยเรื่อง deterministic rules และ audit prototype แต่ persistence,
authentication, authorization, signature และ compliance ต้องทำใน host application

## 20. Save, load และ file

statement ระดับสูง:

```mellow
save {"score": 42} into "profile"
load "profile" into profile
print(profile["score"])
```

file API:

```mellow
file_write("notes.txt", "hello", mode="w")
file_append("notes.txt", "\nnext", mode="a")
let text = file_read("notes.txt", mode="r")
print(file_exists("notes.txt"))
```

filesystem ถูกจำกัดให้อยู่ใน sandbox root และบาง profile ปิด storage ทั้งหมด

## 21. Event

ประกาศ event handler:

```mellow
on("spawn", player_id, hp):
    print(player_id, hp)
```

event ถูกส่งจาก host/CLI เช่น:

```powershell
mellow game.mellow --emit spawn --emit-args '["p1", 100]'
```

events ยัง route ผ่าน Python VM ใน v2.9.0 จึงไม่อยู่ใน Full Native C Core Profile

## 22. Determinism และ sandbox

```powershell
mellow run main.mellow --seed 123
mellow run main.mellow --record run.jsonl --seed 123
mellow run main.mellow --replay run.jsonl
mellow diff first.jsonl second.jsonl
```

profile สำคัญ:

- `default`: runtime ปกติภายใต้งบและ filesystem sandbox
- `finance`: ปิด input, wait, storage, save และ network
- `data`: เปิดงานอ่านข้อมูลแบบ bounded; การเขียนต้องใช้ `--data-write`

ตรวจ environment:

```powershell
mellow doctor
```

## 23. Modern syntax และ compatibility syntax

| แนะนำในโค้ดใหม่ | Compatibility |
| --- | --- |
| `let x = 1` | `var x = 1`, `keep x = 1` |
| `print(x)` | `show x` |
| `def add(a, b):` | `skill add(a, b):`, `fn add(a, b):` |
| `if / elif / else` | `check / also / else` |
| `while condition:` | `loop condition:` |
| `for x in values:` | `loop x in values:` |
| indentation | optional `end`, `do ... end` |
| `input(prompt)` | `ask(prompt)` |

เลือก style เดียวต่อ project และใช้ modern syntax ใน tutorial/library ใหม่

## 24. ขอบเขตของ v2.9.0

- ไม่มี class, object declaration, decorator หรือ static type annotation
- ไม่มี `raise`, `yield`, `async/await`, generator และ match expression
- assignment target ต้องเป็นชื่อ variable ไม่รองรับ `items[0] = value`
- slice step ถูก parse แต่ยังไม่ถูกใช้โดย compiler
- events, debugger และ record/replay ยังใช้ Python VM
- framework, agents, MMG, desktop และ package platform เป็น extended surface ไม่ใช่
  grammar หลักของภาษา

## 25. ตรวจ syntax ก่อนใช้งาน

```powershell
mellow check app.mellow
mellow fmt --check app.mellow
mellow fmt -w app.mellow
mellow run examples\syntax_tour_v280.mellow
```

ดู stable core และความสามารถ runtime เพิ่มเติม:

- `docs/STABLE_CORE.md`
- `docs/CAPABILITIES.md`
- `docs/CLI.md`
- `docs/STYLE_GUIDE.md`
