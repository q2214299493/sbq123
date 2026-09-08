from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json
from scripts.convergence.common import EXTERNAL_COMMAND_TIMEOUT_SECONDS
from scripts.execution_backends import load_execution_backends, require_vasp_backend
from scripts.neb_agent.pilot_validation import validate_pilot_result
from scripts.neb_agent.utils_structure import numbered_image_dirs, read_poscar
from scripts.ts_strategy_engine.dimer_gate import validate_modecar_bundle
from scripts.ts_strategy_engine.execution_gate import require_action
from scripts.ts_strategy_engine.learning_evidence import vasp_input_hashes
from scripts.ts_strategy_engine.learning_store import DEFAULT_DATABASE as LEARNING_DATABASE
from scripts.ts_strategy_engine.strategy_learning import retry_assessment
from scripts.ts_validation.dimer_frequency_gate import evaluate_dimer_frequency_gate
from scripts.vasp_result_gate import read_incar_values


REMOTE_PATH = re.compile(r"^~/sbq/[A-Za-z0-9_./-]+$")
JOB_ID = re.compile(r"Job <(\d+)>")
SUBMISSION_ATTEMPT_FILE = "submission_attempt.json"
SUBMISSION_RECORD_FILE = "submission_record.json"
EXPECTED_ACTION = {
    "diagnostic_static": "SUBMIT_DIAGNOSTIC_VASP",
    "neb_pilot": "SUBMIT_DIAGNOSTIC_VASP",
    "ordinary_neb": "SUBMIT_VASP",
    "ci_neb": "ENABLE_CI_NEB",
    "dimer": "START_DIMER",
    "vfa": "START_VFA",
    "connectivity_relax": "SUBMIT_VASP",
}
NEB_KINDS = {"neb_pilot", "ordinary_neb", "ci_neb"}


def preflight(workdir: Path, kind: str, *, learning_database: Path = LEARNING_DATABASE) -> dict[str, Any]:
    required = _required_files(kind)
    missing = [name for name in required if not (workdir / name).is_file()]
    core_ready = all((workdir / name).is_file() for name in ("INCAR", "KPOINTS", "POTCAR.spec", "script.lsf"))
    incar = read_incar_values(workdir / "INCAR") if core_ready else {}
    cores = _script_cores(workdir / "script.lsf") if core_ready else None
    errors = [f"missing:{name}" for name in missing]
    dimer_gate: dict[str, Any] = {}
    vfa_gate: dict[str, Any] = {}
    connectivity_gate: dict[str, Any] = {}
    images: list[Path] = []
    if kind in NEB_KINDS and core_ready:
        neb_errors, images = _check_neb(workdir, kind, incar, cores)
        errors.extend(neb_errors)
    if kind == "diagnostic_static" and core_ready:
        if int(float(incar.get("NSW", 0))) != 0 or int(float(incar.get("IBRION", -1))) != -1:
            errors.append("diagnostic_static_requires_NSW_0_IBRION_-1")
    if kind == "dimer" and core_ready:
        dimer_errors, dimer_gate = _check_dimer(workdir, incar)
        errors.extend(dimer_errors)
    if kind == "vfa" and core_ready:
        vfa_errors, vfa_gate = _check_vfa(workdir, incar)
        errors.extend(vfa_errors)
    if kind == "connectivity_relax" and core_ready:
        connectivity_errors, connectivity_gate = _check_connectivity_relax(workdir, incar)
        errors.extend(connectivity_errors)
    files = [workdir / name for name in required if (workdir / name).is_file()]
    files.extend(directory / "POSCAR" for directory in images if (directory / "POSCAR").is_file())
    manifest = {path.relative_to(workdir).as_posix(): sha256_file(path) for path in files}
    learning_check = retry_assessment(learning_database, kind, vasp_input_hashes(manifest))
    if learning_check["status"] != "NO_KNOWN_FAILURE":
        errors.append("strategy_retry:" + learning_check["status"])
    payload = {
        "schema_version": 1,
        "kind": kind,
        "passed": not errors,
        "errors": errors,
        "cores": cores,
        "images": int(incar["IMAGES"]) if "IMAGES" in incar else None,
        "files": manifest,
        "bundle_sha256": sha256_json({"kind": kind, "files": manifest}),
        "strategy_retry_check": learning_check,
    }
    if kind == "dimer":
        payload["dimer_hard_gate_passed"] = bool(dimer_gate.get("hard_gate_passed"))
        payload["dimer_hard_gate"] = dimer_gate
        payload["dimer_recommended_gate"] = dimer_gate.get("recommended_checks", {})
    if kind == "vfa":
        payload["vfa_hard_gate_passed"] = not vfa_gate.get("errors")
        payload["vfa_hard_gate"] = vfa_gate
    if kind == "connectivity_relax":
        payload["connectivity_hard_gate_passed"] = not connectivity_gate.get("errors")
        payload["connectivity_hard_gate"] = connectivity_gate
    write_json(workdir / "submission_preflight.json", payload)
    return payload


def _required_files(kind: str) -> list[str]:
    required = ["INCAR", "KPOINTS", "POTCAR.spec", "script.lsf"]
    if kind in {"diagnostic_static", "dimer", "vfa", "connectivity_relax"}:
        required.append("POSCAR")
        if kind == "dimer":
            required.extend(
                (
                    "PREVIOUS_POSCAR",
                    "NEXT_POSCAR",
                    "MODECAR",
                    "dimer_handoff.json",
                    "mode_review.json",
                )
            )
        elif kind == "vfa":
            required.extend(("vfa_handoff.json", "vfa_scope_review.json"))
        elif kind == "connectivity_relax":
            required.extend(
                (
                    "connectivity_handoff.json",
                    "connectivity_displacement_review.json",
                    "user_execution_authorization.json",
                )
            )
    elif kind in NEB_KINDS:
        required.extend(
            [
                "path_generation_report.json",
                "path_geometry_diagnosis.json",
                "path_review.json",
                "dist.dat",
                "movie.xyz",
            ]
        )
    return required


def _check_neb(
    workdir: Path, kind: str, incar: dict[str, str], cores: int | None
) -> tuple[list[str], list[Path]]:
    errors: list[str] = []
    count = int(incar.get("IMAGES", 0))
    images = numbered_image_dirs(workdir)
    if [path.name for path in images] != [f"{index:02d}" for index in range(count + 2)]:
        errors.append("image_sequence_mismatch")
    climb = str(incar.get("LCLIMB", "")).upper() in {".TRUE.", "TRUE", "T"}
    if climb != (kind == "ci_neb"):
        errors.append(f"{kind}_requires_LCLIMB_{str(kind == 'ci_neb').lower()}")
    if not cores or count < 1 or cores % count:
        errors.append("mpi_ranks_not_divisible_by_IMAGES")
    else:
        ranks_per_image = cores // count
        if "NPAR" in incar:
            try:
                npar = int(float(incar["NPAR"]))
            except (TypeError, ValueError):
                errors.append("invalid_NPAR")
            else:
                if npar < 1:
                    errors.append("invalid_NPAR")
                elif ranks_per_image % npar:
                    errors.append("mpi_ranks_per_image_not_divisible_by_NPAR")
    errors.extend(f"missing:{directory.name}/POSCAR" for directory in images if not (directory / "POSCAR").is_file())
    pilot_path = workdir / "neb_pilot_result.json"
    if kind == "ordinary_neb" and pilot_path.is_file():
        try:
            validate_pilot_result(pilot_path, workdir)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"ordinary_neb_pilot_validation_failed:{exc}")
    return errors, images


def _check_dimer(workdir: Path, incar: dict[str, str]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if int(float(incar.get("ICHAIN", 0))) != 2 or int(float(incar.get("NSW", 0))) < 1:
        errors.append("dimer_requires_ICHAIN_2_and_positive_NSW")
    gate = validate_modecar_bundle(workdir)
    errors.extend(f"dimer_hard_gate:{value}" for value in gate.get("hard_gate_errors", []))
    return errors, gate


def _check_vfa(workdir: Path, incar: dict[str, str]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    try:
        valid_incar = (
            int(float(incar.get("IBRION", 0))) == 5
            and int(float(incar.get("NSW", 0))) > 0
            and int(float(incar.get("NFREE", 0))) == 2
            and float(incar.get("POTIM", 0)) > 0
        )
    except (TypeError, ValueError):
        valid_incar = False
    if not valid_incar:
        errors.append("vfa_requires_IBRION_5_positive_NSW_NFREE_2_and_positive_POTIM")
    handoff_path = workdir / "vfa_handoff.json"
    scope_path = workdir / "vfa_scope_review.json"
    if not handoff_path.is_file() or not scope_path.is_file() or not (workdir / "POSCAR").is_file():
        return errors, {"errors": errors}
    handoff = load_json_object(handoff_path)
    scope = load_json_object(scope_path)
    structure = read_poscar(workdir / "POSCAR")
    active = [
        index
        for index, flags in enumerate(structure.flags)
        if structure.selective and flags and all(value == "T" for value in flags)
    ]
    expected_active = [int(value) for value in handoff.get("active_atom_indices_zero_based", [])]
    reaction = {int(value) for value in handoff.get("reaction_atom_indices_zero_based", [])}
    active_set_policy = handoff.get("active_set_policy")
    legacy_scope = active_set_policy is None
    checks = {
        "frequency_structure_bound": handoff.get("frequency_poscar_sha256")
        == sha256_file(workdir / "POSCAR"),
        "active_set_matches_selective_dynamics": active == expected_active,
        "reaction_atoms_active": reaction <= set(active),
        "partial_hessian_policy_bound": legacy_scope
        or (
            handoff.get("frequency_method") == "finite_difference_partial_hessian"
            and active_set_policy == "contract_defined_local"
            and handoff.get("active_indices_source")
            == "explicit_reaction_contract_review"
            and handoff.get("full_hessian_required") is False
            and scope.get("frequency_method") == handoff.get("frequency_method")
            and scope.get("active_set_policy") == active_set_policy
            and scope.get("active_indices_source")
            == handoff.get("active_indices_source")
        ),
        "scope_review_accepted": scope.get("status")
        in {"accepted_for_partial_hessian", "accepted_for_diagnostic_frequency"},
        "scope_review_identity": bool(scope.get("reviewer") and scope.get("reviewed_at")),
        "scope_review_structure_bound": scope.get("frequency_poscar_sha256")
        == sha256_file(workdir / "POSCAR"),
        "scope_review_handoff_bound": scope.get("vfa_handoff_sha256")
        == sha256_file(handoff_path),
        "scope_review_active_set": scope.get("active_atom_indices_zero_based")
        == expected_active,
    }
    if str(handoff.get("source_method", "")).lower() == "dimer":
        saddle_path = _manifest_path(workdir, handoff.get("saddle_analysis_source"))
        source_path = _manifest_path(workdir, handoff.get("source_ts_candidate"))
        embedded_gate = handoff.get("dimer_frequency_gate") or {}
        review_path = _manifest_path(workdir, embedded_gate.get("manual_review_path"))
        dimer_gate = {}
        if saddle_path and source_path and saddle_path.is_file() and source_path.is_file():
            dimer_gate = evaluate_dimer_frequency_gate(
                load_json_object(saddle_path), saddle_path, source_path, review_path
            )
        checks.update(
            {
                "dimer_saddle_analysis_bound": bool(
                    saddle_path
                    and saddle_path.is_file()
                    and handoff.get("saddle_analysis_sha256") == sha256_file(saddle_path)
                ),
                "dimer_source_structure_bound": bool(
                    source_path
                    and source_path.is_file()
                    and handoff.get("source_sha256") == sha256_file(source_path)
                ),
                "dimer_frequency_gate_passed": bool(
                    dimer_gate.get("frequency_handoff_allowed")
                ),
            }
        )
    errors.extend(f"vfa_hard_gate:{name}" for name, passed in checks.items() if not passed)
    return errors, {"checks": checks, "errors": errors}


def _check_connectivity_relax(
    workdir: Path, incar: dict[str, str]
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    try:
        incar_valid = (
            int(float(incar.get("IBRION", 0))) == 2
            and int(float(incar.get("NSW", 0))) > 0
            and float(incar.get("EDIFFG", 0)) < 0
            and "IMAGES" not in incar
            and int(float(incar.get("ICHAIN", 0))) != 2
        )
    except (TypeError, ValueError):
        incar_valid = False
    if not incar_valid:
        errors.append("connectivity_relax_requires_downhill_force_relaxation")
    handoff_path = workdir / "connectivity_handoff.json"
    review_path = workdir / "connectivity_displacement_review.json"
    poscar_path = workdir / "POSCAR"
    if not all(path.is_file() for path in (handoff_path, review_path, poscar_path)):
        return errors, {"errors": errors}
    handoff = load_json_object(handoff_path)
    review = load_json_object(review_path)
    structure = read_poscar(poscar_path)
    fixed = [
        index
        for index, flags in enumerate(structure.flags)
        if structure.selective and flags and all(value == "F" for value in flags)
    ]
    checks = {
        "document_kind": handoff.get("document_kind") == "ts_connectivity_relax_handoff",
        "direction": handoff.get("direction") in {"positive", "negative"},
        "displacement_structure_bound": handoff.get("displacement_poscar_sha256") == sha256_file(poscar_path),
        "review_accepted": review.get("status") == "accepted_for_connectivity_displacement",
        "review_identity": bool(review.get("reviewer") and review.get("reviewed_at")),
        "review_bound": handoff.get("displacement_review_sha256") == sha256_file(review_path),
        "review_source_bound": review.get("source_saddle_sha256") == handoff.get("source_saddle_sha256"),
        "review_vfa_bound": review.get("vfa_analysis_sha256") == handoff.get("vfa_analysis_sha256"),
        "review_mode_bound": review.get("mode_index") == handoff.get("mode_index"),
        "review_amplitude_bound": review.get("amplitude_A") == handoff.get("amplitude_A"),
        "contract_bound": all(handoff.get(key) for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")),
        "selective_dynamics_preserved": structure.selective,
        "fixed_atoms_match_handoff": fixed == handoff.get("fixed_atom_indices_zero_based"),
        "bottom_18_fe_fixed": fixed == list(range(18)),
    }
    errors.extend(f"connectivity_hard_gate:{name}" for name, passed in checks.items() if not passed)
    return errors, {"checks": checks, "errors": errors, "direction": handoff.get("direction")}


def _manifest_path(workdir: Path, value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    return path if path.exists() else workdir / path


def submit(
    workdir: Path,
    decision_path: Path,
    host: str,
    remote_dir: str,
    potcar_source: str,
    potcar_sha256: str,
    action: str,
    reuse_uploaded: bool = False,
) -> dict[str, Any]:
    configured = load_execution_backends().vasp
    backend = require_vasp_backend(host, configured.name)
    attempt_path = workdir / SUBMISSION_ATTEMPT_FILE
    record_path = workdir / SUBMISSION_RECORD_FILE
    if record_path.exists():
        raise FileExistsError(
            f"calculation already has a submission record: {record_path}"
        )
    if attempt_path.exists():
        raise RuntimeError(
            "submission retry refused because a previous remote bsub outcome "
            f"is unresolved; inspect {attempt_path} and follow "
            "SUBMISSION_RECOVERY.md"
        )
    if not REMOTE_PATH.fullmatch(remote_dir) or not REMOTE_PATH.fullmatch(potcar_source):
        raise ValueError("remote paths must remain under ~/sbq and contain no shell metacharacters")
    report = load_json_object(workdir / "submission_preflight.json")
    current = preflight(workdir, report["kind"])
    if not current["passed"] or current["bundle_sha256"] != report["bundle_sha256"]:
        raise ValueError("submission bundle changed after preflight")
    if EXPECTED_ACTION.get(current["kind"]) != action:
        raise ValueError(f"{current['kind']} submission requires action {EXPECTED_ACTION.get(current['kind'])}")
    decision = load_json_object(decision_path)
    embedded = decision.get("EVIDENCE", {}).get("preflight", {})
    if embedded.get("bundle_sha256") != current["bundle_sha256"]:
        raise ValueError("gate decision is not bound to the current submission bundle")
    if embedded.get("strategy_retry_check", {}) != current.get("strategy_retry_check", {}):
        raise ValueError("strategy retry evidence changed; regenerate the execution gate decision")
    require_action(decision_path, action, decision["state_sha256"])
    parent, name = remote_dir.rsplit("/", 1)
    if workdir.name != name:
        raise ValueError("local and remote calculation directory names must match")
    if reuse_uploaded:
        _verify_remote_bundle(host, remote_dir, current["files"])
    else:
        _run(["ssh", host, f"test ! -e {remote_dir} && mkdir -p {parent}"])
        _upload_manifest_files(host, parent, workdir, current["files"])
    remote_check = (
        f"cp {potcar_source} {remote_dir}/POTCAR && "
        f"test \"$(sha256sum {remote_dir}/POTCAR | awk '{{print $1}}')\" = {potcar_sha256} && "
        f"cd {remote_dir} && test -s INCAR && test -s KPOINTS && test -s POTCAR && "
        "bsub script.lsf"
    )
    write_json(
        attempt_path,
        {
            "status": "SUBMISSION_OUTCOME_UNRESOLVED",
            "server_alias": host,
            "remote_dir": remote_dir,
            "action": action,
            "bundle_sha256": current["bundle_sha256"],
            "gate_decision_sha256": sha256_file(decision_path),
        },
    )
    completed = _run(["ssh", host, remote_check])
    match = JOB_ID.search(completed.stdout)
    if not match:
        raise RuntimeError(f"could not parse LSF job ID: {completed.stdout.strip()}")
    payload = {
        "server_alias": host,
        "scheduler": backend.name,
        "job_id": match.group(1),
        "remote_dir": remote_dir,
        "action": action,
        "gate_decision_sha256": sha256_file(decision_path),
        "bundle_sha256": current["bundle_sha256"],
        "potcar_source": potcar_source,
        "potcar_sha256": potcar_sha256,
        "submit_stdout": completed.stdout.strip(),
    }
    write_json(record_path, payload)
    attempt_path.unlink()
    return payload


def stop_job(decision_path: Path, host: str, job_id: str, output: Path) -> dict[str, Any]:
    configured = load_execution_backends().vasp
    backend = require_vasp_backend(host, configured.name)
    decision = load_json_object(decision_path)
    require_action(decision_path, "STOP_JOB", decision["state_sha256"])
    scheduler = decision.get("EVIDENCE", {}).get("scheduler", {})
    expected_status = scheduler.get("status")
    if (
        str(scheduler.get("job_id")) != str(job_id)
        or expected_status not in {"PEND", "RUN"}
    ):
        raise ValueError("STOP_JOB decision is not bound to this active job")
    query = _run(["ssh", host, "bjobs", "-a", str(job_id)])
    live_status = _bjobs_status(query.stdout, str(job_id))
    if live_status != expected_status:
        raise ValueError(
            f"job {job_id} changed from {expected_status} to {live_status}; "
            "refresh scheduler evidence and the gate decision"
        )
    completed = _run(["ssh", host, "bkill", str(job_id)])
    payload = {
        "server_alias": host,
        "scheduler": backend.name,
        "job_id": str(job_id),
        "action": "STOP_JOB",
        "prior_status": live_status,
        "gate_decision_sha256": sha256_file(decision_path),
        "query_stdout": query.stdout,
        "stop_stdout": completed.stdout.strip(),
    }
    write_json(output, payload)
    return payload


def _bjobs_status(stdout: str, job_id: str) -> str:
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] == str(job_id):
            status = fields[2].upper()
            if status in {"PEND", "RUN", "DONE", "EXIT"}:
                return status
    raise ValueError(f"live bjobs output does not contain job {job_id}")


def _script_cores(path: Path) -> int | None:
    match = re.search(r"^NP=(\d+)\s*$", path.read_text(encoding="ascii"), re.MULTILINE)
    return int(match.group(1)) if match else None


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            check=False,
            timeout=EXTERNAL_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"command timed out after {EXTERNAL_COMMAND_TIMEOUT_SECONDS} seconds: "
            f"{argv[0]}"
        ) from exc
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {completed.stderr.strip()}")
    return completed


def _verify_remote_bundle(host: str, remote_dir: str, files: dict[str, str]) -> None:
    checks = [
        f"test \"$(sha256sum {remote_dir}/{name} | awk '{{print $1}}')\" = {digest}"
        for name, digest in files.items()
    ]
    _run(["ssh", host, " && ".join([f"test -d {remote_dir}", *checks])])


def _upload_manifest_files(
    host: str, remote_parent: str, workdir: Path, files: dict[str, str]
) -> None:
    """Upload only hash-bound preflight files, preserving their relative paths."""
    with tempfile.TemporaryDirectory(prefix="vasp-submit-") as temporary:
        staged = Path(temporary) / workdir.name
        for relative in files:
            source = workdir / relative
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        _run(["scp", "-r", str(staged), f"{host}:{remote_parent}/"])


def main() -> None:
    vasp_backend = load_execution_backends().vasp
    parser = argparse.ArgumentParser(description="Preflight or submit a gate-authorized VASP task.")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("preflight")
    check.add_argument("--workdir", type=Path, required=True)
    check.add_argument("--kind", choices=tuple(EXPECTED_ACTION), required=True)
    launch = commands.add_parser("submit")
    launch.add_argument("--workdir", type=Path, required=True)
    launch.add_argument("--decision", type=Path, required=True)
    launch.add_argument("--host", default=vasp_backend.server_alias)
    launch.add_argument("--remote-dir", required=True)
    launch.add_argument("--potcar-source", required=True)
    launch.add_argument("--potcar-sha256", required=True)
    launch.add_argument("--action", choices=tuple(EXPECTED_ACTION.values()), required=True)
    launch.add_argument("--reuse-uploaded", action="store_true")
    stop = commands.add_parser("stop")
    stop.add_argument("--decision", type=Path, required=True)
    stop.add_argument("--host", default=vasp_backend.server_alias)
    stop.add_argument("--job-id", required=True)
    stop.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        result = preflight(args.workdir, args.kind)
    elif args.command == "submit":
        result = submit(
            args.workdir,
            args.decision,
            args.host,
            args.remote_dir,
            args.potcar_source,
            args.potcar_sha256,
            args.action,
            args.reuse_uploaded,
        )
    else:
        result = stop_job(args.decision, args.host, args.job_id, args.output)
    print(result["job_id"] if "job_id" in result else ("PASS" if result["passed"] else "STOP"))


if __name__ == "__main__":
    main()
