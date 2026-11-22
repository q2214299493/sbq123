"""Prepare, execute and inspect one approved CATKINAS steady-state point in a fresh run directory."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
from time import monotonic

import yaml

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm.results import read_single_point
from scripts.baseline_mkm.single_point_result import validate_result
from scripts.execution_permission import require_bound_action
from scripts.baseline_mkm.mapping_scope import MappingBlocked, check_configuration, topology
from scripts.baseline_mkm.sensitivity_inputs import baseline_config, configuration as sensitivity_configuration, reproduce
from scripts.kinetic_parameters.engine import check_version
from scripts.native_model import assemble, publish
from scripts.runtime_resources import resource_path

ACTION = "RUN_CATKINAS_SINGLE_POINT"
LIMIT = 210
INPUT = "INPUT_phase25.m"
NATIVE_OUTPUTS = ("runtime/result_phase25/data1.mat", "runtime/result_phase25/log1",
                  "runtime/result_phase25/Input_phase25_1", "runtime/console.log")


def now():
    return datetime.now(timezone.utc).isoformat()


def ticket_binding(database, ticket_id):
    """Read the Supervisor H7 identity without opening its mutating TicketStore constructor."""
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT question_id,status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    if not row or not re.fullmatch(r"[a-f0-9]{24}", ticket_id) or not re.fullmatch(r"[a-f0-9]{64}", row[0] or ""):
        raise ValueError("Research Ticket requires an existing bound question_id")
    if row[1] in {"CLOSED", "PAUSED"}:
        raise ValueError("Research Ticket is closed or paused")
    return {"ticket_id": ticket_id, "question_id": row[0]}


def event(run, stage, **data):
    return save(run / (stage + ".json"), dict(stage=stage, timestamp=now(), **data))


STAGES = (
    "CREATED",
    "QUALIFICATION",
    "INPUT_GENERATED",
    "AWAITING_APPROVAL",
    "READY",
    "RUNNING",
    "COLLECTING",
    "PARSING",
    "VALIDATING",
    "ACCEPTED",
    "REJECTED",
)


class IncompleteKinetics(ValueError):
    def __init__(self, missing):
        super().__init__("Incomplete kinetic dataset")
        self.missing = missing


def qualify(network, dataset, config):
    check_version(network, "network_version")
    check_version(dataset, "dataset_version")
    if dataset["network_version"] != network["network_version"]:
        raise ValueError("Network version differs from dataset")
    rebuilt = reproduce(network, dataset)
    if rebuilt != dataset:
        raise ValueError("Dataset differs from network, source verification or reviewed rates")
    if "sensitivity_perturbation" in dataset and config != sensitivity_configuration(baseline_config(), rebuilt):
        raise ValueError("Feed or conditions differ from the sensitivity derivative")
    missing = {r["reaction_id"]: r["missing"] for r in dataset["reactions"] if not r["export_eligible"]}
    if missing:
        raise IncompleteKinetics(missing)
    if len(network["catalog"]["sites"]) > 1 or any(
        len(r["definition"].get("phase_ids") or []) > 1 for r in network["reactions"]
    ):
        issues, _ = topology(network)
        if issues:
            raise MappingBlocked(issues)
        check_configuration(config)
    files, adapter = assemble("catkinas", dataset, config)
    parameter = dataset["reactions"][0]["parameter_set"]
    for key, value in (
        ("temperature_K", parameter["temperature_K"]),
        ("total_pressure_bar", parameter["pressure_Pa"] / 100000),
    ):
        if key in config and config[key] != value:
            raise ValueError(f"Requested {key} differs from reviewed condition")
    return files, adapter


def tools_for_run(matlab):
    runtime = yaml.safe_load(resource_path("configs/postprocessing_software.yaml").read_bytes())
    binary = runtime["postprocessing_software"]["catkinas"]["authorized_validation_build"]
    reference = read(resource_path("reports/multiphase/phase2_5_1/catkinas_compatibility.json"))
    if sha256_file(Path(binary["source_path"])) != binary["sha256"]:
        raise ValueError("CATKINAS distribution hash mismatch")
    if sha256_file(matlab) != reference["matlab_executable_sha256"]:
        raise ValueError("MATLAB executable hash mismatch")
    return {
        "catkinas": binary,
        "matlab_path": str(matlab.resolve()),
        "matlab_sha256": reference["matlab_executable_sha256"],
        "matlab_version": reference["matlab_version"],
    }


def prepare(run, network, dataset, configuration, tickets, ticket_id, matlab):
    run = run.resolve()
    run.mkdir(parents=True, exist_ok=False)
    event(run, "CREATED", run_id=run.name)
    event(run, "QUALIFICATION")
    try:
        paths = {"network": network, "dataset": dataset, "configuration": configuration}
        inputs = {k: sha256_file(p) for k, p in paths.items()}
        n, d, c = (read(p) for p in paths.values())
        binding = ticket_binding(tickets, ticket_id)
        save(
            run / "context.json",
            dict(
                **binding,
                run_id=run.name,
                catalyst_project_id=n["project_id"],
                network_version_id=n["network_version"],
                kinetic_dataset_version=d["dataset_version"],
                input_hashes=inputs,
            ),
        )
        files, adapter = qualify(n, d, c)
        runtime = tools_for_run(matlab)
        for k, p in paths.items():
            shutil.copyfile(p, run / (k + ".json"))
            if sha256_file(run / (k + ".json")) != inputs[k]:
                raise ValueError(f"Source changed during preparation: {k}")
        publish(run / "input", files, adapter)
        p = d["reactions"][0]["parameter_set"]
        manifest = dict(
            format="mkm-single-point-plan/1",
            run_id=run.name,
            run_directory=str(run),
            **binding,
            ticket_database=str(tickets.resolve()),
            catalyst_project_id=n["project_id"],
            phase_id=[s["phase_id"] for s in n["catalog"]["phases"]],
            surface_id=[s["surface_id"] for s in n["catalog"]["surfaces"]],
            network_version_id=n["network_version"],
            kinetic_dataset_version=d["dataset_version"],
            input_hashes=inputs,
            native_input_hashes=adapter["files"],
            configuration_hash=sha256_json(c),
            temperature_K=p["temperature_K"],
            partial_pressures_bar=c["partial_pressure_bar"],
            total_pressure_bar=p["pressure_Pa"] / 100000,
            standard_states=p["standard_states"],
            initial_coverages=c["catkinas"]["initial_coverages"],
            site_inventory=n["catalog"]["sites"],
            solver_settings=dict(
                mode="single_point", timeout_s=LIMIT, **{k: c["catkinas"][k] for k in ("MaxTime", "MaxOdeTime")}
            ),
            use_scope=d["reactions"][0]["model"].get("use_scope", "project"),
            runtime=runtime,
            execution_limits={"single_points": 1, "native_invocations": 1, "automatic_retries": 0},
            expected_native_outputs=list(NATIVE_OUTPUTS),
            acceptance_criteria=[
                "Successful process exit within timeout and matching native input echo and runtime identity",
                "Completed solver log with convergence and finite native coefficients, fluxes and coverages",
                "Reviewed species, reaction order, temperature, feed, energies and directional coefficients",
                "Independent mass action, site inventories, charge, element and steady-state balances",
                "Common overall extent, declared turnover basis and selectivity within the configured product set",
            ],
        )
        perturbation = d.get("sensitivity_perturbation", {})
        spec = perturbation.get("spec", {})
        if "composition_grid" in spec:
            manifest["composition_review"] = dict(
                **spec["review_basis"],
                original_target_bar=perturbation["original_target_bar"],
                predicted_native_bar=perturbation["feed_bar"],
                intended_log_step=perturbation["intended_log_step"],
                direction="plus" if perturbation["sign"] == 1 else "minus",
            )
        save(run / "plan.json", manifest)
        event(run, "INPUT_GENERATED")
        event(run, "AWAITING_APPROVAL", state_sha256=sha256_json(manifest))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        event(
            run,
            "REJECTED",
            failure_stage="QUALIFICATION",
            missing_data=getattr(exc, "missing", str(exc)),
            execution="not_started",
            convergence="unknown",
            scientific_validity="unqualified",
            approval="not_requested",
        )
    return status(run)


def launch(directory, executable, timeout=LIMIT):
    command = [
        executable,
        "-sd",
        str(directory),
        "-batch",
        "disp(version); disp(which('CATKINAS')); CATKINAS('INPUT_phase25')",
    ]
    with (directory / "console.log").open("xb") as output:
        proc = subprocess.Popen(command, cwd=directory, stdout=output, stderr=subprocess.STDOUT)
        try:
            return proc.wait(timeout=min(LIMIT, timeout))
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False)
            proc.kill()
            proc.wait(timeout=10)
            raise


def preflight(run, decision_path):
    plan = read(run / "plan.json")
    if not (run / "AWAITING_APPROVAL.json").exists() or (run / "REJECTED.json").exists():
        raise ValueError("Run is not awaiting execution")
    if read(run / "AWAITING_APPROVAL.json")["state_sha256"] != sha256_json(plan):
        raise ValueError("Prepared plan differs from the pending approval request")
    decision = read(decision_path)
    if (
        decision.get("format") != "mkm-execution-approval/1"
        or decision.get("DECISION") != "approve"
        or decision.get("ALLOWED_ACTIONS") != [ACTION]
        or not str(decision.get("reviewer") or "").strip()
        or decision.get("question_id") != plan["question_id"]
    ):
        raise PermissionError("Explicit single-point approval required")
    if sha256_file(Path(decision["source"]["path"])) != decision["source"]["sha256"]:
        raise PermissionError("Approval source changed")
    require_bound_action(decision, ACTION, sha256_json(plan), {ACTION})
    if (
        str(run) != plan["run_directory"]
        or ticket_binding(Path(plan["ticket_database"]), plan["ticket_id"])["question_id"] != plan["question_id"]
    ):
        raise ValueError("Stale directory or Research Ticket binding")
    for k, h in plan["input_hashes"].items():
        if sha256_file(run / (k + ".json")) != h:
            raise ValueError("Changed source snapshot: " + k)
    network, dataset, config = (read(run / (k + ".json")) for k in ("network", "dataset", "configuration"))
    files, adapter = qualify(network, dataset, config)
    publish(run / "input", files, adapter)
    rt = plan["runtime"]
    if tools_for_run(Path(rt["matlab_path"])) != rt or adapter["files"] != plan["native_input_hashes"]:
        raise ValueError("Runtime or input differs from approved plan")
    return plan, decision, dataset, config, files, adapter, rt


def native_output_hashes(directory, required=()):
    """Inventory native outputs, including partial output from a failed attempt."""
    hashes = {
        p.relative_to(directory.parent).as_posix(): sha256_file(p)
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p not in (directory / INPUT, directory / "CATKINAS.p")
    }
    missing = set(required) - hashes.keys()
    if missing:
        raise ValueError("Missing native output: " + ", ".join(sorted(missing)))
    return hashes


def execute(run, decision_path, *, deadline=None):
    run = run.resolve()
    plan, decision, dataset, config, files, adapter, rt = preflight(run, decision_path)
    if ("ts_perturbation" in dataset or "sensitivity_perturbation" in dataset) and deadline is None:
        raise ValueError("Use the bounded DRC pair executor for a TS derivative")
    # Atomic execution claim. A stopped supervisor cannot silently relaunch the same point.
    event(run, "READY", approval_reference=sha256_json(decision))
    stage, execution, convergence = "READY", "not_started", "unknown"
    process = {}
    try:
        save(run / "approval.json", decision)
        directory = run / "runtime"
        directory.mkdir()
        (directory / INPUT).write_bytes(files[INPUT].encode())
        shutil.copyfile(rt["catkinas"]["source_path"], directory / "CATKINAS.p")
        if (
            sha256_file(directory / "CATKINAS.p") != rt["catkinas"]["sha256"]
            or sha256_file(directory / INPUT) != adapter["files"][INPUT]
        ):
            raise ValueError("Staged input or executable hash mismatch")
        stage = "RUNNING"
        event(run, stage)
        execution = "running"
        started = monotonic()
        try:
            if deadline is None:
                code = launch(directory, rt["matlab_path"])
            else:
                remaining = min(LIMIT, deadline - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired("CATKINAS pair budget", 0)
                code = launch(directory, rt["matlab_path"], timeout=remaining)
            process["exit_code"] = code
        finally:
            process["elapsed_process_seconds"] = monotonic() - started
        execution = "exited_successfully" if code == 0 else "failed"
        if code != 0:
            raise ValueError(f"MATLAB exit code {code}")
        stage = "COLLECTING"
        event(run, stage, exit_code=code)
        out = directory / "result_phase25"
        mat, log, echo = out / "data1.mat", out / "log1", out / "Input_phase25_1"
        hashes = native_output_hashes(directory, NATIVE_OUTPUTS)
        if hashes[echo.relative_to(run).as_posix()] != adapter["files"][INPUT]:
            raise ValueError("Native input echo differs from approved input")
        console = (directory / "console.log").read_bytes().decode("ascii", errors="replace")
        version = re.search(r"CATKINAS version\s*:\s*(\d+)", console)
        stage = "PARSING"
        event(run, stage)
        native = read_single_point(mat, log)
        convergence = "converged"
        stage = "VALIDATING"
        event(run, stage)
        native_log = log.read_bytes().decode("ascii", errors="replace")
        matlab = re.search(r"CATKINAS is running now on MATLAB: ([\d.]+ \(R\d+[ab]\))", native_log)
        if not version or not matlab:
            raise ValueError("Native runtime version missing")
        result = validate_result(dataset, config, adapter["validation"], native, native_log, files[INPUT])
        if any(sha256_file(run / name) != h for name, h in hashes.items()):
            raise ValueError("Native output changed during validation")
        result.update(
            run_id=plan["run_id"],
            question_id=plan["question_id"],
            scope=plan["use_scope"],
            plan_sha256=sha256_json(plan),
            output_hashes=hashes,
        )
        if rt["matlab_version"].replace("MATLAB ", "").replace("(", "").replace(")", "") != matlab[1].replace(
            "(", ""
        ).replace(")", ""):
            raise ValueError("Native MATLAB version differs from approved runtime")
        save(run / "result.json", result)
        event(
            run,
            "ACCEPTED",
            execution=execution,
            convergence=convergence,
            scientific_validity="validated_within_scope",
            approval="approved",
            **process,
            catkinas_version=version[1],
            matlab_version=matlab[1],
            output_hashes=hashes,
            validation=result["validation"],
            approval_reference=sha256_json(decision),
            result_sha256=sha256_file(run / "result.json"),
        )
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            execution = "timed_out"
        elif execution == "running":
            execution = "failed"
        try:
            process["output_hashes"] = native_output_hashes(run / "runtime")
        except OSError as collection_error:
            process["output_inventory_error"] = str(collection_error)
        event(
            run,
            "REJECTED",
            failure_stage=stage,
            **process,
            reason=str(exc),
            execution=execution,
            convergence=convergence,
            scientific_validity="rejected" if stage == "VALIDATING" else "unconfirmed",
            approval="approved",
        )
    return status(run)


def status(run):
    stages = [s for s in STAGES if (run / (s + ".json")).is_file()]
    plan = (
        read(run / "plan.json")
        if (run / "plan.json").exists()
        else (read(run / "context.json") if (run / "context.json").exists() else {"run_id": run.name})
    )
    last = read(run / (stages[-1] + ".json"))
    execution = (
        "exited_successfully" if "COLLECTING" in stages else "running" if "RUNNING" in stages else "not_started"
    )
    approval = "approved" if "READY" in stages else "pending" if "AWAITING_APPROVAL" in stages else "not_requested"
    view = dict(plan, stages=stages)
    view.update(execution=execution, approval=approval, convergence="unknown", scientific_validity="unconfirmed")
    view.update(last)
    view["artifacts"] = [f"{s}.json" for s in stages] + [
        s for s in ("plan.json", "result.json") if (run / s).exists()
    ]
    if last["stage"] == "ACCEPTED":
        if sha256_file(run / "result.json") != last["result_sha256"]:
            raise ValueError("Accepted result has changed")
        r = read(run / "result.json")
        view.update(
            coverage={s["species_id"]: s["coverage"] for s in r["species"] if s["coverage"] is not None},
            tof_s_inverse=r["tof_s_inverse"],
            reaction_fluxes={x["reaction_id"]: x["net_flux"] for x in r["reactions"]},
        )
    if view.get("ticket_id"):
        # H7 accepts these three fields on its authenticated, manual handoff endpoint.
        artifact = (run / ("result.json" if last["stage"] == "ACCEPTED" else last["stage"] + ".json")).resolve()
        note = {
            "run": view["run_id"],
            "stage": last["stage"],
            "project": view["catalyst_project_id"],
            "network": view["network_version_id"],
            "T_K": view.get("temperature_K"),
            "P_bar": view.get("total_pressure_bar"),
            "convergence": view["convergence"],
            "validation": view["scientific_validity"],
            "TOF_s^-1": view.get("tof_s_inverse"),
        }
        pointer = " Evidence " + str(artifact)
        view["ticket_handoff"] = {
            "ticket_id": view["ticket_id"],
            "status": "READY_FOR_REVIEW" if last["stage"] == "ACCEPTED" else "WAITING_FOR_HUMAN",
            "note": (json.dumps(note, ensure_ascii=False)[: max(0, 1000 - len(pointer))] + pointer)[:1000],
        }
    return view


def accepted_receipt(run):
    """Verify the accepted result, decision and native bytes for downstream readers."""
    receipt = status(run)
    if receipt["stage"] != "ACCEPTED":
        raise ValueError(f"{run.name}: expected accepted point, found {receipt['stage']}")
    plan = read(run / "plan.json")
    decision = read(run / "approval.json")
    receipt["raw_plan_sha256"] = sha256_json(plan)
    require_bound_action(decision, ACTION, receipt["raw_plan_sha256"], {ACTION})
    if (
        decision["DECISION"] != "approve"
        or decision["question_id"] != plan["question_id"]
        or not decision["reviewer"]
        or sha256_json(decision) != receipt["approval_reference"]
        or sha256_file(Path(decision["source"]["path"])) != decision["source"]["sha256"]
    ):
        raise ValueError("Changed approval binding")
    for path, digest in receipt["output_hashes"].items():
        if sha256_file(run / path) != digest:
            raise ValueError(f"Changed native evidence: {path}")
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    for k in ("run", "network", "dataset", "configuration", "tickets"):
        prep.add_argument(k, type=Path)
    prep.add_argument("ticket_id")
    prep.add_argument("matlab", type=Path)
    exe = commands.add_parser("execute")
    exe.add_argument("run", type=Path)
    exe.add_argument("decision", type=Path)
    commands.add_parser("status").add_argument("run", type=Path)
    args = vars(p.parse_args())
    cmd = args.pop("command")
    if cmd == "execute":
        args["decision_path"] = args.pop("decision")
    result = {"prepare": prepare, "execute": execute, "status": status}[cmd](**args)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return int(result["stage"] == "REJECTED")


if __name__ == "__main__":
    raise SystemExit(main())
