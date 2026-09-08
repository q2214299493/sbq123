from __future__ import annotations

import argparse

import json


from scripts.neb_agent.cli_common import comma_tokens

from scripts.ts_validation.analyze_vfa import analyze_vfa

from scripts.ts_validation.connectivity import analyze_bidirectional_connectivity

from scripts.ts_validation.prepare_connectivity import prepare_connectivity_displacements

from scripts.ts_validation.prepare_vfa_from_ts_image import prepare_vfa_handoff

from scripts.ts_validation.validation_pipeline import evaluate_validation_pipeline

from .contract import load_contract

from .active_learning_cli import main as active_learning_main

from .dimer_analysis import analyze_dimer

from .evidence import (
    record_matched_static_barrier,
    record_ts_validation,
    register_calculation_compatibility,
)

from .handoff import prepare_dimer_handoff

from .ml_neb_path import finalize_gpu_ml_neb_path_manifest, validate_gpu_ml_neb_path_manifest

from .path_evidence import (
    load_json_object,
    validate_path_binding,
    validate_path_review,
    write_path_review_draft,
)

from .templates import record_template

from .learning_cli import main as learning_main

from .workflow import AnalyzeRequest, PlanRequest, analyze_search, plan





def _plan_command(args: argparse.Namespace) -> None:
    plan(
        PlanRequest(
            initial=args.initial,
            final=args.final,
            contract=args.contract,
            workdir=args.workdir,
            database=args.database,
            families=args.families,
            thresholds=args.thresholds,
            initialize_path=args.initialize_path,
            constraints=args.constraints,
            waypoint=tuple(args.waypoint),
            output_dir=args.output_dir,
            images=args.images,
            strategy_variant=args.strategy_variant,
            rebuild=args.rebuild,
            gate_decision=args.gate_decision,
            gate_state_sha256=args.gate_state_sha256,
        )
    )

def _path_review_command(args: argparse.Namespace) -> None:
    print(write_path_review_draft(args.workdir, args.dist, args.nebmovie, args.output))

def _ml_neb_validate_command(args: argparse.Namespace) -> None:
    payload = validate_gpu_ml_neb_path_manifest(args.manifest, require_accepted=args.accepted)
    print(json.dumps({"status": payload["status"], "images": len(payload["images"])}, ensure_ascii=True))

def _ml_neb_finalize_command(args: argparse.Namespace) -> None:
    payload = finalize_gpu_ml_neb_path_manifest(args.candidate, args.review, args.output)
    print(json.dumps({"status": payload["status"], "manifest": str(args.output)}, ensure_ascii=True))

def _analyze_command(args: argparse.Namespace) -> None:
    request = AnalyzeRequest(
        workdir=args.workdir,
        contract=args.contract,
        thresholds=args.thresholds,
        path_review=args.path_review,
        quality_thresholds=args.quality_thresholds,
        preflight=args.preflight,
        validation=args.validation,
        scheduler=args.scheduler,
    )
    analyze_search(request)

def _dimer_command(args: argparse.Namespace) -> None:
    contract = load_contract(args.contract)
    binding = validate_path_binding(args.analysis.parent, contract)
    reviewed, _ = validate_path_review(args.path_review, args.analysis.parent / "path_generation_report.json")
    if not binding["valid"] or not reviewed:
        raise SystemExit("DIMER requires contract-bound path generation and checksum-bound path review")
    prepare_dimer_handoff(
        args.source_image,
        args.previous_image,
        args.next_image,
        args.destination,
        args.dry_run,
        analysis_path=args.analysis,
        path_review_path=args.path_review,
        reaction_indices=contract["reaction_atoms"],
        contract_binding=binding,
        gate_decision=args.gate_decision,
        gate_state_sha256=args.gate_state_sha256,
    )
    print("DRY_RUN" if args.dry_run else args.destination)

def _dimer_analyze_command(args: argparse.Namespace) -> None:
    if not args.workdir.is_dir():
        raise SystemExit(f"workdir not found: {args.workdir}")
    print(analyze_dimer(args.workdir)["status"])

def _vfa_prepare_command(args: argparse.Namespace) -> None:
    contract = load_contract(args.contract)
    prepare_vfa_handoff(
        args.source_image,
        args.destination,
        [int(value) for value in comma_tokens(args.active_indices)],
        contract,
        args.saddle_analysis,
        args.dry_run,
        args.dimer_soft_gate_review,
    )
    print("DRY_RUN" if args.dry_run else args.destination)

def _validation_pipeline_command(args: argparse.Namespace) -> None:
    payload = evaluate_validation_pipeline(
        dimer_analysis_path=args.dimer_analysis,
        path_topology_path=args.path_topology,
        branch_plan_path=args.branch_plan,
        segment_id=args.segment_id,
        dimer_soft_review_path=args.dimer_soft_review,
        vfa_workdir=args.vfa_workdir,
        vfa_analysis_path=args.vfa_analysis,
        connectivity_review_path=args.connectivity_review,
        positive_run=args.positive_run,
        negative_run=args.negative_run,
        connectivity_report_path=args.connectivity_report,
        output=args.output,
    )
    print(payload["status"])

def _connectivity_prepare_command(args: argparse.Namespace) -> None:
    payload = prepare_connectivity_displacements(
        args.source_saddle,
        args.vfa_analysis,
        args.review,
        args.destination,
        amplitude_A=args.amplitude,
        mode_index=args.mode_index,
    )
    print(payload["document_kind"])

def _vfa_analyze_command(args: argparse.Namespace) -> None:
    contract = load_contract(args.contract)
    print(analyze_vfa(args.workdir, contract, args.review)["status"])

def _connectivity_command(args: argparse.Namespace) -> None:
    payload = analyze_bidirectional_connectivity(
        contract_path=args.contract,
        initial_path=args.initial,
        final_path=args.final,
        saddle_path=args.saddle,
        frequency_outcar=args.frequency_outcar,
        positive_run=args.positive_run,
        positive_displacement=args.positive_displacement,
        positive_scheduler=args.positive_scheduler,
        negative_run=args.negative_run,
        negative_displacement=args.negative_displacement,
        negative_scheduler=args.negative_scheduler,
        output=args.output,
    )
    print(payload["status"])

def _record_validation_command(args: argparse.Namespace) -> None:
    analysis = load_json_object(args.analysis, "VFA analysis")
    print(
        record_ts_validation(
            args.database,
            args.validation_id,
            analysis,
            gate_decision=args.gate_decision,
            gate_state_sha256=args.gate_state_sha256,
        )
    )

def _record_barrier_command(args: argparse.Namespace) -> None:
    learning_record = load_json_object(args.learning_record, "learning record")
    payload = record_matched_static_barrier(
        args.database,
        gate_decision=args.gate_decision,
        gate_state_sha256=args.gate_state_sha256,
        barrier_set_id=args.barrier_id,
        reaction_id=args.reaction_id,
        source_calculation_id=args.source_calculation_id,
        ts_validation_id=args.validation_id,
        initial_result_id=args.initial_result_id,
        ts_result_id=args.ts_result_id,
        final_result_id=args.final_result_id,
        learning_record=learning_record,
        notes=args.notes,
    )
    print(json.dumps(payload, ensure_ascii=False))

def _register_compatibility_command(args: argparse.Namespace) -> None:
    contract = load_contract(args.contract)
    print(
        register_calculation_compatibility(
            args.database,
            args.calculation_id,
            contract["compatibility"],
            args.reviewer,
            args.reviewed_at,
        )
    )

def _record_template_command(args: argparse.Namespace) -> None:
    print(record_template(args.database, load_json_object(args.record, "learning record")))

def _active_learning_command(args: argparse.Namespace) -> None:
    active_learning_main(["--help"] if args.active_learning_help else args.active_learning_args)

def _learning_command(args: argparse.Namespace) -> None:
    options = []
    for flag, value in (("--database", args.learning_database), ("--output", args.learning_output)):
        if value is not None:
            options.extend((flag, str(value)))
    learning_main(["--help"] if args.learning_help else options + args.learning_args)
