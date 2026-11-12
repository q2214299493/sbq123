"""The unapproved two-leaf 60-minute proposal; evidence never grants execution."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, sha256_json


TIMEOUT_LEAF = "paper_chco_aqcat25_ft512_20261112_r000_timebudget_restart01_label"
NEXT_LEAF = "paper_chco_aqcat25_ft512_20261112_r001_label"
FAILED_LEAF = "paper_chco_aqcat25_ft512_20261112_r000_launch_recovery01_label"
SCOPE = {
    "allowed_workdir_names": [TIMEOUT_LEAF, NEXT_LEAF], "time_limit": "01:00:00",
    "failed_job_id": "13907", "failed_workdir_name": FAILED_LEAF,
    "maximum_dft_jobs": 2, "maximum_training_jobs": 1, "training_epochs": 100, "automatic_retries": 0,
}
RESOURCES = {"mpi_ranks": 1, "gpus": 1, "cpus_per_task": 4, "memory": "16G", "time_limit": "01:00:00"}
LIMITS = {"max_dft_jobs": 2, "max_training_jobs": 1, "training_epochs": 100}


def validate_budget_scope(backend: dict[str, Any]) -> None:
    extension = backend.get("time_budget_extension")
    if extension is None:
        if TIMEOUT_LEAF in backend["allowed_workdir_names"]:
            raise ValueError("TIMEOUT restart leaf requires explicit bounded budget registration")
        return
    if (sha256_json(extension) != sha256_json(SCOPE)
            or not set(SCOPE["allowed_workdir_names"]) <= set(backend["allowed_workdir_names"])):
        raise ValueError("60-minute proposal cannot expand its exact two-leaf budget")


def validate_budget_authorization(workdir: Path, request: dict, backend: dict) -> dict[str, Any]:
    """Require a raw-bound, separately recorded user budget decision, not a proposal."""
    from scripts.neb_agent.mz73_static import _bound_raw_source

    reference = request.get("execution_budget_authorization")
    path = _bound_raw_source(reference)
    approval = load_json_object(path)
    expected = {
        "document_kind": "user_execution_budget_authorization", "decision": "approved_bounded_DFT_budget",
        "protocol_sha256": request["protocol_sha256"], "failed_job_id": "13907",
        "backend_id": "mz73_paper_vasp", "observed_hostname": "MZ73",
        "allowed_workdir_names": SCOPE["allowed_workdir_names"], "resources": RESOURCES, "limits": LIMITS,
        "allow_cold_restart": True, "automatic_retries": 0,
    }
    if (workdir.name not in SCOPE["allowed_workdir_names"] or backend.get("time_budget_extension") != SCOPE
            or backend["time_limit"] != "01:00:00"
            or any(sha256_json(approval.get(key)) != sha256_json(value) for key, value in expected.items())):
        raise ValueError("60-minute execution requires the exact approved user budget decision")
    if not _bound_raw_source(approval.get("source")).stat().st_size:
        raise ValueError("approved budget requires the nonempty raw user reply source")
    return {**reference, "source": approval["source"], "protocol_sha256": approval["protocol_sha256"],
            "resources": RESOURCES.copy(), "limits": LIMITS.copy()}


def require_budget_execution_source(source: dict, budget_reference: dict) -> None:
    """Bind the separate execution authorization to the same actual user reply."""
    expected = budget_reference["source"]
    if (not isinstance(source, dict) or source.get("sha256") != expected["sha256"]
            or Path(source.get("path", "")).resolve() != Path(expected["path"]).resolve()):
        raise ValueError("60-minute execution authorization must use the actual new budget reply source")


def validate_timebudget_restart(workdir: Path, request: dict, backend: dict) -> dict[str, Any]:
    """Validate one cold rerun of actual job13907 TIMEOUT, never prelaunch recovery."""
    from scripts.neb_agent.mz73_static import _bound_raw_source

    restart = request.get("timebudget_restart")
    if (workdir.name != TIMEOUT_LEAF or not isinstance(restart, dict)
            or set(restart) != {"failed_job_id", "failed_workdir_name", "failure_review", "backend_snapshot",
                                "no_new_scientific_round", "cold_restart"}
            or restart.get("failed_job_id") != "13907" or restart.get("failed_workdir_name") != FAILED_LEAF
            or restart.get("no_new_scientific_round") is not True or restart.get("cold_restart") is not True
            or "launch_recovery" in request):
        raise ValueError("TIMEOUT restart must be the fixed independent cold-rerun request")
    review_path = _bound_raw_source(restart["failure_review"])
    snapshot = _bound_raw_source(restart["backend_snapshot"])
    review = load_json_object(review_path)
    expected = {
        "document_kind": "paper_timebudget_failure_evidence", "failure_stage": "dft_timeout", "job_id": "13907",
        "scheduler_state": "TIMEOUT", "vasp_started": True, "electronically_converged": False,
        "accepted_label_count": 0, "dft_label_created": False, "training_performed": False,
        "budget_authorization_artifact_sha256": request["execution_budget_authorization"]["sha256"],
        **{key: request[key] for key in ("protocol_sha256", "evaluation_index", "candidate_structure_sha256", "search_checkpoint_sha256")},
    }
    if any(sha256_json(review.get(k)) != sha256_json(v) for k, v in expected.items()):
        raise ValueError("TIMEOUT restart lacks its independently reviewed failed-DFT evidence")
    original = (workdir.parent / FAILED_LEAF).resolve()
    paths = _timeout_source_paths(review, original, snapshot)
    receipt, bundle_sha256 = _timeout_submission(original, snapshot, paths, review)
    _same_cold_inputs(workdir, original, request, receipt)
    return {**restart, "original_bundle_sha256": bundle_sha256, "potcar_sha256": receipt["potcar_sha256"],
            "failure_source_files": review["source_files"]}


def _timeout_source_paths(review: dict, original: Path, snapshot: Path) -> dict[str, Path]:
    from scripts.neb_agent.mz73_static import _bound_raw_source

    sources = review.get("source_files")
    required = {"terminal", "submission", "stdout", "OUTCAR", "OSZICAR", "failed_state", "backend_snapshot"}
    if not isinstance(sources, dict) or not required <= set(sources):
        raise ValueError("TIMEOUT review lacks raw source files")
    paths = {key: _bound_raw_source(value) for key, value in sources.items()}
    for key, name in {"terminal": "slurm_13907.terminal.json", "submission": "submission_record.json",
                      "stdout": "vasp.out", "OUTCAR": "OUTCAR", "OSZICAR": "OSZICAR"}.items():
        if paths[key] != original / name:
            raise ValueError("TIMEOUT source evidence belongs to another original directory")
    if paths["backend_snapshot"] != snapshot:
        raise ValueError("TIMEOUT backend snapshot is not the reviewed raw source")
    for key, source in {"failed_state_artifact_sha256": "failed_state", "scheduler_evidence_sha256": "terminal",
                        "launcher_log_sha256": "stdout"}.items():
        if review.get(key) != sources[source]["sha256"]:
            raise ValueError("TIMEOUT state and physical evidence raw source identities differ")
    return paths


def _timeout_submission(original: Path, snapshot: Path, paths: dict, review: dict) -> tuple[dict, str]:
    from scripts.neb_agent.mz73_static import BACKEND_ID, load_mz73_static_backend
    from scripts.neb_agent.submission import InputBundle
    from scripts.slurm_force_label import validate_stored_slurm_force_label
    from scripts.vasp_result_gate import final_scf_status

    old_backend = load_mz73_static_backend(FAILED_LEAF, config_path=snapshot)
    remote = old_backend["remote_root"] + "/" + FAILED_LEAF
    native = validate_stored_slurm_force_label(
        load_json_object(paths["terminal"]), job_id="13907", remote_dir=remote,
        workdir_name=FAILED_LEAF, config_path=snapshot, require_completed=False,
    )
    if native["job_state"] != "TIMEOUT" or review.get("native_exit_code") != native["exit_code"]:
        raise ValueError("TIMEOUT restart requires the original native TIMEOUT evidence")
    report = load_json_object(original / "submission_preflight.json")
    bundle = InputBundle.from_preflight(report)
    bundle.verify(original)
    receipt = load_json_object(paths["submission"])
    if (receipt.get("job_id") != "13907" or receipt.get("status") != "SUBMITTED"
            or receipt.get("scheduler") != "Slurm" or receipt.get("server_alias") != BACKEND_ID
            or receipt.get("remote_dir") != remote or receipt.get("bundle_sha256") != bundle.bundle_sha256
            or report.get("backend_config_sha256") != sha256_file(snapshot)
            or review.get("failed_execution") != {"job_id": "13907", "bundle_sha256": bundle.bundle_sha256,
                                                  "gate_sha256": receipt.get("gate_decision_sha256")}):
        raise ValueError("TIMEOUT restart does not bind the original submission and bundle")
    scf = final_scf_status(paths["OSZICAR"], original / "INCAR", paths["OUTCAR"])
    if (not paths["OUTCAR"].stat().st_size or not scf["last_electronic_iteration"]
            or scf["electronically_converged"]):
        raise ValueError("TIMEOUT restart requires VASP-started, electronically unconverged evidence")
    return receipt, bundle.bundle_sha256


def _same_cold_inputs(workdir: Path, original: Path, request: dict, receipt: dict) -> None:
    from scripts.neb_agent.mz73_static import PAPER_REQUEST

    previous = load_json_object(original / PAPER_REQUEST)
    ignored = {"launch_recovery", "timebudget_restart", "execution_budget_authorization"}
    if sha256_json({k: v for k, v in request.items() if k not in ignored}) != sha256_json({k: v for k, v in previous.items() if k not in ignored}):
        raise ValueError("TIMEOUT cold rerun changes the original scientific request")
    for name in ("POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "POTCAR"):
        if sha256_file(workdir / name) != sha256_file(original / name):
            raise ValueError("TIMEOUT cold rerun changes a frozen scientific input")
    if sha256_file(workdir / "POTCAR") != receipt.get("potcar_sha256"):
        raise ValueError("TIMEOUT cold rerun POTCAR differs from the original submission")
    if any((workdir / name).exists() for name in ("WAVECAR", "CHGCAR")):
        raise ValueError("TIMEOUT cold rerun cannot import wavefunctions or charge restart files")
