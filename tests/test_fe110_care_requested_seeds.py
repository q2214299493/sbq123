"""Explicit seed selection guards; no model or scientific calculation is run."""
from copy import deepcopy

import numpy as np
import pytest

from scripts.adsorption import build_fe110_care_batch as batch
from scripts.adsorption.build_fe110_adsorption import Poscar


@pytest.fixture
def requested_inputs(monkeypatch):
    cell = np.diag([10., 10., 25.])
    ads = np.array([[4., 4., 8.], [5.4, 4., 8.],
                    [3.45, 4.95, 8.], [5.95, 3.05, 8.]])
    pose = Poscar("selector fixture", cell, ["Fe", "C", "H"], [45, 2, 2],
                  np.vstack((np.zeros((45, 3)), ads @ np.linalg.inv(cell))),
                  [("F", "F", "F")] * 18 + [("T", "T", "T")] * 31)
    originals = []
    for config in ("0", "1", "2"):
        coords = pose.frac.copy()
        coords[45:, 0] += .1 * int(config)
        current = Poscar(pose.comment, cell, pose.symbols, pose.counts, coords, pose.flags)
        originals.append(({}, config, current, current,
                          {"source_config": config, "origin": "LOCAL_CARE_POSE_TRANSFER"}, ""))
    target = {"id": "fixture", "signature": batch.molecular_signature(pose),
              "seed_recipes": [{"source_config": config, "label": config,
                                "selection_basis": "selector test"}
                               for config in ("2", "0", "1")]}
    # The selector's guards are tested separately from the real geometry owner.
    monkeypatch.setattr(batch, "review", lambda *args: {"verdict": "pass", "checks": {}})
    return target, originals, pose, {"top": object()}, [(np.eye(3), np.zeros(3))], .2


def test_explicit_source_order_is_preserved(requested_inputs):
    selected = batch.requested_seeds(*requested_inputs)
    assert [metadata["source_config"] for _, metadata in selected] == ["2", "0", "1"]


@pytest.mark.parametrize("mutation,match", [
    ("count", "three recipes"),
    ("missing", "missing requested source"),
    ("duplicate", "near duplicate"),
    ("identity", "geometry/identity"),
])
def test_invalid_explicit_plan_is_rejected(requested_inputs, mutation, match):
    values = list(requested_inputs)
    target = deepcopy(values[0])
    values[0] = target
    if mutation == "count":
        target["seed_recipes"].pop()
    elif mutation == "missing":
        target["seed_recipes"][0]["source_config"] = "missing"
    elif mutation == "duplicate":
        target["seed_recipes"][1]["source_config"] = "2"
    else:
        target["signature"] = [["C", 0, ["C"]], ["C", 2, ["C"]]]
    with pytest.raises(ValueError, match=match):
        batch.requested_seeds(*values)


@pytest.mark.parametrize("anchor,hydrogens,match", [
    (2, 1, "bonded heavy atoms"),
    (0, 0, "hydrogen count"),
])
def test_anchor_graph_role_is_checked(requested_inputs, anchor, hydrogens, match):
    values = list(requested_inputs)
    values[0] = deepcopy(values[0])
    values[0]["seed_recipes"][0]["placement"] = {
        "anchor_local_0based": anchor, "axis_to_local_0based": 1,
        "anchor_H_count": hydrogens,
    }
    with pytest.raises(ValueError, match=match):
        batch.requested_seeds(*values)


def test_display_unwraps_connected_branches_beyond_half_a_cell():
    cell = np.diag([6., 10., 25.])
    ads = np.array([[.1, 4., 8.], [2.9, 4., 8.], [1.5, 4., 8.],
                    [3.4, 4.95, 8.], [3.8, 3.5, 8.]])
    pose = Poscar("periodic branch", cell, ["Fe", "C", "O", "H"], [45, 2, 1, 2],
                  np.vstack((np.zeros((45, 3)), ads @ np.linalg.inv(cell))),
                  [("F", "F", "F")] * 18 + [("T", "T", "T")] * 32)
    actual = batch.display_coordinates(pose)[45:]
    assert np.allclose(actual, ads - ads[0])
    for first, second in batch.connectivity(pose, list(range(45, 50))):
        assert np.linalg.norm(actual[first] - actual[second]) < 1.9
