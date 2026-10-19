"""Real-label database roundtrip and CPU tensor calculus,no force model run."""
import json

import numpy as np
import torch
from ase.db import connect

from scripts.adsorption.force_finetune import build_database, build_database_metadata, digest
from scripts.adsorption.force_role_data import TRAINER, role_metadata
from scripts.adsorption.force_role_runtime import RoleBatchSampler, grouped_force_loss
from scripts.artifact_io import write_json_exclusive

from .probe_runtime import OUTPUT, ROOT

MANIFEST = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_pool_rebuild_20261019_v1/prepared_v2/training_manifest.json"
EXPECTED = "6deb86d4fcb2bfbde29f7d2d6faf3f2663afa2ac04c9d8a79659c876e6234330"


def main():
    if digest(MANIFEST) != EXPECTED:
        raise ValueError("reviewed phase1 pool changed")
    manifest = json.loads(MANIFEST.read_bytes())
    counts, artifacts = {}, []
    OUTPUT.mkdir(exist_ok=True)
    for split in ("train", "development"):
        database, metadata = OUTPUT / (split + ".db"), OUTPUT / (split + "_metadata.npz")
        counts[split] = build_database(MANIFEST, database, split)
        build_database_metadata(database, metadata)
        rows = list(connect(database).select())
        expected_rows = manifest["splits"][split]
        if len(rows) != len(expected_rows):
            raise ValueError("row count changed")
        for actual, original in zip(rows, expected_rows, strict=True):
            atoms = actual.toatoms()
            assert actual.data.sid == original["sample_id"]
            assert atoms.get_chemical_symbols() == original["symbols"]
            np.testing.assert_array_equal(atoms.get_forces(apply_constraint=False), original["forces_eV_per_A"])
            expected_data = role_metadata(original, split)
            for key, value in expected_data.items():
                np.testing.assert_array_equal(actual.data[key], value)
            assert np.all(atoms.get_tags() == 0)
            assert list(atoms.constraints[0].get_indices()) == list(range(18))
        artifacts += [{"path": p.name, "sha256": digest(p)} for p in (database, metadata)]
        print(split + "_DATABASE_ROUNDTRIP_PASS", counts[split], flush=True)
    rows = manifest["splits"]["train"]
    selected = [next(r for r in rows if r["origin"] == "actual_ML_failure_boundary"),
                next(r for r in rows if r["stage"] == "replay"),
                next(r for r in rows if r["origin"] == "expanded_closed_trajectory")]
    reference = torch.tensor([v for row in selected for v in row["forces_eV_per_A"]], dtype=torch.float64)
    weights = torch.tensor([v for row in selected for v in row["proposed_per_atom_loss_weights"]], dtype=torch.float64)
    fixed = torch.tensor([int(i in row["fixed_atom_indices_0based"]) for row in selected for i in range(len(row["symbols"]))])
    counts_tensor = torch.tensor([len(row["symbols"]) for row in selected])
    prediction = reference.clone()
    prediction[fixed == 0] += .02
    prediction[fixed == 1] += 1000
    prediction.requires_grad_()
    loss = grouped_force_loss(prediction, reference, weights, fixed, counts_tensor)
    assert abs(loss.item() - .02*np.sqrt(3)) < 1e-12
    loss.backward()
    assert torch.all(prediction.grad[fixed == 1] == 0)
    assert torch.isfinite(prediction.grad).all()
    probabilities = [row["proposed_source_stage_sampling_probability"] for row in rows]
    sampler = RoleBatchSampler(probabilities, batch_size=2, seed=42)
    sequence = list(sampler)
    sampler.set_epoch_and_start_iteration(0, 7)
    assert list(sampler) == sequence[7:]
    assert digest(MANIFEST) == EXPECTED
    assert not (OUTPUT / "heldout.db").exists()
    result = {"status": "PASS_REAL_LABEL_ROUNDTRIP_AND_CPU_TENSOR_GRADIENT_ONLY", "counts": counts,
        "source_manifest_sha256_before_and_after": EXPECTED, "heldout_training_or_loader": False,
        "toy_force_offset_eV_A": .02, "expected_and_actual_loss_eV_A": loss.item(),
        "selected_train_sample_ids": [r["sample_id"] for r in selected], "fixed_gradients_zero": True,
        "sampler_resume_exact": True, "opt_in_trainer_class": TRAINER, "artifacts": artifacts,
        "torch_version": torch.__version__, "device": "cpu", "force_model_loaded": False,
        "checkpoint_loaded_or_written": False, "GPU_used": False, "training_performed": False,
        "acceleration_or_model_accuracy_proved": False}
    write_json_exclusive(OUTPUT / "local_smoke_receipt.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
