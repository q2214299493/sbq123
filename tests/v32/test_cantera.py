"""Independent closed-form references for the optional Cantera wheel."""

import math

import pytest

from sbq123.reactor import mechanism, simulate
from sbq123.common.kinetic_model.contracts import GAS_CONSTANT, identity


def run(kind, *, mode="fixed", scale=1.0, surface=False, key=None, **changes):
    opts = dict(
        dataset_id=key or ("langmuir" if surface else "first-order"),
        mode=mode,
        temperature_K=400,
        pressure_Pa=400 * GAS_CONSTANT,
        composition={"A": 1, "B": 0},
        volume_m3=scale,
        inlet_mol_s=scale,
        reactant="A",
        product="B",
    )
    if kind == "PFR":
        opts["area_m2"] = scale
    if surface:
        opts.update(catalyst="analytical", conversion_id="analytic-unit-site", catalyst_loading_kg=scale, initial_coverage=[0.5])
    opts.update(changes)
    return simulate(kind, **opts)


@pytest.mark.parametrize("scale", [1, 1e-6, 1e-9, 1e-12, 1e-20])
@pytest.mark.parametrize("mode", ["fixed", "dynamic_mkm"])
def test_scale_invariant_cstr(scale, mode):
    surface = mode == "dynamic_mkm"
    result = run("CSTR", mode=mode, scale=scale, surface=surface)
    assert len(result["points"]) == 1
    row = result["points"][0]
    expected = (3 - math.sqrt(5)) / 2 if surface else 3 / 7
    assert row["conversion"] == pytest.approx(expected, abs=2e-8)
    assert max(abs(x) for x in row["balance_residual_mol_s"]) / scale < 2e-8
    assert abs(row["mass_residual_kg_s"]) / scale < 1e-10
    assert abs(row["element_residual_mol_s"]["X"]) / scale < 1e-7


@pytest.mark.parametrize("mode", ["fixed", "dynamic_mkm"])
def test_surface_profile_and_sampling(mode):
    coarse = run("PFR", mode=mode, surface=True, points=2)
    fine = run("PFR", mode=mode, surface=True, points=11)
    assert coarse["solver"]["continuation_receipts"] == fine["solver"]["continuation_receipts"]
    for row in fine["points"]:
        a = row["mole_fractions"]["A"]
        assert math.log(a) + a == pytest.approx(1 - row["coordinate"], abs=5e-8)
        assert row["coverage"][0] == pytest.approx(a / (1 + a), abs=2e-8)
        assert row["coverage"][0] + row["vacancy"][0] == pytest.approx(1)
        assert row["residence_time_s"] == pytest.approx(row["coordinate"], abs=2e-8)
    assert fine["solver"]["flow_surface_inert_coordinate"] == (mode == "fixed")


def test_pfr_refinement_and_reversible_rate():
    for intervals in (16, 64):
        result = run("PFR", key="reversible-iso", axial_intervals=intervals)
        for row in result["points"]:
            assert row["conversion"] == pytest.approx(0.5 * (1 - math.exp(-1.5 * row["coordinate"])), abs=2e-7)
        assert result["cantera_version"] == "3.2.0"
        assert result["input_sha256"] == identity(result["conditions"])
        assert result["evidence_provenance"]["mechanism_rate_comparison_max_relative"] < 1e-9


def test_unsupported_thermodynamics_and_geometry():
    with pytest.raises(ValueError):
        mechanism("v31-closed-cycle", volume_m3=1)
    with pytest.raises(ValueError):
        run("Batch")
    for seed in ([True], ["0.5"], [1.1]):
        with pytest.raises(ValueError):
            run("PFR", surface=True, initial_coverage=seed)
