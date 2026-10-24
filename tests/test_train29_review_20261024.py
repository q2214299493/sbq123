"""Guard the incremental train-only scope against lost or reserved samples."""
from __future__ import annotations

import pytest

from archive.fe110_train29_review_20261024.inspect import remaining_rows


def checkpoint():
    rows = [{"name": f"sample{i:02}"} for i in range(45)]
    previous = [{"sample_id": row["name"]} for row in rows[:16]]
    selected = {row["name"]: {"partition": "train"} for row in rows}
    return rows, previous, selected


def test_only_remaining29_are_retained_after_previous16():
    rows, previous, selected = checkpoint()
    assert remaining_rows(rows, previous, selected) == rows[16:]


def test_reserved_partition_cannot_enter_recovery_scope():
    rows, previous, selected = checkpoint()
    selected[rows[-1]["name"]]["partition"] = "final_test"
    with pytest.raises(ValueError, match="train-only"):
        remaining_rows(rows, previous, selected)


def test_missing_or_duplicate_submission_is_not_silently_accepted():
    rows, previous, selected = checkpoint()
    for altered in (rows[:-1], rows + [rows[-1]]):
        with pytest.raises(ValueError, match="scope changed"):
            remaining_rows(altered, previous, selected)


def test_duplicate_previous_review_blocks_incremental_merge():
    rows, previous, selected = checkpoint()
    with pytest.raises(ValueError, match="duplicate previously"):
        remaining_rows(rows, previous + previous[:1], selected)
