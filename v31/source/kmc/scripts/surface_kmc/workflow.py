"""Prepare and dispatch a single externally authorized serial Zacros 4.0 call."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess

from scripts.artifact_io import sha256_bytes, sha256_file, sha256_json, write_json_exclusive
from scripts.execution_permission import require_bound_action
from scripts.multiphase_contracts import read_unique_json as read
from scripts.native_inputs import integer
from scripts.native_model import assemble, with_checkpoint
from scripts.surface_kmc.observations import (
    ENGINE,
    STREAMS,
    _collect_history,
    _output,
    _spatial_boundary,
    check_lattice_output,
    read_trajectory,
)
from scripts.surface_kmc.parameter_table import zacros as event_table

ACTIONS = {"RUN_ZACROS_4", "RESUME_ZACROS_4"}


def prepare(dataset, config, executable, run, *, max_steps, timeout_s, output_bytes, parent=None):
    """Return immutable input bytes and review scope. The output limit applies per collected file."""
    files, manifest = assemble("zacros", dataset, config)
    model = sha256_json(manifest)
    exe, dest = Path(executable).resolve(strict=True), Path(run).resolve()
    if sha256_file(exe) != ENGINE:
        raise ValueError("Engine differs from reviewed serial Zacros 4.0")
    c = config["zacros"]
    if integer(max_steps, "cumulative step limit") > c["max_steps"]:
        raise ValueError("Step budget exceeds model limit")
    integer(timeout_s, "external timeout")
    integer(output_bytes, "collection budget")
    inputs = {k: v.encode() for k, v in files.items()}
    lineage = None
    if parent:
        parent = Path(parent).resolve(strict=True)
        receipt = read(parent / "result.json")
        prior = read(parent / "claim.json")
        writer_digest = sha256_json(prior["plan"])
        if read(parent.parent / f".zacros-{writer_digest}.claim.json") != prior:
            raise ValueError("Checkpoint writer claim changed")
        if (
            receipt["status"] != "validated_output"
            or receipt["plan_sha256"] != sha256_json(prior["plan"])
            or prior["plan"]["run"] != str(parent)
            or prior["plan"]["engine_sha256"] != ENGINE
            or prior["plan"]["model_sha256"] != model
            or receipt["terminal_step"] >= max_steps
        ):
            raise ValueError("Incompatible checkpoint writer, model or continuation budget")
        for name in receipt["outputs"]:
            if name not in {*STREAMS, "history_output.txt", "lattice_output.txt", "restart.inf"}:
                raise ValueError("Unexpected writer output")
            if sha256_file(parent / name) != receipt["outputs"][name]:
                raise ValueError("Changed checkpoint writer stream")
        raw = _output(parent / "restart.inf", output_bytes)
        files, _ = with_checkpoint(
            files,
            manifest,
            raw,
            dict(model_sha256=model, checkpoint_sha256=receipt["outputs"]["restart.inf"]),
        )
        inputs["restart.inf"] = files["restart.inf"]
        lineage = dict(
            run=str(parent),
            receipt_sha256=sha256_file(parent / "result.json"),
            terminal_step=receipt["terminal_step"],
            headers=receipt["headers"],
            tail=receipt["tail"],
            history_header=receipt.get("history_header"),
        )
        if "snapshot_every_events" in c:
            if prior["plan"]["lineage"] and "last_snapshot_step" not in prior["plan"]["lineage"]:
                # Verify the complete old chain from its immutable evidence before issuing a new scope.
                from scripts.surface_kmc.study import replay

                replay(dataset, config, parent)
            lineage.update(_spatial_boundary(receipt, c["snapshot_every_events"]))
    plan = dict(
        format="zacros-4-single-call/1",
        action="RESUME_ZACROS_4" if parent else "RUN_ZACROS_4",
        executable=str(exe),
        engine_sha256=ENGINE,
        run=str(dest),
        model_sha256=model,
        inputs={k: sha256_bytes(v) for k, v in inputs.items()},
        lineage=lineage,
        seed=c["seed"],
        max_steps=max_steps,
        max_time_s=c["max_time_s"],
        native_wall_s=c["wall_time_s"],
        timeout_s=timeout_s,
        max_output_bytes_per_file=output_bytes,
        threads=1,
        retries=0,
        arguments=[f"--max_steps={max_steps}", f"--wall_time={c['wall_time_s']}"],
    )
    return plan, inputs, manifest


def _collect(dest, plan, dataset, config, manifest):
    receipt = {}
    limit = plan["max_output_bytes_per_file"]
    outputs = {n: _output(dest / n, limit) for n in STREAMS}
    events = event_table(dataset)["events"]
    mapping = manifest["validation"]
    result = read_trajectory(
        outputs, dataset, mapping, events, max_steps=plan["max_steps"], parent=plan["lineage"]
    )
    if not plan["lineage"]:
        expected = Counter(sid for sid, _ in config["zacros"]["seeds"])
        initial = result["specnum"][0]
        if initial[1] != 0 or any(v != expected[sid] for sid, v in initial[2].items()):
            raise ValueError("Initial species populations differ from seed inventory")
    if "topology" in mapping and not plan["lineage"]:
        outputs["lattice_output.txt"] = _output(dest / "lattice_output.txt", limit)
        check_lattice_output(outputs["lattice_output.txt"], mapping["topology"])
    if "snapshot_every_events" in config["zacros"]:
        _collect_history(dest, plan, config, dataset, mapping, events, result, outputs, receipt)
    if config["zacros"]["write_restart"]:
        if b"Restart information successfully written" not in outputs["general_output.txt"]:
            raise ValueError("Missing checkpoint writer marker")
        outputs["restart.inf"] = _output(dest / "restart.inf", limit)
        if not outputs["restart.inf"]:
            raise ValueError("Empty native checkpoint")
    for key in ("procstat", "specnum"):
        receipt.setdefault("tail", {})[key] = result.pop(key)[-1]
    receipt.update(
        result, status="validated_output", outputs={k: sha256_bytes(v) for k, v in outputs.items()}
    )
    return receipt


def execute(dataset, config, executable, run, *, decision, **budgets):
    """Decision is the externally authenticated review document. All failure paths consume the claim after reservation."""
    plan, inputs, manifest = prepare(dataset, config, executable, run, **budgets)
    decision_path = Path(decision).resolve(strict=True)
    approval = read(decision_path)
    digest = sha256_json(plan)
    if (
        approval.get("format") != "zacros-4-single-call-approval/1"
        or approval.get("DECISION") != "approve"
        or approval.get("ALLOWED_ACTIONS") != [plan["action"]]
        or not str(approval.get("reviewer") or "").strip()
    ):
        raise PermissionError("Explicit, attributable single-call Zacros review required")
    source = approval.get("source") or {}
    source_path = Path(source.get("path", ""))
    if (
        not source_path.is_file()
        or source_path.resolve() == decision_path
        or sha256_file(source_path) != source.get("sha256")
    ):
        raise PermissionError("Missing or changed external approval source")
    require_bound_action(approval, plan["action"], digest, ACTIONS)
    dest = Path(plan["run"])
    if dest.exists():
        raise FileExistsError(dest)
    claim = dict(plan=plan, decision_sha256=sha256_json(approval), approval=approval)
    write_json_exclusive(dest.parent / f".zacros-{digest}.claim.json", claim)
    dest.mkdir(exist_ok=False)
    write_json_exclusive(dest / "claim.json", claim)
    receipt = dict(plan_sha256=digest, status="failed", outputs={})
    try:
        for name, raw in inputs.items():
            with (dest / name).open("xb") as f:
                f.write(raw)
        if any(sha256_file(dest / name) != digest for name, digest in plan["inputs"].items()):
            raise ValueError("Staged input changed before launch")
        if sha256_file(Path(plan["executable"])) != ENGINE:
            raise ValueError("Executable changed after review")
        env = dict(os.environ, OMP_NUM_THREADS="1", OMP_THREAD_LIMIT="1")
        with (dest / "console.log").open("xb") as log:
            call = subprocess.run(
                [plan["executable"], *plan["arguments"]],
                cwd=dest,
                env=env,
                timeout=plan["timeout_s"],
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        receipt["exit_code"] = call.returncode
        if call.returncode:
            raise ValueError(f"Native exit code {call.returncode}")
        receipt.update(_collect(dest, plan, dataset, config, manifest))
    except subprocess.TimeoutExpired:
        receipt.update(status="timeout", error="External wall time exceeded")
    except (ValueError, OSError, KeyError, IndexError) as exc:
        receipt.update(status="failed", error=str(exc))
    write_json_exclusive(dest / "result.json", receipt)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=["plan", "execute"])
    for key in ("dataset", "configuration", "executable", "run"):
        p.add_argument(key, type=Path)
    for key in ("max-steps", "timeout-s", "output-bytes"):
        p.add_argument("--" + key, required=True, type=int)
    p.add_argument("--parent", type=Path)
    p.add_argument("--decision", type=Path)
    args = vars(p.parse_args())
    op, decision = args.pop("operation"), args.pop("decision")
    args["config"] = read(args.pop("configuration"))
    args["dataset"] = read(args["dataset"])
    if op == "plan":
        plan = prepare(**args)[0]
        print(json.dumps(dict(plan=plan, state_sha256=sha256_json(plan)), indent=2))
        return 0
    if decision is None:
        p.error("Execution requires an external decision file")
    result = execute(**args, decision=decision)
    print(json.dumps(result, indent=2))
    return int(result["status"] != "validated_output")


if __name__ == "__main__":
    raise SystemExit(main())
