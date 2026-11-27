import math
import pytest

from sbq123.common.kinetic_model.contracts import GAS_CONSTANT, Model, identity
from sbq123.common.evidence.registry import dataset, entry
from sbq123.reactor import simulate

T = 400
P = GAS_CONSTANT * T


def request(kind, key="first-order", **kwargs):
    data = dict(
        kind=kind,
        dataset_id=key,
        mode="fixed",
        temperature_K=T,
        pressure_Pa=P,
        composition={"A": 1.0, "B": 0.0},
        volume_m3=1.0,
        reactant="A",
        product="B",
        points=4,
    )
    data["inlet_mol_s"] = 1.0
    if kind == "PFR":
        data["area_m2"] = 0.5
    data.update(kwargs)
    return simulate(**data)


@pytest.mark.parametrize("kind", ["PFR", "CSTR"])
@pytest.mark.parametrize("k", ["zero", "first-order"])
def test_analytic(kind, k):
    out = request(kind, k)
    end = out["points"][-1]
    expected = 0 if k == "zero" else 0.75 / 1.75 if kind == "CSTR" else 1 - math.exp(-0.75)
    assert end["conversion"] == pytest.approx(expected, abs=1e-8)
    assert end["yield_mol_per_mol_fed"] == pytest.approx(expected, abs=1e-8)
    if k != "zero":
        assert end["selectivity_mol_per_mol_consumed"] == pytest.approx(1.0)
        assert end["source_mol_m3_s"]["A"] < 0 < end["source_mol_m3_s"]["B"]
    if kind != "Batch":
        assert end["residence_time_s"] == pytest.approx(1.0)
    if kind == "PFR":
        assert end["coordinate"] == 2
    assert sum(end["source_mol_m3_s"].values()) == pytest.approx(0)
    assert out["result_sha256"] == identity({k: v for k, v in out.items() if k != "result_sha256"})


def test_three_roots():
    out = request("CSTR", "autocatalytic")
    assert sorted(r["conversion"] for r in out["points"]) == pytest.approx(
        [0, (1 - math.sqrt(5 / 9)) / 2, (1 + math.sqrt(5 / 9)) / 2], abs=1e-8
    )
    assert out["solver"]["stability"] is None


def test_units_and_stiffness():
    assert request("PFR", "stiff")["points"][-1]["conversion"] == pytest.approx(1, abs=1e-9)
    end = request("PFR", "mass-normalized", catalyst_loading_kg=2.0)["points"][-1]
    assert end["conversion"] == pytest.approx(1 - math.exp(-1.5), abs=1e-8)
    end = request("PFR", "first-order", pressure_Pa=P * 2)["points"][-1]
    assert end["conversion"] == pytest.approx(1 - math.exp(-1.5), abs=1e-8)
    end = request("PFR", "arrhenius", temperature_K=500.0, pressure_Pa=P*500/T)["points"][-1]
    k = 0.75 * math.exp(-5000 / GAS_CONSTANT * (1 / 500 - 1 / T))
    assert end["conversion"] == pytest.approx(1 - math.exp(-k), abs=1e-8)


@pytest.mark.parametrize(
    "change",
    [{"points": True}, {"points": 2.0}, {"temperature_K": float("nan")}, {"pressure_Pa": 0}, {"composition": {"A": 0.8}}, {"volume_m3": 0}],
)
def test_invalid_request(change):
    with pytest.raises(ValueError):
        request("PFR", **change)


def test_approvals():
    for loading in [0, -1, True]:
        with pytest.raises(ValueError):
            request("PFR", "mass-normalized", catalyst_loading_kg=loading)
    with pytest.raises(ValueError):
        request("PFR", "site-normalized", catalyst_loading_kg=1.0, catalyst="analytical")
    with pytest.raises(ValueError):
        request("PFR", "site-normalized", catalyst_loading_kg=1.0, catalyst="analytical", conversion_id="analytic-unit-site")


def test_balance_checks():
    for field in ["elements", "charge"]:
        data = entry("datasets", "first-order")["model"]
        data["species"][1][field] = {"Y": 1} if field == "elements" else 1
        with pytest.raises(ValueError, match="Unbalanced"):
            Model._from_verified_record(data, registered_digest=identity(data), provenance="test")
    with pytest.raises(ValueError):
        dataset("unknown")


@pytest.mark.parametrize("kind", ["PFR", "CSTR"])
def test_dynamic_analytical(kind):
    pytest.importorskip("sbq123.mkm.catkinas.local")
    out = request(
        kind,
        "langmuir",
        mode="dynamic_mkm",
        catalyst="analytical",
        catalyst_loading_kg=1.0,
        conversion_id="analytic-unit-site",
        initial_coverage=[0.5],
    )
    end = out["points"][-1]
    a = end["concentration_mol_m3"]["A"]
    assert end["coverage"][0] == pytest.approx(a / (1 + a), abs=1e-9)
    # dA/dt = -A/(1+A); CSTR steady 1-A=A/(1+A).
    if kind == "CSTR":
        assert a == pytest.approx((math.sqrt(5) - 1) / 2, abs=1e-8)
    else:
        assert math.log(a) + a == pytest.approx(0, abs=2e-8)
    assert out["local_solver_receipts"] and all(r["converged"] for r in out["local_solver_receipts"])


def test_local_failure():
    pytest.importorskip("sbq123.mkm.catkinas.local")
    with pytest.raises(ValueError, match="continuity"):
        request(
            "PFR",
            "langmuir",
            mode="dynamic_mkm",
            catalyst="analytical",
            catalyst_loading_kg=1.0,
            conversion_id="analytic-unit-site",
            initial_coverage=[0.01],
            max_root_distance=0.01,
        )
