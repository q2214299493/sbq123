"""Independently verify the real database row order against the CPU sampling plan."""
from __future__ import annotations

from collections import Counter
from itertools import chain
from pathlib import Path

import numpy as np
import torch
import yaml
from ase.db import connect

from scripts.adsorption.force_role_runtime import RoleBatchSampler
from scripts.artifact_io import load_json_object as load, sha256_file as sha, write_json_exclusive
from .build import BATCH, FROZEN, INCREMENT, MODEL, OUT, SEED, TEMPLATE, bind, guard_hashes, verify_preserved


def native_epoch_hits(sessions, row_names, new_ids):
    result = {}
    for number, draws in enumerate(sessions, 1):
        names = [row_names[index] for index in draws]
        counts = Counter(name for name in names if name in new_ids)
        if counts != {name: 1 for name in new_ids}:
            raise ValueError(f"Epoch {number} failed the exact nine-frame visit schedule")
        result[str(number)] = {name: names.index(name) + 1 for name in sorted(new_ids)}
    return result


def main():
    doc = load(OUT / "cpu_data_preflight.json")
    assert doc["manifest"] == bind(OUT / "training_manifest.json")
    assert doc["request"] == bind(OUT / "training_request.review.json")
    assert doc["train_database"]["database_sha256"] == sha(OUT / "train.db")
    assert doc["train_database"]["metadata_sha256"] == sha(OUT / "train_metadata.npz")
    manifest = load(OUT / "training_manifest.json")
    source = load(INCREMENT / "increment_manifest.json")
    expected = [r["sample_id"] for r in manifest["splits"]["train"]]
    newer = {r["sample_id"] for r in source["samples"]}
    db = list(connect(OUT / "train.db").select())
    names = [row.data.sid for row in db]
    assert names == expected and [row.id for row in db] == list(range(1, 546))
    with np.load(OUT / "train_metadata.npz", allow_pickle=False) as metadata:
        weights = metadata["adsorption_sampling_probability"].copy()
        assert np.array_equal(metadata["row_ids"], [r.id for r in db]) and np.all(weights == 1 / 545)
    cfg = yaml.safe_load((OUT / "config.yml").read_text(encoding="utf-8"))
    reference = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    for key in ("train", "val"):
        fields = {"src", "metadata_path"}
        assert {k: v for k, v in cfg["dataset"][key].items() if k not in fields} == {
            k: v for k, v in reference["dataset"][key].items() if k not in fields
        }
    assert cfg["model"] == reference["model"]
    assert cfg["seed"] == SEED and cfg["optim"]["max_epochs"] == 2
    opts = load(Path(doc["cpu_native_mapping"]["path"]))
    assert doc["cpu_native_mapping"] == bind(OUT / "provenance" / "cpu" / "native_cpu.stdout.json")
    assert opts["seed"] == SEED and opts["checkpoint_sha256"] == sha(MODEL)
    native = native_epoch_hits(opts["epoch_draws_db_positions_0based"], names, newer)
    local = {}
    permutation = opts["database_positions_in_runtime_order"]
    sampler = RoleBatchSampler(weights[permutation], batch_size=1, seed=SEED)
    for epoch in range(2):
        sampler.set_epoch(epoch)
        drawn = [permutation[index] for (index,) in sampler]
        local[str(epoch + 1)] = len({names[index] for index in drawn} & newer)
    assert not torch.cuda.is_initialized()
    verify_preserved(load(FROZEN / "training_manifest.json"), manifest, newer)
    assert guard_hashes() == load(BATCH / "final_submission_list.json")["frozen_hashes"]
    report = OUT / "two_epoch_replay.json"
    write_json_exclusive(report, {
        "status": "PASS_NINE_NEW_ROWS_ON_EACH_EPOCH_WITH_NATIVE_CPU_ORDER",
        "source_cpu_data_preflight": bind(OUT / "cpu_data_preflight.json"),
        "native_runtime_basis": doc["cpu_native_mapping"],
        "seed": SEED, "per_frame_sampling_probability": 1 / 545,
        "native_torch_version": opts["torch"], "native_new_samples_first_draw_step_by_epoch_1based": native,
        "desktop_torch_version": str(torch.__version__), "desktop_replay_distinct_new_frames_by_epoch": local,
        "guarantee_scope": "Full two epochs with the reviewed row order, seed, and verified native loader/sampler mapping",
        "raw_training_data_uploaded_for_cpu_probe": False,
        "training_authorized": False, "gpu_started": False, "optimizer_steps": 0,
    })
    files = [
        {"path": p.relative_to(OUT).as_posix(), "sha256": sha(p), "bytes": p.stat().st_size}
        for p in sorted(OUT.rglob("*")) if p.is_file()
    ]
    write_json_exclusive(OUT / "package_inventory.json", {"files": files, "training_authorized": False})
    assert {sample for epoch in native.values() for sample in epoch} == newer
    assert len(list(chain.from_iterable(native.values()))) == 18
    print("Native positions bind all nine real IDs once in each full epoch.")
    print("Desktop CPU sampler distinct new frames per epoch:", local)


if __name__ == "__main__":
    main()
