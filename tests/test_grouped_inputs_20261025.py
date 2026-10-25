from pathlib import Path

import pytest

from archive.fe110_grouped_inputs_20261025.prepare import budget, timing


def test_bounded_timing_parser_uses_walltime_not_cpu_time(tmp_path: Path):
    source = tmp_path / "synthetic_OUTCAR"
    source.write_text("running on 32 total cores\nIteration 80( 4)\n"
        "Total CPU time used (sec): 99999\nElapsed time (sec): 3600.0\n")
    record = timing(source)
    assert record["last_ionic_iteration_in_tail"] == 80
    assert record["allocated_core_hours"] == 32


def test_missing_timing_cannot_silently_become_zero_cost(tmp_path: Path):
    source = tmp_path / "synthetic_incomplete_OUTCAR"
    source.write_text("running on 32 total cores\n")
    with pytest.raises(ValueError, match="missing or invalid"):
        timing(source)


def test_budget_separates_single_points_optimizations_and_unknown_price():
    result = budget([{"allocated_core_hours": 10, "elapsed_seconds": 1125},
                     {"allocated_core_hours": 20, "elapsed_seconds": 2250}],
                    [{"allocated_core_hours": 300}, {"allocated_core_hours": 400}])
    assert result["combined_reference_core_hours"] == [720, 1040]
    assert result["max_ionic_steps_per_optimization"] == 80
    assert result["monetary_cost"] is None
    assert result["automatic_continuation"] is False
