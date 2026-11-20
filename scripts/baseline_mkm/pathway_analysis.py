"""Stoichiometric hyperedges and bounded, labelled species-path witnesses."""

from collections import defaultdict, deque


def reach(start, adjacency):
    seen = set(start)
    todo = list(seen)
    while todo:
        node = todo.pop()
        for other, _, _ in adjacency.get(node, ()):
            if other not in seen:
                seen.add(other)
                todo.append(other)
    return seen


def witnesses(feed, product, adjacency, *, excluded=None, limit=32):
    queue = deque([([feed], [])])
    paths = []
    visited = 0
    while queue and len(paths) < limit and visited < 4096:
        nodes, steps = queue.popleft()
        visited += 1
        for other, rid, direction in adjacency.get(nodes[-1], ()):
            if rid == excluded or other in nodes or any(s["reaction_id"] == rid for s in steps):
                continue
            trace = [*steps, dict(reaction_id=rid, direction=direction)]
            if other == product:
                paths.append(dict(species=nodes + [other], steps=trace))
                if len(paths) == limit:
                    return paths, True
            else:
                queue.append((nodes + [other], trace))
    return paths, bool(queue)


def pathway_graph(network, rates, feeds, products):
    nodes = {
        s["species_id"]: {k: s[k] for k in ("phase", "surface_ids", "interface_id", "composition")}
        for s in network["species"]
    }
    surfaces = {s["surface_id"]: s["phase_id"] for s in network["catalog"]["surfaces"]}
    for node in nodes.values():
        node["phase_ids"] = sorted({surfaces[s] for s in node["surface_ids"] if surfaces[s] is not None})
    rows = {r["reaction_id"]: r for r in rates["reactions"]} if rates else {}
    site_phase = {s["site_id"]: surfaces[s["surface_id"]] for s in network["catalog"]["sites"]}
    edges = []
    adjacency = defaultdict(list)
    producer = defaultdict(set)
    consumer = defaultdict(set)
    hyperedges = []
    for entry in network["reactions"]:
        r = entry["definition"]
        rid = r["reaction_id"]
        row = rows.get(rid, {})
        edge = {
            k: r.get(k)
            for k in ("reaction_id", "phase_ids", "surface_ids", "interface_id", "required_sites", "reversible")
        }
        edge.update(
            direction=entry["direction"],
            reaction_free_energy_eV=entry["energies"]["gibbs_ev"]["reaction"],
            net_flux=row.get("net_flux"),
            forward_flux=row.get("forward_flux"),
            reverse_flux=row.get("reverse_flux"),
        )
        site_ids = (
            set(r.get("required_sites") or {})
            | set(r.get("sites_consumed") or {})
            | set(r.get("sites_released") or {})
        )
        participants = set(r["reactants"]) | set(r["products"])
        phases = {p for sid in participants for p in nodes[sid]["phase_ids"]}
        phases.update(site_phase[s] for s in site_ids if site_phase[s] is not None)
        edge["participating_phase_ids"] = sorted(phases)
        edges.append(edge)
        for direction, side in entry["direction"].items():
            if direction == "status" or not side:
                continue
            lhs, rhs = set(side["reactants"]), set(side["products"])
            hyperedges.append((lhs, rhs))
            for a in sorted(lhs):
                consumer[a].add(rid)
                for b in sorted(rhs - {a}):
                    adjacency[a].append((b, rid, direction))
            for b in rhs:
                producer[b].add(rid)
    reachable = set(feeds)
    while True:
        expanded = reachable.union(*(rhs for lhs, rhs in hyperedges if lhs <= reachable))
        if expanded == reachable:
            break
        reachable = expanded
    can_reach = {s: reach([s], adjacency) for s in nodes}
    components, cycles = cyclic_components(can_reach, adjacency)
    paths = []
    for a in feeds:
        for b in products:
            traced, limited = witnesses(a, b, adjacency)
            paths.append(
                dict(feed=a, product=b, paths=traced, enumeration_limited=limited, competing_paths=len(traced) > 1)
            )
    intermediates = [s for s in nodes if producer[s] and consumer[s] and s not in set(feeds) | set(products)]
    return dict(
        nodes=nodes,
        reactions=edges,
        feed_to_product=paths,
        intermediates=intermediates,
        dead_ends=[s for s in nodes if nodes[s]["phase"] == "surface" and not set(products) & can_reach[s]]
        if products
        else None,
        branching={s: sorted(rs) for s, rs in consumer.items() if len(rs) > 1},
        reversible_reactions=[e["reaction_id"] for e in edges if e["reversible"] is True],
        cyclic_species_components=components,
        multistep_cycle_witnesses=cycles,
        cross_phase_reactions=[e["reaction_id"] for e in edges if len(e["participating_phase_ids"]) > 1],
        feed_reachable_with_all_coreactants=sorted(reachable),
        pathway_percentages=None,
        algorithm="Directed species projection of stoichiometric hyperedges; simple species and reaction paths, "
        "32 witnesses / 4096 expansions per feed-product pair. Components indicate mutual reachability. "
        "Feed closure requires all co-reactants, assumes site availability, and ignores flux magnitude. "
        "No atom tracing or flux decomposition.",
    )


def cycle_witness(group, adjacency):
    """One projection cycle using distinct reaction IDs, excluding elementary backtracking."""
    for start in group:
        for other, rid, direction in adjacency[start]:
            if other not in group:
                continue
            paths, _ = witnesses(other, start, adjacency, excluded=rid, limit=1)
            if paths:
                return {
                    "species": [start, *paths[0]["species"]],
                    "steps": [dict(reaction_id=rid, direction=direction), *paths[0]["steps"]],
                }
    return None


def cyclic_components(can_reach, adjacency):
    remaining = set(can_reach)
    components = []
    while remaining:
        s = min(remaining)
        component = sorted(t for t in can_reach[s] if s in can_reach[t])
        remaining.difference_update(component)
        if len(component) > 1:
            components.append(component)
    cycles = []
    for group in components:
        witness = cycle_witness(group, adjacency)
        if witness:
            cycles.append(witness)
    return components, cycles
