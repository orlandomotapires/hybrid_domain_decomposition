"""How a batch configuration names and expands its cases (no pipeline imports: the Studio uses it)."""

from __future__ import annotations

from typing import Any


def case_key(matrix: Any, algorithm: Any, size: Any) -> str:
    """``<matrix>__<algorithm preset>__<coarsening preset>``: the case's folder and manifest key."""
    return f"{matrix}__{algorithm}__{size}"


def unique_matrix_keys(configuration: dict[str, Any]) -> list[str]:
    """Matrix keys of ``"matrices": [{"key": ...}]`` in order, each once (a repeated matrix runs once)."""
    keys: list[str] = []
    for entry in configuration.get("matrices", []):
        key = str(entry.get("key")) if isinstance(entry, dict) else str(entry)
        if key not in keys:
            keys.append(key)
    return keys
