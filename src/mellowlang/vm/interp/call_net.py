"""Net and websocket builtins, second in the storage name walk. One step of the storage name walk."""

from __future__ import annotations

from .actions import _NEXT, _PASS


class NetGroupMixin:
    def _call_net_builtins(self, f_name: str, args: list, kwargs: dict) -> object:
        """Net and websocket builtins, second in the storage name walk."""
        if f_name in ('net_http_post','net_http_get','net_ws_connect','net_ws_send','net_ws_recv','net_ws_close','net_ws_state'):
            if not bool(self.config.get('allow_net', False)):
                self._raise_sandbox('net is disabled')
            from ...net_core import http_post_json, http_get_json, ws_manager
            import base64

            # Limits
            max_bytes = int(self.config.get('net_max_bytes', 262144) or 262144)
            timeout_s = float(self.config.get('net_timeout_s', 10.0) or 10.0)

            def _check_url(url: str, kind: str) -> None:
                key = 'net_http_allow' if kind == 'http' else 'net_ws_allow'
                allow = str(self.config.get(key) or '')
                if not allow:
                    self._raise_sandbox(f'net_{kind}: no allowlist configured')
                ok = False
                for prefix in allow.split(','):
                    prefix = prefix.strip()
                    if prefix and url.startswith(prefix):
                        ok = True
                        break
                if not ok:
                    self._raise_sandbox(f'net_{kind}: url not allowlisted')

            if f_name == 'net_http_post':
                if len(args) < 2:
                    self._raise_runtime('net_http_post expects 2 args: url, json_obj')
                url = str(args[0])
                _check_url(url, 'http')
                body = args[1]
                if not isinstance(body, dict):
                    self._raise_runtime('net_http_post: json_obj must be a map')
                token = str(args[2]) if len(args) > 2 and args[2] is not None else None
                headers = {}
                if token:
                    headers['Authorization'] = f"Bearer {token}"
                try:
                    resp = http_post_json(url, body, timeout_s=timeout_s, headers=headers)
                except Exception as e:
                    self._raise_runtime(str(e))
                # crude size guard
                import json as _json
                raw = _json.dumps(resp, ensure_ascii=False).encode('utf-8')
                if len(raw) > max_bytes:
                    self._raise_runtime('NET_QUOTA_BYTES: response too large')
                self.stack.append(resp)
                self.pc += 1
                return _NEXT

            if f_name == 'net_http_get':
                if len(args) < 1:
                    self._raise_runtime('net_http_get expects 1 arg: url')
                url = str(args[0])
                _check_url(url, 'http')
                token = str(args[1]) if len(args) > 1 and args[1] is not None else None
                headers = {}
                if token:
                    headers['Authorization'] = f"Bearer {token}"
                try:
                    resp = http_get_json(url, timeout_s=timeout_s, headers=headers)
                except Exception as e:
                    self._raise_runtime(str(e))
                import json as _json
                raw = _json.dumps(resp, ensure_ascii=False).encode('utf-8')
                if len(raw) > max_bytes:
                    self._raise_runtime('NET_QUOTA_BYTES: response too large')
                self.stack.append(resp)
                self.pc += 1
                return _NEXT

            if f_name == 'net_ws_connect':
                if len(args) < 1:
                    self._raise_runtime('net_ws_connect expects 1 arg: url')
                url = str(args[0])
                _check_url(url, 'ws')
                token = str(args[1]) if len(args) > 1 and args[1] is not None else None
                headers = {}
                if token:
                    headers['Authorization'] = f"Bearer {token}"
                hid = ws_manager().connect(url, headers=headers)
                self.stack.append(int(hid))
                self.pc += 1
                return _NEXT

            if f_name == 'net_ws_send':
                if len(args) < 2:
                    self._raise_runtime('net_ws_send expects 2 args: conn_id, data')
                hid = int(args[0])
                data = args[1]
                if isinstance(data, str):
                    b = data.encode('utf-8')
                elif isinstance(data, bytes):
                    b = data
                else:
                    # allow json map/list
                    import json as _json
                    b = _json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode('utf-8')
                if len(b) > max_bytes:
                    self._raise_runtime('NET_QUOTA_BYTES: payload too large')
                ok = ws_manager().send(hid, b)
                self.stack.append(bool(ok))
                self.pc += 1
                return _NEXT

            if f_name == 'net_ws_recv':
                if len(args) < 1:
                    self._raise_runtime('net_ws_recv expects 1 arg: conn_id')
                hid = int(args[0])
                tout = float(args[1]) if len(args) > 1 and args[1] is not None else 0.0
                b = ws_manager().recv(hid, timeout_s=tout)
                if b is None:
                    self.stack.append(None)
                else:
                    if len(b) > max_bytes:
                        self._raise_runtime('NET_QUOTA_BYTES: incoming message too large')
                    # return utf-8 string if possible, else base64
                    try:
                        self.stack.append(b.decode('utf-8'))
                    except Exception:
                        self.stack.append(base64.b64encode(b).decode('ascii'))
                self.pc += 1
                return _NEXT

            if f_name == 'net_ws_close':
                if len(args) < 1:
                    self._raise_runtime('net_ws_close expects 1 arg: conn_id')
                hid = int(args[0])
                self.stack.append(bool(ws_manager().close(hid)))
                self.pc += 1
                return _NEXT

            if f_name == 'net_ws_state':
                if len(args) < 1:
                    self._raise_runtime('net_ws_state expects 1 arg: conn_id')
                hid = int(args[0])
                self.stack.append(ws_manager().state(hid))
                self.pc += 1
                return _NEXT
        return _PASS
