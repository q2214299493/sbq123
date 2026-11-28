"""Physical denominator checks for the dimension-aware V2 rate contract."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction

from sbq123.common.artifacts.artifact_io import sha256_json
from sbq123.common.kinetic_model.kinetic_parameters.rate_units import convert_unit, extent_scale, unit
from sbq123.common.validation.scientific_validation import finite_number


COUNT_UNITS = {
    "reference_site": {"site", "reference site"},
    "reference_site_pair": {"site pair", "reference site pair"},
    "lattice_site": {"lattice site"},
    "simulation_cell": {"cell", "simulation cell"},
}
PHYSICAL_UNITS = {"surface_area": "m²", "catalyst_mass": "kg", "reactor_volume": "m³"}
NUMERATOR = {"forward_flux": "event", "reverse_flux": "event", "net_progress": "event",
             "species_source": "molecule", "site_source": "vacancy"}
# A stored factor counts units of the first physical basis per unit of the second.
BRIDGES = {
    ("surface_area", "reactor_volume"): ("catalyst_m2_per_reactor_m3", "m²/m³"),
    ("surface_area", "catalyst_mass"): ("catalyst_m2_per_kg", "m²/kg"),
    ("catalyst_mass", "reactor_volume"): ("catalyst_kg_per_reactor_m3", "kg/m³"),
    ("reference_site", "reference_site_pair"): ("sites_per_reference", "1"),
    ("lattice_site", "simulation_cell"): ("lattice_sites_per_cell", "1"),
    ("lattice_site", "reference_site"): ("lattice_sites_per_reference", "1"),
    ("lattice_site", "reference_site_pair"): ("lattice_sites_per_reference", "1"),
    ("reference_site", "simulation_cell"): ("references_per_cell", "1"),
    ("reference_site_pair", "simulation_cell"): ("references_per_cell", "1"),
}
for reference in ("reference_site", "reference_site_pair", "lattice_site"):
    for physical, quantity, units in (
        ("surface_area", "reference_mol_per_catalyst_m2", "mol/m²"),
        ("catalyst_mass", "reference_mol_per_kg", "mol/kg"),
        ("reactor_volume", "reference_mol_per_reactor_m3", "mol/m³"),
    ):
        BRIDGES[reference, physical] = (quantity, units)


def basis_identity(basis):
    """Hash the physical reference independently of time unit, extent and denominator magnitude."""
    record = {k: basis[k] for k in ("basis_kind", "reference_scope", "reference_id", "definition")}
    record["inventory_ids"] = sorted(basis.get("inventory_ids", ()))
    if basis["basis_kind"] in ("other", "unresolved"):
        record["denominator_unit"] = basis["denominator_unit"]
    if "basis_evidence" in basis:
        record["basis_evidence"] = basis["basis_evidence"]
    return sha256_json(record)


def denominator_scale(basis):
    """Scale of one written denominator unit in the canonical basis unit (schema checked upstream)."""
    convert_unit(1, basis["time_unit"], "s")
    kind, label = basis["basis_kind"], basis["denominator_unit"]
    name = label.strip().lower().replace("_", " ").removesuffix("s")
    if kind in PHYSICAL_UNITS:
        return convert_unit(1, label, PHYSICAL_UNITS[kind])
    if kind in COUNT_UNITS and name not in COUNT_UNITS[kind]:
        raise ValueError(f"{label!r} does not denote {kind}")
    if kind == "other":
        if any(name in aliases for aliases in COUNT_UNITS.values()):
            raise ValueError("A standard count basis cannot be relabelled as custom")
        try:
            unit(label)
        except ValueError:
            pass  # A custom count unit is identified by its definition and hash-bound evidence.
        else:
            raise ValueError("A recognized unit cannot be relabelled as a custom denominator")
    return 1.0


def _bridge(source, target, evidence):
    identities = basis_identity(source), basis_identity(target)
    kinds = source["basis_kind"], target["basis_kind"]
    if identities[0] == identities[1]:
        if evidence is not None:
            raise ValueError("A physical bridge was supplied for an identical basis")
        return 1.0, []
    if "unresolved" in kinds:
        return None, ["resolved physical basis identity and inventory mapping"]
    reverse = kinds not in BRIDGES
    edge = kinds[::-1] if reverse else kinds
    if edge not in BRIDGES:
        return None, [f"supported physical mapping from {kinds[0]} to {kinds[1]} for the named references"]
    quantity, expected_unit = BRIDGES[edge]
    if evidence is None:
        return None, [quantity]
    expected_ids = identities[::-1] if reverse else identities
    if (evidence["quantity"] != quantity
            or (evidence["numerator_basis_sha256"], evidence["denominator_basis_sha256"]) != expected_ids):
        raise ValueError(f"{quantity} evidence must bind both exact physical bases in canonical orientation")
    ratio = convert_unit(evidence["value"], evidence["unit"], expected_unit)
    if expected_unit.startswith("mol/"):
        ratio *= extent_scale("mol", "event")
    ratio = Fraction(finite_number(ratio, quantity, positive=True))
    return (1 / ratio if reverse else ratio), []


def convert_checked_rate(value, kind, source, target, evidence):
    """Convert a schema-checked request. Return both bases and the exact supplied evidence."""
    if kind not in NUMERATOR:
        raise ValueError("Choose a flux, net progress, species source or vacancy source for rate conversion")
    src_scale, dst_scale = denominator_scale(source), denominator_scale(target)
    ratio, missing = _bridge(source, target, evidence)
    directional = kind in ("forward_flux", "reverse_flux")
    if value == "not_applicable" and not directional:
        raise ValueError("Only a directional flux can be not_applicable")
    native_unit = NUMERATOR[kind] if source["extent_unit"] == "event" else source["extent_unit"]
    target_unit = NUMERATOR[kind] if target["extent_unit"] == "event" else target["extent_unit"]
    result = {"quantity_kind": kind, "native_value": value, "native_basis": deepcopy(source),
              "native_numerator_unit": native_unit, "target_numerator_unit": target_unit,
              "target_basis": deepcopy(target), "evidence": deepcopy(evidence), "value": None, "missing": missing}
    if value == "not_applicable":
        return dict(result, status="not_applicable", missing=[])
    if value is None:
        missing.append(f"native {kind} observation")
    else:
        if isinstance(value, str):
            raise ValueError(f"Expected a numeric {kind} or explicit unavailable direction")
        number = finite_number(value, kind, nonnegative=directional)
    if missing:
        return dict(result, status="unavailable")
    # Combine the finite scales before rounding so extreme denominator weights do not silently zero a rate.
    scaled = Fraction(number) * Fraction(ratio) * Fraction(extent_scale(source["extent_unit"], target["extent_unit"]))
    scaled *= Fraction(convert_unit(1, target["time_unit"], source["time_unit"]))
    scaled *= Fraction(target["denominator_value"]) * Fraction(dst_scale)
    scaled /= Fraction(source["denominator_value"]) * Fraction(src_scale)
    converted = finite_number(scaled, "converted rate")
    if number and converted == 0:
        raise ValueError("Rate conversion underflow")
    return dict(result, status="available", value=converted)
