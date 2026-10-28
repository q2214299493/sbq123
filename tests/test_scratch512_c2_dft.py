"""A C2 benchmark must not silently accept fragmented or duplicated sources."""
import copy

import pytest

from archive.fe110_scratch512_20261028.prepare_c2_dft import reviewed_c2


def rows():
    return [{"name": "10_A", "model": model, "composition": "C2H3", "geometry_eligible_for_DFT_review": True,
        "chemical_classification": "INITIAL_GRAPH_RETAINED"} for model in ["nequip", "finetune"]]


def test_c3_diagnostic_stays_outside_c2_three_arm_input_scope():
    candidates = rows()
    extra = copy.deepcopy(candidates[0])
    extra.update(name="C3_05", composition="C3H2O", chemical_classification="FRAGMENTED")
    selected = reviewed_c2(candidates + [extra])
    assert set(selected) == {"nequip", "finetune"}
    assert all(row["composition"] == "C2H3" for row in selected.values())


@pytest.mark.parametrize("change", ["duplicate", "missing", "composition", "geometry", "chemistry"])
def test_invalid_candidate_provenance_blocks_before_inputs_are_built(change):
    candidates = rows()
    if change == "duplicate":
        candidates.append(copy.deepcopy(candidates[0]))
    elif change == "missing":
        candidates.pop()
    elif change == "composition":
        candidates[0]["composition"] = "C3H2O"
    elif change == "geometry":
        candidates[1]["geometry_eligible_for_DFT_review"] = False
    else:
        candidates[0]["chemical_classification"] = "FRAGMENTED"
    with pytest.raises(ValueError):
        reviewed_c2(candidates)
