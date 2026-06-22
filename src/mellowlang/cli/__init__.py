"""CLI package."""

import shutil
import sys
from importlib import import_module

__all__ = ["main", "_cmd_check", "_print_pretty_error", "_doctor_report"]


def __getattr__(name):
    if name == "_print_pretty_error":
        _common_module = import_module(".common", __name__)
        return getattr(_common_module, name)
    if name == "_cmd_check":
        _main_module = import_module(".main", __name__)
        return getattr(_main_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 1 and args[0] in {"--version", "-V", "version"}:
        from mellowlang import __version__
        print(f"mellow {__version__}")
        return 0
    from .main import main as _main
    return _main(argv)


_ENTRYPOINT = main


def _call_main_attr(name, *args, **kwargs):
    _main_module = import_module(".main", __name__)
    globals()["main"] = _ENTRYPOINT
    for patched in (
        "_distribution_version",
        "_read_project_version",
        "_find_all_mellow_on_path",
        "_find_project_root",
    ):
        if patched in _ENTRYPOINT.__dict__ and _ENTRYPOINT.__dict__[patched] is not _DEFAULT_MAIN_ATTRS.get(patched):
            setattr(_main_module, patched, _ENTRYPOINT.__dict__[patched])
    return getattr(_main_module, name)(*args, **kwargs)


def _doctor_report(*args, **kwargs):
    return _call_main_attr("_doctor_report", *args, **kwargs)


_ENTRYPOINT._doctor_report = _doctor_report
_ENTRYPOINT._distribution_version = lambda: _call_main_attr("_distribution_version")
_ENTRYPOINT._read_project_version = lambda project_root: _call_main_attr("_read_project_version", project_root)
_ENTRYPOINT._find_all_mellow_on_path = lambda: _call_main_attr("_find_all_mellow_on_path")
_ENTRYPOINT._find_project_root = lambda start: _call_main_attr("_find_project_root", start)
_DEFAULT_MAIN_ATTRS = {
    "_distribution_version": _ENTRYPOINT._distribution_version,
    "_read_project_version": _ENTRYPOINT._read_project_version,
    "_find_all_mellow_on_path": _ENTRYPOINT._find_all_mellow_on_path,
    "_find_project_root": _ENTRYPOINT._find_project_root,
}
_ENTRYPOINT.shutil = shutil
main = _ENTRYPOINT
