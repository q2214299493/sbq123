"""Compare one-point and four-point AQCat25 fits with the same update budget."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from train_latest_label import (
    EPOCHS, bound_file, handle_sigterm, isolated_config, require, require_cuda_model,
    require_single_cuda, reset_from_base, sha256_file, validate_output_root, write_json,
)


TRAINING = {"single": [12], "joint": [9, 10, 11, 12]}
VALIDATION = [7, 8]
MOVABLE = list(range(18, 49))
BASE_SHA = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"


class CyclicSingletonSampler:
    """One sample per epoch, with the same number of steps in both arms."""

    def __init__(self, indices):
        self.indices = tuple(indices)
        require(bool(self.indices) and len(set(self.indices)) == len(self.indices), "bad sampler inputs")
        self.epoch = 0

    def __len__(self):
        return 1

    def set_epoch_and_start_iteration(self, epoch, skip):
        require(skip == 0 and 0 <= epoch < EPOCHS, "unexpected resumed epoch")
        self.epoch = epoch

    def __iter__(self):
        yield [self.epoch % len(self.indices)]

    def point(self):
        return self.indices[self.epoch % len(self.indices)]


def load_sample(root, item):
    import numpy as np
    from ase.constraints import FixAtoms
    from ase.io import read

    path = root / f"point_{item['point']:02d}.vasp"
    bound_file(path, item["poscar_sha256"])
    atoms = read(path, format="vasp")
    fixed = sorted(int(i) for c in atoms.constraints for i in c.get_indices())
    require(len(atoms) == 49 and atoms.get_chemical_symbols() == ["Fe"] * 45 + ["C", "C", "O", "H"]
            and all(isinstance(c, FixAtoms) for c in atoms.constraints)
            and fixed == list(range(18)), "structure/fixed mask mismatch")
    forces = np.asarray(item["forces_eV_per_A"], dtype=float)
    require(forces.shape == (49, 3) and np.isfinite(forces).all(), "invalid label forces")
    require(np.isfinite(item["energy_eV"]), "invalid label energy")
    atoms.info.update(is_spin_off=False, is_low_fi=False, bonds_TS=[[45, 46, "form"]],
                      indices_ads=list(range(45, 49)))
    return atoms, forces


def assigned_cuda():
    import torch

    require(bool(os.environ.get("SLURM_JOB_ID")), "Slurm allocation required")
    device = require_single_cuda(torch)
    tensor = torch.empty(1, device="cuda")
    torch.cuda.synchronize()
    devices = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=pid,gpu_uuid", "--format=csv,noheader"],
        text=True, timeout=10,
    )
    assigned = [uuid.strip() for row in devices.splitlines()
                if len(parts := row.split(",", 1)) == 2
                for pid, uuid in [parts] if pid.strip() == str(os.getpid())]
    require(tensor.is_cuda and len(set(assigned)) == 1 and assigned[0].startswith("GPU-"),
            "could not bind CUDA process to an allocated GPU UUID")
    return {**device, "gpu_uuid": assigned[0], "slurm_job_id": os.environ["SLURM_JOB_ID"]}


def train(root, request, arm):
    import numpy as np
    import torch
    import yaml
    from ase.calculators.singlepoint import SinglePointCalculator
    from ase.db import connect
    from fairchem.core.common.flags import flags
    from fairchem.core.common.utils import build_config, new_trainer_context
    from fairchem.core.modules.exponential_moving_average import ExponentialMovingAverage
    from fairchem.core.models.equiformer_v2.trainers.forces_trainer import EquiformerV2ForcesTrainer

    device = assigned_cuda()
    samples = json.loads(bound_file(root / "train_points.json", request["train_sha256"]))
    require([x["point"] for x in samples] == TRAINING["joint"], "wrong train partition")
    selected = [x for x in samples if x["point"] in TRAINING[arm]]
    out = root / arm
    out.mkdir(exist_ok=False)
    db = out / "training.db"
    with connect(db) as store:
        for item in selected:
            atoms, forces = load_sample(root, item)
            atoms.calc = SinglePointCalculator(atoms, energy=item["energy_eV"], forces=forces)
            store.write(atoms, data={"sid": f"coverage_point_{item['point']}", "fid": 0,
                       "is_spin_off": False, "is_low_fi": False, "adsorption_energy": item["energy_eV"],
                       "source_label_sha256": item["label_sha256"]})
        require(store.count() == len(selected), "ASE database count mismatch")
    np.savez(out / "metadata.npz", natoms=np.full(len(selected), 49, dtype=np.int64))
    template = yaml.safe_load(bound_file(root / "force_only_config.yml", request["template_sha256"]))
    config = isolated_config(template, db)
    # End-of-fit checkpoint only. This changes disk I/O, not the optimization.
    config["optim"]["checkpoint_every"] = EPOCHS
    config_path = out / "config.yml"
    with config_path.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)
    args, overrides = flags.get_parser().parse_known_args([
        "--mode", "train", "--config-yml", str(config_path), "--run-dir", str(out),
        "--identifier", f"force-coverage-{arm}", "--seed", "0", "--amp",
    ])
    configured = build_config(args, overrides)
    require(configured["checkpoint"] is None, "automatic checkpoint restore")
    base = Path(request["base_path"])
    require(sha256_file(base) == request["base_sha256"] == BASE_SHA, "base checkpoint mismatch")
    sampler = CyclicSingletonSampler(TRAINING[arm])
    trace = []
    original_load_datasets = EquiformerV2ForcesTrainer.load_datasets

    def load_datasets_with_matched_steps(trainer):
        original_load_datasets(trainer)
        require(len(trainer.train_dataset) == len(selected) and trainer.val_loader is None
                and trainer.test_loader is None, "unexpected trainer data split")
        trainer.train_sampler = sampler
        trainer.train_loader = trainer.get_dataloader(trainer.train_dataset, sampler, workers=0)
        require(len(trainer.train_loader) == 1, "expected one sample per optimizer update")

    # Equiformer builds the scheduler from the loader length during __init__.
    with patch.object(EquiformerV2ForcesTrainer, "load_datasets", load_datasets_with_matched_steps), \
            new_trainer_context(config=configured) as ctx:
        trainer = ctx.trainer
        require_cuda_model(trainer)
        schedule = trainer.scheduler.scheduler_params
        require(schedule["epochs"] == EPOCHS and schedule["warmup_epochs"] == 1
                and schedule["lambda_type"] == "cosine" and schedule["lr"] == 1e-4,
                "scheduler was not initialized for the matched update budget")
        reset_from_base(trainer, str(base), amp=configured["amp"],
                        ema_factory=ExponentialMovingAverage, scaler_factory=torch.GradScaler)

        def after_update(*_args):
            trace.append({"step": trainer.step, "point": sampler.point(),
                          "lr": [float(g["lr"]) for g in trainer.optimizer.param_groups]})

        hook = trainer.optimizer.register_step_post_hook(after_update)
        try:
            trainer.train(disable_eval_tqdm=True)
        finally:
            hook.remove()
        checkpoint = Path(trainer.config["cmd"]["checkpoint_dir"]) / "checkpoint.pt"
    verify_trace(trace, arm)
    saved = torch.load(checkpoint, map_location="cpu", weights_only=False)
    require(saved["step"] == EPOCHS and saved["epoch"] == EPOCHS, "wrong final checkpoint step")
    require(all(torch.isfinite(x).all().item() for x in saved["state_dict"].values() if torch.is_tensor(x)),
            "nonfinite model weights")
    write_json(out / "fit_result.json", {"arm": arm, "device": device, "base_sha256": BASE_SHA,
               "trace": trace, "checkpoint": str(checkpoint), "checkpoint_sha256": sha256_file(checkpoint)})


def verify_trace(trace, arm):
    import math

    points = TRAINING[arm]
    require([event["step"] for event in trace] == list(range(1, EPOCHS + 1)), "missing optimizer updates")
    require([event["point"] for event in trace] == points * (EPOCHS // len(points)), "unbalanced sampling")
    require(all(event["lr"] and all(math.isfinite(x) and 0 < x <= 1e-4 for x in event["lr"])
                for event in trace), "unexpected actual learning rates")


def evaluate(root, request, output_root, fit_hashes=None):
    import gc
    import numpy as np
    import torch
    from fairchem.core.common.relaxation.ase_utils import patched_calc

    device = assigned_cuda()
    fits = {}
    for arm in TRAINING:
        path = root / arm / "fit_result.json"
        fits[arm] = json.loads(bound_file(path, fit_hashes[arm]) if fit_hashes else path.read_bytes())
    training_device = fits["single"]["device"]
    for arm, fit in fits.items():
        verify_trace(fit["trace"], arm)
        require(fit["base_sha256"] == BASE_SHA and fit["device"] == training_device, "arm base/allocation mismatch")
    require([x["lr"] for x in fits["single"]["trace"]] == [x["lr"] for x in fits["joint"]["trace"]],
            "learning-rate traces differ")
    # Open validation labels only after both final checkpoints have been checked.
    samples = json.loads(bound_file(root / "validation_points.json", request["validation_sha256"]))
    require([x["point"] for x in samples] == VALIDATION, "wrong validation partition")
    rows = {}
    for arm, fit in fits.items():
        ckpt = Path(fit["checkpoint"])
        require(ckpt.resolve().is_relative_to((root / arm).resolve())
                and sha256_file(ckpt) == fit["checkpoint_sha256"], "bad final checkpoint identity")
        calc = patched_calc(checkpoint_path=str(ckpt), is_spin_off=False, is_low_fi=False, cpu=False)
        require_cuda_model(calc.trainer)
        rows[arm] = []
        for item in samples:
            atoms, dft = load_sample(root, item)
            atoms.calc = calc
            ml = np.asarray(atoms.get_forces(apply_constraint=False), dtype=float)
            require(ml.shape == (49, 3) and np.isfinite(ml).all(), "bad model validation forces")
            err = ml[MOVABLE] - dft[MOVABLE]
            norms = np.linalg.norm(err, axis=1)
            rows[arm].append({"point": item["point"], "label_sha256": item["label_sha256"],
                             "predicted_forces_eV_per_A": ml.tolist(),
                             "max_vector_error_eV_per_A": float(norms.max()),
                             "component_mae_eV_per_A": float(np.abs(err).mean()),
                             "max_error_atom_one_based": MOVABLE[int(norms.argmax())] + 1})
        del atoms, calc
        gc.collect()
        torch.cuda.empty_cache()
    write_json(output_root / "comparison_result.json", {"device": device, "training_device": training_device,
               "base_sha256": BASE_SHA,
               "data_counts": {arm: dict(Counter(v["point"] for v in fit["trace"])) for arm, fit in fits.items()},
               "validation": rows, "updates_per_arm": EPOCHS, "identical_lr_trace": True,
               "force_target_eV_per_A": 0.03, "new_dft_performed": False, "model_promoted": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("single", "joint", "evaluate"))
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--fit-root", type=Path)
    parser.add_argument("--fit-sha256", nargs=2, metavar=("SINGLE", "JOINT"))
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, handle_sigterm)
    root = Path.cwd()
    validate_output_root(root)
    fit_root = args.fit_root or root
    validate_output_root(fit_root)
    require(bool(args.fit_root) == bool(args.fit_sha256)
            and (args.arm == "evaluate" or args.fit_root is None), "invalid evaluation-only fit binding")
    request = json.loads(bound_file(fit_root / "request.json", args.request_sha256))
    require(request["training"] == TRAINING and request["validation"] == VALIDATION
            and request["updates"] == EPOCHS and request["force_target_eV_per_A"] == 0.03,
            "request is outside the reviewed comparison")
    if args.arm == "evaluate":
        evaluate(fit_root, request, root, dict(zip(TRAINING, args.fit_sha256)) if args.fit_sha256 else None)
    else:
        train(root, request, args.arm)


if __name__ == "__main__":
    main()
