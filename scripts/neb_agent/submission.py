from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.artifact_io import (
    load_json_object, require_sha256, sha256_file, sha256_json, write_json,
    write_json_exclusive,
)
from scripts.convergence.common import EXTERNAL_COMMAND_TIMEOUT_SECONDS
from scripts.execution_backends import load_execution_backends, require_vasp_backend
from scripts.neb_agent.pilot_validation import validate_pilot_result
from scripts.neb_agent.utils_structure import numbered_image_dirs, read_poscar
from scripts.ts_strategy_engine.dimer_gate import validate_modecar_bundle
from scripts.ts_strategy_engine.execution_gate import require_action
from scripts.ts_strategy_engine.execution_evidence import workdir_identity
from scripts.ts_strategy_engine.execution_path_rules import (
    require_job_id, require_local_input, require_relative_input_path, require_remote_path,
)
from scripts.ts_strategy_engine.learning_evidence import vasp_input_hashes
from scripts.ts_strategy_engine.learning_store import DEFAULT_DATABASE as LEARNING_DATABASE
from scripts.ts_strategy_engine.strategy_learning import retry_assessment
from scripts.ts_validation.dimer_frequency_gate import evaluate_dimer_frequency_gate
from scripts.vasp_result_gate import read_incar_values


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
UNKNOWN = "UNKNOWN_NEEDS_RECONCILIATION"


@dataclass(frozen=True)
class InputBundle:
    kind: str
    files: tuple[tuple[str, str], ...]
    bundle_sha256: str

    @classmethod
    def from_preflight(cls, report: dict[str, Any]) -> InputBundle:
        kind = report["kind"]
        if kind not in EXPECTED_ACTION or not report.get("passed"):
            raise ValueError("submission bundle changed or preflight did not pass")
        files = report["files"]
        if not isinstance(files, dict) or not set(_required_files(kind)) <= set(files):
            raise ValueError("input bundle manifest is incomplete")
        validated = tuple(sorted(
            (require_relative_input_path(name), require_sha256(digest, label=name))
            for name, digest in files.items()
        ))
        digest = require_sha256(report["bundle_sha256"], label="input bundle")
        if digest != sha256_json({"kind": kind, "files": dict(validated)}):
            raise ValueError("input bundle manifest hash mismatch")
        return cls(kind, validated, digest)

    def verify(self, workdir: Path) -> None:
        for name, digest in self.files:
            if sha256_file(require_local_input(workdir, name)) != digest:
                raise ValueError(f"submission bundle changed: {name}")


@dataclass(frozen=True)
class SubmissionReservation:
    reservation_id: str
    created_at_utc: str
    workdir_identity: str
    server_alias: str
    remote_dir: str
    action: str
    bundle_sha256: str
    evidence_sha256: str
    gate_decision_sha256: str
    authorization: dict[str, Any]
    status: str = UNKNOWN


@dataclass(frozen=True)
class SubmissionResult:
    reservation_id: str
    status: str
    job_id: str | None
    submit_stdout: str


def submission_status(workdir: Path) -> dict[str, Any]:
    """Read-only recovery: missing/corrupt receipts never authorize another bsub."""
    reservation = workdir / SUBMISSION_ATTEMPT_FILE
    receipt = workdir / SUBMISSION_RECORD_FILE
    if receipt.exists():
        try:
            result = load_json_object(receipt)
            if result.get("status") == "SUBMITTED":
                require_job_id(result["job_id"])
                saved = load_json_object(reservation)
                if result.get("reservation_id") == saved["reservation_id"]:
                    return result
        except (OSError, KeyError, TypeError, ValueError):
            pass
        return {"status": UNKNOWN}
    if reservation.exists() or reservation.is_symlink():
        return {"status": UNKNOWN}
    return {"status": "NOT_RESERVED"}


def preflight(
    workdir: Path, kind: str, *, learning_database: Path = LEARNING_DATABASE,
    write_report: bool = True,
) -> dict[str, Any]:
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
    if write_report:
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
    from scripts.ts_validation.prepare_vfa_from_ts_image import vfa_scope_checks

    handoff = load_json_object(handoff_path)
    checks = vfa_scope_checks(workdir, handoff_path)
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
    workdir = workdir.resolve(strict=True)
    attempt_path = workdir / SUBMISSION_ATTEMPT_FILE
    record_path = workdir / SUBMISSION_RECORD_FILE
    if record_path.exists() or record_path.is_symlink():
        raise FileExistsError(f"calculation already has a submission record: {record_path}")
    if attempt_path.exists() or attempt_path.is_symlink():
        raise RuntimeError(
            f"submission retry refused: {UNKNOWN}; inspect {attempt_path} and follow "
            "SUBMISSION_RECOVERY.md"
        )
    require_remote_path(remote_dir)
    require_remote_path(potcar_source)
    potcar_sha256 = require_sha256(potcar_sha256, label="POTCAR")
    parent, name = remote_dir.rsplit("/", 1)
    if workdir.name != name:
        raise ValueError("local and remote calculation directory names must match")
    report = load_json_object(workdir / "submission_preflight.json")
    bundle = InputBundle.from_preflight(report)
    bundle.verify(workdir)
    if EXPECTED_ACTION[bundle.kind] != action:
        raise ValueError(f"{bundle.kind} submission requires action {EXPECTED_ACTION[bundle.kind]}")
    decision = load_json_object(decision_path)
    decision_digest = sha256_file(decision_path)
    _verify_submission_binding(
        workdir, decision_path, decision_digest, decision, report, bundle,
        host, remote_dir, action, potcar_source, potcar_sha256,
    )
    reservation = SubmissionReservation(
        uuid4().hex, datetime.now(timezone.utc).isoformat(), workdir_identity(workdir),
        host, remote_dir, action, bundle.bundle_sha256,
        decision["evidence_binding"]["evidence_sha256"], decision_digest,
        decision["execution_authorization"],
    )
    # This exclusive creation is the linearization point. The reservation is
    # retained on every exit, including success; no code path releases it.
    try:
        write_json_exclusive(attempt_path, asdict(reservation))
    except FileExistsError as exc:
        raise RuntimeError(f"submission retry refused: {UNKNOWN}; reservation already exists") from exc
    try:
        _verify_submission_binding(
            workdir, decision_path, decision_digest, decision, report, bundle,
            host, remote_dir, action, potcar_source, potcar_sha256,
        )
        # Also reserve the remote target, so different local checkouts cannot
        # submit the same uploaded directory. Remote reservations are never removed.
        remote_lock = remote_dir + ".submission-reservation"
        setup = [
            *_remote_path_checks(parent, allow_root=True),
            f"mkdir -p {parent}",
            *_remote_path_checks(remote_dir),
            f"mkdir {remote_lock}",
            f"printf '%s\n' {reservation.reservation_id} > {remote_lock}/reservation_id",
        ]
        if not reuse_uploaded:
            setup.append(f"test ! -e {remote_dir}")
        _run(["ssh", host, _remote_shell(setup)])
        if not reuse_uploaded:
            _upload_manifest_files(host, parent, workdir, dict(bundle.files))
        _verify_submission_binding(
            workdir, decision_path, decision_digest, decision, report, bundle,
            host, remote_dir, action, potcar_source, potcar_sha256,
        )
        # Full verification and bsub share one command for BOTH upload modes.
        # POTCAR is copied first, then included in the complete final manifest.
        remote_check = _remote_shell([
            *_remote_path_checks(remote_lock + "/reservation_id"),
            f'test "$(cat {remote_lock}/reservation_id)" = {reservation.reservation_id}',
            *_remote_path_checks(potcar_source),
            *_remote_path_checks(remote_dir + "/POTCAR"),
            f"test -f {potcar_source}",
            f"test \"$(sha256sum {potcar_source} | awk '{{print $1}}')\" = {potcar_sha256}",
            f"if test ! -e {remote_dir}/POTCAR; then cp {potcar_source} {remote_dir}/POTCAR; fi",
            *_remote_bundle_checks(remote_dir, {**dict(bundle.files), "POTCAR": potcar_sha256}),
            f"cd {remote_dir}",
            "bsub script.lsf",
        ])
        completed = _run(["ssh", host, remote_check])
        matches = JOB_ID.findall(completed.stdout)
        if len(matches) != 1:
            raise RuntimeError(f"could not parse one LSF job ID: {completed.stdout.strip()}")
        result = SubmissionResult(
            reservation.reservation_id, "SUBMITTED", require_job_id(matches[0]),
            completed.stdout.strip(),
        )
        payload = {
            **asdict(result), "server_alias": host, "scheduler": backend.name,
            "remote_dir": remote_dir, "action": action,
            "gate_decision_sha256": decision_digest, "bundle_sha256": bundle.bundle_sha256,
            "potcar_source": potcar_source, "potcar_sha256": potcar_sha256,
        }
        write_json_exclusive(record_path, payload)
        return payload
    except BaseException:
        # A killed process may never reach here. submission_status derives the
        # same UNKNOWN state from a reservation without a valid success receipt.
        try:
            write_json_exclusive(record_path, asdict(SubmissionResult(
                reservation.reservation_id, UNKNOWN, None, "",
            )))
        except (OSError, ValueError):
            pass
        raise


def _verify_submission_binding(
    workdir: Path, decision_path: Path, decision_digest: str, decision: dict[str, Any],
    report: dict[str, Any], bundle: InputBundle, host: str, remote_dir: str,
    action: str, potcar_source: str, potcar_sha256: str,
) -> None:
    if sha256_file(decision_path) != decision_digest:
        raise ValueError("gate decision changed after validation")
    validated = require_action(decision_path, action, decision["state_sha256"])
    auth = validated["EVIDENCE"]["authorization"]
    if (
        auth["action"] != action
        or auth["target"] != {"server_alias": host, "remote_dir": remote_dir}
        or auth["workdir_identity"] != workdir_identity(workdir)
        or auth["bundle_sha256"] != bundle.bundle_sha256
        or auth["potcar"] != {"source": potcar_source, "sha256": potcar_sha256,
                              "spec_sha256": dict(bundle.files)["POTCAR.spec"]}
    ):
        raise ValueError("execution authorization does not bind this target, workdir, bundle or POTCAR")
    bundle.verify(workdir)
    current = preflight(workdir, bundle.kind, write_report=False)
    if current != report or validated["EVIDENCE"].get("preflight") != report:
        raise ValueError("preflight or strategy retry evidence changed; regenerate the execution gate decision")


def stop_job(decision_path: Path, host: str, job_id: str, output: Path) -> dict[str, Any]:
    configured = load_execution_backends().vasp
    backend = require_vasp_backend(host, configured.name)
    job_id = require_job_id(job_id)
    decision = load_json_object(decision_path)
    decision_digest = sha256_file(decision_path)
    validated = require_action(decision_path, "STOP_JOB", decision["state_sha256"])
    target = validated["EVIDENCE"]["authorization"]["target"]
    require_remote_path(target["remote_dir"])
    if target["server_alias"] != host or target["job_id"] != job_id:
        raise ValueError("STOP_JOB authorization target mismatch")
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
    if sha256_file(decision_path) != decision_digest:
        raise ValueError("STOP_JOB decision changed during live scheduler verification")
    require_action(decision_path, "STOP_JOB", decision["state_sha256"])
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
            encoding="utf-8",
            errors="replace",
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
    _run(["ssh", host, _remote_shell(_remote_bundle_checks(remote_dir, files))])


def _remote_shell(checks: list[str]) -> str:
    return "bash -c " + shlex.quote("set -euo pipefail; " + " && ".join(checks))


def _remote_path_checks(path: str, *, allow_root: bool = False) -> list[str]:
    require_remote_path(path, allow_root=allow_root)
    parts = path.split("/")
    return [
        'test "$(realpath -e ~/sbq)" = "$HOME/sbq"',
        *(f"test ! -L {'/'.join(parts[:index])}" for index in range(2, len(parts) + 1)),
    ]


def _remote_bundle_checks(remote_dir: str, files: dict[str, str]) -> list[str]:
    require_remote_path(remote_dir)
    if not files:
        raise ValueError("remote manifest must not be empty")
    validated = [
        (require_relative_input_path(name), require_sha256(digest, label=name))
        for name, digest in files.items()
    ]
    checks = [*_remote_path_checks(remote_dir), f"test -d {remote_dir}"]
    for name, digest in validated:
        path = f"{remote_dir}/{name}"
        checks.extend([
            *_remote_path_checks(path), f"test -f {path}",
            f"test \"$(sha256sum {path} | awk '{{print $1}}')\" = {digest}",
        ])
    # Reused directories must not carry unbound restart files or symlinks.
    checks.extend([
        f"test \"$(find {remote_dir} -type l -print | wc -l)\" -eq 0",
        f"test \"$(find {remote_dir} -type f -print | wc -l)\" -eq {len(files)}",
    ])
    return checks


def _upload_manifest_files(
    host: str, remote_parent: str, workdir: Path, files: dict[str, str]
) -> None:
    """Upload only hash-bound preflight files, preserving their relative paths."""
    require_remote_path(remote_parent, allow_root=True)
    require_relative_input_path(workdir.name)
    validated = {
        require_relative_input_path(name): require_sha256(digest, label=name)
        for name, digest in files.items()
    }
    with tempfile.TemporaryDirectory(prefix="vasp-submit-") as temporary:
        staged = Path(temporary) / workdir.name
        for relative, digest in validated.items():
            source = require_local_input(workdir, relative)
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if sha256_file(target) != digest:
                raise ValueError(f"staged submission bundle changed: {relative}")
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
    status = commands.add_parser("status", help="Read submission/reconciliation state without retrying.")
    status.add_argument("--workdir", type=Path, required=True)
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
    elif args.command == "stop":
        result = stop_job(args.decision, args.host, args.job_id, args.output)
    else:
        result = submission_status(args.workdir)
    print(result.get("job_id") or result.get("status") or ("PASS" if result["passed"] else "STOP"))


if __name__ == "__main__":
    main()
