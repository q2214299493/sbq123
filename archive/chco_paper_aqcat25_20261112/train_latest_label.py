"""One explicitly authorized, isolated AQCat25 paper-sequential training round.

Standalone deployment needs this file, the hash-bound request/POSCAR/template,
and the already installed AQCat25/FairChem environment. No submission or model
promotion is implemented. AQCat's masked L2MAE/normalization/AdamW recipe is an
explicit adaptation of the paper, not an unchanged eSEN reproduction.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
import re
import signal
from pathlib import Path
from typing import Any


EPOCHS = 100
WRITE_ROOT = Path("/home/sbq/sbq")


def handle_sigterm(signum: int, _frame: Any) -> None:
    """Let the active round's existing failure receipt handle a budget timeout."""
    raise TimeoutError(f"SIGTERM ({signum}) interrupted this round; no automatic retry")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_output_root(path: Path) -> None:
    """Accept the declared server alias while rejecting child symlink escapes."""
    require(path.is_absolute() and path.is_relative_to(WRITE_ROOT),
            "output declaration must remain below /home/sbq/sbq")
    boundary = WRITE_ROOT.resolve(strict=True)
    require(path.resolve().is_relative_to(boundary), "output resolves outside the canonical GPU write boundary")


def require_single_cuda(torch_runtime: Any) -> dict[str, Any]:
    require(torch_runtime.cuda.is_available(), "CUDA is required; CPU fallback is forbidden")
    count = torch_runtime.cuda.device_count()
    require(count == 1, "exactly one visible CUDA device is required")
    return {"visible_cuda_device_count": count, "visible_cuda_device_name": torch_runtime.cuda.get_device_name(0)}


def require_cuda_model(trainer: Any) -> list[str]:
    require(trainer.cpu is False, "trainer selected CPU fallback")
    parameters = list(trainer.model.parameters())
    require(parameters and all(parameter.device.type == "cuda" for parameter in parameters),
            "every model parameter must reside on CUDA")
    return sorted({str(parameter.device) for parameter in parameters})


def bound_file(path: Path, digest: str) -> bytes:
    require(isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest) is not None, "invalid SHA256")
    require(path.stat().st_size <= 10 * 1024 * 1024, f"text input is unexpectedly large: {path}")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, f"input hash mismatch: {path}")
    return raw


def validated_label(request: dict[str, Any]) -> tuple[dict[str, Any], list[list[float]], list[int]]:
    require(request.get("document_kind") == "paper_sequential_training_request", "wrong training request kind")
    require(isinstance(request.get("protocol_sha256"), str) and
            re.fullmatch(r"[a-f0-9]{64}", request["protocol_sha256"]) is not None, "missing frozen protocol hash")
    require(request.get("checkpoint_selection") == "final_epoch_only", "validation epoch selection is forbidden")
    for key in ("reset_model_weights", "reset_optimizer_state", "reset_scheduler_state", "reset_amp_state", "reset_ema_state"):
        require(request.get(key) is True, f"request must require {key}")
    settings = request["training"]
    for key, expected in {"epochs": EPOCHS, "initial_learning_rate": 1e-4, "scheduler": "cosine",
                          "target": "forces_only", "energy_loss_coefficient": 0.0,
                          "train_on_all": False, "train_finetuned": False, "replay": False,
                          "validation_epoch_selection": False}.items():
        require(settings.get(key) is expected if isinstance(expected, bool) else settings.get(key) == expected,
                f"unsupported training setting: {key}")
    restrictions = request["restrictions"]
    require(set(restrictions) == {"submission_allowed", "automatic_submission", "scientifically_validated_ts",
                                  "reportable_barrier", "production_checkpoint_promotion"} and
            all(value is False for value in restrictions.values()), "request cannot grant scientific or submission authority")
    samples = request["training_samples"]
    require(isinstance(samples, list) and len(samples) == 1, "only the latest single label may train")
    sample = samples[0]
    raw = base64.b64decode(sample["raw_label_base64"], validate=True)
    require(hashlib.sha256(raw).hexdigest() == sample["artifact_sha256"], "original label bytes hash mismatch")
    label = json.loads(raw)
    require(label == sample["label"], "parsed label differs from original bytes")
    for key in ("normal_completion", "electronically_converged", "eligible_for_force_only_training"):
        require(label.get(key) is True, f"owner label failed {key}")
    forces = label["forces_eV_per_A"]
    require(isinstance(forces, list) and len(forces) > 0, "empty raw forces")
    require(all(isinstance(row, list) and len(row) == 3 and all(
        type(value) in (int, float) and math.isfinite(value) for value in row) for row in forces), "invalid raw Nx3 forces")
    require(forces == sample["raw_forces_eV_per_A"], "training forces differ from original raw forces")
    movable = request["movable_atom_indices_zero_based"]
    require(isinstance(movable, list) and movable and all(type(i) is int and 0 <= i < len(forces) for i in movable)
            and len(set(movable)) == len(movable), "invalid movable mask")
    fixed = sorted(set(range(len(forces))) - set(movable))
    require(label.get("fixed_atom_indices_zero_based") == fixed, "label fixed mask mismatch")
    energy = label["dft_toten_eV_force_label_only"]
    require(type(energy) in (int, float) and math.isfinite(energy), "missing finite owner DFT energy")
    return label, forces, movable


def isolated_config(template: dict[str, Any], database: Path) -> dict[str, Any]:
    """Keep the AQCat recipe, changing only this experiment's data/epochs/output policy."""
    config = copy.deepcopy(template)
    require(config["trainer"] == "equiformerv2_forces", "unexpected AQCat trainer")
    require(config["optim"]["lr_initial"] == 1e-4 and config["optim"]["batch_size"] == 1, "AQCat learning rate/batch mismatch")
    require(config["optim"]["scheduler"] == "LambdaLR" and
            config["optim"]["scheduler_params"]["lambda_type"] == "cosine", "AQCat cosine scheduler required")
    losses = {name: settings for row in config["loss_functions"] for name, settings in row.items()}
    require(set(losses) == {"energy", "forces"} and losses["energy"]["coefficient"] == 0.0 and
            losses["forces"]["coefficient"] == 1 and losses["forces"]["fn"] == "l2mae", "AQCat force-only loss mismatch")
    require(config["outputs"]["forces"]["train_on_free_atoms"] is True, "AQCat free-atom force mask required")
    train = config["dataset"]["train"]
    require(train["a2g_args"]["r_energy"] is False and train["a2g_args"]["r_forces"] is True, "force-only graph labels required")
    train.update(format="ase_db", src=str(database.resolve()))
    config["dataset"] = {"train": train}
    for key in ("val_dataset", "test_dataset", "relax_dataset"):
        config.pop(key, None)
    config["checkpoint"] = None
    config["logger"] = "tensorboard"
    config.setdefault("task", {})["eval_relaxations"] = False
    config["optim"].update(max_epochs=EPOCHS, load_best=False, checkpoint_every=-1)
    config["optim"]["scheduler_params"]["epochs"] = EPOCHS
    return config


def reset_from_base(trainer: Any, base_path: str, *, amp: bool, ema_factory: Any, scaler_factory: Any) -> None:
    """Use the installed loader's compatibility handling, never resume training state."""
    require(trainer.epoch == 0 and trainer.step == 0 and not trainer.optimizer.state, "trainer was not freshly constructed")
    scheduler_before = copy.deepcopy(trainer.scheduler.scheduler.state_dict())
    trainer.load_checkpoint(checkpoint_path=base_path, inference_only=True)
    require(trainer.epoch == 0 and trainer.step == 0 and not trainer.optimizer.state, "base loading resumed training state")
    require(trainer.scheduler.scheduler.state_dict() == scheduler_before, "base loading changed the fresh scheduler")
    trainer.ema = ema_factory(trainer.model.parameters(), trainer.ema_decay) if trainer.ema_decay else None
    trainer.scaler = scaler_factory("cuda") if amp and not trainer.cpu else None


def completed_training(trainer: Any, updates: list[dict[str, Any]], saved: dict[str, Any]) -> dict[str, Any]:
    require(len(trainer.train_dataset) == len(trainer.train_loader) == 1, "training must contain one structure/batch")
    require(trainer.val_loader is None and trainer.test_loader is None, "validation/test selection is forbidden")
    require(trainer.step == EPOCHS and trainer.epoch == EPOCHS, "live trainer did not complete 100 epochs")
    require(updates == [{"step": i, "epoch": float(i)} for i in range(1, EPOCHS + 1)], "100 actual optimizer updates were not observed")
    require(saved.get("step") == EPOCHS and saved.get("epoch") == EPOCHS, "final checkpoint did not record 100 epochs")
    require(saved.get("config", {}).get("optim", {}).get("max_epochs") == EPOCHS, "final checkpoint epoch configuration mismatch")
    require("state_dict" in saved, "final checkpoint has no model state")
    return {"completed_epochs": trainer.epoch, "completed_steps": trainer.step,
            "observed_optimizer_updates": len(updates), "optimizer_update_events": updates}


def train_round(config_path: Path, base_path: str, run_root: Path) -> tuple[Path, dict[str, Any]]:
    """Called only after external authorization; no task.setup or submission API."""
    import torch
    from fairchem.core.common.flags import flags
    from fairchem.core.common.utils import build_config, new_trainer_context
    from fairchem.core.modules.exponential_moving_average import ExponentialMovingAverage

    devices = require_single_cuda(torch)
    args, overrides = flags.get_parser().parse_known_args([
        "--mode", "train", "--config-yml", str(config_path), "--run-dir", str(run_root),
        "--identifier", "paper-latest-label", "--seed", "0", "--amp",
    ])
    config = build_config(args, overrides)
    require(config["checkpoint"] is None, "context must not auto-load a checkpoint")
    with new_trainer_context(config=config) as context:
        trainer = context.trainer
        require_cuda_model(trainer)
        require(len(trainer.train_dataset) == len(trainer.train_loader) == 1 and
                trainer.val_loader is None and trainer.test_loader is None, "unexpected dataset or validation loader")
        reset_from_base(trainer, base_path, amp=config["amp"], ema_factory=ExponentialMovingAverage,
                        scaler_factory=torch.GradScaler)
        devices["model_parameter_devices"] = require_cuda_model(trainer)
        updates: list[dict[str, Any]] = []

        def observed_update(*_args: Any) -> None:
            updates.append({"step": trainer.step, "epoch": float(trainer.epoch)})

        hook = trainer.optimizer.register_step_post_hook(observed_update)
        try:
            trainer.train(disable_eval_tqdm=True)
        finally:
            hook.remove()
        checkpoint = Path(trainer.config["cmd"]["checkpoint_dir"]) / "checkpoint.pt"
        require(checkpoint.is_file(), "final checkpoint.pt was not written")
        saved = torch.load(checkpoint, map_location="cpu", weights_only=False)
        evidence = completed_training(trainer, updates, saved)
        evidence["execution_devices"] = devices
        return checkpoint, evidence


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)


def execute(args: argparse.Namespace) -> dict[str, Any]:
    import yaml
    from ase.calculators.singlepoint import SinglePointCalculator
    from ase.constraints import FixAtoms
    from ase.db import connect
    from ase.io import read

    require(args.execute_authorized, "separate explicit training authorization is required")
    validate_output_root(args.output_root)
    require(not args.output_root.exists(), "output root already exists; choose a new round directory")
    raw_request = bound_file(args.request, args.request_sha256)
    raw_template = bound_file(args.template, args.template_sha256)
    request = json.loads(raw_request)
    label, forces, movable = validated_label(request)
    structure_sha256 = label["structure"]["sha256"]
    bound_file(args.structure, structure_sha256)
    base = request["base_checkpoint"]
    # Hash large checkpoints incrementally; do not read/deserialize them during preflight.
    require(sha256_file(Path(base["path"])) == base["sha256"], "frozen base checkpoint hash mismatch")
    atoms = read(args.structure, format="vasp")
    require(len(atoms) == len(forces), "structure/force atom count mismatch")
    require(all(isinstance(constraint, FixAtoms) for constraint in atoms.constraints), "partial/unknown SD constraints are unsupported")
    fixed = sorted({int(index) for constraint in atoms.constraints for index in constraint.get_indices()})
    require(fixed == sorted(set(range(len(atoms))) - set(movable)), "POSCAR SD free mask differs from accepted label")
    template = yaml.safe_load(raw_template)
    config = isolated_config(template, args.output_root / "training.db")
    args.output_root.mkdir(parents=True, exist_ok=False)
    try:
        atoms.calc = SinglePointCalculator(atoms, energy=label["dft_toten_eV_force_label_only"], forces=forces)
        with connect(args.output_root / "training.db") as database:
            database.write(atoms, data={"sid": "latest_owner_accepted_label", "fid": 0, "is_spin_off": False,
                                       "is_low_fi": False, "adsorption_energy": label["dft_toten_eV_force_label_only"],
                                       "reportable_final_energy": False, "source_label_sha256": request["training_samples"][0]["artifact_sha256"]})
            require(database.count() == 1, "training database must contain exactly one label")
        config_path = args.output_root / "config.yml"
        with config_path.open("x", encoding="utf-8") as stream:
            yaml.safe_dump(config, stream, sort_keys=False)
        write_json(args.output_root / "input_binding.json", {
            "request_sha256": args.request_sha256, "template_sha256": args.template_sha256,
            "base_checkpoint": base, "structure_sha256": structure_sha256,
            "label_sha256": request["training_samples"][0]["artifact_sha256"],
            "runner_sha256": sha256_file(Path(__file__)), "config_sha256": sha256_file(config_path),
            "database_sha256": sha256_file(args.output_root / "training.db"),
            "model_recipe_adaptation": "AQCat25 existing masked normalized L2MAE/AdamW/cosine, not original eSEN",
        })
        checkpoint, evidence = train_round(config_path, base["path"], args.output_root)
        require(sha256_file(Path(base["path"])) == base["sha256"], "frozen base checkpoint changed during training")
        result = {"document_kind": "aqcat25_paper_single_label_training_result", "status": "completed_candidate_only",
                  "training_request_artifact_sha256": args.request_sha256, "protocol_sha256": request["protocol_sha256"],
                  "base_checkpoint_sha256": base["sha256"],
                  "checkpoint": {"path": str(checkpoint), "sha256": sha256_file(checkpoint)},
                  "training_evidence": evidence, "production_checkpoint_promotion": False,
                  "scientific_acceptance": False, "reportable_final_energy": False, "reportable_barrier": False}
        write_json(args.output_root / "training_result.json", result)
        return result
    except Exception as error:
        write_json(args.output_root / "training_failure.json", {
            "status": "failed_no_automatic_retry", "type": type(error).__name__, "message": str(error),
            "training_request_artifact_sha256": args.request_sha256, "scientific_acceptance": False,
        })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("request", "structure", "template", "output-root"):
        parser.add_argument(f"--{flag}", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--template-sha256", required=True)
    parser.add_argument("--execute-authorized", action="store_true")
    args = parser.parse_args()
    if not args.execute_authorized:
        parser.error("--execute-authorized requires separate external training authorization")
    previous_handler = signal.signal(signal.SIGTERM, handle_sigterm)
    try:
        result = execute(args)
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    print(json.dumps({"status": result["status"], "completed_epochs": result["training_evidence"]["completed_epochs"]}))


if __name__ == "__main__":
    main()
