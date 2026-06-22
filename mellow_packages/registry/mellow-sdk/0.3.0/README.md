# mellow-sdk

OpenAI Python SDK shape for Mellow scripts.

```mellow
use mellow-sdk as openai

let client = openai.OpenAI({
    "api_key_env": "DEEPSEEK_API_KEY",
    "base_url": "https://api.deepseek.com"
})

let response = call chat.completions_create(
    client,
    "deepseek-chat",
    [{"role": "user", "content": "Hello"}],
    none
)

print(response["choices"][0]["message"]["content"])
```

See `docs/MELLOW_SDK.md` for the full Python side-by-side mapping.
