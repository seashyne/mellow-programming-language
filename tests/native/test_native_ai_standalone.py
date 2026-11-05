"""Standalone C parity for the random and std.ai surface.

The standalone runtime is the product engine: every ai.* and random syscall has
to behave like the Python reference. Each case compiles one source twice, once
with the C binary and once through MellowVM's Python engine, and compares the
printed output line by line.
"""

from __future__ import annotations

import contextlib
import io
import os
import random
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from mellowlang.compiler import Compiler
from mellowlang.vm import MellowVM, RunConfig


ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native" / "standalone"

_PY_CALL = re.compile(r"(?<![\w.])ai\.([a-z_0-9]+)\(")


def _compiler() -> str | None:
    return shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")


@pytest.fixture(scope="module")
def native_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    compiler = _compiler()
    if not compiler:
        pytest.skip("C compiler is not available")
    build = tmp_path_factory.mktemp("mellow-ai-native")
    binary = build / ("mellow.exe" if os.name == "nt" else "mellow")
    command = [
        compiler,
        "-std=c99",
        "-I",
        str(NATIVE / "include"),
        "-I",
        str(ROOT / "native" / "sm" / "include"),
        str(NATIVE / "src" / "mellowrt_core.c"),
        str(NATIVE / "src" / "mellowrt_debug.c"),
        str(NATIVE / "src" / "mellowrt_ledger.c"),
        str(NATIVE / "src" / "mellowrt_money.c"),
        str(NATIVE / "src" / "mellowrt_platform.c"),
        str(NATIVE / "src" / "mellowrt_packages.c"),
        str(NATIVE / "src" / "mellowrt_scheduler.c"),
        str(NATIVE / "src" / "mellowrt_server.c"),
        str(NATIVE / "src" / "mellowrt_sm_cli.c"),
        str(NATIVE / "src" / "mellowrt_storage.c"),
        str(NATIVE / "src" / "mellowrt_syscalls.c"),
        str(NATIVE / "src" / "mellowc.c"),
        str(NATIVE / "src" / "mellowc_lexer.c"),
        str(NATIVE / "src" / "mellowc_modules.c"),
        str(NATIVE / "src" / "mellowc_parser.c"),
        str(ROOT / "native" / "sm" / "src" / "sm_native.c"),
        str(NATIVE / "src" / "mellowrt_main.c"),
        "-o",
        str(binary),
        "-lm",
    ]
    if os.name == "nt":
        command.append("-lws2_32")
    built = subprocess.run(command, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    return binary


@pytest.fixture(autouse=True)
def _clean_ai_state() -> None:
    from mellowlang.ai import state as ai_state

    ai_state._MODELS.clear()
    ai_state._LLM_MODELS.clear()
    ai_state._SESSIONS.clear()
    ai_state._RUNTIME_STATE.update({"booted": False, "boot_count": 0, "last_boot_at": None})
    ai_state._API_CONFIG.clear()
    ai_state._API_CONFIG.update(
        {
            "offline": {"mode": "offline", "max_context": 16, "status": "ready"},
            "local-rag": {"mode": "offline", "max_context": 8, "status": "ready"},
        }
    )


def _run_native(binary: Path, source: str, cwd: Path, seed: int = 42) -> str:
    script = cwd / "case.mellow"
    script.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    result = subprocess.run(
        [str(binary), "run", str(script), "--seed", str(seed)],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout


def _run_python(source: str, cwd: Path, *, seed: int = 42) -> str:
    program = Compiler().compile(textwrap.dedent(source).lstrip("\n"), filename="<native-ai>")
    vm = MellowVM()
    output = io.StringIO()
    previous = os.getcwd()
    os.chdir(cwd)
    random.seed(seed)
    try:
        with contextlib.redirect_stdout(output):
            vm.run(program, config=RunConfig(engine="py", seed=seed))
    finally:
        os.chdir(previous)
    return output.getvalue()


def _python_source(source: str) -> str:
    """Mellow's Python engine reaches host calls through `get ai.name(...)`."""
    return _PY_CALL.sub(r"get ai.\1(", textwrap.dedent(source).lstrip("\n"))


def _same_line(native_line: str, python_line: str) -> bool:
    try:
        left = float(native_line)
        right = float(python_line)
    except ValueError:
        return native_line == python_line
    return left == pytest.approx(right, rel=1e-5, abs=1e-9)


def _assert_same(native_output: str, python_output: str) -> None:
    native_lines = native_output.strip().splitlines()
    python_lines = python_output.strip().splitlines()
    assert len(native_lines) == len(python_lines), (native_lines, python_lines)
    for native_line, python_line in zip(native_lines, python_lines):
        assert _same_line(native_line, python_line), (native_line, python_line)


def _parity(binary: Path, source: str, cwd: Path, *, seed: int = 42) -> None:
    _assert_same(_run_native(binary, source, cwd, seed), _run_python(_python_source(source), cwd, seed=seed))


def test_native_random_follows_cpython_mt19937(native_binary: Path, tmp_path: Path) -> None:
    source = """
        print(random())
        print(random())
        print(random(10))
        print(random(10, 20))
        print(random(-5, 5))
        print(random(0))
    """
    output = _run_native(native_binary, source, tmp_path)
    reference = random.Random(42)
    expected = [
        reference.random(),
        reference.random(),
        reference.randint(0, 10),
        reference.randint(10, 20),
        reference.randint(-5, 5),
        0,
    ]
    lines = output.strip().splitlines()
    assert len(lines) == len(expected)
    for line, value in zip(lines, expected):
        assert float(line) == pytest.approx(value, rel=1e-5, abs=1e-9)


def test_native_random_matches_python_engine(native_binary: Path, tmp_path: Path) -> None:
    source = """
        print(random())
        print(random(10))
        print(random(10, 20))
        print(random(-5, 5))
    """
    python_source = source.replace("random(", "get random.range(")
    _assert_same(_run_native(native_binary, source, tmp_path), _run_python(python_source, tmp_path))


def test_native_seed_flag_is_accepted_before_and_after_command(native_binary: Path, tmp_path: Path) -> None:
    script = tmp_path / "seed.mellow"
    script.write_text("print(random(1000))\n", encoding="utf-8")
    trailing = subprocess.run(
        [str(native_binary), "run", str(script), "--seed", "7"],
        capture_output=True, text=True, cwd=tmp_path, check=False,
    )
    leading = subprocess.run(
        [str(native_binary), "--seed=7", "run", str(script)],
        capture_output=True, text=True, cwd=tmp_path, check=False,
    )
    assert trailing.returncode == leading.returncode == 0
    assert trailing.stdout == leading.stdout


def test_native_model_train_and_predict_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        let created = ai.model_create("xor", [{"in": 2, "out": 4, "activation": "relu"}, {"in": 4, "out": 2}], "classify")
        print(created["status"])
        let trained = ai.train("xor", [[0, 0], [0, 1], [1, 0], [1, 1]], [0, 1, 1, 0], 5, 0.1)
        print(trained["final_loss"])
        let predicted = ai.predict("xor", [1, 0])
        let probabilities = predicted["probabilities"]
        print(probabilities[0])
        print(predicted["prediction"])
        let losses = ai.loss_history("xor")
        print(len(losses))
        let info = ai.model_info("xor")
        print(info["task"])
        print(len(ai.models_list()))
    """
    _parity(native_binary, source, tmp_path)


def test_native_embeddings_and_retrieval_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        let vector = ai.embed("hello world")
        print(len(vector))
        print(vector[0])
        print(vector[5])
        print(vector[63])
        let ranked = ai.vector_search("hello", ["hello world", "bye"], 2)
        print(ranked[0]["score"])
        print(ranked[1]["score"])
        print(ranked[1]["index"])
        let answer = ai.rag_answer("hello", ["hello world"], 1)
        print(answer["answer"])
        print(ai.prompt_template("Hi {{name}}", {"name": "Mellow"}))
    """
    _parity(native_binary, source, tmp_path)


def test_native_sessions_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        let opened = ai.session_open("demo", "sys")
        print(opened["session"])
        print(opened["system"])
        let reply = ai.session_message(opened["session"], "train")
        print(reply["response"])
        print(reply["messages"])
        let history = ai.session_history(opened["session"])
        print(len(history))
    """
    _parity(native_binary, source, tmp_path)


def test_native_runtime_and_providers_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        let before = ai.runtime_info()
        print(before["boot_count"])
        let boot = ai.runtime_boot({"mode": "test"})
        print(boot["status"])
        let after = ai.runtime_info()
        print(after["boot_count"])
        print(len(ai.api_providers()))
        let configured = ai.api_configure("local-rag", {"max_context": 4})
        print(configured["status"])
        let completion = ai.api_complete("offline", "Summarize this text")
        print(completion["response"])
        let embedded = ai.api_embed("offline", "hi")
        print(len(embedded["embedding"]))
        let chat = ai.chat("train", "chatty")
        print(chat["response"])
        print(chat["memory_size"])
        print(ai.decide(["only"]))
    """
    _parity(native_binary, source, tmp_path)


def test_native_llm_dataset_eval_and_generate_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        let dataset = ai.llm_dataset(["abcdefgh", "ijklmnop"], {"chunk_chars": 4})
        print(dataset["count"])
        print(dataset["chars"])
        let samples = dataset["samples"]
        print(len(samples))
        print(samples[0])
        let created = ai.llm_create("tiny", {"order": 3})
        print(created["kind"])
        let trained = ai.llm_train("tiny", ["abcdefgh", "abcabcabc"])
        print(trained["loss"])
        print(trained["perplexity"])
        print(trained["vocab"])
        print(trained["tokens"])
        let evaluated = ai.llm_eval("tiny", ["abc"])
        print(evaluated["loss"])
        print(evaluated["perplexity"])
        let generated = ai.llm_generate("tiny", "abc", {"max_tokens": 8, "seed": 7})
        print(generated["text"])
        print(generated["generated_tokens"])
        let info = ai.llm_info("tiny")
        print(info["order"])
        print(info["vocab"])
        print(len(ai.llm_models()))
        print(len(ai.llm_backends()))
        let plan = ai.llm_device_plan({"backend": "mellow-native"})
        print(plan["status"])
        print(plan["strategy"])
    """
    _parity(native_binary, source, tmp_path)


def test_native_llm_complete_and_chat_shapes_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        let created = ai.llm_create("shape", {"order": 2})
        let trained = ai.llm_train("shape", ["abcd", "abab"])
        let completed = ai.llm_complete("shape", "ab", {"max_tokens": 4})
        let choices = completed["choices"]
        let first = choices[0]
        print(first["finish_reason"])
        print(first["text"])
        let usage = completed["usage"]
        print(usage["prompt_tokens"])
        print(usage["completion_tokens"])
        let chatted = ai.llm_chat("shape", [{"role": "user", "content": "ab"}], {"max_tokens": 4})
        let message = chatted["message"]
        print(message["role"])
        print(message["content"])
        let tokenized = ai.llm_tokenize("ab")
        print(tokenized["count"])
    """
    _parity(native_binary, source, tmp_path)


def test_native_tensor_kernels_match_python(native_binary: Path, tmp_path: Path) -> None:
    source = """
        let product = ai.llm_tensor("matmul", [1, 2, 3, 4], [5, 6, 7, 8], 2, 2, 2)
        let values = product["values"]
        print(product["backend"])
        print(values[0])
        print(values[3])
        let norm = ai.llm_tensor("layer_norm", [1, 2, 3], [1, 1, 1], [0, 0, 0], 0.00001)
        let normalized = norm["values"]
        print(normalized[0])
        print(normalized[1])
        print(normalized[2])
        let batch = ai.llm_tensor_batch([{"op": "softmax", "values": [1, 2]}, {"op": "gelu", "values": [0, 1]}, {"op": "nope", "values": [1]}])
        print(batch["operations"])
        print(batch["errors"])
        print(batch["backend"])
        let results = batch["results"]
        print(len(results))
    """
    _parity(native_binary, source, tmp_path)
    # Python's extension and its pure fallback word this error differently, so
    # only the standalone wording is pinned here.
    rejected = _run_native(
        native_binary,
        'let batch = ai.llm_tensor_batch([{"op": "nope", "values": [1]}])\n'
        'let results = batch["results"]\n'
        'let first = results[0]\n'
        'print(first["error"])\n',
        tmp_path,
    ).strip()
    assert rejected == "unknown tensor op: nope"


def test_native_checkpoint_loads_in_python(native_binary: Path, tmp_path: Path) -> None:
    saved = _run_native(
        native_binary,
        """
        let created = ai.llm_create("cross", {"order": 3})
        let trained = ai.llm_train("cross", ["abcdefgh", "abcabcabc"])
        let slot = ai.llm_save("cross", "cross")
        print(slot["saved"])
        let again = ai.llm_save("cross", "cross")
        print(again["saved"])
        """,
        tmp_path,
    )
    assert saved.splitlines()[0] == saved.splitlines()[1]
    loaded = _run_python(
        """
        let model = get ai.llm_load("cross")
        print(model["loaded"])
        print(model["tokens"])
        let generated = get ai.llm_generate("cross", "abc", {"max_tokens": 5})
        print(generated["text"])
        """,
        tmp_path,
    )
    assert loaded.splitlines() == ["cross", "17", "abcabcab"]


def test_python_checkpoint_loads_in_native(native_binary: Path, tmp_path: Path) -> None:
    _run_python(
        """
        let created = get ai.model_create("handoff", [{"in": 2, "out": 4, "activation": "relu"}, {"in": 4, "out": 2}], "classify")
        let trained = get ai.train("handoff", [[0, 0], [0, 1], [1, 0], [1, 1]], [0, 1, 1, 0], 5, 0.1)
        let saved = get ai.model_save("handoff", "handoff")
        print(saved["saved"])
        """,
        tmp_path,
    )
    output = _run_native(
        native_binary,
        """
        let loaded = ai.model_load("handoff")
        print(loaded["loaded"])
        print(loaded["layers"])
        let predicted = ai.predict("handoff", [1, 0])
        let probabilities = predicted["probabilities"]
        print(probabilities[0])
        """,
        tmp_path,
    )
    lines = output.strip().splitlines()
    assert lines[0] == "handoff"
    assert lines[1] == "2"
    assert float(lines[2]) == pytest.approx(0.0706, abs=1e-4)
