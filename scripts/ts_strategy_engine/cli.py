from __future__ import annotations

import argparse

from pathlib import Path

from .cli_commands import _active_learning_command, _analyze_command, _connectivity_command, _connectivity_prepare_command, _dimer_analyze_command, _dimer_command, _learning_command, _ml_neb_finalize_command, _ml_neb_validate_command, _path_review_command, _plan_command, _record_barrier_command, _record_template_command, _record_validation_command, _register_compatibility_command, _validation_pipeline_command, _vfa_analyze_command, _vfa_prepare_command

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATABASE = ROOT / "data" / "project_registry.sqlite3"

DEFAULT_FAMILIES = ROOT / "configs" / "ts_strategy_engine" / "families.yaml"

DEFAULT_THRESHOLDS = ROOT / "configs" / "neb_agent" / "default_thresholds.yaml"

def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Unified V3 transition-state workflow; never submits calculations.")
    commands = root.add_subparsers(dest="command", required=True)
    _add_plan_parser(commands)
    _add_path_parsers(commands)
    _add_dimer_parsers(commands)
    _add_vfa_parsers(commands)
    _add_registry_parsers(commands)
    active_learning = commands.add_parser(
        "active-learning",
        help="Run the AQCat25 TS active-learning state machine.",
        add_help=False,
    )
    active_learning.add_argument("-h", "--help", dest="active_learning_help", action="store_true")
    active_learning.add_argument("active_learning_args", nargs=argparse.REMAINDER)
    active_learning.set_defaults(handler=_active_learning_command)
    learning = commands.add_parser("learning", help="Capture, improve and compare existing strategies without execution.", add_help=False)
    learning.add_argument("-h", "--help", dest="learning_help", action="store_true")
    learning.add_argument("--database", dest="learning_database", type=Path)
    learning.add_argument("--output", dest="learning_output", type=Path)
    learning.add_argument("learning_args", nargs=argparse.REMAINDER)
    learning.set_defaults(handler=_learning_command)
    return root

def _add_plan_parser(commands: argparse._SubParsersAction) -> None:
    planning = commands.add_parser("plan", help="Validate evidence/endpoints, retrieve templates, and optionally build a path.")
    planning.add_argument("--is", dest="initial", type=Path, required=True)
    planning.add_argument("--fs", dest="final", type=Path, required=True)
    planning.add_argument("--contract", type=Path, required=True)
    planning.add_argument("--workdir", type=Path, required=True)
    planning.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    planning.add_argument("--families", type=Path, default=DEFAULT_FAMILIES)
    planning.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    planning.add_argument("--initialize-path", action="store_true")
    planning.add_argument("--constraints", type=Path)
    planning.add_argument("--waypoint", type=Path, action="append", default=[])
    planning.add_argument("--output-dir", type=Path)
    planning.add_argument("--images", type=int)
    planning.add_argument("--strategy-variant", help="Experimental learning variant; all existing gates still apply.")
    planning.add_argument("--rebuild", action="store_true")
    planning.add_argument("--gate-decision", type=Path)
    planning.add_argument("--gate-state-sha256")
    planning.set_defaults(handler=_plan_command)

def _add_path_parsers(commands: argparse._SubParsersAction) -> None:
    ml_validate = commands.add_parser(
        "ml-neb-path-validate",
        help="Validate a returned complete GPU ML-NEB path manifest and all image hashes.",
    )
    ml_validate.add_argument("--manifest", type=Path, required=True)
    ml_validate.add_argument("--accepted", action="store_true")
    ml_validate.set_defaults(handler=_ml_neb_validate_command)
    ml_finalize = commands.add_parser(
        "ml-neb-path-finalize",
        help="Bind an accepted work-side path review and create the DIMER-parent manifest.",
    )
    ml_finalize.add_argument("--candidate", type=Path, required=True)
    ml_finalize.add_argument("--review", type=Path, required=True)
    ml_finalize.add_argument("--output", type=Path, required=True)
    ml_finalize.set_defaults(handler=_ml_neb_finalize_command)
    review = commands.add_parser("path-review-draft", help="Checksum-bind dist.pl and nebmovie.pl 0 evidence for review.")
    review.add_argument("--workdir", type=Path, required=True)
    review.add_argument("--dist", type=Path, required=True)
    review.add_argument("--nebmovie", type=Path, required=True)
    review.add_argument("--output", type=Path)
    review.set_defaults(handler=_path_review_command)
    analysis = commands.add_parser("analyze", help="Analyze NEB/CI-NEB evidence and choose the next method.")
    analysis.add_argument("--workdir", type=Path, required=True)
    analysis.add_argument("--contract", type=Path, required=True)
    analysis.add_argument("--path-review", type=Path)
    analysis.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    analysis.add_argument(
        "--quality-thresholds",
        type=Path,
        default=ROOT / "configs" / "neb_path_quality_control_v2.yaml",
    )
    analysis.add_argument("--preflight", type=Path)
    analysis.add_argument("--validation", type=Path)
    analysis.add_argument("--scheduler", type=Path)
    analysis.set_defaults(handler=_analyze_command)

def _add_dimer_parsers(commands: argparse._SubParsersAction) -> None:
    handoff = commands.add_parser("dimer", help="Prepare an evidence-gated DIMER candidate and MODECAR.")
    handoff.add_argument("--source-image", type=Path, required=True)
    handoff.add_argument("--previous-image", type=Path, required=True)
    handoff.add_argument("--next-image", type=Path, required=True)
    handoff.add_argument("--analysis", type=Path, required=True)
    handoff.add_argument("--path-review", type=Path, required=True)
    handoff.add_argument("--contract", type=Path, required=True)
    handoff.add_argument("--destination", type=Path, required=True)
    handoff.add_argument("--dry-run", action="store_true")
    handoff.add_argument("--gate-decision", type=Path)
    handoff.add_argument("--gate-state-sha256")
    handoff.set_defaults(handler=_dimer_command)
    analysis = commands.add_parser("dimer-analyze", help="Parse DIMCAR/OUTCAR and gate DIMER convergence.")
    analysis.add_argument("--workdir", type=Path, required=True)
    analysis.set_defaults(handler=_dimer_analyze_command)

def _add_vfa_parsers(commands: argparse._SubParsersAction) -> None:
    pipeline = commands.add_parser(
        "validation-pipeline-status",
        help="Evaluate the resumable Dimer -> VFA validation stage.",
    )
    pipeline.add_argument("--dimer-analysis", type=Path, required=True)
    pipeline.add_argument("--path-topology", type=Path)
    pipeline.add_argument("--branch-plan", type=Path)
    pipeline.add_argument("--segment-id")
    pipeline.add_argument("--dimer-soft-review", type=Path)
    pipeline.add_argument("--vfa-workdir", type=Path)
    pipeline.add_argument("--vfa-analysis", type=Path)
    pipeline.add_argument("--connectivity-review", type=Path)
    pipeline.add_argument("--positive-run", type=Path)
    pipeline.add_argument("--negative-run", type=Path)
    pipeline.add_argument("--connectivity-report", type=Path)
    pipeline.add_argument("--output", type=Path)
    pipeline.set_defaults(handler=_validation_pipeline_command)

    handoff = commands.add_parser("vfa-prepare", help="Prepare a contract-bound partial-Hessian frequency handoff.")
    handoff.add_argument("--source-image", type=Path, required=True)
    handoff.add_argument("--destination", type=Path, required=True)
    handoff.add_argument("--active-indices", required=True)
    handoff.add_argument("--contract", type=Path, required=True)
    handoff.add_argument("--saddle-analysis", type=Path, required=True)
    handoff.add_argument("--dimer-soft-gate-review", type=Path)
    handoff.add_argument("--dry-run", action="store_true")
    handoff.set_defaults(handler=_vfa_prepare_command)
    analysis = commands.add_parser("vfa-analyze", help="Grade frequency and target-mode evidence.")
    analysis.add_argument("--workdir", type=Path, required=True)
    analysis.add_argument("--contract", type=Path, required=True)
    analysis.add_argument("--review", type=Path, required=True)
    analysis.set_defaults(handler=_vfa_analyze_command)

    connectivity = commands.add_parser(
        "connectivity-analyze",
        help="Prove both imaginary-mode directions with completed VASP downhill relaxations.",
    )
    connectivity.add_argument("--contract", type=Path, required=True)
    connectivity.add_argument("--is", dest="initial", type=Path, required=True)
    connectivity.add_argument("--fs", dest="final", type=Path, required=True)
    connectivity.add_argument("--saddle", type=Path, required=True)
    connectivity.add_argument("--frequency-outcar", type=Path, required=True)
    connectivity.add_argument("--positive-run", type=Path, required=True)
    connectivity.add_argument("--positive-displacement", type=Path, required=True)
    connectivity.add_argument("--positive-scheduler", type=Path, required=True)
    connectivity.add_argument("--negative-run", type=Path, required=True)
    connectivity.add_argument("--negative-displacement", type=Path, required=True)
    connectivity.add_argument("--negative-scheduler", type=Path, required=True)
    connectivity.add_argument("--output", type=Path, required=True)
    connectivity.set_defaults(handler=_connectivity_command)

    connectivity_prepare = commands.add_parser(
        "connectivity-prepare",
        help="Create reviewed positive/negative principal-mode displacements.",
    )
    connectivity_prepare.add_argument("--source-saddle", type=Path, required=True)
    connectivity_prepare.add_argument("--vfa-analysis", type=Path, required=True)
    connectivity_prepare.add_argument("--review", type=Path, required=True)
    connectivity_prepare.add_argument("--destination", type=Path, required=True)
    connectivity_prepare.add_argument("--amplitude", type=float, required=True)
    connectivity_prepare.add_argument("--mode-index", type=int)
    connectivity_prepare.set_defaults(handler=_connectivity_prepare_command)

def _add_registry_parsers(commands: argparse._SubParsersAction) -> None:
    validation = commands.add_parser("record-validation", help="Store a reviewed VFA validation record.")
    validation.add_argument("--validation-id", required=True)
    validation.add_argument("--analysis", type=Path, required=True)
    validation.add_argument("--gate-decision", type=Path, required=True)
    validation.add_argument("--gate-state-sha256", required=True)
    validation.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    validation.set_defaults(handler=_record_validation_command)

    barrier = commands.add_parser(
        "record-barrier",
        help="Compute and store an accepted compatible IS/TS/FS final-energy barrier set.",
    )
    barrier.add_argument("--barrier-id", required=True)
    barrier.add_argument("--reaction-id", required=True)
    barrier.add_argument("--source-calculation-id", required=True)
    barrier.add_argument("--validation-id", required=True)
    barrier.add_argument("--initial-result-id", required=True)
    barrier.add_argument("--ts-result-id", required=True)
    barrier.add_argument("--final-result-id", required=True)
    barrier.add_argument(
        "--learning-record",
        type=Path,
        required=True,
        help="Strategy-only Grade-A learning record atomically stored with the barrier.",
    )
    barrier.add_argument("--notes")
    barrier.add_argument("--gate-decision", type=Path, required=True)
    barrier.add_argument("--gate-state-sha256", required=True)
    barrier.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    barrier.set_defaults(handler=_record_barrier_command)

    compatibility = commands.add_parser("register-compatibility", help="Bind a calculation to the reviewed method branch.")
    compatibility.add_argument("--calculation-id", required=True)
    compatibility.add_argument("--contract", type=Path, required=True)
    compatibility.add_argument("--reviewer", required=True)
    compatibility.add_argument("--reviewed-at", required=True)
    compatibility.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    compatibility.set_defaults(handler=_register_compatibility_command)

    record = commands.add_parser("record", help="Store an evidence-bound success or explicit failed experience.")
    record.add_argument("--record", type=Path, required=True)
    record.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    record.set_defaults(handler=_record_template_command)

def main() -> None:
    args = parser().parse_args()
    args.handler(args)

if __name__ == "__main__":
    main()
