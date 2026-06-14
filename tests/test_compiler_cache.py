from mellowlang.compiler import Compiler


def test_compiler_reuses_identical_source():
    Compiler.clear_cache()
    compiler = Compiler()
    source = "let value = 1 + 2\nprint(value)\n"

    first = compiler.compile(source, filename="<cache-test>")
    second = compiler.compile(source, filename="<cache-test>")
    info = Compiler.cache_info()

    assert second is first
    assert info["hits"] == 1
    assert info["misses"] == 1
    assert info["size"] == 1


def test_compiler_cache_key_includes_options():
    Compiler.clear_cache()
    compiler = Compiler()
    source = "print(1)\n"

    optimized = compiler.compile(source, filename="<cache-options>", optimize=True)
    unoptimized = compiler.compile(source, filename="<cache-options>", optimize=False)

    assert optimized is not unoptimized
    assert Compiler.cache_info()["size"] == 2
