# core-llm

Official package for local language-model experiments in Mellow.

The package wraps Mellow's AI host bridge for dependency-free character-level
causal language models. It provides a product-facing API for dataset preparation,
training, evaluation, generation, chat-shaped completions, and checkpointing.

The bundled backend is useful for local prototypes and tests, while larger
production LLMs should live in provider packages that preserve this API shape.

Backends:

- `tiny-causal-char-lm`: dependency-free local model.
- `mellow-native`: official Mellow-owned backend contract for future native
  tensor kernels and transformer training.
- `transformer-torch`: optional PyTorch transformer backend target.

`mellow-native` currently exposes conformance-covered tensor kernels for
`matmul`, `softmax`, `layer_norm`, and `gelu`, with Python reference fallback
when the optional C extension is not built.
