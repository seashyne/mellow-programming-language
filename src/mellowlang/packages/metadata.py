from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

HOST_DEP_SENTINELS = {"host", "builtin", "built-in", "internal"}

def _normalize_authors(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
        return out
    return [str(value).strip()] if str(value).strip() else []


def package_authors(manifest_or_item: Dict[str, Any] | None) -> List[str]:
    data = manifest_or_item or {}
    authors = _normalize_authors(data.get("authors"))
    for key in ("author", "creator", "publisher", "maintainer", "owner"):
        if not authors:
            authors = _normalize_authors(data.get(key))
    metadata = data.get("metadata")
    if not authors and isinstance(metadata, dict):
        authors = package_authors(metadata)
    manifest = data.get("manifest")
    if not authors and isinstance(manifest, dict):
        authors = package_authors(manifest)
    return authors


def package_creator(manifest_or_item: Dict[str, Any] | None) -> str:
    authors = package_authors(manifest_or_item)
    return ", ".join(authors) if authors else "unknown"


def split_namespace(name: str) -> tuple[str | None, str]:
    norm = normalize_name(name)
    if norm.startswith('@') and '/' in norm:
        ns, rest = norm[1:].split('/', 1)
        return ns or None, rest
    return None, norm


def canonical_package_name(name: str) -> str:
    return normalize_name(name)


def bare_package_name(name: str) -> str:
    return split_namespace(name)[1]


def normalize_name(name: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() or ch in "-_/@." else "-" for ch in (name or "pkg"))
    return safe.strip("-") or "pkg"


def _split_pkg_ref(name: str) -> Tuple[str, str | None]:
    if "@" in name[1:]:
        base, ver = name.rsplit("@", 1)
        if re.match(r"^[0-9A-Za-z][0-9A-Za-z.+\-]{0,63}$", ver or ""):
            return normalize_name(base), ver
    return normalize_name(name), None


def _version_key(version: str) -> Tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", version or "0")[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def _version_satisfies(version: str, spec: str | None) -> bool:
    spec = (spec or "").strip()
    if not spec or spec in {"*", "latest"}:
        return True
    if spec in HOST_DEP_SENTINELS:
        return True
    parts = [p.strip() for p in re.split(r"[, ]+", spec) if p.strip()]
    vkey = _version_key(version)

    def _one(part: str) -> bool:
        if part in {"*", "latest"}:
            return True
        if part.startswith("^"):
            base = part[1:].strip()
            major = _version_key(base)[0]
            return vkey[0] == major and vkey >= _version_key(base)
        if part.startswith("~"):
            base = part[1:].strip()
            bkey = _version_key(base)
            return vkey[:2] == bkey[:2] and vkey >= bkey
        for op in (">=", "<=", ">", "<"):
            if part.startswith(op):
                rhs = _version_key(part[len(op):].strip())
                return {">=": vkey >= rhs, "<=": vkey <= rhs, ">": vkey > rhs, "<": vkey < rhs}[op]
        return version == part

    return all(_one(part) for part in parts)


def _choose_version(versions: List[str], spec: str | None) -> str | None:
    if not versions:
        return None
    ordered = sorted(versions, key=_version_key)
    candidates = [v for v in ordered if _version_satisfies(v, spec)]
    if candidates:
        return candidates[-1]
    if spec and spec not in {"*", "latest"}:
        return None
    return ordered[-1]


def _normalized_versions(value: Any, latest: Any = None) -> List[str]:
    if isinstance(value, dict):
        versions = [str(v) for v in value.keys()]
    elif isinstance(value, (list, tuple, set)):
        versions = [str(v) for v in value]
    elif isinstance(value, str) and value.strip():
        versions = [value.strip()]
    else:
        versions = []
    latest_text = str(latest).strip() if latest is not None else ""
    if latest_text and latest_text not in versions:
        versions.append(latest_text)
    return sorted(versions, key=_version_key)
