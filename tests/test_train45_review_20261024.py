from __future__ import annotations

import pytest

from archive.fe110_train45_review_20261024.process_main import prioritized_done


def test_gap_representatives_first_without_dropping_similar_completed_labels():
    jobs = [{"name": "a1", "status": "DONE"}, {"name": "a2", "status": "DONE"},
            {"name": "b1", "status": "DONE"}, {"name": "c1", "status": "RUN"},
            {"name": "d1", "status": "PEND"}]
    groups = [{"unreviewed_selected_input_ids": ["a1", "a2"]},
              {"unreviewed_selected_input_ids": ["b1"]},
              {"unreviewed_selected_input_ids": ["c1"]}]
    assert [r["name"] for r in prioritized_done(jobs, groups)] == ["a1", "b1", "a2"]


def test_duplicate_completed_sample_not_silently_collapsed():
    with pytest.raises(ValueError, match="duplicate"):
        prioritized_done([{"name": "a", "status": "DONE"}] * 2, [])
