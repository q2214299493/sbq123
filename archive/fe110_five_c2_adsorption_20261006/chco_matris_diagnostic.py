"""Review existing CHCO repair and compare frozen, exact-structure model forces."""

import argparse
import base64
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from ase.io import read

from archive.fe110_five_c2_adsorption_20261006 import c2_force_gpu as gpu
from archive.fe110_five_c2_adsorption_20261006.assess_c2_force_prediction import metrics
from scripts.artifact_io import sha256_file, write_json

BASE = gpu.BASE
SOURCE = gpu.SOURCE
HERE = Path(__file__).resolve().parent
PACKAGE = BASE / "gpu_matris_force_diagnostic_v1"
EVIDENCE = BASE / "gpu_matris_force_diagnostic_submission_v1"
REVIEW = BASE / "chco_reassessment_20261010"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/fe110_c2_matris_force_diagnostic_20261010_v1"
CHECKPOINT = "/home/sbq/sbq/mlip_same_structure_benchmark_20260825/MatRIS_4M_FeCOH_compliant.pth.tar"
CHECKPOINT_SHA = "1e6a85b33db075ad1637eca7537084024a694b1340358911212d8a5c518c6601"
AQ = BASE / "gpu_force_diagnostic_submission_v1/predictions.returned.json"


def review():
    REVIEW.mkdir(exist_ok=False)
    records = []
    for package in ("vasp_batch_v1", "vasp_supplement_v1", "vasp_repair_v1"):
        for record in json.loads((BASE / package / "submission_summary.json").read_text())["records"]:
            if record["species_id"] == "03":
                records.append({k: record[k] for k in ("name", "job_id", "remote_dir", "workdir")})
    code = """import base64,json,pathlib,subprocess
records=json.loads(%r)
status=subprocess.run(['bjobs','-a']+[r['job_id'] for r in records],capture_output=True,text=True)
out={'scheduler_stdout':status.stdout,'scheduler_stderr':status.stderr,'scheduler_exit':status.returncode,'records':[]}
for r in records:
 p=pathlib.Path(r['remote_dir'].replace('~',str(pathlib.Path.home()),1))
 files={}
 for name in ('POSCAR','CONTCAR','OSZICAR'):
  f=p/name
  if f.is_file() and f.stat().st_size<=1000000: files[name]=base64.b64encode(f.read_bytes()).decode()
 out['records'].append({**r,'files':files})
print(json.dumps(out))
""" % json.dumps(records)
    remote = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex", "python3 -"],
                            input=code.encode(), capture_output=True, timeout=90)
    (REVIEW / "remote_snapshot.json").write_bytes(remote.stdout)
    (REVIEW / "ssh_stderr.txt").write_bytes(remote.stderr)
    if remote.returncode:
        raise RuntimeError("snapshot failed; inspect saved receipt")
    snapshot = json.loads(remote.stdout)
    output = []
    for record in snapshot["records"]:
        target = REVIEW / record["name"]
        target.mkdir()
        for name, value in record["files"].items():
            (target / name).write_bytes(base64.b64decode(value))
        local = Path(record["workdir"]) / "POSCAR"
        if sha256_file(target / "POSCAR") != sha256_file(local):
            raise ValueError("remote submitted structure changed")
        geometries = {}
        for name in ("POSCAR", "CONTCAR"):
            path = target / name
            if not path.is_file() or path.stat().st_size == 0:
                continue
            atoms = read(path, format="vasp")
            atoms.pbc = [True, True, False]
            if atoms.get_chemical_symbols() != ["Fe"] * 45 + ["C", "C", "O", "H"]:
                raise ValueError("CHCO atom order changed")
            bonds = {label: float(atoms.get_distance(i, j, mic=True))
                     for label, i, j in (("CC", 45, 46), ("CO", 46, 47), ("CH", 45, 48))}
            contacts = [{"atom_0based": i, "Fe_0based": int(np.argmin(atoms.get_distances(i, range(45), mic=True))),
                         "distance_A": float(min(atoms.get_distances(i, range(45), mic=True)))} for i in range(45, 49)]
            geometries[name] = {"sha256": sha256_file(path), "bonds_A": bonds, "nearest_Fe": contacts}
        output.append({"name": record["name"], "job_id": record["job_id"], "geometry": geometries})
    repair = json.loads((BASE / "gpu_repair_review_v1/review.json").read_text())["records"][0]
    repaired = next(r for r in output if r["name"] == "03_extra2_repair_v1")
    if repaired["geometry"]["POSCAR"]["sha256"] != repair["source_structure_sha256"] or not repair["geometry"]["pass"]:
        raise ValueError("existing repair binding invalid")
    write_json(REVIEW / "review.json", {
        "records": output, "scheduler_stdout": snapshot["scheduler_stdout"],
        "source_snapshot_sha256": sha256_file(REVIEW / "remote_snapshot.json"),
        "repair_review_sha256": sha256_file(BASE / "gpu_repair_review_v1/review.json"),
        "decision": "REUSE_EXISTING_INTACT_REPAIR_9842136_NO_DUPLICATE_SUBMISSION",
        "interpretation": "Original placement dissociates in both ML and DFT trajectories; this does not establish universal CHCO instability or a model-only failure.",
        "remote_inputs_changed": False, "vasp_jobs_stopped": False, "scientific_acceptance": False})
    print(json.dumps({"scheduler": snapshot["scheduler_stdout"], "geometry": output}))


def freeze():
    reviewed = REVIEW / "review.json"
    if not reviewed.is_file():
        raise ValueError("review CHCO before inference")
    plan = json.loads((SOURCE / "assessment_plan.json").read_text())
    if sha256_file(SOURCE / "labels.json") != plan["labels_sha256"]:
        raise ValueError("labels changed")
    if sha256_file(AQ) != "d6f19f637b7df4e06382e5264ab98861ac1b2dc92029bcaf8e7dd2b29dc582eb":
        raise ValueError("AQ predictions changed")
    PACKAGE.mkdir(exist_ok=False)
    shutil.copyfile(SOURCE / "labels.json", PACKAGE / "labels.json")
    shutil.copytree(SOURCE / "structures", PACKAGE / "structures")
    for name in ("matris_force_predict.py",):
        shutil.copyfile(HERE / name, PACKAGE / name)
    for name in ("mlip_same_structure_benchmark.py", "artifact_io.py"):
        shutil.copyfile(gpu.ROOT / "scripts" / name, PACKAGE / name)
    shutil.copyfile(HERE / "matris_force_prediction_job.sh", PACKAGE / "batch_job.sh")
    (PACKAGE / "runtime").mkdir()
    shutil.copyfile(BASE / "gpu_repair_v1/runtime/aqcat25_mz73_env.sh", PACKAGE / "runtime/aqcat25_mz73_env.sh")
    # Adapter for the existing no-model preflight transport; no TS request invented.
    (PACKAGE / "force_prediction_preflight.py").write_text(
        'from matris_force_predict import validate\nvalidate()\nprint("GPU_BEFORE_EXECUTION_PASS_NO_MODEL_RUN")\n', encoding="utf-8")
    write_json(PACKAGE / "authorization.json", {
        "execution_authorized": True, "user_authorization": "2026-10-10: 先修审异常CH-C-O构型，再让MatRIS对已有VASP标签的相同结构预测力，与AQCat25公平比较",
        "checkpoint_path": CHECKPOINT, "checkpoint_sha256": CHECKPOINT_SHA,
        "checkpoint_selection": "provider_baseline_same_as_original_model_benchmark_not_OH_epoch6",
        "labels_sha256": sha256_file(SOURCE / "labels.json"), "aqcat_predictions_sha256": sha256_file(AQ),
        "chco_review_sha256": sha256_file(reviewed), "geometry_optimization": False, "fine_tuning": False,
        "submit_vasp": False, "model_promotion": False, "automatic_retry": False,
        "limits": {"GPU_count": 1, "cpus": 4, "memory_GiB": 32, "walltime_minutes": 30}})
    write_json(PACKAGE / "batch_manifest.json", {"remote_root": REMOTE, "checkpoint_sha256": CHECKPOINT_SHA,
        "files": [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)}
                  for p in sorted(PACKAGE.rglob("*")) if p.is_file()]})
    print("FROZEN_10_IDENTICAL_STRUCTURES_MATRIS_BASELINE")


def compare(labels, aq, matris):
    expected = {s["sample_id"] for s in labels["samples"]}
    result = {}
    for backend, prediction in (("aqcat25", aq), ("matris", matris)):
        rows = prediction["samples"]
        by_id = {p["sample_id"]: p for p in rows}
        if len(rows) != len(by_id) or set(by_id) != expected:
            raise ValueError("sample set mismatch")
        buckets = {}
        for label in labels["samples"]:
            predicted = by_id[label["sample_id"]]
            if predicted["structure_sha256"] != label["structure_sha256"]:
                raise ValueError("nonidentical structure")
            ref = np.asarray(label["forces_eV_per_A"], dtype=float)
            forces = np.asarray(predicted["forces_eV_per_A"], dtype=float)
            if forces.shape != ref.shape or ref.shape != (len(label["symbols"]), 3) or not np.isfinite(forces).all():
                raise ValueError("invalid forces")
            fixed = set(label["fixed_atom_indices_1based"])
            for i, symbol in enumerate(label["symbols"]):
                if i + 1 in fixed:
                    continue
                group = "movable_Fe" if symbol == "Fe" else "adsorbate"
                for stage in ("all", label["label_stage"]):
                    for kind in ("all_movable", group, "element_" + symbol):
                        buckets.setdefault(stage + "/" + kind, []).append(forces[i] - ref[i])
        result[backend] = {k: metrics(np.asarray(v)) for k, v in buckets.items()}
    return result


def assess():
    receipt = json.loads((EVIDENCE / "producer_exit_record.json").read_text())
    prediction = EVIDENCE / "predictions.returned.json"
    if receipt["exit_code"] != 0 or receipt["source_batch_sha256"] != sha256_file(PACKAGE / "batch_manifest.json"):
        raise ValueError("producer failed or stale binding")
    if receipt["checkpoint_sha256"] != CHECKPOINT_SHA or receipt["predictions_sha256"] != sha256_file(prediction):
        raise ValueError("prediction provenance mismatch")
    matris = json.loads(prediction.read_text())
    auth = json.loads((PACKAGE / "authorization.json").read_text())
    if (matris["labels_sha256"] != sha256_file(SOURCE / "labels.json")
            or matris["labels_sha256"] != auth["labels_sha256"]
            or matris["checkpoint_sha256"] != CHECKPOINT_SHA
            or matris["source_batch_sha256"] != sha256_file(PACKAGE / "batch_manifest.json")
            or sha256_file(AQ) != auth["aqcat_predictions_sha256"]):
        raise ValueError("prediction labels/model mismatch")
    groups = compare(json.loads((SOURCE / "labels.json").read_text()), json.loads(AQ.read_text()), matris)
    target = EVIDENCE / "model_comparison.json"
    if target.exists():
        raise FileExistsError(target)
    write_json(target, {"groups": groups, "labels_sha256": sha256_file(SOURCE / "labels.json"),
        "matris_predictions_sha256": sha256_file(prediction), "aqcat_predictions_sha256": sha256_file(AQ),
        "matris_checkpoint_sha256": CHECKPOINT_SHA,
        "scope": "10 correlated initial/final structures from 5 jobs; no species03 CHCO or independent held-out coverage",
        "fixed_atoms_excluded": list(range(18)), "training_performed": False, "model_promoted": False,
        "speedup_measured": False, "absolute_model_energy_comparison": False})
    print(json.dumps({b: {k: v for k, v in g.items() if k in ("all/adsorbate", "final/adsorbate", "final/element_O", "all/all_movable")}
                      for b, g in groups.items()}))


def record():
    from scripts.state_manager.models import validate_event

    previous_id = "task-fe110-c2-force-gpu2177-assessed-20261008"
    previous = gpu.ROOT / "modules/state_handoff/events" / (previous_id + ".json")
    event = json.loads(previous.read_text())
    identifier = "task-fe110-c2-matris2180-compared-20261010"
    target = previous.parent / (identifier + ".json")
    if target.exists():
        raise FileExistsError(target)
    now = datetime.now(timezone.utc).isoformat()
    paths = [REVIEW / "review.json", PACKAGE / "batch_manifest.json", PACKAGE / "authorization.json",
             EVIDENCE / "preflight_binding.json", EVIDENCE / "submission_summary.json",
             EVIDENCE / "producer_exit_record.json", EVIDENCE / "predictions.returned.json",
             EVIDENCE / "model_comparison.json"]
    event.update(event_id=identifier, occurred_at=now, recorded_at=now, supersedes=[previous_id],
                 summary="Reviewed existing intact CHCO repair; MatRIS2180 exact ten-structure inference complete and compared with frozen AQCat2177 predictions, no model switch or training.",
                 evidence=[{"locator": p.relative_to(gpu.ROOT).as_posix(), "sha256": sha256_file(p),
                            "authority": "module_validation", "observed_at": now} for p in paths])
    event["payload"].update(
        current_evidence=[
            "CHCO9839757 RUN, latest CC2.760969A indicates fragmentation; 9842107 RUN CC1.432429A intact. No job stopped or input changed.",
            "Existing intact repair9842136 PEND; submitted POSCAR hash matches GPU2176 accepted candidate. Reused correction, no redundant rebuild/submission.",
            "MatRIS2180 producer exit0; ten exact structures/checkpoint/labels/source/output hashes and finite force vectors verified. Slurm terminal accounting unavailable, not inferred DONE.",
            "Same10 correlated initial/final structures, fixedFe0-17 excluded, 306 movable vectors, no CHCO03 or independent held-out coverage.",
            "AQ/MatRIS all-movable vectorRMSE0.142569/0.101360; initial adsorbate0.264832/0.159047; final adsorbate0.185275/0.157218eV/A.",
            "MatRIS improves C/O here but worsens final FeRMSE0.037950->0.091038 and HRMSE0.028731->0.089728. No production-model promotion, fine-tuning or speedup claim."
        ],
        one_executable_step="After intact CHCO VASP candidates finish, complete exact-identity/site/duplicate and force-label review, then prepare disjoint adsorption validation before selecting model or fine-tuning; no new remote calculation authorized.",
        submission_boundary="This instruction authorized only one completed MatRIS fixed-geometry diagnostic. No further training, GPU/VASP submissions, stopping or parameter changes authorized.")
    event["payload"]["authoritative_references"].extend(p.relative_to(gpu.ROOT).as_posix() for p in paths)
    validate_event(event)
    write_json(target, event)
    print(target.relative_to(gpu.ROOT).as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["review", "freeze", "assess", "record", "upload", "preflight", "submit"])
    action = parser.parse_args().action
    if action == "review":
        review()
    elif action == "freeze":
        freeze()
    elif action == "assess":
        assess()
    elif action == "record":
        record()
    else:
        gpu.PACKAGE, gpu.EVIDENCE, gpu.REMOTE = PACKAGE, EVIDENCE, REMOTE
        gpu.main()
