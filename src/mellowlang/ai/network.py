"""The feed-forward network: _Layer and MellowModel."""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List


from .numerics import _add_vec, _matmul, _relu, _sigmoid, _softmax


class _Layer:
    def __init__(self, in_size: int, out_size: int, activation: str = "relu"):
        std = math.sqrt(2.0 / in_size)
        rng = random.Random(42)
        self.W = [[rng.gauss(0, std) for _ in range(in_size)] for _ in range(out_size)]
        self.b = [0.0] * out_size
        self.activation = activation
        # cache for backprop
        self._in: List[float] = []
        self._z: List[float] = []
        self._out: List[float] = []

    def forward(self, x: List[float]) -> List[float]:
        self._in = x
        z = _add_vec(_matmul(self.W, x), self.b)
        self._z = z
        if self.activation == "sigmoid":
            out = [_sigmoid(v) for v in z]
        elif self.activation == "softmax":
            out = _softmax(z)
        elif self.activation == "linear":
            out = list(z)
        else:  # relu
            out = [_relu(v) for v in z]
        self._out = out
        return out

    def backward(self, grad_out: List[float], lr: float) -> List[float]:
        n_out = len(grad_out)
        n_in = len(self._in)
        # activation gradient
        if self.activation == "sigmoid":
            act_grad = [self._out[i] * (1 - self._out[i]) * grad_out[i] for i in range(n_out)]
        elif self.activation == "relu":
            act_grad = [grad_out[i] if self._z[i] > 0 else 0.0 for i in range(n_out)]
        elif self.activation in ("softmax", "linear"):
            act_grad = list(grad_out)
        else:
            act_grad = list(grad_out)

        # weight/bias update
        for i in range(n_out):
            self.b[i] -= lr * act_grad[i]
            for j in range(n_in):
                self.W[i][j] -= lr * act_grad[i] * self._in[j]

        # gradient w.r.t. input
        grad_in = [0.0] * n_in
        for j in range(n_in):
            for i in range(n_out):
                grad_in[j] += self.W[i][j] * act_grad[i]
        return grad_in

    def to_dict(self) -> dict:
        return {"W": self.W, "b": self.b, "activation": self.activation}

    @classmethod
    def from_dict(cls, d: dict) -> "_Layer":
        out_size = len(d["W"])
        in_size = len(d["W"][0]) if out_size else 0
        obj = cls.__new__(cls)
        obj.W = d["W"]
        obj.b = d["b"]
        obj.activation = d.get("activation", "relu")
        obj._in = []
        obj._z = []
        obj._out = []
        return obj

class MellowModel:
    """Lightweight sandboxed neural network model."""

    def __init__(self, name: str, layers: List[_Layer], task: str = "classify"):
        self.name = name
        self.layers = layers
        self.task = task  # "classify" | "regress"
        self.trained = False
        self.loss_history: List[float] = []
        self._chat_memory: List[Dict] = []

    # ── forward ──
    def predict(self, x: List[float]) -> Any:
        out = list(x)
        for layer in self.layers:
            out = layer.forward(out)
        if self.task == "classify":
            return int(out.index(max(out)))
        return out[0] if len(out) == 1 else out

    def predict_proba(self, x: List[float]) -> List[float]:
        out = list(x)
        for layer in self.layers:
            out = layer.forward(out)
        return out

    # ── training ──
    def train_step(self, x: List[float], y: Any, lr: float = 0.01) -> float:
        # forward
        out = self.predict_proba(x)
        # loss + output grad
        if self.task == "classify":
            n_classes = len(out)
            target = int(y)
            # cross-entropy loss with softmax output
            loss = -math.log(max(out[target], 1e-9))
            grad = list(out)
            grad[target] -= 1.0
        else:
            target_val = float(y)
            diff = out[0] - target_val
            loss = 0.5 * diff * diff
            grad = [diff]
        # backward
        g = grad
        for layer in reversed(self.layers):
            g = layer.backward(g, lr)
        return loss

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "task": self.task,
            "trained": self.trained,
            "loss_history": self.loss_history[-20:],
            "layers": [la.to_dict() for la in self.layers],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MellowModel":
        layers = [_Layer.from_dict(ld) for ld in d.get("layers", [])]
        obj = cls(d["name"], layers, d.get("task", "classify"))
        obj.trained = d.get("trained", False)
        obj.loss_history = d.get("loss_history", [])
        obj._chat_memory = []
        return obj

def _parse_layer_spec(spec: Any) -> _Layer:
    """Parse a layer spec dict or tuple [in, out, activation]."""
    if isinstance(spec, dict):
        in_s = int(spec.get("in", spec.get("input", 2)))
        out_s = int(spec.get("out", spec.get("output", 2)))
        act = str(spec.get("activation", "relu"))
        return _Layer(in_s, out_s, act)
    elif isinstance(spec, (list, tuple)) and len(spec) >= 2:
        return _Layer(int(spec[0]), int(spec[1]), str(spec[2]) if len(spec) > 2 else "relu")
    return _Layer(2, 2, "relu")
