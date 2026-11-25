"""Reference documentation (the Studio wiki): categories, topics and lookup by parameter."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent / "data" / "wiki.json"


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def categories() -> list[dict[str, Any]]:
    return _data()["categories"]


def topics(category: str | None = None) -> list[dict[str, Any]]:
    return [t for t in _data()["topics"] if category is None or t["category"] == category]


def topic(topic_id: str) -> dict[str, Any] | None:
    return next((t for t in _data()["topics"] if t["id"] == topic_id), None)


def topic_for_parameter(key: str, value: Any = None) -> dict[str, Any] | None:
    """Topic documenting a parameter, given its dotted key and, optionally, its current value.

    Choices are documented one topic per value (``strategy = "sorted"``); the value picks it.
    """
    leaf = key.split(".")[-1]
    if leaf == "simulated":  # documented with the method: 'partitioning_strategy = "...", simulated = false'
        strategy = key.split(".")[-2]
        wanted = f'simulated = {str(True if value is None else bool(value)).lower()}'
        return next((t for t in _data()["topics"] if f'"{strategy}"' in (t.get("codeKey") or "") and wanted in t["codeKey"]), None)
    candidates = []
    for item in _data()["topics"]:
        code = (item.get("codeKey") or "").split(" ")[0]
        if code == key or code.endswith("." + leaf) or code == leaf:
            candidates.append((len(code), item))
    if not candidates:
        return None
    if value is not None:
        exact = [c for c in candidates if f'"{value}"' in (c[1].get("codeKey") or "")]
        if exact:
            return max(exact, key=lambda c: c[0])[1]
    return max(candidates, key=lambda c: c[0])[1]


def search(text: str) -> list[dict[str, Any]]:
    needle = text.strip().lower()
    if not needle:
        return topics()

    def haystack(t: dict[str, Any]) -> str:
        parts = [t.get("title", ""), t.get("shortSummary", ""), t.get("codeKey", "") or ""]
        for field in ("scientificBackground", "implementationDetails", "tuningGuidelines"):
            parts.extend(t.get(field) or [])
        return " ".join(parts).lower()

    return [t for t in topics() if needle in haystack(t)]
