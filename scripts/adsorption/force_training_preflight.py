"""Read-only checks for the opt-in adsorption training comparison; never submits."""
import argparse
import json
import shlex
from pathlib import Path

import numpy as np
import yaml
from ase.db import connect
from ase.io import read

from scripts.adsorption.force_finetune import digest, local_path, verify_request
from scripts.adsorption.force_role_data import role_metadata


def check_budget(request, config):
    limits = request["training_limits"]
    steps = request["split_counts"]["train"]  # this reviewed experiment is batch size one
    expected = {"epochs": 2, "learning_rate": 1e-5, "seed": 42, "batch_size": 1,
                "GPU_count": 1, "CPU_count": 4, "memory_GB": 32, "walltime_minutes": 30,
                "unattended_retries": 0, "max_optimizer_steps": steps * 2}
    if any(limits.get(key) != value for key, value in expected.items()):
        raise ValueError("bounded comparison budget changed")
    if config["optim"].get("eval_every") != steps or config["optim"].get("checkpoint_every") != steps:
        raise ValueError("development/checkpoint cadence must be once per epoch")
    if config["optim"]["scheduler_params"]["epochs"] != limits["epochs"]:
        raise ValueError("scheduler budget mismatch")
    if set(config["dataset"]) != {"train", "val"}:
        raise ValueError("heldout/test loader forbidden during training")
def check_database_labels(root, request):
    manifest = json.loads((root / request["manifest_path"]).read_text(encoding="utf-8"))
    for split in ("train", "development"):
        rows = list(connect(root / f"{split}.db").select())
        if len(rows) != len(manifest["splits"][split]):
            raise ValueError("database count mismatch")
        for dbrow, source in zip(rows, manifest["splits"][split], strict=True):
            atoms = dbrow.toatoms()
            original = read(local_path(root, source["structure_path"]), format="vasp")
            if dbrow.data.sid != source["sample_id"] or atoms.get_chemical_symbols() != source["symbols"]:
                raise ValueError("database row identity/order mismatch")
            for actual, expected_array in ((atoms.positions, original.positions), (atoms.cell.array, original.cell.array),
                                           (atoms.pbc, original.pbc), (atoms.get_forces(apply_constraint=False), source["forces_eV_per_A"])):
                if not np.array_equal(actual, expected_array):
                    raise ValueError("database geometry/raw force differs from source")
            if np.any(atoms.get_tags()) or sorted(int(i) for c in atoms.constraints for i in c.get_indices()) != source["fixed_atom_indices_0based"]:
                raise ValueError("database tags/fixed mask mismatch")
            for key, value in role_metadata(source, split).items():
                if not np.array_equal(dbrow.data.get(key), value):
                    raise ValueError("database role metadata differs from reviewed manifest")


def check_launcher(root):
    wrapper = (root / "runtime/role_training_job.sh").read_text(encoding="utf-8")
    if 'export PYTHONPATH="$PACKAGE_ROOT/runtime:$PYTHONPATH"' not in wrapper:
        raise ValueError("package namespace must lead PYTHONPATH")
    if any(line.startswith("#SBATCH --" + option) for option in ("requeue",) for line in wrapper.splitlines()):
        raise ValueError("automatic requeue forbidden")
    for option in ("--gres=gpu:1", "--cpus-per-task=4", "--mem=32G", "--time=00:30:00", "--no-requeue"):
        if "#SBATCH " + option not in wrapper:
            raise ValueError("launcher resource budget mismatch")


def verify_training_package(request_path: Path) -> dict:
    verdict = verify_request(request_path)
    root = request_path.parent
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request["runtime_contract_version"] != 3 or request["training_authorized"] is not False:
        raise ValueError("only an unmodified v3 review request is supported")
    config = yaml.safe_load((root / request["config_path"]).read_text(encoding="utf-8"))
    bound = {entry["path"] for entry in request["artifacts"]}
    required = {"runtime/scripts/__init__.py", "runtime/scripts/adsorption/__init__.py",
                "runtime/scripts/adsorption/force_finetune.py", "runtime/scripts/adsorption/force_training_preflight.py",
                "runtime/role_training_job.sh", "runtime/aqcat25_mz73_env.sh"}
    if not required <= bound:
        raise ValueError("namespace/launcher/preflight not hash bound")
    check_budget(request, config)
    if (root / "heldout.db").exists():
        raise ValueError("heldout database must remain outside the training package")
    check_database_labels(root, request)
    check_launcher(root)
    return {**verdict, "role_database_roundtrip": True, "namespace_and_budget_bound": True,
            "heldout_loader_created": False, "GPU_run": False, "request_sha256": digest(request_path)}


def check_native_cli(root: Path) -> dict:
    """Native parser/registry only, not trainer construction or a CUDA check."""
    from fairchem.core.common.flags import flags
    from fairchem.core.common.registry import registry
    from fairchem.core.common.utils import build_config

    request = json.loads((root / "training_request.json").read_text(encoding="utf-8"))
    config = yaml.safe_load((root / request["config_path"]).read_text(encoding="utf-8"))
    wrapper = (root / "runtime/role_training_job.sh").read_text(encoding="utf-8")
    lines = [line for line in wrapper.splitlines() if ' -m fairchem.core._cli ' in line]
    if len(lines) != 1:
        raise ValueError("expected one reviewed CLI invocation")
    tokens = shlex.split(lines[0])
    if tokens[:3] != ["$AQCAT_PYTHON", "-m", "fairchem.core._cli"]:
        raise ValueError("unexpected training entry point")
    args, overrides = flags.get_parser().parse_known_args([
        token.replace("$PACKAGE_ROOT", str(root)).replace("$RUN_ROOT", str(root / "output/preflight_placeholder"))
        for token in tokens[3:]])
    if overrides:
        raise ValueError("unreviewed CLI overrides")
    effective = build_config(args, overrides)
    for key in ("trainer", "model", "dataset", "optim", "loss_functions", "outputs", "evaluation_metrics", "seed"):
        if effective[key] != config[key]:
            raise ValueError("native CLI changes " + key)
    if effective["mode"] != "train" or not effective["amp"] or effective["submit"] or effective["world_size"] != 1:
        raise ValueError("native execution scope mismatch")
    trainer = registry.get_trainer_class(config["trainer"])
    import sys
    module = sys.modules[trainer.__module__]
    if not Path(module.__file__).resolve().is_relative_to((root / "runtime").resolve()):
        raise ValueError("trainer did not resolve from bound package namespace")
    return {"status": "PASS_NATIVE_CLI_NO_MODEL", "trainer_module": module.__file__, "model_instantiated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--native-cli", action="store_true")
    args = parser.parse_args()
    result = verify_training_package(args.request)
    if args.native_cli:
        result["native_cli"] = check_native_cli(args.request.parent)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
