import pytest

from archive.fe110_c3_continuation_20261027.prepare import timing_budget


def timing_file(path, count=80, cores=32):
    path.write_text(f"running on {cores} total cores\n" +
        "".join(f"LOOP+: cpu time 1: real time {20 if i < 60 else 10}\n" for i in range(count)) +
        "Elapsed time (sec): 1400.0\n")


def test_budget_distinguishes_recent_rate_from_whole_run_and_allocated_cores(tmp_path):
    path = tmp_path / "OUTCAR"
    timing_file(path)
    result = timing_budget(path)
    assert result["full_cap_reference_wall_hours"] == pytest.approx([3000/3600, 5250/3600])
    assert result["full_cap_reference_core_hours"] == pytest.approx([3000/3600*32, 5250/3600*32])
    assert result["actual_convergence_can_stop_earlier"] is True
    assert result["not_a_cost_cap_or_confidence_interval"] is True
    assert result["monetary_price_per_core_hour"] is None


@pytest.mark.parametrize("count,cores", [(79, 32), (81, 32), (80, 64)])
def test_incomplete_or_different_core_timing_cannot_support_this_budget(tmp_path, count, cores):
    path = tmp_path / "OUTCAR"
    timing_file(path, count, cores)
    with pytest.raises(ValueError, match="exact80-step32-core"):
        timing_budget(path)
