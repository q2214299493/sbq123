"""Structural, provenance, and element-balance validation checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PASS = "PASS"
WARNING = "WARNING"
FAILED = "FAILED"
NOT_AVAILABLE = "NOT_AVAILABLE"
NOT_CHECKED = "NOT_CHECKED"
SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"

_ELEMENT_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")


@dataclass(frozen=True)
class CheckResult:
    """One non-mutating validation result."""

    status: str
    message: str
    details: dict[str, object] = field(default_factory=dict)


def check_required_fields(record: dict[str, Any]) -> CheckResult:
    """Check structural fields required for a traceable reaction record."""

    missing: list[str] = []
    reaction_id = record.get("reaction_id")
    if not isinstance(reaction_id, str) or not reaction_id.strip():
        missing.append("reaction_id")

    species = record.get("species")
    if not isinstance(species, dict):
        missing.extend(["reactant", "product"])
    else:
        for key in ("reactant", "product"):
            values = species.get(key)
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(item, str) or not item.strip() for item in values)
            ):
                missing.append(key)

    calculation = record.get("calculation")
    source_path = calculation.get("source_path") if isinstance(calculation, dict) else None
    if not isinstance(source_path, str) or not source_path.strip():
        missing.append("source_path")

    energetics = record.get("energetics")
    if not isinstance(energetics, dict) or "E_final" not in energetics:
        missing.append("energy information")

    if missing:
        return CheckResult(
            FAILED,
            f"Missing or invalid required fields: {', '.join(missing)}.",
            {"fields": missing},
        )
    return CheckResult(PASS, "Required fields are present.")


def check_source(record: dict[str, Any]) -> CheckResult:
    """Check whether the recorded local source path exists."""

    calculation = record.get("calculation")
    source_path = calculation.get("source_path") if isinstance(calculation, dict) else None
    if not isinstance(source_path, str) or not source_path.strip():
        return CheckResult(NOT_AVAILABLE, "source_path is not available.")

    resolved = Path(source_path).expanduser()
    if not resolved.exists():
        return CheckResult(
            SOURCE_NOT_FOUND,
            f"Recorded source path does not exist: {source_path}",
            {"source_path": source_path},
        )
    return CheckResult(
        PASS,
        "Recorded source path exists.",
        {"source_path": str(resolved.resolve())},
    )


def _parse_composition(
    species_label: str,
    allowed_elements: set[str],
) -> dict[str, int] | None:
    """Parse a strict formula with optional trailing surface-site asterisks."""

    formula = species_label.strip().rstrip("*")
    if not formula:
        return {}

    composition: dict[str, int] = {}
    position = 0
    for match in _ELEMENT_TOKEN.finditer(formula):
        if match.start() != position:
            return None
        element, count_text = match.groups()
        if element not in allowed_elements:
            return None
        count = int(count_text) if count_text else 1
        if count <= 0:
            return None
        composition[element] = composition.get(element, 0) + count
        position = match.end()
    if position != len(formula):
        return None
    return composition


def _sum_compositions(
    labels: list[str],
    allowed_elements: set[str],
) -> dict[str, int] | None:
    """Sum strict species formulas on one reaction side."""

    total: dict[str, int] = {}
    for label in labels:
        composition = _parse_composition(label, allowed_elements)
        if composition is None:
            return None
        for element, count in composition.items():
            total[element] = total.get(element, 0) + count
    return total


def check_element_balance(
    record: dict[str, Any],
    allowed_elements: tuple[str, ...],
) -> CheckResult:
    """Compare configured-element counts across reactants and products."""

    species = record.get("species")
    if not isinstance(species, dict):
        return CheckResult(NOT_CHECKED, "Species information cannot be parsed.")
    reactant = species.get("reactant")
    product = species.get("product")
    if not isinstance(reactant, list) or not isinstance(product, list):
        return CheckResult(NOT_CHECKED, "Species lists are not available.")
    if any(not isinstance(label, str) for label in [*reactant, *product]):
        return CheckResult(NOT_CHECKED, "Species labels are not strings.")

    allowed = set(allowed_elements)
    reactant_counts = _sum_compositions(reactant, allowed)
    product_counts = _sum_compositions(product, allowed)
    if reactant_counts is None or product_counts is None:
        return CheckResult(
            NOT_CHECKED,
            "At least one species formula is outside the supported strict syntax.",
        )

    details: dict[str, object] = {
        "reactant": reactant_counts,
        "product": product_counts,
    }
    if reactant_counts != product_counts:
        return CheckResult(FAILED, "Element counts are not balanced.", details)
    return CheckResult(PASS, "Element counts are balanced.", details)
