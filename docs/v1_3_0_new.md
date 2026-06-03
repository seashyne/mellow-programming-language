# MellowLang v1.3.0 NEW (Hybrid)

## What’s new
- `mellow test <path> --engine=dual` : run tests in both engines and compare results.
- `mellow replay <file> --input run.jsonl` : replay a recorded run.
- `mellow diff run1.jsonl run2.jsonl` : find the first difference between logs.
- `mellow run` supports `--engine=auto|py|c`.

## Quickstart
```bash
python -m pip install -e .

# Run a script (auto prefers C VM if available)
mellow run examples/hello.mellow --engine=auto

# Dual-engine test (parity check)
mellow test tests --engine=dual

# Record / replay (deterministic)
mellow run examples/ai_small.mellow --record run.jsonl --engine=py
mellow replay examples/ai_small.mellow --input run.jsonl --engine=py

# Diff logs
mellow diff run.jsonl run2.jsonl
```

## Notes
- Hybrid means: **Python compiler & tooling**, **C runtime (optional)**.
- If you use `--record` / `--replay`, v1.3.0 currently runs on Python engine to guarantee correct log semantics.
