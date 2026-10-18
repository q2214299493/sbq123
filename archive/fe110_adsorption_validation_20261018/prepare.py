"""Freeze the user-authorized16-force/three-geometry validation; never train."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json_exclusive

from .runtime import verify

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
OLD = ROOT / "calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v6"
DEST = BASE / "adsorption_validation_2185_20261018_v2"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/adsorption_validation_2185_20261018_v2"
EXCEPTION = "fe110_adsorption_validation_2185_20261018"
RUN_ID = "direct-fe110-adsorption-validation-2185-20261018-v2"


def prepare() -> None:
    # Reuse the hash-bound source package's validator, not an unrelated working
    # copy of a training adapter. Importing review/tests needs no private data.
    checked_source = subprocess.run([sys.executable, str(OLD / "runtime/force_finetune.py"), "verify",
        "--request", str(OLD / "training_request.json")], capture_output=True, check=True)
    validation = json.loads(checked_source.stdout)
    if validation["counts"] != {"train": 34, "development": 12, "heldout": 16}:
        raise ValueError("frozen source split changed")
    DEST.mkdir(exist_ok=False)
    manifest = json.loads((OLD / "training_manifest.json").read_bytes())
    calibration = BASE / "adsorption_calibration_20261018_v1"
    summary = json.loads((calibration / "development_review.json").read_bytes())
    dataset = json.loads((calibration / "current_trajectories/dataset_review.json").read_bytes())
    artifacts = []

    def copy(source: Path, relative: str) -> str:
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(target)
        shutil.copyfile(source, target)
        artifacts.append({"path": relative, "sha256": sha256_file(target)})
        return relative

    heldout = []
    for row in manifest["splits"]["heldout"]:
        path = copy(OLD / row["structure_path"], "heldout/" + row["sample_id"] + ".vasp")
        heldout.append({**row, "structure_path": path})
    cases = []
    for name in ("06_C", "07_B", "08_A"):
        rows = [s for s in dataset["samples"] if s["source_name"] == name]
        final = max(rows, key=lambda row: row["ionic_step"])
        if final["ionic_step"] != final["source_total_steps"] or not final["geometry_review_pass"]:
            raise ValueError("reference is not a reviewed final DFT frame")
        reference = calibration / "current_trajectories/sources" / name / "CONTCAR"
        cases.append({"name": name, "source_VASP_job_id": final["source_job_id"],
            "source_OUTCAR_sha256": final["source_OUTCAR_sha256"],
            "seed_path": copy(BASE / "gpu_direct_v3" / name / "POSCAR", "geometry/" + name + "/seed.vasp"),
            "reference_path": copy(reference, "geometry/" + name + "/DFT_CONTCAR"),
            "reference_sha256": sha256_file(reference), "reference_force_eV_A": final["movable_fmax_eV_A"],
            "role": "previously_screened_geometry_comparison_not_independent_holdout"})
    source_manifest = copy(OLD / "training_manifest.json", "evidence/source_training_manifest.json")
    copy(calibration / "development_review.json", "evidence/development_review.json")
    copy(calibration / "current_trajectories/split_review.json", "evidence/new_label_split_review.json")
    policy = copy(ROOT / "configs/execution_backends.yaml", "backend_policy.yaml")
    copy(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR", "geometry/clean_Fe45_CONTCAR")
    for name in ("runtime.py", "validation_helpers.py"):
        copy(Path(__file__).parent / name, "runtime/" + name)
    request = {"document_kind": "adsorption_frozen_checkpoint_gpu_validation", "schema_version": 1,
        "run_id": RUN_ID, "remote_root": REMOTE, "exception_id": EXCEPTION,
        "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "gpu_index": 1, "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da", "max_wall_seconds": 1800,
        "models": summary["checkpoints"], "heldout": heldout, "geometry_cases": cases,
        "source_manifest_path": source_manifest, "source_manifest_sha256": sha256_file(OLD / "training_manifest.json"),
        "limits": {"seed_max_steps": 80, "minimum_drift_max_steps": 20, "fmax_eV_per_A": .10},
        "comparison": "same fixed16 structures; same3 raw seeds and DFT minima; no molecular COM/height fitting",
        "scientific_boundaries": {"training": False, "new_VASP": False, "default_model_change": False,
            "energy_ranking_calibrated": False, "independent_chemical_families_proved": False,
            "heldout_used_for_epoch_selection": False, "speedup_proved": False},
        "policy": {"path": policy, "sha256": sha256_file(DEST / policy)}, "artifacts": artifacts}
    path = DEST / "validation_request.json"
    write_json_exclusive(path, request)
    write_json_exclusive(DEST / "submission_authorization.json", {
        "action": "RUN_GPU_ADSORPTION_FROZEN_VALIDATION", "user_request": "验证", "user_authorized": True,
        "request_sha256": sha256_file(path), "scope": "one bounded GPU validation only; no training/VASP/promotion"})
    checked = verify(path, DEST / "submission_authorization.json")
    archive = DEST / "validation_bundle.tar"
    with tarfile.open(archive, "x") as handle:
        for name in [item["path"] for item in artifacts] + ["validation_request.json", "submission_authorization.json"]:
            handle.add(DEST / name, arcname=name, recursive=False)
    write_json_exclusive(DEST / "preparation_receipt.json", {"request_sha256": sha256_file(path),
        "archive_sha256": sha256_file(archive), "heldout_count": len(checked["heldout"]), "geometry_cases": len(cases),
        "model_executed": False, "training_performed": False, "new_VASP": False})
    print(json.dumps({"status": "LOCAL_EXECUTABLE_PACKAGE_PASS", "request_sha256": sha256_file(path),
                      "heldout": len(heldout), "geometry_cases": len(cases)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    prepare()


if __name__ == "__main__":
    main()
