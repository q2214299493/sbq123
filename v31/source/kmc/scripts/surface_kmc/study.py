"""Offline analysis of approved-run receipts. A study names its dataset, runs and precision design."""

import argparse
import json
from pathlib import Path

from scripts.replay_evidence import evidence_path
from scripts.artifact_io import sha256_bytes, sha256_file, sha256_json
from scripts.execution_permission import require_bound_action
from scripts.kinetic_data.scientific_identity import read_artifact
from scripts.multiphase_contracts import read_unique_json as read
from scripts.native_model import assemble
from scripts.surface_kmc.analysis import seed_precision, seed_series, size_sensitivity, window_analysis
from scripts.surface_kmc.observations import (
    ENGINE,
    STREAMS,
    _collect_history,
    _output,
    _spatial_boundary,
    join_samples,
    read_trajectory,
)
from scripts.surface_kmc.parameter_table import zacros as event_table
from scripts.surface_kmc.topology import topology


def _replay_history(folder, plan, receipt, config, dataset, mapping, events, obs):
    outputs, spatial = {}, {}
    _collect_history(folder, plan, config, dataset, mapping, events, obs, outputs, spatial)
    raw = outputs.get("history_output.txt")
    digest = sha256_bytes(raw) if raw is not None else None
    if (
        digest != receipt["outputs"].get("history_output.txt")
        or any(spatial[k] != receipt[k] for k in ("history_header", "last_snapshot_step"))
        or "first_snapshot_step" in receipt
        and spatial["first_snapshot_step"] != receipt["first_snapshot_step"]
    ):
        raise ValueError("Spatial output differs from receipt")


def _receipt_binding(folder, claim, digest, result, receipt_hash, manifest, config):
    plan = claim["plan"]
    approval = claim["approval"]
    parent = plan["lineage"]
    action = "RESUME_ZACROS_4" if parent else "RUN_ZACROS_4"
    if (plan["action"] != action or plan["seed"] != config["zacros"]["seed"] or result["exit_code"] != 0
            or approval.get("format") != "zacros-4-single-call-approval/1" or not approval.get("reviewer")
            or approval.get("DECISION") != "approve" or approval.get("ALLOWED_ACTIONS") != [action]
            or sha256_json(approval) != claim["decision_sha256"]):
        raise ValueError("Zacros execution or approval identity differs")
    require_bound_action(approval, action, digest, {action})
    source = approval["source"]
    if sha256_file(evidence_path(source["path"])) != source["sha256"]:
        raise ValueError("Changed Zacros approval source")
    expected = dict(manifest["files"])
    if parent:
        expected["restart.inf"] = plan["inputs"]["restart.inf"]
    if plan["inputs"] != expected or any(sha256_file(folder / k) != v for k, v in manifest["files"].items()):
        raise ValueError("Zacros staged inputs differ from reconstructed model")
    for name, value in result["outputs"].items():
        if Path(name).name != name or sha256_file(folder / name) != value:
            raise ValueError(f"Changed Zacros output {name}")
    return dict(run=plan["run"], plan_sha256=digest, receipt_sha256=receipt_hash,
                approval_sha256=claim["decision_sha256"], model_sha256=plan["model_sha256"],
                parent_receipt_sha256=parent["receipt_sha256"] if parent else None,
                checkpoint_input_sha256=expected.get("restart.inf"),
                terminal_step=result["terminal_step"], terminal_time_s=result["terminal_time_s"])


def _writer_boundary(plan, config):
    lineage = plan["lineage"]
    parent = evidence_path(lineage["run"]).resolve()
    writer, receipt_hash = read_artifact(parent / "result.json")
    if (receipt_hash != lineage["receipt_sha256"]
            or sha256_file(parent / "restart.inf") != plan["inputs"]["restart.inf"]):
        raise ValueError("Changed writer or checkpoint")
    if any(lineage[key] != writer[key] for key in ("terminal_step", "headers", "tail")):
        raise ValueError("Checkpoint lineage differs from its writer")
    if "snapshot_every_events" in config["zacros"]:
        boundary = _spatial_boundary(writer, config["zacros"]["snapshot_every_events"])
        if (any(lineage.get(k, v) != v for k, v in boundary.items())
                or lineage["history_header"] != writer["history_header"]):
            raise ValueError("Spatial lineage differs from checkpoint writer")
        # Old plans omit the cursor. Only their hash-bound writer can supply it.
        lineage = dict(lineage, **boundary)
    return parent, lineage


def replay(dataset, config, run, *, bind_receipts=False):
    """Rebuild the model, check its receipt chain, and stitch cumulative streams exactly once."""
    _, manifest = assemble("zacros", dataset, config)
    mapping = dict(manifest["validation"])
    if "topology" not in mapping:
        mapping["topology"] = topology(config["zacros"], dataset["catalog"])[3]
    events = event_table(dataset)["events"]
    chain, seen, receipts = [], set(), []
    folder = evidence_path(run).resolve()
    while True:
        if folder in seen:
            raise ValueError("Cyclic continuation lineage")
        seen.add(folder)
        claim = read(folder / "claim.json")
        plan = claim["plan"]
        digest = sha256_json(plan)
        result, receipt_hash = read_artifact(folder / "result.json")
        if (
            read(folder.parent / f".zacros-{digest}.claim.json") != claim
            or result["plan_sha256"] != digest
            or result["status"] != "validated_output"
            or plan["engine_sha256"] != ENGINE
            or evidence_path(plan["run"]).resolve() != folder
            or plan["model_sha256"] != sha256_json(manifest)
        ):
            raise ValueError("Run identity, approval claim, result or model differs")
        if bind_receipts:
            receipts.append(_receipt_binding(folder, claim, digest, result, receipt_hash, manifest, config))
        outputs = {k: _output(folder / k, plan["max_output_bytes_per_file"]) for k in STREAMS}
        if any(sha256_bytes(v) != result["outputs"][k] for k, v in outputs.items()):
            raise ValueError("Changed trajectory output")
        lineage = plan["lineage"]
        if lineage:
            parent, lineage = _writer_boundary(plan, config)
            plan = dict(plan, lineage=lineage)
        obs = read_trajectory(outputs, dataset, mapping, events, max_steps=plan["max_steps"], parent=lineage)
        if (
            obs["terminal_step"] != result["terminal_step"]
            or obs["terminal_time_s"] != result["terminal_time_s"]
        ):
            raise ValueError("Terminal output differs from receipt")
        chain.append(obs)
        if "snapshot_every_events" in config["zacros"]:
            _replay_history(folder, plan, result, config, dataset, mapping, events, obs)
        if not lineage:
            break
        folder = parent
    trajectory = chain.pop()
    for part in reversed(chain):
        for key in ("procstat", "specnum"):
            part[key] = join_samples(trajectory[key], part[key])
        trajectory = part
    series = seed_series(config, dataset, trajectory, mapping)
    if bind_receipts:
        series["receipts"] = list(reversed(receipts))
    return series


def analyze(study_path):
    path = Path(study_path)
    study = read(path)
    root = path.parent
    dataset = read(root / study["dataset"])
    runs = [replay(dataset, read(root / r["configuration"]), root / r["directory"]) for r in study["runs"]]
    design = study["design"]
    results = [
        window_analysis(r["trajectory"], dataset, r["mapping"], design["start_s"], design["end_s"])
        for r in runs
    ]
    report = dict(study_sha256=sha256_file(path), per_seed=results, precision=seed_precision(runs, **design))
    if "larger_lattice_runs" in study:
        larger = [
            replay(dataset, read(root / r["configuration"]), root / r["directory"])
            for r in study["larger_lattice_runs"]
        ]
        report["size_sensitivity"] = size_sensitivity(runs, larger, **design)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("study", type=Path)
    print(json.dumps(analyze(p.parse_args().study), indent=2, allow_nan=False))
