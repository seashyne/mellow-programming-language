from pathlib import Path
import sys

sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "src")))

from mellowlang.compiler import Compiler
from mellowlang.host.legacy import default_host
from mellowlang.vm.vm import MellowVM, RunConfig


def test_core_llm_host_train_and_generate():
    host = default_host()
    created = host.call("std.ai.llm_create", ["tiny-test", {"order": 3, "seed": 7}])
    dataset = host.call(
        "std.ai.llm_dataset",
        [["hello mellow", "mellow learns language"], {"chunk_chars": 64}],
    )
    trained = host.call(
        "std.ai.llm_train",
        ["tiny-test", dataset, {"epochs": 2}],
    )
    generated = host.call(
        "std.ai.llm_generate",
        ["tiny-test", "mel", {"max_tokens": 12, "seed": 7, "top_k": 4}],
    )
    complete = host.call(
        "std.ai.llm_complete",
        ["tiny-test", "mel", {"max_tokens": 8, "seed": 7}],
    )
    chat = host.call(
        "std.ai.llm_chat",
        ["tiny-test", [{"role": "user", "content": "hello"}], {"max_tokens": 8, "seed": 7}],
    )
    score = host.call("std.ai.llm_eval", ["tiny-test", dataset])
    info = host.call("std.ai.llm_info", ["tiny-test"])
    models = host.call("std.ai.llm_models", [])
    backends = host.call("std.ai.llm_backends", [])
    mellow_plan = host.call("std.ai.llm_device_plan", [{"backend": "mellow-native", "cpu_workers": 2}])

    assert created["status"] == "created"
    assert dataset["count"] == 2
    assert trained["status"] == "trained"
    assert trained["tokens"] > 0
    assert trained["perplexity"] > 0
    assert generated["text"].startswith("mel")
    assert len(generated["text"]) > len("mel")
    assert complete["choices"][0]["text"]
    assert chat["message"]["role"] == "assistant"
    assert score["perplexity"] > 0
    assert info["trained"] is True
    assert any(row["name"] == "tiny-test" for row in models)
    assert any(row["name"] == "mellow-native" for row in backends)
    assert mellow_plan["backend"] == "mellow-native"
    assert mellow_plan["status"] == "kernels-ready"


def test_mellow_native_tensor_kernels():
    host = default_host()

    matmul = host.call("std.ai.llm_tensor", ["matmul", [1, 2, 3, 4], [5, 6, 7, 8], 2, 2, 2])
    softmax = host.call("std.ai.llm_tensor", ["softmax", [1, 2, 3]])
    gelu = host.call("std.ai.llm_tensor", ["gelu", [-1, 0, 1]])
    norm = host.call("std.ai.llm_tensor", ["layer_norm", [1, 2, 3], [1, 1, 1], [0, 0, 0], 1e-5])

    assert matmul["values"] == [19.0, 22.0, 43.0, 50.0]
    assert round(sum(softmax["values"]), 6) == 1.0
    assert gelu["values"][1] == 0.0
    assert abs(sum(norm["values"])) < 1e-6


def test_mellow_native_tensor_batch():
    host = default_host()
    result = host.call(
        "std.ai.llm_tensor_batch",
        [[
            {"op": "matmul", "a": [1, 2, 3, 4], "b": [5, 6, 7, 8], "m": 2, "n": 2, "k": 2},
            {"op": "softmax", "values": [1, 2, 3]},
            {"op": "gelu", "values": [-1, 0, 1]},
        ]],
    )

    assert result["operations"] == 3
    assert result["errors"] == 0
    assert result["results"][0]["values"] == [19.0, 22.0, 43.0, 50.0]


def test_core_llm_from_mellow_script(capsys):
    source = """
call ai.llm_create("script-llm", {"order": 2, "seed": 3})
let data = call ai.llm_dataset(["aba mellow", "aba model"], {"chunk_chars": 32})
let train = call ai.llm_train("script-llm", data, {"epochs": 1})
let score = call ai.llm_eval("script-llm", data)
let out = call ai.llm_complete("script-llm", "ab", {"max_tokens": 8, "seed": 3})
show train["status"]
show score["perplexity"]
show out["text"]
"""
    program = Compiler().compile(source, filename="<core-llm-test>")
    MellowVM().run(program, config=RunConfig(engine="py"))
    output = capsys.readouterr().out

    assert "trained" in output
    assert "ab" in output
