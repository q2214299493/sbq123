import copy

import pytest

from archive.fe110_five_c2_adsorption_20261006.chco_matris_diagnostic import compare


def fixture():
    labels = {"samples": [{"sample_id": "example", "structure_sha256": "a" * 64,
                          "symbols": ["Fe", "C", "O"], "fixed_atom_indices_1based": [1],
                          "label_stage": "final", "forces_eV_per_A": [[99, 99, 99], [0, 0, 0], [0, 0, 0]]}]}
    aq = {"samples": [{"sample_id": "example", "structure_sha256": "a" * 64,
                       "forces_eV_per_A": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}]}
    return labels, aq, copy.deepcopy(aq)


def test_equal_predictions_and_fixed_exclusion():
    result = compare(*fixture())
    assert result["aqcat25"] == result["matris"]
    assert result["matris"]["final/adsorbate"]["vector_rmse_eV_per_A"] == 1
    assert result["matris"]["all/all_movable"]["atom_vectors"] == 2


@pytest.mark.parametrize("mutation", ["hash", "duplicate", "nonfinite", "shape"])
def test_reject_unfair_or_invalid_comparison(mutation):
    labels, aq, matris = fixture()
    row = matris["samples"][0]
    if mutation == "hash":
        row["structure_sha256"] = "b" * 64
    elif mutation == "duplicate":
        matris["samples"].append(copy.deepcopy(row))
    elif mutation == "nonfinite":
        row["forces_eV_per_A"][1][0] = float("nan")
    else:
        row["forces_eV_per_A"].pop()
    with pytest.raises(ValueError):
        compare(labels, aq, matris)
