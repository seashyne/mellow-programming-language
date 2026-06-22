# Mellow SDK — same shape as the Python OpenAI SDK

Mellow cannot use `client.chat.completions.create(...)` as a method chain yet.
The client is passed as the **first argument** instead:

| Python | Mellow |
| --- | --- |
| `from openai import OpenAI` | `use mellow-sdk as openai` |
| `client = OpenAI(api_key=..., base_url=...)` | `let client = openai.OpenAI({...})` |
| `client.chat.completions.create(...)` | `call chat.completions_create(client, model, messages, options)` |
| `response.choices[0].message.content` | `response["choices"][0]["message"]["content"]` |

Use Python when you only need a quick API script. Use this package when the rest
of the project is already `.mellow`.

## DeepSeek example

### Python

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ],
    stream=False,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)

print(response.choices[0].message.content)
```

### Mellow

```mellow
use mellow-sdk as openai

let client = openai.OpenAI({
    "api_key_env": "DEEPSEEK_API_KEY",
    "base_url": "https://api.deepseek.com"
})

let response = call chat.completions_create(
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

print(response["choices"][0]["message"]["content"])
```

Package-only equivalent (no global `chat` module):

```mellow
let response = openai.ChatCompletions_create(client, "deepseek-chat", messages, options)
```

## Setup

```powershell
python -m pip install -e ".[sdk]"
$env:DEEPSEEK_API_KEY = "sk-..."
mellow run main.mellow --engine=py
```

```json
{
  "permissions": ["net", "net.http:https://api.deepseek.com/", "net.timeout_s:60"]
}
```

## Why one argument differs

Python binds `client` as the receiver: `client.chat.completions.create(...)`.

Mellow currently exposes host calls as `module.function(...)`, so the client is
the first argument: `call chat.completions_create(client, ...)`.

Everything else follows the same names and payload shape as the Python SDK.
