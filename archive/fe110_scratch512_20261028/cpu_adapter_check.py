"""Two cheap fixed-geometry CPU interface checks;no optimization or scoring."""
import time

import numpy as np

from archive.fe110_adsorption_validation_20261018.runtime import load_atoms
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .prepare_speed import OUTPUT, PACKAGE, TRAINING_OUTPUT
from .relaxation_adapter import MODEL_SHA, nequip_calculator


def check():
    import torch
    if torch.cuda.is_initialized():
        raise ValueError("CPU interface check cannot initialize CUDA")
    target = OUTPUT / "cpu_nequip_interface.json"
    if target.exists():
        raise FileExistsError("preserve completed interface check")
    torch.set_num_threads(4)
    start = time.monotonic()
    reviewed = load_json_object(TRAINING_OUTPUT / "terminal_review_20261028.json")
    model = TRAINING_OUTPUT / "terminal_recovery_20261028_v3/returned" / reviewed["candidates"]["nequip_best"]["path"]
    calculator = nequip_calculator(model, MODEL_SHA["nequip"], "cpu")
    rows = []
    for name in ["10_A", "C3_05"]:
        source = PACKAGE / "geometry" / name / "POSCAR"
        atoms = load_atoms(source)
        positions = atoms.positions.copy()
        atoms.calc = calculator
        force = atoms.get_forces(apply_constraint=False)
        if force.shape != (len(atoms), 3) or not np.isfinite(force).all() or not np.array_equal(positions, atoms.positions):
            raise ValueError("invalid calculator output or changed fixed geometry")
        rows.append({"name": name, "POSCAR_sha256": sha256_file(source), "shape": list(force.shape),
            "finite": True, "coordinates_unchanged": True, "raw_forces_eV_A": force.tolist()})
    if torch.cuda.is_initialized():
        raise ValueError("CPU interface check unexpectedly used CUDA")
    result = {"status": "PASS_LOCAL_NEQUIP_ASE_CPU_TWO_ORIGINS", "model_sha256": sha256_file(model),
        "model_device": str(next(calculator.model.parameters()).device), "CUDA_initialized": False,
        "optimizer_steps": 0, "accuracy_established": False, "elapsed_seconds": time.monotonic()-start, "cases": rows,
        "source_files": source_file_manifest([model, PACKAGE / "request.json", __import__('pathlib').Path(__file__)])}
    write_json_exclusive(target, result)
    print({k: result[k] for k in ["status", "model_device", "CUDA_initialized", "optimizer_steps", "elapsed_seconds"]}, flush=True)


if __name__ == "__main__":
    check()
