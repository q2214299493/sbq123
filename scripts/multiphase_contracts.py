"""Offline validation of version 1.0.0 multiphase exchange records. No writes or execution."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from referencing import Registry, Resource

from scripts.kinetic_data.interphase_transfer import assess_transfer
from scripts.kinetic_data.stoichiometric_sources import stoichiometric_totals
from scripts.runtime_resources import resource_path
from scripts.scientific_validation import finite_number


# Collection, record schema name, primary key.
COLLECTIONS = (
    ("projects", "catalyst_project", "project_id"),
    ("materials", "catalyst_material", "material_id"),
    ("phases", "phase", "phase_id"),
    ("surfaces", "surface", "surface_id"),
    ("sites", "active_site", "site_id"),
    ("interfaces", "interface", "interface_id"),
    ("species", "species", "species_id"),
    ("reactions", "reaction", "reaction_id"),
    ("parameter_sets", "kinetic_parameter", "parameter_set_id"),
    ("runs", "simulation_run", "run_id"),
)
# Rounding allowance for an identity between serialized eV quantities, per elementary event.
ENERGY_ATOL_EV = 1e-8


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON property {key!r}")
        result[key] = value
    return result


def decode_unique_json(raw):
    return json.loads(raw, object_pairs_hook=_unique_keys)


def read_unique_json(path):
    return decode_unique_json(path.read_bytes())


def _check_finite(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            _check_finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _check_finite(child, f"{path}[{i}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        finite_number(value, path)


@lru_cache(maxsize=1)
def _bundle_validator():
    schemas = {}
    for folder, names in (
        ("catalysis", ["common", *(item[1] for item in COLLECTIONS[:6])]),
        ("kinetics", ["bundle", *(item[1] for item in COLLECTIONS[6:])]),
    ):
        for name in names:
            path = resource_path(f"configs/{folder}/{name}.schema.json")
            schemas[name] = json.loads(path.read_text(encoding="utf-8"))
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return Draft202012Validator(schemas["bundle"], registry=registry)


def _get(index, collection, key):
    try:
        return index[collection][key]
    except KeyError as exc:
        raise ValueError(f"unknown {collection} reference {key!r}") from exc


def _project_for_surface(index, surface_id):
    surface = _get(index, "surfaces", surface_id)
    phase = _get(index, "phases", surface["phase_id"])
    return _get(index, "materials", phase["material_id"])["project_id"]


def interface_phase_ids(interface, index):
    """Resolve only explicitly declared phases or owners of the named surfaces."""
    surfaces = interface.get("surface_ids")
    if surfaces is None:
        surfaces = []
    declared = interface.get("phase_ids")
    if (not isinstance(surfaces, list) or any(not isinstance(key, str) for key in surfaces)
            or len(set(surfaces)) != len(surfaces) or (declared is None and len(surfaces) < 2)):
        raise ValueError("Invalid interface surface domains")
    owners = {_get(index, "surfaces", sid).get("phase_id") for sid in surfaces}
    if declared is None:
        phases = owners
    else:
        if (not isinstance(declared, list) or any(not isinstance(key, str) for key in declared)
                or len(set(declared)) != len(declared) or len(declared) < 2):
            raise ValueError("An explicit interface needs at least two distinct phase IDs")
        phases = set(declared)
        if not (owners - {None}) <= phases:
            raise ValueError("Interface phases contradict surface ownership")
    projects = {_get(index, "materials", _get(index, "phases", pid)["material_id"])["project_id"]
                for pid in phases if pid is not None}
    if len(projects) > 1:
        raise ValueError(f"{interface['interface_id']}: interface crosses projects")
    return phases


def matches_interface_surfaces(row, interface, index):
    """Reaction domains cover the contact. A located species may occupy one side."""
    surfaces = set(row["surface_ids"])
    assigned = set(interface.get("surface_ids") or [])
    if not surfaces or not surfaces <= assigned:
        return False
    if surfaces == assigned:
        return True
    if "species_id" not in row:
        return False
    return all(_get(index, "sites", site)["surface_id"] in surfaces for site in row.get("site_occupancy") or {})


def check_site_interface(site, interface_id):
    if site.get("interface_id") is not None and site["interface_id"] != interface_id:
        raise ValueError(f"{site['site_id']}: site belongs to a different interface")


def check_interface_ownership(index):
    for interface in index["interfaces"].values():
        interface_phase_ids(interface, index)
    for site in index["sites"].values():
        if site.get("interface_id") is not None:
            interface = _get(index, "interfaces", site["interface_id"])
            if site["surface_id"] not in (interface.get("surface_ids") or []):
                raise ValueError(f"{site['site_id']}: site surface is not assigned to its interface")


def _check_context(record, index):
    surfaces = set(record["surface_ids"])
    projects = {_project_for_surface(index, key) for key in surfaces}
    if len(projects) > 1:
        raise ValueError("surface context crosses catalyst projects")
    interface_id = record["interface_id"]
    if interface_id is not None:
        interface = _get(index, "interfaces", interface_id)
        located = {_get(index, "surfaces", key)["phase_id"] for key in surfaces}
        if (not matches_interface_surfaces(record, interface, index)
                or ("species_id" not in record and interface_phase_ids(interface, index) != located)):
            raise ValueError("interface and surface context disagree")
    elif len(surfaces) > 1 and not (
        record.get("reaction_type") in ("interphase_transfer", "cross_phase_elementary") and record["eligibility"] in ("draft", "blocked")
    ):
        raise ValueError("multi-surface context needs an interface")
    return {_get(index, "surfaces", key)["phase_id"] for key in surfaces}


def _check_catalog(index):
    for collection, field, parent in (
        ("materials", "project_id", "projects"), ("phases", "material_id", "materials"),
        ("surfaces", "phase_id", "phases"), ("sites", "surface_id", "surfaces"),
    ):
        for record in index[collection].values():
            _get(index, parent, record[field])
    check_interface_ownership(index)
    for surface in index["surfaces"].values():
        indices = surface.get("miller_indices", [])
        if len(indices) == 4 and sum(indices[:3]) != 0:
            raise ValueError(f"{surface['surface_id']}: inconsistent Miller-Bravais indices")
    for species in index["species"].values():
        phases = _check_context(species, index)
        materials = {_get(index, "phases", key)["material_id"] for key in phases}
        if set(species["material_ids"]) != materials:
            raise ValueError(f"{species['species_id']}: material/surface identity mismatch")
        sites = [_get(index, "sites", key) for key in species["site_occupancy"]]
        for site in sites:
            check_site_interface(site, species["interface_id"])
        occupied = {site["surface_id"] for site in sites}
        if occupied != set(species["surface_ids"]):
            raise ValueError(f"{species['species_id']}: occupied sites disagree with surface identity")


def _check_species_context(species, reaction):
    key = species["species_id"]
    if not set(species["surface_ids"]).issubset(reaction["surface_ids"]):
        raise ValueError(f"{key}: species is outside reaction surface context")
    if species["interface_id"] is not None and species["interface_id"] != reaction["interface_id"]:
        raise ValueError(f"{key}: species belongs to a different interface")


def _side(stoichiometry, free_sites, reaction, index):
    terms = []
    for key, coefficient in stoichiometry.items():
        species = _get(index, "species", key)
        _check_species_context(species, reaction)
        if reaction["eligibility"] == "eligible" and (
            species["validation"]["status"] != "accepted" or species["thermochemistry_status"] != "reviewed"
        ):
            raise ValueError(f"{key}: eligible reaction requires reviewed species")
        terms.append((coefficient, species["composition"], species["charge"], species["site_occupancy"]))
    totals = stoichiometric_totals(terms, free_sites)
    if None in totals:
        raise ValueError("Reaction balance requires complete composition, charge and site inventories")
    return totals


def check_cross_phase_scope(reaction, index, left, right):
    """Check the declared contact against actual residents, required sites and optional located TS."""
    surfaces = set(reaction["surface_ids"])
    declared = set(reaction["phase_ids"])
    owners = {_get(index, "surfaces", s).get("phase_id") for s in surfaces}
    if len(declared) < 2 or len(surfaces) < 2 or (None not in owners and owners != declared):
        raise ValueError("Cross-phase elementary reaction requires at least two participating phases and their surfaces")
    contact_id = reaction["interface_id"]
    if contact_id is not None:
        contact = _get(index, "interfaces", contact_id)
        if interface_phase_ids(contact, index) != declared:
            raise ValueError("Declared phases differ from the participating interface")
    residents = [_get(index, "species", sid) for sid in reaction["reactants"].keys() | reaction["products"].keys()]
    gaps = []
    if "ts_species_id" in reaction:
        ts = _get(index, "species", reaction["ts_species_id"])
        _check_species_context(ts, reaction)
        identity = (reaction.get("state_identities") or {}).get("TS") or reaction.get("ts_id")
        if (ts["phase"] != "surface" or reaction.get("ts_treatment") != "located" or not identity
                or identity not in (ts.get("structure_id"), (ts.get("structural_provenance") or {}).get("sha256"))):
            raise ValueError("TS species needs a matching located transition structure")
        footprint = ts.get("site_occupancy")
        if footprint is None:
            gaps.append("Unknown TS site footprint")
        elif reaction.get("required_sites") is not None and not Counter(footprint) <= Counter(reaction["required_sites"]):
            raise ValueError("Required sites do not cover the TS species footprint")
        if ts in residents:
            raise ValueError("Transition complex must have its own species identity")
        for field, lhs, rhs in zip(("composition", "charge"), left[:2], right[:2], strict=True):
            known = [value for value in (lhs, rhs) if value is not None]
            if ts.get(field) is None or not known:
                gaps.append(f"Unknown TS {field} balance")
            elif any(ts[field] != value for value in known):
                raise ValueError(f"TS species {field} disagrees with reaction stoichiometry")
        if reaction.get("eligibility") == "eligible" and (ts.get("validation") or {}).get("status") != "accepted":
            raise ValueError("Eligible reaction requires a reviewed TS species")
        residents.append(ts)
    used = {s for row in residents for s in row["surface_ids"]}
    for field in ("required_sites", "sites_consumed", "sites_released"):
        used.update(_get(index, "sites", site)["surface_id"] for site in reaction.get(field) or {})
    if surfaces != used:
        raise ValueError("Cross-phase reaction has an unrelated or missing participating surface")
    return gaps


def _check_balance(reaction, index):
    left = _side(reaction["reactants"], reaction["sites_consumed"], reaction, index)
    right = _side(reaction["products"], reaction["sites_released"], reaction, index)
    for label, lhs, rhs in zip(("element", "charge", "site"), left, right, strict=True):
        if lhs != rhs:
            raise ValueError(f"{label} conservation failed: {lhs} != {rhs}")
    if reaction["reaction_type"] == "cross_phase_elementary":
        check_cross_phase_scope(reaction, index, left, right)
    for site in reaction["required_sites"].keys() | reaction["sites_consumed"].keys() | reaction["sites_released"].keys():
        row = _get(index, "sites", site)
        check_site_interface(row, reaction["interface_id"])
        if row["surface_id"] not in reaction["surface_ids"]:
            raise ValueError(f"{site}: required site outside reaction context")
    if not left[2] <= Counter(reaction["required_sites"]):
        raise ValueError("required sites do not cover the reaction footprint")


def _energy_check(energy, record, sources):
    if energy["reference_id"] != record["energy_reference_id"]:
        raise ValueError("incompatible energy reference")
    if energy["source"] not in sources:
        raise ValueError("energy source absent from record provenance")
    if record["eligibility"] == "eligible" and energy["source"]["kind"] in {"model_prediction", "synthetic"}:
        raise ValueError("eligible records require scientific evidence")


def _check_triple(values, reaction, *, thermal):
    eligible = reaction["eligibility"] == "eligible"
    for name, energy in values.items():
        if energy is not None:
            _energy_check(energy, reaction, reaction["provenance"])
            if thermal and eligible and energy["source"]["kind"] not in {"thermal_correction", "experiment"}:
                raise ValueError("eligible Gibbs values require thermochemical evidence")
        elif thermal and eligible and (name != "reverse" or reaction["reversible"]):
            raise ValueError(f"eligible reaction missing {name} free energy")
    if all(v is not None for v in values.values()):
        difference = values["forward"]["value"] - values["reverse"]["value"]
        if not math.isclose(difference, values["reaction"]["value"], rel_tol=0, abs_tol=ENERGY_ATOL_EV):
            raise ValueError("forward minus reverse barrier disagrees with reaction energy")


def _require_reviewed_context(reaction, index):
    records = [_get(index, "sites", key) for key in reaction["required_sites"]]
    if reaction["interface_id"] is not None:
        records.append(_get(index, "interfaces", reaction["interface_id"]))
    for key in reaction["surface_ids"]:
        surface = _get(index, "surfaces", key)
        phase = _get(index, "phases", surface["phase_id"])
        material = _get(index, "materials", phase["material_id"])
        records.extend((surface, phase, material, _get(index, "projects", material["project_id"])))
    if any(row["validation"]["status"] != "accepted" for row in records):
        raise ValueError("eligible reaction requires reviewed catalyst context")


def _check_reaction(reaction, index):
    if reaction["reaction_type"] == "interfacial" and reaction["interface_id"] is None:
        raise ValueError("interfacial reaction requires an interface")
    if _check_context(reaction, index) != set(reaction["phase_ids"]):
        raise ValueError("phase/surface context mismatch")
    _check_balance(reaction, index)
    if reaction["reaction_type"] == "interphase_transfer":
        assess_transfer(reaction, index)
    _check_triple(reaction["electronic_energies"], reaction, thermal=False)
    free = reaction["free_energies"]
    if free is not None:
        _check_triple(free["values"], reaction, thermal=True)
    if reaction["eligibility"] == "eligible":
        _require_reviewed_context(reaction, index)
        if any(entry["kind"] in {"synthetic", "model_prediction"} for entry in reaction["provenance"]):
            raise ValueError("eligible reaction contains exploratory provenance")


def _check_rate(rate, name, energies, parameter):
    energy = rate["activation_energy"]
    eligible = parameter["eligibility"] == "eligible"
    _energy_check(energy, parameter, parameter["sources"])
    barrier = energies[name] if energies is not None else None
    if barrier is None:
        if eligible:
            raise ValueError(f"eligible {name} rate lacks source barrier")
    elif not math.isclose(energy["value"], barrier["value"], rel_tol=0, abs_tol=ENERGY_ATOL_EV):
        raise ValueError(f"{name} rate barrier differs from source reaction")
    elif eligible and energy["source"] != barrier["source"]:
        raise ValueError(f"eligible {name} rate must cite the reaction barrier's source")


def _check_parameter(parameter, index):
    reaction = _get(index, "reactions", parameter["reaction_id"])
    eligible = parameter["eligibility"] == "eligible"
    if eligible and (reaction["eligibility"] != "eligible" or any(
        source["kind"] in {"model_prediction", "synthetic"} for source in parameter["sources"]
    )):
        raise ValueError("eligible parameter needs an eligible reaction and scientific sources")
    if (parameter["energy_reference_id"], parameter["rate_law_id"]) != (reaction["energy_reference_id"], reaction["rate_law_id"]):
        raise ValueError("parameter reference or rate law disagrees with reaction")
    if parameter["reverse"] is not None and not reaction["reversible"]:
        raise ValueError("irreversible rate law has a reverse rate")
    if eligible and reaction["reversible"] and parameter["reverse"] is None:
        raise ValueError("eligible reversible parameter set needs reverse rate")
    for field in ("temperature_K", "pressure_Pa"):
        valid = parameter["validity_range"]
        if not valid["min_" + field] <= parameter[field] <= valid["max_" + field]:
            raise ValueError(f"{field} is outside parameter validity range")
    energies = reaction["electronic_energies"]
    if parameter["energy_basis"] == "gibbs":
        free = reaction["free_energies"]
        if free and (free["temperature_K"], free["standard_state_id"]) != (parameter["temperature_K"], parameter["standard_state_id"]):
            raise ValueError("Gibbs temperature or standard state disagrees")
        energies = free["values"] if free else None
    for name in ("forward", "reverse"):
        if parameter[name] is not None:
            _check_rate(parameter[name], name, energies, parameter)
    for term in parameter["coverage_terms"]:
        species = _get(index, "species", term["species_id"])
        if species["phase"] != "surface":
            raise ValueError("coverage term needs a species on the reaction surface")
        _check_species_context(species, reaction)
        if eligible and species["validation"]["status"] != "accepted":
            raise ValueError(f"{species['species_id']}: eligible parameter set requires an accepted coverage species")
        if term["min_fraction"] > term["max_fraction"]:
            raise ValueError("reversed coverage validity interval")
        _energy_check(term["coefficient"], parameter, parameter["sources"])


def _check_run(run, index):
    for key in run["parameter_set_ids"]:
        _get(index, "parameter_sets", key)
    if run["scientific_validity"]["status"] == "accepted" and (
        run["execution_status"] != "succeeded"
        or run["numerical_convergence"] not in {"converged", "inapplicable"}
        or not run["outputs"]
        or any(index["parameter_sets"][key]["eligibility"] != "eligible" for key in run["parameter_set_ids"])
    ):
        raise ValueError(f"{run['run_id']}: accepted run lacks completed, reviewed result context")


def validate_bundle(bundle: dict) -> None:
    """Raise ValueError at the first invalid record. Success grants no downstream authority."""
    _check_finite(bundle)
    error = next(_bundle_validator().iter_errors(bundle), None)
    if error:
        error = best_match([error])
        raise ValueError(f"{error.json_path}: {error.message}")
    index = {}
    for collection, _, primary_key in COLLECTIONS:
        records = {}
        for record in bundle[collection]:
            key = record[primary_key]
            if key in records:
                raise ValueError(f"{collection}: duplicate ID {key!r}")
            records[key] = record
        index[collection] = records
    _check_catalog(index)
    for collection, check in (("reactions", _check_reaction), ("parameter_sets", _check_parameter)):
        for key, record in index[collection].items():
            try:
                check(record, index)
            except ValueError as exc:
                raise ValueError(f"{collection}.{key}: {exc}") from exc
    standard_states = {}
    for parameter in bundle["parameter_sets"]:
        key, states = parameter["standard_state_id"], parameter["standard_states"]
        if standard_states.setdefault(key, states) != states:
            raise ValueError(f"{key}: conflicting standard-state definitions")
    for run in bundle["runs"]:
        _check_run(run, index)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="path to a versioned JSON bundle")
    args = parser.parse_args(argv)
    try:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_keys)
        validate_bundle(bundle)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Invalid multiphase bundle: {exc}\n")
    print("Multiphase bundle conforms to 1.0.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
