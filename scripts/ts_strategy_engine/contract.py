from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import sha256_json


COMPATIBILITY_FIELDS = (
    "material",
    "surface",
    "branch",
    "slab_model",
    "xc",
    "potcar_family",
    "encut_ev",
    "kmesh",
    "magnetic_state",
    "coverage",
)
FINAL_ENERGY_COMPATIBILITY_FIELDS = (
    "ismear",
    "sigma_ev",
    "fixed_atom_indices_zero_based",
    "ldipol",
    "vacuum_thickness_angstrom",
    "final_energy_convention",
)
REQUIRED_FIELDS = (
    "reaction_id",
    "reaction_family",
    "reactant_id",
    "product_id",
    "index_base",
    "atom_map",
    "reaction_atoms",
    "broken_bonds",
    "formed_bonds",
    "site_changes",
    "compatibility",
    "endpoints",
)


def load_contract(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"reaction contract not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("reaction contract must be a JSON/YAML object")
    normalized = _verified_normalized_contract(payload)
    if normalized is not None:
        return normalized
    return normalize_contract(payload)


def _verified_normalized_contract(payload: dict[str, Any]) -> dict[str, Any] | None:
    hashes = ("atom_map_sha256", "compatibility_sha256", "contract_sha256")
    if payload.get("version") != 1 or not all(payload.get(field) for field in hashes):
        return None
    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing:
        raise ValueError("normalized reaction contract missing: " + ", ".join(missing))
    unsigned = dict(payload)
    stored = unsigned.pop("contract_sha256")
    if stored != sha256_json(unsigned):
        raise ValueError("normalized reaction contract hash mismatch")
    if payload["atom_map_sha256"] != sha256_json(payload["atom_map"]):
        raise ValueError("normalized reaction contract atom-map hash mismatch")
    if payload["compatibility_sha256"] != sha256_json(payload["compatibility"]):
        raise ValueError("normalized reaction contract compatibility hash mismatch")
    return payload


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if str(value).strip() not in {str(integer), f"{integer}.0"}:
        raise ValueError(f"{label} must be an integer")
    return integer


def _index(value: Any, index_base: int, label: str) -> int:
    index = _integer(value, label) - index_base
    if index < 0:
        raise ValueError(f"{label} is below index_base")
    return index


def _pairs(values: Any, index_base: int, label: str) -> list[list[int]]:
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list of two-index pairs")
    pairs: list[list[int]] = []
    for position, pair in enumerate(values):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(f"{label}[{position}] must contain two indices")
        left = _index(pair[0], index_base, f"{label}[{position}][0]")
        right = _index(pair[1], index_base, f"{label}[{position}][1]")
        if left == right:
            raise ValueError(f"{label}[{position}] cannot reference one atom twice")
        pairs.append(sorted((left, right)))
    return [list(pair) for pair in sorted({tuple(pair) for pair in pairs})]


def _atom_map(values: Any, index_base: int) -> list[dict[str, int]]:
    if not isinstance(values, list) or not values:
        raise ValueError("atom_map must be a non-empty list")
    normalized: list[dict[str, int]] = []
    for position, item in enumerate(values):
        if isinstance(item, dict):
            left, right = item.get("is"), item.get("fs")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            left, right = item
        else:
            raise ValueError(f"atom_map[{position}] must be {{is, fs}} or a two-index pair")
        normalized.append(
            {
                "is": _index(left, index_base, f"atom_map[{position}].is"),
                "fs": _index(right, index_base, f"atom_map[{position}].fs"),
            }
        )
    return normalized


def _nonempty_text(value: Any, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} must be non-empty")
    return text


def _reaction_coordinates(values: Any, index_base: int) -> list[dict[str, Any]]:
    if values in (None, []):
        return []
    if not isinstance(values, list) or not values:
        raise ValueError("reaction_coordinates must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    for position, value in enumerate(values):
        if not isinstance(value, dict):
            raise ValueError(f"reaction_coordinates[{position}] must be an object")
        kind = _nonempty_text(value.get("kind"), f"reaction_coordinates[{position}].kind").lower()
        atoms = value.get("atoms")
        if kind != "distance" or not isinstance(atoms, (list, tuple)) or len(atoms) != 2:
            raise ValueError("current executable reaction coordinates require kind=distance and two atoms")
        interval = value.get("important_interval_A")
        if not isinstance(interval, (list, tuple)) or len(interval) != 2:
            raise ValueError(f"reaction_coordinates[{position}].important_interval_A must contain two values")
        low, high = (float(interval[0]), float(interval[1]))
        if low <= 0 or low >= high:
            raise ValueError(f"reaction_coordinates[{position}].important_interval_A is invalid")
        normalized.append(
            {
                "name": _nonempty_text(value.get("name"), f"reaction_coordinates[{position}].name"),
                "kind": kind,
                "atoms": [
                    _index(atoms[0], index_base, f"reaction_coordinates[{position}].atoms[0]"),
                    _index(atoms[1], index_base, f"reaction_coordinates[{position}].atoms[1]"),
                ],
                "important_interval_A": [low, high],
                "role": _nonempty_text(value.get("role", "secondary"), "reaction coordinate role").lower(),
            }
        )
    if sum(item["role"] == "primary" for item in normalized) != 1:
        raise ValueError("reaction_coordinates must define exactly one primary coordinate")
    return normalized


def has_final_energy_compatibility(compatibility: dict[str, Any]) -> bool:
    return set(FINAL_ENERGY_COMPATIBILITY_FIELDS) <= set(compatibility)


def _normalize_compatibility(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("compatibility must be an object")
    missing_compatibility = [field for field in COMPATIBILITY_FIELDS if field not in value]
    if missing_compatibility:
        raise ValueError("missing compatibility fields: " + ", ".join(missing_compatibility))
    normalized = {field: value[field] for field in COMPATIBILITY_FIELDS}
    normalized["kmesh"] = [_integer(item, "compatibility.kmesh") for item in value["kmesh"]]
    if len(normalized["kmesh"]) != 3:
        raise ValueError("compatibility.kmesh must contain three integers")
    normalized["encut_ev"] = float(value["encut_ev"])
    for field in set(COMPATIBILITY_FIELDS) - {"encut_ev", "kmesh"}:
        normalized[field] = _nonempty_text(normalized[field], f"compatibility.{field}").lower()
    present = set(FINAL_ENERGY_COMPATIBILITY_FIELDS) & set(value)
    if present and present != set(FINAL_ENERGY_COMPATIBILITY_FIELDS):
        missing = sorted(set(FINAL_ENERGY_COMPATIBILITY_FIELDS) - present)
        raise ValueError("partial final-energy compatibility block; missing: " + ", ".join(missing))
    if not present:
        return normalized
    normalized["ismear"] = _integer(value["ismear"], "compatibility.ismear")
    normalized["sigma_ev"] = float(value["sigma_ev"])
    normalized["vacuum_thickness_angstrom"] = float(value["vacuum_thickness_angstrom"])
    if normalized["sigma_ev"] < 0:
        raise ValueError("compatibility.sigma_ev must be non-negative")
    if normalized["vacuum_thickness_angstrom"] <= 0:
        raise ValueError("compatibility.vacuum_thickness_angstrom must be positive")
    fixed = value["fixed_atom_indices_zero_based"]
    if not isinstance(fixed, list) or not fixed:
        raise ValueError("compatibility.fixed_atom_indices_zero_based must be a non-empty list")
    normalized["fixed_atom_indices_zero_based"] = sorted(
        {_integer(item, "compatibility.fixed_atom_indices_zero_based") for item in fixed}
    )
    if any(index < 0 for index in normalized["fixed_atom_indices_zero_based"]):
        raise ValueError("compatibility.fixed_atom_indices_zero_based cannot contain negative indices")
    if not isinstance(value["ldipol"], bool):
        raise ValueError("compatibility.ldipol must be a JSON/YAML boolean")
    normalized["ldipol"] = value["ldipol"]
    normalized["final_energy_convention"] = _nonempty_text(
        value["final_energy_convention"], "compatibility.final_energy_convention"
    ).lower()
    return normalized


def normalize_contract(payload: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing:
        raise ValueError("missing reaction contract fields: " + ", ".join(missing))
    index_base = _integer(payload["index_base"], "index_base")
    if index_base not in {0, 1}:
        raise ValueError("index_base must be 0 or 1")

    normalized_compatibility = _normalize_compatibility(payload["compatibility"])

    endpoints = payload["endpoints"]
    if not isinstance(endpoints, dict) or not {"initial", "final"} <= set(endpoints):
        raise ValueError("endpoints.initial and endpoints.final are required")
    normalized_endpoints: dict[str, dict[str, str]] = {}
    for name in ("initial", "final"):
        record = endpoints[name]
        if not isinstance(record, dict):
            raise ValueError(f"endpoints.{name} must be an object")
        required = ("calculation_id", "structure_file_id", "static_result_id")
        missing_endpoint = [field for field in required if field not in record]
        if missing_endpoint:
            raise ValueError(f"endpoints.{name} missing: " + ", ".join(missing_endpoint))
        normalized_endpoints[name] = {field: _nonempty_text(record[field], f"endpoints.{name}.{field}") for field in required}

    normalized = {
        "version": 1,
        "reaction_id": _nonempty_text(payload["reaction_id"], "reaction_id"),
        "reaction_family": _nonempty_text(payload["reaction_family"], "reaction_family").lower(),
        "reactant_id": _nonempty_text(payload["reactant_id"], "reactant_id").lower(),
        "product_id": _nonempty_text(payload["product_id"], "product_id").lower(),
        "index_base": 0,
        "atom_map": _atom_map(payload["atom_map"], index_base),
        "reaction_atoms": sorted({_index(value, index_base, "reaction_atoms") for value in payload["reaction_atoms"]}),
        "broken_bonds": _pairs(payload["broken_bonds"], index_base, "broken_bonds"),
        "formed_bonds": _pairs(payload["formed_bonds"], index_base, "formed_bonds"),
        "reaction_coordinates": _reaction_coordinates(payload.get("reaction_coordinates"), index_base),
        "site_changes": sorted({_nonempty_text(value, "site_changes").lower() for value in payload["site_changes"]}),
        "compatibility": normalized_compatibility,
        "endpoints": normalized_endpoints,
        "waypoint_files": [str(Path(value)) for value in payload.get("waypoint_files", [])],
        "retrieval_constraints": payload.get("retrieval_constraints"),
    }
    if not normalized["reaction_atoms"]:
        raise ValueError("reaction_atoms must contain explicit numeric atom indices")
    mapped = {item["is"] for item in normalized["atom_map"]}
    if not set(normalized["reaction_atoms"]) <= mapped:
        raise ValueError("every reaction atom must exist in atom_map")
    for label in ("broken_bonds", "formed_bonds"):
        if any(not set(pair) <= mapped for pair in normalized[label]):
            raise ValueError(f"every {label} atom must exist in atom_map")
    if any(not set(item["atoms"]) <= mapped for item in normalized["reaction_coordinates"]):
        raise ValueError("every reaction-coordinate atom must exist in atom_map")
    normalized["atom_map_sha256"] = sha256_json(normalized["atom_map"])
    normalized["compatibility_sha256"] = sha256_json(normalized["compatibility"])
    normalized["contract_sha256"] = sha256_json(normalized)
    return normalized
