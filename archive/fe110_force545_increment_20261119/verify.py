"""Read back the finished review, including the CPU checkpoint and sampler."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import torch
import yaml

from scripts.adsorption.force_finetune import validate_label_row
from scripts.adsorption.force_role_runtime import RoleBatchSampler
from scripts.adsorption.force_training_preflight import check_budget
from scripts.artifact_io import sha256_json, source_file_manifest_valid, write_json_exclusive
from .prepare import BATCH, FROZEN, MODEL, OUT, TEMPLATE, bind, force_table_locator, guard_hashes, load, sha


def sample_indices(probabilities) -> list[int]:
    sampler = RoleBatchSampler(probabilities, batch_size=1, seed=42)
    assert len(sampler) == len(probabilities)
    indices = []
    for epoch in (0, 1):
        sampler.set_epoch(epoch)
        indices.extend(batch[0] for batch in sampler)
    assert len(indices) == 2 * len(probabilities)
    return indices


def main() -> None:
    manifest_path = OUT / "increment_manifest.json"
    preflight_path = OUT / "comparison_preflight.json"
    weights_path = OUT / "sampling_weights.json"
    isolation_path = OUT / "isolation_review.json"
    manifest = load(manifest_path)
    preflight = load(preflight_path)
    probabilities = load(weights_path)
    isolation = load(isolation_path)
    assert source_file_manifest_valid(manifest) and source_file_manifest_valid(isolation)
    assert preflight["increment_manifest"] == bind(manifest_path) and preflight["weights"] == bind(weights_path)
    assert len(manifest["samples"]) == 9 and len(isolation["same_composition_pair_distances_A"]) == 13
    proof = {row["id"]: row for row in isolation["samples"]}
    for row in manifest["samples"]:
        validate_label_row(OUT, row)
        binding = row["binding"]
        for name in ("reico_frame", "reico_frame_metadata", "outcar", "source_static_review", "lsf_receipt", "terminal_snapshot"):
            assert sha(Path(binding[name]["path"])) == binding[name]["sha256"]
        assert sha256_json(proof[row["sample_id"]]) == binding["isolation_review"]["row_sha256"]
        assert binding["isolation_review"]["sha256"] == sha(isolation_path)
        assert (
            force_table_locator(Path(binding["outcar"]["path"]), len(row["symbols"]), row["source_force_table_sha256"])
            == binding["force_table"]
        )

    torch.set_num_threads(2)
    state = torch.load(MODEL, map_location="cpu", weights_only=True)
    template = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    assert state["config"]["model"] == template["model"]
    assert state["state_dict"] and all(v.device.type == "cpu" and torch.isfinite(v).all().item() for v in state["state_dict"].values())
    assert not set(state) & {"optimizer", "scheduler", "scaler", "epoch", "step"}
    assert sha(MODEL) == preflight["common_initialization"]["sha256"]
    normalizer = template["dataset"]["train"]["transforms"]["normalizer"]["forces"]
    assert float(state["normalizers"]["forces"]["mean"]) == normalizer["mean"]
    assert math.isclose(float(state["normalizers"]["forces"]["rmsd"]), normalizer["stdev"], rel_tol=1e-7)
    prior_metric = state["val_metrics"]["forces_role_vector_mae"]
    assert prior_metric["numel"] == 78 and prior_metric["metric"] == preflight["baseline"]["prior_development_force_role_vector_mae_eV_A"]
    assert not torch.cuda.is_initialized()

    counts = {}
    for arm, expected_count in (("control536", 536), ("increment545", 545)):
        spec = preflight["arms"][arm]
        cfg_ref = spec["config_review_template"]
        cfg_path = Path(cfg_ref["path"])
        assert sha(cfg_path) == cfg_ref["sha256"]
        config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        check_budget({"training_limits": spec["limits"], "split_counts": spec["split_counts"]}, config)
        arm_rows = probabilities["arms"][arm]
        all_p = np.array([row["sampling_probability"] for row in arm_rows])
        assert len(all_p) == expected_count and np.all(all_p == 1 / expected_count)
        indices = sample_indices(all_p)
        extra = [i for i in indices if i >= 536]
        counts[arm] = {
            "draws": len(indices),
            "sample_count": len(all_p),
            "sum_probability": float(all_p.sum()),
            "increment_draws_in_local_CPU_sampler_simulation": len(extra),
            "unique_increment_frames_in_simulation": len(set(extra)),
        }
    sensitivity = []
    for factor in (2, 4):
        trial = np.array([1.0] * 536 + [float(factor)] * 9)
        trial /= trial.sum()
        selected = [idx for idx in sample_indices(trial) if idx >= 536]
        sensitivity.append(
            {
                "new_frame_factor": factor,
                "new_frame_probability_mass": float(trial[536:].sum()),
                "increment_draws": len(selected),
                "distinct_increment_frames": len(set(selected)),
            }
        )

    original = load(FROZEN / "training_manifest.json")
    assert [len(original["splits"][split]) for split in ("train", "development", "heldout")] == [536, 78, 53]
    assert len(original["quarantined_observed_heldout"]) == 16
    assert guard_hashes() == load(BATCH / "final_submission_list.json")["frozen_hashes"]
    assert not torch.cuda.is_initialized()
    write_json_exclusive(
        OUT / "local_verification.json",
        {
            "status": "PASS_REVIEW_READBACK_RAW_FORCE_BINDING_CPU_CHECKPOINT_AND_SAMPLER",
            "input_artifacts": [bind(p) for p in (manifest_path, isolation_path, preflight_path, weights_path)],
            "model": {
                "artifact": bind(MODEL),
                "readback_device": "cpu",
                "torch_version": str(torch.__version__),
                "model_config_matches": True,
                "finite_state_tensors": len(state["state_dict"]),
                "native_forces_role_vector_mae": prior_metric["metric"],
                "native_dev_frames": prior_metric["numel"],
            },
            "sampler": counts,
            "sampling_sensitivity_not_applied": sensitivity,
            "physical_label_rows_replayed": 9,
            "frozen_guard_hashes_unchanged": True,
            "native_fairchem_runtime_preflight_completed": False,
            "amp_proposed_per_arm": True,
            "gpu_initialized": False,
            "models_trained": 0,
            "new_dft_jobs": 0,
        },
    )
    print("CPU readback passed:", counts)


if __name__ == "__main__":
    main()
