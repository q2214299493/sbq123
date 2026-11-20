"""Offline network scans, evidence binding, budget boundaries and partial batch recovery."""

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import drc_batch as batch, drc_batch_execution as executor
from scripts.baseline_mkm import drc_cross_reaction as campaign
from scripts.baseline_mkm.drc_batch_report import describe, ranking
from scripts.baseline_mkm.drc_pair import REPORTS


@pytest.fixture
def parents():
    return read(REPORTS / "phase3_0/closed_cycle_network.json"), read(REPORTS / "phase2_5_2/cycle_dataset.json")


def test_scan_all_laws_and_missing_values(parents):
    rows = batch.scan(*parents)
    assert list(rows) == ["ads", "transfer", "hydrogenate", "desorb"]
    assert all(r["status"] == "READY" and r["drc"] is None for r in rows.values())
    assert rows["ads"]["coefficient_units"] == {"forward": "bar^-1 s^-1", "reverse": "s^-1"}
    assert rows["desorb"]["coefficient_units"] == {"forward": "s^-1", "reverse": "bar^-1 s^-1"}


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("missing row", "UNAVAILABLE"),
        ("TS", "REQUIRES_REVIEW"),
        ("direction", "REQUIRES_REVIEW"),
        ("rate", "UNAVAILABLE"),
        ("missing evidence", "BLOCKED"),
    ],
)
def test_ineligible_row(parents, fault, expected):
    n, d = parents
    entry, row = n["reactions"][0], d["reactions"][0]
    if fault == "missing row":
        row = None
    elif fault == "TS":
        entry["ts_review"] = None
    elif fault == "direction":
        entry["direction"]["status"] = "unknown"
    elif fault == "rate":
        row["rates"]["reverse"] = None
    else:
        row["missing"] = ["unreviewed reference"]
    status, gaps = batch.eligibility(n, d, entry, row)
    assert status == expected and gaps


def test_fe_scan_without_native_prepare():
    data = read(REPORTS / "phase2_4/fe110_parameters.json")
    network = read(REPORTS / "networks" / ("network-" + data["network_version"] + ".json"))
    (row,) = batch.scan(network, data).values()
    assert row["drc"] is None and row["status"] == "BLOCKED" and row["reversibility"] == "unknown"
    assert "Missing compatible free energies" in row["missing"]


def test_network_binding(parents):
    n, d = parents
    n["project_id"] = "other"
    with pytest.raises(ValueError, match="network_version"):
        batch.scan(n, d)


def test_reuse_reconstructs_both_pairs_and_rejects_tampering(tmp_path, monkeypatch):
    src = {}
    for size, phase in (("coarse", "phase3_2_0"), ("fine", "phase3_2_0_1")):
        path = REPORTS / phase / "result.json"
        src[size] = dict(pair=str(tmp_path / size), report=str(path), sha256=sha256_file(path))

    def compare(root, base):
        result = read(Path(src[root.name]["report"]))
        result.pop("step_size_validation", None)
        return result

    monkeypatch.setattr(batch, "compare", compare)
    assert batch.reuse(tmp_path, "transfer", src)["step_size_validation"]["passed"]
    with pytest.raises(ValueError, match="Wrong reaction"):
        batch.reuse(tmp_path, "ads", src)
    src["fine"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        batch.reuse(tmp_path, "transfer", src)


@pytest.mark.parametrize("fault", ["pass", "missing member", "duplicate", "different batch", "native budget", "too many"])
def test_plan_individual_approval_and_spawn_bounds(tmp_path, fault):
    jobs = {"a": {"directory": "pair-1"}, "b": {"directory": "pair-2"}}
    manifest = {"jobs": jobs, "limits": batch.LIMITS.copy()}
    if fault == "too many":
        jobs["c"] = {"directory": "pair-3"}
    if fault == "native budget":
        manifest["limits"]["per_run_s"] = 211
    approvals = dict(
        batch_plan_sha256=sha256_json(manifest),
        decisions={rid: {side: str(tmp_path / (rid + side)) for side in ("plus", "minus")} for rid in jobs},
    )
    if fault == "pass":
        assert len(executor.decisions_for_plan(manifest, approvals)) == 2
        return
    if fault == "missing member":
        approvals["decisions"]["a"].pop("minus")
    elif fault == "duplicate":
        approvals["decisions"]["b"]["minus"] = approvals["decisions"]["a"]["plus"]
    elif fault == "different batch":
        approvals["batch_plan_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        executor.decisions_for_plan(manifest, approvals)


@pytest.mark.parametrize("fault", ["fail first", "resume accepted", "expired", "unbound partial"])
def test_shared_clock_partial_recovery(tmp_path, monkeypatch, fault):
    names = ["pair-1", "pair-2"]
    calls = []
    for name in names:
        (tmp_path / name).mkdir()
        save(tmp_path / name / "pair.json", {})
    if fault != "fail first":
        save(tmp_path / names[0] / "started.json", {})
    if fault in ("resume accepted", "expired"):
        save(tmp_path / "started.json", {"utc_epoch_s": 100 if fault == "expired" else 990, "pairs_sha256": "bound"})
    monkeypatch.setattr(campaign.pair, "clock", lambda: 1100)
    monkeypatch.setattr(campaign.pair, "verified_finish", lambda *_: {})
    accepted = {names[0]} if fault == "resume accepted" else set()

    def run_pair(directory, base, decisions, *, campaign_deadline):
        assert campaign_deadline - campaign.monotonic() <= 960
        if directory.name in accepted:
            return
        calls.append(directory.name)
        if fault == "fail first":
            raise ValueError("native failed")
        accepted.add(directory.name)

    monkeypatch.setattr(campaign.pair, "run_pair", run_pair)
    args = tmp_path, tmp_path, "bound", names, dict.fromkeys(names), 960
    if fault == "resume accepted":
        campaign.run_verified(*args)
        campaign.run_verified(*args)
        assert calls == ["pair-2"]
    else:
        with pytest.raises((ValueError, TimeoutError)):
            campaign.run_verified(*args)
        assert calls == ([names[0]] if fault == "fail first" else [])
        assert not (tmp_path / "finished.json").exists()


@pytest.mark.parametrize("field", ["baseline", "normalization", "temperature_K", "partial_pressures_bar", "network_version"])
def test_no_cross_condition_pooling(field):
    result, manifest = reference()
    manifest["baseline_hashes" if field == "baseline" else field] = "other"
    with pytest.raises(ValueError, match="Different batch"):
        describe(result, manifest)


def reference():
    r = read(REPORTS / "phase3_2_0_1/result.json")
    b = r["cases"]["baseline"]
    m = {k: deepcopy(r[k]) for k in ("temperature_K", "partial_pressures_bar", "normalization", "observable")}
    m.update(baseline_hashes=b["source_hashes"], dataset_version=b["dataset_version"], network_version=b["network_version"])
    return r, m


def test_only_stable_results_ranked_and_uncertainty_labeled():
    r, m = reference()
    stable = describe(r, m)
    r["step_size_validation"]["passed"] = False
    unstable = describe(r, m)
    del r["step_size_validation"]
    single = describe(r, m)
    assert single["stability"] == "untested" and single["numerical_uncertainty"]["standard_error"] is None
    assert ranking(dict(s=stable, u=unstable, new=single, pending={"drc": None, "stability": "unavailable"})) == [
        {"reaction_id": "s", "drc": stable["drc"]}
    ]


def test_pilot_plan_is_reproducible_without_native_execution(parents):
    from scripts.baseline_mkm.ts_perturbation import derivative

    manifest = read(REPORTS / "phase3_2_1/batch-plan.json")
    network, parent = parents
    assert manifest["network_version"] == network["network_version"]
    assert manifest["dataset_version"] == parent["dataset_version"]
    assert manifest["baseline_hashes"]["result"] == sha256_file(REPORTS / "phase3_0/result.json")
    assert {rid for rid, row in manifest["candidates"].items() if row["status"] == "READY"} == set(manifest["jobs"])
    assert len(manifest["jobs"]) * 2 <= manifest["limits"]["max_runs"]
    for rid, job in manifest["jobs"].items():
        for label, sign in batch.pair.SIGNS:
            child = derivative(network, parent, sign, 0.005, rid)
            assert job["members"][label]["run_id"] == label + "-" + child["dataset_version"][:16]
    for rid, ref in manifest["reuse_sources"].items():
        phase = (REPORTS / "phase3_2_0_1" if rid == "transfer" else REPORTS / "phase3_2_0_2/fine") / "result.json"
        assert sha256_file(phase) == ref["fine"]["sha256"]
        assert manifest["candidates"][rid]["drc"] == read(phase)["drc"]
