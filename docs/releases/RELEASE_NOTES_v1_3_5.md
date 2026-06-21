# Release Notes — v1.3.5

This release adds **always-online primitives** and a complete **Hybrid Save (Level C)** standard.

## Added

### Networking (project-mode safe)

- `net_http_get(url, token=None)`
- `net_http_post(url, json_obj, token=None)`
- `net_ws_connect(url, token=None)`
- `net_ws_send(conn_id, data)`
- `net_ws_recv(conn_id, timeout_s=0)`
- `net_ws_state(conn_id)`
- `net_ws_close(conn_id)`

Networking is **deny-by-default** in project mode and must be enabled via `mellow.json` permissions.

### Hybrid Save (Level C)

- `save_commit_signed(slot, sign_url, pubkey_b64, token=None)`
- `save_load_signed(slot, pubkey_b64)`

Signed saves use **Ed25519** signatures returned by your server. Any local tampering will fail verification.

## Changed

- Save file format now supports `ver=2` (signed). Reading `ver=1` (unsigned) remains supported.

## Project permissions

In `mellow.json`:

```json
{
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

## Tests

- Added test coverage for:
  - Signed save commit/load + tamper detection
  - HTTP JSON request/response
  - WebSocket echo send/recv
