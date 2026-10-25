"""Freeze the final mixed-partition scope; do not silently retag reserved labels."""
import pytest

from archive.fe110_final30_qc_20261025.run import validate_scope


def checkpoint():
    partitions = ["train"] * 23 + ["development"] * 3 + ["final_test"] * 4
    rows = [{"name": f"new{i}"} for i in range(30)]
    selected = {row["name"]: {"partition": partition} for row, partition in zip(rows, partitions)}
    previous = [{"sample_id": f"old{i}"} for i in range(262)]
    config = {"expected_remaining": 30, "previous_reviewed": 262,
              "expected_partitions": {"train": 23, "development": 3, "final_test": 4}}
    return rows, selected, previous, config


def test_frozen_training_development_and_test_counts_are_accepted():
    validate_scope(*checkpoint())


def test_reserved_partition_cannot_be_silently_retagged_for_training():
    rows, selected, previous, config = checkpoint()
    selected[rows[-1]["name"]]["partition"] = "train"
    with pytest.raises(ValueError, match="partition counts"):
        validate_scope(rows, selected, previous, config)


def test_duplicate_or_previously_reviewed_label_blocks_recovery():
    rows, selected, previous, config = checkpoint()
    with pytest.raises(ValueError, match="scope"):
        validate_scope(rows + rows[:1], selected, previous, config)
    previous[0]["sample_id"] = rows[0]["name"]
    with pytest.raises(ValueError, match="scope"):
        validate_scope(rows, selected, previous, config)
