from __future__ import annotations

import contextlib
import io
import os
import json
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from mellowlang.compiler import Compiler
from mellowlang.ledger_core import LedgerError, balance, create, entries, post, verify
from mellowlang.vm import MellowVM, RunConfig


ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native" / "standalone"
SPEC = json.loads((ROOT / "spec" / "mellow-2.9-core.json").read_text(encoding="utf-8"))


def _compiler() -> str | None:
    return shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")


@pytest.fixture(scope="module")
def native_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    compiler = _compiler()
    if not compiler:
        pytest.skip("C compiler is not available")
    build = tmp_path_factory.mktemp("mellow-full-native")
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


def test_full_native_version_has_no_python_runtime(native_binary: Path) -> None:
    result = subprocess.run(
        [str(native_binary), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "Mellow Programming Language 2.9.8 (Full Native C)"


def test_full_native_reports_runtime_platform(native_binary: Path) -> None:
    result = subprocess.run(
        [str(native_binary), "--runtime-info"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    info = json.loads(result.stdout)
    assert info["runtime"] == "mellow-c"
    assert info["backend"] == "generic-c"
    assert info["architecture"] in {"x86", "x86_64", "arm32", "arm64", "unknown"}
    assert info["pointer_bits"] in {32, 64}
    assert isinstance(info["little_endian"], bool)
    assert isinstance(info["arm_neon_available"], bool)
    assert info["optimized_kernels"] is False


def test_full_native_compiles_checks_and_runs_source(native_binary: Path) -> None:
    source = ROOT / SPEC["conformance_fixture"]
    checked = subprocess.run(
        [str(native_binary), "check", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    assert "native-c" in checked.stdout

    ran = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.splitlines() == SPEC["conformance_output"]


def test_full_native_serves_http_from_mellow_source(native_binary: Path) -> None:
    source = ROOT / "examples" / "native_server.mellow"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen(
        [str(native_binary), "server", "serve", str(source), "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/hello", timeout=0.5) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    assert resp.status == 200
                    assert payload == {"ok": True, "method": "GET", "path": "/hello"}
                    return
            except Exception:
                if proc.poll() is not None:
                    out = proc.stdout.read() if proc.stdout else ""
                    err = proc.stderr.read() if proc.stderr else ""
                    raise AssertionError(out + err)
                time.sleep(0.1)
        raise AssertionError("native server did not respond before timeout")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_full_native_runs_every_frozen_core_surface(native_binary: Path) -> None:
    source = ROOT / "tests" / "fixtures" / "native_core_surface.mellow"
    expected = (ROOT / "tests" / "fixtures" / "native_core_surface.expected").read_text(encoding="utf-8").splitlines()
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == expected


def test_full_native_runs_specialized_integer_loop_fast_path(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "integer-loop-fast-path.mellow"
    source.write_text(
        "\n".join(
            [
                "let i = 0",
                "let total = 0",
                "let n = 1000",
                "while i < n:",
                "    total = total + i",
                "    i = i + 1",
                "print(total)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "499500"


def test_full_native_repeated_function_calls_do_not_corrupt_locals(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "function-call-loop.mellow"
    source.write_text(
        "\n".join(
            [
                "def add(a, b):",
                "    return a + b",
                "",
                "let i = 0",
                "let total = 0",
                "let n = 1000",
                "",
                "while i < n:",
                "    total = add(total, i)",
                "    i = i + 1",
                "",
                "print(total)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "499500"


def test_full_native_specialized_list_index_loop(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "list-index-loop.mellow"
    source.write_text(
        "\n".join(
            [
                "let values = [1, 2, 3, 4, 5]",
                "let i = 0",
                "let total = 0",
                "let n = 1000",
                "",
                "while i < n:",
                "    total = total + values[i % 5]",
                "    i = i + 1",
                "",
                "print(total)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "3000"


def test_full_native_string_addition_does_not_use_integer_fast_path(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "string-add-fallback.mellow"
    source.write_text(
        "\n".join(
            [
                'let text = "mel"',
                'text = text + "low"',
                "print(text)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "mellow"


def test_full_native_reports_compile_error_location(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "bad-syntax.mellow"
    source.write_text("let values = [1, 2\n", encoding="utf-8")
    result = subprocess.run(
        [str(native_binary), "check", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert f"{source}:1:1: syntax error:" in result.stderr


def test_full_native_rejects_integer_literal_overflow(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "integer-overflow.mellow"
    source.write_text("let value = 44444444444444444444444444444444444444444444444444444444444444444444444444\n", encoding="utf-8")
    result = subprocess.run(
        [str(native_binary), "check", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "integer literal is outside the signed 64-bit range" in result.stderr


def test_full_native_accepts_maximum_signed_integer(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "maximum-integer.mellow"
    source.write_text("print(9223372036854775807)\n", encoding="utf-8")
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "9223372036854775807"


def test_full_native_io_builtins_read_stdin_and_write_stdout(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "io-builtins.mellow"
    source.write_text(
        "\n".join(
            [
                'let name = input("Name: ")',
                'write("Hello,")',
                'write(" ")',
                "println(name)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        input="Ada\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Name: Hello, Ada\n"


def test_full_native_readline_alias_returns_string(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "readline-alias.mellow"
    source.write_text(
        'let city = readline()\nprint(city)\nprint(type(city))\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        input="Bangkok\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["Bangkok", "str"]


def test_full_native_system_builtins_expose_cli_args_and_cwd(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "system-builtins.mellow"
    source.write_text(
        "\n".join(
            [
                "let argv = args()",
                "print(len(argv))",
                "print(argv[0])",
                "print(argv[1])",
                "print(type(cwd()))",
                "sleep_ms(0)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source), "alpha", "beta"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["2", "alpha", "beta", "str"]


def test_full_native_get_style_builtin_modules(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "get-style-modules.mellow"
    source.write_text(
        "\n".join(
            [
                "let root = get math.sqrt(81)",
                "print(root)",
                "io.println(type(sys.cwd()))",
                "let argv = get sys.args()",
                "print(len(argv))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source), "one"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["9", "str", "1"]


def test_full_native_imports_builtin_module_aliases(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "builtin-module-imports.mellow"
    source.write_text(
        "\n".join(
            [
                'import "math" as m',
                "use sys as system",
                "need io as out",
                "out.println(m.sqrt(25))",
                "out.println(type(system.cwd()))",
                "let argv = system.args()",
                "out.println(argv[0])",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source), "native-import"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["5", "str", "native-import"]


def test_full_native_accepts_installed_package_import(native_binary: Path, tmp_path: Path) -> None:
    project = tmp_path / "pkg-project"
    source = project / "src" / "main.mellow"
    package = project / "mellow_packages" / "installed" / "demo-pkg" / "current" / "package"
    source.parent.mkdir(parents=True)
    package.joinpath("src").mkdir(parents=True)
    (project / "mellow.toml").write_text(
        'name = "pkg-project"\nversion = "0.1.0"\nentry = "src/main.mellow"\n',
        encoding="utf-8",
    )
    (package / "manifest.json").write_text(
        '{"name":"demo-pkg","version":"0.1.0","entry":"src/main.mellow"}\n',
        encoding="utf-8",
    )
    (package / "src" / "main.mellow").write_text('keep ok = true\n', encoding="utf-8")
    source.write_text('use demo-pkg as demo\nprint("package-ok")\n', encoding="utf-8")
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["package-ok"]


def test_full_native_imports_mellow_package_api_without_python(native_binary: Path, tmp_path: Path) -> None:
    project = tmp_path / "pkg-api-project"
    source = project / "src" / "main.mellow"
    package = project / "mellow_packages" / "installed" / "math-kit" / "current" / "package"
    source.parent.mkdir(parents=True)
    package.joinpath("src").mkdir(parents=True)
    (project / "mellow.toml").write_text(
        'name = "pkg-api-project"\nversion = "0.1.0"\nentry = "src/main.mellow"\n',
        encoding="utf-8",
    )
    (package / "manifest.json").write_text(
        '{"name":"math-kit","version":"0.1.0","entry":"src/main.mellow"}\n',
        encoding="utf-8",
    )
    (package / "src" / "main.mellow").write_text(
        "\n".join(
            [
                "def double(x):",
                "    return x * 2",
                "",
                "def add3(x):",
                "    return x + 3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    source.write_text(
        "\n".join(
            [
                "use math-kit as kit",
                "print(kit.double(7))",
                "print(kit.add3(4))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["14", "7"]


def test_full_native_core_money_package_uses_native_money_module(native_binary: Path, tmp_path: Path) -> None:
    project = tmp_path / "finance-project"
    source = project / "src" / "main.mellow"
    package_src = ROOT / "starter_packages" / "core-money"
    package = project / "mellow_packages" / "installed" / "core-money" / "current" / "package"
    source.parent.mkdir(parents=True)
    package.parent.mkdir(parents=True)
    shutil.copytree(package_src, package)
    (project / "mellow.toml").write_text(
        'name = "finance-project"\nversion = "0.1.0"\nentry = "src/main.mellow"\n',
        encoding="utf-8",
    )
    (project / "mellow_packages" / "installed" / "core-money" / "current" / "manifest.json").write_text(
        '{"name":"core-money","version":"0.1.1","entry":"src/main.mellow"}\n',
        encoding="utf-8",
    )
    source.write_text(
        "\n".join(
            [
                "use core-money as money",
                "let subtotal = money.of(\"0.10\", \"THB\")",
                "let fee = money.of(\"0.20\", \"THB\")",
                "let total = money.add(subtotal, fee)",
                "print(money.format(total))",
                "print(money.amount(total))",
                "print(money.currency(total))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["THB 0.30", "0.30", "THB"]


def test_full_native_core_finance_package_uses_native_money_module(native_binary: Path, tmp_path: Path) -> None:
    project = tmp_path / "finance-package-project"
    source = project / "src" / "main.mellow"
    package_src = ROOT / "starter_packages" / "core-finance"
    package = project / "mellow_packages" / "installed" / "core-finance" / "current" / "package"
    source.parent.mkdir(parents=True)
    package.parent.mkdir(parents=True)
    shutil.copytree(package_src, package)
    (project / "mellow.toml").write_text(
        'name = "finance-package-project"\nversion = "0.1.0"\nentry = "src/main.mellow"\n',
        encoding="utf-8",
    )
    (project / "mellow_packages" / "installed" / "core-finance" / "current" / "manifest.json").write_text(
        '{"name":"core-finance","version":"0.1.0","entry":"src/main.mellow"}\n',
        encoding="utf-8",
    )
    source.write_text(
        "\n".join(
            [
                "use core-finance as finance",
                "let gross = finance.of(\"100.00\", \"USD\")",
                "let fee = finance.fee(gross, \"0.025\")",
                "let net = finance.net(gross, fee)",
                "print(finance.format(fee))",
                "print(finance.format(net))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["USD 2.50", "USD 97.50"]


def test_full_native_core_math_package_uses_native_math_module(native_binary: Path, tmp_path: Path) -> None:
    project = tmp_path / "math-package-project"
    source = project / "src" / "main.mellow"
    package_src = ROOT / "starter_packages" / "core-math"
    package = project / "mellow_packages" / "installed" / "core-math" / "current" / "package"
    source.parent.mkdir(parents=True)
    package.parent.mkdir(parents=True)
    shutil.copytree(package_src, package)
    (project / "mellow.toml").write_text(
        'name = "math-package-project"\nversion = "0.1.0"\nentry = "src/main.mellow"\n',
        encoding="utf-8",
    )
    (project / "mellow_packages" / "installed" / "core-math" / "current" / "manifest.json").write_text(
        '{"name":"core-math","version":"0.2.0","entry":"src/main.mellow"}\n',
        encoding="utf-8",
    )
    source.write_text(
        "\n".join(
            [
                "use core-math as mathx",
                "print(mathx.clamp(7, 0, 5))",
                "print(mathx.clamp01(2))",
                "print(mathx.lerp(10, 20, 0.5))",
                "print(mathx.distance2(0, 0, 3, 4))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["5", "1", "15", "5"]


LEDGER_SOURCE = """
use ledger as ledger
let book = ledger.create("  thb  ")
let debit = {"account": " cash ", "amount": "125.50"}
let credit = {"account": "revenue", "amount": "-125.5"}
let sold = ledger.post(book, "sale-001", [debit, credit], "cash sale", {"channel": "web", "items": 2})
let back = [{"account": "revenue", "amount": "-25.50"}, {"account": "cash", "amount": "25.50"}]
let refund = ledger_post(sold, "refund-001", back, "partial refund")
let rows = ledger.entries(refund)
let first = rows[0]
let second = rows[1]
let status = ledger_verify(refund)
print(len(ledger_entries(book)))
print(len(rows))
print(first["hash"])
print(second["previous_hash"])
print(status["head"])
print(status["ok"])
print(status["count"])
print(money_format(ledger_balance(refund, "cash")))
print(money_format(ledger_balance(refund, "petty-cash")))
let meta = first["metadata"]
print(meta["channel"])
print(meta["items"])
"""


def _reference_ledger_output() -> list[str]:
    book = create("  thb  ")
    sold = post(
        book,
        "sale-001",
        [{"account": " cash ", "amount": "125.50"}, {"account": "revenue", "amount": "-125.5"}],
        "cash sale",
        {"channel": "web", "items": 2},
    )
    refund = post(
        sold,
        "refund-001",
        [{"account": "revenue", "amount": "-25.50"}, {"account": "cash", "amount": "25.50"}],
        "partial refund",
    )
    rows = entries(refund)
    status = verify(refund)
    cash = balance(refund, "cash")
    petty = balance(refund, "petty-cash")
    return [
        str(len(entries(book))),
        str(len(rows)),
        rows[0]["hash"],
        rows[1]["previous_hash"],
        status["head"],
        "true" if status["ok"] else "false",
        str(status["count"]),
        f"{cash['currency']} {cash['amount']}",
        f"{petty['currency']} {petty['amount']}",
        "web",
        "2",
    ]


def test_full_native_ledger_matches_python_ledger_core(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "ledger.mellow"
    source.write_text(LEDGER_SOURCE.lstrip("\n"), encoding="utf-8")
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == _reference_ledger_output()


@pytest.mark.parametrize(
    ("transaction_id", "postings", "expected"),
    [
        ("", [{"account": "cash", "amount": "1.00"}, {"account": "revenue", "amount": "-1.00"}],
         "ledger: transaction id is required"),
        ("t-1", [{"account": "cash", "amount": "10.00"}],
         "ledger: postings must contain at least two rows"),
        ("t-1", [{"amount": "10.00"}, {"account": "revenue", "amount": "-10.00"}],
         "ledger: posting account is required"),
        ("t-1", [{"account": "cash", "amount": "10.00"}, {"account": "revenue", "amount": "-9.00"}],
         "ledger: transaction is not balanced: 1.00"),
        ("t-1", [{"account": "cash", "amount": "not-money"}, {"account": "revenue", "amount": "-1.00"}],
         "ledger: invalid amount: not-money"),
    ],
)
def test_full_native_ledger_rejects_invalid_transactions(
    native_binary: Path,
    tmp_path: Path,
    transaction_id: str,
    postings: list[dict[str, str]],
    expected: str,
) -> None:
    with pytest.raises(LedgerError) as reference:
        post(create("THB"), transaction_id, postings, "memo")
    assert str(reference.value) == expected

    source = tmp_path / "ledger-invalid.mellow"
    source.write_text(
        "let book = ledger_create(\"THB\")\n"
        f"let bad = ledger_post(book, {json.dumps(transaction_id)}, "
        f"{json.dumps(postings)}, \"memo\")\n"
        "print(bad)\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert f":2:1: runtime error: {expected}" in result.stderr


STORAGE_FIXTURE = ROOT / "tests" / "fixtures" / "storage_core.mellow"

ABSOLUTE_PROBE = "C:/Windows/win.ini" if os.name == "nt" else "/etc/hosts"

# (source, message fragment both engines must report).
STORAGE_ESCAPE_CASES = {
    "storage_traversal": ('let slot = storage.save("../evil", {"a": 1})\nprint(slot)\n',
                          "invalid storage path (path traversal blocked)"),
    "storage_dir_traversal": ('let root = storage_dir("../outside")\nprint(root)\n',
                              'storage_dir: ".." traversal is blocked'),
    "fs_traversal": ('let body = fs_read("../secret.txt")\nprint(body)\n',
                     'fs: ".." traversal is blocked'),
    "fs_absolute": (f'let body = fs_read("{ABSOLUTE_PROBE}")\nprint(body)\n',
                    "absolute paths are disabled by default"),
    "missing_folder": ('let slot = storage.save("nodir/hero", {"a": 1})\nprint(slot)\n',
                       "Folder not found:"),
}


def _run_python_engine(source: str, cwd: Path, engine: str = "py") -> str:
    previous = os.getcwd()
    os.chdir(cwd)
    try:
        program = Compiler().compile(source, filename="<storage-parity>")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            MellowVM().run(
                program,
                config=RunConfig(engine=engine, native_allow_fallback=False,
                                 native_require=(engine == "c")),
            )
        return buffer.getvalue()
    finally:
        os.chdir(previous)


def _tree(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def test_full_native_storage_matches_python_engine(native_binary: Path, tmp_path: Path) -> None:
    source = STORAGE_FIXTURE.read_text(encoding="utf-8")
    native_dir = tmp_path / "native"
    python_dir = tmp_path / "python"
    native_dir.mkdir()
    python_dir.mkdir()

    result = subprocess.run(
        [str(native_binary), str(STORAGE_FIXTURE)],
        cwd=native_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "storage ok\n"
    assert _run_python_engine(source, python_dir) == result.stdout

    saved = Path("mellow_fixture_saves") / "profiles" / "hero.json"
    assert (native_dir / saved).read_bytes() == (python_dir / saved).read_bytes()
    assert _tree(native_dir) == _tree(python_dir)


@pytest.mark.parametrize(
    ("case", "source", "fragment"),
    [(name, source, fragment) for name, (source, fragment) in sorted(STORAGE_ESCAPE_CASES.items())],
)
def test_full_native_storage_rejects_the_same_paths_as_the_python_engine(
    native_binary: Path,
    tmp_path: Path,
    case: str,
    source: str,
    fragment: str,
) -> None:
    script = tmp_path / f"{case}.mellow"
    script.write_text(source, encoding="utf-8")
    native_dir = tmp_path / f"{case}-native"
    python_dir = tmp_path / f"{case}-python"
    native_dir.mkdir()
    python_dir.mkdir()

    result = subprocess.run(
        [str(native_binary), str(script)],
        cwd=native_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, result.stdout
    assert fragment in result.stderr

    with pytest.raises(Exception) as reference:
        _run_python_engine(source, python_dir)
    assert fragment in str(reference.value)
    assert _tree(native_dir) == _tree(python_dir)


def test_full_native_sm_cli_pack_inspect_unpack(native_binary: Path, tmp_path: Path) -> None:
    src = tmp_path / "asset.mellow"
    packed = tmp_path / "asset.sm"
    restored = tmp_path / "asset.restored.mellow"
    src.write_text("keep name = \"mellow\"\nkeep name = \"mellow\"\n", encoding="utf-8")

    pack = subprocess.run(
        [str(native_binary), "sm", "pack", str(src), "-o", str(packed), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert pack.returncode == 0, pack.stderr
    pack_info = json.loads(pack.stdout)
    assert pack_info["codec"] == "sm3-token-native-crc32"
    assert packed.exists()

    inspect = subprocess.run(
        [str(native_binary), "sm", "inspect", str(packed), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert inspect.returncode == 0, inspect.stderr
    inspect_info = json.loads(inspect.stdout)
    assert inspect_info["version"] == 3
    assert inspect_info["checksum_ok"] is True

    unpack = subprocess.run(
        [str(native_binary), "sm", "unpack", str(packed), "-o", str(restored), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert unpack.returncode == 0, unpack.stderr
    unpack_info = json.loads(unpack.stdout)
    assert unpack_info["codec"] == "sm3-token-native-crc32"
    assert restored.read_bytes() == src.read_bytes()


def test_full_native_reports_missing_package_import(native_binary: Path, tmp_path: Path) -> None:
    project = tmp_path / "missing-pkg-project"
    source = project / "src" / "main.mellow"
    source.parent.mkdir(parents=True)
    (project / "mellow.toml").write_text(
        'name = "missing-pkg-project"\nversion = "0.1.0"\nentry = "src/main.mellow"\n',
        encoding="utf-8",
    )
    source.write_text('use missing-pkg as missing\nprint("never")\n', encoding="utf-8")
    result = subprocess.run(
        [str(native_binary), "check", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "package import not installed" in result.stderr


def test_full_native_gc_stats_foundation(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "gc-foundation.mellow"
    source.write_text(
        "\n".join(
            [
                "print(gc_collect())",
                "let stats = gc_stats()",
                'print(stats["collections"])',
                'print(stats["mode"])',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["0", "1", "mark-sweep-native-handles"]


def test_full_native_gc_sweeps_unreachable_native_channels(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "gc-sweep.mellow"
    source.write_text(
        "\n".join(
            [
                "let ch = channel()",
                'send(ch, "queued")',
                "ch = none",
                "gc_collect()",
                "let stats = gc_stats()",
                'print(stats["native_allocated"])',
                'print(stats["native_freed"])',
                'print(stats["native_live"])',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["1", "1", "0"]


def test_full_native_gc_sweeps_unreachable_str_list_map_heap(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "gc-value-heap.mellow"
    source.write_text(
        "\n".join(
            [
                'let text = "hello"',
                'let values = [text, "world"]',
                'let data = {"values": values}',
                "text = none",
                "values = none",
                "data = none",
                "gc_collect()",
                "let stats = gc_stats()",
                'print(stats["heap_last_gc_freed"] > 0)',
                'print(stats["heap_live"])',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["true", "0"]


def test_full_native_green_thread_foundation_and_yield(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "thread-foundation.mellow"
    source.write_text(
        "\n".join(
            [
                "def worker():",
                "    return 1",
                "let id = spawn(worker)",
                "yield()",
                "let stats = gc_stats()",
                "print(id)",
                'print(stats["spawned"])',
                'print(stats["yielded"])',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["1", "1", "1"]


def test_full_native_mn_scheduler_workers_are_configurable(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "mn-scheduler-workers.mellow"
    source.write_text(
        "\n".join(
            [
                "use thread as t",
                "print(t.scheduler_mode())",
                "print(t.worker_count())",
                "print(t.workers(4))",
                "def worker():",
                "    yield()",
                "    return 7",
                "spawn(worker)",
                "yield()",
                "let stats = gc_stats()",
                'print(stats["scheduler_mode"])',
                'print(stats["workers"])',
                'print(stats["tasks"])',
                'print(stats["switches"] > 0)',
                'print(stats["worker_changes"])',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "m:n-cooperative",
        "1",
        "4",
        "m:n-cooperative",
        "4",
        "2",
        "true",
        "1",
    ]


def test_full_native_channels_send_recv_and_module_alias(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "channel-foundation.mellow"
    source.write_text(
        "\n".join(
            [
                "use chan as c",
                "let ch = c.channel()",
                'print(c.send(ch, "hello"))',
                "print(c.recv(ch))",
                "print(c.recv(ch))",
                "let stats = gc_stats()",
                'print(stats["channels"])',
                'print(stats["yielded"])',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["true", "hello", "none", "1", "1"]


def test_full_native_green_threads_switch_between_tasks(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "green-thread-switching.mellow"
    source.write_text(
        "\n".join(
            [
                "def task_a():",
                '    print("A1")',
                "    yield()",
                '    print("A2")',
                "def task_b():",
                '    print("B1")',
                "    yield()",
                '    print("B2")',
                "spawn(task_a)",
                "spawn(task_b)",
                "yield()",
                'print("M1")',
                "yield()",
                'print("M2")',
                "yield()",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["A1", "B1", "M1", "A2", "B2", "M2"]


def test_full_native_recv_empty_channel_implicitly_yields(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "channel-implicit-yield.mellow"
    source.write_text(
        "\n".join(
            [
                "let ch = channel()",
                "def receiver():",
                '    print("R wait")',
                "    print(recv(ch))",
                '    print("R done")',
                "def sender():",
                "    yield()",
                '    send(ch, "msg")',
                '    print("S sent")',
                "spawn(receiver)",
                "spawn(sender)",
                "yield()",
                "yield()",
                "yield()",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["R wait", "S sent", "msg", "R done"]


def test_full_native_gc_reports_heap_bytes_blocks_and_nested_ownership(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "gc-nested-ownership.mellow"
    source.write_text(
        "\n".join(
            [
                'let inner = ["alpha", "beta"]',
                'let outer = {"inner": inner, "label": "root"}',
                'let holder = [outer, {"copy": inner}]',
                "inner = none",
                "outer = none",
                "holder = none",
                "gc_collect()",
                "let stats = gc_stats()",
                'print(stats["heap_blocks"])',
                'print(stats["heap_bytes"])',
                'print(stats["last_freed_blocks"] > 0)',
                'print(stats["last_freed_bytes"] > 0)',
                'print(stats["heap_live"])',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["0", "0", "true", "true", "0"]


def test_full_native_gc_stress_collects_repeated_nested_values(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "gc-stress.mellow"
    source.write_text(
        "\n".join(
            [
                "var i = 0",
                "var item = none",
                "while i < 200:",
                '    item = {"name": "item", "values": [i, str(i), {"again": str(i)}]}',
                "    i = i + 1",
                "item = none",
                "gc_collect()",
                "let stats = gc_stats()",
                'print(stats["last_freed_blocks"] > 100)',
                'print(stats["last_freed_bytes"] > 100)',
                'print(stats["heap_live"])',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["true", "true", "0"]


def test_full_native_canvas_package_surface_writes_ppm(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "canvas-circle.mellow"
    image = (tmp_path / "circle.ppm").as_posix()
    source.write_text(
        "\n".join(
            [
                "use canvas as c",
                "img = c.create(48, 48)",
                'c.clear(img, "white")',
                'c.circle(img, 24, 24, 14, "#33ccff")',
                'c.rect(img, 4, 4, 8, 8, "yellow")',
                f'print(c.save(img, "{image}"))',
                "let stats = gc_stats()",
                'print(stats["canvases"])',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["true", "1"]
    data = (tmp_path / "circle.ppm").read_bytes()
    assert data.startswith(b"P6\n48 48\n255\n")
    assert len(data) == len(b"P6\n48 48\n255\n") + 48 * 48 * 3


def test_full_native_syntax_parity_for_elif_show_stop_and_inline_comments(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "syntax-parity.mellow"
    source.write_text(
        "\n".join(
            [
                "let score = 7 // inline comment",
                "if score < 3:",
                '    print("low")',
                "elif score < 10:",
                '    show "mid" # old output spelling',
                "else:",
                '    print("high")',
                "stop",
                'print("after")',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["mid"]


def test_full_native_syntax_parity_for_var_null_range_wait_break_continue(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "syntax-parity-more.mellow"
    source.write_text(
        "\n".join(
            [
                "var total = 0",
                "let empty = null",
                "for i in range(5):",
                "    if i == 1:",
                "        continue",
                "    if i == 4:",
                "        break",
                "    total = total + i",
                "wait 0",
                "print(total)",
                "print(empty)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["5", "none"]


def test_full_native_exit_builtin_sets_process_status(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "exit-status.mellow"
    source.write_text('write("before")\nexit(7)\nprintln("after")\n', encoding="utf-8")
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 7
    assert result.stdout == "before"


def test_full_native_reports_runtime_error_location(native_binary: Path, tmp_path: Path) -> None:
    source = tmp_path / "bad-runtime.mellow"
    source.write_text("let values = [1]\nprint(values[4])\n", encoding="utf-8")
    result = subprocess.run(
        [str(native_binary), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert f"{source}:2:1: runtime error: index out of range" in result.stderr
