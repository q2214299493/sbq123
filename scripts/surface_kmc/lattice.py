"""Validate and expand the periodic unit cell used by the Zacros input."""
import math

from scripts.native_inputs import integer, token
from scripts.scientific_validation import finite_number

OFFSETS = {"self": (0, 0), "north": (0, 1), "east": (1, 0), "northeast": (1, 1), "southeast": (1, -1)}


def lattice(config, site_ids):
    aliases = config["site_aliases"]
    if set(aliases) != site_ids or len({token(s) for s in aliases.values()}) != len(aliases):
        raise ValueError("Invalid lattice site type names")
    (a, b), (c, d) = config["cell_vectors_A"]
    if not math.isfinite(a*d-b*c) or a*d-b*c <= 0:
        raise ValueError("Invalid periodic lattice vectors")
    nx, ny = (integer(n, "cell repetitions") for n in config["repeat_cell"])
    cell = config["cell_sites"]
    if {s for s, x, y in cell} != site_ids or len({(x, y) for s, x, y in cell}) != len(cell):
        raise ValueError("Invalid unit cell site inventory")
    if any(not (0 <= finite_number(v, "fractional coordinate") < 1) for _, x, y in cell for v in (x, y)):
        raise ValueError("Site outside unit cell")
    nodes = {(x, y, i): s for x in range(nx) for y in range(ny) for i, (s, _, _) in enumerate(cell, 1)}
    graph = {k: set() for k in nodes}
    for i, j, direction in config["links"]:
        dx, dy = OFFSETS[direction]
        for x in range(nx):
            for y in range(ny):
                u, v = (x, y, i), ((x+dx) % nx, (y+dy) % ny, j)
                if u not in graph or v not in graph or u == v or v in graph[u]:
                    raise ValueError("Invalid or duplicate translated lattice link")
                graph[u].add(v)
                graph[v].add(u)
    labels = list(dict.fromkeys(aliases[s] for s, _, _ in cell))
    lines = ["lattice periodic_cell", "cell_vectors", f"{a:.17e} {b:.17e}", f"{c:.17e} {d:.17e}", f"repeat_cell {nx} {ny}",
             f"n_site_types {len(labels)}", "site_type_names "+" ".join(labels), f"n_cell_sites {len(cell)}",
             "site_types "+" ".join(aliases[s] for s, _, _ in cell), "site_coordinates",
             *[f"{x:.17e} {y:.17e}" for _, x, y in cell], "neighboring_structure",
             *[f"{i}-{j} {direction}" for i, j, direction in config["links"]], "end_neighboring_structure", "end_lattice"]
    return lines, nodes, graph


def embeddings(labels, edges, nodes, graph):
    """Enumerate connected typed matches. The event normalization uses distinct transitions."""
    adj = {i: set() for i in range(len(labels))}
    for i, j in edges:
        if i not in adj or j not in adj or i == j:
            raise ValueError("Invalid pattern edge")
        adj[i].add(j)
        adj[j].add(i)

    def extend(used):
        if len(used) == len(labels):
            yield tuple(used[i] for i in range(len(labels)))
            return
        if used:
            frontier = [i for i in adj if i not in used and adj[i] & used.keys()]
            if not frontier:
                raise ValueError("Disconnected site pattern")
            i = frontier[0]
            choices = set.intersection(*(graph[used[j]] for j in adj[i] & used.keys()))
        else:
            i, choices = 0, nodes.keys()
        for node in choices:
            if nodes[node] == labels[i] and node not in used.values():
                yield from extend({**used, i: node})

    yield from extend({})
