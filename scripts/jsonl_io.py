from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


JsonlObjectError = Callable[[Path, int], str]


def read_jsonl_objects(path: Path, object_error: JsonlObjectError | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            message = object_error(path, line_number) if object_error else f"{path}:{line_number}: expected JSON object"
            raise ValueError(message)
        records.append(payload)
    return records
