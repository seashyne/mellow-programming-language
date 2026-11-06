# core-server

HTTP route and response helpers for Mellow server apps.

```mellow
import "pkg:core-server" as server

keep req = server.request()
if req["path"] == "/hello":
    server.json({"ok": true, "path": req["path"]})
else:
    server.status(404, {"error": "not found"})
```

Run it with:

```bash
./mellow server serve app.mellow
```
