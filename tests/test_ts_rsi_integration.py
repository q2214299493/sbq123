"""Synthetic CLI transport, real main workflow and temporary registry; no model/DFT."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import subprocess

import numpy as np
import pytest
import yaml

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, source_file_manifest, write_json
from scripts.neb_agent.utils_structure import Poscar, read_poscar, write_poscar
from scripts.ts_strategy_engine import cli, rsi_advice, strategy_learning as learning, workflow
from scripts.ts_strategy_engine.learning_store import get_event
from scripts.ts_strategy_engine.learning_evidence import attempt_input_hashes, bind_files
from tests.test_ts_strategy_engine import ROOT, contract, database


ACTUAL_RUNTIME_CHECK = rsi_advice._runtime


def reference(path):
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


@pytest.fixture
def trial(tmp_path, monkeypatch):
    """The producer is deliberately synthetic; it only publishes saved fixture replies."""
    backend = tmp_path / "synthetic-cli"
    package = backend / "scripts/ts_strategy_engine"
    package.mkdir(parents=True)
    (backend / "scripts/__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    producer = package / "learning_cli.py"
    producer.write_text('''import json, sys
from pathlib import Path
assert sys.argv[1] == "advise-next"
def value(flag): return sys.argv[sys.argv.index(flag) + 1]
root = Path(__file__).resolve().parents[2]
if (root / "reject").exists():
    sys.stderr.write("synthetic producer rejection")
    raise SystemExit(2)
reply = json.loads((root / (value("--workflow-policy") + ".json")).read_text(encoding="utf-8"))
with Path(value("--report")).open("x", encoding="utf-8") as handle:
    json.dump(reply, handle)
print("synthetic no-model CLI transport")
''', encoding="utf-8")
    monkeypatch.setattr(rsi_advice, "_runtime", lambda: {
        "root": str(backend), "revision": rsi_advice.RSI_REVISION,
        "interface": "synthetic_cli_transport", "synthetic_fixture": True,
        "source_files": source_file_manifest([producer]), "model_calls": 0})
    db = database(tmp_path / "synthetic-registry.sqlite3")
    structure = Poscar("synthetic Fe C O", np.eye(3) * 10, ["Fe", "C", "O"], [1, 1, 1],
                       np.array([[0., 0., 0.], [.2, 0., .2], [.4, 0., .2]]),
                       True, [("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")])
    initial, final = tmp_path / "IS.POSCAR", tmp_path / "FS.POSCAR"
    write_poscar(initial, structure)
    write_poscar(final, structure)
    reaction = tmp_path / "reaction.yaml"
    reaction.write_text(yaml.safe_dump(contract(), sort_keys=False), encoding="utf-8")
    request = workflow.PlanRequest(initial, final, reaction, tmp_path / "plan", db,
                                   ROOT / "configs/ts_strategy_engine/families.yaml",
                                   ROOT / "configs/neb_agent/default_thresholds.yaml")
    source = write_json(tmp_path / "synthetic-evidence.json", {"symptom": "saved path underresolution"})
    case = {"case_id": "synthetic-case", "group_id": "co_split", "question": "Synthetic geometry review?",
            "evidence": [{"evidence_id": "symptom", "pointer": "/symptom", "value": "saved path underresolution",
                          "source_sha256": sha256_file(source)}]}
    case["input_sha256"] = sha256_json(case)
    public = write_json(tmp_path / "public.json", {"schema_version": 2, "cases": [case]})
    diagnosis = {"case_id": case["case_id"], "input_sha256": case["input_sha256"], "failure_class": "geometry",
                 "causal_status": "hypothesis", "causal_claim": "Synthetic resolution hypothesis",
                 "causal_evidence_ids": ["symptom"], "evidence_ids": ["symptom"],
                 "next_review": learning.policy()["failure_routes"]["geometry"]}
    answers = write_json(tmp_path / "answers.json", {"schema_version": 2,
                         "public_sha256": sha256_json(load_json_object(public)), "answers": [diagnosis]})
    store = tmp_path / "synthetic-store"
    (store / "policies").mkdir(parents=True)
    record = {"schema_version": 1, "kind": "baseline", "scope": "synthetic-integration",
              "provenance": "synthetic", "inputs": {"public": reference(public), "answers": reference(answers)},
              "orders": {"geometry": ["interpolation_strategy", "initial_images"], "optimizer": ["candidate_method"]},
              "observations": [{**reference(source), "pointer": "/symptom", "value": "saved path underresolution"}]}
    env = {"root": tmp_path, "backend": backend, "store": store, "request": request,
           "record": record, "public": public, "answers": answers, "source": source,
           "case": case, "diagnosis": diagnosis}
    select_policy(env)
    return env


def select_policy(env, *, reverse=False, unknown=False):
    record = json.loads(json.dumps(env["record"]))
    if reverse:
        parent = sha256_json(record)
        write_json(env["store"] / "policies" / f"{parent}.json", record)
        record.update(kind="candidate", parent_id=parent, rationale="Synthetic order-only candidate")
        record["orders"]["geometry"].reverse()
    identity = sha256_json(record)
    write_json(env["store"] / "policies" / f"{identity}.json", record)
    diagnosis = dict(env["diagnosis"])
    if unknown:
        diagnosis.update(causal_status="unknown", causal_claim=None, causal_evidence_ids=[])
        write_json(env["answers"], {"schema_version": 2,
                   "public_sha256": sha256_json(load_json_object(env["public"])), "answers": [diagnosis]})
        record["inputs"]["answers"] = reference(env["answers"])
        identity = sha256_json(record)
        write_json(env["store"] / "policies" / f"{identity}.json", record)
    row = {k: diagnosis[k] for k in ("case_id", "failure_class", "causal_status", "causal_claim",
                                    "causal_evidence_ids", "next_review")}
    row.update(group_id="co_split", review_focus="collect_cause_specific_evidence" if unknown else "test_specific_causal_claim",
               ts_strategy_fields_to_review=[] if unknown else record["orders"]["geometry"],
               requires_owning_review=True, automatic_execution=False)
    reply = {"schema_version": 1, "status": "ADVISORY_ONLY_NOT_AUTHORIZED",
             "public_sha256": sha256_json(load_json_object(env["public"])),
             "answers_sha256": sha256_file(env["answers"]), "policy_sha256": sha256_file(learning.POLICY),
             "public_source_files_reverified": False, "causal_claims_scientifically_validated": False,
             "ts_strategy_changes_authorized": False, "recommendations": [row], "workflow_strategy": {
                 "policy_id": identity, "scope": record["scope"], "mode": "offline_evaluation", "provenance": "synthetic"}}
    write_json(env["backend"] / f"{identity}.json", reply)
    spec = {"schema_version": 1, "task_id": "co_split", "case_id": "synthetic-case",
            "rsi_revision": rsi_advice.RSI_REVISION, "store": str(env["store"]), "policy_id": identity,
            "scope": record["scope"], "plan_inputs": rsi_advice.plan_inputs(env["request"]), "offline_evaluation": True}
    env["spec"] = write_json(env["root"] / "rsi-request.json", spec)
    env["identity"] = identity


def run_plan(env, name="plan", *, enabled=True, extra_args=()):
    request = env["request"]
    args = ["plan", "--is", str(request.initial), "--fs", str(request.final), "--contract", str(request.contract),
            "--workdir", str(env["root"] / name), "--database", str(request.database)]
    for field, flag in (("initialize_path", "--initialize-path"), ("rebuild", "--rebuild")):
        if getattr(request, field):
            args.append(flag)
    if request.constraints is not None:
        args += ["--constraints", str(request.constraints)]
    for waypoint in request.waypoint:
        args += ["--waypoint", str(waypoint)]
    if enabled:
        args += ["--rsi-request", str(env["spec"]), "--rsi-request-sha256", sha256_file(env["spec"])]
    args += list(extra_args)
    parsed = cli.parser().parse_args(args)
    parsed.handler(parsed)
    return load_json_object(env["root"] / name / "ts_strategy.json")


def scientific_plan(result):
    return {k: v for k, v in result.items() if k != "workflow_review"}


def test_real_workflow_consumes_synthetic_cli_advice_and_changes_review_plan(trial, monkeypatch):
    received, original = [], workflow.plan
    def observe(request):
        received.append(request.rsi_advice)
        return original(request)
    monkeypatch.setattr(workflow, "plan", observe)
    p0 = run_plan(trial, "p0")
    select_policy(trial, reverse=True)
    p1 = run_plan(trial, "p1")
    assert all(c["status"] == "available" and c["producer_exit_code"] == 0 for c in received)
    assert [c["field"] for c in p0["workflow_review"]["items"]] == ["interpolation_strategy", "initial_images"]
    assert [c["field"] for c in p1["workflow_review"]["items"]] == ["initial_images", "interpolation_strategy"]
    assert p1["workflow_review"]["workflow_strategy"]["policy_id"] == trial["identity"]
    assert all(c["check_status"] == "PENDING" for c in p1["workflow_review"]["items"])
    assert p1["workflow_review"]["scientific_review_completed"] is False
    assert scientific_plan(p0) == scientific_plan(p1)


def test_explicit_unavailable_stops_and_default_call_has_no_rsi_side_effects(trial, monkeypatch):
    baseline = run_plan(trial, "disabled", enabled=False)
    assert "workflow_review" not in baseline
    assert not (trial["root"] / "disabled/rsi").exists()
    assert not (trial["root"] / "disabled/rsi_integration.json").exists()
    def unavailable():
        raise OSError("synthetic unavailable runtime")
    monkeypatch.setattr(rsi_advice, "_runtime", unavailable)
    with pytest.raises(ValueError, match="synthetic unavailable runtime"):
        run_plan(trial)
    assert not (trial["request"].workdir / "ts_strategy.json").exists()
    receipt = load_json_object(next(trial["request"].workdir.glob("rsi/*/invocation-result.json")))
    assert receipt["status"] == "unavailable" and receipt["producer_launch_attempted"] is False
    assert run_plan(trial, "explicitly-disabled", enabled=False) == baseline


@pytest.mark.parametrize("field,value", [("rsi_revision", "0" * 40), ("schema_version", 2),
    ("policy_id", "0" * 64), ("task_id", "wrong-task"), ("scope", "wrong-scope")])
def test_wrong_policy_version_task_or_scope_rejects_explicit_request(trial, field, value):
    baseline = run_plan(trial, "disabled", enabled=False)
    spec = load_json_object(trial["spec"])
    spec[field] = value
    write_json(trial["spec"], spec)
    with pytest.raises(ValueError, match="RSI"):
        run_plan(trial)
    receipt = load_json_object(next(trial["request"].workdir.glob("rsi/*/invocation-result.json")))
    assert receipt["status"] == "unavailable" and receipt["task_id"] == "co_split"
    assert not (trial["request"].workdir / "ts_strategy.json").exists()
    assert run_plan(trial, "explicitly-disabled", enabled=False) == baseline


def test_stale_request_hash_and_incomplete_evidence_stop(trial):
    with pytest.raises(ValueError, match="RSI"):
        rsi_advice.prepare_advice(trial["request"], trial["spec"], "0" * 64)
    stale = load_json_object(next(trial["request"].workdir.glob("rsi/*/invocation-result.json")))
    assert stale["status"] == "unavailable" and stale["producer_launch_attempted"] is False
    trial["source"].unlink()  # Synthetic temporary fixture only.
    with pytest.raises(ValueError, match="RSI"):
        run_plan(trial, "missing-source")
    assert not (trial["root"] / "missing-source/ts_strategy.json").exists()


@pytest.mark.parametrize("damage", ["evidence", "advice", "policy"])
def test_changed_sources_between_invocation_and_consumption_cannot_be_adopted(trial, monkeypatch, damage):
    original = rsi_advice.prepare_advice
    def prepare(*args):
        context = original(*args)
        assert context["status"] == "available"
        path = {"evidence": trial["source"], "advice": Path(context["advice"]["path"]),
                "policy": trial["store"] / "policies" / f"{trial['identity']}.json"}[damage]
        path.write_bytes(path.read_bytes() + b" ")
        return context
    monkeypatch.setattr(rsi_advice, "prepare_advice", prepare)
    with pytest.raises(ValueError, match="RSI advice consumption rejected"):
        run_plan(trial)
    result = load_json_object(trial["request"].workdir / "rsi_rejection.json")
    assert result["status"] == "unavailable" and "items" not in result
    assert not (trial["request"].workdir / "ts_strategy.json").exists()


@pytest.mark.parametrize("damage", ["authority", "field", "diagnosis", "schema"])
def test_invalid_producer_advice_never_enters_review_plan(trial, damage):
    path = trial["backend"] / f"{trial['identity']}.json"
    report = load_json_object(path)
    if damage == "authority":
        report["ts_strategy_changes_authorized"] = True
    elif damage == "field":
        report["recommendations"][0]["ts_strategy_fields_to_review"] = ["shell"]
    elif damage == "diagnosis":
        report["recommendations"][0]["causal_status"] = "confirmed"
    else:
        report["schema_version"] = 2
    write_json(path, report)
    with pytest.raises(ValueError, match="RSI"):
        run_plan(trial)
    assert not (trial["request"].workdir / "ts_strategy.json").exists()


def test_unknown_cause_keeps_evidence_route_and_has_no_ts_parameter_hints(trial):
    select_policy(trial, unknown=True)
    result = run_plan(trial)
    review = result["workflow_review"]
    assert review["causal_status"] == "unknown" and review["items"] == []
    assert review["review_focus"] == "collect_cause_specific_evidence"
    assert review["automatic_execution"] is False and result["automatic_submission"] is False


@pytest.mark.parametrize("failure", ["reject", "timeout"])
def test_producer_rejection_or_timeout_is_recorded_and_stops_explicit_workflow(trial, monkeypatch, failure):
    if failure == "reject":
        (trial["backend"] / "reject").write_text("synthetic", encoding="utf-8")
    else:
        def timeout(*args): raise subprocess.TimeoutExpired("synthetic advise-next", 30)
        monkeypatch.setattr(rsi_advice, "_run", timeout)
    with pytest.raises(ValueError, match="RSI"):
        run_plan(trial)
    receipt = load_json_object(next(trial["request"].workdir.glob("rsi/*/invocation-result.json")))
    assert receipt["status"] == "unavailable"
    assert receipt["producer_exit_code"] == (2 if failure == "reject" else None)
    assert receipt["producer_launch_attempted"] is True
    assert not (trial["request"].workdir / "ts_strategy.json").exists()


def test_advice_cannot_bypass_actual_endpoint_stop_or_invoke_calculations(trial, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError("scientific execution forbidden")
    monkeypatch.setattr(workflow, "_initialize_path", forbidden)
    from scripts.neb_agent import submission
    monkeypatch.setattr(submission, "submit", forbidden)
    run_plan(trial, "safe")
    structure = read_poscar(trial["request"].final)
    write_poscar(trial["request"].final, replace(structure, cell=structure.cell * 1.1))
    spec = load_json_object(trial["spec"])
    spec["plan_inputs"] = rsi_advice.plan_inputs(trial["request"])
    write_json(trial["spec"], spec)
    with pytest.raises(SystemExit) as stopped:
        run_plan(trial)
    assert stopped.value.code == 2
    assert not (trial["root"] / "plan/ts_strategy.json").exists()
    assert load_json_object(trial["root"] / "plan/endpoint_check.json")["status"] == "STOP"


def test_invocation_adoption_plan_and_existing_outcome_binding(trial):
    before = sha256_file(trial["request"].database)
    plan = run_plan(trial)
    assert sha256_file(trial["request"].database) == before
    path = trial["root"] / "plan/rsi_integration.json"
    receipt = load_json_object(path)
    invocation, adoption = receipt["invocation"], receipt["adoption"]
    assert invocation["invocation_id"] == adoption["invocation_id"]
    assert invocation["advice"] == adoption["advice"]
    assert receipt["plan"] == reference(trial["root"] / "plan/ts_strategy.json")
    assert adoption == plan["workflow_review"] and receipt["task_id"] == "co_split"
    assert invocation["runtime"]["synthetic_fixture"] is True
    assert receipt["execution"] is None and receipt["outcome"] is None
    # Existing VASP attempt.inputs carries provenance without changing retry identity.
    # A method-only historical template need not contain an image count. This
    # explicit synthetic settings source is for the not-run lifecycle fixture.
    settings_source = write_json(trial["root"] / "synthetic-settings.json", {
        "initial_images": 5, "interpolation_strategy": plan["interpolation_strategy"], "candidate_method": "ordinary_neb"})
    settings = load_json_object(settings_source)
    variant = learning.capture_baseline(trial["request"].database, {"task_id": "co_split", "cases": ["co_split"],
        "attempt_budget": 1, "settings": settings, "sources": {"current": str(settings_source)}})
    inputs = {"POSCAR": str(trial["request"].initial)}
    for name, text in {"INCAR": "NSW=0\nIBRION=-1\n", "KPOINTS": "synthetic\n0\nGamma\n1 1 1\n0 0 0\n",
                       "POTCAR.spec": "synthetic metadata only", "script.lsf": "#!/bin/sh\n# synthetic not submitted\n"}.items():
        source = trial["root"] / name
        source.write_text(text, encoding="utf-8")
        inputs[name] = str(source)
    original_hashes = attempt_input_hashes("diagnostic_static", bind_files(inputs))
    inputs.update(workflow_plan=str(trial["root"] / "plan/ts_strategy.json"), rsi_integration=str(path))
    assert attempt_input_hashes("diagnostic_static", bind_files(inputs)) == original_hashes
    attempt = learning.start_attempt(trial["request"].database, {"attempt_id": "synthetic-not-run", "variant_id": variant,
        "task_id": "co_split", "kind": "diagnostic_static", "inputs": inputs, "parent_attempt_id": None})
    observed = write_json(trial["root"] / "synthetic-not-run.json", {"status": "NOT_RUN"})
    learning.record_outcome(trial["request"].database, attempt, {"status": "unknown", "failure_class": "unknown",
        "root_cause_status": "unknown", "deterministic": False, "reviewer": "synthetic fixture",
        "observations": [{**reference(observed), "pointer": "/status", "value": "NOT_RUN"},
                         {**reference(path), "pointer": "/invocation/invocation_id", "value": invocation["invocation_id"]}],
        "costs": {}, "ts_template_id": None})
    saved = get_event(trial["request"].database, "attempt", attempt)
    assert saved["inputs"]["rsi_integration"] == reference(path)
    assert get_event(trial["request"].database, "outcome", attempt)["status"] == "unknown"


def test_offline_advice_does_not_authorize_path_preparation(trial):
    request = replace(trial["request"], initialize_path=True)
    spec = load_json_object(trial["spec"])
    spec["plan_inputs"] = rsi_advice.plan_inputs(request)
    write_json(trial["spec"], spec)
    with pytest.raises(ValueError, match="cannot prepare or rebuild"):
        rsi_advice.prepare_advice(request, trial["spec"], sha256_file(trial["spec"]))
    context = load_json_object(next(request.workdir.glob("rsi/*/invocation-result.json")))
    assert context["status"] == "unavailable"
    assert "cannot prepare or rebuild" in context["reason"]


@pytest.mark.parametrize("dirty", [False, True])
def test_actual_source_admission_rejects_wrong_head_or_dirty_tree(trial, monkeypatch, dirty):
    monkeypatch.setattr(rsi_advice, "RSI_ROOT", trial["backend"])
    monkeypatch.setattr(rsi_advice, "_runtime", ACTUAL_RUNTIME_CHECK)
    def git_probe(argv, cwd):
        assert argv[0] == "git" and cwd == trial["backend"]
        data = ((rsi_advice.RSI_REVISION if dirty else "0" * 40).encode() if argv[1] == "rev-parse"
                else (b" M scripts/fixture.py" if dirty else b""))
        return subprocess.CompletedProcess(argv, 0, data, b"")
    monkeypatch.setattr(rsi_advice, "_run", git_probe)
    with pytest.raises(ValueError, match="source version"):
        run_plan(trial)
    context = load_json_object(next(trial["request"].workdir.glob("rsi/*/invocation-result.json")))
    assert context["status"] == "unavailable" and "source version" in context["reason"]


@pytest.mark.parametrize("context", [{"status": "available"}, "not-an-invocation"])
def test_malformed_direct_consumer_input_stops_without_a_plan(trial, context):
    request = replace(trial["request"], rsi_advice=context)
    with pytest.raises(ValueError, match="RSI advice consumption rejected"):
        workflow.plan(request)
    result = load_json_object(request.workdir / "rsi_rejection.json")
    assert result["status"] == "unavailable" and result["automatic_execution"] is False
    assert not (request.workdir / "ts_strategy.json").exists()
