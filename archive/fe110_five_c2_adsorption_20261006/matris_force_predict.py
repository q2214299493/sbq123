"""Exact adsorption-force inference; no geometry optimization or training."""

import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from ase.io import read

try:
    from scripts.artifact_io import sha256_file
    from scripts.mlip_same_structure_benchmark import _load_calculator
except ModuleNotFoundError:
    from artifact_io import sha256_file
    from mlip_same_structure_benchmark import _load_calculator

ROOT = Path(__file__).resolve().parent


def validate(root=ROOT, checkpoint=True):
    batch = json.loads((root / "batch_manifest.json").read_text())
    for item in batch["files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe package path")
        if sha256_file(root / relative) != item["sha256"]:
            raise ValueError("package hash mismatch: " + item["path"])
    auth = json.loads((root / "authorization.json").read_text())
    if auth.get("execution_authorized") is not True:
        raise ValueError("inference not authorized")
    for key in ("geometry_optimization", "fine_tuning", "submit_vasp", "model_promotion"):
        if auth.get(key) is not False:
            raise ValueError("unsupported authorization: " + key)
    if checkpoint and sha256_file(Path(auth["checkpoint_path"])) != batch["checkpoint_sha256"]:
        raise ValueError("checkpoint hash mismatch")
    if checkpoint and not Path("/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS/matris").is_dir():
        raise ValueError("approved MatRIS runtime missing")
    labels = json.loads((root / "labels.json").read_text())
    validate_structures(root, labels)
    if (root / "output").exists():
        raise FileExistsError("no duplicate execution")
    return batch, auth, labels


def validate_structures(root, labels):
    names = set()
    cell = None
    for sample in labels["samples"]:
        name = sample["sample_id"]
        if name in names or Path(name).name != name:
            raise ValueError("duplicate/unsafe sample ID")
        names.add(name)
        path = root / "structures" / (name + ".vasp")
        if sha256_file(path) != sample["structure_sha256"]:
            raise ValueError("structure hash mismatch")
        atoms = read(path, format="vasp")
        if atoms.get_chemical_symbols() != sample["symbols"]:
            raise ValueError("atom order mismatch")
        if atoms.get_chemical_symbols()[:45] != ["Fe"] * 45:
            raise ValueError("not the frozen Fe45 branch")
        fixed = sorted({int(i) for c in atoms.constraints for i in c.get_indices()})
        if fixed != list(range(18)) or sample["fixed_atom_indices_1based"] != list(range(1, 19)):
            raise ValueError("fixed mask mismatch")
        if not np.isfinite(atoms.positions).all():
            raise ValueError("nonfinite geometry")
        if cell is None:
            cell = atoms.cell.array.copy()
        if not np.allclose(cell, atoms.cell.array, rtol=0, atol=1e-10):
            raise ValueError("cell mismatch")
    if len(names) != 10:
        raise ValueError("expected the identical ten AQCat structures")


def predict(output):
    import torch

    batch, auth, labels = validate()
    if socket.gethostname() != "MZ73" or not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("requires allocated MZ73 job")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    calc = _load_calculator("matris", Path(auth["checkpoint_path"]), "cuda")
    rows = []
    for sample in labels["samples"]:
        path = ROOT / "structures" / (sample["sample_id"] + ".vasp")
        atoms = read(path, format="vasp")
        # Match the previously executed AQCat evaluator's PBC and fixed mask.
        atoms.calc = calc
        forces = np.asarray(atoms.get_forces(), dtype=float)
        energy = float(atoms.get_potential_energy())
        if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all() or not np.isfinite(energy):
            raise RuntimeError("invalid prediction")
        rows.append({"sample_id": sample["sample_id"], "structure_sha256": sha256_file(path),
                     "forces_eV_per_A": forces.tolist(), "predicted_energy_eV": energy})
        print(sample["sample_id"], flush=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump({"backend": "matris", "checkpoint_sha256": batch["checkpoint_sha256"],
                   "source_batch_sha256": sha256_file(ROOT / "batch_manifest.json"),
                   "labels_sha256": sha256_file(ROOT / "labels.json"), "samples": rows}, handle, indent=2)


def run():
    batch, _, _ = validate()
    started = datetime.now(timezone.utc).isoformat()
    output = ROOT / "output"
    # Child preflight requires no output directory; create only after it returns.
    target = ROOT / "predictions.json"
    if target.exists():
        raise FileExistsError(target)
    code = subprocess.run([sys.executable, __file__, "predict", "--output", str(target)], check=False).returncode
    output.mkdir()
    receipt = {"gpu_job_id": os.environ["SLURM_JOB_ID"], "hostname": socket.gethostname(),
               "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
               "exit_code": code, "checkpoint_sha256": batch["checkpoint_sha256"],
               "source_batch_sha256": sha256_file(ROOT / "batch_manifest.json"),
               "predictions_sha256": sha256_file(target) if code == 0 else None,
               "evidence_class": "producer_process_only_not_scheduler_accounting"}
    with (output / "producer_exit_record.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2)
    raise SystemExit(code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight", "run", "predict"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "preflight":
        validate()
        print("GPU_BEFORE_EXECUTION_PASS_NO_MODEL_RUN")
    elif args.action == "predict":
        predict(args.output)
    else:
        run()
