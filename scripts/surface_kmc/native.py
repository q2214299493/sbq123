"""Construct the four Zacros 4.0 model files and optional initial state."""
import math
from collections import Counter, defaultdict

from scripts.artifact_io import sha256_json
from scripts.native_inputs import conditions, integer, token
from scripts.scientific_validation import finite_number
from scripts.surface_kmc.lattice import embeddings, lattice


def species_names(config, dataset):
    gas, surface = config["gas"], config["surface_aliases"]
    species = {s["species_id"]: s for s in dataset["species"]}
    if set(gas) != {s for s, v in species.items() if v["phase"] == "gas"} or set(surface) != set(species)-gas.keys():
        raise ValueError("Native gas/surface species map is incomplete")
    names = {s: token(v["name"]) for s, v in gas.items()}
    names.update({s: token(v)+"*" for s, v in surface.items()})
    if len(set(names.values())) != len(names):
        raise ValueError("Duplicate native species")
    for reaction in dataset["reactions"]:
        for direction in ("forward", "reverse"):
            law = reaction["model"].get(direction) or {}
            if law.get("method") in {"gas_adsorption", "dissociative_adsorption"}:
                mass = gas[law["gas_species_id"]]["mass_g_mol"]
                if not math.isclose(mass, law["mass_u"], rel_tol=1e-9):
                    raise ValueError("Gas molecular weight differs from approved collision mass")
    return species, names


def simulation(c, pressures, names, species, t, p):
    gas = {s: c["gas"][s] for s in sorted(c["gas"])}
    surface = sorted(c["surface_aliases"])
    lines = [f"random_seed {integer(c['seed'], 'random seed')}", f"temperature {t:.17e}", f"pressure {p:.17e}", f"n_gas_species {len(gas)}"]
    if gas:
        if p <= 0:
            raise ValueError("Gas mixture needs positive pressure")
        lines += ["gas_specs_names "+" ".join(names[s] for s in gas),
                  "gas_energies "+" ".join(str(finite_number(v["energy_eV"], "gas energy")) for v in gas.values()),
                  "gas_molec_weights "+" ".join(str(finite_number(v["mass_g_mol"], "mass", positive=True)) for v in gas.values()),
                  "gas_molar_fracs "+" ".join(str(pressures[s]/p) for s in gas)]
    lines += [f"n_surf_species {len(surface)}", "surf_specs_names "+" ".join(names[s] for s in surface),
              "surf_specs_dent "+" ".join(str(sum(species[s]["site_occupancy"].values())) for s in surface),
              "snapshots off", "process_statistics on event 1", "species_numbers on event 1",
              f"max_steps {integer(c['max_steps'], 'max steps')}", f"max_time {finite_number(c['max_time_s'], 'max time', positive=True)}",
              f"wall_time {integer(c['wall_time_s'], 'wall time')}"]
    if type(c["write_restart"]) is not bool:
        raise ValueError("Specify checkpoint policy")
    return lines + ([] if c["write_restart"] else ["no_restart"]) + ["finish"]


def slots(pattern, names):
    entities, legs = {}, Counter()
    lines = []
    for i, slot in enumerate(pattern):
        key = tuple(slot) if slot else (None, i)
        entity = entities.setdefault(key, len(entities)+1)
        legs[key] += 1
        label = names[slot[0]] if slot else "*"
        lines.append(f"{entity} {label} {legs[key]}")
    return lines


def configuration_key(pattern, match):
    molecules = defaultdict(list)
    for slot, site in zip(pattern, match, strict=True):
        if slot:
            molecules[tuple(slot)].append(site)
    # Dentate positions are ordered in the native pattern.
    return tuple(sorted((sid, tuple(sites)) for (sid, _), sites in molecules.items()))


def pattern_header(labels, edges, aliases):
    lines = [f"sites {len(labels)}", "site_types "+" ".join(aliases[s] for s in labels)]
    if edges:
        lines.append("neighboring "+" ".join(f"{i+1}-{j+1}" for i, j in edges))
    return lines


def proximity_setting(config, local_event, direction):
    if not config["clusters"] and not any(v["energy_eV"] for v in config["gas"].values()):
        return []
    if local_event.get("coefficient_basis") != "isolated_reactants":
        raise ValueError("Interacting lattice rates require a reviewed isolated-reactants reference")
    value = finite_number(local_event.get("forward_proximity_factor"), "reviewed BEP proximity factor", nonnegative=True)
    if value > 1:
        raise ValueError("BEP proximity factor exceeds one")
    factor = value if direction == "forward" else 1-value
    return [f"prox_factor {factor:.17e}"]


def mechanism(events, dataset, c, names, nodes, graph):
    rows = {r["reaction_id"]: r for r in dataset["reactions"]}
    gas = sorted(c["gas"])
    lines, checks = ["mechanism"], []
    reference = math.prod(c["repeat_cell"])*finite_number(c["reference_sites_per_cell"], "reference sites", positive=True)
    for i, e in enumerate(events, 1):
        r = rows[e["reaction_id"]]
        if e["coverage_fractions"]:
            raise ValueError("Fixed-coverage point coefficients cannot be used across a changing lattice coverage")
        matches = embeddings(e["site_ids"], e["neighbors_zero_based"], nodes, graph)
        transitions = {(tuple(sorted(m)), configuration_key(e["initial"], m), configuration_key(e["final"], m)) for m in matches}
        ratio = len(transitions)/reference
        expected = r["model"]["local_event"]["patterns_per_reference_site"][e["direction"]]
        if not math.isclose(ratio, expected, rel_tol=1e-12) or not transitions:
            raise ValueError("Lattice matching-event multiplicity differs from approved normalization")
        step = f"r{i}_{e['direction']}"
        lines += ["step "+step, *pattern_header(e["site_ids"], e["neighbors_zero_based"], c["site_aliases"])]
        f = e["reaction"]
        net = {s: f["products"].get(s, 0)-f["reactants"].get(s, 0) for s in gas}
        if {s: -n for s, n in net.items() if n < 0} != e["gas_partial_pressure_orders"]:
            raise ValueError("Native net gas stoichiometry cannot express this pressure order")
        if any(net.values()):
            lines.append("gas_reacs_prods "+" ".join(f"{names[s]} {n}" for s, n in net.items() if n))
        lines += ["initial", *slots(e["initial"], names), "final", *slots(e["final"], names),
                  f"pre_expon {e['pre_expon']:.17e}", f"activ_eng {e['activ_eng_eV']:.17e}",
                  *proximity_setting(c, r["model"]["local_event"], e["direction"]), "end_step"]
        checks.append({"native_step": step, "reaction_id": e["reaction_id"], "matching_events": len(transitions),
                       "reference_sites": reference, "patterns_per_reference_site": ratio, "coefficient": e["pre_expon"]})
    return lines+["end_mechanism"], checks


def energetics(c, dataset, species, names, nodes, graph):
    lines = ["energetics"]
    clusters = c["clusters"]
    if clusters or any(v["energy_eV"] for v in c["gas"].values()):
        physical = {"clusters": clusters, "gas_energies_eV": {s: v["energy_eV"] for s, v in c["gas"].items()}}
        if any(r["model"]["local_event"].get("energetics_sha256") != sha256_json(physical) for r in dataset["reactions"]):
            raise ValueError("Lateral/gas energetics must be bound to the reviewed local rate model")
    if not clusters:
        # Zacros requires a nonempty expansion even for an explicitly ideal lattice.
        clusters = [{"site_ids": [site], "neighbors_zero_based": [], "state": [None],
                     "graph_multiplicity": 1, "energy_eV": 0.0} for site in sorted(c["site_aliases"])]
    for i, cl in enumerate(clusters, 1):
        labels, edges, state = cl["site_ids"], cl["neighbors_zero_based"], cl["state"]
        if len(state) != len(labels) or not next(embeddings(labels, edges, nodes, graph), None):
            raise ValueError("Unrealizable energetic cluster")
        fragments = defaultdict(Counter)
        for s, slot in zip(labels, state, strict=True):
            if slot:
                fragments[tuple(slot)][s] += 1
        if any(foot != species[sid]["site_occupancy"] for (sid, _), foot in fragments.items()):
            raise ValueError("Invalid energetic cluster footprint")
        lines += [f"cluster c{i}", *pattern_header(labels, edges, c["site_aliases"]), "lattice_state", *slots(state, names),
                  f"graph_multiplicity {integer(cl['graph_multiplicity'], 'cluster multiplicity')}",
                  f"cluster_eng {finite_number(cl['energy_eV'], 'cluster energy')}", "end_cluster"]
    return lines+["end_energetics"]


def event_leg_orders(events):
    """Zacros numbers a molecule's legs in local-pattern order on each side."""
    orders = defaultdict(set)
    for event in events:
        for side in ("initial", "final"):
            entities = defaultdict(list)
            for site, slot in zip(event["site_ids"], event[side], strict=True):
                if slot:
                    entities[tuple(slot)].append(site)
            for (sid, _), labels in entities.items():
                orders[sid].add(tuple(labels))
    return orders


def state_input(c, species, names, nodes, graph, events):
    lines, occupied = ["initial_state"], set()
    orders = event_leg_orders(events)
    # Zacros numbers basis sites consecutively inside each replicated cell.
    ordered = sorted(nodes)
    for sid, indices in c["seeds"]:
        if not indices or any(type(i) is not int or not 1 <= i <= len(ordered) for i in indices):
            raise ValueError("Invalid initial site index")
        sites = [ordered[i-1] for i in indices]
        if len(set(sites)) != len(sites) or occupied.intersection(sites) or Counter(nodes[s] for s in sites) != species[sid]["site_occupancy"]:
            raise ValueError("Overlapping seed or incorrect footprint")
        if orders[sid] and tuple(nodes[s] for s in sites) not in orders[sid]:
            raise ValueError("Seed dentate order differs from the reviewed local event patterns")
        connected = {sites[0]}
        for _ in sites:
            connected |= {s for s in sites if graph[s] & connected}
        if connected != set(sites):
            raise ValueError("Disconnected initial molecule")
        occupied.update(sites)
        lines.append("seed_on_sites "+names[sid]+" "+" ".join(map(str, indices)))
    return lines+["end_initial_state"]


def render(table, config, dataset):
    events = table["events"]
    first, c = events[0], config["zacros"]
    pressures = conditions(dataset, config, first["pressure_bar"])
    species, names = species_names(c, dataset)
    lat, nodes, graph = lattice(c, {s["site_id"] for s in dataset["catalog"]["sites"]})
    mech, checks = mechanism(events, dataset, c, names, nodes, graph)
    files = {"simulation_input.dat": simulation(c, pressures, names, species, first["T_K"], first["pressure_bar"]),
             "lattice_input.dat": lat, "mechanism_input.dat": mech,
             "energetics_input.dat": energetics(c, dataset, species, names, nodes, graph)}
    if c["seeds"]:
        files["state_input.dat"] = state_input(c, species, names, nodes, graph, events)
    return {name: "\n".join(lines)+"\n" for name, lines in files.items()}, {"species_names": names, "site_count": len(nodes),
            "gas_indices": {s: i for i, s in enumerate(sorted(c["gas"]), 1)},
            "surface_indices": {s: i for i, s in enumerate(sorted(c["surface_aliases"]), 1)},
            "site_aliases": c["site_aliases"], "partial_pressure_bar": pressures,
            "event_checks": checks, "initial_state": "seeded" if c["seeds"] else "empty"}
