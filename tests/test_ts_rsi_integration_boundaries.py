"""Synthetic CLI replies; full repository handler/workflow, never path generation."""
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json
from scripts.ts_strategy_engine import rsi_advice, workflow
from tests.test_ts_rsi_integration import reference, run_plan, select_policy, trial as synthetic_trial
from tests.test_ts_strategy_engine import raw_contract


trial = synthetic_trial


def test_disabled_rsi_keeps_existing_initialization_control_flow(trial, monkeypatch):
    trial["request"] = replace(trial["request"], initialize_path=True)
    reached = []
    monkeypatch.setattr(workflow, "_initialize_path", lambda *args: reached.append("initialize"))
    plan = run_plan(trial, enabled=False)
    assert reached == ["initialize"] and "workflow_review" not in plan
    assert plan["automatic_submission"] is False
    assert not (trial["request"].workdir / "rsi").exists()


@pytest.mark.parametrize("failure", ["hash", "offline_initialize", "offline_rebuild", "offline_both"])
def test_explicit_rejection_stops_full_handler_before_path_preparation(trial, monkeypatch, failure):
    request = replace(trial["request"], initialize_path=failure != "offline_rebuild",
                      rebuild=failure in {"offline_rebuild", "offline_both"})
    trial["request"] = request
    select_policy(trial)
    reached = []
    monkeypatch.setattr(workflow, "_initialize_path", lambda *args: reached.append("initialize"))
    monkeypatch.setattr(workflow, "generate_path", lambda *args, **kwargs: reached.append("generate"))
    extra = ["--rsi-request-sha256", "0" * 64] if failure == "hash" else []
    with pytest.raises(ValueError, match="RSI"):
        run_plan(trial, extra_args=extra)
    assert reached == []
    assert not (request.workdir / "ts_strategy.json").exists()
    assert not (request.workdir / "rsi_integration.json").exists()
    records = list(request.workdir.glob("rsi/*/invocation-result.json"))
    assert len(records) == 1
    rejection = load_json_object(records[0])
    assert rejection["status"] == "unavailable" and rejection["producer_launch_attempted"] is False
    if failure == "hash":
        assert rejection["request"]["sha256"] == "0" * 64
        assert "missing or stale evidence" in rejection["reason"] and str(trial["spec"]) in rejection["reason"]
    else:
        assert "cannot prepare or rebuild" in rejection["reason"]


@pytest.fixture
def indirect_trial(trial):
    directory = trial["root"] / "contract-inputs"
    directory.mkdir()
    waypoints = [directory / name for name in ("first.POSCAR", "second.POSCAR", "explicit.POSCAR")]
    for path in waypoints:
        path.write_bytes(trial["request"].initial.read_bytes())
    constraints = write_json(directory / "constraints.json", {"synthetic": "original"})
    payload = raw_contract()
    payload.update(waypoint_files=["first.POSCAR", "second.POSCAR"],
                   retrieval_constraints={"constraints_file": "constraints.json"})
    contract_path = directory / "reaction.yaml"
    contract_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    trial["request"] = replace(trial["request"], contract=contract_path)
    trial.update(waypoints=waypoints, indirect_constraints=constraints)
    select_policy(trial)
    return trial


@pytest.mark.parametrize("source", ["indirect_waypoint", "indirect_constraints", "string_constraints",
                                     "explicit_waypoint", "explicit_constraints"])
def test_effective_path_source_change_rejects_full_workflow(indirect_trial, monkeypatch, source):
    env = indirect_trial
    request = env["request"]
    changed = env["waypoints"][0] if source == "indirect_waypoint" else env["indirect_constraints"]
    if source == "string_constraints":
        payload = yaml.safe_load(request.contract.read_text(encoding="utf-8"))
        payload["retrieval_constraints"] = "constraints.json"
        request.contract.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    if source == "explicit_waypoint":
        request = replace(request, waypoint=(Path("explicit.POSCAR"),))
        changed = env["waypoints"][2]
    if source == "explicit_constraints":
        changed = write_json(env["root"] / "explicit.json", {"synthetic": "override"})
        request = replace(request, constraints=changed)
    env["request"] = request
    select_policy(env)
    before_contract = sha256_file(request.contract)
    original = rsi_advice.prepare_advice
    reached = []
    def prepare(*args, **kwargs):
        context = original(*args, **kwargs)
        assert context["status"] == "available"
        changed.write_bytes(changed.read_bytes() + b" ")
        return context
    monkeypatch.setattr(rsi_advice, "prepare_advice", prepare)
    monkeypatch.setattr(workflow, "_initialize_path", lambda *args: reached.append("initialize"))
    monkeypatch.setattr(workflow, "generate_path", lambda *args, **kwargs: reached.append("generate"))
    with pytest.raises(ValueError, match="planning inputs changed"):
        run_plan(env)
    assert sha256_file(request.contract) == before_contract
    assert reached == [] and not (request.workdir / "ts_strategy.json").exists()
    assert not (request.workdir / "rsi_integration.json").exists()
    rejected = load_json_object(request.workdir / "rsi_rejection.json")
    assert rejected["status"] == "unavailable" and "items" not in rejected


def test_effective_bindings_share_path_resolution_and_preserve_order(indirect_trial):
    env = indirect_trial
    request = replace(env["request"], waypoint=(Path("explicit.POSCAR"),))
    env["request"] = request
    bound = rsi_advice.plan_inputs(request)
    normalized = workflow.load_contract(request.contract)
    resolved = workflow._resolve_waypoints(request.contract, normalized, request.waypoint)
    assert resolved == tuple(env["waypoints"])
    assert [bound["files"][f"waypoint_{i}"] for i in range(3)] == [reference(path) for path in resolved]
    assert bound["files"]["constraints"] == reference(workflow._resolve_constraints(request, normalized))
    select_policy(env)
    plan = run_plan(env)
    assert plan["workflow_review"]["status"] == "ADOPTED_FOR_REVIEW_PLANNING"
    assert all(item["check_status"] == "PENDING" for item in plan["workflow_review"]["items"])
    receipt = load_json_object(request.workdir / "rsi_integration.json")
    assert receipt["execution"] is None and receipt["outcome"] is None


@pytest.mark.parametrize("source", ["indirect_waypoint", "indirect_constraints"])
def test_stale_indirect_input_rejects_before_producer_launch(indirect_trial, source):
    env = indirect_trial
    changed = env["waypoints"][0] if source == "indirect_waypoint" else env["indirect_constraints"]
    changed.write_bytes(changed.read_bytes() + b" ")
    with pytest.raises(ValueError, match="current task/plan inputs"):
        run_plan(env)
    rejected = load_json_object(next(env["request"].workdir.glob("rsi/*/invocation-result.json")))
    assert rejected["producer_launch_attempted"] is False
    assert not (env["request"].workdir / "ts_strategy.json").exists()


@pytest.mark.parametrize("missing", [False, True])
def test_overridden_constraints_are_not_effective_inputs(indirect_trial, monkeypatch, missing):
    env = indirect_trial
    explicit = write_json(env["root"] / "explicit.json", {"synthetic": "explicit constraints"})
    env["request"] = replace(env["request"], constraints=explicit)
    select_policy(env)
    original = rsi_advice.prepare_advice
    def prepare(*args, **kwargs):
        context = original(*args, **kwargs)
        if missing:
            env["indirect_constraints"].unlink()  # Only this temporary synthetic fixture.
        else:
            env["indirect_constraints"].write_bytes(b"changed but overridden")
        return context
    monkeypatch.setattr(rsi_advice, "prepare_advice", prepare)
    before = sha256_json(rsi_advice.plan_inputs(env["request"]))
    plan = run_plan(env)
    assert sha256_json(rsi_advice.plan_inputs(env["request"])) == before
    assert rsi_advice.plan_inputs(env["request"])["files"]["constraints"] == reference(explicit)
    assert workflow._resolve_constraints(env["request"], workflow.load_contract(env["request"].contract)) == explicit
    assert plan["workflow_review"]["execution_authorized"] is False
    assert plan["workflow_review"]["scientific_review_completed"] is False
