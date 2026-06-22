from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

from .config import remember_alias
from .metadata import HOST_DEP_SENTINELS, _split_pkg_ref, normalize_name, package_authors, package_creator
from .manifest import _write_toml, read_manifest

PKG_ROOT = Path("mellow_packages")
REGISTRY_ROOT = PKG_ROOT / "registry"
INSTALLED_ROOT = PKG_ROOT / "installed"

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]

def _update_lock_entry(*args, **kwargs):
    from ..package_manager import _update_lock_entry as impl
    return impl(*args, **kwargs)

def resolve_project_runtime(*args, **kwargs):
    from ..package_manager import resolve_project_runtime as impl
    return impl(*args, **kwargs)

def _project_package_root(project_dir: str | Path | None = None) -> Path:
    if project_dir is None:
        return PKG_ROOT
    return Path(project_dir) / "mellow_packages"


def _project_registry_root(project_dir: str | Path | None = None) -> Path:
    if project_dir is None:
        return REGISTRY_ROOT
    return _project_package_root(project_dir) / "registry"


def _project_installed_root(project_dir: str | Path | None = None) -> Path:
    if project_dir is None:
        return INSTALLED_ROOT
    return _project_package_root(project_dir) / "installed"


def _repo_registry_root() -> Path:
    return _repo_root() / "mellow_packages" / "registry"


def _repo_starter_packages_root() -> Path:
    return _repo_root() / "starter_packages"


def _entry_candidates(entry: str) -> list[str]:
    entry = str(entry or "src/main.mel").replace("\\", "/")
    out = [entry]
    if entry.endswith(".mellow"):
        out.append(entry[:-7] + ".mel")
    elif entry.endswith(".mel"):
        out.append(entry[:-4] + ".mellow")
    return list(dict.fromkeys(out))


def _resolve_existing_entry(package_dir: Path, manifest: Dict[str, Any]) -> str:
    entry = str(manifest.get("entry", "src/main.mel"))
    for candidate in _entry_candidates(entry):
        if (package_dir / candidate).exists():
            return candidate
    return entry


def _load_manifest_from_source_dir(src: Path) -> Dict[str, Any]:
    manifest = read_manifest(src)
    manifest = dict(manifest)
    manifest["entry"] = _resolve_existing_entry(src, manifest)
    return manifest


def _find_local_package_source(name: str, version: str | None = None, project_dir: str | Path | None = None) -> tuple[Path | None, str | None, str | None]:
    base_name, version_from_ref = _split_pkg_ref(name)
    chosen_version = version or version_from_ref
    roots = []
    if project_dir is not None:
        roots.append(_project_registry_root(project_dir))
    roots.extend([REGISTRY_ROOT, _repo_registry_root()])
    for root in roots:
        pkg_root = root / base_name
        if not pkg_root.exists():
            continue
        versions = sorted([p.name for p in pkg_root.iterdir() if p.is_dir()])
        if not versions:
            continue
        ver = chosen_version or versions[-1]
        src = pkg_root / ver
        if src.exists():
            return src, ver, "registry"
    starter = _repo_starter_packages_root() / base_name
    if starter.exists():
        return starter, chosen_version or str(read_manifest(starter).get("version", "0.1.0")), "starter"
    return None, None, None


def install_local_package_into_project(name: str, project_dir: str | Path, version: str | None = None, *, with_deps: bool = True, _visited: set[str] | None = None) -> Dict[str, Any]:
    base = Path(project_dir)
    base_name, version_from_ref = _split_pkg_ref(name)
    chosen_version = version or version_from_ref
    src, resolved_version, source_kind = _find_local_package_source(base_name, chosen_version, project_dir=base)
    if src is None:
        return {"ok": False, "error": f"local package not found: {base_name}"}
    manifest = _load_manifest_from_source_dir(src)
    resolved_version = resolved_version or str(manifest.get("version", "0.1.0"))
    installed_root = _project_installed_root(base)
    dst = installed_root / base_name / "current"
    if dst.parent.exists():
        shutil.rmtree(dst.parent)
    (dst / "package").mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst / "package", dirs_exist_ok=True)
    (dst / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    alias_path = remember_alias(base_name, project_dir=base)
    lockfile_path = _update_lock_entry(base_name, resolved_version, manifest, registry="local", project_dir=base)
    installed = [{"name": base_name, "version": resolved_version}]
    visited = _visited or set()
    visit_key = f"{base_name}@{resolved_version}"
    if visit_key in visited:
        return {"ok": True, "name": base_name, "version": resolved_version, "installed_to": str(dst.parent), "entry": str(manifest.get("entry", "")), "authors": package_authors(manifest), "creator": package_creator(manifest), "installed": installed, "lockfile": str(lockfile_path), "aliases_file": str(alias_path), "source_kind": source_kind}
    visited.add(visit_key)
    if with_deps:
        for dep_name, dep_spec in (manifest.get("dependencies", {}) or {}).items():
            if str(dep_spec).strip().lower() in HOST_DEP_SENTINELS:
                continue
            dep_res = install_local_package_into_project(dep_name, base, version=str(dep_spec), with_deps=True, _visited=visited)
            if not dep_res.get("ok"):
                return dep_res
            installed.extend(dep_res.get("installed", [{"name": dep_name, "version": dep_res.get("version")}]))
    return {"ok": True, "name": base_name, "version": resolved_version, "installed_to": str(dst.parent), "entry": str(manifest.get("entry", "")), "authors": package_authors(manifest), "creator": package_creator(manifest), "installed": installed, "lockfile": str(lockfile_path), "aliases_file": str(alias_path), "source_kind": source_kind}


def _preset_dependencies(preset: str = "starter") -> Dict[str, str]:
    preset = (preset or "starter").strip().lower()
    presets: Dict[str, Dict[str, str]] = {
        "starter": {
            "core-print": "^0.2.0",
            "core-strings": "^0.2.0",
            "core-collections": "^0.2.0",
            "core-math": "^0.2.0",
            "core-json": "^0.2.0",
            "core-time": "^0.2.0",
        },
        "app": {
            "core-print": "^0.2.0",
            "core-strings": "^0.2.0",
            "core-storage": "^0.2.0",
            "core-window": "^0.2.0",
        },
        "automation": {
            "core-print": "^0.2.0",
            "core-json": "^0.2.0",
            "core-time": "^0.2.0",
            "core-workflow": "^0.2.0",
        },
        "ai-agent": {
            "core-print": "^0.2.0",
            "core-strings": "^0.2.0",
            "core-json": "^0.2.0",
            "core-ai": "^0.2.0",
        },
        "gamekit": {
            "core-print": "^0.2.0",
            "core-math": "^0.2.0",
            "core-gamekit": "^0.2.0",
        },
        "api-webhook": {
            "core-print": "^0.2.0",
            "core-json": "^0.2.0",
            "core-http": "^0.2.0",
            "core-workflow": "^0.2.0",
        },
        "finance": {
            "core-print": "^0.2.0",
            "core-json": "^0.2.0",
            "core-money": "^0.1.0",
            "core-ledger": "^0.1.0",
        },
        "data": {
            "core-print": "^0.2.0",
            "core-json": "^0.2.0",
            "core-data": "^0.1.0",
        },
    }
    return dict(presets.get(preset, presets["starter"]))


def _default_starter_dependencies() -> Dict[str, str]:
    return _preset_dependencies("starter")


def _preset_entry_source(preset: str = "starter") -> str:
    preset = (preset or "starter").strip().lower()
    samples: Dict[str, str] = {
        "starter": """import "pkg:core-print" as out
import "pkg:core-strings" as text
import "pkg:core-math" as mathx
import "pkg:core-workflow" as wf

out.banner(text.upper("mellow starter"))
keep task = wf.job("demo.run", {"score": mathx.clamp01(2)})
out.kv("task", wf.to_json(task))
out.success("starter packages ready")
""",
        "app": """import "pkg:core-print" as out
import "pkg:core-window" as win

keep count = 0
keep name = "Mellow"

keep app = win.window("Mellow Desktop App", 960, 640)
win.menu(app, "File", ["About"])
win.menu_item(app, "File", "Quit", "close")
win.label(app, "Hello Mellow")
win.input(app, "Mellow")
win.button(app, "Count +1", "inc:count")
win.label(app, "Count = {{state.count}}")
win.button(app, "Close", "close")
win.run(app)
out.success("desktop app spec ready")
""",
        "automation": """import "pkg:core-print" as out
import "pkg:core-json" as jsonx
import "pkg:core-time" as time
import "pkg:core-workflow" as wf

keep payload = {"kind": "nightly.sync", "at": time.unix()}
keep job = wf.job("sync.users", payload)
out.kv("job", wf.to_json(job))
out.kv("payload", jsonx.pretty(payload))
""",
        "ai-agent": """import "pkg:core-print" as out
import "pkg:core-ai" as ai

keep plan = ai.prompt("Summarize user onboarding steps for a small SaaS")
out.banner("AI Agent Preset")
out.kv("prompt", plan)
""",
        "gamekit": """import "pkg:core-print" as out
import "pkg:core-gamekit" as game
import "pkg:core-math" as mathx

keep hero = game.entity("hero", {"x": 10, "y": 5, "speed": mathx.clamp01(1)})
out.kv("hero", game.to_json(hero))
out.success("gamekit preset ready")
""",
        "api-webhook": """import "pkg:core-print" as out
import "pkg:core-http" as http
import "pkg:core-json" as jsonx

keep route = http.route("POST", "/webhooks/orders")
keep sample = {"route": route, "body": {"ok": true}}
out.kv("webhook", jsonx.pretty(sample))
""",
        "finance": """import "pkg:core-print" as out
import "pkg:core-money" as money
import "pkg:core-ledger" as ledger

keep book = ledger.create("USD")
keep amount = money.of("125.50", "USD")
ledger.post(book, "cash", "revenue", amount, "sale-001")
out.kv("balance", money.format(ledger.balance(book, "cash")))
""",
        "data": """import "pkg:core-print" as out
import "pkg:core-data" as data

keep rows = [{"kind": "sale", "amount": 10}, {"kind": "sale", "amount": 15}]
keep sales = data.where(rows, "kind", "eq", "sale")
out.kv("total", data.sum(sales, "amount"))
""",
    }
    return samples.get(preset, samples["starter"])


def ensure_project_starter_packages(project_dir: str | Path, packages: List[str] | None = None, *, resolve_runtime_map: bool = True) -> Dict[str, Any]:
    base = Path(project_dir)
    selected = [normalize_name(p) for p in (packages or list(_default_starter_dependencies().keys()))]
    installed_rows: List[Dict[str, Any]] = []
    for pkg in selected:
        res = install_local_package_into_project(pkg, base, with_deps=True)
        if not res.get("ok"):
            return res
        installed_rows.extend(res.get("installed", [{"name": pkg, "version": res.get("version")}]))
    runtime = None
    if resolve_runtime_map:
        runtime = resolve_project_runtime(base, install_missing=False, strict=False)
    return {"ok": True, "project_dir": str(base), "packages": selected, "installed": installed_rows, "runtime": runtime}


def scaffold_project(target_dir: str | Path, *, force: bool = False, with_core: bool = True, preset: str = "starter") -> Dict[str, Any]:
    dest = Path(target_dir).resolve()
    template = _repo_root() / "project_template"
    if not template.exists():
        return {"ok": False, "error": "project_template not found"}
    if dest.exists() and any(dest.iterdir()) and not force:
        return {"ok": False, "error": "destination not empty. Use --force."}
    if dest.exists() and force:
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, dest, dirs_exist_ok=True)

    preset_name = (preset or "starter").strip().lower()
    deps = _preset_dependencies(preset_name) if with_core else {}

    src_dir = dest / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    entry_name = "src/main.mel"
    (src_dir / "main.mel").write_text(_preset_entry_source(preset_name), encoding="utf-8")

    if preset_name == "app":
        desktop_dir = dest / "desktop"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        (desktop_dir / "window.json").write_text(json.dumps({
            "title": f"{dest.name} App",
            "width": 960,
            "height": 640,
            "source": entry_name,
            "engine": "tkinter-host",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif preset_name == "api-webhook":
        api_dir = dest / "api"
        api_dir.mkdir(parents=True, exist_ok=True)
        (api_dir / "routes.json").write_text(json.dumps({
            "routes": [{"method": "POST", "path": "/webhooks/orders", "source": entry_name}],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    mj = dest / "mellow.json"
    if mj.exists():
        try:
            data = json.loads(mj.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        data["entry"] = entry_name
        data["name"] = normalize_name(dest.name)
        data["preset"] = preset_name
        data["starter_packages"] = list(deps.keys()) if with_core else []
        mj.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "name": normalize_name(dest.name),
        "version": "0.1.0",
        "description": f"Mellow {preset_name} project scaffold",
        "entry": entry_name,
        "license": "MIT",
        "visibility": "private",
        "namespace": "",
        "preset": preset_name,
        "dependencies": deps,
    }
    _write_toml(dest / "mellow.toml", manifest)

    readme_text = (
        f"# {dest.name}\n\n"
        f"Scaffolded with `mellow new --preset {preset_name}`.\n\n"
        "## Run\n\n"
        "```bash\n"
        "mellow run src/main.mel\n"
        "```\n\n"
    )
    if preset_name == "app":
        readme_text += (
            "## Desktop window\n\n"
            "```bash\n"
            "mellow desktop run src/main.mel\n"
            "```\n\n"
        )
    readme_text += "## Starter packages\n\n"
    if with_core and deps:
        readme_text += ''.join(f"- {name}\n" for name in deps.keys())
    else:
        readme_text += "No starter packages preloaded.\n"
    (dest / "README.md").write_text(readme_text, encoding="utf-8")

    result = {
        "ok": True,
        "project_dir": str(dest),
        "manifest": str(dest / "mellow.toml"),
        "entry": entry_name,
        "preset": preset_name,
        "with_core": with_core,
    }
    if with_core and deps:
        preload = ensure_project_starter_packages(dest, packages=list(deps.keys()), resolve_runtime_map=True)
        if not preload.get("ok"):
            return preload
        result["preload"] = preload
    return result
