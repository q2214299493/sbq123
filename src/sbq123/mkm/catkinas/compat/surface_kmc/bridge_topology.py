"""Audit one bridged species on two inventories of a declared finite, open graph."""
import argparse
from collections import Counter
import json
from pathlib import Path

from scripts.artifact_io import sha256_bytes
from scripts.multiphase_contracts import _unique_keys
from scripts.native_inputs import integer, token
from scripts.scientific_validation import finite_number
from scripts.surface_kmc.native import pattern_header, slots, state_input


def maximum_matching(pairs):
    """Return a deterministic largest set of vertex-disjoint bipartite edges."""
    neighbors = {}
    for left, right in sorted(pairs):
        neighbors.setdefault(left, []).append(right)
    partner = {}

    def augment(left, seen):
        for right in neighbors[left]:
            if right in seen:
                continue
            seen.add(right)
            if right not in partner or augment(partner[right], seen):
                partner[right] = left
                return True
        return False

    for left in neighbors:
        augment(left, set())
    return sorted((left, right) for right, left in partner.items())


def _finite_graph(spec, observation):
    if spec["classification"] != "synthetic_test_assumption":
        raise ValueError("This mapping is a synthetic topology audit")
    if spec["boundary"] != "finite_open":
        raise ValueError("This finite graph requires explicit open boundaries")
    nodes = sorted(spec["nodes"], key=lambda row: integer(row["index"], "native node index"))
    if [n["index"] for n in nodes] != list(range(1, len(nodes) + 1)):
        raise ValueError("Native indices must be unique and contiguous from one")
    indices = {n["node_id"]: n["index"] for n in nodes}
    inventory = {n["index"]: n["inventory_id"] for n in nodes}
    members = [(s["site_id"], key) for s in observation["sites"] for key in s["physical_site_ids"]]
    actual = [(n["inventory_id"], n["node_id"]) for n in nodes]
    if len(indices) != len(nodes) or Counter(actual) != Counter(members):
        raise ValueError("Missing, duplicate or incorrectly typed physical inventory node")
    adjacent = {i: set() for i in inventory}
    for first, second in spec["edges"]:
        if first not in indices or second not in indices:
            raise ValueError("Unknown edge endpoint")
        i, j = indices[first], indices[second]
        if i == j or j in adjacent[i]:
            raise ValueError("Self-loop or duplicate undirected edge")
        adjacent[i].add(j)
        adjacent[j].add(i)
    return nodes, indices, inventory, adjacent


def _lattice_lines(nodes, adjacent, aliases, legs):
    lines = ["lattice explicit", f"n_sites {len(nodes)}",
             f"max_coord {max(map(len, adjacent.values()))}", f"n_site_types {len(aliases)}",
             "site_type_names " + " ".join(aliases[q] for q in legs), "lattice_structure"]
    coordinates = set()
    for row in nodes:
        x, y = (finite_number(v, "drawing coordinate") for v in row["drawing_xy_angstrom"])
        if (x, y) in coordinates:
            raise ValueError("Duplicate drawing coordinates")
        coordinates.add((x, y))
        i = row["index"]
        links = sorted(adjacent[i])
        fields = [i, str(x), str(y), aliases[row["inventory_id"]], len(links), *links]
        lines.append(" ".join(map(str, fields)))
    return lines + ["end_lattice_structure", "end_lattice"]


def _initial_bridges(spec, observation, indices, pairs):
    bridge = spec["bridge_species_id"]
    owners, seeds = {}, {}
    for entity in spec["initial_bridges"]:
        name = entity["entity_id"]
        if not isinstance(name, str) or not name or name in seeds:
            raise ValueError("Missing or duplicate molecular entity ID")
        if any(n not in indices for n in entity["leg_nodes"]):
            raise ValueError("Unknown initial bridge node")
        pair = tuple(indices[n] for n in entity["leg_nodes"])
        if pair not in pairs:
            raise ValueError("Initial bridge needs an adjacent pair in declared leg order")
        if any(i in owners for i in pair):
            raise ValueError("Initial bridges share a physical node")
        seeds[name] = pair
        owners.update(dict.fromkeys(pair, name))
    counts = observation["species"]
    if (len(counts) != 1 or counts[0]["species_id"] != bridge or counts[0]["coverage"] != len(seeds)
            or counts[0]["molecular_reference"] != observation["inventory_reference"]):
        raise ValueError("Initial entities differ from the molecular counting observation")
    return owners, seeds


def _connected(adjacent):
    reached, pending = set(), [next(iter(adjacent))]
    while pending:
        i = pending.pop()
        if i not in reached:
            reached.add(i)
            pending.extend(adjacent[i] - reached)
    return len(reached) == len(adjacent)


def analyze(spec, definition, observation):
    """Compute geometry-only matches and Zacros review fragments. No rates or execution."""
    gas, bridge = spec["gas_species_id"], spec["bridge_species_id"]
    legs = spec["leg_inventories"]
    aliases = {q: token(v) for q, v in spec["site_aliases"].items()}
    catalog = {s["site_id"]: s for s in definition["sites"]}
    species = {s["species_id"]: s for s in definition["species"]}
    reactions = {r["reaction_id"]: r for r in definition["reactions"]}
    rx = reactions[spec["reaction_id"]]
    if (len(legs) != 2 or len(set(legs)) != 2 or set(legs) != aliases.keys()
            or len(set(aliases.values())) != 2 or not set(legs) <= catalog.keys()):
        raise ValueError("Expected two distinct ordered inventory types and native aliases")
    footprint = dict.fromkeys(legs, 1)
    if (rx["reactants"] != {gas: 1} or rx["products"] != {bridge: 1}
            or species[gas]["phase"] != "gas" or species[bridge]["phase"] != "surface"
            or species[bridge]["site_occupancy"] != footprint
            or rx["sites_consumed"] != footprint or rx["sites_released"] != {}):
        raise ValueError("Bridge and vacancies must match the source adsorption reaction")
    nodes, indices, inventory, adjacent = _finite_graph(spec, observation)
    if set(inventory.values()) != set(legs):
        raise ValueError("Node inventory outside the declared bridge types")
    pairs = sorted((i, j) for i in adjacent if inventory[i] == legs[0]
                   for j in adjacent[i] if inventory[j] == legs[1])
    owners, seeds = _initial_bridges(spec, observation, indices, pairs)

    free = [(i, j) for i, j in pairs if i not in owners and j not in owners]
    witness = maximum_matching(pairs)
    additional = maximum_matching(free)
    event = {"site_ids": legs, "initial": [None, None], "final": [[bridge, 1], [bridge, 1]]}
    names = {bridge: token(spec["bridge_alias"]) + "*", gas: token(spec["gas_alias"])}
    seed_rows = sorted(seeds.items(), key=lambda item: item[1])
    seed_config = {"seeds": [(bridge, list(pair)) for _, pair in seed_rows]}
    empty, bound = (slots(event[side], names) for side in ("initial", "final"))
    candidates = {
        "lattice_input_lines": _lattice_lines(nodes, adjacent, aliases, legs),
        "surface_species": {"surf_specs_names": names[bridge], "surf_specs_dent": 2},
        "gas_species": names[gas], "event_header": pattern_header(legs, [(0, 1)], aliases),
        "adsorption": {"gas_reacs_prods": [names[gas], -1], "initial": empty, "final": bound},
        "desorption_pattern": {"gas_reacs_prods": [names[gas], 1], "initial": bound, "final": empty},
        "state_input_lines": state_input(seed_config, species, names, inventory, adjacent, [event]),
        "source_reversible": rx["reversible"], "execution_plan": None,
        "native_acceptance": "unverified",
    }
    edge_rows = [{"leg_nodes": [i, j], "initial_entities": [owners.get(i), owners.get(j)],
                  "adsorption_match": i not in owners and j not in owners,
                  "desorption_match": i in owners and owners[i] == owners.get(j)} for i, j in pairs]
    by_inventory = {q: {"capacity": sum(v == q for v in inventory.values()),
                        "occupied": sum(inventory[i] == q for i in owners)} for q in legs}
    for row in by_inventory.values():
        row["vacant"] = row["capacity"] - row["occupied"]
    return {
        "classification": spec["classification"], "network_version": observation["network_version"],
        "inventory_reference": observation["inventory_reference"], "boundary": spec["boundary"],
        "connected": _connected(adjacent), "matrix_node_order": [n["node_id"] for n in nodes],
        "adjacency_matrix": [[int(j in adjacent[i]) for j in inventory] for i in inventory],
        "edges": edge_rows, "empty_lattice_matches": len(pairs), "available_adsorptions": len(free),
        "initial_bridges": dict(seed_rows), "initial_desorption_patterns": sum(r["desorption_match"] for r in edge_rows),
        "inventories": by_inventory, "maximum_simultaneous_bridges": len(witness),
        "maximum_witness": witness, "additional_matching_with_seeds_fixed": additional, "zacros_candidate": candidates,
    }


def read_audit(spec_path, root):
    graph_bytes = spec_path.read_bytes()
    spec = json.loads(graph_bytes, object_pairs_hook=_unique_keys)
    sources = {}
    for role in ("definition", "observation"):
        ref = spec["sources"][role]
        raw = (root / ref["path"]).read_bytes()
        if sha256_bytes(raw) != ref["sha256"]:
            raise ValueError(f"Source digest differs for {role}")
        sources[role] = json.loads(raw, object_pairs_hook=_unique_keys)
    result = analyze(spec, **sources)
    result["graph_sha256"] = sha256_bytes(graph_bytes)
    result["sources"] = spec["sources"]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="root of source bindings")
    args = parser.parse_args()
    print(json.dumps(read_audit(args.graph, args.root), indent=2, allow_nan=False))
