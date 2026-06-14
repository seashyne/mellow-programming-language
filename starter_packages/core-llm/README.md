# core-llm

Official starter package for local language-model experiments in Mellow.

This package keeps LLM experimentation outside the core language runtime. It
wraps the built-in AI host bridge for a dependency-free character-level causal
model that can prepare datasets, train, evaluate, generate, expose chat-style
results, inspect, save, and load small checkpoints.

It is intended for local learning, tests, game dialogue prototypes, and package
API design. Production-quality LLMs should use a provider package such as an
Ollama, vLLM, or hosted API adapter.

```mellow
use core-llm as llm

llm.create("demo", {"order": 3, "seed": 7})
let data = llm.dataset(["hello mellow", "mellow learns"], {"chunk_chars": 64})
llm.train("demo", data, {"epochs": 2})
let score = llm.eval("demo", data)
let out = llm.complete("demo", "mel", {"max_tokens": 24, "seed": 7})
print(score["perplexity"])
print(out["text"])
```

This package is product-facing API surface, not a claim that the bundled tiny
backend competes with transformer LLMs. The API is designed so heavier provider
packages can keep the same shape.

## Backends

`core-llm` exposes a backend contract so Mellow can grow beyond the bundled tiny
model without changing user scripts.

- `tiny-causal-char-lm`: dependency-free local model for tests and small demos.
- `mellow-native`: official Mellow-owned backend contract. It is ready for
  device planning and API integration, but needs native tensor kernels before it
  should claim transformer training.
- `transformer-torch`: optional GPT/Transformer backend target through PyTorch.
  Install with `python -m pip install -e .[llm]`.

```mellow
let backends = llm.backends()
let plan = llm.device_plan({"backend": "mellow-native", "cpu_workers": 8})
print(plan["status"])
```

The Mellow-native backend should evolve in layers:

1. CPU tensor core in C: matmul, softmax, layer norm, GELU, attention, AdamW.
2. Transformer graph/runtime: tokenizer, GPT block, checkpoint format.
3. Multi-device scheduler: CPU threads first, then CUDA/Vulkan/Metal plugins.
4. Training product layer: streaming datasets, checkpoints, eval, logs.

The first tensor layer now has conformance-covered kernels for `matmul`,
`softmax`, `layer_norm`, and `gelu`. If the optional native extension is not
built, `core-llm` falls back to the Python reference kernels with the same API.
