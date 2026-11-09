"""Reject unsafe admission evidence without launching any scientific process."""
import copy

import pytest

from archive.fe110_c3_lowforce_candidates_20261109.assess_admission import eligibility


def candidates():
    base = {"split": "train", "partition": "train", "calculation_group": "reico_family_0099",
            "electronic_converged": True, "geometry_review_pass": True, "magnetic_review_flags": [],
            "magnetic_review_level": "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE",
            "forces_eV_per_A": [[0., 0., 0.]] * 50 + [[.03, 0., 0.]], "movable_fmax_eV_A": .03}
    return [{**copy.deepcopy(base), "sample_id": str(i)} for i in range(24)]


def test_valid_force_candidates_do_not_require_manufactured_done():
    eligibility(candidates())


@pytest.mark.parametrize("field,value", [("split", "heldout"), ("electronic_converged", False),
    ("magnetic_review_flags", ["unreviewed"]), ("magnetic_review_level", "LEGACY_TOTAL_MAGNETIZATION_ONLY"),
    ("movable_fmax_eV_A", .01)])
def test_unsafe_candidate_is_rejected(field, value):
    rows = candidates()
    rows[0][field] = value
    with pytest.raises(ValueError):
        eligibility(rows)


def test_duplicate_candidate_identity_is_rejected():
    rows = candidates()
    rows[1]["sample_id"] = rows[0]["sample_id"]
    with pytest.raises(ValueError, match="unique"):
        eligibility(rows)
