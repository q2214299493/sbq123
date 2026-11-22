"""Index catalyst domains and species for one network snapshot."""
from collections import Counter

from scripts.artifact_io import sha256_json
from scripts.multiphase_contracts import (
    COLLECTIONS, _bundle_validator, check_interface_ownership, check_site_interface, interface_phase_ids,
    matches_interface_surfaces,
)

SCHEMA_BASE = "https://schemas.sbq123.invalid/multiphase/1.0.0/"
COMMON = SCHEMA_BASE + "common.schema.json#/$defs/"
DESCRIPTORS = {
    "phase": ("phase_category", "description", "composition", "charge"),
    "surface": ("surface_descriptor", "miller_indices", "lattice_vectors_angstrom", "coordinate_convention"),
    "interface": ("geometry",),
}


def check_common(value, name):
    error = next(_bundle_validator().evolve(schema={"$ref": COMMON + name}).iter_errors(value), None)
    if error:
        raise ValueError(f"Invalid {name}: {error.message}")


def check_record_field(schema, field, value):
    ref = SCHEMA_BASE + f"{schema}.schema.json#/properties/{field}"
    error = next(_bundle_validator().evolve(schema={"$ref": ref}).iter_errors(value), None)
    if error:
        raise ValueError(f"Invalid {schema}.{field}: {error.message}")


def check_structural_fields(index):
    # Partial network definitions may omit evidence. Validate supplied metadata
    # with the same field schemas as complete exchange records.
    for schema, names in DESCRIPTORS.items():
        fields = (*names, "structure_id", "structural_provenance", "validation")
        if schema == "interface":
            fields += ("phase_ids", "surface_ids")
        for row in index[schema + "s"].values():
            for field in fields:
                if row.get(field) is None:
                    continue
                check_record_field(schema, field, row[field])
    for surface in index["surfaces"].values():
        indices = surface.get("miller_indices") or []
        if len(indices) == 4 and sum(indices[:3]) != 0:
            raise ValueError(f"{surface['surface_id']}: inconsistent Miller-Bravais indices")


def index_records(data):
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
    return index


def catalog(data):
    index = index_records(data)
    for group, field, parent in (("materials", "project_id", "projects"), ("phases", "material_id", "materials"),
                                 ("surfaces", "phase_id", "phases"), ("sites", "surface_id", "surfaces")):
        for row in index[group].values():
            if group == "surfaces" and row.get(field) is None:
                continue  # Partial field mappings may lack the catalyst phase.
            if row.get(field) not in index[parent]:
                raise ValueError(f"Unknown {group}.{field}")
    check_structural_fields(index)
    check_interface_ownership(index)
    for surface in index["surfaces"].values():
        if "site_types" in surface:
            validate_site_types(surface["site_types"])
    for site in index["sites"].values():
        surface = index["surfaces"][site["surface_id"]]
        if "site_types" in surface and site["site_type"] not in surface["site_types"]:
            raise ValueError("Site type is outside the configured surface catalog")
    return index


def check_network_version(snapshot):
    digest = sha256_json({k: v for k, v in snapshot.items() if k != "network_version"})
    if snapshot.get("network_version") != digest:
        raise ValueError("Network version digest mismatch")
    return digest


def ownership_report(data):
    """Read-only identity edges. Missing evidence stays local to its row."""
    report = {"phases": {}, "surfaces": {}, "interfaces": {}, "sites": {}}
    if data.get("format") == "reaction-network/1":
        report["network_version"] = check_network_version(data)
        data = data["catalog"]
    elif not (data.get("format") == "network-definition/1"
              or ("format" not in data and data.get("schema_version") == "1.0.0")):
        raise ValueError("Expected a versioned bundle, network definition or network snapshot")
    index = index_records(data)
    for group, parent, field in (("phases", "materials", "material_id"), ("surfaces", "phases", "phase_id"),
                                 ("sites", "surfaces", "surface_id")):
        for identity, row in sorted(index[group].items()):
            owner = row.get(field)
            resolved = owner is not None and owner in index[parent]
            entry = {field: owner if resolved else None, "issues": []}
            if not resolved:
                entry["issues"].append(f"Unresolved {field}: {owner!r}")
            if group == "sites":
                entry["site_type"] = row.get("site_type")
            else:
                describe_structure(entry, row, "phase" if group == "phases" else "surface")
            report[group][identity] = entry

    for identity, row in sorted(index["interfaces"].items()):
        report["interfaces"][identity] = interface_ownership_row(row, index, report["surfaces"])

    for key, entry in report["sites"].items():
        owner = index["sites"][key].get("interface_id")
        entry["interface_id"] = None
        if owner is not None:
            interface = report["interfaces"].get(owner)
            if interface is not None and entry["surface_id"] in (interface["surface_ids"] or []):
                entry["interface_id"] = owner
            else:
                entry["issues"].append(f"Unresolved site interface: {owner}")
    return report


def interface_ownership_row(row, index, surfaces_by_id):
    entry = {"issues": []}
    describe_structure(entry, row, "interface")
    declared = row.get("phase_ids")
    surfaces = row.get("surface_ids")
    if surfaces is None:
        surfaces = []
    if not isinstance(surfaces, list) or any(not isinstance(key, str) for key in surfaces):
        entry["issues"].append("Invalid interface surface IDs")
        surfaces = []
    located = []
    try:
        phases = interface_phase_ids(dict(row, surface_ids=[]) if declared is not None else row, index)
    except (KeyError, ValueError) as exc:
        phases = {pid for pid in declared if isinstance(pid, str) and pid in index["phases"]} if isinstance(declared, list) else set()
        entry["issues"].append(str(exc))
    for key in sorted(set(surfaces)):
        surface = surfaces_by_id.get(key)
        if surface is None or (declared is not None and surface["phase_id"] is not None and surface["phase_id"] not in phases):
            entry["issues"].append(f"Unresolved interface surface: {key}")
        else:
            located.append(key)
            if surface["phase_id"] is None:
                entry["issues"].append(f"Unresolved phase owner of {key}")
    if len(surfaces) != len(set(surfaces)):
        entry["issues"].append("Repeated interface surface ID")
    entry["surface_ids"] = located or None
    located_phases = {surfaces_by_id[key]["phase_id"] for key in located}
    entry["phase_ids"] = sorted((phases if declared is not None else located_phases) - {None}) or None
    for pid in sorted(phases - located_phases - {None}):
        entry["issues"].append(f"Surface assignment unknown for {pid}")
    return entry


def describe_structure(entry, row, schema):
    for field in (*DESCRIPTORS[schema], "structure_id", "structural_provenance", "validation"):
        if field in DESCRIPTORS[schema] and field not in row:
            continue
        value = row.get(field)
        if value is not None:
            try:
                check_record_field(schema, field, value)
            except ValueError:
                value = None
                entry["issues"].append(f"Invalid {field}")
        elif field in ("structure_id", "structural_provenance"):
            entry["issues"].append(f"Missing {field}")
        if field == "validation":
            entry["validation_status"] = value["status"] if value else None
        else:
            entry[field] = value


def validate_site_types(types):
    if not isinstance(types, list):
        raise ValueError("Surface site_types must be a list")
    for label in types:
        check_common(label, "id")
    if len(types) != len(set(types)):
        raise ValueError("Duplicate configured site type")


def check_context(row, index):
    surfaces = set(row["surface_ids"])
    if surfaces - index["surfaces"].keys() or len(surfaces) != len(row["surface_ids"]):
        raise ValueError("Unknown or repeated surface")
    interface = row.get("interface_id")
    if interface is not None or len(surfaces) > 1:
        if interface not in index["interfaces"] or not matches_interface_surfaces(row, index["interfaces"][interface], index):
            raise ValueError("Interface and surface domains disagree")
    return {index["surfaces"][sid].get("phase_id") for sid in surfaces}


def site_counts(counts, index, surfaces, interface_id=None):
    if counts is None:
        return
    check_common(counts, "sites")
    for site in counts:
        if site not in index["sites"] or index["sites"][site]["surface_id"] not in surfaces:
            raise ValueError(f"Site {site} is outside the surface domain")
        check_site_interface(index["sites"][site], interface_id)


def register_species(index, confirmed_zero=()):
    fingerprints = {}
    seen = {}
    for key, row in index["species"].items():
        phases = check_context(row, index)
        surfaces = row["surface_ids"]
        if row["phase"] not in ("gas", "surface", "liquid") or bool(surfaces) != (row["phase"] == "surface"):
            raise ValueError(f"{key}: species phase and surface disagree")
        materials = set(row["material_ids"])
        known_materials = {index["phases"][p]["material_id"] for p in phases if p is not None}
        if (materials - index["materials"].keys() or not known_materials <= materials
                or (None not in phases and materials != known_materials)):
            raise ValueError(f"{key}: material/phase mismatch")
        check_common(row["composition"], "composition")
        if row.get("charge") is not None and type(row["charge"]) is not int:
            raise ValueError(f"{key}: invalid charge")
        occupied = row.get("site_occupancy")
        site_counts(occupied, index, surfaces, row.get("interface_id"))
        if (occupied is not None and not (occupied == {} and key in confirmed_zero)
                and {index["sites"][s]["surface_id"] for s in occupied} != set(surfaces)):
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


def resolve_site(label, surfaces, index, interface_id=None):
    sites = index["sites"]
    if label in sites:
        site_counts({label: 1}, index, surfaces, interface_id)
        return label
    choices = [s for s, row in sites.items() if row["site_type"] == label and row["surface_id"] in surfaces
               and row.get("interface_id") in (None, interface_id)]
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
        location = index["species"][species]
        site = resolve_site(item["site_type"], location["surface_ids"], index, location.get("interface_id"))
        occupancies.setdefault(species, Counter())[site] += item["multiplicity"]
    result = {"occupancies": {key: dict(v) for key, v in occupancies.items()}}
    for kind in ("sites_consumed", "sites_released"):
        total = Counter()
        for item in value[kind]:
            total[resolve_site(item["site_type"], surfaces, index, interface)] += item["count"]
        result[kind] = dict(total)
    return result
