from __future__ import annotations

import itertools

import numpy as np
import pytest

from scripts.adsorption.reico_chemical_environments import (
    canonical_graph, chemical_environment, stratum_summary,
)
from scripts.adsorption.reico_stratified_audit import CachedSOAP, composition_soap
from tests.test_reico_environment_audit import slab


def test_graph_is_invariant_to_all_equal_element_permutations():
    symbols = ["C", "C", "C", "O", "H", "H"]
    edges = [(0, 1), (1, 2), (2, 3), (0, 4), (2, 5)]
    coordination = [1, 2, 3, 1, 0, 0]
    expected = canonical_graph(symbols, edges, coordination)
    for carbon in itertools.permutations(range(3)):
        for hydrogen in itertools.permutations((4, 5)):
            order = list(carbon)+[3]+list(hydrogen)
            mapping = {old: new for new, old in enumerate(order)}
            assert canonical_graph([symbols[i] for i in order], [(mapping[i], mapping[j]) for i,j in edges],
                                   [coordination[i] for i in order]) == expected


def test_joint_stratum_preserves_which_carbon_binds_Fe():
    symbols, edges = ["C"]*3, [(0, 1), (1, 2)]
    assert canonical_graph(symbols, edges, [0, 1, 1]) != canonical_graph(symbols, edges, [1, 0, 1])


def test_equal_bond_histograms_do_not_merge_different_topology():
    chain = [(0, 1), (1, 2), (2, 3)]
    star = [(0, 1), (0, 2), (0, 3)]
    assert canonical_graph(["C"]*3+["O"], chain) != canonical_graph(["C"]*3+["O"], star)


def test_known_geometry_contacts_and_periodic_invariance():
    atoms = slab()
    atoms.set_cell([300, 100, 50])
    atoms.positions[:45] = [[20+5*i, 20, 0] for i in range(45)]
    atoms.positions[44] = [10, 10, 10]
    atoms.positions[45:] = [[10,10,12], [11.4,10,12], [10,10,13.3], [9.2,10,12.5]]
    rules = {"covalent_radius_scale": 1.25, "minimum_bond_distance_angstrom": .35}
    first = chemical_environment(atoms, rules)
    assert first["coordination_by_element"] == {"C": [1, 1], "O": [0], "H": [0]}
    assert first["bond_counts"]["C-C"] == first["bond_counts"]["C-O"] == 1
    atoms.positions[45:, 0] += 300
    second = chemical_environment(atoms, rules)
    for key in ("graph_signature", "coordination_signature", "joint_signature"):
        assert first[key] == second[key]


def record(sid, family, vector, composition):
    vector = np.asarray(vector, dtype=float)
    return {"sample_id":sid,"family_id":family,"composition":composition,"partition":"train",
            "roles":np.array(["C"]),"vectors":(vector/np.linalg.norm(vector))[None,:]}


def test_cross_composition_match_cannot_hide_missing_environment():
    records = [record("a", "f1", [1,0], "C2HO"), record("b", "f2", [1,.1], "C2HO"),
               record("gap", "f3", [0,1], "C2HO"), record("c", "f4", [0,1], "C3H2O"),
               record("d", "f5", [.1,1], "C3H2O")]
    report, scores = composition_soap(records, {"a","b","c","d"}, .95)
    assert next(r for r in scores if r["sample_id"] == "gap")["novelty_ratio"] > 1
    assert report["C2HO"]["SOAP_gap_frames"] == 1
    assert report["C3H2O"]["SOAP_gap_frames"] == 0


@pytest.mark.parametrize("partition", ["development", "final_test", None])
def test_reserved_data_never_enters_stratified_soap(partition):
    row = record("reserved", "family", [1,0], "C2HO")
    row["partition"] = partition
    with pytest.raises(ValueError, match="training records only"):
        composition_soap([row], set(), .95)


def test_missing_strata_remain_visible_without_deleting_frames():
    rows = [{"sample_id":"selected","family_id":"f1","graph_signature":"A","novelty_ratio":0.},
            {"sample_id":"unseen","family_id":"f2","graph_signature":"B","novelty_ratio":.1},
            {"sample_id":"unseen2","family_id":"f3","graph_signature":"B","novelty_ratio":.2}]
    result = stratum_summary(rows, {"selected"}, "graph_signature")
    assert result["missing_strata"] == 1 and result["frames_in_missing_strata"] == 2
    assert sum(r["pool_frames"] for r in result["strata"]) == len(rows)
    assert result["strata"][1]["representative_id"] == "unseen2"
    assert len(rows) == 3


def test_missing_cache_never_invokes_a_new_descriptor_calculation():
    with pytest.raises(ValueError, match="never recomputes SOAP"):
        CachedSOAP(544).create(None)
