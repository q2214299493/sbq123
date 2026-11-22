"""Cross-check a finite bridge graph against Zacros text, typed embeddings and exhaustive packing."""
from itertools import combinations
import json
from pathlib import Path

import pytest

from scripts.multiphase_contracts import read_unique_json
from scripts.surface_kmc.bridge_topology import analyze, maximum_matching, read_audit
from scripts.surface_kmc.lattice import embeddings


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "tests/fixtures/multiphase/synthetic_oxide_bridge_graph.json"
REPORT = ROOT / "reports/multiphase/stage_b2_3_2_2/mapping.json"


@pytest.fixture
def inputs():
    graph = read_unique_json(GRAPH)
    return (graph, *(read_unique_json(ROOT / graph["sources"][key]["path"])
                     for key in ("definition", "observation")))


def largest_pack(pairs):
    """Independent small-graph oracle: try subsets in decreasing cardinality."""
    for size in range(len(pairs), 0, -1):
        for subset in combinations(pairs, size):
            if len({n for pair in subset for n in pair}) == 2 * size:
                return size
    return 0


def crosscheck(report):
    candidate = report["zacros_candidate"]
    lines = candidate["lattice_input_lines"]
    assert lines[0] == "lattice explicit" and not any("cell_vectors" in line for line in lines)
    types, neighbors = {}, {}
    for line in lines[lines.index("lattice_structure") + 1:lines.index("end_lattice_structure")]:
        index, x, y, site, degree, *links = line.split()
        assert len(links) == int(degree)
        types[int(index)] = site
        neighbors[int(index)] = set(map(int, links))
    assert f"n_sites {len(types)}" in lines
    assert f"max_coord {max(map(len, neighbors.values()))}" in lines
    assert all(i in neighbors[j] for i, row in neighbors.items() for j in row)
    assert report["adjacency_matrix"] == [[int(j in neighbors[i]) for j in sorted(types)] for i in sorted(types)]
    labels = candidate["event_header"][1].split()[1:]
    assert "neighboring 1-2" in candidate["event_header"]
    pairs = set(embeddings(labels, [(0, 1)], types, neighbors))
    seeded = {tuple(map(int, line.split()[2:])) for line in candidate["state_input_lines"][1:-1]}
    occupied = {i for pair in seeded for i in pair}
    free = {p for p in pairs if occupied.isdisjoint(p)}
    assert seeded <= pairs and len(occupied) == 2 * len(seeded)
    assert pairs == {tuple(r["leg_nodes"]) for r in report["edges"]}
    assert free == {tuple(r["leg_nodes"]) for r in report["edges"] if r["adsorption_match"]}
    assert seeded == {tuple(r["leg_nodes"]) for r in report["edges"] if r["desorption_match"]}
    assert (len(pairs), len(free), len(seeded)) == (
        report["empty_lattice_matches"], report["available_adsorptions"], report["initial_desorption_patterns"])
    for pool, witness in [(pairs, report["maximum_witness"]), (free, report["additional_matching_with_seeds_fixed"])]:
        assert set(map(tuple, witness)) <= pool
        assert len({n for pair in witness for n in pair}) == 2 * len(witness)
        assert len(witness) == largest_pack(pool)
    assert len(report["maximum_witness"]) == report["maximum_simultaneous_bridges"]


def test_archived_graph_result_and_entity_semantics():
    report = read_audit(GRAPH, ROOT)
    assert json.loads(json.dumps(report)) == read_unique_json(REPORT)
    crosscheck(report)
    assert report["connected"] and report["boundary"] == "finite_open"
    assert report["empty_lattice_matches"] == 6 and report["available_adsorptions"] == 2
    assert report["maximum_simultaneous_bridges"] == 3
    assert report["inventories"] == {"acid-A": {"capacity": 4, "occupied": 2, "vacant": 2},
                                     "oxygen-B": {"capacity": 3, "occupied": 2, "vacant": 1}}
    different_entities = next(r for r in report["edges"] if r["leg_nodes"] == [2, 5])
    assert different_entities["initial_entities"] == ["bridge-2", "bridge-1"]
    assert not different_entities["adsorption_match"] and not different_entities["desorption_match"]
    c = report["zacros_candidate"]
    assert c["surface_species"]["surf_specs_dent"] == 2
    assert c["adsorption"]["final"] == c["desorption_pattern"]["initial"] == ["1 CO2bridge* 1", "1 CO2bridge* 2"]
    assert c["source_reversible"] is c["execution_plan"] is None and c["native_acceptance"] == "unverified"


def test_alternative_connected_graph_with_identical_nodes_and_seeds(inputs):
    graph, definition, obs = inputs
    graph["edges"].remove(["acid-4", "oxygen-3"])
    graph["edges"].extend([["acid-4", "oxygen-1"], ["acid-1", "oxygen-2"]])
    result = analyze(graph, definition, obs)
    crosscheck(result)
    assert result["connected"] and result["empty_lattice_matches"] == 7
    assert [r["leg_nodes"] for r in result["edges"] if r["adsorption_match"]] == [[3, 7]]


def test_disconnected_lattice_and_same_type_bond_do_not_add_bridge_events(inputs):
    graph, definition, obs = inputs
    graph["edges"] = [["acid-1", "oxygen-1"], ["acid-2", "oxygen-2"], ["acid-3", "acid-4"]]
    report = analyze(graph, definition, obs)
    crosscheck(report)
    assert not report["connected"]
    assert report["maximum_simultaneous_bridges"] == 2
    assert report["available_adsorptions"] == 0


def test_compatible_initial_bridges_can_prevent_reaching_global_maximum(inputs):
    graph, definition, obs = inputs
    graph["initial_bridges"][0]["leg_nodes"] = ["acid-2", "oxygen-1"]
    graph["initial_bridges"][1]["leg_nodes"] = ["acid-3", "oxygen-3"]
    result = analyze(graph, definition, obs)
    crosscheck(result)
    assert result["initial_desorption_patterns"] == 2
    assert result["additional_matching_with_seeds_fixed"] == []
    assert result["maximum_simultaneous_bridges"] == 3


def test_maximum_matching_can_reassign_an_earlier_bridge():
    assert maximum_matching([(1, 3), (1, 4), (2, 3)]) == [(1, 4), (2, 3)]


@pytest.mark.parametrize(("mutation", "message"), [
    ("duplicate", "duplicate undirected edge"), ("reverse_duplicate", "duplicate undirected edge"),
    ("loop", "Self-loop"), ("missing_node", "physical inventory node"), ("unknown_endpoint", "Unknown edge"),
    ("wrong_type", "physical inventory node"), ("reverse_legs", "leg order"), ("non_edge", "adjacent pair"),
    ("overlap", "share a physical node"), ("duplicate_entity", "entity ID"), ("periodic", "open boundaries"),
])
def test_invalid_graph_or_initial_state(inputs, mutation, message):
    graph, definition, obs = inputs
    if mutation in {"duplicate", "reverse_duplicate", "loop", "unknown_endpoint"}:
        graph["edges"].append({"duplicate": ["acid-1", "oxygen-1"], "reverse_duplicate": ["oxygen-1", "acid-1"],
                               "loop": ["acid-1", "acid-1"], "unknown_endpoint": ["acid-1", "absent"]}[mutation])
    elif mutation == "missing_node":
        graph["nodes"].pop()
    elif mutation == "wrong_type":
        graph["nodes"][0]["inventory_id"] = "oxygen-B"
    elif mutation == "duplicate_entity":
        graph["initial_bridges"][1]["entity_id"] = "bridge-1"
    elif mutation == "periodic":
        graph["boundary"] = "periodic"
    else:
        graph["initial_bridges"][1]["leg_nodes"] = {
            "reverse_legs": ["oxygen-2", "acid-2"], "non_edge": ["acid-2", "oxygen-3"],
            "overlap": ["acid-2", "oxygen-1"]}[mutation]
    with pytest.raises(ValueError, match=message):
        analyze(graph, definition, obs)


def test_permutation_node_renaming_and_native_renumbering(inputs):
    graph, definition, obs = inputs
    original = analyze(graph, definition, obs)
    for key in ("nodes", "edges", "initial_bridges"):
        graph[key].reverse()
    for edge in graph["edges"]:
        edge.reverse()
    assert analyze(graph, definition, obs) == original
    renaming = {n["node_id"]: f"node-{8 - n['index']}" for n in graph["nodes"]}
    for n in graph["nodes"]:
        n["node_id"] = renaming[n["node_id"]]
        n["index"] = 8 - n["index"]
    for edge in graph["edges"]:
        edge[:] = [renaming[n] for n in edge]
    for entity in graph["initial_bridges"]:
        entity["leg_nodes"] = [renaming[n] for n in entity["leg_nodes"]]
    for site in obs["sites"]:
        site["physical_site_ids"] = [renaming[n] for n in site["physical_site_ids"]]
    result = analyze(graph, definition, obs)
    crosscheck(result)

    def signatures(report, lookup):
        return {(tuple(map(lookup, r["leg_nodes"])), r["adsorption_match"], r["desorption_match"])
                for r in report["edges"]}

    assert signatures(result, lambda i: 8 - i) == signatures(original, lambda i: i)
    assert result["maximum_simultaneous_bridges"] == original["maximum_simultaneous_bridges"]


def test_changed_source_bytes_are_rejected(inputs, tmp_path):
    graph, _, _ = inputs
    graph["sources"]["observation"]["sha256"] = "0" * 64
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf8")
    with pytest.raises(ValueError, match="Source digest differs for observation"):
        read_audit(path, ROOT)
