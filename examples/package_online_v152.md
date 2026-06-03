# Online package flow (v1.5.2)

```bash
python -m mellowlang.registry.server --host 127.0.0.1 --port 8089
mellow pkg registry http://127.0.0.1:8089
mellow pkg login --username admin --password admin
mellow pkg init physics2d
mellow pkg publish physics2d --online
mellow pkg search physics
mellow pkg install physics2d --online
```
