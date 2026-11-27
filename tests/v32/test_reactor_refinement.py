"""Trajectory ownership and joint root identity for the Cantera reactor contract."""

from types import SimpleNamespace

import pytest

from sbq123.common.evidence.registry import dataset
from sbq123.common.kinetic_model.contracts import RootFailure, identity
from sbq123.mkm.catkinas.local import local_point
from sbq123.reactor import simulate
from sbq123.reactor.kinetics.source import LocalSource
from sbq123.reactor.models import cstr


def _surface(kind, **opts):
    return simulate(
        kind,
        dataset_id="langmuir",
        mode="dynamic_mkm",
        temperature_K=400,
        pressure_Pa=3325.785047261296,
        inlet_mol_s=1,
        volume_m3=1,
        composition={"A": 1, "B": 0},
        reactant="A",
        product="B",
        catalyst="analytical",
        catalyst_loading_kg=1,
        conversion_id="analytic-unit-site",
        initial_coverage=[0.5],
        max_root_distance=0.02,
        **opts,
    )


def _check_chain(records):
    previous = None
    accepted = []
    known = set()
    for record in records:
        body = dict(record)
        receipt = body.pop("receipt_sha256")
        assert identity(body) == receipt
        owner = body.pop("evaluation_type")
        parent = body.pop("predecessor_checkpoint_sha256")
        solver_digest = body.pop("solver_receipt_sha256")
        body.pop("subdivision_failures", None)
        assert identity(body) == solver_digest
        assert body["converged"] and body["root_state_sha256"] == identity(body["coverage"])
        if owner == "accepted":
            assert parent == previous
            assert receipt not in known
            accepted.append(receipt)
            known.add(receipt)
            previous = receipt
        elif owner == "trial":
            assert parent == previous
        else:
            assert owner == "report" and parent in known
    assert {r["evaluation_type"] for r in records} == {"trial", "accepted", "report"}
    return accepted


@pytest.mark.parametrize("intervals", [4, 32])
def test_reporting_preserves_physical_checkpoints(intervals):
    histories = []
    for n in (2, 11):
        out = _surface("PFR", area_m2=1, points=n, axial_intervals=intervals)
        records = out["local_solver_receipts"]
        ids = _check_chain(records)
        solver = out["solver"]
        assert ids == [solver["initial_checkpoint_sha256"], *solver["continuation_receipts"]]
        assert len(solver["continuation_receipts"]) == solver["physical_intervals"] + 1
        reports = [r for r in records if r["evaluation_type"] == "report"]
        assert len(reports) == n
        assert [r["receipt_sha256"] for r in reports] == [p["local_receipt_sha256"] for p in out["points"]]
        assert reports[-1]["predecessor_checkpoint_sha256"] == ids[-1]
        histories.append(([r for r in records if r["evaluation_type"] != "report"], out["points"][-1]["conversion"]))
    assert histories[0] == histories[1]


def test_failed_trial_keeps_last_accepted_root(monkeypatch):
    gas = SimpleNamespace(concentrations=[0.001, 0], T=400, P=3325.785047261296)
    source = LocalSource(dataset("langmuir"), 1, [0.5], 0.2)
    source.evaluate(gas, commit=True)
    checkpoint = source.checkpoint
    failed = {"converged": False, "reason": "test local failure"}
    monkeypatch.setattr(source, "solve", lambda *args, **kwargs: ([0, 0, 0], failed))
    with pytest.raises(RootFailure) as caught:
        source.evaluate(gas, commit=True)
    assert source.checkpoint is checkpoint
    assert caught.value.receipt == failed and caught.value.prior_receipts == tuple(source.receipts)
    assert len(source.receipts) == 1


def test_cstr_seed_report_owns_its_physical_chain():
    out = _surface("CSTR", cstr_seeds=[[1, 0], [2, 0], [0, 0]])
    assert len(out["points"]) == 1
    root = out["points"][0]
    assert root["root_sha256"] == identity(root["root_state"])
    assert root["root_state"]["surface_coverage"] == dict(zip(["A*"], root["coverage"]))
    for seed in out["solver"]["seed_outcomes"]:
        if seed["status"] == "rejected":
            assert seed["seed"] == [0, 0] and seed["reason"]
            continue
        assert seed["root_sha256"] == root["root_sha256"]
        start, count = seed["receipt_start"], seed["receipt_count"]
        records = out["local_solver_receipts"][start : start + count]
        _check_chain(records)
        assert records[-1]["evaluation_type"] == "report"
        assert records[-1]["receipt_sha256"] == seed["local_receipt_sha256"]
        assert sum(r["evaluation_type"] == "report" for r in records) == 1


def test_equal_gas_distinct_registered_surface_roots(monkeypatch):
    # Exercise seed grouping only. These are verified local roots of the existing
    # control, not new physical CSTR solutions of an unqualified mechanism.
    import numpy as np

    model = dataset("three-surface-roots")
    coverages = [local_point(model, [1, 0], 400, 1e5, [x], 0.12)[1]["coverage"] for x in (0.2, 0.8)]
    case = SimpleNamespace(x=np.array([1.0, 0.0]), names=["A", "B"], surface_names=["A*"])

    def outlet(case, start):
        cov = coverages[int(start[1] > 0.4)]
        return dict(mole_fractions={"A": 0.5, "B": 0.5}, coverage=cov, local_receipt_sha256=None), []

    monkeypatch.setattr(cstr, "_one", outlet)
    rows, solver, _ = cstr.stirred_tank(case, [[1, 0], [2, 0], [0, 1]])
    assert len(rows) == 2
    assert sorted(row["coverage"][0] for row in rows) == pytest.approx([0.2, 0.8])
    ids = [row["root_sha256"] for row in rows]
    assert len(set(ids)) == 2 and all(row["root_sha256"] == identity(row["root_state"]) for row in rows)
    requested = [s for s in solver["seed_outcomes"] if s["source"] == "request"]
    assert [s["root_sha256"] for s in requested] == [ids[0], ids[0], ids[1]]
    close = dict(rows[0]["root_state"], surface_coverage={"A*": 0.2 + 1e-10})
    assert cstr._same_root(rows[0]["root_state"], close)
