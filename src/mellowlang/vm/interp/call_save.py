"""Signed-save and journal builtins, first in the storage name walk. One step of the storage name walk."""

from __future__ import annotations

from .actions import _NEXT, _PASS


class SaveGroupMixin:
    def _call_save_builtins(self, f_name: str, args: list, kwargs: dict) -> object:
        """Signed-save and journal builtins, first in the storage name walk."""
        if f_name in ('save_init','save_set','save_get','save_commit','save_load','save_list','save_delete','save_clear',
                      'save_commit_signed','save_load_signed'):
            if not bool(self.config.get('allow_save', True)):
                self._raise_sandbox('save is disabled')
            from ...save_core import SaveSystem, SaveLimits
            from ...net_core import http_post_json, b64_decode
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from cryptography.hazmat.primitives import hashes
            import base64

            # state
            app_id = str(self.config.get('save_app_id') or '')
            buf = self.config.get('save_buffer')
            if not isinstance(buf, dict):
                buf = {}
                self.config['save_buffer'] = buf

            limits = SaveLimits(
                max_slots=int(self.config.get('save_slots_max', 10) or 10),
                max_bytes=int(self.config.get('save_bytes_max', 1_048_576) or 1_048_576),
            )

            def _require_app_id():
                if not app_id:
                    self._raise_runtime('SAVE_NOT_INITIALIZED: call save_init(app_id="...") first')

            if f_name == 'save_init':
                # save_init(app_id="my.game")
                if len(args) < 1:
                    self._raise_runtime('save_init expects 1 arg: app_id')
                app_id2 = str(args[0])
                self.config['save_app_id'] = app_id2
                # reset buffer on init
                self.config['save_buffer'] = {}
                # touch directory
                _ = SaveSystem(app_id=app_id2, limits=limits)
                self.stack.append(True)
                self.pc += 1
                return _NEXT

            _require_app_id()
            ss = SaveSystem(app_id=app_id, limits=limits)
            if f_name == 'save_set':
                if len(args) < 2:
                    self._raise_runtime('save_set expects 2 args: key, value')
                k = str(args[0])
                v = args[1]
                buf[k] = v
                self.stack.append(True)
                self.pc += 1
                return _NEXT
            if f_name == 'save_get':
                if len(args) < 1:
                    self._raise_runtime('save_get expects 1 arg: key')
                k = str(args[0])
                default = args[1] if len(args) > 1 else None
                self.stack.append(buf.get(k, default))
                self.pc += 1
                return _NEXT
            if f_name == 'save_clear':
                buf.clear()
                self.stack.append(True)
                self.pc += 1
                return _NEXT
            if f_name == 'save_commit':
                if len(args) < 1:
                    self._raise_runtime('save_commit expects 1 arg: slot')
                slot = str(args[0])
                try:
                    ss.commit(slot, dict(buf))
                except Exception as e:
                    self._raise_runtime(str(e))
                self.stack.append(True)
                self.pc += 1
                return _NEXT
            if f_name == 'save_commit_signed':
                # save_commit_signed(slot, url, pubkey_b64, token=None)
                if len(args) < 3:
                    self._raise_runtime('save_commit_signed expects 3 args: slot, url, pubkey_b64')
                slot = str(args[0])
                url = str(args[1])
                pub_b64 = str(args[2])
                token = str(args[3]) if len(args) > 3 and args[3] is not None else None

                if not bool(self.config.get('allow_net', False)):
                    self._raise_sandbox('net is disabled')
                # Allowlist check (http)
                allow = str(self.config.get('net_http_allow') or '')
                if allow:
                    ok = False
                    for prefix in allow.split(','):
                        prefix = prefix.strip()
                        if prefix and url.startswith(prefix):
                            ok = True
                            break
                    if not ok:
                        self._raise_sandbox('net_http: url not allowlisted')

                # Canonical plaintext payload (same as SaveSystem)
                import json as _json
                payload_bytes = _json.dumps(dict(buf), ensure_ascii=False, separators=(",", ":")).encode('utf-8')
                digest = hashes.Hash(hashes.SHA256())
                digest.update(payload_bytes)
                hhex = digest.finalize().hex()

                headers = {}
                if token:
                    headers['Authorization'] = f"Bearer {token}"
                try:
                    resp = http_post_json(url, {
                        'app_id': app_id,
                        'slot': slot,
                        'hash_sha256': hhex,
                    }, timeout_s=float(self.config.get('net_timeout_s', 10.0) or 10.0), headers=headers)
                except Exception as e:
                    self._raise_runtime(str(e))

                sig_b64 = resp.get('signature_b64') or resp.get('sig_b64') or resp.get('signature')
                if not isinstance(sig_b64, str) or not sig_b64:
                    self._raise_runtime('SAVE_SIGNATURE: server did not return signature_b64')
                try:
                    sig = base64.b64decode(sig_b64.encode('ascii'))
                except Exception:
                    self._raise_runtime('SAVE_SIGNATURE: invalid base64 signature')
                # Verify signature locally before writing
                try:
                    pk = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64.encode('ascii')))
                    pk.verify(sig, bytes.fromhex(hhex))
                except Exception:
                    self._raise_runtime('SAVE_SIGNATURE_INVALID: signature verify failed')
                try:
                    ss.commit_signed(slot, dict(buf), signature=sig)
                except Exception as e:
                    self._raise_runtime(str(e))
                self.stack.append(True)
                self.pc += 1
                return _NEXT
            if f_name == 'save_load':
                if len(args) < 1:
                    self._raise_runtime('save_load expects 1 arg: slot')
                slot = str(args[0])
                try:
                    obj = ss.load(slot)
                except Exception as e:
                    self._raise_runtime(str(e))
                if obj is None:
                    self.stack.append(False)
                else:
                    buf.clear()
                    buf.update(obj)
                    self.stack.append(True)
                self.pc += 1
                return _NEXT
            if f_name == 'save_load_signed':
                # save_load_signed(slot, pubkey_b64)
                if len(args) < 2:
                    self._raise_runtime('save_load_signed expects 2 args: slot, pubkey_b64')
                slot = str(args[0])
                pub_b64 = str(args[1])
                try:
                    obj = ss.load(slot)
                except Exception as e:
                    self._raise_runtime(str(e))
                if obj is None:
                    self.stack.append(False)
                    self.pc += 1
                    return _NEXT
                sig_hex = obj.get('$signature')
                if not isinstance(sig_hex, str) or not sig_hex:
                    self._raise_runtime('SAVE_UNSIGNED: save file has no server signature')
                # Remove signature from buffer
                try:
                    sig = bytes.fromhex(sig_hex)
                except Exception:
                    self._raise_runtime('SAVE_CORRUPT: invalid signature encoding')
                obj2 = dict(obj)
                obj2.pop('$signature', None)

                import json as _json
                payload_bytes = _json.dumps(obj2, ensure_ascii=False, separators=(",", ":")).encode('utf-8')
                digest = hashes.Hash(hashes.SHA256())
                digest.update(payload_bytes)
                hhex = digest.finalize().hex()
                try:
                    pk = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64.encode('ascii')))
                    pk.verify(sig, bytes.fromhex(hhex))
                except Exception:
                    self._raise_runtime('SAVE_SIGNATURE_INVALID: signature verify failed')
                buf.clear()
                buf.update(obj2)
                self.stack.append(True)
                self.pc += 1
                return _NEXT
            if f_name == 'save_list':
                self.stack.append(ss.list_slots())
                self.pc += 1
                return _NEXT
            if f_name == 'save_delete':
                if len(args) < 1:
                    self._raise_runtime('save_delete expects 1 arg: slot')
                slot = str(args[0])
                self.stack.append(ss.delete_slot(slot))
                self.pc += 1
                return _NEXT
        return _PASS
