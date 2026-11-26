"""Offline identity checks on existing kinetic-dataset records. No numerical rate comparison."""

from collections import Counter

from scripts.artifact_io import sha256_json
from scripts.kinetic_parameters.engine import check_version
from scripts.kinetic_parameters.export import verify_event
from scripts.multiphase_contracts import read_artifact as read_artifact
from scripts.reaction_network.builder import directions, side as side_totals
from scripts.reaction_network.catalog import catalog, check_context, register_species, site_counts
from scripts.runtime_resources import SOURCE_ROOT


def dataset_reference(dataset, file_sha256):
    check_version(dataset, "dataset_version")
    if dataset["format"] != "kinetic-dataset/1":
        raise ValueError("Expected kinetic-dataset/1")
    parameters = {}
    for row in dataset["reactions"]:
        rid, record = row["reaction_id"], row["parameter_set"]
        if rid in parameters or record["reaction_id"] != rid or (
            row["model"]["parameter_set_id"] != record["parameter_set_id"]
        ):
            raise ValueError(f"Conflicting parameter identity for {rid}")
        parameters[rid] = dict(parameter_set_id=record["parameter_set_id"], reaction_row_sha256=sha256_json(row),
                               energy_reference_id=record["energy_reference_id"], energy_basis=record["energy_basis"],
                               uncertainty=record["uncertainty"])
    return dict(file_sha256=file_sha256, dataset_version=dataset["dataset_version"],
                network_version=dataset["network_version"], project_id=dataset["project_id"], parameters=parameters)


def _connected(slots, graph):
    pending = [next(iter(slots))]
    reached = set()
    while pending:
        node = pending.pop()
        if node not in reached:
            reached.add(node)
            pending.extend((graph[node] & slots) - reached)
    return reached == slots


def _molecular_footprints(sites, slots, base, species):
    if not isinstance(slots, list) or len(slots) != len(sites):
        raise ValueError("Incomplete local configuration")
    entities = {}
    for index, slot in enumerate(slots, base):
        if slot is None:
            continue
        if not isinstance(slot, list) or len(slot) != 2:
            raise ValueError("Invalid local entity slot")
        sid, entity = slot
        if not isinstance(sid, str) or sid not in species or type(entity) is not int or entity < 1:
            raise ValueError("Unknown or invalid local entity")
        occupant, legs = entities.setdefault(entity, (sid, set()))
        if occupant != sid:
            raise ValueError("Distinct local molecules share an entity")
        legs.add(index)
    for sid, legs in entities.values():
        occupancy = Counter(sites[i - base] for i in legs)
        if species[sid]["phase"] != "surface" or occupancy != species[sid]["site_occupancy"]:
            raise ValueError("Local molecular footprint differs from species inventory")
        yield legs


def _local_geometry(event, row, species):
    if not isinstance(event, dict):
        raise ValueError("Missing local site pattern")
    graph = []
    groups = []
    parts = [(event, ("initial", "final"))]
    if "environment" in event:
        parts.append((event["environment"], ("state",)))
    for part, states in parts:
        if not isinstance(part, dict):
            raise ValueError("Invalid local geometry")
        sites = part.get("site_ids")
        if not isinstance(sites, list) or not sites or any(not isinstance(site, str) for site in sites):
            raise ValueError("Invalid local site inventory")
        base = len(graph)
        graph.extend(set() for _ in sites)
        edges = part.get("neighbors_zero_based")
        if not isinstance(edges, list):
            raise ValueError("Missing local adjacency")
        for edge in edges:
            if not isinstance(edge, list) or len(edge) != 2 or any(
                type(i) is not int or not 0 <= i < len(graph) for i in edge
            ):
                raise ValueError("Invalid local site index")
            i, j = edge
            if i == j or j in graph[i] or max(i, j) < base:
                raise ValueError("Self-loop, duplicate or misplaced local adjacency")
            graph[i].add(j)
            graph[j].add(i)
        for state in states:
            groups.extend(_molecular_footprints(sites, part.get(state), base, species))
    if not _connected(set(range(len(graph))), graph) or any(not _connected(legs, graph) for legs in groups):
        raise ValueError("Disconnected local geometry or molecular footprint")
    verify_event(event, row, species)


def _identity_catalog(dataset, source_root):
    check_version(dataset, "dataset_version")
    index = catalog(dict(dataset["catalog"], species=dataset["species"], reactions=dataset["reactions"]))
    if dataset["format"] != "kinetic-dataset/1" or dataset["project_id"] not in index["projects"]:
        raise ValueError("Dataset format or project differs from catalog")
    return index, register_species(index, require_structure=True, source_root=source_root)


def _reaction(dataset, reaction_id, identity_catalog):
    index, fingerprints = identity_catalog
    if reaction_id not in index["reactions"]:
        raise ValueError(f"Unknown reaction {reaction_id}")
    row = index["reactions"][reaction_id]
    check_context(row, index)
    direction = row["direction"]
    forward = direction["forward"]
    for sid in forward["reactants"].keys() | forward["products"].keys():
        if sid not in index["species"] or index["species"][sid].get("composition") is None:
            raise ValueError(f"Missing molecular identity for {sid}")
    before = side_totals(forward["reactants"], forward["sites_consumed"], row, index)
    after = side_totals(forward["products"], forward["sites_released"], row, index)
    if None in before or None in after or before != after or dict(before[2]) != row["site_balance"]:
        raise ValueError(f"{reaction_id}: unbalanced molecular or site inventory")
    status = direction["status"]
    if status not in ("irreversible", "reversible") or direction != directions(
        dict(forward, reversible=status == "reversible")
    ):
        raise ValueError(f"{reaction_id}: contradictory reaction direction")
    molecules = {}
    for side in ("reactants", "products"):
        molecules[side] = {fingerprints[sid]: count for sid, count in forward[side].items()}

    inventories = {k: forward[k] for k in ("sites_consumed", "sites_released")}
    inventories["site_balance"] = row["site_balance"]
    for counts in inventories.values():
        if counts is None:
            raise ValueError("Missing site inventory")
        site_counts(counts, index, row["surface_ids"], row["interface_id"])
    local = (row.get("model") or {}).get("local_event")
    _local_geometry(local, row, index["species"])
    sites = set(local["site_ids"])
    geometry = {k: local[k] for k in ("site_ids", "neighbors_zero_based")}
    for side in ("initial", "final"):
        geometry[side] = [None if leg is None else [fingerprints[leg[0]], leg[1]] for leg in local[side]]
    if "environment" in local:
        env = local["environment"]
        sites.update(env["site_ids"])
        geometry["environment"] = dict(site_ids=env["site_ids"], neighbors_zero_based=env["neighbors_zero_based"],
                                       state=[None if leg is None else [fingerprints[leg[0]], leg[1]]
                                              for leg in env["state"]])
    site_counts(dict.fromkeys(sites, 1), index, row["surface_ids"], row["interface_id"])
    # Resolve inventory labels to their owning structures, including both ends of an interface.
    domains = {"site": [index["sites"][k] for k in sorted(sites)]}
    domains["surface"] = [index["surfaces"][k] for k in sorted(row["surface_ids"])]
    domains["phase"] = [index["phases"][k] for k in sorted({s["phase_id"] for s in domains["surface"]})]
    domains["material"] = [index["materials"][k] for k in sorted({p["material_id"] for p in domains["phase"]})]
    domains["interface"] = [index["interfaces"][row["interface_id"]]] if row["interface_id"] else []
    # Validation dates and review paths are provenance, not structural differences.
    physical = {group: [{k: v for k, v in item.items() if k not in ("validation", "schema_version")}
                        for item in rows] for group, rows in domains.items()}
    return dict(project=dataset["project_id"], molecular_stoichiometry=molecules,
                per_event_sites=inventories, inventory_owners=physical, direction=status, local_geometry=geometry)


class IncompatibleIdentity(ValueError):
    """Both sides have evidence and their physical definitions disagree."""


def require_reaction_identity(left, right, reaction_id):
    """Verify this oriented elementary identity only. Conditions and parameters have separate bindings."""
    catalogs = [_identity_catalog(d, SOURCE_ROOT) for d in (left, right)]
    return _match_reaction(left, right, reaction_id, catalogs)


def require_common_identities(left, right, *, left_root=SOURCE_ROOT):
    catalogs = [_identity_catalog(left, left_root), _identity_catalog(right, SOURCE_ROOT)]
    reactions = [c[0]["reactions"].keys() for c in catalogs]
    if not all(reactions):
        raise ValueError("Missing reaction environment")
    for rid in sorted(reactions[0] & reactions[1]):
        _match_reaction(left, right, rid, catalogs)
    if reactions[0] != reactions[1]:
        raise IncompatibleIdentity("Different reaction environments")
    if catalogs[0][1] != catalogs[1][1]:
        raise IncompatibleIdentity("Incompatible molecular species")


def _match_reaction(left, right, reaction_id, catalogs):
    a, b = (_reaction(d, reaction_id, c) for d, c in zip((left, right), catalogs, strict=True))
    differences = [k for k in a if a[k] != b[k]]
    if differences:
        raise IncompatibleIdentity(f"{reaction_id}: incompatible " + ", ".join(differences))
    return dict(reaction_id=reaction_id, **a)


def check_binding(recorded, reconstructed):
    """Only compare with evidence freshly reconstructed by the owning reader."""
    if sha256_json(recorded) != sha256_json(reconstructed):
        raise ValueError("Stored binding differs from reconstructed evidence")
