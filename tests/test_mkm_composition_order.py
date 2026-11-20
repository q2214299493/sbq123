import math

import pytest

from scripts.baseline_mkm.pressure_perturbation import checked_feed, log_order
from scripts.baseline_mkm.reaction_order import archived_grid, frozen_pressures
from scripts.baseline_mkm.sensitivity_inputs import FIXED_TOTAL, derive
from scripts.baseline_mkm import drc_pair as pair


BASE = {"H2-g": 1.0, "HNO-g": 0.1, "NO-g": 0.5}


@pytest.mark.parametrize("step", [0.04, -0.04, 0.02, -0.02])
def test_archived_candidates_survive_actual_input_writer(step):
    grid, _ = archived_grid()
    parent = pair.REPORTS / "phase3_0"
    n, d, c = [pair.read(f) for f in (parent / "closed_cycle_network.json",
               pair.REPORTS / "phase2_5_2/cycle_dataset.json", parent / "workflow_configuration.json")]
    spec = dict(kind="gas_order", species_id="NO-g", constraint=FIXED_TOTAL, step=abs(step),
                composition_grid={"plus": grid[abs(step)], "minus": grid[-abs(step)]})
    derivative, config = derive(n, d, c, spec, 1 if step > 0 else -1)
    files, _ = pair.point.qualify(n, derivative, config)
    target = grid[step]
    assert derivative["reactions"] == d["reactions"]
    assert frozen_pressures(files[pair.point.INPUT]) == target
    assert {k: float(format(v, ".5g")) for k, v in target.items()} == target
    assert checked_feed(BASE, target, "NO-g", 1.6) == pytest.approx(step, rel=0.005)


@pytest.mark.parametrize("target", [
    {"H2-g": 0.98145, "HNO-g": 0.098145, "NO-g": 0.52041},
    {"H2-g": 0.98, "HNO-g": 0.10, "NO-g": 0.52},
    {"H2-g": 0.0, "HNO-g": 0.1, "NO-g": 1.5},
    {"H2-g": 1.0, "NO-g": 0.6},
    {"H2-g": 1.0000000001, "HNO-g": 0.1, "NO-g": 0.5},
])
def test_no_rounding_to_admit_unapproved_mat_feed(target):
    with pytest.raises(ValueError):
        checked_feed(BASE, target, "NO-g", 1.6)


def test_asymmetric_log_quadratic_at_zero():
    x = [-0.038, 0.0, 0.041]
    values = log_order([0.5 * math.exp(t) for t in x], [math.exp(2 + 0.7*t + 3*t*t) for t in x])
    assert values["quadratic_at_zero"] == pytest.approx(0.7)
    assert values["secant"] == pytest.approx(0.709)
    assert values["negative_side"] == pytest.approx(0.586)
    assert values["positive_side"] == pytest.approx(0.823)


@pytest.mark.parametrize("pressures,rates", [([1, 1, 2], [1, 1, 2]), ([0, 1, 2], [1, 1, 2]), ([0.5, 1, 2], [0, 1, 2])])
def test_invalid_response_is_unavailable(pressures, rates):
    with pytest.raises(ValueError):
        log_order(pressures, rates)
