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


@pytest.mark.parametrize(
    "scale,loading,area",
    [(1.0, 1.0, 1.0), (0.5, 0.5, 0.5), (2.0, 2.0, 2.0), (1.0, 1e-6, 1.0), (1.0, 1.0, 0.25)],
)
def test_fixed_surface_pfr_area_and_loading(scale, loading, area):
    result = run("PFR", scale=scale, surface=True, catalyst_loading_kg=loading, area_m2=area)
    for row in result["points"]:
        extent = row["amount_or_flow"]["B"] / scale
        tau = row["coordinate"] * area / scale
        # Integrated Langmuir balance, evaluated without subtracting near-equal concentrations.
        dose = loading / scale * tau
        assert abs(math.log1p(-extent) - extent + dose) <= 3e-14 + 2e-8 * dose
        assert row["conversion"] == pytest.approx(extent, abs=3e-14)
        assert row["amount_or_flow"]["A"] / scale == pytest.approx(1 - extent, abs=3e-14)
        assert row["residence_time_s"] == pytest.approx(tau, abs=2e-8)


def test_fixed_surface_pfr_rejects_trace_product_area_error(monkeypatch):
    from sbq123.common.kinetic_model.contracts import RootFailure
    from sbq123.reactor.models import pfr

    good = run("PFR", surface=True, catalyst_loading_kg=1e-6)
    # Recreate the rejected total-area weighting on the actual Cantera interface.
    attach = pfr.ct.ReactorSurface

    def wrong_area(interface, reactor, *, clone, A):
        return attach(interface, reactor, clone=clone, A=A * 1e-6)

    monkeypatch.setattr(pfr.ct, "ReactorSurface", wrong_area)
    with pytest.raises(RootFailure, match="Independent axial species balance failed") as caught:
        run("PFR", surface=True, catalyst_loading_kg=1e-6)
    receipt = caught.value.receipt
    assert receipt["converged"] is False
    assert receipt["input_sha256"] == good["input_sha256"]
    assert receipt["species"] == ["A", "B"]
    for residual, tolerance in zip(receipt["residual_per_feed"], receipt["tolerance_per_feed"], strict=True):
        assert tolerance < abs(residual) < 2e-6


def test_unsupported_thermodynamics_and_geometry():
    with pytest.raises(ValueError):
        mechanism("v31-closed-cycle", volume_m3=1)
    with pytest.raises(ValueError):
        run("Batch")
    for seed in ([True], ["0.5"], [1.1]):
        with pytest.raises(ValueError):
            run("PFR", surface=True, initial_coverage=seed)


@pytest.mark.parametrize("fraction", [1e-16, 1e-14, 1e-12, 1e-10, 1e-8, 1e-6, 1.0])
def test_dilute_surface_pfr(fraction):
    result = run("PFR", surface=True, composition={"A": fraction, "B": 1 - fraction},
                 initial_coverage=[fraction / (1 + fraction)])
    for row in result["points"]:
        # Normalizing by reactant feed keeps the integrated Langmuir equation
        # well-conditioned even when the outlet product increment is below 1 ULP.
        x = row["conversion"]
        assert abs(-math.log1p(-x) + fraction * x - row["coordinate"]) < 2e-7
        assert row["yield_mol_per_mol_fed"] == pytest.approx(x, abs=2e-7)
    receipt = result["solver"]["species_balance"]
    assert abs(receipt["relative_species_residual"][0]) < 2e-6
    assert receipt["tolerance_per_feed"][0] <= 2e-6 * fraction * (1 + 1e-12)


def test_dilute_surface_pfr_unresolved_quadrature():
    from sbq123.common.kinetic_model.contracts import RootFailure

    fraction = 1e-14
    with pytest.raises(RootFailure, match="axial species balance") as caught:
        run("PFR", surface=True, axial_intervals=4, composition={"A": fraction, "B": 1 - fraction},
            initial_coverage=[fraction / (1 + fraction)])
    receipt = caught.value.receipt
    assert not receipt["converged"] and len(receipt["input_sha256"]) == 64
    assert receipt["quadrature_difference_per_feed"][0] > receipt["quadrature_tolerance_per_feed"][0]
