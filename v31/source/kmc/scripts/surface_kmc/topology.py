"""Bind native site numbers and edges to the reviewed inventories and contacts."""

from collections import Counter
from math import prod

from scripts.native_inputs import integer, token
from scripts.scientific_validation import finite_number
from scripts.surface_kmc.lattice import explicit_lines, lattice


def _open_graph(c, explicit, sites):
    if explicit["boundary"] != "finite_open" or any(
        k in c for k in ("repeat_cell", "cell_vectors_A", "cell_sites", "links", "reference_sites_per_cell")
    ):
        raise ValueError("Explicit open graph has incompatible boundary or periodic fields")
    rows = explicit["nodes"]
    ids = [r["node_id"] for r in rows]
    if not rows or len(ids) != len(set(ids)) or any(not isinstance(i, str) or not i.strip() for i in ids):
        raise ValueError("Invalid or duplicate physical node ID")
    order = list(range(1, len(rows) + 1))
    indices = dict(zip(ids, order, strict=True))
    nodes = {i: row["inventory_id"] for i, row in zip(order, rows, strict=True)}
    if set(nodes.values()) != set(sites) or c["site_aliases"].keys() != sites.keys():
        raise ValueError("Explicit inventories differ from catalog")
    xy = [r["drawing_xy_angstrom"] for r in rows]
    type_order = sorted(c["site_aliases"])
    aliases = [token(v).lower() for v in c["site_aliases"].values()]
    if len(aliases) != len(set(aliases)):
        raise ValueError("Duplicate native site alias")
    graph = {i: set() for i in order}
    contacts = {}
    for left, right, contact in explicit["edges"]:
        if left not in indices or right not in indices:
            raise ValueError("Unknown physical edge endpoint")
        i, j = indices[left], indices[right]
        if i == j or j in graph[i]:
            raise ValueError("Self or duplicate physical edge")
        graph[i].add(j)
        graph[j].add(i)
        contacts[min(i, j), max(i, j)] = contact
    lines = explicit_lines(
        [dict(r, index=i) for r, i in zip(rows, order, strict=True)],
        graph,
        c["site_aliases"],
        sorted(c["site_aliases"]),
    )
    return lines, nodes, graph, order, ids, xy, type_order, contacts


def topology(c, catalog):
    sites = {s["site_id"]: s["surface_id"] for s in catalog["sites"]}
    phases = {s["surface_id"]: s["phase_id"] for s in catalog["surfaces"]}
    interfaces = {i["interface_id"]: set(i["surface_ids"]) for i in catalog["interfaces"]}
    explicit = c.get("explicit_graph")
    if explicit is None:
        lines, nodes, graph = lattice(c, set(sites))
        order = sorted(nodes)
        ids = [":".join(map(str, key)) for key in order]
        (ax, ay), (bx, by) = c["cell_vectors_A"]
        xy = []
        for x, y, i in order:
            _, u, v = c["cell_sites"][i - 1]
            xy.append([(x + u) * ax + (y + v) * bx, (x + u) * ay + (y + v) * by])
        type_order = list(dict.fromkeys(s for s, _, _ in c["cell_sites"]))
        contacts = {}
    else:
        lines, nodes, graph, order, ids, xy, type_order, contacts = _open_graph(c, explicit, sites)
    index = {node: i for i, node in enumerate(order, 1)}
    ledger = [
        dict(
            index=index[n],
            node_id=key,
            inventory_id=nodes[n],
            surface_id=sites[nodes[n]],
            phase_id=phases[sites[nodes[n]]],
            xy_angstrom=xy[index[n] - 1],
            type_index=type_order.index(nodes[n]) + 1,
        )
        for n, key in zip(order, ids, strict=True)
    ]
    edges = []
    for n in order:
        for m in sorted(graph[n]):
            i, j = index[n], index[m]
            if j <= i:
                continue
            surfaces = {sites[nodes[n]], sites[nodes[m]]}
            possible = [k for k, members in interfaces.items() if surfaces <= members]
            contact = contacts.get((i, j))
            if len(surfaces) > 1:
                if explicit is None and len(possible) == 1:
                    contact = possible[0]
                if contact not in possible:
                    raise ValueError("Unknown or ambiguous physical interface")
            elif contact is not None:
                raise ValueError("Unexpected contact on same-surface edge")
            edges.append([i, j, contact])
    vectors = []
    if explicit is None:
        vectors = [
            [component * repeat for component in vector]
            for vector, repeat in zip(c["cell_vectors_A"], c["repeat_cell"], strict=True)
        ]
    return (
        lines,
        nodes,
        graph,
        dict(nodes=ledger, edges=edges, cell_vectors_A=vectors, capacities=dict(Counter(nodes.values()))),
    )


def reference_size(c):
    if "explicit_graph" in c:
        return integer(c["reference_sites"], "reference sites")
    return prod(c["repeat_cell"]) * finite_number(
        c["reference_sites_per_cell"], "reference sites", positive=True
    )
