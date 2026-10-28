"""Prepare two force-only training routes without deployment or execution."""
import copy
from pathlib import Path, PurePosixPath
import shutil

import yaml

from scripts.adsorption.nequip_force_data import export_data
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .probe import OUTPUT, ROOT

SOURCE = ROOT / "calculations/fe110_reico_pilot300_20261022/combined_force_package_20261027_v3"
MANIFEST_SHA = "ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee"
REMOTE = "/home/sbq/sbq/fe110_scratch512_20261028_v1"
TYPES = ["Fe", "C", "H", "O"]


def config(data_root, run_root, stats, smoke=False):
    dataset = {"_target_": "scripts.adsorption.nequip_force_runtime.MovableASEDataset", "transforms": [
        {"_target_": "nequip.data.transforms.ChemicalSpeciesToAtomTypeMapper", "model_type_names": TYPES},
        {"_target_": "nequip.data.transforms.NeighborListTransform", "r_max": 5.}]}
    train, val = [dict(copy.deepcopy(dataset), file_path=str(data_root / (("smoke_" if smoke else "") + s + ".xyz"))) for s in ["train", "development"]]
    metrics = {"_target_": "nequip.train.MetricsManager", "metrics": [{"name": "movable_force_vector_mae", "field": None,
        "metric": {"_target_": "scripts.adsorption.nequip_force_runtime.MovableForceVectorMAE"}, "coeff": 1.}]}
    result = {"run": ["train"], "model_type_names": TYPES, "data": {
        "_target_": "nequip.data.datamodule.NequIPDataModule", "seed": 42, "train_dataset": train, "val_dataset": val,
        "train_dataloader": {"_target_": "torch.utils.data.DataLoader", "batch_size": 2 if smoke else 4, "num_workers": 0, "shuffle": False},
        "val_dataloader": {"_target_": "torch.utils.data.DataLoader", "batch_size": 2 if smoke else 4, "num_workers": 0}},
        "trainer": {"_target_": "lightning.Trainer", "accelerator": "cpu" if smoke else "gpu", "devices": 1,
            "max_epochs": 1 if smoke else 100, "max_steps": 2 if smoke else 12800, "max_time": "00:00:05:00" if smoke else "00:00:30:00",
            "num_sanity_val_steps": 0, "enable_progress_bar": False, "log_every_n_steps": 1 if smoke else 128,
            "logger": False, "default_root_dir": str(run_root), "callbacks": [
                {"_target_": "lightning.pytorch.callbacks.ModelCheckpoint", "dirpath": str(run_root), "filename": "best",
                    "save_last": True, "monitor": "val0_epoch/movable_force_vector_mae", "mode": "min"},
                {"_target_": "lightning.pytorch.callbacks.EarlyStopping", "monitor": "val0_epoch/movable_force_vector_mae",
                    "mode": "min", "patience": 20, "min_delta": 1e-4, "check_finite": True}]},
        "training_module": {"_target_": "nequip.train.NequIPLightningModule", "loss": metrics, "val_metrics": copy.deepcopy(metrics),
            "optimizer": {"_target_": "torch.optim.Adam", "lr": .001},
            "model": {"_target_": "nequip.model.NequIPGNNModel", "seed": 42, "model_dtype": "float32", "type_names": TYPES,
                "r_max": 5., "num_layers": 3, "l_max": 1, "parity": True, "num_features": 32,
                "radial_mlp_depth": 2, "radial_mlp_width": 64,
                "avg_num_neighbors": stats["avg_num_neighbors"], "per_type_energy_scales": stats["movable_force_component_rms_eV_A"],
                "per_type_energy_shifts": {s: 0. for s in TYPES}, "per_type_energy_shifts_trainable": False}},
        "hydra": {"run": {"dir": str(run_root)}, "job": {"chdir": False}}}
    if smoke:
        result["trainer"].update(limit_train_batches=2, limit_val_batches=1)
    else:
        result["data"]["train_dataloader"]["sampler"] = {"_target_": "torch.utils.data.WeightedRandomSampler",
            "weights": [1 / 512] * 512, "num_samples": 512, "replacement": True}
    return result


def prepare():
    if sha256_file(SOURCE / "training_manifest.json") != MANIFEST_SHA:
        raise ValueError("frozen source manifest changed")
    package = OUTPUT / "package"
    package.mkdir(exist_ok=False)
    summary = export_data(SOURCE / "training_manifest.json", package / "nequip/data")
    native = config(PurePosixPath(REMOTE) / "nequip/data", PurePosixPath(REMOTE) / "nequip/output", summary["training_only_initialization"])
    smoke = config(package / "nequip/data", OUTPUT / "cpu_smoke", summary["training_only_initialization"], True)
    for path, value in [(package / "nequip/config.yaml", native), (OUTPUT / "cpu_smoke.yaml", smoke)]:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(value, handle, sort_keys=False)
    runtime = package / "runtime/scripts/adsorption"
    runtime.mkdir(parents=True)
    for name in ["scripts/__init__.py", "scripts/adsorption/__init__.py", "scripts/adsorption/nequip_force_runtime.py"]:
        shutil.copyfile(ROOT / name, package / "runtime" / name)
    proposal = {"status": "PREPARED_FOR_REVIEW_NOT_AUTHORIZED_FOR_GPU_EXECUTION", "source_manifest_sha256": MANIFEST_SHA,
        "split_counts": {s: len(v) for s, v in load_json_object(SOURCE / "training_manifest.json")["splits"].items()},
        "arms": {"nequip_scratch": {"framework_version": "0.19.1", "initialization": "random_no_pretrained_checkpoint",
            "max_epochs": 100, "max_parameter_updates": 12800, "learning_rate": .001, "batch_size": 4},
            "aqcat25_finetune": {"initialization": "original_AQCat25_not_previous_finetune", "max_epochs": 20,
                "max_native_iterations": 10240, "learning_rate": 1e-5, "batch_size": 1}},
        "resources": {"sequential_arms": True, "GPU_count": 1, "per_arm_wall_seconds": 1800, "total_GPU_wall_seconds": 3600,
            "CPU_count": 4, "memory_GB": 32, "automatic_retries": 0},
        "selection": "same per-graph movable force vector MAE;development only;freeze before any heldout use",
        "scope": "workflow comparison with different architectures/optimizers;not isolated causal effect of pretraining",
        "no_DFT_no_heldout_training_no_model_promotion": True,
        "source_files": source_file_manifest([Path(__file__), SOURCE / "training_manifest.json", package / "nequip/data/export.json"])}
    write_json_exclusive(OUTPUT / "proposal.json", proposal)
    print({"exported": summary["counts"], "GPU_training_started": False, "proposal": str(OUTPUT / "proposal.json")})


if __name__ == "__main__":
    prepare()
