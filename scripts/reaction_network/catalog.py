"""Index catalyst domains and species for one network snapshot."""
from collections import Counter

from scripts.artifact_io import sha256_json
from scripts.multiphase_contracts import COLLECTIONS, _bundle_validator

COMMON = "https://schemas.sbq123.invalid/multiphase/1.0.0/common.schema.json#/$defs/"


def check_common(value, name):
    error = next(_bundle_validator().evolve(schema={"$ref": COMMON + name}).iter_errors(value), None)
    if error:
        raise ValueError(f"Invalid {name}: {error.message}")


def catalog(data):
    index = {}
    for group, _, key in COLLECTIONS[:-1]:
        rows = {}
        for row in data.get(group, []):
            identity = row[key]
            check_common(identity, "id")
            if identity in rows:
                raise ValueError(f"Duplicate {group} ID {identity}")
            rows[identity] = row
        index[group] = rows
    if len(index["projects"]) != 1:
        raise ValueError("A network snapshot needs one catalyst project")
    for group, field, parent in (("materials", "project_id", "projects"), ("phases", "material_id", "materials"),
                                 ("surfaces", "phase_id", "phases"), ("sites", "surface_id", "surfaces")):
        for row in index[group].values():
            if group == "surfaces" and row.get(field) is None:
                continue  # Partial field mappings may lack the catalyst phase.
            if row.get(field) not in index[parent]:
                raise ValueError(f"Unknown {group}.{field}")
    for interface in index["interfaces"].values():
        ids = interface["surface_ids"]
        if len(set(ids)) != len(ids) or len(ids) < 2 or set(ids) - index["surfaces"].keys():
            raise ValueError("Invalid interface surface domains")
    return index


def check_context(row, index):
    surfaces = set(row["surface_ids"])
    if surfaces - index["surfaces"].keys() or len(surfaces) != len(row["surface_ids"]):
        raise ValueError("Unknown or repeated surface")
    interface = row.get("interface_id")
    if interface is not None or len(surfaces) > 1:
        if interface not in index["interfaces"] or surfaces != set(index["interfaces"][interface]["surface_ids"]):
            raise ValueError("Interface and surface domains disagree")
    return {index["surfaces"][sid].get("phase_id") for sid in surfaces}


def site_counts(counts, index, surfaces):
    if counts is None:
        return
    check_common(counts, "sites")
    for site in counts:
        if site not in index["sites"] or index["sites"][site]["surface_id"] not in surfaces:
            raise ValueError(f"Site {site} is outside the surface domain")


def register_species(index):
    fingerprints = {}
    seen = {}
    for key, row in index["species"].items():
        phases = check_context(row, index)
        surfaces = row["surface_ids"]
        if row["phase"] not in ("gas", "surface", "liquid") or bool(surfaces) != (row["phase"] == "surface"):
            raise ValueError(f"{key}: species phase and surface disagree")
        materials = set(row["material_ids"])
        if materials - index["materials"].keys() or (None not in phases and materials != {
            index["phases"][p]["material_id"] for p in phases
        }):
            raise ValueError(f"{key}: material/phase mismatch")
        check_common(row["composition"], "composition")
        if row.get("charge") is not None and type(row["charge"]) is not int:
            raise ValueError(f"{key}: invalid charge")
        occupied = row.get("site_occupancy")
        site_counts(occupied, index, surfaces)
        if occupied is not None and {index["sites"][s]["surface_id"] for s in occupied} != set(surfaces):
            raise ValueError(f"{key}: occupancy does not cover species domains")
        physical = {f: row.get(f) for f in ("phase", "composition", "charge", "interface_id", "site_occupancy",
                                            "adsorption_geometry", "source_atom_indices_zero_based", "configuration_id")}
        atoms = physical["source_atom_indices_zero_based"]
        if atoms is not None:
            if not isinstance(atoms, list) or any(type(i) is not int or i < 0 for i in atoms) or len(set(atoms)) != len(atoms):
                raise ValueError("Invalid species fragment atom map")
            physical["source_atom_indices_zero_based"] = sorted(atoms)
        physical.update(project=next(iter(index["projects"])), material_ids=sorted(materials), surface_ids=sorted(surfaces),
                        phase_ids=sorted(p for p in phases if p is not None),
                        structure=(row.get("structural_provenance") or {}).get("sha256") or row.get("structure_id"))
        physical["facets"] = [{k: index["surfaces"][s].get(k) for k in ("phase_id", "miller_indices", "termination", "defects")}
                              for s in sorted(surfaces)]
        physical["site_types"] = {s: index["sites"][s]["site_type"] for s in occupied or {}}
        digest = sha256_json(physical)
        if digest in seen:
            raise ValueError(f"Duplicate species fingerprint: {seen[digest]} and {key}; disambiguate configurations")
        fingerprints[key] = digest
        seen[digest] = key
    return fingerprints


def resolve_site(label, surfaces, index):
    sites = index["sites"]
    if label in sites and sites[label]["surface_id"] in surfaces:
        return label
    choices = [s for s, row in sites.items() if row["site_type"] == label and row["surface_id"] in surfaces]
    if len(choices) != 1:
        raise ValueError(f"Unknown or ambiguous site type {label}; supply a domain-specific site ID")
    return choices[0]


def site_mapping(record, reaction, index):
    value = record["value"]
    surfaces = reaction["surface_ids"]
    interface = reaction.get("interface_id")
    if value["interface_assignment"] not in ([interface] if interface else ["single surface", "single_surface", *surfaces]):
        raise ValueError("Confirmed interface assignment differs from the reaction domain")
    occupancies = {}
    for item in value["occupancies"]:
        species = item["species"]
        if species not in index["species"] or (species not in reaction["reactants"] and species not in reaction["products"]):
            raise ValueError(f"Confirmed species outside reaction: {species}")
        site = resolve_site(item["site_type"], index["species"][species]["surface_ids"], index)
        occupancies.setdefault(species, Counter())[site] += item["multiplicity"]
    result = {"occupancies": {key: dict(v) for key, v in occupancies.items()}}
    for kind in ("sites_consumed", "sites_released"):
        total = Counter()
        for item in value[kind]:
            total[resolve_site(item["site_type"], surfaces, index)] += item["count"]
        result[kind] = dict(total)
    return result
