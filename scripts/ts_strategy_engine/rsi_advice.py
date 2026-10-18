"""Fixed-version, no-model RSI advice consumption at the TS planning boundary."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess
import sys
import uuid
import warnings

from scripts.artifact_io import (
    load_json_object, require_sha256, sha256_file, sha256_json,
    source_file_manifest, source_file_manifest_valid, write_json_exclusive,
)
from .contract import load_contract
from .learning_evidence import bind_files, exact_keys, observe, validate_files
from .path_evidence import _resolve_constraints, _resolve_waypoints
from .strategy_learning import POLICY, policy


RSI_SOURCE_ROOT_ENV = "SBQ_RSI_SOURCE_ROOT"
# Always verify the exact approved producer revision, independent of its location.
RSI_REVISION = "79cc038eac32e8526f6a5ccdb768182dd8b3e828"
TIMEOUT_SECONDS = 30


def _reference(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


def _source(reference: dict) -> dict:
    validate_files({"source": reference})
    path = Path(reference["path"])
    if not path.is_absolute() or path.stat().st_size > 1024 * 1024:
        raise ValueError("RSI JSON source requires an absolute path and at most 1 MiB")
    return load_json_object(path)


def plan_inputs(request) -> dict:
    """Freeze existing planning inputs; output locations are not scientific inputs."""
    contract = load_contract(request.contract)
    files = {name: str(getattr(request, name)) for name in
             ("initial", "final", "contract", "families", "thresholds")}
    constraints = _resolve_constraints(request, contract)
    if constraints is not None:
        files["constraints"] = str(constraints)
    waypoints = _resolve_waypoints(request.contract, contract, request.waypoint)
    files.update({f"waypoint_{i}": str(path) for i, path in enumerate(waypoints)})
    if request.gate_decision is not None:
        files["gate_decision"] = str(request.gate_decision)
    return {"files": bind_files(files), "database": str(request.database.resolve()),
            "strategy_variant": request.strategy_variant, "images": request.images,
            "initialize_path": request.initialize_path, "rebuild": request.rebuild,
            "gate_state_sha256": request.gate_state_sha256}


def _run(argv: list[str], cwd: Path):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", PYTHONNOUSERSITE="1")
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                          timeout=TIMEOUT_SECONDS, check=False)


def _source_root(operator_root: Path | None = None) -> Path:
    """Select a versioned checkout on this host; never from the untrusted task JSON."""
    selected = operator_root if operator_root is not None else os.environ.get(RSI_SOURCE_ROOT_ENV)
    if selected is None or not str(selected).strip():
        raise ValueError(f"RSI source not configured: pass --rsi-source-root or set {RSI_SOURCE_ROOT_ENV}")
    path = Path(selected).expanduser()
    if not path.is_absolute():
        raise ValueError("RSI source root must be an absolute directory on the invoking host")
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("RSI source root is not a directory")
    return root


def _runtime(operator_root: Path | None = None) -> dict:
    root = _source_root(operator_root)
    toplevel = _run(["git", "rev-parse", "--show-toplevel"], root)
    if toplevel.returncode or Path(toplevel.stdout.decode("utf-8").strip()).resolve() != root:
        raise ValueError("RSI source root must be a Git checkout root")
    head = _run(["git", "rev-parse", "HEAD"], root)
    dirty = _run(["git", "status", "--porcelain=v1", "--untracked-files=all",
                  "--", "scripts", "configs", "pyproject.toml"], root)
    if head.returncode or dirty.returncode or head.stdout.decode().strip() != RSI_REVISION or dirty.stdout:
        raise ValueError("RSI source version is unavailable, changed or dirty")
    if sha256_file(root / "configs/ts_strategy_engine/learning.yaml") != sha256_file(POLICY):
        raise ValueError("RSI and current strategy policy differ")
    sources = [root / "scripts/artifact_io.py", root / "configs/ts_strategy_engine/learning.yaml"]
    sources.extend(root / "scripts/ts_strategy_engine" / name for name in (
        "learning_cli.py", "next_review.py", "next_review_core.py", "learning_cases.py",
        "learning_evidence.py", "strategy_learning.py", "workflow_improvement.py", "workflow_evaluation.py"))
    return {"root": str(root), "revision": RSI_REVISION, "python": sys.executable,
            "python_version": sys.version, "python_sha256": sha256_file(Path(sys.executable)),
            "source_files": source_file_manifest(sources),
            "interface": "learning advise-next", "model_calls": 0}


def _policy_sources(store: Path, identity: str) -> list[Path]:
    """Snapshot only referenced ancestry and observations, without another registry."""
    paths, seen = [], set()
    while identity is not None:
        if identity in seen or len(seen) >= 32:
            raise ValueError("invalid RSI policy ancestry")
        seen.add(identity)
        path = store / "policies" / f"{require_sha256(identity, label='policy')}.json"
        record = _source(_reference(path))
        if sha256_json(record) != identity:
            raise ValueError("RSI policy content identity mismatch")
        validate_files(record["inputs"])
        if any(not Path(ref["path"]).is_absolute() for ref in record["observations"]):
            raise ValueError("RSI observations require absolute source paths")
        observe(record["observations"])
        paths.append(path)
        paths.extend(Path(ref["path"]) for ref in record["inputs"].values())
        paths.extend(Path(ref["path"]) for ref in record["observations"])
        for kind in ("decisions", "evaluations"):
            source = store / kind / f"{identity}.json"
            if source.exists():
                paths.append(source)
        identity = record.get("parent_id")
    return paths


def _validate_advice(context: dict) -> dict:
    spec = _source(context["request"])
    if not source_file_manifest_valid({"source_files": context["sources"]}):
        raise ValueError("RSI evidence or policy changed after invocation")
    if not source_file_manifest_valid(context["runtime"]):
        raise ValueError("RSI producer source changed after invocation")
    store = Path(spec["store"])
    record = _source(_reference(store / "policies" / f"{spec['policy_id']}.json"))
    public, answers = (_source(record["inputs"][name]) for name in ("public", "answers"))
    report = _source(context["advice"])
    if type(report["schema_version"]) is not int or report["schema_version"] != 1 \
            or report["status"] != "ADVISORY_ONLY_NOT_AUTHORIZED" \
            or any(report[key] is not False for key in ("public_source_files_reverified",
                   "causal_claims_scientifically_validated", "ts_strategy_changes_authorized")):
        raise ValueError("RSI advice schema or authority mismatch")
    if report["public_sha256"] != sha256_json(public) \
            or report["answers_sha256"] != record["inputs"]["answers"]["sha256"] \
            or report["policy_sha256"] != sha256_file(POLICY):
        raise ValueError("RSI advice source identity mismatch")
    selection = report["workflow_strategy"]
    mode = "offline_evaluation" if spec["offline_evaluation"] else (
        "baseline_review" if record["kind"] == "baseline" else "accepted_review")
    if record["provenance"] == "synthetic" and not spec["offline_evaluation"]:
        raise ValueError("synthetic advice requires explicit offline evaluation")
    if any(selection[key] != value for key, value in {
            "policy_id": spec["policy_id"], "scope": spec["scope"], "mode": mode,
            "provenance": record["provenance"]}.items()):
        raise ValueError("RSI policy selection mismatch")
    cases = [c for c in public["cases"] if c["case_id"] == spec["case_id"]]
    rows = [r for r in report["recommendations"] if r["case_id"] == spec["case_id"]]
    diagnoses = [a for a in answers["answers"] if a["case_id"] == spec["case_id"]]
    if len(cases) != 1 or len(rows) != 1 or len(diagnoses) != 1:
        raise ValueError("RSI advice requires one matching case and diagnosis")
    case, row, diagnosis = cases[0], rows[0], diagnoses[0]
    if case["group_id"] != spec["task_id"] or row["group_id"] != spec["task_id"] \
            or diagnosis["input_sha256"] != case["input_sha256"]:
        raise ValueError("RSI advice task/input mismatch")
    for key in ("failure_class", "causal_status", "causal_claim", "causal_evidence_ids", "next_review"):
        if sha256_json(row[key]) != sha256_json(diagnosis[key]):
            raise ValueError("RSI advice changed the bound diagnosis")
    expected = [] if row["causal_status"] == "unknown" else record["orders"].get(row["failure_class"], [])
    fields = row["ts_strategy_fields_to_review"]
    if fields != expected or not isinstance(fields, list) or len(set(fields)) != len(fields) \
            or not set(fields) <= policy()["settings_schema"]["properties"].keys() \
            or row["next_review"] != policy()["failure_routes"][row["failure_class"]] \
            or row["automatic_execution"] is not False or row["requires_owning_review"] is not True:
        raise ValueError("RSI advice is not an authorized review-order permutation")
    return {"selection": selection, "row": row, "input_sha256": case["input_sha256"]}


def prepare_advice(request, request_path: Path | None, expected_sha256: str | None,
                   *, source_root: Path | None = None) -> dict | None:
    """No option preserves ordinary planning; an explicit invalid request stops."""
    if request_path is None and expected_sha256 is None:
        if source_root is not None:
            raise ValueError("--rsi-source-root requires an explicit RSI request")
        return None
    context = {"status": "unavailable", "invocation_id": uuid.uuid4().hex,
               "started_at": datetime.now(timezone.utc).isoformat(), "task_id": None,
               "producer_launch_attempted": False, "producer_exit_code": None}
    directory = request.workdir / "rsi" / context["invocation_id"]
    try:
        context["task_id"] = load_contract(request.contract)["reaction_id"]
        if request_path is None:
            raise ValueError("RSI request path is missing")
        context["request"] = {"path": str(request_path.resolve()),
                              "sha256": require_sha256(expected_sha256, label="RSI request")}
        spec = _source(context["request"])
        exact_keys(spec, {"schema_version", "task_id", "case_id", "rsi_revision", "store",
                          "policy_id", "scope", "plan_inputs", "offline_evaluation"})
        if type(spec["schema_version"]) is not int or spec["schema_version"] != 1 \
                or type(spec["offline_evaluation"]) is not bool or spec["rsi_revision"] != RSI_REVISION:
            raise ValueError("RSI request schema/version mismatch")
        context["requested_task_id"] = spec["task_id"]
        context["plan_inputs"] = plan_inputs(request)
        if sha256_json(spec["plan_inputs"]) != sha256_json(context["plan_inputs"]) \
                or spec["task_id"] != context["task_id"]:
            raise ValueError("RSI request does not bind the current task/plan inputs")
        if spec["offline_evaluation"] and (request.initialize_path or request.rebuild):
            raise ValueError("offline RSI candidate preview cannot prepare or rebuild a path")
        store = Path(spec["store"]).resolve(strict=True)
        policy_path = store / "policies" / f"{require_sha256(spec['policy_id'], label='policy')}.json"
        record = _source(_reference(policy_path))
        sources = _policy_sources(store, spec["policy_id"])
        context["sources"] = source_file_manifest([request_path, POLICY, *sources])
        context["runtime"] = _runtime(source_root)
        public = _source(record["inputs"]["public"])
        directory.mkdir(parents=True, exist_ok=False)
        report_path = directory / "advice.json"
        argv = [sys.executable, "-B", "-s", "-m", "scripts.ts_strategy_engine.learning_cli", "advise-next",
                "--public", record["inputs"]["public"]["path"], "--answers", record["inputs"]["answers"]["path"],
                "--expected-public-sha256", sha256_json(public), "--report", str(report_path.resolve()),
                "--workflow-store", str(store), "--workflow-policy", spec["policy_id"], "--workflow-scope", spec["scope"]]
        if spec["offline_evaluation"]:
            argv.append("--offline-evaluation")
        context["command"] = argv
        write_json_exclusive(directory / "invocation-started.json", context)
        context["producer_launch_attempted"] = True
        completed = _run(argv, Path(context["runtime"]["root"]))
        context["producer_exit_code"] = completed.returncode
        if completed.returncode:
            context["stderr"] = completed.stderr.decode("utf-8", errors="replace")[-4000:]
            raise ValueError("RSI advise-next rejected the request; see recorded stderr")
        context["advice"] = _reference(report_path)
        _validate_advice(context)
        context["status"] = "available"
    except (OSError, ValueError, KeyError, TypeError, SystemExit, subprocess.SubprocessError) as exc:
        context["reason"] = f"{type(exc).__name__}: {exc}"
    context["ended_at"] = datetime.now(timezone.utc).isoformat()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        receipt = directory / "invocation-result.json"
        write_json_exclusive(receipt, context)
        context["receipt"] = _reference(receipt)
    except OSError as exc:
        raise ValueError(f"Explicit RSI invocation receipt unavailable: {exc}") from exc
    if context["status"] != "available":
        raise ValueError(f"Explicit RSI request rejected: {context['reason']}")
    return context


def consume_advice(request) -> dict | None:
    """Materialize an ordered review plan, never parameter changes or approval."""
    context = request.rsi_advice
    if context is None:
        return None
    result = {"status": "unavailable", "invocation_id": None,
              "task_id": None, "automatic_execution": False}
    try:
        if not isinstance(context, dict):
            raise ValueError("invalid RSI invocation context")
        result.update(invocation_id=context.get("invocation_id"), task_id=context.get("task_id"))
        if context["status"] != "available":
            raise ValueError(context.get("reason", "RSI producer unavailable"))
        if sha256_json(_source(context["receipt"])) != sha256_json({k: v for k, v in context.items() if k != "receipt"}):
            raise ValueError("RSI invocation receipt differs from the consumed context")
        if sha256_json(plan_inputs(request)) != sha256_json(context["plan_inputs"]):
            raise ValueError("planning inputs changed before RSI advice consumption")
        selected = _validate_advice(context)
        row = selected["row"]
        result.update(status="ADOPTED_FOR_REVIEW_PLANNING", advice=context["advice"],
                      workflow_strategy=selected["selection"], case_id=row["case_id"],
                      input_sha256=selected["input_sha256"], next_review=row["next_review"],
                      causal_status=row["causal_status"], review_focus=row["review_focus"],
                      items=[{"sequence": i, "field": field, "check_status": "PENDING"}
                             for i, field in enumerate(row["ts_strategy_fields_to_review"])],
                      scientific_review_completed=False, execution_authorized=False)
    except (OSError, ValueError, KeyError, TypeError, SystemExit) as exc:
        result["reason"] = f"{type(exc).__name__}: {exc}"
        request.workdir.mkdir(parents=True, exist_ok=True)
        write_json_exclusive(request.workdir / "rsi_rejection.json", result)
        raise ValueError(f"Explicit RSI advice consumption rejected: {result['reason']}") from exc
    return result


def record_plan_binding(request, review: dict | None) -> None:
    if review is not None:
        try:
            write_json_exclusive(request.workdir / "rsi_integration.json", {
                "schema_version": 1, "task_id": review["task_id"], "invocation": request.rsi_advice,
                "adoption": review, "plan": _reference(request.workdir / "ts_strategy.json"),
                "execution": None, "outcome": None,
                "downstream_binding": "Existing VASP learning start inputs may reference this receipt and workflow_plan; other backends use outcome observations. No execution is inferred."})
        except OSError as exc:
            warnings.warn(f"RSI binding receipt unavailable; workflow plan is preserved: {exc}", RuntimeWarning)
