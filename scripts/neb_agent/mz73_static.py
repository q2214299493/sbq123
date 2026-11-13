"""One explicitly scoped MZ73 GPU-VASP static-label backend, not a job executor."""
from __future__ import annotations

import copy
import re
import shlex
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from scripts.artifact_io import (
    load_json_object, require_sha256, sha256_file, sha256_json, source_file_manifest, source_file_manifest_valid,
)
from scripts.execution_backends import DEFAULT_CONFIG, load_execution_backends
from scripts.scientific_validation import finite_array, finite_number, integer_number, validate_finite_tree
from scripts.ts_strategy_engine.execution_path_rules import require_relative_input_path


BACKEND_ID = "mz73_paper_vasp"
LAUNCHER = "script.sbatch"
PAPER_REQUEST = "paper_DFT_request.json"
STATIC_GEOMETRY_KIND = "mz73_static_candidate_geometry_diagnosis"
STATIC_ANALYSIS_KIND = "mz73_static_output_analysis"
STATIC_PRODUCER = "scripts.neb_agent.mz73_static"
_BOUNDARY = "/home/sbq/sbq"
_CANONICAL_BOUNDARY = "/home/ubuntu/hdd/sbq/sbq"
_FAILED_LEAF = "paper_chco_aqcat25_ft512_20261112_r000_label"
_RECOVERY_LEAF = "paper_chco_aqcat25_ft512_20261112_r000_launch_recovery01_label"
_RECOVERY_SCOPE = {
    "workdir_name": _RECOVERY_LEAF, "failed_workdir_name": _FAILED_LEAF,
    "failed_job_id": "13901", "probe_job_id": "13902", "maximum_attempts": 1,
    "consumes_new_scientific_round": False,
}


def _safe_absolute_path(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("/") or PurePosixPath(value).as_posix() != value:
        raise ValueError("backend path must be a normalized absolute POSIX path")
    require_relative_input_path(value[1:])
    return value


def require_mz73_path(backend: dict[str, Any], value: str, *, allow_root: bool = False) -> str:
    path = _safe_absolute_path(value)
    boundary = backend["remote_write_boundary"]
    if path == boundary and allow_root:
        return path
    if not path.startswith(boundary + "/"):
        raise ValueError("MZ73 path escapes the configured write boundary")
    return path


def canonical_remote_path(backend: dict[str, Any], path: str) -> str:
    require_mz73_path(backend, path, allow_root=True)
    return backend["canonical_write_boundary"] + path[len(backend["remote_write_boundary"]):]


def require_remote_target(backend: dict[str, Any], remote_dir: str, workdir_name: str) -> str:
    require_mz73_path(backend, remote_dir)
    if workdir_name not in backend["allowed_workdir_names"]:
        raise ValueError("MZ73 experiment does not authorize this workdir")
    if remote_dir != backend["remote_root"] + "/" + workdir_name:
        raise ValueError("MZ73 target must match the exact experiment root and local leaf")
    return remote_dir


def _validate_fixed_scope(backend: dict[str, Any]) -> None:
    from scripts.neb_agent.mz73_continuation import validate_scope
    from scripts.neb_agent.mz73_timebudget import validate_budget_scope

    fixed = {
        "role": "scoped_gpu_vasp_force_label_experiment", "scheduler": "Slurm", "ssh_backend_ref": "aqcat_gpu",
        "allowed_kind": "diagnostic_static", "remote_write_boundary": _BOUNDARY,
        "canonical_write_boundary": _CANONICAL_BOUNDARY, "partition": "gpu", "node": "MZ73",
        "mpi_ranks": 1, "gpus": 1, "cpus_per_task": 4, "memory": "16G", "requeue": False,
        "automatic_retries": 0, "gpu_parallel_overrides": {"NPAR": 1, "NCORE": 1, "KPAR": 1},
        "automatic_remote_submission": False, "final_energy_or_ts_acceptance": False,
    }
    if any(type(backend.get(key)) is not type(value) or backend.get(key) != value for key, value in fixed.items()):
        raise ValueError("MZ73 experimental backend scope or resource limits were changed")
    if not re.fullmatch(r"00:(?:0[1-9]|[12][0-9]|30):00", str(backend.get("time_limit", ""))):
        raise ValueError("MZ73 static label time limit must be at most thirty minutes")
    names = backend.get("allowed_workdir_names")
    if not isinstance(names, list) or not names or len(set(names)) != len(names):
        raise ValueError("MZ73 experiment requires explicit, unique workdir names")
    for name in names:
        require_relative_input_path(name)
        if "/" in name:
            raise ValueError("MZ73 experiment scope must contain leaf names only")
    recovery = backend.get("launch_recovery")
    if recovery is not None and (not isinstance(recovery, dict) or recovery != _RECOVERY_SCOPE
                                 or any(type(recovery.get(k)) is not type(v) for k, v in _RECOVERY_SCOPE.items())
                                 or _RECOVERY_LEAF not in names):
        raise ValueError("MZ73 launch recovery must retain the explicitly reviewed once-only scope")
    if _RECOVERY_LEAF in names and recovery != _RECOVERY_SCOPE:
        raise ValueError("MZ73 launch recovery is not explicitly registered")
    validate_budget_scope(backend)
    validate_scope(backend)
    caps = backend.get("reviewed_contract")
    if not isinstance(caps, dict) or set(caps) != {"contract_sha256", "compatibility_sha256", "atom_map_sha256"}:
        raise ValueError("MZ73 experiment requires its exact reviewed contract identities")
    for key, value in caps.items():
        require_sha256(value, label="reviewed " + key)
    require_mz73_path(backend, backend.get("remote_root"))


def load_mz73_static_backend(
    workdir_name: str, kind: str = "diagnostic_static", *, config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Resolve only the registered two-label experiment, keeping default LSF intact."""
    load_execution_backends(config_path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    configured = payload["backends"].get(BACKEND_ID)
    if not isinstance(configured, dict):
        raise ValueError("MZ73 GPU VASP experiment is not explicitly registered")
    backend = copy.deepcopy(configured)
    _validate_fixed_scope(backend)
    if kind != "diagnostic_static" or workdir_name not in backend["allowed_workdir_names"]:
        raise ValueError("MZ73 backend permits only the explicitly scoped diagnostic_static workdirs")
    gpu = payload["backends"][backend["ssh_backend_ref"]]
    if gpu.get("observed_hostname") != "MZ73" or gpu.get("remote_write_boundary") != _BOUNDARY:
        raise ValueError("MZ73 SSH reference does not identify the verified GPU backend")
    ssh = gpu.get("ssh")
    if not isinstance(ssh, dict) or ssh.get("identities_only") is not True:
        raise ValueError("MZ73 SSH must retain IdentitiesOnly")
    for key in ("host", "user"):
        if not isinstance(ssh.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", ssh[key]):
            raise ValueError("invalid referenced MZ73 SSH metadata")
    if type(ssh.get("port")) is not int or not 1 <= ssh["port"] <= 65535 or not ssh.get("identity_file"):
        raise ValueError("invalid referenced MZ73 SSH port or identity path")
    for key in ("mpi_executable", "vasp_executable"):
        _safe_absolute_path(backend.get(key))
    libraries = backend.get("library_paths")
    if not isinstance(libraries, list) or not libraries:
        raise ValueError("MZ73 VASP runtime library paths are missing")
    for directory in libraries:
        _safe_absolute_path(directory)
    backend.update({"id": BACKEND_ID, "ssh": copy.deepcopy(ssh), "config_sha256": sha256_file(config_path)})
    extension = backend.get("time_budget_extension")
    if extension and workdir_name in extension["allowed_workdir_names"]:
        backend["time_limit"] = extension["time_limit"]
        backend["requires_budget_authorization"] = True
    from scripts.neb_agent.mz73_continuation import NAMES

    if workdir_name in NAMES:
        backend["time_limit"] = backend["continuous_active_learning"]["time_limit"]
        backend["memory"] = backend["continuous_active_learning"]["memory"]
        backend["requires_continuation_authorization"] = True
    return backend


def _ssh_options(backend: dict[str, Any], *, scp: bool = False) -> list[str]:
    ssh = backend["ssh"]
    return ["-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=8", "-i", str(ssh["identity_file"]), "-P" if scp else "-p", str(ssh["port"])]


def ssh_argv(backend: dict[str, Any], command: str) -> list[str]:
    ssh = backend["ssh"]
    return ["ssh", "-T", *_ssh_options(backend), "--", f"{ssh['user']}@{ssh['host']}", command]


def scp_argv(backend: dict[str, Any], staged: str, parent: str) -> list[str]:
    require_mz73_path(backend, parent, allow_root=True)
    ssh = backend["ssh"]
    return ["scp", *_ssh_options(backend, scp=True), "-r", "--", staged, f"{ssh['user']}@{ssh['host']}:{parent}/"]


def remote_path_checks(backend: dict[str, Any], path: str, *, allow_root: bool = False) -> list[str]:
    """Allow the known root mapping, but no symlinks or escape beneath it."""
    require_mz73_path(backend, path, allow_root=allow_root)
    root, canonical = backend["remote_write_boundary"], backend["canonical_write_boundary"]
    relative = path[len(root):].strip("/").split("/") if path != root else []
    checks = [f'test "$(realpath -e -- {shlex.quote(root)})" = {shlex.quote(canonical)}',
              f'test "$(realpath -m -- {shlex.quote(path)})" = {shlex.quote(canonical_remote_path(backend, path))}']
    checks.extend(f"test ! -L {shlex.quote(root + '/' + '/'.join(relative[:index]))}"
                  for index in range(1, len(relative) + 1))
    return checks


def render_launcher(backend: dict[str, Any]) -> str:
    """Produce the only accepted single-rank/single-GPU script for this experiment."""
    libraries = ":".join(backend["library_paths"])
    return f'''#!/bin/bash
#SBATCH --partition=gpu
#SBATCH --nodelist=MZ73
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem={backend["memory"]}
#SBATCH --time={backend["time_limit"]}
#SBATCH --no-requeue
set -euo pipefail
finish() {{
    code=$?
    trap - EXIT
    set -C
    printf '{{"document_kind":"producer_exit_record","evidence_class":"process_only_not_scheduler_terminal_state","job_id":"%s","exit_code":%d}}\\n' "${{SLURM_JOB_ID:-unknown}}" "$code" > producer_exit_record.json
    exit "$code"
}}
trap finish EXIT
test -n "${{SLURM_JOB_ID:-}}"
test "${{SLURM_NTASKS:-0}}" = 1
case "${{CUDA_VISIBLE_DEVICES:-}}" in ''|*,*) exit 2 ;; esac
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export TMPDIR="$PWD/tmp" XDG_CACHE_HOME="$PWD/cache/xdg" CUDA_CACHE_PATH="$PWD/cache/cuda"
mkdir -p -- "$TMPDIR" "$XDG_CACHE_HOME" "$CUDA_CACHE_PATH"
export LD_LIBRARY_PATH={shlex.quote(libraries)}"${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}"
test -x {shlex.quote(backend["mpi_executable"])}
test -x {shlex.quote(backend["vasp_executable"])}
{shlex.quote(backend["mpi_executable"])} --bind-to none -np 1 {shlex.quote(backend["vasp_executable"])} > vasp.out 2>&1
'''


def validate_launcher(backend: dict[str, Any], path: Path) -> None:
    if path.read_bytes() != render_launcher(backend).encode("ascii"):
        raise ValueError("MZ73 launcher differs from the bound single-rank/single-GPU template")


def sbatch_command(backend: dict[str, Any], remote_dir: str) -> str:
    require_mz73_path(backend, remote_dir)
    return shlex.join([
        "sbatch", "--parsable", "--partition=gpu", "--nodelist=MZ73", "--nodes=1", "--ntasks=1",
        "--cpus-per-task=4", "--gres=gpu:1", "--mem=" + backend["memory"], "--time=" + backend["time_limit"], "--no-requeue",
        "--chdir=" + remote_dir, "--output=" + remote_dir + "/slurm-%j.out",
        "--error=" + remote_dir + "/slurm-%j.err", LAUNCHER,
    ])


def parse_sbatch_job_id(stdout: str) -> str:
    match = re.fullmatch(r"([1-9][0-9]{0,19})(?:;[A-Za-z0-9_.-]+)?\s*", stdout)
    if not match:
        raise ValueError("sbatch did not return exactly one native parsable Slurm job ID")
    return match.group(1)


def validate_paper_dft_request(workdir: Path, *, backend: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bind the independently prepared paper request to this exact static POSCAR."""
    path = workdir / PAPER_REQUEST
    request = load_json_object(path)
    if (request.get("document_kind") != "paper_sequential_DFT_request"
            or request.get("calculation") != "exact_structure_static_single_point"
            or request.get("requires_exact_structure_hash_gate") is not True
            or request.get("requires_authoritative_execution_gate") is not True):
        raise ValueError("MZ73 static calculation requires its exact paper DFT request")
    identities = {key: require_sha256(request.get(key), label=key) for key in (
        "protocol_sha256", "candidate_structure_sha256", "search_checkpoint_sha256", "contract_sha256", "compatibility_sha256",
    )}
    if identities["candidate_structure_sha256"] != sha256_file(workdir / "POSCAR"):
        raise ValueError("paper DFT request does not match the candidate POSCAR")
    backend = backend or load_mz73_static_backend(workdir.name)
    if any(identities[key] != backend["reviewed_contract"][key] for key in ("contract_sha256", "compatibility_sha256")):
        raise ValueError("paper DFT request belongs to another reviewed contract")
    result = {**identities, "request_sha256": sha256_file(path)}
    if workdir.name == _RECOVERY_LEAF:
        result["launch_recovery"] = _validate_launch_recovery(workdir, request, backend)
    elif "launch_recovery" in request:
        raise ValueError("launch recovery cannot consume or overwrite a scientific-round leaf")
    from scripts.neb_agent.mz73_timebudget import TIMEOUT_LEAF, validate_budget_authorization, validate_timebudget_restart

    if backend.get("requires_continuation_authorization"):
        from scripts.neb_agent.mz73_continuation import validate_request

        result["execution_budget_authorization"] = validate_request(workdir, request, backend)
    elif backend.get("requires_budget_authorization"):
        result["execution_budget_authorization"] = validate_budget_authorization(workdir, request, backend)
    elif "execution_budget_authorization" in request:
        raise ValueError("extended budget metadata is outside its exact two-leaf scope")
    if workdir.name == TIMEOUT_LEAF:
        result["timebudget_restart"] = validate_timebudget_restart(workdir, request, backend)
    elif "timebudget_restart" in request:
        raise ValueError("TIMEOUT restart metadata is forbidden outside its one fixed leaf")
    return result


def _bound_raw_source(descriptor: Any) -> Path:
    if not isinstance(descriptor, dict) or set(descriptor) != {"path", "sha256"}:
        raise ValueError("launch recovery requires exact raw source descriptors")
    path = Path(descriptor["path"])
    if (not path.is_absolute() or not path.is_file()
            or sha256_file(path) != require_sha256(descriptor["sha256"], label="recovery source")):
        raise ValueError("launch recovery raw source is missing or changed")
    return path.resolve()


def _validate_launch_recovery(workdir: Path, request: dict, backend: dict) -> dict[str, Any]:
    """Validate this one reviewed pre-VASP launch failure; never grant a retry."""
    recovery = request.get("launch_recovery")
    if (backend.get("launch_recovery") != _RECOVERY_SCOPE or not isinstance(recovery, dict)
            or set(recovery) != {"failed_job_id", "failed_workdir_name", "failure_review", "backend_snapshot",
                                 "no_new_scientific_round"}
            or recovery["failed_job_id"] != "13901" or recovery["failed_workdir_name"] != _FAILED_LEAF
            or recovery["no_new_scientific_round"] is not True):
        raise ValueError("launch recovery does not match its fixed infrastructure-only scope")
    review_path = _bound_raw_source(recovery["failure_review"])
    snapshot = _bound_raw_source(recovery["backend_snapshot"])
    review = load_json_object(review_path)
    required = {
        "document_kind": "paper_prelaunch_failure_evidence", "job_id": "13901",
        "native_state": "FAILED", "native_exit_code": "131:0", "VASP_started": False,
        "accepted_label_count": 0, "training_performed": False, "failure_stage": "mpi_prelaunch",
        "vasp_started": False, "dft_label_created": False,
    }
    if any(type(review.get(k)) is not type(v) or review.get(k) != v for k, v in required.items()):
        raise ValueError("launch recovery lacks reviewed evidence that VASP never started")
    absence = review.get("remote_absence_check", {})
    if absence.get("command") != "test absence of OUTCAR OSZICAR CONTCAR" or type(absence.get("returncode")) is not int or absence["returncode"] != 0:
        raise ValueError("launch recovery lacks reviewed remote output-absence evidence")
    sources = review.get("source_files")
    required_sources = {"terminal", "stdout", "producer", "submission", "failed_state", "MPI_probe",
                        "MPI_probe_terminal", "backend_snapshot"}
    if not isinstance(sources, dict) or not required_sources <= set(sources):
        raise ValueError("launch recovery review is missing raw source evidence")
    paths = {key: _bound_raw_source(value) for key, value in sources.items()}
    if paths["backend_snapshot"] != snapshot:
        raise ValueError("launch recovery backend snapshot differs from reviewed evidence")
    original = (workdir.parent / _FAILED_LEAF).resolve()
    for key, name in {"terminal": "slurm_13901.terminal.json", "stdout": "vasp.out",
                      "producer": "producer_exit_record.json", "submission": "submission_record.json"}.items():
        if paths[key] != original / name:
            raise ValueError("launch recovery evidence belongs to another original directory")
    if any((original / name).exists() for name in ("OUTCAR", "OSZICAR", "CONTCAR", "vasprun.xml")):
        raise ValueError("launch recovery refuses an original job with VASP outputs")
    _validate_recovery_request_identity(original, request, review)
    for key, source in {"failed_state_artifact_sha256": "failed_state", "scheduler_evidence_sha256": "terminal",
                        "launcher_log_sha256": "stdout"}.items():
        if review.get(key) != sources[source]["sha256"]:
            raise ValueError("launch recovery wrapper disagrees with its raw evidence")
    receipt, bundle_sha256 = _validate_failed_recovery_submission(original, snapshot, paths, review)
    for name in ("POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "POTCAR"):
        if sha256_file(original / name) != sha256_file(workdir / name):
            raise ValueError("launch recovery must preserve every original scientific input")
    if sha256_file(workdir / "POTCAR") != receipt.get("potcar_sha256"):
        raise ValueError("launch recovery POTCAR differs from the original submitted bundle")
    _validate_recovery_probe(workdir, backend, paths)
    return {**recovery, "original_bundle_sha256": bundle_sha256,
            "potcar_sha256": receipt["potcar_sha256"], "failure_source_files": sources}


def _validate_recovery_request_identity(original: Path, request: dict, review: dict) -> None:
    original_request = load_json_object(original / PAPER_REQUEST)
    unsigned = {key: value for key, value in request.items() if key != "launch_recovery"}
    if sha256_json(unsigned) != sha256_json(original_request) or "launch_recovery" in original_request:
        raise ValueError("launch recovery changes the original scientific request")
    for key in ("protocol_sha256", "evaluation_index", "candidate_structure_sha256", "search_checkpoint_sha256"):
        if review.get(key) != original_request.get(key):
            raise ValueError("launch recovery failure review belongs to another candidate or round")


def _validate_failed_recovery_submission(original: Path, snapshot: Path, paths: dict, review: dict) -> tuple[dict, str]:
    from scripts.neb_agent.submission import InputBundle
    from scripts.slurm_force_label import validate_stored_slurm_force_label

    previous = load_mz73_static_backend(_FAILED_LEAF, config_path=snapshot)
    remote = previous["remote_root"] + "/" + _FAILED_LEAF
    native = validate_stored_slurm_force_label(
        load_json_object(paths["terminal"]), job_id="13901", remote_dir=remote,
        workdir_name=_FAILED_LEAF, config_path=snapshot, require_completed=False,
    )
    if native["job_state"] != "FAILED" or native["exit_code"] != "131:0":
        raise ValueError("launch recovery requires the exact native prelaunch failure")
    receipt = load_json_object(paths["submission"])
    preflight = load_json_object(original / "submission_preflight.json")
    bundle = InputBundle.from_preflight(preflight)
    bundle.verify(original)
    if (receipt.get("job_id") != "13901" or receipt.get("status") != "SUBMITTED"
            or receipt.get("scheduler") != "Slurm" or receipt.get("server_alias") != BACKEND_ID
            or receipt.get("remote_dir") != remote or receipt.get("bundle_sha256") != bundle.bundle_sha256
            or preflight.get("backend_config_sha256") != sha256_file(snapshot)
            or review.get("failed_execution") != {"job_id": "13901", "bundle_sha256": bundle.bundle_sha256,
                                                  "gate_sha256": receipt.get("gate_decision_sha256")}):
        raise ValueError("launch recovery does not bind the original submission and input bundle")
    producer = load_json_object(paths["producer"])
    log = paths["stdout"].read_text(encoding="utf-8")
    if (producer.get("job_id") != "13901" or producer.get("exit_code") != 131
            or "hwloc_set_cpubind" not in log or "without launching the target application" not in log):
        raise ValueError("launch recovery lacks its exact MPI prelaunch failure")
    return receipt, bundle.bundle_sha256


def _validate_recovery_probe(workdir: Path, backend: dict, paths: dict) -> None:
    from scripts.slurm_force_label import parse_scontrol_job

    probe_root = workdir.parent.parent / "mpi_binding_probe_13901"
    if paths["MPI_probe"] != (probe_root / "probe.json").resolve() or paths["MPI_probe_terminal"] != (probe_root / "scontrol.raw.txt").resolve():
        raise ValueError("launch recovery probe sources belong to another experiment")
    probe_native = parse_scontrol_job(paths["MPI_probe_terminal"].read_text(encoding="utf-8"), "13902")
    probe_remote = str(PurePosixPath(backend["remote_root"]).parent / "mpi_binding_probe_13901")
    if (probe_native["job_state"] != "COMPLETED" or probe_native["exit_code"] != "0:0"
            or probe_native["remote_dir"] not in {probe_remote, canonical_remote_path(backend, probe_remote)}
            or probe_native["command"] not in {probe_remote + "/probe.sh", canonical_remote_path(backend, probe_remote) + "/probe.sh"}
            or load_json_object(paths["MPI_probe"]).get("cuda") is not True):
        raise ValueError("launch recovery requires the reviewed native successful CUDA/MPI probe")


def _load_reviewed_contract(contract_path: Path, backend: dict[str, Any]) -> dict[str, Any]:
    from scripts.ts_strategy_engine.contract import _normalize_contract_payload

    contract = load_json_object(contract_path)
    validate_finite_tree(contract, "reviewed case contract")
    unsigned = dict(contract)
    unsigned.pop("contract_sha256", None)
    observed = {"contract_sha256": sha256_json(unsigned),
                "compatibility_sha256": sha256_json(contract["compatibility"]),
                "atom_map_sha256": sha256_json(contract["atom_map"])}
    if any(contract.get(key) != digest or backend["reviewed_contract"][key] != digest for key, digest in observed.items()):
        raise ValueError("reviewed case contract hash does not match its exact experiment caps")
    # This release's older normalizer drops newer compatibility fields and
    # lowercases descriptions. Reuse its common-field validation, never its
    # replacement payload or hashes; the approved source dictionary stays intact.
    common = _normalize_contract_payload(contract)
    ignored = {"compatibility", "compatibility_sha256", "contract_sha256"}
    if any(contract.get(key) != value for key, value in common.items() if key not in ignored):
        raise ValueError("reviewed case contract common fields are not canonical")
    compatibility = contract["compatibility"]
    finite_array(compatibility["cell_angstrom"], "reviewed unit cell", shape=(3, 3))
    for key in ("clean_slab_sha256", "potcar_bundle_sha256"):
        if key in compatibility:
            require_sha256(compatibility[key], label=key)
    for key in ("ediff_ev", "force_threshold_ev_per_A"):
        if key in compatibility:
            finite_number(compatibility[key], key, positive=True)
    if "slab_layers" in compatibility:
        integer_number(compatibility["slab_layers"], "slab layers", positive=True)
    return contract


def load_reviewed_case_contract(
    contract_path: Path, *, workdir_name: str, config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Preserve this exact reviewed CH+CO contract across the older release schema.

    This is a hash-capped experiment bridge, not a new contract normalizer or
    permission to import another method. No input bytes or identity are rewritten.
    """
    return _load_reviewed_contract(Path(contract_path), load_mz73_static_backend(workdir_name, config_path=config_path))


def _bound_search_inputs(
    initial_structure_path: Path, search_request_path: Path, request_sha256: str, contract_path: Path, backend: dict,
    *, continuation: bool = False, candidate_path: Path | None = None, protocol_sha256: str | None = None,
):

    if sha256_file(search_request_path) != require_sha256(request_sha256, label="ML search request"):
        raise ValueError("ML search request raw source hash mismatch")
    # Read the bound JSON directly: YAML would turn JSON's 1e-05 into text.
    request, contract = load_json_object(search_request_path), _load_reviewed_contract(contract_path, backend)
    dependencies, binding = [], None
    from scripts.neb_agent.paper_candidate_source import BINDING_KIND, resolve_continuation_source

    if continuation:
        if request.get("document_kind") != BINDING_KIND:
            raise ValueError("the next scientific round requires its explicit continuation source binding")
        resolved = resolve_continuation_source(
            search_request_path, binding_sha256=request_sha256, candidate_path=candidate_path,
            initial_structure_path=initial_structure_path, expected_protocol_sha256=protocol_sha256, contract=contract,
        )
        request, dependencies, binding = resolved["effective_request"], resolved["dependency_paths"], resolved["source_binding"]
    elif request.get("document_kind") == BINDING_KIND:
        raise ValueError("a continuation source binding cannot replace the original first-round request")
    if sha256_file(initial_structure_path) != request.get("initial", {}).get("sha256"):
        raise ValueError("original IS raw source hash mismatch")
    for key in ("contract_sha256", "compatibility_sha256", "atom_map_sha256"):
        if request.get("reaction", {}).get(key) != contract.get(key):
            raise ValueError("ML request and reaction contract identity mismatch")
    guard_ref = request.get("geometry_guard_source", {})
    source = Path(guard_ref["path"])
    if sha256_file(source) != guard_ref.get("sha256"):
        raise ValueError("geometry guard raw source hash mismatch")
    guard_request = load_json_object(source)
    guards = guard_request["geometry_guards"]
    geometry = request["geometry"]
    if finite_number(geometry["minimum_pair_distance_A"], "minimum contact", positive=True) != guards["minimum_pair_distance_A"]:
        raise ValueError("minimum contact differs from the reviewed guard source")
    expected = [{"name": row["name"], "atoms": row["atoms_zero_based"],
                 "minimum_A": row.get("hard_minimum_A", row["minimum_A"]),
                 "maximum_A": row.get("hard_maximum_A", row["maximum_A"]),
                 "soft_minimum_A": row["minimum_A"], "soft_maximum_A": row["maximum_A"]}
                for row in guards["preserved_bonds"]]
    if geometry["preserved_bonds"] != expected:
        raise ValueError("preserved-bond bounds differ from their reviewed guard source")
    return request, contract, [source, *dependencies], binding


def _static_reference_identity(initial_structure_path: Path, candidate: Path, request: dict, contract: dict, candidate_sha: str):
    from ase.io import read
    from scripts.aqcat25_ml_neb import _fixed_indices
    from scripts.ml_candidate_source import _structure_row

    reference = read(initial_structure_path, format="vasp")
    if len(reference) != len(contract["atom_map"]) or reference.get_chemical_symbols() != contract.get("atom_symbols"):
        raise ValueError("original IS atom count or species/order differs from the reaction contract")
    fixed = contract["compatibility"]["fixed_atom_indices_zero_based"]
    if request["fixed_indices_zero_based"] != fixed or _fixed_indices(reference) != fixed:
        raise ValueError("original IS or ML request fixed mask differs from the reaction contract")
    contract_reference = reference.copy()
    contract_reference.set_cell(contract["compatibility"]["cell_angstrom"])
    _structure_row(initial_structure_path, request["initial"]["sha256"], "original_IS", None,
                   "reference", "static_candidate_geometry", contract_reference)
    atoms, _ = _structure_row(candidate, candidate_sha, "static_candidate", None,
                              "DFT_force_label_candidate", "static_candidate_geometry", reference)
    expected_changes = [[*pair, "form"] for pair in contract["formed_bonds"]] + [
        [*pair, "break"] for pair in contract["broken_bonds"]]
    if request["reaction"]["bonds"] != expected_changes:
        raise ValueError("ML candidate reaction bonds differ from the reviewed contract")
    retained = {tuple(sorted(row["atoms"])) for row in request["geometry"]["preserved_bonds"]}
    monitored = request["reaction"]["monitor_pairs"]
    if retained != {tuple(sorted(monitored[key])) for key in ("CH", "CO")}:
        raise ValueError("retained-bond guards do not match the reviewed CH/CO atom pairs")
    symbols = atoms.get_chemical_symbols()
    for key, expected_symbols in (("CH", {"C", "H"}), ("CO", {"C", "O"})):
        if {symbols[index] for index in monitored[key]} != expected_symbols:
            raise ValueError("retained-bond species do not match the CH/CO reaction identity")
    return atoms, fixed


def _static_bond_evidence(atoms, geometry: dict[str, Any]) -> tuple[list[dict], list[str], list[str]]:
    rows, errors, warnings = [], [], []
    for rule in geometry["preserved_bonds"]:
        pair = rule["atoms"]
        if len(pair) != 2 or any(type(index) is not int or not 0 <= index < len(atoms) for index in pair) or pair[0] == pair[1]:
            raise ValueError("invalid retained-bond atom indices")
        low, high, soft_low, soft_high = [finite_number(rule[key], key, positive=True)
                                       for key in ("minimum_A", "maximum_A", "soft_minimum_A", "soft_maximum_A")]
        if not low <= soft_low <= soft_high <= high:
            raise ValueError("retained-bond hard/soft windows must be nested")
        distance = float(atoms.get_distance(*pair, mic=True))
        passed = low <= distance <= high
        if not passed:
            errors.append("retained_bond:" + rule["name"])
        elif not soft_low <= distance <= soft_high:
            warnings.append("retained_bond_soft_window:" + rule["name"])
        rows.append({"name": rule["name"], "atoms_zero_based": pair, "distance_A": distance,
                     "hard_window_A": [low, high], "soft_window_A": [soft_low, soft_high], "hard_passed": passed})
    return rows, errors, warnings


def diagnose_static_candidate_geometry(
    workdir: Path, *, initial_structure_path: Path, search_request_path: Path, search_request_sha256: str,
    contract_path: Path, review_path: Path, geometry_evidence_path: Path, review_image_path: Path,
) -> dict[str, Any]:
    """Diagnose one actual structure using frozen IS/contract and reviewed guards.

    This checks a starting structure for a static force label. It establishes
    neither a reaction path, a saddle, a force-converged TS, nor execution rights.
    """
    from scripts import aqcat25_ml_neb, ml_candidate_source
    from scripts.aqcat25_ml_neb import _minimum_pair_distance
    from scripts.ts_strategy_engine import contract as contract_owner

    workdir = Path(workdir).resolve(strict=True)
    backend = load_mz73_static_backend(workdir.name)
    paths = {key: Path(value).resolve(strict=True) for key, value in {
        "initial_structure_path": initial_structure_path, "search_request_path": search_request_path,
        "contract_path": contract_path, "review_path": review_path,
        "geometry_evidence_path": geometry_evidence_path, "review_image_path": review_image_path,
    }.items()}
    candidate = workdir / "POSCAR"
    paper = validate_paper_dft_request(workdir, backend=backend)
    from scripts.neb_agent.mz73_continuation import NAMES
    from scripts.neb_agent.mz73_timebudget import NEXT_LEAF

    request, contract, search_sources, continuation_binding = _bound_search_inputs(
        paths["initial_structure_path"], paths["search_request_path"], search_request_sha256, paths["contract_path"], backend,
        continuation=workdir.name == NEXT_LEAF or workdir.name in NAMES,
        candidate_path=candidate, protocol_sha256=paper["protocol_sha256"],
    )
    if any(paper[key] != contract[key] for key in ("contract_sha256", "compatibility_sha256")):
        raise ValueError("paper DFT request and static candidate contract differ")
    if paper["search_checkpoint_sha256"] != request["checkpoint"]["sha256"]:
        raise ValueError("paper candidate uses another ML checkpoint")
    review = load_json_object(paths["review_path"])
    if (review.get("decision") != "accepted_for_exact_structure_DFT_force_diagnosis_only"
            or not review.get("reviewer") or review.get("not_transition_state_acceptance") is not True
            or review.get("candidate_structure_sha256") != paper["candidate_structure_sha256"]
            or review.get("geometry_evidence_sha256") != sha256_file(paths["geometry_evidence_path"])
            or review.get("image_sha256") != sha256_file(paths["review_image_path"])):
        raise ValueError("actual candidate work review or its geometry/image source binding is missing")
    atoms, fixed = _static_reference_identity(paths["initial_structure_path"], candidate, request, contract,
                                             paper["candidate_structure_sha256"])
    bonds, errors, warnings = _static_bond_evidence(atoms, request["geometry"])
    minimum = _minimum_pair_distance(atoms)
    threshold = request["geometry"]["minimum_pair_distance_A"]
    if minimum < threshold:
        errors.append("minimum_pair_distance")
    return {
        "schema_version": 1, "document_kind": STATIC_GEOMETRY_KIND, "producer": STATIC_PRODUCER,
        "diagnosis_inputs": {"workdir": str(workdir), **{key: str(value) for key, value in paths.items()},
                             "search_request_sha256": search_request_sha256},
        **({"continuation_source_binding": continuation_binding} if continuation_binding else {}),
        "source_files": source_file_manifest([candidate, workdir / PAPER_REQUEST, *paths.values(), *search_sources,
                                             Path(__file__), Path(aqcat25_ml_neb.__file__),
                                             Path(ml_candidate_source.__file__), Path(contract_owner.__file__)]),
        "status": "FAIL" if errors else "PASS", "hard_errors": errors, "warnings": warnings,
        "candidate_structure_sha256": paper["candidate_structure_sha256"],
        "contract_sha256": contract["contract_sha256"], "compatibility_sha256": contract["compatibility_sha256"],
        "atom_map_sha256": contract["atom_map_sha256"], "atom_count": len(atoms),
        "atom_symbols": atoms.get_chemical_symbols(), "fixed_atom_indices_zero_based": fixed,
        "minimum_pair_distance_A": minimum, "minimum_allowed_pair_distance_A": threshold,
        "preserved_bonds": bonds, "result_class": "geometry_checked_static_starting_candidate_only",
        "not_transition_state_acceptance": True, "not_path_or_MEP_validation": True, "submission_allowed": False,
    }


def analyze_static_candidate_outputs(workdir: Path) -> dict[str, Any]:
    """Report actual local output presence, without inventing NEB image states."""
    workdir = Path(workdir).resolve(strict=True)
    load_mz73_static_backend(workdir.name)
    paper = validate_paper_dft_request(workdir)
    outputs = [workdir / name for name in ("OUTCAR", "OSZICAR", "vasp.out") if (workdir / name).is_file()]
    return {
        "schema_version": 1, "document_kind": STATIC_ANALYSIS_KIND, "producer": STATIC_PRODUCER,
        "analysis_inputs": {"workdir": str(workdir)},
        "source_files": source_file_manifest([Path(__file__), workdir / "POSCAR", workdir / "INCAR",
                                             workdir / PAPER_REQUEST, *outputs]),
        "status": "OUTPUT_PRESENT" if outputs else "NO_OUTPUT", "outputs_present": [path.name for path in outputs],
        "candidate_structure_sha256": paper["candidate_structure_sha256"],
        "contract_sha256": paper["contract_sha256"], "compatibility_sha256": paper["compatibility_sha256"],
        "result_class": "static_output_presence_only", "scientifically_validated_ts": False, "submission_allowed": False,
    }


def validate_static_evidence(artifact: dict[str, Any], preflight: dict[str, Any], *, name: str) -> bool:
    """Recompute this owner evidence only for the scoped experimental backend."""
    if (preflight.get("experimental_backend") != BACKEND_ID or preflight.get("kind") != "diagnostic_static"
            or name not in {"geometry", "analysis"}):
        return False
    expected_kind = STATIC_GEOMETRY_KIND if name == "geometry" else STATIC_ANALYSIS_KIND
    if (artifact.get("document_kind") != expected_kind or artifact.get("producer") != STATIC_PRODUCER
            or not source_file_manifest_valid(artifact)):
        return False
    try:
        from scripts.ts_strategy_engine.execution_evidence import workdir_identity

        inputs = artifact["diagnosis_inputs" if name == "geometry" else "analysis_inputs"]
        workdir = Path(inputs["workdir"])
        if preflight.get("local_workdir_identity") != workdir_identity(workdir):
            return False
        paper = validate_paper_dft_request(workdir)
        if (paper != preflight.get("paper_dft_request")
                or paper["candidate_structure_sha256"] != preflight["files"]["POSCAR"]
                or paper["request_sha256"] != preflight["files"][PAPER_REQUEST]):
            return False
        regenerated = (diagnose_static_candidate_geometry(**inputs) if name == "geometry"
                       else analyze_static_candidate_outputs(workdir))
        if name == "geometry" and (regenerated["status"] != "PASS" or regenerated["hard_errors"] != []):
            return False
        if name == "analysis" and (regenerated["status"] != "NO_OUTPUT" or regenerated["outputs_present"] != []):
            return False
        return sha256_json(regenerated) == sha256_json(artifact)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
