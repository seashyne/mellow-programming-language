"""TinyCausalLM plus the torch/device probing it needs."""

from __future__ import annotations

import math
import os
import random
import time
from typing import Any, Dict, List, Optional


class TinyCausalLM:
    """Dependency-free character n-gram language model for local LLM experiments."""

    def __init__(self, name: str, order: int = 3, seed: int = 42):
        self.name = name
        self.order = max(1, min(int(order), 8))
        self.seed = int(seed)
        self.vocab: List[str] = []
        self.transitions: Dict[str, Dict[str, int]] = {}
        self.trained_tokens = 0
        self.loss_history: List[float] = []
        self.created_at = int(time.time())

    def _context(self, prefix: str) -> str:
        return prefix[-self.order:]

    def _add_vocab(self, text: str) -> None:
        seen = set(self.vocab)
        for ch in text:
            if ch not in seen:
                self.vocab.append(ch)
                seen.add(ch)
        self.vocab.sort()

    def train(self, texts: List[str], epochs: int = 1) -> float:
        clean = [str(t) for t in texts if str(t)]
        if not clean:
            return 0.0
        joined = "\n".join(clean)
        self._add_vocab(joined)
        total_loss = 0.0
        for _ in range(max(1, int(epochs))):
            for text in clean:
                history = ""
                for ch in text:
                    ctx = self._context(history)
                    bucket = self.transitions.setdefault(ctx, {})
                    bucket[ch] = bucket.get(ch, 0) + 1
                    history += ch
                    self.trained_tokens += 1
            total_loss = self.loss(clean)
            self.loss_history.append(round(total_loss, 6))
        return total_loss

    def loss(self, texts: List[str]) -> float:
        vocab_size = max(len(self.vocab), 1)
        nll = 0.0
        count = 0
        for text in texts:
            history = ""
            for ch in text:
                bucket = self.transitions.get(self._context(history), {})
                total = sum(bucket.values())
                prob = (bucket.get(ch, 0) + 1.0) / (total + vocab_size)
                nll -= math.log(prob)
                count += 1
                history += ch
        return nll / max(count, 1)

    def evaluate(self, texts: List[str]) -> dict:
        clean = [str(t) for t in texts if str(t)]
        loss = self.loss(clean) if clean else 0.0
        return {
            "loss": round(loss, 6),
            "perplexity": round(math.exp(min(loss, 20.0)), 6),
            "samples": len(clean),
            "tokens": sum(len(t) for t in clean),
        }

    def generate(
        self,
        prompt: str = "",
        max_tokens: int = 64,
        temperature: float = 1.0,
        seed: Optional[int] = None,
        top_k: int = 0,
        stop: Optional[List[str]] = None,
    ) -> str:
        if not self.vocab:
            return prompt
        rng = random.Random(self.seed if seed is None else int(seed))
        out = str(prompt)
        temp = max(float(temperature), 0.001)
        stop_tokens = [str(s) for s in (stop or []) if str(s)]
        for _ in range(max(0, int(max_tokens))):
            bucket = self.transitions.get(self._context(out))
            choices = bucket or {ch: 1 for ch in self.vocab}
            if top_k and top_k > 0:
                choices = dict(sorted(choices.items(), key=lambda item: item[1], reverse=True)[: int(top_k)])
            weighted = []
            total = 0.0
            for ch, count in sorted(choices.items()):
                weight = max(float(count), 0.001) ** (1.0 / temp)
                weighted.append((ch, weight))
                total += weight
            pick = rng.random() * total
            upto = 0.0
            next_ch = weighted[-1][0]
            for ch, weight in weighted:
                upto += weight
                if upto >= pick:
                    next_ch = ch
                    break
            out += next_ch
            if stop_tokens and any(out.endswith(token) for token in stop_tokens):
                break
        return out

    def to_dict(self) -> dict:
        return {
            "kind": "tiny-causal-char-lm",
            "name": self.name,
            "order": self.order,
            "seed": self.seed,
            "vocab": self.vocab,
            "transitions": self.transitions,
            "trained_tokens": self.trained_tokens,
            "loss_history": self.loss_history[-50:],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TinyCausalLM":
        model = cls(str(data.get("name", "llm")), int(data.get("order", 3)), int(data.get("seed", 42)))
        model.vocab = [str(ch) for ch in data.get("vocab", [])]
        model.transitions = {
            str(ctx): {str(ch): int(count) for ch, count in dict(bucket).items()}
            for ctx, bucket in dict(data.get("transitions", {})).items()
        }
        model.trained_tokens = int(data.get("trained_tokens", 0))
        model.loss_history = [float(v) for v in data.get("loss_history", [])]
        model.created_at = int(data.get("created_at", int(time.time())))
        return model

def _torch_status() -> Dict[str, Any]:
    try:
        import torch  # type: ignore
    except Exception as exc:
        return {
            "available": False,
            "backend": "transformer-torch",
            "reason": f"torch unavailable: {exc.__class__.__name__}",
            "devices": [{"id": "cpu", "type": "cpu", "available": True, "workers": os.cpu_count() or 1}],
        }

    devices = [{"id": "cpu", "type": "cpu", "available": True, "workers": os.cpu_count() or 1}]
    cuda_available = bool(getattr(torch.cuda, "is_available", lambda: False)())
    cuda_count = int(getattr(torch.cuda, "device_count", lambda: 0)()) if cuda_available else 0
    for idx in range(cuda_count):
        props = torch.cuda.get_device_properties(idx)
        devices.append({
            "id": f"cuda:{idx}",
            "type": "cuda",
            "available": True,
            "name": getattr(props, "name", f"CUDA {idx}"),
            "memory_gb": round(float(getattr(props, "total_memory", 0)) / (1024 ** 3), 3),
        })
    return {
        "available": True,
        "backend": "transformer-torch",
        "version": getattr(torch, "__version__", "unknown"),
        "cuda": cuda_available,
        "cuda_count": cuda_count,
        "devices": devices,
    }

def _device_plan(config: Dict[str, Any]) -> Dict[str, Any]:
    requested = config.get("devices", "auto")
    workers = max(1, int(config.get("cpu_workers", os.cpu_count() or 1)))
    torch_info = _torch_status()
    devices = torch_info["devices"]

    if requested == "auto":
        selected = [d for d in devices if d["type"] == "cuda"] or [{"id": "cpu", "type": "cpu", "workers": workers}]
    elif requested == "cpu":
        selected = [{"id": "cpu", "type": "cpu", "workers": workers}]
    elif requested == "cuda:all":
        selected = [d for d in devices if d["type"] == "cuda"]
    elif isinstance(requested, list):
        allowed = {str(item) for item in requested}
        selected = [d for d in devices if d["id"] in allowed]
    else:
        selected = [d for d in devices if d["id"] == str(requested)]

    if not selected:
        selected = [{"id": "cpu", "type": "cpu", "workers": workers, "fallback": True}]

    strategy = "single"
    if len(selected) > 1 and any(d.get("type") == "cuda" for d in selected):
        strategy = "data-parallel"
    elif selected[0].get("type") == "cpu" and workers > 1:
        strategy = "cpu-threaded"

    return {
        "requested": requested,
        "selected": selected,
        "strategy": strategy,
        "torch": torch_info,
    }

def _llm_texts(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value is None:
        return []
    return [str(value)] if str(value) else []

def _llm_dataset_from_texts(texts: List[str], options: Dict[str, Any]) -> dict:
    chunk_chars = max(1, int(options.get("chunk_chars", options.get("max_chars", 512))))
    stride = int(options.get("stride", chunk_chars))
    stride = max(1, min(stride, chunk_chars))
    min_chars = max(1, int(options.get("min_chars", 1)))
    samples: List[str] = []
    total_chars = 0
    for text in texts:
        total_chars += len(text)
        if len(text) <= chunk_chars:
            if len(text) >= min_chars:
                samples.append(text)
            continue
        start = 0
        while start < len(text):
            chunk = text[start:start + chunk_chars]
            if len(chunk) >= min_chars:
                samples.append(chunk)
            start += stride
    return {
        "samples": samples,
        "count": len(samples),
        "chars": total_chars,
        "chunk_chars": chunk_chars,
        "stride": stride,
    }

def _llm_prompt_from_messages(messages: Any) -> str:
    if isinstance(messages, list):
        parts = []
        for item in messages:
            if isinstance(item, dict):
                role = str(item.get("role", "user"))
                content = str(item.get("content", ""))
                if content:
                    parts.append(f"{role}: {content}")
            else:
                parts.append(f"user: {item}")
        parts.append("assistant:")
        return "\n".join(parts)
    return str(messages)
