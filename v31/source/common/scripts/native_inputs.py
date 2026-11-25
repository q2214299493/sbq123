"""Input validation shared by native model adapters."""
import math
import re

from scripts.scientific_validation import finite_number, validate_finite_tree


def token(s):
    if not isinstance(s, str) or not re.fullmatch("[A-Za-z][A-Za-z0-9_]*", s):
        raise ValueError(f"Invalid native identifier {s!r}")
    return s


def integer(n, label, minimum=1):
    if type(n) is not int or n < minimum:
        raise ValueError(f"Invalid {label}")
    return n


def conditions(dataset, config, pressure):
    if config["dataset_version"] != dataset["dataset_version"]:
        raise ValueError("Configuration belongs to a different kinetic dataset")
    validate_finite_tree(config)
    gas = {s["species_id"] for s in dataset["species"] if s["phase"] == "gas"}
    pressures = config["partial_pressure_bar"]
    if set(pressures) != gas or any(finite_number(p, "partial pressure") < 0 for p in pressures.values()):
        raise ValueError("Incomplete or invalid gas pressures")
    if gas and not math.isclose(sum(pressures.values()), pressure, abs_tol=1e-12):
        raise ValueError("Gas partial pressures differ from total pressure")
    return pressures
