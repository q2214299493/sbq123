"""Offline controls for the physical site graph and the Ni/Cu interface crosswalk."""
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.surface_kmc.lattice import embeddings


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/multiphase"


@pytest.mark.parametrize(
    ("extra_edges", "all_pairs", "vacant_pairs"),
    [
        ([(4, 7)], 6, {(3, 7), (4, 7)}),
        ([(4, 5), (1, 6)], 7, {(3, 7)}),
    ],
)
def test_same_oxide_counts_allow_different_event_matches(extra_edges, all_pairs, vacant_pairs):
    observation = json.loads((REPORTS / "stage_b2_1/oxide_observations.json").read_bytes())
    inventory = {s["site_id"]: len(s["physical_site_ids"]) for s in observation["sites"]}
    assert inventory == {"acid-A": 4, "oxygen-B": 3}
    assert observation["species"][0]["coverage"] == 2

    # Two hypothetical graphs, each with the same two seeded bridges. No geometry is assigned to the fixture.
    nodes = {i: "acid-A" if i <= 4 else "oxygen-B" for i in range(1, 8)}
    edges = [(1, 5), (2, 5), (2, 6), (3, 6), (3, 7), *extra_edges]
    graph = {i: set() for i in nodes}
    for acid, oxygen in edges:
        graph[acid].add(oxygen)
        graph[oxygen].add(acid)
    pairs = set(embeddings(["acid-A", "oxygen-B"], [(0, 1)], nodes, graph))
    seeds = {(1, 5), (2, 6)}
    assert seeds <= pairs
    occupied = {site for pair in seeds for site in pair}
    assert len(pairs) == all_pairs
    assert {pair for pair in pairs if occupied.isdisjoint(pair)} == vacant_pairs


def test_archived_interface_identity_matches_one_two_leg_entity():
    with ZipFile(REPORTS / "phase2_5_1/benchmarks/dent.zip") as archive:
        dataset = json.loads(archive.read("dataset.json"))
        manifest = json.loads(archive.read("manifest.json"))
        mechanism = archive.read("mechanism_input.dat").decode("ascii").splitlines()
        state = archive.read("state_input.dat").decode("ascii").splitlines()
    bridge = next(s for s in dataset["species"] if s["species_id"] == "H2-bridge")
    assert bridge["interface_id"] == dataset["reactions"][0]["interface_id"] == "junction"
    sites = {s["site_id"]: s["surface_id"] for s in dataset["catalog"]["sites"]}
    assert {sites[site] for site in bridge["site_occupancy"]} == set(bridge["surface_ids"])
    assert bridge["site_occupancy"] == {"top-Ni": 1, "bridge-Cu": 1}
    alias = manifest["validation"]["species_names"][bridge["species_id"]]
    for step, side in [("step r1_forward", "final"), ("step r2_reverse", "initial")]:
        start = mechanism.index(step)
        block = mechanism[start:mechanism.index("end_step", start)]
        assert "site_types Ni Cu" in block and "neighboring 1-2" in block
        first = block.index(side) + 1
        assert block[first:first + 2] == [f"1 {alias} 1", f"1 {alias} 2"]
    assert f"seed_on_sites {alias} 1 2" in state
