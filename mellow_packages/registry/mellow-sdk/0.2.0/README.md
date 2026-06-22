# mellow-sdk

OpenAI-compatible chat SDK for Mellow scripts.

Use this package when your project already lives in `.mellow`. If you only need a
quick API script, Python is still simpler — see `docs/MELLOW_SDK.md`.

## Install

```powershell
python -m pip install -e ".[sdk]"
```

## Permissions

```json
{
  "entry": "main.mellow",
  "permissions": [
    "net",
    "net.http:https://api.deepseek.com/",
    "net.timeout_s:60"
  ]
}
```

```powershell
$env:DEEPSEEK_API_KEY = "sk-..."
mellow run main.mellow --engine=py
```

## Python vs Mellow

| Python | Mellow |
| --- | --- |
| `from openai import OpenAI` | `use mellow-sdk as openai` |
| `OpenAI(api_key=..., base_url=...)` | `openai.OpenAI({...})` |
| `OpenAI(..., base_url="https://api.deepseek.com")` | `openai.DeepSeek({})` |
| `client.chat.completions.create(...)` | `openai.chat_completions_create(client, model, messages, options)` |
| `response.choices[0].message.content` | `response["choices"][0]["message"]["content"]` |
| shortcut | `response["content"]` or `openai.response_content(response)` |

## DeepSeek example

```mellow
use mellow-sdk as openai

let client = openai.DeepSeek({})
let response = openai.chat_completions_create(
    client,
    "deepseek-chat",
    [
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"}
    ],
    {
        "stream": false,
        "reasoning_effort": "high",
        "extra_body": {"thinking": {"type": "enabled"}}
    }
)
print(openai.response_content(response))
```

## OpenAI example

```mellow
use mellow-sdk as openai

let client = openai.OpenAI({
    "api_key_env": "OPENAI_API_KEY",
    "base_url": "https://api.openai.com/v1"
})
let response = openai.chat_completions_create(
    client,
    "gpt-4o-mini",
    [{"role": "user", "content": "Summarize MellowLang in one line"}],
    {"max_tokens": 64}
)
print(response["content"])
```

## Notes

- Import the package as `openai` to mirror the Python mental model.
- Network calls use the Python engine (`--engine=py`) today.
- Legacy helpers `deepseek()`, `chat()`, and `text()` still work but are not the
  recommended API.
