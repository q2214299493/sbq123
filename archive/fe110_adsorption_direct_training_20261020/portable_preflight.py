"""Hash-bound CPU preflight adapter for measured cross-platform POSCAR roundoff only."""
import argparse
import json
from pathlib import Path

import numpy as np
import yaml
from ase.db import connect
from ase.io import read

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.adsorption.direct_force_training import verify
from scripts.adsorption.force_role_data import role_metadata
from scripts.adsorption import force_training_preflight as frozen


def portable_database(root, request, coordinate_atol=1e-12):
    manifest = load_json_object(root / request["manifest_path"])
    largest, count = 0., 0
    for split in ("train", "development"):
        rows = list(connect(root / f"{split}.db").select())
        if len(rows) != len(manifest["splits"][split]):
            raise ValueError("database count mismatch")
        for dbrow, source in zip(rows, manifest["splits"][split], strict=True):
            atoms = dbrow.toatoms()
            original = read(root / source["structure_path"], format="vasp")
            if dbrow.data.sid != source["sample_id"] or atoms.get_chemical_symbols() != source["symbols"]:
                raise ValueError("row identity/order mismatch")
            if not np.allclose(atoms.positions, original.positions, rtol=0., atol=coordinate_atol):
                raise ValueError("coordinate difference exceeds numerical roundtrip allowance")
            largest = max(largest, float(np.max(np.abs(atoms.positions-original.positions))))
            for actual, expected in ((atoms.cell.array, original.cell.array), (atoms.pbc, original.pbc),
                                     (atoms.get_forces(apply_constraint=False), source["forces_eV_per_A"])):
                if not np.array_equal(actual, expected):
                    raise ValueError("cell/PBC/raw forces differ;no tolerance permitted")
            if np.any(atoms.get_tags()) or sorted(int(i) for c in atoms.constraints for i in c.get_indices()) != source["fixed_atom_indices_0based"]:
                raise ValueError("tags/fixed mask mismatch")
            for key, value in role_metadata(source, split).items():
                if not np.array_equal(dbrow.data.get(key), value):
                    raise ValueError("role/sampling metadata differs")
            count += 1
    return {"coordinate_atol_A": coordinate_atol, "largest_coordinate_difference_A": largest, "rows": count,
            "raw_forces_cell_PBC_exact": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adjustment-sha256", required=True)
    parser.add_argument("--arm", choices=("control", "treatment"), required=True)
    args = parser.parse_args()
    root = Path(__file__).parent.resolve()
    path = root / "preflight_adjustment.json"
    if sha256_file(path) != args.adjustment_sha256:
        raise ValueError("preflight adjustment changed")
    adjustment = load_json_object(path)
    if sha256_file(Path(__file__)) != adjustment["adapter_sha256"] or adjustment["coordinate_atol_A"] != 1e-12:
        raise ValueError("unbound portable comparison code/tolerance")
    approval = load_json_object(root / "preflight_adjustment_authorization.json")
    if approval["request_sha256"] != args.adjustment_sha256 or approval["user_authorized"] is not True or approval["user_request"] != "跑":
        raise ValueError("missing portable preflight authority")
    sha = adjustment["direct_request_sha256"]
    verify(root / "direct_request.json", sha, remote=True)
    arm = root / args.arm
    stats = {}
    original = frozen.check_database_labels
    def check(arm_root, request):
        stats.update(portable_database(arm_root, request))
    try:
        frozen.check_database_labels = check  # opt-in RAM-only callback;frozen disk source unchanged
        verdict = frozen.verify_training_package(arm / "training_request.json")
    finally:
        frozen.check_database_labels = original
    native = frozen.check_native_cli(arm)
    import torch
    request = load_json_object(arm / "training_request.json")
    checkpoint = Path(request["base_checkpoint"]["path"])
    if sha256_file(checkpoint) != request["base_checkpoint"]["sha256"]:
        raise ValueError("baseline changed")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    if payload["config"]["model"] != yaml.safe_load((arm / "config.yml").read_text())["model"]:
        raise ValueError("baseline architecture changed")
    result = {"status": "PASS_NATIVE_PACKAGE_CPU", "request_sha256": sha, "adjustment_sha256": args.adjustment_sha256,
        "arm": args.arm, "label_verdict": verdict, "portable_DB_comparison": stats, "native_CLI": native,
        "model_instantiated": False, "CUDA_initialized": torch.cuda.is_initialized()}
    write_json_exclusive(root / ("preflight_" + args.arm + ".json"), result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
