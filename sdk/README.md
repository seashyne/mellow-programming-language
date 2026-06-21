# Mellow SDK

Python helpers for OpenAI-compatible providers.

For Mellow scripts, import the starter package:

```mellow
use mellow-sdk as openai
```

Read `docs/MELLOW_SDK.md` for the Python vs Mellow decision guide.

## Python-only quick start

```powershell
pip install openai
$env:DEEPSEEK_API_KEY = "sk-..."
python -m mellow_sdk.openai_bridge
```

Send JSON on stdin with `base_url`, `model`, `messages`, and optional `options`.
