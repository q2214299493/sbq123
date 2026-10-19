"""One frozen-checkpoint validation; no training, VASP, or model promotion."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import signal
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from ase.io import read, write
from ase.optimize import LBFGS

FORCE_ONLY_KINDS = {
    "adsorption_exact_trajectory_force_comparison",
    "adsorption_exact_static_force_comparison",
}

if __package__:
    from .validation_helpers import cuda_binding, force_metrics, gpu_available
else:
    from validation_helpers import cuda_binding, force_metrics, gpu_available


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            value.update(block)
    return value.hexdigest()


def save(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
        handle.write("\n")


def local_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("artifact escapes package")
    return path


def load_atoms(path: Path):
    atoms = read(path, format="vasp")
    fixed = sorted(int(i) for constraint in atoms.constraints for i in constraint.get_indices())
    if atoms.get_chemical_symbols()[:45] != ["Fe"] * 45 or fixed != list(range(18)):
        raise ValueError("Fe45/order/fixed-mask mismatch")
    if not np.isfinite(atoms.positions).all() or not np.isfinite(atoms.cell).all():
        raise ValueError("nonfinite geometry")
    atoms.set_tags(np.zeros(len(atoms), dtype=int))
    atoms.info.update(is_spin_off=False, is_low_fi=False)
    return atoms


def validate_force_only_scope(request: dict, exception: dict) -> None:
    if request["limits"] or request["geometry_cases"] or request.get("sample_role") != "screened_untrained_diagnostic_not_independent_heldout":
        raise ValueError("force-only comparison cannot optimize geometry or claim independent heldout")
    rows = request["samples"]
    if len(rows) != exception["sample_count"] or len({r["sample_id"] for r in rows}) != exception["sample_count"]:
        raise ValueError("diagnostic sample scope/count changed")
    if sorted({r["source_name"] for r in rows}) != exception["source_names"]:
        raise ValueError("diagnostic source scope changed")


def validate_scope(request: dict, authorization: dict, request_sha: str, exception: dict) -> None:
    force_only = request.get("document_kind") in FORCE_ONLY_KINDS
    action = "RUN_GPU_ADSORPTION_EXACT_FORCES" if force_only else "RUN_GPU_ADSORPTION_FROZEN_VALIDATION"
    if (authorization.get("request_sha256") != request_sha or authorization.get("user_authorized") is not True
            or authorization.get("action") != action):
        raise ValueError("missing or stale explicit user authorization")
    for key in ("gpu_index", "gpu_uuid", "max_wall_seconds", "remote_root"):
        if request[key] != exception[key]:
            raise ValueError("backend scope mismatch: " + key)
    if request["execution_mode"] != "direct_no_scheduler" or request["scheduler_job_id"] is not None:
        raise ValueError("direct execution must not emulate a scheduler")
    if set(request["models"]) != {"baseline", "candidate"}:
        raise ValueError("unexpected model set")
    for model in ("baseline", "candidate"):
        if request["models"][model]["sha256"] != exception[model + "_checkpoint_sha256"]:
            raise ValueError("unauthorized checkpoint")
    if force_only:
        validate_force_only_scope(request, exception)
    elif request["limits"] != {"seed_max_steps": exception["seed_max_steps"],
                             "minimum_drift_max_steps": exception["minimum_drift_max_steps"],
                             "fmax_eV_per_A": exception["fmax_eV_per_A"]}:
        raise ValueError("optimizer budget changed")
    if not force_only and (len(request["heldout"]) != exception["heldout_count"] or len({r["sample_id"] for r in request["heldout"]}) != exception["heldout_count"]):
        raise ValueError("heldout scope/count changed")
    if not force_only and [case["name"] for case in request["geometry_cases"]] != exception["geometry_case_names"]:
        raise ValueError("geometry cases changed")
    if authorization["user_request"] != exception["authorizing_user_request"]:
        raise ValueError("user scope changed")


def verify_labels(root: Path, request: dict) -> None:
    if digest(local_path(root, request["source_manifest_path"])) != request["source_manifest_sha256"]:
        raise ValueError("source training manifest changed")
    source = json.loads(local_path(root, request["source_manifest_path"]).read_bytes())
    force_only = request.get("document_kind") in FORCE_ONLY_KINDS
    rows = request["samples"] if force_only else request["heldout"]
    originals = source["samples"] if force_only else source["splits"]["heldout"]
    expected = {row["sample_id"]: row for row in originals}
    if len(expected) != len(originals) or {row["sample_id"] for row in rows} != set(expected):
        raise ValueError("frozen heldout membership changed")
    for row in rows:
        original = expected[row["sample_id"]]
        keys = ["structure_sha256", "forces_eV_per_A", "symbols", "fixed_atom_indices_0based", "source_OUTCAR_sha256"]
        if request.get("document_kind") == "adsorption_exact_static_force_comparison":
            keys += ["source_name", "source_job_id", "ionic_step", "source_force_table_sha256", "source_POSCAR_sha256", "source_INCAR_sha256"]
        else:
            keys += ["source_name", "source_job_id", "ionic_step", "source_total_steps", "source_force_table_sha256", "source_XDATCAR_sha256"] if force_only else ["calculation_group"]
        for key in keys:
            if row[key] != original[key]:
                raise ValueError("frozen heldout label changed: " + key)
        path = local_path(root, row["structure_path"])
        if digest(path) != row["structure_sha256"]:
            raise ValueError("structure bytes do not match exact label")
        atoms = load_atoms(path)
        forces = np.asarray(row["forces_eV_per_A"], dtype=float)
        if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
            raise ValueError("incomplete/nonfinite reference forces")
        if atoms.get_chemical_symbols() != row["symbols"] or row["fixed_atom_indices_0based"] != list(range(18)):
            raise ValueError("reference atom order or mask changed")
        if not row["electronic_converged"] or not row["geometry_review_pass"]:
            raise ValueError("unreviewed heldout reference")
    for case in request["geometry_cases"]:
        first, final = [load_atoms(local_path(root, case[key])) for key in ("seed_path", "reference_path")]
        if first.get_chemical_symbols() != final.get_chemical_symbols() or not np.allclose(first.cell, final.cell):
            raise ValueError("geometry reference incompatible")


def verify(path: Path, authorization_path: Path, remote: bool = False) -> dict:
    root = path.parent.resolve()
    request = json.loads(path.read_bytes())
    if request.get("document_kind") not in {"adsorption_frozen_checkpoint_gpu_validation", *FORCE_ONLY_KINDS}:
        raise ValueError("not a frozen adsorption validation")
    authorization = json.loads(authorization_path.read_bytes())
    policy = local_path(root, request["policy"]["path"])
    if digest(policy) != request["policy"]["sha256"]:
        raise ValueError("backend policy changed")
    exception = yaml.safe_load(policy.read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["direct_execution_exceptions"][request["exception_id"]]
    validate_scope(request, authorization, digest(path), exception)
    for artifact in request["artifacts"]:
        if digest(local_path(root, artifact["path"])) != artifact["sha256"]:
            raise ValueError("artifact changed: " + artifact["path"])
    verify_labels(root, request)
    if remote:
        if socket.gethostname() != "MZ73" or root != Path(request["remote_root"]).resolve():
            raise ValueError("wrong execution host/root")
        boundary = Path("/home/sbq/sbq").resolve()
        if str(boundary) != exception["canonical_remote_boundary"] or not root.is_relative_to(boundary):
            raise ValueError("remote write boundary changed")
        for model in request["models"].values():
            if digest(Path(model["path"])) != model["sha256"]:
                raise ValueError("checkpoint bytes changed")
    return request


def require_safe_step(atoms, deadline: float) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError("validation walltime exhausted")
    forces = atoms.get_forces(apply_constraint=False)
    if not np.isfinite(forces).all() or not np.isfinite(atoms.positions).all():
        raise FloatingPointError("nonfinite geometry/forces")
    copy = atoms.copy()
    copy.pbc = [True, True, False]
    distances = copy.get_all_distances(mic=True)
    np.fill_diagonal(distances, np.inf)
    if distances.min() < .35 or distances[:45, 45:].min() < .80:
        raise ValueError("verified emergency atom overlap")


def relax_case(root: Path, output: Path, case: dict, origin: str, calc, limits: dict, deadline: float) -> dict:
    directory = output / case["name"] / origin
    directory.mkdir(parents=True, exist_ok=False)
    start = case["seed_path"] if origin == "seed" else case["reference_path"]
    atoms = load_atoms(local_path(root, start))
    initial_fixed = atoms.positions[:18].copy()
    atoms.calc = calc
    maximum = limits["seed_max_steps"] if origin == "seed" else limits["minimum_drift_max_steps"]
    optimizer = LBFGS(atoms, logfile=str(directory / "optimizer.log"), trajectory=str(directory / "optimization.traj"))
    optimizer.attach(lambda: require_safe_step(atoms, deadline), interval=1)
    started = time.monotonic()
    error, converged = None, False
    try:
        converged = bool(optimizer.run(fmax=limits["fmax_eV_per_A"], steps=maximum))
    except TimeoutError:
        raise
    except Exception as exc:
        error = type(exc).__name__ + ": " + str(exc)
    if not np.array_equal(atoms.positions[:18], initial_fixed):
        raise ValueError("fixed atoms moved")
    if np.isfinite(atoms.positions).all():
        write(directory / "POSCAR", atoms, format="vasp", direct=True, vasp5=True)
    result = {"name": case["name"], "origin": origin, "source_structure_sha256": digest(root / start),
              "status": "ERROR_PRESERVED" if error else "ML_CONVERGED" if converged else "STEP_LIMIT_NOT_CONVERGED",
              "optimizer_steps": int(optimizer.nsteps), "converged": converged, "error": error,
              "elapsed_seconds": time.monotonic() - started, "max_steps": maximum,
              "scientific_acceptance": False}
    if error is None:
        result["ML_movable_fmax_eV_A"] = float(np.linalg.norm(atoms.get_forces()[18:], axis=1).max())
    save(directory / "case_record.json", result)
    return result


def predict_heldout(root: Path, rows: list, calc, deadline: float) -> list:
    result = []
    for row in rows:
        if time.monotonic() > deadline:
            raise TimeoutError("validation walltime exhausted")
        atoms = load_atoms(local_path(root, row["structure_path"]))
        atoms.calc = calc
        predicted = atoms.get_forces(apply_constraint=False)
        result.append({"sample_id": row["sample_id"], "structure_sha256": row["structure_sha256"],
            "predicted_forces_eV_per_A": predicted.tolist(),
            "metrics": force_metrics(row["forces_eV_per_A"], predicted, row["symbols"], row["fixed_atom_indices_0based"])})
        print("prediction " + row["sample_id"], flush=True)
    return result


def run(path: Path, authorization: Path) -> None:
    request = verify(path, authorization, remote=True)
    root, output = path.parent.resolve(), path.parent / "output"
    output.mkdir(exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    code, error = 1, None
    try:
        gpu_available(request)
        if os.environ.get("CUDA_VISIBLE_DEVICES") != request["gpu_uuid"]:
            raise ValueError("wrong physical CUDA binding")
        import torch
        from fairchem.core.common.relaxation.ase_utils import patched_calc
        from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401

        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("one CUDA device required; no CPU fallback")
        torch.set_num_threads(4)
        torch.manual_seed(42)
        deadline = time.monotonic() + request["max_wall_seconds"]
        for name, model in request["models"].items():
            print("loading " + name, flush=True)
            calc = patched_calc(checkpoint_path=model["path"], is_spin_off=False, is_low_fi=False, cpu=False)
            binding = cuda_binding(calc)
            save(output / (name + "_device.json"), binding)
            force_only = request["document_kind"] in FORCE_ONLY_KINDS
            predictions = predict_heldout(root, request["samples"] if force_only else request["heldout"], calc, deadline)
            suffix = "_forces.json" if force_only else "_heldout.json"
            save(output / (name + suffix), {"checkpoint_sha256": model["sha256"], "samples": predictions})
            cases = []
            for case in request["geometry_cases"]:
                for origin in ("seed", "minimum"):
                    cases.append(relax_case(root, output / name, case, origin, calc, request["limits"], deadline))
                    print(name + " geometry " + case["name"] + " " + origin, flush=True)
            if not force_only:
                save(output / (name + "_geometry.json"), {"cases": cases})
            del calc
            gc.collect()
            torch.cuda.empty_cache()
        code = 0
    except Exception as exc:
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        save(output / "producer_exit_record.json", {"run_id": request["run_id"], "exit_code": code,
            "request_sha256": digest(path), "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
            "error": error, "scheduler_job_id": None, "evidence_class": "producer_process_only_not_scheduler_state",
            "training_performed": False, "model_promoted": False, "vasp_submitted": False})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "preflight", "run"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "run":
        def stop(signum, frame):
            raise TimeoutError("termination signal " + str(signum))
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        run(args.request, args.authorization)
    else:
        request = verify(args.request, args.authorization, remote=args.action == "preflight")
        if args.action == "preflight":
            gpu_available(request)
            from fairchem.core.common.relaxation.ase_utils import patched_calc  # noqa: F401
            from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
        print(json.dumps({"status": "PREFLIGHT_PASS", "sample_count": len(request.get("samples", request.get("heldout", []))),
                          "geometry_cases": len(request["geometry_cases"]), "model_executed": False}))


if __name__ == "__main__":
    main()
