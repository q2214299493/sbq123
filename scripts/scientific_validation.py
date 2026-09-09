"""Shared finite scalar/range validation for scientific inputs (no thresholds)."""
from __future__ import annotations

import math
from numbers import Real
from typing import Any


def finite_number(value: Any, label: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    if positive and number <= 0 or nonnegative and number < 0:
        raise ValueError(f"{label} is outside its physical range")
    return number


def integer_number(value: Any, label: str, *, positive: bool = False, nonnegative: bool = False) -> int:
    number = finite_number(value, label, positive=positive, nonnegative=nonnegative)
    if not number.is_integer():
        raise ValueError(f"{label} must be an integer")
    return int(number)


def validate_finite_tree(value: Any, label: str = "scientific input") -> None:
    """Reject nonfinite numerical metadata without coercing text or optional nulls."""
    if isinstance(value, dict):
        for key, item in value.items():
            validate_finite_tree(item, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            validate_finite_tree(item, f"{label}[{index}]")
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return
        finite_number(number, label)
    elif isinstance(value, Real) and not isinstance(value, bool):
        finite_number(value, label)
