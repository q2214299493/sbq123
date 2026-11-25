"""Analytical event-clock fixtures with explicit independent-seed and finite-window designs."""

from copy import deepcopy

import pytest

from scripts.surface_kmc.analysis import (
    contact_flux,
    seed_precision,
    seed_series,
    size_sensitivity,
    window_analysis,
)
from scripts.native_model import assemble
from test_kmc_spatial_core import open_model


def series(seed, split):
    d, c = open_model()
    c["zacros"]["seed"] = seed
    mapping = assemble("zacros", d, c)[1]["validation"]
    steps = [r["native_step"] for r in mapping["event_checks"]]
    proc, pop = [], []
    for n, t in enumerate((0.0, split, 1.0, 1.0 + split, 2.0)):
        state = n % 2
        proc.append((n, t, dict(zip(steps, [(n + 1) // 2, n // 2], strict=True))))
        pop.append((n, t, {"H2-bridge": state, "H2-top": 0, "H2-g": -state}))
    return seed_series(c, d, dict(procstat=proc, specnum=pop), mapping)


def test_time_weighted_multidentate_coverage_pathway_and_rate():
    r = series(7, 0.25)

    def window(a, b, **kw):
        return window_analysis(r["trajectory"], r["dataset"], r["mapping"], a, b, **kw)

    v = window(0.25, 1.5, denominator=3, basis="bridge sites")
    assert v["molecules_per_cell"]["H2-bridge"] == pytest.approx(1 / 1.25)
    assert v["coverage"] == pytest.approx({"top-Ni": 0.8 / 4, "bridge-Cu": 0.8 / 3})
    assert list(v["event_frequency_s_inverse"].values()) == [0.8, 0.8]
    assert v["species_net_rate"]["H2-g"] == 0
    assert window(0, 0.5)["pathway_flux"]["ads"]["net_rate"] == 2
    for a, b in ((1, 1), (-1, 1), (0, 3)):
        with pytest.raises(ValueError):
            window(a, b)


def test_independent_seed_precision_and_burn_in_sensitivity():
    runs = [series(i, x) for i, x in enumerate((0.2, 0.25, 0.3), 1)]
    design = dict(
        start_s=0, end_s=2, observable="coverage", key="bridge-Cu", required_seeds=3, absolute_precision=0.1
    )
    result = seed_precision(runs, **design)
    assert result["mean"] == pytest.approx(0.25)
    assert result["half_width_95"] == pytest.approx(4.3026527297 * (0.05 / 3) / (3**0.5))
    assert result["decision"] == "precision_met" and result["drift"] == pytest.approx(0)
    assert seed_precision(runs[:1], **design)["interval_95"] is None
    assert seed_precision(runs, **dict(design, absolute_precision=0.001))["decision"] == "inconclusive"
    with pytest.raises(ValueError, match="unique"):
        seed_precision(runs + [runs[0]], **design)
    stale = deepcopy(runs[2])
    stale["condition"] = "different lattice size"
    with pytest.raises(ValueError, match="identical"):
        seed_precision([runs[0], stale], **design)


def test_contact_resolution_reports_ambiguous_event_intervals():
    r = series(1, 0.25)
    mapping = r["mapping"]
    a = dict(step=0, sites={1: None, 2: None})
    b = dict(step=1, sites={1: "H2-bridge", 2: "H2-bridge"})
    end = dict(step=4, sites=a["sites"])
    result = contact_flux(
        [a, b, end], r["trajectory"]["procstat"], [dict(site_ids=[1, 2]), dict(site_ids=[1, 2])], mapping
    )
    assert result["resolved"] == [
        dict(native_step="r1_forward", left=1, right=2, interface_id="junction", count=1)
    ]
    assert result["unresolved"] == {"r1_forward": 1, "r2_reverse": 2}


def test_periodic_size_sensitivity_uses_intensive_observables():
    from test_native_model import model

    def group(nx, seeds):
        d, c = model(gas=True)
        c["zacros"].update(repeat_cell=[nx, 3], spatial_analysis=True)
        runs = []
        for seed, x in zip(seeds, (0.2, 0.25, 0.3), strict=True):
            c["zacros"]["seed"] = seed
            mapping = assemble("zacros", d, c)[1]["validation"]
            obs = series(seed, x)["trajectory"]
            runs.append(seed_series(c, d, obs, mapping))
        return runs

    a, b = group(3, [1, 2, 3]), group(6, [4, 5, 6])
    design = dict(
        start_s=0, end_s=2, observable="coverage", key="bridge-Cu", required_seeds=3, absolute_precision=0.1
    )
    result = size_sensitivity(a, b, **design)
    assert result["site_counts"] == [18, 36]
    assert result["difference"] == pytest.approx(-0.75 / 18)
    assert result["decision"] == "within_tolerance"
    assert size_sensitivity(a, b, **dict(design, absolute_precision=0.001))["decision"] == "inconclusive"
