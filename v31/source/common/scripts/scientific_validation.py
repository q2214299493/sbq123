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


def finite_array(value: Any, label: str, *, shape: tuple[int | None, ...]) -> list:
    """Validate rectangular numeric arrays without NumPy coercion or field loss."""
    if not shape or not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{label} must be a non-empty array")
    if shape[0] is not None and len(value) != shape[0]:
        raise ValueError(f"{label} dimension mismatch")
    if len(shape) == 1:
        return [finite_number(item, f"{label}[{index}]") for index, item in enumerate(value)]
    rows = [finite_array(item, f"{label}[{index}]", shape=shape[1:]) for index, item in enumerate(value)]
    def dimensions(row):
        result = []
        while isinstance(row, list):
            result.append(len(row))
            row = row[0]
        return result
    if any(dimensions(row) != dimensions(rows[0]) for row in rows):
        raise ValueError(f"{label} must be rectangular")
    return rows
