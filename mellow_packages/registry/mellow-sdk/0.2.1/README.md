# mellow-sdk

Short OpenAI-compatible chat SDK for Mellow.

## Short API (recommended)

```mellow
use mellow-sdk as ai

print(ai.txt(ai.ask("Hello", none)))
```

```mellow
use mellow-sdk as ai

let c = ai.ds(none)
let r = ai.chat(c, "deepseek-chat", [{"role": "user", "content": "Hello"}], none)
print(ai.txt(r))
```

| Function | Meaning |
| --- | --- |
| `ai.ds()` | DeepSeek client |
| `ai.oa()` | OpenAI client |
| `ai.mk({...})` | custom client |
| `ai.chat(c, model, msgs, opts)` | chat completion |
| `ai.txt(r)` | response text |
| `ai.ask(prompt, opts)` | one-shot DeepSeek |

## Setup

```powershell
python -m pip install -e ".[sdk]"
$env:DEEPSEEK_API_KEY = "sk-..."
mellow run main.mellow --engine=py
```

`mellow.json` permissions:

```json
["net", "net.http:https://api.deepseek.com/", "net.timeout_s:60"]
```

## Python-compat names

Longer aliases still work: `OpenAI()`, `DeepSeek()`, `chat_completions_create()`.

See `docs/MELLOW_SDK.md` for Python vs Mellow.
