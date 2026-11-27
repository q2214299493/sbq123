from collections import Counter, defaultdict


def verify_pattern(sites, slots, direction, species, side, vacancy_key):
    if len(slots) != len(sites):
        raise ValueError("Lattice pattern length differs from footprint")
    fragments = defaultdict(Counter)
    vacancies = Counter()
    for site, slot in zip(sites, slots, strict=True):
        if slot is None:
            vacancies[site] += 1
        else:
            sid, entity = slot
            if sid not in direction[side] or type(entity) is not int or entity < 1:
                raise ValueError("Unknown or invalid lattice entity")
            fragments[sid, entity][site] += 1
    observed = Counter()
    if len({entity for _, entity in fragments}) != len(fragments):
        raise ValueError("Distinct lattice molecules share an entity number")
    for (sid, _entity), occupancy in fragments.items():
        if species[sid]["site_occupancy"] != dict(occupancy):
            raise ValueError("Pattern occupancy conflicts with species site inventory")
        observed[sid] += 1
    expected = {s: n for s, n in direction[side].items() if species[s]["phase"] == "surface"}
    if vacancies != Counter(direction[vacancy_key]) or observed != expected:
        raise ValueError("Event pattern disagrees with reaction stoichiometry")


def verify_event(event, r, species):
    if not event:
        raise ValueError("Zacros requires reviewed local site pattern and event normalization")
    sites = event["site_ids"]
    if not sites or Counter(sites) != Counter(r["site_balance"]):
        raise ValueError("Event sites differ from the reaction footprint")
    graph = {i: set() for i in range(len(sites))}
    for i, j in event["neighbors_zero_based"]:
        if type(i) is not int or type(j) is not int or i not in graph or j not in graph or i == j:
            raise ValueError("Invalid event neighbor pair")
        graph[i].add(j)
        graph[j].add(i)
    seen, todo = set(), [0]
    while todo:
        node = todo.pop()
        if node not in seen:
            seen.add(node)
            todo.extend(graph[node] - seen)
    if len(seen) != len(sites):
        raise ValueError("Disconnected local event graph")
    fwd = r["direction"]["forward"]
    verify_pattern(sites, event["initial"], fwd, species, "reactants", "sites_consumed")
    verify_pattern(sites, event["final"], fwd, species, "products", "sites_released")
