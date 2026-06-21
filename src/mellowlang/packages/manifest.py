from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .metadata import package_authors, package_creator

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

def _manifest_paths(package_dir: Path) -> List[Path]:
    return [package_dir / "mellow.toml", package_dir / "mellow.pkg.json"]


def _parse_toml(path: Path) -> Dict[str, Any]:
    if tomllib is None:
        raise RuntimeError("tomllib not available; use mellow.pkg.json or Python 3.11+")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {
        "name": data.get("name", path.parent.name),
        "version": data.get("version", "0.1.0"),
        "entry": data.get("entry", "src/main.mellow"),
        "description": data.get("description", "Mellow package"),
        "authors": data.get("authors", []),
        "license": data.get("license", "MIT"),
        "keywords": data.get("keywords", ["mellow"]),
        "badges": data.get("badges", []),
        "official": bool(data.get("official", False)),
        "deprecated": bool(data.get("deprecated", False)),
        "dependencies": data.get("dependencies", {}) or {},
        "visibility": data.get("visibility", "public"),
        "namespace": data.get("namespace", ""),
    }


def _write_toml(path: Path, manifest: Dict[str, Any]) -> None:
    deps = manifest.get("dependencies", {}) or {}
    lines = [
        f'name = "{manifest.get("name", path.parent.name)}"',
        f'version = "{manifest.get("version", "0.1.0")}"',
        f'description = "{manifest.get("description", "Mellow package")}"',
        f'entry = "{manifest.get("entry", "src/main.mellow")}"',
        f'license = "{manifest.get("license", "MIT")}"',
        f'visibility = "{manifest.get("visibility", "public")}"',
    ]
    namespace = (manifest.get("namespace") or "").strip()
    if namespace:
        lines.append(f'namespace = "{namespace}"')
    authors = manifest.get("authors", []) or []
    if authors:
        lines.append("authors = [" + ", ".join(json.dumps(a, ensure_ascii=False) for a in authors) + "]")
    keywords = manifest.get("keywords", []) or []
    if keywords:
        lines.append("keywords = [" + ", ".join(json.dumps(k, ensure_ascii=False) for k in keywords) + "]")
    badges = manifest.get("badges", []) or []
    if badges:
        lines.append("badges = [" + ", ".join(json.dumps(b, ensure_ascii=False) for b in badges) + "]")
    if manifest.get("official"):
        lines.append("official = true")
    if manifest.get("deprecated"):
        lines.append("deprecated = true")
    lines.append("")
    lines.append("[dependencies]")
    if deps:
        for k, v in deps.items():
            lines.append(f'{k} = "{v}"')
    else:
        lines.append("# add package = \"^1.0.0\"")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_manifest(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if p.is_dir():
        for cand in _manifest_paths(p):
            if cand.exists():
                p = cand
                break
        else:
            raise FileNotFoundError(f"no package manifest found in {p}; expected one of: mellow.toml, mellow.pkg.json")
    if not p.exists():
        raise FileNotFoundError(f"manifest not found: {p}")
    if p.is_dir():
        raise IsADirectoryError(f"expected a manifest file, got directory: {p}")
    data = _parse_toml(p) if p.suffix == ".toml" else json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("name", p.parent.name)
    data.setdefault("version", "0.1.0")
    data.setdefault("entry", "src/main.mellow")
    data.setdefault("description", "Mellow package")
    data.setdefault("authors", [])
    data.setdefault("dependencies", {})
    data.setdefault("visibility", "public")
    data.setdefault("namespace", "")
    data["authors"] = package_authors(data)
    data["creator"] = package_creator(data)
    return data
