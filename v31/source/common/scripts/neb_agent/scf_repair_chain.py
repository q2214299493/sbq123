"""One-allocation SCF executor. No SSH, bsub, retry, or scientific registration.

Run the generated stdlib-only zipapp after canonical submission grants a
manifest-bound permit. Precheck is read-only and never invokes a model/VASP.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive, require_sha256
from scripts.neb_agent.scf_chain_evidence import collect, geometry_error, restart_files, structure
from scripts.scientific_validation import finite_number, integer_number
from scripts.ts_strategy_engine.scf_chain_gate import (
    STAGES, compare_states, decide_stage, require_runtime_permit, validate_policy,
)
from scripts.vasp_result_gate import read_incar_values

INPUTS = ("POSCAR", "KPOINTS", "POTCAR.spec", "A.INCAR", "B.INCAR", "C.INCAR", "baseline.json")
OUTPUTS = ("OUTCAR", "OSZICAR", "vasp.out", "WAVECAR", "CHGCAR", "CONTCAR")


def safe_file(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in {".", ".."}:
        raise ValueError("unsafe SCF filename")
    path = root / name
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)() or not path.is_file():
        raise ValueError("missing/nonregular SCF file: " + name)
    return path


def verify_inputs(root: Path, manifest: dict) -> None:
    for name, digest in manifest["inputs"].items():
        if sha256_file(safe_file(root, name)) != require_sha256(digest, label=name):
            raise ValueError("changed SCF input: " + name)


def precheck(root: Path) -> dict:
    manifest = load_json_object(safe_file(root, "scf_chain.json"))
    if set(manifest) != {"schema_version", "inputs", "potcar_sha256", "runtime", "policy", "stages"}:
        raise ValueError("unknown/missing SCF manifest fields")
    if manifest["schema_version"] != 1 or manifest["stages"] != list(STAGES):
        raise ValueError("only the reviewed three stages are supported")
    if set(manifest["inputs"]) != set(INPUTS):
        raise ValueError("incomplete SCF input bindings")
    verify_inputs(root, manifest)
    validate_policy(manifest["policy"])
    require_sha256(manifest["potcar_sha256"], label="POTCAR")
    runtime = manifest["runtime"]
    if set(runtime) != {"executable", "executable_sha256", "mpirun", "mpirun_sha256", "ranks", "stage_timeout_seconds"}:
        raise ValueError("incomplete runtime binding")
    for key in ("executable", "mpirun"):
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", runtime[key]) or ".." in runtime[key].split("/"):
            raise ValueError("runtime command must be a reviewed absolute path")
        require_sha256(runtime[key + "_sha256"], label=key)
    ranks = integer_number(runtime["ranks"], "MPI ranks", positive=True)
    finite_number(runtime["stage_timeout_seconds"], "stage timeout", positive=True)
    reference = structure(safe_file(root, "POSCAR"))
    _check_incars(root, ranks)
    baseline = load_json_object(safe_file(root, "baseline.json"))
    if set(baseline) != {"state", "geometry", "source_files", "review_status"} or baseline["review_status"] != "REVIEWED":
        raise ValueError("missing reviewed baseline")
    if not baseline["source_files"]:
        raise ValueError("baseline provenance is missing")
    for digest in baseline["source_files"].values():
        require_sha256(digest, label="baseline source")
    geometry_error(reference, baseline["geometry"], manifest["policy"]["geometry_A"])
    compare_states(baseline["state"], baseline["state"])
    if len(baseline["state"]["forces"]) != len(reference["positions"]):
        raise ValueError("baseline atom count mismatch")
    return manifest


def _check_incars(root: Path, ranks: int) -> None:
    incars = [read_incar_values(safe_file(root, name)) for name in ("A.INCAR", "B.INCAR", "C.INCAR")]
    changed = {"ICHARG", "ISTART"}
    common = [{k: v for k, v in inc.items() if k not in changed} for inc in incars]
    if common[0] != common[1] or common[1] != common[2]:
        raise ValueError("stages may differ only in ISTART/ICHARG")
    for inc, (start, charge) in zip(incars, ((0, 12), (0, 2), (1, 1))):
        required = {"ISTART": start, "ICHARG": charge, "NSW": 0, "IBRION": -1,
                    "ISPIN": 2, "LORBIT": 11, "LMAXMIX": 4}
        if any(float(inc.get(k, "nan")) != v for k, v in required.items()):
            raise ValueError("invalid stage/static/collinear INCAR")
        if any(k in inc for k in ("NPAR", "IMAGES", "ICHAIN", "LNONCOLLINEAR", "LSORBIT")):
            raise ValueError("unsupported competing parallel/method/spin tag")
        if any(inc.get(k, "").upper() not in {"TRUE", ".TRUE.", "T"} for k in ("LWAVE", "LCHARG")):
            raise ValueError("LWAVE/LCHARG must be enabled")
        ncore = integer_number(inc["NCORE"], "NCORE", positive=True)
        bands = integer_number(inc["NBANDS"], "NBANDS", positive=True)
        if ranks % ncore or bands % (ranks // ncore) or float(inc.get("KPAR", 1)) != 1:
            raise ValueError("incompatible ranks/NCORE/NBANDS/KPAR")
        if inc.get("ALGO", "").lower() != "normal" or "IALGO" in inc:
            raise ValueError("only reviewed ALGO=Normal is supported")
        finite_number(inc["EDIFF"], "EDIFF", positive=True)
        finite_number(inc["ENCUT"], "ENCUT", positive=True)
        integer_number(inc["NELM"], "NELM", positive=True)


def expected_runtime(root: Path, index: int) -> dict:
    incar = read_incar_values(root / ("ABC"[index] + ".INCAR"))
    keys = ("ISTART", "ICHARG", "ISPIN", "NSW", "IBRION", "NCORE", "NBANDS", "ENCUT", "NELM", "EDIFF", "LMAXMIX")
    return {key: finite_number(incar[key], key) for key in keys}


def file_hashes(directory: Path, names: tuple[str, ...]) -> dict:
    return {name: sha256_file(safe_file(directory, name)) for name in names if (directory / name).exists()}


def stage_evidence(root: Path, directory: Path, manifest: dict, index: int, code: int, previous: dict | None) -> dict:
    reference = structure(root / "POSCAR")
    expected = expected_runtime(root, index)
    evidence = collect(directory, expected, reference, manifest["policy"]["geometry_A"],
                       exit_code=code, restarted=index == 2)
    # Validate finite atom-resolved state even for non-selfconsistent A.
    compare_states(evidence["state"], evidence["state"])
    if index:
        try:
            restart_files(directory, expected, reference, manifest["policy"]["geometry_A"])
            evidence["restart_files_valid"] = True
        except (OSError, ValueError, OverflowError) as exc:
            evidence["restart_files_valid"] = False
            evidence["errors"].append(str(exc))
        baseline = load_json_object(root / "baseline.json")["state"]
        evidence["comparisons"] = {"baseline": compare_states(evidence["state"], baseline)}
        if index == 2:
            evidence["comparisons"]["restart"] = compare_states(evidence["state"], previous["state"])
    return evidence


def launch(command: list[str], directory: Path, timeout: float) -> int:
    with (directory / "vasp.out").open("xb") as log:
        process = subprocess.Popen(command, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Only this stage's process group, never the allocation or other jobs.
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            return 124


def _stage(root: Path, manifest: dict, permit: dict, identity: dict, index: int,
           command: list[str], prior: list[dict], results: list[dict]) -> tuple[dict, dict]:
    stage = STAGES[index]
    directory = root / stage
    if directory.is_symlink() or getattr(directory, "is_junction", lambda: False)():
        raise ValueError("stage directory cannot be a link")
    receipt = directory / "receipt.json"
    previous = results[-1] if results else None
    source_inputs = {"POSCAR": "POSCAR", "KPOINTS": "KPOINTS", "POTCAR": "POTCAR", "INCAR": "ABC"[index] + ".INCAR"}
    expected_inputs = {dest: sha256_file(safe_file(root, source)) for dest, source in source_inputs.items()}
    if directory.exists():
        if not receipt.is_file():
            raise RuntimeError("UNKNOWN_NEEDS_RECONCILIATION: " + stage)
        saved = load_json_object(safe_file(directory, "receipt.json"))
        if saved["outputs"] != file_hashes(directory, OUTPUTS):
            raise ValueError("completed output changed: " + stage)
        if saved["inputs"] != expected_inputs or expected_inputs != file_hashes(directory, tuple(source_inputs)):
            raise ValueError("completed input changed: " + stage)
        evidence = stage_evidence(root, directory, manifest, index, saved["exit_code"], previous)
        gate = decide_stage(stage, evidence, manifest["policy"], permit=permit,
                            manifest_sha256=identity["manifest_sha256"], prior=prior)
        if gate != saved["gate"]:
            raise ValueError("completed stage gate changed: " + stage)
        return evidence, gate
    directory.mkdir()  # Exclusive reservation; never overwrite/retry a stage.
    for dest, source in source_inputs.items():
        shutil.copyfile(safe_file(root, source), directory / dest)
    restart_sources = {}
    if index == 2:
        source = root / STAGES[1]
        saved = load_json_object(source / "receipt.json")
        for name in ("WAVECAR", "CHGCAR"):
            restart_sources[name] = saved["outputs"][name]
            if sha256_file(safe_file(source, name)) != restart_sources[name]:
                raise ValueError("validated restart source changed")
            shutil.copyfile(source / name, directory / name)
            if sha256_file(directory / name) != restart_sources[name]:
                raise ValueError("restart copy changed")
    if file_hashes(directory, tuple(source_inputs)) != expected_inputs:
        raise ValueError("stage input copy changed")
    write_json_exclusive(directory / "started.json", {
        **identity, "stage": stage, "inputs": expected_inputs,
        "restart_sources": restart_sources, "command": command,
    })
    code = launch(command, directory, manifest["runtime"]["stage_timeout_seconds"])
    try:
        evidence = stage_evidence(root, directory, manifest, index, code, previous)
    except (OSError, ValueError, KeyError, IndexError, OverflowError) as exc:
        evidence = {"exit_code": code, "errors": ["INVALID_RESULT: " + str(exc)]}
    if file_hashes(directory, tuple(source_inputs)) != expected_inputs:
        evidence.setdefault("errors", []).append("STAGE_INPUTS_CHANGED")
    gate = decide_stage(stage, evidence, manifest["policy"], permit=permit,
                        manifest_sha256=identity["manifest_sha256"], prior=prior)
    write_json_exclusive(receipt, {"gate": gate, "exit_code": code, "evidence": evidence,
                                   "inputs": expected_inputs, "outputs": file_hashes(directory, OUTPUTS)})
    return evidence, gate


def run_chain(root: Path, permit: dict, *, job_id: str, hosts: list[str]) -> dict:
    root = root.resolve(strict=True)
    manifest = precheck(root)
    digest = sha256_file(root / "scf_chain.json")
    require_runtime_permit(permit, digest)
    if not re.fullmatch(r"[1-9][0-9]*", job_id) or not hosts or any(not re.fullmatch(r"[\w.-]+", h) for h in hosts):
        raise ValueError("LSF allocation identity is missing/invalid")
    if len(hosts) != manifest["runtime"]["ranks"]:
        raise ValueError("allocated host slots do not match reviewed MPI ranks")
    if sha256_file(safe_file(root, "POTCAR")) != manifest["potcar_sha256"]:
        raise ValueError("POTCAR mismatch")
    runtime = manifest["runtime"]
    for key in ("executable", "mpirun"):
        if sha256_file(Path(runtime[key])) != runtime[key + "_sha256"]:
            raise ValueError("runtime executable changed: " + key)
    lock = root / "scf_chain.lock"
    # A stale lock is deliberately not auto-broken. Reconcile before any retry.
    with lock.open("x", encoding="ascii") as handle:
        handle.write(job_id)
    prior, results = [], []
    try:
        identity = {"job_id": job_id, "hosts": hosts, "manifest_sha256": digest, "permit": permit}
        allocation = root / "scf_allocation.json"
        if allocation.exists():
            if load_json_object(allocation) != identity:
                raise PermissionError("resume must use the same authorized allocation")
        else:
            write_json_exclusive(allocation, identity)
        nodelist = root / "scf_nodes"
        node_text = "\n".join(hosts) + "\n"
        if nodelist.exists():
            if safe_file(root, "scf_nodes").read_text() != node_text:
                raise ValueError("node list changed")
        else:
            with nodelist.open("x", encoding="ascii") as handle:
                handle.write(node_text)
        command = [runtime["mpirun"], "-np", str(runtime["ranks"]), "-machinefile", str(nodelist), runtime["executable"]]
        for index, stage in enumerate(STAGES):
            verify_inputs(root, manifest)
            if sha256_file(root / "scf_chain.json") != digest:
                raise ValueError("manifest changed during execution")
            for key in ("executable", "mpirun"):
                if sha256_file(Path(runtime[key])) != runtime[key + "_sha256"]:
                    raise ValueError("runtime changed between stages")
            evidence, gate = _stage(root, manifest, permit, identity, index, command, prior, results)
            prior.append(gate)
            results.append(evidence)
            if gate["status"] == "STOP":
                return {"status": "STOP", "stages": prior, "scientific_acceptance": False}
        return {"status": "NUMERICAL_REPAIR_VERIFIED", "stages": prior, "scientific_acceptance": False}
    finally:
        lock.unlink()  # Our own transient lock only; stage reservations remain.


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precheck", action="store_true")
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.precheck:
        precheck(args.workdir)
        print(json.dumps({"precheck": "PASS", "executed": False}))
        return 0
    permit = json.loads(base64.b64decode(os.environ["SCF_CHAIN_PERMIT"], validate=True))
    if sha256_file(Path(sys.argv[0])) != permit["runtime_sha256"]:
        raise PermissionError("runtime zipapp hash mismatch")
    target = permit["target"]["remote_dir"]
    if not target.startswith("~/sbq/") or args.workdir.resolve() != (Path.home() / target[2:]).resolve():
        raise PermissionError("runtime target differs from canonical authorization")
    result = run_chain(args.workdir, permit, job_id=os.environ["LSB_JOBID"], hosts=os.environ["LSB_HOSTS"].split())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "NUMERICAL_REPAIR_VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
