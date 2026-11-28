"""Units for reported kinetic quantities. Astropy owns dimensional algebra and scale factors."""
from __future__ import annotations

import re
from functools import lru_cache

from sbq123.common.kinetic_model.kinetic_parameters.laws import fraction, pressure_unit
from sbq123.common.workflow.optional_dependencies import require_optional
from sbq123.common.validation.scientific_validation import finite_number, integer_number


@lru_cache(maxsize=1)
def _units():
    return require_optional("astropy.units", "dimensional kinetic rate validation")


@lru_cache(maxsize=1)
def _aliases():
    u = _units()
    # Private count units keep event extents, molecular counts and vacancy counts distinct.
    return {
        "event": u.def_unit("event"), "molecule": u.def_unit("molecule"), "vacancy": u.def_unit("vacancy"),
        "atm": require_optional("astropy.units.cds", "standard atmosphere conversion").atm,
        "dimensionless_activity": u.one, "fractional_coverage": u.one, "1": u.one,
    }


@lru_cache(maxsize=256)
def unit(text):
    """Read products of units and an optional denominator product, e.g. m^6 mol^-2 min^-1."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Expected a nonempty unit")
    parts = text.strip().split("/")
    if len(parts) > 2:
        raise ValueError(f"Use a single denominator product in {text!r}")
    result = _units().one
    for index, part in enumerate(parts):
        part = part.strip()
        if part.startswith("(") and part.endswith(")"):
            part = part[1:-1].strip()
        if not part or part.startswith("*") or part.endswith("*") or "**" in part:
            raise ValueError(f"Invalid unit expression {text!r}")
        for token in re.split(r"\s*\*\s*|\s+", part):
            match = re.fullmatch(r"([A-Za-z_]+|1)(?:\^(-?\d+))?", token)
            if match and match[1] in _aliases():
                factor = _aliases()[match[1]] ** int(match[2] or 1)
            else:
                if not re.fullmatch(r"[A-Za-z]+(?:\^?-?\d+|[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)?", token):
                    raise ValueError(f"Invalid unit token {token!r}")
                factor = _units().Unit(token)
            result = result / factor if index else result * factor
    return result


def convert_unit(value, source_unit, target_unit):
    """Explicit scalar or compound unit conversion; no physical basis or activity equivalencies."""
    number = finite_number(value, "quantity")
    if {source_unit, target_unit} == {"fractional_coverage", "dimensionless_activity"}:
        raise ValueError("Converting site coverage into thermodynamic activity requires an activity model")
    if "fractional_coverage" in (source_unit, target_unit):
        fraction(number, "fractional coverage")
    if "dimensionless_activity" in (source_unit, target_unit):
        finite_number(number, "activity", nonnegative=True)
    result = unit(source_unit).to(unit(target_unit), number, equivalencies=None)
    if number and result == 0:
        raise ValueError("Unit conversion underflow")
    return finite_number(result, "converted quantity")


def convert_coefficient(value, source_unit, target_unit, activity_orders):
    """Validate both units against the declared powers, without changing the activity convention."""
    conventions = {"pressure", "concentration", "dimensionless_activity", "fractional_coverage"}
    if not isinstance(activity_orders, dict) or activity_orders.keys() - conventions:
        raise ValueError("Unknown activity convention")
    orders = {key: integer_number(n, f"{key} order", nonnegative=True) for key, n in activity_orders.items()}
    expected = unit(pressure_unit(orders.get("pressure", 0), "Pa"))
    expected *= unit("m³/mol") ** orders.get("concentration", 0)
    if not all(unit(label).is_equivalent(expected, equivalencies=None) for label in (source_unit, target_unit)):
        raise ValueError("Coefficient unit disagrees with declared pressure/concentration orders and inverse time")
    return convert_unit(finite_number(value, "coefficient", nonnegative=True), source_unit, target_unit)


def extent_scale(source, target):
    """Target extents per source extent for one fixed quantity kind."""
    if source == target:
        return 1.0
    if "event" not in (source, target):
        return convert_unit(1, source, target)
    avogadro = require_optional("astropy.constants", "count to amount conversion").N_A.value
    if source == "event":
        return convert_unit(1 / avogadro, "mol", target)
    return convert_unit(1, source, "mol") * avogadro
