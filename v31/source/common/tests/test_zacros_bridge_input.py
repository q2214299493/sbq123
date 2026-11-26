"""Offline readback of the shipped Zacros candidate. No engine invocation."""
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.artifact_io import sha256_bytes
from scripts.surface_kmc.bridge_input import build_candidate

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "tests/fixtures/multiphase/synthetic_oxide_bridge_graph.json"
MAPPING = ROOT / "reports/multiphase/stage_b2_3_2_2/mapping.json"
DELIVERY = ROOT / "reports/multiphase/stage_b2_3_2_3/native"


def read_lattice():
    lines = (DELIVERY / "lattice_input.dat").read_text().splitlines()
    assert lines[0] == "lattice explicit" and not any(line.startswith("cell_vectors") for line in lines)
    rows = lines[lines.index("lattice_structure") + 1:lines.index("end_lattice_structure")]
    site_types, adjacency = {}, {}
    for row in rows:
        node, _, _, site_type, degree, *neighbors = row.split()
        assert int(node) not in site_types and int(degree) == len(set(neighbors)) == len(neighbors)
        site_types[int(node)] = site_type
        adjacency[int(node)] = set(map(int, neighbors))
    assert all(i in adjacency[j] for i, ns in adjacency.items() for j in ns)
    pairs = {(i, j) for i, ns in adjacency.items() for j in ns if site_types[i] == "acidA"}
    assert all(site_types[j] == "oxygenB" for _, j in pairs)
    return site_types, pairs


def read_seeds():
    lines = (DELIVERY / "state_input.dat").read_text().splitlines()
    seeds = []
    for line in lines[1:-1]:
        keyword, species, first, second = line.split()
        assert keyword == "seed_on_sites" and species == "CO2bridge*"
        seeds.append((int(first), int(second)))
    return seeds


def read_events():
    text = (DELIVERY / "mechanism_input.dat.in").read_text()
    events = {}
    for block in text.split("\nstep ")[1:]:
        lines = block.split("\nend_step")[0].splitlines()
        assert "sites 2" in lines and "site_types acidA oxygenB" in lines and "neighboring 1-2" in lines
        initial, final = lines.index("initial"), lines.index("final")
        events[lines[0]] = (lines[initial + 1:initial + 3], lines[final + 1:final + 3],
                             next(line for line in lines if line.startswith("gas_reacs_prods")))
    return events


def matches(pattern, pair, state):
    """Map local entity labels bijectively to physical entities, including distinct vacancies."""
    entity_map = {}
    for slot, site in zip(pattern, pair, strict=True):
        local_id, species, leg = slot.split()
        physical_id, actual_species, actual_leg = state.get(site, (("vacancy", site), "*", 1))
        if (species, int(leg)) != (actual_species, actual_leg):
            return False
        if entity_map.setdefault(local_id, physical_id) != physical_id:
            return False
    return len(set(entity_map.values())) == len(entity_map)


def test_shipped_native_bytes_and_source_bindings(tmp_path):
    files, manifest = build_candidate(GRAPH, MAPPING, ROOT)
    assert set(p.name for p in DELIVERY.iterdir()) == {*files, "input_manifest.json"}
    assert manifest == json.loads((DELIVERY / "input_manifest.json").read_bytes())
    assert manifest["graph_sha256"] == sha256_bytes(GRAPH.read_bytes())
    assert manifest["mapping_sha256"] == sha256_bytes(MAPPING.read_bytes())
    for name, raw in files.items():
        assert raw == (DELIVERY / name).read_bytes() and b"\r" not in raw
        assert manifest["files_sha256"][name] == sha256_bytes(raw)
    out = tmp_path / "review"
    args = [sys.executable, "-m", "scripts.surface_kmc.bridge_input", GRAPH, MAPPING, out]
    subprocess.run(args, cwd=ROOT, capture_output=True, check=True)
    assert all((out / f.name).read_bytes() == f.read_bytes() for f in DELIVERY.iterdir())
    assert subprocess.run(args, cwd=ROOT, capture_output=True).returncode != 0
    assert all((out / f.name).read_bytes() == f.read_bytes() for f in DELIVERY.iterdir())


def test_templates_hold_only_unbound_rates_and_zero_event_controls():
    files, manifest = build_candidate(GRAPH, MAPPING, ROOT)
    assert manifest["native_run_eligible"] is False and manifest["source_reversible"] is None
    assert sorted(manifest["complete_native_members"]) == ["lattice_input.dat", "state_input.dat"]
    assert all(b"@" in files[k] and k.endswith(".dat.in") for k in manifest["templates_require_binding"])
    settings = files["simulation_input.dat.in"].decode().splitlines()
    assert {"temperature @TEMPERATURE_K@", "pressure @TOTAL_PRESSURE_BAR@", "surf_specs_dent 2",
            "debug_report_processes", "max_steps 0"} <= set(settings)
    assert "no_restart" not in settings
    lines = files["mechanism_input.dat.in"].decode().splitlines()
    for name in ("ADSORPTION", "DESORPTION"):
        assert f"pre_expon @{name}_PRE_EXPON@" in lines and f"activ_eng @{name}_EA_EV@" in lines


def test_entities_directions_maximum_and_inventory_updates():
    types, pairs = read_lattice()
    assert Counter(types.values()) == {"acidA": 4, "oxygenB": 3}
    assert pairs == {(1, 5), (2, 5), (2, 6), (3, 6), (3, 7), (4, 7)}
    seeds = read_seeds()
    assert seeds == [(1, 5), (2, 6)]
    state = {site: (entity, "CO2bridge*", leg) for entity, seed in enumerate(seeds)
             for leg, site in enumerate(seed, 1)}
    events = read_events()
    assert set(events) == {"adsorption", "desorption"}
    vacant, bound, gas = events["adsorption"]
    assert events["desorption"] == (bound, vacant, "gas_reacs_prods CO2 1") and gas == "gas_reacs_prods CO2 -1"
    assert {pair for pair in pairs if matches(vacant, pair, state)} == {(3, 7), (4, 7)}
    assert {pair for pair in pairs if matches(bound, pair, state)} == {(1, 5), (2, 6)}
    assert not matches(bound, (2, 5), state)
    # Negative control: exchange the legs of only the first seed.
    flipped = {**state, 1: state[5], 5: state[1]}
    assert {pair for pair in pairs if matches(bound, pair, flipped)} == {(2, 6)}
    packs = [subset for n in range(len(pairs) + 1) for subset in combinations(pairs, n)
             if len({i for edge in subset for i in edge}) == 2 * n]
    assert max(map(len, packs)) == 3
    for placement in packs:
        used = {node for edge in placement for node in edge}
        empty = Counter(types[node] for node in types.keys() - used)
        assert (empty["acidA"], empty["oxygenB"]) == (4 - len(placement), 3 - len(placement))
    for edge in [(3, 7), (4, 7)]:
        filled = {**state, edge[0]: (2, "CO2bridge*", 1), edge[1]: (2, "CO2bridge*", 2)}
        assert not any(matches(vacant, p, filled) for p in pairs)
        assert {p for p in pairs if matches(bound, p, filled)} == {*seeds, edge}
        assert {i: v for i, v in filled.items() if v[0] != 2} == state


def test_stale_mapping_rejected_before_writing(tmp_path):
    mapping = json.loads(MAPPING.read_bytes())
    mapping["zacros_candidate"]["state_input_lines"][1] = "seed_on_sites CO2bridge* 5 1"
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps(mapping))
    with pytest.raises(ValueError, match="Archived mapping differs"):
        build_candidate(GRAPH, stale, ROOT)
