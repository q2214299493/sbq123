from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .active_learning import (
    assess_path_force_predictions,
    assess_force_prediction,
    assess_independent_ts_domain,
    decide_ts_domain_reuse,
    ingest_vasp_force_label,
    ingest_path_vasp_force_labels,
    initialize_path_workflow,
    initialize_workflow,
    load_state,
    prepare_ba_sella_rerun,
    prepare_ml_neb_path_rerun,
    prepare_path_force_predictions,
    prepare_path_vasp_force_labels,
    prepare_finetuning_package,
    prepare_force_prediction_request,
    prepare_vasp_force_label,
    record_stage_failure,
    register_finetuning_result,
    register_ts_domain_calibration,
    register_job_evidence,
    register_next_candidate,
    register_next_path,
    resume_retryable_failure,
)
from .active_learning_common import STATE_NAME, write_json
from scripts.scheduler_evidence import query_lsf_job


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "configs" / "aqcat25_ts_active_learning.yaml"


def _add_state_target(command: argparse.ArgumentParser) -> None:
    target = command.add_mutually_exclusive_group(required=True)
    target.add_argument("--state", type=Path)
    target.add_argument("--ts-workdir", type=Path)


def _state_path(args: argparse.Namespace) -> Path:
    if args.state:
        return args.state
    return args.ts_workdir / "active_learning" / STATE_NAME


def _discover_candidate_manifest(ts_workdir: Path) -> Path:
    """Find the single returned GPU candidate owned by a TS work directory.

    The TS workflow writes returned candidates below ``output/job_*``.  Keeping
    discovery here means callers do not have to manually copy a path between
    the TS and active-learning command surfaces.  Ambiguous directories are
    rejected instead of silently selecting stale evidence.
    """
    candidates = sorted(ts_workdir.glob("output/job_*/gpu_result_manifest.json"))
    if len(candidates) != 1:
        if not candidates:
            raise FileNotFoundError(
                f"no GPU candidate manifest found below {ts_workdir / 'output'}"
            )
        raise ValueError(
            "TS work directory contains multiple GPU candidate manifests; "
            "pass --candidate-manifest explicitly: "
            + ", ".join(str(path) for path in candidates)
        )
    return candidates[0]


def _init_from_ts_args(args: argparse.Namespace) -> dict:
    ts_workdir = args.ts_workdir.resolve()
    candidate_manifest = (
        args.candidate_manifest.resolve()
        if args.candidate_manifest
        else _discover_candidate_manifest(ts_workdir)
    )
    handoff_root = (args.handoff_root or ts_workdir).resolve()
    # Existing TS workdirs may only retain the source YAML. ``load_contract``
    # normalizes and hash-binds it in memory, so no auxiliary normalized file
    # is needed just to cross the CLI boundary.
    contract = ts_workdir / "reaction_contract.normalized.json"
    if not contract.is_file():
        contract = ts_workdir / "contract" / "reaction.yaml"
    if not contract.is_file():
        raise FileNotFoundError(
            f"TS reaction contract not found: {ts_workdir / 'contract'}"
        )
    return initialize_workflow(
        candidate_manifest,
        handoff_root,
        contract,
        args.policy,
        ts_workdir / "active_learning",
        dry_run=args.dry_run,
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Evidence-gated AQCat25 TS active learning; never submits calculations."
    )
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--candidate-manifest", type=Path, required=True)
    init.add_argument("--handoff-root", type=Path, required=True)
    init.add_argument("--contract", type=Path, required=True)
    init.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    init.add_argument("--destination", type=Path, required=True)
    init.add_argument("--dry-run", action="store_true")

    path_init = commands.add_parser(
        "path-init",
        help="Start path-level active learning from one complete GPU ML-NEB manifest.",
    )
    path_init.add_argument("--path-manifest", type=Path, required=True)
    path_init.add_argument("--contract", type=Path, required=True)
    path_init.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    path_init.add_argument("--destination", type=Path, required=True)
    path_init.add_argument("--committee-assessment", type=Path)
    path_init.add_argument("--dry-run", action="store_true")

    bridge = commands.add_parser(
        "init-from-ts",
        aliases=["start"],
        help="Start active learning from one TS work directory.",
    )
    bridge.add_argument("--ts-workdir", type=Path, required=True)
    bridge.add_argument(
        "--candidate-manifest",
        type=Path,
        help="Returned GPU manifest; auto-discovered when the TS directory has one candidate.",
    )
    bridge.add_argument(
        "--handoff-root",
        type=Path,
        help="Root used to resolve manifest paths; defaults to --ts-workdir.",
    )
    bridge.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    bridge.add_argument("--dry-run", action="store_true")

    for name in (
        "prepare-label",
        "ingest-label",
        "prepare-prediction",
        "assess",
        "assess-domain",
        "register-domain-calibration",
        "decide-domain-reuse",
        "prepare-finetune",
        "register-finetune",
        "prepare-rerun",
        "next-candidate",
        "register-job",
        "record-failure",
        "resume",
        "status",
        "prepare-path-labels",
        "ingest-path-labels",
        "prepare-path-predictions",
        "assess-path",
        "prepare-path-rerun",
        "next-path",
    ):
        _add_state_target(commands.add_parser(name))

    commands.choices["prepare-label"].add_argument("--destination", type=Path, required=True)
    commands.choices["ingest-label"].add_argument("--scheduler-evidence", type=Path, required=True)
    commands.choices["prepare-prediction"].add_argument("--destination", type=Path, required=True)
    commands.choices["assess"].add_argument("--prediction", type=Path, required=True)
    commands.choices["assess-domain"].add_argument("--manifest", type=Path, required=True)
    commands.choices["register-domain-calibration"].add_argument(
        "--review", type=Path, required=True
    )
    commands.choices["decide-domain-reuse"].add_argument(
        "--context", type=Path, required=True
    )
    commands.choices["prepare-finetune"].add_argument("--destination", type=Path, required=True)
    commands.choices["register-finetune"].add_argument("--result", type=Path, required=True)
    commands.choices["prepare-rerun"].add_argument("--destination", type=Path, required=True)
    candidate = commands.choices["next-candidate"]
    candidate.add_argument("--candidate-manifest", type=Path, required=True)
    candidate.add_argument("--handoff-root", type=Path, required=True)
    candidate.add_argument("--contract", type=Path, required=True)
    commands.choices["register-job"].add_argument("--evidence", type=Path, required=True)
    commands.choices["record-failure"].add_argument("--evidence", type=Path, required=True)
    commands.choices["prepare-path-labels"].add_argument("--destination", type=Path, required=True)
    commands.choices["ingest-path-labels"].add_argument(
        "--evidence-manifest", type=Path, required=True
    )
    commands.choices["prepare-path-predictions"].add_argument(
        "--destination", type=Path, required=True
    )
    commands.choices["assess-path"].add_argument("--manifest", type=Path, required=True)
    commands.choices["prepare-path-rerun"].add_argument(
        "--destination", type=Path, required=True
    )
    next_path = commands.choices["next-path"]
    next_path.add_argument("--path-manifest", type=Path, required=True)
    next_path.add_argument("--contract", type=Path, required=True)
    next_path.add_argument("--committee-assessment", type=Path)

    scheduler = commands.add_parser("capture-lsf-evidence")
    scheduler.add_argument("--job-id", required=True)
    scheduler.add_argument("--stage", default="vasp_force_label", choices=["vasp_force_label"])
    scheduler.add_argument("--output", type=Path, required=True)
    return root


def _dispatch_path_state_command(args: argparse.Namespace, state_path: Path) -> dict:
    if args.command == "prepare-path-labels":
        return prepare_path_vasp_force_labels(state_path, args.destination)
    if args.command == "ingest-path-labels":
        return ingest_path_vasp_force_labels(state_path, args.evidence_manifest)
    if args.command == "prepare-path-predictions":
        return prepare_path_force_predictions(state_path, args.destination)
    if args.command == "assess-path":
        return assess_path_force_predictions(state_path, args.manifest)
    if args.command == "prepare-path-rerun":
        return prepare_ml_neb_path_rerun(state_path, args.destination)
    return register_next_path(
        state_path,
        args.path_manifest,
        args.contract,
        committee_assessment_path=args.committee_assessment,
    )


def _dispatch_state_command(args: argparse.Namespace, state_path: Path) -> dict:
    if args.command == "prepare-label":
        return prepare_vasp_force_label(state_path, args.destination)
    if args.command == "ingest-label":
        return ingest_vasp_force_label(state_path, args.scheduler_evidence)
    if args.command == "prepare-prediction":
        return prepare_force_prediction_request(state_path, args.destination)
    if args.command == "assess":
        return assess_force_prediction(state_path, args.prediction)
    if args.command == "assess-domain":
        return assess_independent_ts_domain(state_path, args.manifest)
    if args.command == "register-domain-calibration":
        return register_ts_domain_calibration(state_path, args.review)
    if args.command == "decide-domain-reuse":
        return decide_ts_domain_reuse(state_path, args.context)
    if args.command == "prepare-finetune":
        return prepare_finetuning_package(state_path, args.destination)
    if args.command == "register-finetune":
        return register_finetuning_result(state_path, args.result)
    if args.command == "prepare-rerun":
        return prepare_ba_sella_rerun(state_path, args.destination)
    if args.command == "next-candidate":
        return register_next_candidate(
            state_path, args.candidate_manifest, args.handoff_root, args.contract
        )
    if args.command == "register-job":
        return register_job_evidence(state_path, args.evidence)
    if args.command == "record-failure":
        return record_stage_failure(state_path, args.evidence)
    if args.command == "resume":
        return resume_retryable_failure(state_path)
    state = load_state(state_path)
    return {
        "reaction_id": state["reaction_id"],
        "status": state["status"],
        "next_action": state["next_action"],
        "round_count": len(state["rounds"]),
        "data_policy": state["data_policy"],
    }


def dispatch(args: argparse.Namespace) -> dict:
    if args.command == "init":
        return initialize_workflow(
            args.candidate_manifest,
            args.handoff_root,
            args.contract,
            args.policy,
            args.destination,
            dry_run=args.dry_run,
        )
    if args.command == "path-init":
        return initialize_path_workflow(
            args.path_manifest,
            args.contract,
            args.policy,
            args.destination,
            committee_assessment_path=args.committee_assessment,
            dry_run=args.dry_run,
        )
    if args.command in {"init-from-ts", "start"}:
        return _init_from_ts_args(args)
    if args.command == "capture-lsf-evidence":
        result = query_lsf_job(args.job_id, stage=args.stage)
        write_json(args.output, result)
        return result
    state_path = _state_path(args)
    if args.command in {
        "prepare-path-labels",
        "ingest-path-labels",
        "prepare-path-predictions",
        "assess-path",
        "prepare-path-rerun",
        "next-path",
    }:
        return _dispatch_path_state_command(args, state_path)
    return _dispatch_state_command(args, state_path)


def main(argv: Sequence[str] | None = None) -> None:
    result = dispatch(parser().parse_args(argv))
    print(json.dumps(result, indent=2, ensure_ascii=False))
