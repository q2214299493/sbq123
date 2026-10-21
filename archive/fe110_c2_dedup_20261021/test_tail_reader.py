import pytest

from archive.fe110_c2_dedup_20261021.tail_reader import final_cycle_metadata


def test_final_absolute_ionic_step_and_electronic_iteration():
    text = " RMM: 11 -1.0 -0.000001 -0.000001\n 296 F= -1.0 E0= -1.0\n"
    assert final_cycle_metadata(text) == (296, 11)


def test_new_unfinished_cycle_rejected():
    with pytest.raises(ValueError, match="incomplete"):
        final_cycle_metadata(" RMM: 11 -1.0 -1e-6 -1e-6\n 296 F= -1.0\n RMM: 1 -1.0 -0.1 -0.1\n")


def test_missing_final_summary_rejected():
    with pytest.raises(ValueError, match="incomplete"):
        final_cycle_metadata(" RMM: 11 -1.0 -1e-6 -1e-6\n")
