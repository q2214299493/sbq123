"""Synthetic selection tests; no DFT, network, model or production data."""
from __future__ import annotations

import copy

import pytest

from scripts.adsorption.reico_probe_batch import select_probes


@pytest.fixture
def records():
    rows = []
    for composition in ("C2HO", "C2H2O", "C2H3", "C3H2O"):
        for i in range(11):
            rows.append({"family_id": f"{composition}_{i:02d}", "composition": composition, "partition": "train",
                         "status": "CPU_GEOMETRY_CANDIDATE", "geometry_audit": {"pair_minima_A": {"C-Fe": 1.6 + i / 10}}})
    return rows


def test_balanced_six_are_deterministic_geometry_quantiles(records):
    result = select_probes(records, {"C-Fe": 1.6})
    assert [r["family_id"] for r in result] == ["C2HO_05", "C2H2O_05", "C2H3_05", "C3H2O_01", "C3H2O_05", "C3H2O_09"]
    assert select_probes(list(reversed(records)), {"C-Fe": 1.6}) == result


def test_heldout_or_failed_families_cannot_change_selection(records):
    original = select_probes(records, {"C-Fe": 1.6})
    extra = []
    for row in records:
        for partition in ("development", "final_test"):
            new = copy.deepcopy(row)
            new.update(family_id=f"heldout_{partition}_{row['family_id']}", partition=partition)
            new["geometry_audit"]["pair_minima_A"]["C-Fe"] = 0.1
            extra.append(new)
    assert select_probes(records + extra, {"C-Fe": 1.6}) == original


def test_missing_composition_or_three_C3_families_fails_without_padding(records):
    reduced = [r for r in records if r["composition"] != "C2H3"]
    with pytest.raises(ValueError, match="insufficient"):
        select_probes(reduced, {"C-Fe": 1.6})
    reduced = [r for r in records if r["composition"] != "C3H2O" or r["family_id"].endswith(("00", "01"))]
    with pytest.raises(ValueError, match="insufficient"):
        select_probes(reduced, {"C-Fe": 1.6})


@pytest.mark.parametrize("distance", [0.9, float("nan"), float("inf"), -1])
def test_invalid_or_guard_violating_descriptors_block_selection(records, distance):
    records[0]["geometry_audit"]["pair_minima_A"]["C-Fe"] = distance
    with pytest.raises(ValueError):
        select_probes(records, {"C-Fe": 1.6})
