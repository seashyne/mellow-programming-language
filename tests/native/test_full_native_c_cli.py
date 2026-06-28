from __future__ import annotations

import os
import json
import shutil
import subprocess
from pathlib import Path

import pytest


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
        str(NATIVE / "src" / "mellowrt_core.c"),
        str(NATIVE / "src" / "mellowrt_debug.c"),
        str(NATIVE / "src" / "mellowrt_platform.c"),
        str(NATIVE / "src" / "mellowrt_packages.c"),
        str(NATIVE / "src" / "mellowrt_scheduler.c"),
        str(NATIVE / "src" / "mellowrt_syscalls.c"),
        str(NATIVE / "src" / "mellowc.c"),
        str(NATIVE / "src" / "mellowc_lexer.c"),
        str(NATIVE / "src" / "mellowc_modules.c"),
        str(NATIVE / "src" / "mellowc_parser.c"),
        str(NATIVE / "src" / "mellowrt_main.c"),
        "-o",
        str(binary),
        "-lm",
    ]
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
    assert result.stdout.strip() == "Mellow Programming Language 2.9.7 (Full Native C)"


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
