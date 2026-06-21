# Mellow Interop

Mellow can call tools written in other languages through a small JSON stdio
bridge. This keeps the language core simple while still allowing real projects
to use JavaScript, TypeScript, Go, Rust, Java, C++, C#, COBOL, Python, or any
other runtime that can read stdin and write stdout.

Interop is deny-by-default. In project mode, allow only the commands you need:

```json
{
  "entry": "main.mel",
  "permissions": [
    "interop:node",
    "interop:go"
  ]
}
```

You can also use the object form:

```json
{
  "permissions": {
    "interop": ["node", "go", "java"]
  }
}
```

For local experiments outside project mode, set `MELLOW_INTEROP_ALLOW`:

```powershell
$env:MELLOW_INTEROP_ALLOW = "node,go"
```

## Mellow API

```mellow
keep info = get interop.describe()
keep result = get interop.run("node", ["tools/hello.js"], {"name": "Mellow"})
print(result)
```

`interop.run(command, args=[], payload={}, options={})` sends this JSON to the
external process on stdin:

```json
{
  "protocol": "mellow.interop.v1",
  "payload": {"name": "Mellow"}
}
```

If stdout is JSON, Mellow returns it in `result`. If stdout is plain text, Mellow
returns `{"stdout": "..."}`.

Return shape:

```json
{
  "ok": true,
  "code": 0,
  "result": {"hello": "Mellow"},
  "stdout": "{\"hello\":\"Mellow\"}\n",
  "stderr": ""
}
```

Options:

- `timeout_s`: process timeout, 0-30 seconds, default 5
- `max_stdout`: stdout/stderr capture limit, default 1000000
- `cwd`: working directory relative to `project_root` in project mode

## Language Examples

JavaScript:

```js
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
console.log(JSON.stringify({ hello: input.payload.name }));
```

Go:

```go
package main

import (
  "encoding/json"
  "fmt"
  "os"
)

func main() {
  var input map[string]any
  json.NewDecoder(os.Stdin).Decode(&input)
  payload := input["payload"].(map[string]any)
  out := map[string]any{"hello": payload["name"]}
  b, _ := json.Marshal(out)
  fmt.Println(string(b))
}
```

Rust, Java, C++, C#, COBOL, and TypeScript follow the same contract: read JSON
from stdin and print JSON to stdout. For compiled languages, prefer building a
binary first and allowlisting that binary name.

## Security Boundary

Interop is for trusted local tools. Mellow does not invoke a shell, but the
allowed command still runs with the user's OS permissions. Keep allowlists
specific, use short timeouts, and avoid `interop:*` except in isolated dev
environments.
