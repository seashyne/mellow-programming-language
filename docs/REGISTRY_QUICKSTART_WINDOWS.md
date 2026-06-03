# Registry Quickstart (Windows)

Run from the project root.

```powershell
py -m pip install -e .
mellow registry https://your-worker.workers.dev
mellow login --token your-token
mellow whoami
```

If `mellow` on PATH is stale, use the local launcher:

```powershell
.\mellow.ps1 registry https://your-worker.workers.dev
.\mellow.ps1 login --token your-token
.\mellow.ps1 whoami
```
