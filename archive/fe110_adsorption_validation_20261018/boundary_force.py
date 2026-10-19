"""Collect three immutable VASP statics and compare two frozen exact forces."""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from archive.fe110_adsorption_calibration_20261018.reviewed_trajectory_helpers import verify_frame
from scripts.aqcat25_calibration import parse_final_outcar
from scripts.artifact_io import sha256_file, sha256_text, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_outcar
from scripts.scheduler_evidence import query_lsf_job, validate_stored_lsf_evidence
from scripts.vasp_result_gate import final_scf_status, read_incar_values

from .force24 import aggregate, read_predictions
from .prepare import BASE, ROOT
from .prepare_06c_boundary import DEST as SOURCE
from .runtime import local_path, verify
from .validation_helpers import force_metrics

DEST = BASE / "adsorption_06c_force_comparison_20261019_v1"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/" + DEST.name
EXCEPTION = "fe110_adsorption_06c_boundary_force_20261019"
AUTH = Path(__file__).with_name("authorization_boundary_force_20261019.md")
SAMPLES = ["06C_before_003", "06C_after_004", "06C_final_057"]
FILES = ["POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "script.lsf", "CONTCAR", "OUTCAR", "OSZICAR"]


def force_frame(text: str) -> dict:
    """Extract exactly one static table with its original printed coordinates."""
    blocks = list(re.finditer(r"POSITION\s+TOTAL-FORCE \(eV/Angst\)", text))
    if len(blocks) != 1:
        raise ValueError("expected one NSW=0 force evaluation")
    rows = []
    for line in text[blocks[0].end():].splitlines()[1:]:
        tokens = line.split()
        if len(tokens) == 6:
            try:
                [float(v) for v in tokens]
            except ValueError:
                break
            rows.append(tokens)
        elif rows:
            break
    return {"positions_A": [[float(v) for v in row[:3]] for row in rows],
            "position_tokens": [row[:3] for row in rows],
            "forces_eV_per_A": [[float(v) for v in row[3:]] for row in rows],
            "source_force_table_sha256": sha256_text("\n".join(" ".join(r) for r in rows) + "\n")}


def validate_static(directory: Path) -> dict:
    atoms = read(directory / "POSCAR", format="vasp")
    values = read_incar_values(directory / "INCAR")
    if values["NSW"] != "0" or values["IBRION"] != "-1" or float(values["SIGMA"]) != .20:
        raise ValueError("not the unchanged SIGMA0.20 static branch")
    text = (directory / "OUTCAR").read_text(encoding="utf-8", errors="replace")
    frame = force_frame(text)
    forces = verify_frame(atoms, frame)
    parsed = parse_final_outcar(directory / "OUTCAR")
    scf = final_scf_status(directory / "OSZICAR", directory / "INCAR", directory / "OUTCAR")
    out = parse_outcar(directory / "OUTCAR")
    if not parsed["normal_completion"] or not scf["electronically_converged"] or out["fatal_keywords"]:
        raise ValueError("VASP normal/electronic/fatal gate failed")
    if atoms.get_chemical_symbols() != ["Fe"] * 45 + ["C", "C", "O", "H"]:
        raise ValueError("atom order/count changed")
    if not np.array_equal(forces, np.asarray(parsed["forces_eV_per_A"])):
        raise ValueError("canonical/raw force parsers disagree")
    final = read(directory / "CONTCAR", format="vasp")
    if final.get_chemical_symbols() != atoms.get_chemical_symbols() or not np.allclose(final.cell, atoms.cell, atol=1e-10, rtol=0):
        raise ValueError("CONTCAR order/cell changed")
    _, delta = find_mic(final.positions-atoms.positions, atoms.cell, atoms.pbc)
    if np.max(delta) > 1e-10 or not np.isfinite(parsed["final_toten_eV"]):
        raise ValueError("static coordinates changed or energy nonfinite")
    moments = out["local_magnetization_last_muB"]
    if len(moments) != len(atoms) or not np.isfinite(moments).all() or not out["total_magnetization_history_muB"]:
        raise ValueError("missing/nonfinite final local/total magnetic data")
    return {"symbols": atoms.get_chemical_symbols(), "fixed_atom_indices_0based": list(range(18)),
        "forces_eV_per_A": forces.tolist(), "electronic_converged": True, "normal_completion": True,
        "geometry_review_pass": True, "geometry_review_scope": "exact static diagnostic only;not stable adsorption acceptance",
        "movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()),
        "toten_eV_force_label_only": parsed["final_toten_eV"], "SCF": scf,
        "total_magnetization_muB": out["total_magnetization_history_muB"][-1],
        "local_magnetization_muB": moments, "source_force_table_sha256": frame["source_force_table_sha256"]}


def collect() -> None:
    if DEST.exists():
        raise FileExistsError("preserve/reconcile existing collection before any retry")
    batch = json.loads((SOURCE / "batch_request.json").read_bytes())
    if sha256_file(SOURCE / "batch_request.json") != "7830bd801ff8b3c2cdae07eb007a2c1eaf032b11cd437a30d103f3f44fcfe62f":
        raise ValueError("original batch changed")
    records = json.loads((SOURCE / "submission_summary.json").read_bytes())["records"]
    if [r["sample_id"] for r in records] != SAMPLES:
        raise ValueError("not the exact three authorized jobs")
    with ThreadPoolExecutor(max_workers=3) as pool:
        schedulers = list(pool.map(lambda r: query_lsf_job(r["job_id"]), records))
    for record in schedulers:
        validate_stored_lsf_evidence(record, required_status="DONE")
    code = "ROWS=" + repr(records) + "\nFILES=" + repr(FILES) + "\n" + """import json,hashlib,getpass
from pathlib import Path
assert getpass.getuser()=='nsgkn_chengdj3'
rows=[]
for row in ROWS:
 root=Path(row['remote_dir'].replace('~',str(Path.home()),1))
 files={}
 for name in FILES:
  p=root/name
  if not p.is_file() or not 0<p.stat().st_size<2000000:raise ValueError('missing/oversize '+str(p))
  files[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
 rows.append({'sample_id':row['sample_id'],'remote_root':str(root),'files':files,'POTCAR_sha256':hashlib.sha256((root/'POTCAR').read_bytes()).hexdigest()})
print(json.dumps(rows))
"""
    process = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex", "python3 -"], input=code.encode(), capture_output=True, timeout=40, check=True)
    metadata = json.loads(process.stdout)
    expected = {s["sample_id"]: s for s in batch["samples"]}
    for row in metadata:
        if row["POTCAR_sha256"] != batch["POTCAR"]["sha256"] or any(row["files"][name]["sha256"] != digest for name, digest in expected[row["sample_id"]]["input_hashes"].items()):
            raise ValueError("remote frozen input/POTCAR changed")
    DEST.mkdir(exist_ok=False)
    write_json_exclusive(DEST / "remote_source_manifest.json", {"files": metadata})
    samples = []
    for record, scheduler, meta in zip(records, schedulers, metadata, strict=True):
        name = record["sample_id"]
        directory = DEST / "vasp" / name
        directory.mkdir(parents=True, exist_ok=False)
        sources = ["sunboquan-codex:" + meta["remote_root"] + "/" + filename for filename in FILES]
        transfer = subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", *sources, str(directory)], capture_output=True, timeout=60, check=False)
        if transfer.returncode:
            raise RuntimeError("preserved partial collection;inspect before retry: " + transfer.stderr.decode(errors="replace")[-1000:])
        if any(sha256_file(directory / filename) != entry["sha256"] for filename, entry in meta["files"].items()):
            raise ValueError("copied VASP source bytes changed")
        write_json_exclusive(directory / "scheduler_evidence.json", scheduler)
        row = {"sample_id": name, "source_name": "06_C", "source_job_id": record["job_id"], "ionic_step": 1,
            "structure_path": "vasp/" + name + "/POSCAR", "structure_sha256": sha256_file(directory / "POSCAR"),
            "source_POSCAR_sha256": sha256_file(directory / "POSCAR"), "source_INCAR_sha256": sha256_file(directory / "INCAR"),
            "source_OUTCAR_sha256": sha256_file(directory / "OUTCAR"), **validate_static(directory)}
        write_json_exclusive(directory / "label_review.json", row)
        samples.append(row)
    write_json_exclusive(DEST / "dataset_review.json", {"document_kind": "reviewed_exact_static_force_diagnostics", "samples": samples,
        "original_batch_sha256": sha256_file(SOURCE / "batch_request.json"), "training_authorized": False,
        "reportable_final_energy": False, "sample_role": "screened_untrained_diagnostic_not_independent_heldout"})
    print(json.dumps({"status": "THREE_STATIC_LABELS_VERIFIED", "samples": [{"sample_id": s["sample_id"], "SCF": s["SCF"]["last_electronic_iteration"], "fmax_eV_A": s["movable_fmax_eV_A"], "magnetization_muB": s["total_magnetization_muB"]} for s in samples]}))


def prepare() -> None:
    dataset_path = DEST / "dataset_review.json"
    dataset = json.loads(dataset_path.read_bytes())
    plan = json.loads((SOURCE / "exact_prediction_plan.json").read_bytes())
    artifacts = []

    def copy(path: Path, name: str) -> str:
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(target)
        shutil.copyfile(path, target)
        artifacts.append({"path": name, "sha256": sha256_file(target)})
        return name

    samples = [{**row, "structure_path": copy(local_path(DEST, row["structure_path"]), "samples/" + row["sample_id"] + ".vasp")} for row in dataset["samples"]]
    source = copy(dataset_path, "evidence/dataset_review.json")
    policy = copy(ROOT / "configs/execution_backends.yaml", "backend_policy.yaml")
    copy(AUTH, "evidence/user_authorization.md")
    for name in ("runtime.py", "validation_helpers.py"):
        copy(Path(__file__).with_name(name), "runtime/" + name)
    request = {"document_kind": "adsorption_exact_static_force_comparison", "schema_version": 1,
        "run_id": "direct-fe110-adsorption-06c-boundary-force-20261019-v1", "remote_root": REMOTE,
        "exception_id": EXCEPTION, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "gpu_index": 1, "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da", "max_wall_seconds": 600,
        "models": plan["models"], "samples": samples, "geometry_cases": [], "limits": {},
        "sample_role": "screened_untrained_diagnostic_not_independent_heldout", "source_manifest_path": source,
        "source_manifest_sha256": sha256_file(dataset_path), "scientific_boundaries": {"training": False, "new_VASP": False,
        "default_model_change": False, "geometry_optimization": False, "independent_heldout": False, "speedup_proved": False},
        "policy": {"path": policy, "sha256": sha256_file(DEST / policy)}, "artifacts": artifacts}
    path = DEST / "validation_request.json"
    write_json_exclusive(path, request)
    write_json_exclusive(DEST / "submission_authorization.json", {"action": "RUN_GPU_ADSORPTION_EXACT_FORCES",
        "user_request": "授权运行这一个受限预测批次", "user_authorized": True, "request_sha256": sha256_file(path),
        "source_path": "evidence/user_authorization.md", "source_sha256": sha256_file(AUTH),
        "scope": "exactly3 static structures,two frozen models,no relaxation/training/VASP/promotion"})
    verify(path, DEST / "submission_authorization.json")
    with tarfile.open(DEST / "validation_bundle.tar", "x") as handle:
        for name in [a["path"] for a in artifacts] + ["validation_request.json", "submission_authorization.json"]:
            handle.add(DEST / name, arcname=name, recursive=False)
    print(json.dumps({"status": "EXACT_THREE_GPU_FORCE_PACKAGE_VERIFIED", "request_sha256": sha256_file(path), "GPU_executed": False}))


def bond_projection(atoms, forces, i: int, j: int) -> float:
    direction = atoms.get_distance(i, j, mic=True, vector=True)
    norm = np.linalg.norm(direction)
    if not np.isfinite(norm) or norm == 0:
        raise ValueError("undefined bond axis")
    return float(.5 * np.dot(np.asarray(forces)[j] - np.asarray(forces)[i], direction / norm))


def review() -> None:
    request_path = DEST / "validation_request.json"
    request = verify(request_path, DEST / "submission_authorization.json")
    returned = DEST / "returned"
    manifest = json.loads((returned / "return_manifest.json").read_bytes())
    for entry in manifest["files"]:
        if sha256_file(local_path(returned, entry["path"])) != entry["sha256"]:
            raise ValueError("returned bytes changed")
    record = json.loads((returned / "output/producer_exit_record.json").read_bytes())
    if record["exit_code"] or record["request_sha256"] != sha256_file(request_path):
        raise ValueError("failed/stale GPU result")
    predictions = {}
    for name in request["models"]:
        device = json.loads((returned / "output" / (name + "_device.json")).read_bytes())
        if not device["model_device"].startswith("cuda") or device["physical_gpu_uuid"] != request["gpu_uuid"]:
            raise ValueError("not the bound physical CUDA execution")
        predictions[name] = read_predictions(request, returned, name)
    frames, atom_rows = [], []
    for row in request["samples"]:
        reference = np.asarray(row["forces_eV_per_A"])
        atoms = read(local_path(DEST, row["structure_path"]), format="vasp")
        metrics, bonds, worst = {}, {}, {}
        for model, samples in predictions.items():
            predicted = np.asarray(samples[row["sample_id"]])
            metrics[model] = force_metrics(reference, predicted, row["symbols"], row["fixed_atom_indices_0based"])
            errors = np.linalg.norm(predicted-reference, axis=1)
            index = 18 + int(np.argmax(errors[18:]))
            worst[model] = {"index_0based": index, "symbol": row["symbols"][index], "vector_error_eV_A": float(errors[index])}
            bonds[model] = {str(i) + "-" + str(j): {"DFT_eV_A": bond_projection(atoms, reference, i, j), "ML_eV_A": bond_projection(atoms, predicted, i, j)} for i, j in ((45, 47), (46, 47), (45, 48))}
            for i, symbol in enumerate(row["symbols"]):
                rn, pn = np.linalg.norm(reference[i]), np.linalg.norm(predicted[i])
                cosine = float(np.dot(reference[i], predicted[i])/(rn*pn)) if min(rn, pn) > 1e-8 else None
                atom_rows.append([row["sample_id"], model, i, symbol, i < 18, *reference[i], *predicted[i], float(errors[i]), cosine])
        frames.append({"sample_id": row["sample_id"], "metrics": metrics, "worst_movable_atom": worst,
            "bond_virtual_stretch_force": bonds, "DFT_movable_fmax_eV_A": row["movable_fmax_eV_A"],
            "magnetization_muB": row["total_magnetization_muB"]})
    pooled = {name: aggregate(request["samples"], samples) for name, samples in predictions.items()}
    result = {"status": "EXACT_THREE_FORCE_COMPARISON_COMPLETE_NOT_PROMOTION", "request_sha256": sha256_file(request_path),
        "models": request["models"], "groups": pooled, "frames": frames, "fixed_Fe_excluded_from_metrics": list(range(18)),
        "bond_projection_definition": "0.5*(F_j-F_i).unit(r_j-r_i);virtual equal/opposite bond stretch;not acceleration or a proven reaction coordinate",
        "training_performed": False, "model_promoted": False,
        "limitations": ["three screened diagnostics are not independent heldout validation", "force agreement is not full-path or stable-basin proof", "no VASP steps/time speedup measured", "no automatic force-error training threshold introduced"]}
    write_json_exclusive(DEST / "force_comparison_review.json", result)
    with (DEST / "per_atom_force_errors.csv").open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_id", "model", "atom_index_0based", "element", "fixed_excluded", "DFT_Fx_eV_A", "DFT_Fy_eV_A", "DFT_Fz_eV_A", "ML_Fx_eV_A", "ML_Fy_eV_A", "ML_Fz_eV_A", "vector_error_eV_A", "force_direction_cosine"])
        writer.writerows(atom_rows)
    print(json.dumps({"pooled": pooled, "frames": frames}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "prepare", "review"))
    args = parser.parse_args()
    {"collect": collect, "prepare": prepare, "review": review}[args.action]()
