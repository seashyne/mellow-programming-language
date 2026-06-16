# Mellow Programming Language Specification 2.9

Status: **Normative and frozen for the Mellow 2.9 release line**

This document defines the portable Mellow 2.9 Core Profile. A conforming
implementation must accept the syntax and preserve the behavior described
here. `docs/SYNTAX_REFERENCE.md` is a broader user guide; when the two
documents differ, this specification wins.

## 1. Compatibility Contract

The language version uses `MAJOR.MINOR`.

- Patch releases in the 2.9 line may fix bugs but must not change valid program
  meaning.
- New syntax requires Mellow 2.10 or later.
- Removing or changing Core Profile syntax requires a major version.
- Implementations may provide extensions, but must identify them as
  `extended`, `experimental`, or `legacy`.
- A Core Profile program must run through both the Python implementation and
  the Full Native C implementation.

## 2. Source Text

- Source files use the `.mellow` extension.
- Source text is UTF-8.
- Keywords are ASCII and case-sensitive.
- A logical line ends at a newline unless it is inside `()`, `[]`, or `{}`.
- Blocks use four spaces of indentation.
- Tabs in indentation are not portable and must be rejected by strict tools.
- `#` starts a comment outside a string.
- There is no normative block-comment syntax.

## 3. Lexical Grammar

The grammar uses EBNF. `{ x }` means zero or more repetitions and `[ x ]`
means optional.

```ebnf
letter        = "A"…"Z" | "a"…"z" | "_" ;
digit         = "0"…"9" ;
identifier    = letter, { letter | digit } ;

integer       = digit, { digit } ;
float         = digit, { digit }, ".", digit, { digit } ;
number        = integer | float ;

string        = double_string | single_string ;
double_string = '"', { string_character }, '"' ;
single_string = "'", { string_character }, "'" ;

comment       = "#", { any_character_except_newline } ;
```

Identifiers are case-sensitive. These identifiers are reserved in the Core
Profile:

```text
let keep def return if else while for in
true false none and or not
```

`range`, `print`, `len`, `str`, `type`, `abs`, `floor`, `ceil`, `sqrt`,
`min`, and `max` are standard built-in names, not grammar keywords.

## 4. Program Grammar

```ebnf
program       = { blank_line | comment_line | statement } ;

statement     = declaration
              | assignment
              | expression_statement
              | return_statement
              | if_statement
              | while_statement
              | for_statement
              | function_definition ;

declaration   = ("let" | "keep"), identifier, "=", expression, newline ;
assignment    = identifier, "=", expression, newline ;
expression_statement = expression, newline ;
return_statement = "return", [ expression ], newline ;

if_statement  = "if", expression, ":", newline, block,
                [ "else", ":", newline, block ] ;
while_statement = "while", expression, ":", newline, block ;
for_statement = "for", identifier, "in", "range", "(",
                expression, ",", expression, ")", ":",
                newline, block ;

function_definition = "def", identifier, "(",
                      [ identifier, { ",", identifier } ], ")",
                      ":", newline, block ;

block         = indent, statement, { statement }, dedent ;
```

`let` is the preferred declaration spelling. `keep` is a frozen alias retained
for Mellow's friendly syntax. They have identical runtime behavior in 2.9.

## 5. Expression Grammar

Operators are listed from lowest to highest precedence.

```ebnf
expression    = or_expression ;
or_expression = and_expression, { "or", and_expression } ;
and_expression = comparison, { "and", comparison } ;
comparison    = sum, [ compare_operator, sum ] ;
compare_operator = "==" | "!=" | "<" | "<=" | ">" | ">=" ;
sum           = product, { ("+" | "-"), product } ;
product       = unary, { ("*" | "/" | "%"), unary } ;
unary         = [ "-" | "not" ], primary ;

primary       = number
              | string
              | "true" | "false" | "none"
              | identifier
              | call
              | list
              | map
              | "(", expression, ")" ;

call          = identifier, "(", [ expression, { ",", expression } ], ")" ;
list          = "[", [ expression, { ",", expression } ], "]" ;
map           = "{", [ expression, ":", expression,
                { ",", expression, ":", expression } ], "}" ;
index         = primary, "[", expression, "]" ;
```

Evaluation is left-to-right. `and` and `or` produce boolean results in the Core
Profile. Division by zero is a runtime error.

## 6. Values

The Core Profile defines:

- `none`
- booleans: `true`, `false`
- signed integers
- floating-point numbers
- strings
- lists
- maps
- function values used by direct calls

Implementations may use different internal number widths. Portable programs
must keep integers within signed 64-bit range and must not depend on exact
floating-point formatting.

List indexes are zero-based. Negative list and string indexes count from the
end. Missing map keys and out-of-range indexes are runtime errors.

## 7. Statements and Control Flow

Assignments update an existing name or the name declared in the current scope.
Function parameters and declarations inside a function are local to that
function.

Mellow 2.9 Core functions do not define closure capture. Portable functions
must receive external values as parameters.

`range(start, stop)` includes `start` and excludes `stop`. A Core Profile
`for` loop uses exactly two range arguments.

```mellow
let total = 0
for i in range(0, 5):
    total = total + i
print(total)
```

## 8. Standard Built-ins

Every Core Profile implementation provides:

| Built-in | Contract |
|---|---|
| `print(values...)` | Writes values separated by one space and then a newline |
| `len(value)` | Length of a string, list, or map |
| `str(value)` | Human-readable string conversion |
| `type(value)` | Stable lowercase type name |
| `abs(number)` | Absolute value |
| `floor(number)` | Greatest integer not above the value |
| `ceil(number)` | Smallest integer not below the value |
| `sqrt(number)` | Square root |
| `min(a, b)` | Smaller numeric value |
| `max(a, b)` | Larger numeric value |
| `range(start, stop)` | Integer sequence used by Core `for` loops |

Host services such as money, data, ledger, files, network, events, packages,
and AI are libraries or extended profiles. They are not grammar.

## 9. Errors

A syntax error must:

- return a non-zero process status;
- identify the source line when available;
- not execute a partially compiled program.

A runtime error must return a non-zero process status. Exact diagnostic wording
is not frozen in 2.9, but error categories and successful-program behavior are.

## 10. Core Conformance Program

The repository conformance program is
`tests/fixtures/full_native_core.mellow`. Its required output is:

```text
30
mellow
3
```

Both the Python runtime and the Full Native C executable must preserve this
result.

## 11. Non-Core Syntax

The following syntax may remain supported by the Python implementation but is
not portable Mellow 2.9 Core syntax:

- `var`, `fn`, `function`, `skill`, `show`, `ask`
- `elif`, `check`, `also`
- `null`
- `//` comments
- `do ... end`
- multi-assignment and tuple unpacking
- default/named arguments, lambdas, closures
- comprehensions, spread, slices
- `try`, `catch`, `finally`
- imports, events, save/load, wait, sandbox commands

Tools and documentation must label these forms as compatibility, extended, or
experimental. Their presence must not silently expand the Core Profile.

## 12. Change Process

Changing this specification requires:

1. a proposal describing syntax, semantics, migration, and native impact;
2. parser/compiler implementation in both Python and C;
3. positive and negative conformance tests;
4. an update to the language version when grammar or semantics change;
5. a changelog entry.

No syntax becomes Core merely because one parser accepts it.
