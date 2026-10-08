"""Freeze existing first/final DFT labels; never run models or submit jobs."""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from scripts.artifact_io import sha256_file, write_json
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import final_scf_state, read_incar_values

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
DEST = BASE / "c2_force_diagnostic_v1"
NAMES = ["01_cfg2", "01_cfg1", "02_cfg2", "04_cfg0", "05_cfg0"]
CHECKPOINT = "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50"
RUNNER = Path("C:/Users/86177/Desktop/机器学习/aqcat25_ts_pilot/evaluate_fe45_calibration.py")

REMOTE_READER = r"""
import base64, hashlib, json, re, sys
from pathlib import Path
root = Path('~/sbq/Fe110/adsorption/fe110_five_c2_20261006').expanduser()
def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576), b''):h.update(b)
    return h.hexdigest()
for name in NAMES:
    print('collecting '+name, file=sys.stderr, flush=True)
    p = root/name; out = p/'OUTCAR'; before = out.stat()
    with out.open('rb') as f:
        head = f.read(4000000); f.seek(max(0,before.st_size-4000000)); tail = f.read(4000000)
    frames = []
    for stage,data,offset,choose in [('initial',head,0,0),('final',tail,max(0,before.st_size-4000000),-1)]:
        starts = list(re.finditer(rb'TOTAL-FORCE \(eV/Angst\)',data))
        if not starts:raise ValueError('No force table within bounded read: '+name)
        start = starts[choose].start(); body = data[start:]; lines = body.splitlines(keepends=True)
        rows=[]; token_rows=[]; used=0
        for line in lines:
            used += len(line); fields=line.split()
            if len(fields)==6:
                try:row=[float(v) for v in fields]
                except ValueError:continue
                rows.append(row); token_rows.append([v.decode() for v in fields[:3]])
            elif rows:break
        if len(rows) not in (48,49):raise ValueError('Incomplete force table '+name)
        prefix=data[:start].decode(errors='replace')
        iterations=re.findall(r'Iteration\s+(\d+)\s*\(\s*(\d+)\s*\)',prefix)
        if not iterations:raise ValueError('Missing electronic cycle before force block')
        ionic,electronic=map(int,iterations[-1])
        marker='aborting loop because EDIFF is reached' in prefix[prefix.rfind('Iteration'):]
        frames.append({'stage':stage,'positions_A':[r[:3] for r in rows],
            'position_tokens':token_rows,'forces_eV_per_A':[r[3:] for r in rows],
            'ionic_step':ionic,'electronic_iteration':electronic,'EDIFF_marker_before_force':marker,
            'source_byte_range':[offset+start,offset+start+used],
            'force_table_base64':base64.b64encode(body[:used]).decode()})
    files={n:base64.b64encode((p/n).read_bytes()).decode() for n in ('POSCAR','CONTCAR','INCAR','KPOINTS','OSZICAR')}
    sha=digest(out);after=out.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Source changed during collection')
    print(json.dumps({'name':name,'remote_dir':str(p),'OUTCAR_sha256':sha,'OUTCAR_bytes':before.st_size,
        'OUTCAR_mtime_ns':before.st_mtime_ns,'files':files,'frames':frames,
        'required_accuracy_in_tail':b'reached required accuracy' in tail,
        'normal_footer_in_tail':b'General timing and accounting informations for this job' in tail}),flush=True)
"""


def verify_frame(atoms, frame):
    positions = np.asarray(frame["positions_A"], dtype=float)
    forces = np.asarray(frame["forces_eV_per_A"], dtype=float)
    if positions.shape != (len(atoms), 3) or forces.shape != (len(atoms), 3):
        raise ValueError("Atom/force shape mismatch")
    if not np.isfinite(positions).all() or not np.isfinite(forces).all():
        raise ValueError("Nonfinite frame")
    _, delta = find_mic(positions - atoms.positions, atoms.cell, pbc=[True, True, False])
    precision = np.array([[len(t.split(".")[-1]) for t in row] for row in frame["position_tokens"]])
    bound = np.linalg.norm(0.5 * 10.0 ** (-precision), axis=1)
    if not np.all(delta <= bound + 1e-8):
        raise ValueError("Force geometry differs from exact structure beyond OUTCAR printing precision")
    if len(atoms.constraints) != 1 or list(atoms.constraints[0].get_indices()) != list(range(18)):
        raise ValueError("Unexpected fixed mask")
    return forces


def prepare():
    if DEST.exists():
        raise FileExistsError("Preserve frozen diagnostic package; inspect before resuming")
    records = json.loads((BASE / "vasp_batch_v1/submission_summary.json").read_text())["records"]
    selected = {r["name"]: r for r in records if r["name"] in NAMES}
    query = "bjobs -a -w " + " ".join(selected[n]["job_id"] for n in NAMES)
    scheduler = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex", query], capture_output=True, check=True, timeout=30
    )
    states = {
        line.split()[0]: line.split()[2] for line in scheduler.stdout.decode().splitlines() if line.split() and line.split()[0].isdigit()
    }
    if any(states.get(selected[n]["job_id"]) != "DONE" for n in NAMES):
        raise ValueError("Only closed DONE jobs selected for immutable source labels")
    source = "NAMES=" + repr(NAMES) + "\n" + REMOTE_READER
    try:
        returned = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex", "python3 -"],
            input=source.encode(),
            capture_output=True,
            check=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        print("Remote collection timed out; progress: " + (exc.stderr or b"").decode(errors="replace"))
        raise
    if len(returned.stdout) > 2_000_000:
        raise ValueError("Unexpectedly large diagnostic payload")
    docs = [json.loads(line) for line in returned.stdout.decode().splitlines()]
    if [d["name"] for d in docs] != NAMES:
        raise ValueError("Unexpected diagnostic sample order")
    DEST.mkdir()
    (DEST / "scheduler_snapshot.txt").write_bytes(scheduler.stdout)
    (DEST / "remote_extraction.jsonl").write_bytes(returned.stdout)
    samples, bindings = [], []
    for doc in docs:
        name = doc["name"]
        folder = DEST / "sources" / name
        folder.mkdir(parents=True)
        for filename, value in doc["files"].items():
            (folder / filename).write_bytes(base64.b64decode(value, validate=True))
        for filename in ("POSCAR", "INCAR", "KPOINTS"):
            if (folder / filename).read_bytes() != (BASE / "vasp_batch_v1" / name / filename).read_bytes():
                raise ValueError("Remote input differs from submitted bytes: " + filename)
        values = read_incar_values(folder / "INCAR")
        if float(values["SIGMA"]) != 0.20 or int(values["ISMEAR"]) != 1:
            raise ValueError("Wrong occupation branch")
        osz = parse_oszicar(folder / "OSZICAR")
        if not final_scf_state(osz, values)["electronically_converged"]:
            raise ValueError("Final electronic convergence failed")
        if not doc["required_accuracy_in_tail"] or not doc["normal_footer_in_tail"]:
            raise ValueError("Final ionic/normal termination evidence missing")
        for frame in doc["frames"]:
            stage = frame["stage"]
            structure = folder / ("POSCAR" if stage == "initial" else "CONTCAR")
            atoms = read(structure, format="vasp")
            forces = verify_frame(atoms, frame)
            cycle = osz["electronic_cycles"][0 if stage == "initial" else -1]
            if cycle["ionic_step"] != frame["ionic_step"] or cycle["iteration"] != frame["electronic_iteration"]:
                raise ValueError("OSZICAR/force-frame cycle mismatch")
            if not frame["EDIFF_marker_before_force"]:
                raise ValueError("Force frame lacks EDIFF termination marker")
            sample_id = name + "_" + stage
            target = DEST / "structures" / (sample_id + ".vasp")
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(structure, target)
            table_path = folder / (stage + "_force_table.txt")
            table_path.write_bytes(base64.b64decode(frame["force_table_base64"], validate=True))
            samples.append(
                {
                    "sample_id": sample_id,
                    "family": "c_c2_o",
                    "label_stage": stage,
                    "structure_sha256": sha256_file(target),
                    "symbols": atoms.get_chemical_symbols(),
                    "fixed_atom_indices_1based": list(range(1, 19)),
                    "forces_eV_per_A": forces.tolist(),
                    "source_job_id": selected[name]["job_id"],
                    "source_OUTCAR_sha256": doc["OUTCAR_sha256"],
                    "source_potcar_sha256": selected[name]["potcar_sha256"],
                    "source_force_table_sha256": sha256_file(table_path),
                    "source_byte_range": frame["source_byte_range"],
                    "source_ionic_step": frame["ionic_step"],
                    "electronic_converged": True,
                    "ionic_converged": stage == "final",
                    "result_role": "diagnostic_force_label_not_accepted_energy",
                }
            )
        bindings.append(
            {
                "name": name,
                "job_id": selected[name]["job_id"],
                "OUTCAR_sha256": doc["OUTCAR_sha256"],
                "OUTCAR_bytes": doc["OUTCAR_bytes"],
                "files": {n: sha256_file(folder / n) for n in doc["files"]},
            }
        )
    write_json(
        DEST / "labels.json",
        {
            "calibration_id": "aqcat25_fe45_c2_diagnostic_20261008_v1",
            "source_backend": "sunboquan-codex",
            "compatibility_branch": "true_fe110_5layer_5x5x1_sigma0p20",
            "samples": samples,
        },
    )
    shutil.copyfile(RUNNER, DEST / "evaluate_fe45_calibration.py")
    write_json(
        DEST / "assessment_plan.json",
        {
            "status": "AWAITING_EXACT_CHECKPOINT_FORCE_PREDICTIONS",
            "checkpoint_sha256": CHECKPOINT,
            "samples": len(samples),
            "source_jobs": bindings,
            "labels_sha256": sha256_file(DEST / "labels.json"),
            "runner_sha256": sha256_file(DEST / "evaluate_fe45_calibration.py"),
            "metrics": ["component_MAE", "vector_RMSE", "vector_P95", "maximum_vector_error", "per_atom_vectors"],
            "groups": ["all_movable", "movable_Fe", "adsorbate", "element"],
            "fixed_atom_policy": "Retain raw DFT fixed-atom forces; exclude fixedFe0-17 from error metrics because predictor constraints zero their forces.",
            "scope": "C2 diagnostic only; initial/final pairs are correlated, not independent training/held-out sets. Not a global recalibration of aqcat25_fe45_v1.",
            "missing_coverage": "No completed CH-C-O species03 or new supplementary jobs included.",
            "threshold_policy": "Reference existing adsorption force thresholds only; do not import TS thresholds or alter global in_domain status.",
            "automatic_submission": False,
            "GPU_submitted": False,
            "finetuning_submitted": False,
            "force_errors_computed": False,
            "actual_speedup_measured": False,
        },
    )
    print(json.dumps({"structures": len(samples), "jobs": len(bindings), "status": "PREDICTIONS_MISSING", "output": str(DEST)}))


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    prepare()
