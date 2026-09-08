from __future__ import annotations

import json
from pathlib import Path


CANDIDATES = (
    "inputs/retrieval_top5.json",
    "references/retrieval_top5.json",
    "retrieval_top5.json",
)


def find_retrieval_file(root: Path) -> Path | None:
    for relative in CANDIDATES:
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def read_retrieval_source(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("retrieval JSON must contain an object")
    results = payload.get("results", [])
    if not isinstance(results, list) or len(results) > 5:
        raise ValueError("retrieval results must be a list containing at most five items")
    if not payload.get("whitelist_valid"):
        raise ValueError("retrieval source did not pass the whitelist gate")
    return payload
