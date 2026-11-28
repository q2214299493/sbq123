"""Trace observables and signed reaction budgets in the installed Cantera adapter."""
from copy import deepcopy
import importlib
import math

import pytest

from sbq123.common.kinetic_model.contracts import RootFailure, identity
from sbq123.reactor import simulate


def request(kind, a, **changes):
    q = dict(kind=kind, dataset_id="first-order", mode="fixed", temperature_K=400.,
             pressure_Pa=3325.785047261296, composition={"A": a, "B": 1-a},
             volume_m3=1., inlet_mol_s=1., reactant="A", product="B")
    if kind == "PFR":
        q["area_m2"] = 1.
    return q | changes


@pytest.mark.parametrize("kind,fraction", [("PFR", 1e-14), ("PFR", 1e-16), ("CSTR", 1e-16), ("CSTR", 1e-6), ("PFR", 1e-8)])
def test_dilute_homogeneous_observables(kind, fraction):
    d = simulate(**request(kind, fraction))
    assert all(row["observable_basis"] == "signed_reaction_progress" for row in d["points"])
    row = d["points"][-1]
    ref = -math.expm1(-.75) if kind == "PFR" else 3/7
    assert row["conversion"] == pytest.approx(ref, rel=2e-8)
    assert row["yield_mol_per_mol_fed"] == pytest.approx(ref, rel=2e-8)
    assert row["selectivity_mol_per_mol_consumed"] == pytest.approx(1., abs=2e-8)
    assert row["net_production_mol_s"]["A"] / fraction == pytest.approx(-ref, rel=2e-8)
    assert row["amount_or_flow"]["A"] / fraction == pytest.approx(1-ref, rel=2e-8)


@pytest.mark.parametrize("kind", ["PFR", "CSTR"])
def test_unresolved_reversible_net_is_structured(kind):
    q = request(kind, .5, dataset_id="reversible-iso")
    with pytest.raises(RootFailure) as caught:
        simulate(**q)
    r = caught.value.receipt
    assert not r["converged"] and len(r["input_sha256"]) == 64
    assert r["species"] == ["A", "B"]
    assert len(r["residual_per_feed"]) == len(r["tolerance_per_feed"]) == 2


@pytest.mark.parametrize("kind", ["PFR", "CSTR"])
def test_two_precursors_feeding_one_product(kind, monkeypatch):
    # Test-only elementary directions A -> B and C -> B. Use the reviewed
    # equal-mass A/B/C thermodynamics without adding a public dataset.
    module = importlib.import_module("sbq123.reactor.mechanism")
    companion, model = deepcopy(module._record("stiff-cascade"))
    for step, origin, k in zip(model["steps"], ["A", "C"], [.25, .75], strict=True):
        step.update(coefficient=k, change={origin: -1, "B": 1}, orders={origin: 1})
    companion["model_sha256"] = identity(model)
    monkeypatch.setattr(module, "_record", lambda key: (companion, model))
    a, c = 1e-14, 2e-14
    d = simulate(**request(kind, a, dataset_id="two-precursors-test",
                           composition={"A": a, "B": 1-a-c, "C": c}))
    row = d["points"][-1]
    convert = (lambda k: -math.expm1(-k)) if kind == "PFR" else (lambda k: k/(1+k))
    da, dc = a*convert(.25), c*convert(.75)
    for name, expected in {"A": -da, "B": da+dc, "C": -dc}.items():
        assert row["net_production_mol_s"][name] == pytest.approx(expected, rel=2e-7, abs=0)
    assert row["gross_production_mol_s"]["B"] == pytest.approx(da+dc, rel=2e-7, abs=0)
    assert row["gross_consumption_mol_s"]["B"] == 0
    assert row["selectivity_mol_per_mol_consumed"] == pytest.approx((da+dc)/da, rel=2e-7)


def test_nonzero_progress_below_flow_resolution():
    q = request("PFR", 1e-160, dataset_id="langmuir", catalyst="analytical",
                conversion_id="analytic-unit-site", catalyst_loading_kg=1e-180, initial_coverage=[1e-160])
    with pytest.raises(RootFailure, match="below molar-flow resolution") as caught:
        simulate(**q)
    assert caught.value.receipt["unresolved_species"] == "A"
    assert caught.value.receipt["residual_mol_s"] == [None, None]
