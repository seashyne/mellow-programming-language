from mellowlang.standalone_runtime import standalone_runtime_status


def test_standalone_runtime_status_shape():
    info = standalone_runtime_status()
    assert info["exists"] is True
    assert info["python_dependency_free_goal"] is True
    assert any(path.endswith("include/mellowrt.h") for path in info["source_files"])
