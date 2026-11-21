"""Offline TS derivatives, analytic sensitivities and bounded executor fault injection."""

from math import exp
from pathlib import Path
import subprocess

import pytest

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import drc_pair as pair, single_point as point
from scripts.baseline_mkm import drc_pair_records as records, drc_report
from scripts.baseline_mkm.ts_perturbation import PARENT, REACTION, central_difference, derivative, reproduce
from scripts.thermochemistry.harmonic import KB

REPORTS = pair.REPORTS
BASE = REPORTS / "phase3_0"


@pytest.fixture
def parents():
    return read(BASE / "closed_cycle_network.json"), read(REPORTS / "phase2_5_2/cycle_dataset.json")


@pytest.mark.parametrize("x", [-1.1, 0, 0.3, 1, 1.9])
def test_analytic_slope_and_ev_units(x):
    # Independent J/K and J/eV constants; do not reuse the engine constant.
    thermal = 1.380649e-23 * 400 / 1.602176634e-19
    assert central_difference(3, 3 * exp(-x * 0.01 / thermal), 3 * exp(x * 0.01 / thermal), 400, 0.01) == pytest.approx(x)


@pytest.mark.parametrize(
    "args",
    [
        (0, 1, 2, 400, 0.01),
        (1, 0, 2, 400, 0.01),
        (1, 2, -1, 400, 0.01),
        (1, 2, 3, 0, 0.01),
        (1, 2, 3, 400, 0),
        (1, None, 2, 400, 0.01),
        (1, float("nan"), 2, 400, 0.01),
    ],
)
def test_invalid_observable_or_units(args):
    with pytest.raises(ValueError):
        central_difference(*args)


@pytest.mark.parametrize("sign", [-1, 1])
def test_derivative_qualified_immutable_and_reproducible(parents, sign):
    n, d = parents
    before = sha256_json([n, d])
    new = derivative(n, d, sign)
    assert reproduce(n, new) == new and new["dataset_version"] != PARENT
    assert sha256_json([n, d]) == before
    assert new["ts_perturbation"]["parent_network_sha256"] == n["network_version"]
    cfg = dict(read(BASE / "workflow_configuration.json"), dataset_version=new["dataset_version"])
    _, adapter = point.qualify(n, new, cfg)
    assert len(adapter["validation"]["reaction_indices"]) == 4
    for original, row in zip(d["reactions"], new["reactions"], strict=True):
        if row["reaction_id"] != REACTION:
            assert row == original
            continue
        for direction in ("forward", "reverse"):
            ratio = row["rates"][direction]["activity_coefficient_s^-1"] / original["rates"][direction]["activity_coefficient_s^-1"]
            assert ratio == pytest.approx(exp(-sign * 0.01 / (KB * 400)))
            assert row["energies"]["gibbs_ev"][direction] == pytest.approx(original["energies"]["gibbs_ev"][direction] + sign * 0.01)
        assert row["energies"]["gibbs_ev"]["reaction"] == original["energies"]["gibbs_ev"]["reaction"]
        assert abs(row["equilibrium"]["log_ratio_residual"]) < 1e-12


@pytest.mark.parametrize("change", ["direction", "unrelated", "provenance"])
def test_rehashed_tampering_rejected(parents, change):
    n, d = parents
    new = derivative(n, d, 1)
    if change == "direction":
        new["reactions"][1]["energies"]["gibbs_ev"]["reverse"] -= 0.01
    elif change == "unrelated":
        new["reactions"][0]["rates"]["forward"]["activity_coefficient_s^-1"] *= 2
    else:
        new["ts_perturbation"]["parent_dataset_sha256"] = "0" * 64
    new["dataset_version"] = sha256_json({k: v for k, v in new.items() if k != "dataset_version"})
    with pytest.raises(ValueError, match="reviewed rates"):
        point.qualify(n, new, dict(read(BASE / "workflow_configuration.json"), dataset_version=new["dataset_version"]))


def test_stale_network_and_fe_protection(parents):
    n, d = parents
    n["project_id"] = "different"
    with pytest.raises(ValueError, match="network_version"):
        derivative(n, d, 1)
    fe = next((REPORTS / "networks").glob("network-2a80*.json"))
    with pytest.raises(ValueError, match="blocked"):
        derivative(read(fe), read(REPORTS / "phase2_4/fe110_parameters.json"), 1)


@pytest.fixture
def clocked(tmp_path, monkeypatch):
    manifest = {"baseline_result_sha256": "baseline"}
    save(tmp_path / "pair.json", manifest)
    states = {"plus": "AWAITING_APPROVAL", "minus": "AWAITING_APPROVAL"}
    calls = []
    elapsed = [0]
    monkeypatch.setattr(pair, "clock", lambda: 1000 + elapsed[0])
    monkeypatch.setattr(pair, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(pair, "baseline", lambda _: ({"result_sha256": "baseline"}, {}))
    monkeypatch.setattr(pair, "check_member", lambda root, base, label, sign: root / label)
    monkeypatch.setattr(pair.point, "status", lambda r: {"stage": states[r.name]})
    monkeypatch.setattr(pair.point, "preflight", lambda *_: None)

    def accepted(run):
        if states[run.name] != "ACCEPTED":
            raise ValueError("unaccepted")

    monkeypatch.setattr(pair, "accepted", accepted)

    def execute(run, decision, *, deadline):
        assert deadline == 480
        calls.append(run.name)
        elapsed[0] += 100
        states[run.name] = "ACCEPTED"
        return {"stage": states[run.name]}

    monkeypatch.setattr(pair.point, "execute", execute)
    return tmp_path, states, calls, elapsed


def run(root):
    return pair.run_pair(root, Path("baseline"), {"plus": Path("positive"), "minus": Path("negative")})


def test_order_budget_and_reuse(clocked):
    root, _, calls, _ = clocked
    result = run(root)
    assert calls == ["plus", "minus"] and result["elapsed_s"] == 200 and result["remaining_s"] == 280
    assert run(root) == result and calls == ["plus", "minus"]


@pytest.mark.parametrize("failed", ["plus", "minus"])
def test_fail_fast_no_retry(clocked, monkeypatch, failed):
    root, states, calls, _ = clocked
    launch = pair.point.execute

    def execute(r, d, *, deadline):
        if r.name == failed:
            calls.append(r.name)
            states[r.name] = "REJECTED"
            return {"stage": "REJECTED", "reason": "native timeout"}
        return launch(r, d, deadline=deadline)

    monkeypatch.setattr(pair.point, "execute", execute)
    with pytest.raises(ValueError, match="native timeout"):
        run(root)
    assert calls == (["plus"] if failed == "plus" else ["plus", "minus"])
    with pytest.raises(ValueError, match="previously failed"):
        run(root)
    assert not (root / "finished.json").exists()


def test_expired_partial_pair(clocked):
    root, states, calls, _ = clocked
    states["plus"] = "ACCEPTED"
    save(root / "started.json", dict(utc_epoch_s=500, pair_sha256=sha256_json(read(root / "pair.json"))))
    with pytest.raises(TimeoutError):
        run(root)
    assert calls == [] and not (root / "finished.json").exists()


def test_incomplete_pair_cannot_report(clocked, monkeypatch):
    root, *_ = clocked
    monkeypatch.setattr(drc_report, "baseline", pair.baseline)
    with pytest.raises((ValueError, FileNotFoundError)):
        drc_report.compare(root, root)


def test_duplicate_plan_or_changed_conditions(parents, tmp_path):
    n, d = parents
    base = tmp_path / "base"
    base.mkdir()
    c = read(BASE / "workflow_configuration.json")
    for k, doc in [("network", n), ("dataset", d), ("configuration", c)]:
        save(base / (k + ".json"), doc)
    child, config = pair.expected(base, 1)
    label = "plus-" + child["dataset_version"][:16]
    member = tmp_path / label
    member.mkdir()
    plan = {"test": "fixture"}
    save(member / "plan.json", plan)
    save(tmp_path / "pair.json", {"delta_eV": 0.01, "members": {"plus": {"run_id": label, "plan_sha256": sha256_json(plan)}}})
    save(member / "dataset.json", child)
    config["partial_pressure_bar"]["H2-g"] = 2
    save(member / "configuration.json", config)
    with pytest.raises(ValueError, match="conditions"):
        pair.check_member(tmp_path, base, "plus", 1)
    with pytest.raises(ValueError, match="Conflicting immutable"):
        pair.put(member / "configuration.json", c)


def test_launch_timeout_is_bounded(tmp_path, monkeypatch):
    calls = []

    class Proc:
        pid = 1234

        def wait(self, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise subprocess.TimeoutExpired("mock", timeout)
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Proc())
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    with pytest.raises(subprocess.TimeoutExpired):
        point.launch(tmp_path, "mock", timeout=13.5)
    assert calls == [13.5, 10]


@pytest.mark.parametrize("label,sign", [("plus", 1), ("minus", -1)])
@pytest.mark.parametrize("phase,step", [("phase3_2_0", 0.01), ("phase3_2_0_1", 0.005)])
def test_offline_raw_native_replay(parents, label, sign, phase, step, tmp_path):
    from scripts.baseline_mkm.results import read_single_point
    from scripts.baseline_mkm.single_point_result import validate_result

    n, parent = parents
    output = REPORTS / phase
    member = output / label
    receipt = read(member / "accepted.json")
    report = read(output / "result.json")
    case = report["cases"][label]
    assert sha256_file(member / "accepted.json") == case["run_receipt_sha256"]
    assert sha256_file(member / "data1.mat") == receipt["output_hashes"]["runtime/result_phase25/data1.mat"]
    dataset = derivative(n, parent, sign, step)
    config = dict(read(BASE / "workflow_configuration.json"), dataset_version=dataset["dataset_version"])
    files, adapter = point.qualify(n, dataset, config)
    assert sha256_file(save(tmp_path / "dataset.json", dataset)) == case["source_hashes"]["dataset"]
    assert sha256_file(save(tmp_path / "config.json", config)) == case["source_hashes"]["configuration"]
    assert adapter["files"][point.INPUT] == receipt["output_hashes"]["runtime/result_phase25/Input_phase25_1"]
    raw = read_single_point(member / "data1.mat", member / "native_log_extract.txt")
    result = validate_result(
        dataset, config, adapter["validation"], raw, (member / "native_log_extract.txt").read_text(), files[point.INPUT]
    )
    result.update(
        run_id=case["run_id"],
        question_id=read(BASE / "benchmark_manifest.json")["question_id"],
        scope="synthetic_benchmark",
        plan_sha256=case["source_hashes"]["plan"],
        output_hashes=receipt["output_hashes"],
    )
    assert sha256_file(save(tmp_path / "result.json", result)) == receipt["result_sha256"] == case["source_hashes"]["result"]
    assert result["overall_rate"] == pytest.approx(case["net_tof_per_site_pair_s"])
    assert case["perturbation"] == dataset["ts_perturbation"]
    assert receipt["convergence"] == "converged" and receipt["scientific_validity"] == "validated_within_scope"


@pytest.mark.parametrize("phase", ["phase3_2_0", "phase3_2_0_1"])
def test_published_contract_and_independent_drc(phase):
    from jsonschema import Draft202012Validator

    output = REPORTS / phase
    report = read(output / "result.json")
    schema = read(REPORTS.parents[1] / "configs/kinetics/mkm_drc.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(report)
    c = report["cases"]
    assert c["baseline"]["source_hashes"]["result"] == sha256_file(BASE / "result.json")
    assert c["baseline"]["dataset_version"] == PARENT
    assert central_difference(
        *(c[k]["product_based_tof_per_site_pair_s"] for k in ("baseline", "plus", "minus")), report["temperature_K"], report["delta_eV"]
    ) == pytest.approx(report["drc"])
    assert not validator.is_valid(dict(report, cases={"baseline": c["baseline"], "plus": c["plus"]}))
    assert report["fe110"]["drc"] is None and report["fe110"]["gaps"]
    assert sum(c[k]["runtime_s"] for k in ("plus", "minus")) <= report["budget"]["elapsed_s"] <= 480


def test_changed_budget_receipt(clocked):
    root, *_ = clocked
    save(root / "finished.json", dict(pair_sha256=sha256_json(read(root / "pair.json")), elapsed_s=300, remaining_s=400))
    with pytest.raises(ValueError, match="budget"):
        pair.verified_finish(root, read(root / "pair.json"))


def test_baseline_must_match_accepted_receipt(monkeypatch):
    receipt = read(BASE / "benchmark_manifest.json")
    archived = read(REPORTS / "phase3_1/closed_cycle/analysis.json")
    monkeypatch.setattr(records, "accepted", lambda _: (receipt, archived))
    assert pair.baseline(Path("synthetic")) == (receipt, archived)
    receipt["approval_reference"] = "0" * 64
    with pytest.raises(ValueError, match="approval_reference"):
        pair.baseline(Path("synthetic"))


def test_rejected_or_unconverged_never_used(monkeypatch):
    monkeypatch.setattr(point, "status", lambda _: {"stage": "REJECTED", "convergence": "unknown"})
    with pytest.raises(ValueError, match="expected accepted point"):
        pair.accepted(Path("failed"))


def test_partial_resume_reuses_accepted_plus(clocked):
    root, states, calls, _ = clocked
    states["plus"] = "ACCEPTED"
    save(root / "started.json", dict(utc_epoch_s=1000, pair_sha256=sha256_json(read(root / "pair.json"))))
    run(root)
    assert calls == ["minus"]


def test_out_of_range_diagnostic_retains_signed_result():
    r = read(REPORTS / "phase3_2_0/result.json")
    t = r["temperature_K"]
    for label, sign in pair.SIGNS:
        r["cases"][label]["net_tof_per_site_pair_s"] = r["cases"]["baseline"]["net_tof_per_site_pair_s"] * exp(sign * 0.01 / (KB * t))
    r.update(drc=-1, independent_product_drc=-1, outside_zero_to_one=True)
    text = drc_report.render(r)
    assert "DRC = -1" in text and "One-sided slopes are -1" in text


def test_half_step_changes_only_selected_gibbs_barriers_and_rates(parents):
    n, parent = parents
    for sign in (1, -1):
        child = derivative(n, parent, sign, 0.005)
        assert child == reproduce(n, child)
        for old, new in zip(parent["reactions"], child["reactions"], strict=True):
            if old["reaction_id"] != REACTION:
                assert old == new
                continue
            assert new["energies"]["electronic_ev"] == old["energies"]["electronic_ev"]
            for side in ("forward", "reverse"):
                assert new["energies"]["gibbs_ev"][side] - old["energies"]["gibbs_ev"][side] == pytest.approx(sign * 0.005)
                assert new["rates"][side]["prefactor_at_unit_activity_s^-1"] == old["rates"][side]["prefactor_at_unit_activity_s^-1"]
            assert old["energies"]["gibbs_ev"]["reaction"] == new["energies"]["gibbs_ev"]["reaction"]
            assert abs(new["equilibrium"]["log_ratio_residual"]) < 1e-12
    with pytest.raises(ValueError, match="step size"):
        derivative(n, parent, 1, 0.0025)


def step_reports():
    return [read(REPORTS / phase / "result.json") for phase in ("phase3_2_0", "phase3_2_0_1")]


def test_project_step_stability_and_one_sided_signs():
    from scripts.baseline_mkm.drc_step_size import validation

    coarse, fine = step_reports()
    v = validation(coarse, fine, sha256_file(REPORTS / "phase3_2_0/result.json"))
    assert v == fine["step_size_validation"]
    assert v["passed"] and v["next_pair_proposal"] is None
    assert v["absolute_difference"] == pytest.approx(0.00044145429)
    assert v["tolerance"] == pytest.approx(0.00203452256)
    for label, expected in (("coarse", (0.04712913, 0.03513468)), ("fine", (0.04367290, 0.03770800))):
        assert (v[label]["positive_side"], v[label]["negative_side"]) == pytest.approx(expected, abs=5e-8)


@pytest.mark.parametrize("field", ["baseline", "normalization", "temperature_K", "delta_eV"])
def test_incompatible_step_comparison_rejected(field):
    from scripts.baseline_mkm.drc_step_size import validation

    coarse, fine = step_reports()
    if field == "baseline":
        fine["cases"]["baseline"]["run_id"] = "unrelated"
    else:
        fine[field] = coarse["delta_eV"] if field == "delta_eV" else None
    with pytest.raises(ValueError):
        validation(coarse, fine, "a" * 64)


def test_failed_step_criterion_only_proposes_quarter_step():
    from scripts.baseline_mkm.drc_step_size import validation

    coarse, fine = step_reports()
    b = fine["cases"]["baseline"]["net_tof_per_site_pair_s"]
    for label in ("plus", "minus"):
        fine["cases"][label]["net_tof_per_site_pair_s"] = b
    fine.update(drc=0, independent_product_drc=0)
    v = validation(coarse, fine, "a" * 64)
    assert not v["passed"] and v["tolerance"] == 0.002
    assert v["next_pair_proposal"]["delta_eV"] == 0.0025
    assert v["next_pair_proposal"]["execution"] == "not_started"


def test_existing_pair_rejects_new_step_before_preparation(tmp_path, monkeypatch):
    save(tmp_path / "pair.json", {"delta_eV": 0.01})
    monkeypatch.setattr(pair, "baseline", lambda _: ({}, {}))
    with pytest.raises(ValueError, match="different step size"):
        pair.prepare(tmp_path, tmp_path, 0.005)
    assert list(tmp_path.iterdir()) == [tmp_path / "pair.json"]


def test_pair_record_functions_keep_the_legacy_imports():
    for name in ("accepted", "baseline", "expected", "planned_inputs", "check_member", "put", "verified_finish"):
        assert getattr(pair, name) is getattr(records, name)
    for name in ("accepted", "baseline", "check_member", "put", "verified_finish"):
        assert getattr(drc_report, name) is getattr(records, name)
    for name in ("REPORTS", "OPTIONS", "BUDGET", "SIGNS"):
        assert getattr(pair, name) == getattr(records, name)


def test_pair_record_publication_reuses_equal_json_without_rewriting(tmp_path):
    path = tmp_path / "record.json"
    pair.put(path, {"a": 1, "b": 2})
    assert read(path) == {"a": 1, "b": 2}
    path.write_bytes(b'{ "b": 2, "a": 1 }\r\n')
    original = path.read_bytes()
    pair.put(path, {"a": 1, "b": 2})
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match="Conflicting immutable artifact"):
        pair.put(path, {"a": 2, "b": 2})
    assert path.read_bytes() == original
