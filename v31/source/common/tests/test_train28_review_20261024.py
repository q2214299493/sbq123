"""Do not count a previously covered environment again when a sibling finishes."""
from archive.fe110_train28_review_20261024.finalize import gap_contributions


def test_completed_sibling_of_prior_candidate_is_not_an_additional_type():
    old = {"unreviewed_selected_input_ids": ["old", "sibling"]}
    new = {"unreviewed_selected_input_ids": ["new"]}
    missing = {"unreviewed_selected_input_ids": ["pending"]}
    covered, remaining, prior = gap_contributions([old, new, missing], {"old"}, {"sibling", "new"})
    assert covered == [new] and remaining == [missing] and prior == [old]


def test_multiple_new_frames_of_one_type_remain_one_contribution():
    group = {"unreviewed_selected_input_ids": ["a", "b"]}
    assert gap_contributions([group], set(), {"a", "b"}) == ([group], [], [])


def test_no_eligible_labels_preserves_every_remaining_gap():
    group = {"unreviewed_selected_input_ids": ["a"]}
    assert gap_contributions([group], set(), set()) == ([], [group], [])
