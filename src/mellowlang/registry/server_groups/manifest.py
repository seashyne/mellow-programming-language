"""Read a JSON file that may not exist, and the manifest fields every
package record carries: authors, creator, keywords and badges."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _json_load(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _authors_from_manifest(manifest: Dict[str, Any] | None) -> list[str]:
    data = manifest or {}
    value = data.get("authors") or data.get("author") or data.get("creator") or data.get("publisher") or data.get("maintainer") or data.get("owner")
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _creator_from_manifest(manifest: Dict[str, Any] | None) -> str:
    authors = _authors_from_manifest(manifest)
    return ", ".join(authors) if authors else "unknown"


def _list_from_manifest(manifest: Dict[str, Any] | None, key: str) -> list[str]:
    value = (manifest or {}).get(key)
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _package_badges(manifest: Dict[str, Any] | None, *, signed: bool = False) -> list[str]:
    data = manifest or {}
    badges = _list_from_manifest(data, "badges")
    if data.get("official") and "official" not in badges:
        badges.append("official")
    if signed and "verified" not in badges:
        badges.append("verified")
    if data.get("deprecated") and "deprecated" not in badges:
        badges.append("deprecated")
    return badges
