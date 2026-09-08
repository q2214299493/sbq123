from __future__ import annotations

import math

from pathlib import Path

from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_POLICY = ROOT / "configs" / "dimer_gate.yaml"

def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))

def _sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )

def _at_most(value: Any, maximum: Any) -> bool:
    return bool(_finite(value) and _finite(maximum) and float(value) <= float(maximum))

def _force_reduced(row: dict[str, Any] | None, fraction_max: float) -> bool:
    if not row:
        return False
    history = [
        float(value)
        for value in row.get("atomic_force_history_last10_eVA", [])
        if _finite(value)
    ]
    return bool(len(history) >= 2 and history[-1] <= history[0] * fraction_max)

def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("document_kind") != "dimer_gate_policy":
        raise ValueError(f"invalid DIMER gate policy: {path}")
    return payload
