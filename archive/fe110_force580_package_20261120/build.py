"""Assemble and CPU-check the reviewed 545+35 force-only package."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import chain
from pathlib import Path

import numpy as np
import torch
import yaml
from ase.db import connect
from ase.io import read

from archive.fe110_c2_c3_pathgap_20261119.batch import RUN, protected_inputs
from archive.fe110_combined_force_package_20261023 import prepare as owner
from archive.fe110_combined_force_package_20261023.role_helpers import role_groups
from archive.fe110_force545_increment_20261119.prepare import TEMPLATE, bind, force_table_locator
from archive.fe110_force_package_20261113.prepare import inventory_entries
from scripts.adsorption.force_finetune import local_path, verify_request
from scripts.adsorption.force_role_runtime import RoleBatchSampler
from scripts.adsorption.force_training_preflight import check_budget, check_database_labels
from scripts.artifact_io import load_json_object as load, sha256_file as sha, source_file_manifest, write_json_exclusive as save

BASE = RUN.parent
PARENT = BASE / "force545_training_package_20261119_v1"
REVIEW = RUN / "completion_review_20261120_v1"
NATIVE = BASE / "force580_cpu_mapping_check_20261120_v1"
OUT = BASE / "force580_training_package_20261120_v1"
COUNTS = {"train": 580, "development": 78, "heldout": 53}
SEED = 42
PROBABILITY = 1 / COUNTS["train"]


def verified_review():
    report = load(REVIEW / "force_label_review.json")
    isolation = load(REVIEW / "isolation_review.json")
    assert report["training_authorized"] is report["scientific_acceptance"] is False
    assert isolation["package545_manifest_sha256"] == sha(PARENT / "training_manifest.json")
    assert isolation["package545_inventory_sha256"] == sha(PARENT / "package_inventory.json")
    assert [(r["job_id"], r["sample_id"]) for r in report["records"] if r["status"] == "HOLD"] == [("9428", "family_0039_step006")]
    rows = [r for r in report["records"] if r["status"] == "QC_PASS_FORCE_INCREMENT_CANDIDATE"]
    assert len(report["records"]) == 36 and len({r["sample_id"] for r in rows}) == len(rows) == 35
    isolated = {r["id"] for r in isolation["records"] if not r["flags"]}
    assert {r["sample_id"] for r in rows} <= isolated
    return rows


def copy_parent(inventory):
    for entry in inventory:
        relative = Path(entry["path"])
        if relative.parts[0] in {"structures", "labels", "provenance", "source_archives", "runtime"} or relative.name in {
            "development.db",
            "development_metadata.npz",
            "development_build_receipt.json",
        }:
            owner.copy_checked(local_path(PARENT, entry["path"]), local_path(OUT, entry["path"]), entry["sha256"])


def copy_metadata(root, target, names):
    for name in names:
        owner.copy_checked(root / name, target / name, sha(root / name))


def admitted_row(record, evidence, collection, overlap):
    sid = record["sample_id"]
    source = REVIEW / "source_evidence" / sid
    label_path = source / "label_review.json"
    assert record["label_review"] == bind(label_path)
    label = load(label_path)
    assert label["source_job_id"] == record["job_id"] and label["source_terminal_status"] == "DONE"
    assert label["electronic_converged"] and label["normal_completion"] and label["geometry_review_pass"]
    assert label["Fe_positive_moment_count"] == 45
    assert label["isolation_evidence_sha256"] == sha(REVIEW / "isolation_review.json")
    assert label["source_scheduler_evidence_sha256"] == sha(REVIEW / "bjobs_terminal_raw.json")
    target = evidence / "source_evidence" / sid
    for filename, digest in label["source_files"].items():
        assert collection["files"][f"{sid}/{filename}"]["sha256"] == digest
        owner.copy_checked(source / filename, target / filename, digest)
    owner.copy_checked(label_path, target / "label_review.json", record["label_review"]["sha256"])
    assert label["source_POTCAR_sha256"] == collection["files"][f"{sid}/POTCAR"]["sha256"]
    assert force_table_locator(target / "OUTCAR", len(label["symbols"]), label["source_force_table_sha256"]) == label["force_table_locator"]
    original = label["source"]
    assert original["id"] == sid and sha(Path(original["source"])) == original["source_sha256"] == label["source_files"]["POSCAR"]
    if "source_metadata" in original:
        assert sha(Path(original["source_metadata"])) == original["source_metadata_sha256"]
        family = sid.rsplit("_step", 1)[0]
        group, stage = "reico_" + family, "random_static"
    else:
        assert sha(Path(original["source_outcar"])) == original["source_outcar_sha256"]
        group = "vasp_path_job" + sid.split("_", 1)[0].removeprefix("job")
        family, stage = group, "reaction_path_static"
    atoms = read(target / "POSCAR", format="vasp")
    fixed = label["fixed_atom_indices_0based"]
    assert fixed == list(range(18))
    free_count = len(atoms) - len(fixed)
    row = {
        "sample_id": sid,
        "family_id": family,
        "calculation_group": group,
        "source_name": sid,
        "source_job_id": record["job_id"],
        "composition": record["composition"],
        "partition": "train",
        "split": "train",
        "ionic_step": 1,
        "stage": stage,
        "source_collection": "fe110_pathgap_qc35_20261120",
        "structure_path": (target / "POSCAR").relative_to(OUT).as_posix(),
        "structure_sha256": label["source_files"]["POSCAR"],
        "symbols": label["symbols"],
        "source_OUTCAR_sha256": label["source_files"]["OUTCAR"],
        "source_POTCAR_sha256": label["source_POTCAR_sha256"],
        "source_force_table_sha256": label["source_force_table_sha256"],
        "forces_eV_per_A": label["forces_eV_per_A"],
        "fixed_atom_indices_0based": fixed,
        "force_role_groups": role_groups(atoms),
        "proposed_per_atom_loss_weights": [0.0] * len(fixed) + [1 / free_count] * free_count,
        "proposed_source_stage_sampling_probability": PROBABILITY,
        "energy_eV_force_label_only": label["toten_eV_force_label_only"],
        "reportable_final_energy": False,
        "magnetic_review_level": "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE",
        "electronic_converged": True,
        "geometry_review_pass": True,
        "accepted_endpoint": False,
        "training_authorized": False,
        "movable_fmax_eV_A": record["movable_fmax_eV_A"],
        "binding": {
            "static_review": {"copy_in_package": (target / "label_review.json").relative_to(OUT).as_posix(), **bind(label_path)},
            "outcar": {"copy_in_package": (target / "OUTCAR").relative_to(OUT).as_posix(), **bind(source / "OUTCAR")},
            "force_table": label["force_table_locator"],
        },
    }
    for field, values in overlap.items():
        if row[field] in values:
            raise ValueError(f"{sid} duplicates a package label by {field}")
        values.add(row[field])
    archived_label = {**label, "structure_sha256": row["structure_sha256"], "source_OUTCAR_sha256": row["source_OUTCAR_sha256"]}
    return row, archived_label


def build_increment(records, old_rows):
    evidence = OUT / "provenance" / "increment35"
    copy_metadata(
        REVIEW,
        evidence,
        ("force_label_review.json", "isolation_review.json", "bjobs_terminal_raw.json", "source_collection.json", "9428_hold_detail.json"),
    )
    collection = load(evidence / "source_collection.json")
    assert collection["scheduler_sha256"] == sha(evidence / "bjobs_terminal_raw.json")
    assert collection["source_submission_sha256"] == sha(RUN / "submission_summary.json")
    fields = ("sample_id", "source_job_id", "structure_sha256", "source_OUTCAR_sha256", "source_force_table_sha256")
    overlap = {key: {str(r.get(key)) for r in old_rows} for key in fields}
    rows, labels = zip(*(admitted_row(record, evidence, collection, overlap) for record in records), strict=True)
    label_source = evidence / "force_label_source.json"
    save(label_source, {"samples": labels, "force_unit": "eV/Angstrom", "training_authorized": False})
    sources = [
        (row, OUT, {"path": label_source.relative_to(OUT).as_posix(), "sha256": sha(label_source), "sample_id": row["sample_id"]}, None)
        for row in rows
    ]
    return owner.materialize(sources, OUT, [])


def native_replay():
    receipt = load(NATIVE / "receipt.json")
    source = NATIVE / "native_cpu.stdout.json"
    assert receipt["exit_code"] == 0 and receipt["stdout_sha256"] == sha(source)
    assert receipt["probe_payload_sha256"] == sha(NATIVE / "executed_probe.py")
    probe = load(source)
    prior_request = load(PARENT / "training_request.review.json")
    assert probe["checkpoint_sha256"] == prior_request["base_checkpoint"]["sha256"]
    assert probe["sampler_sha256"] == sha(PARENT / "runtime/scripts/adsorption/force_role_runtime.py")
    assert probe["training_row_count"] == COUNTS["train"] and probe["seed"] == SEED and probe["strict_cpu_model_load"]
    assert probe["cuda_initialized"] is probe["training_authorized"] is False
    assert probe["optimizer_steps"] == probe["native_forward_calls"] == 0
    prior_probe = load(PARENT / "provenance/cpu/native_cpu.stdout.json")
    assert probe["dataset_factory_sha256"] == prior_probe["dataset_factory_sha256"]
    assert probe["reference_config_sha256"] == sha(TEMPLATE)
    reference_config = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    base_config = yaml.safe_load((PARENT / "config.yml").read_text(encoding="utf-8"))

    def loader_options(config):
        return {k: v for k, v in config["dataset"]["train"].items() if k not in {"src", "metadata_path"}}

    assert loader_options(reference_config) == loader_options(base_config)
    mapping = probe["database_positions_in_runtime_order"]
    assert sorted(mapping) == list(range(COUNTS["train"]))
    native = probe["epoch_draws_db_positions_0based"]
    assert len(native) == 2 and all(len(epoch) == COUNTS["train"] and set(epoch) <= set(mapping) for epoch in native)
    tallies = [Counter(epoch) for epoch in native]
    assert probe["epoch_counts_by_db_position"] == [[tally[i] for i in range(COUNTS["train"])] for tally in tallies]
    return probe, prior_request


def local_replay(weights, mapping):
    sampler = RoleBatchSampler(weights[mapping], batch_size=1, seed=SEED)
    draws = []
    for epoch in range(2):
        sampler.set_epoch(epoch)
        draws.append([mapping[batch[0]] for batch in sampler])
    return draws


def ordered_training(old, new, probe):
    mapping = probe["database_positions_in_runtime_order"]
    replay = probe["epoch_draws_db_positions_0based"] + local_replay(np.full(COUNTS["train"], PROBABILITY), mapping)
    hits = [Counter(epoch) for epoch in replay]
    positions = [i for i in range(COUNTS["train"]) if all(tally[i] == 1 for tally in hits)][: len(new)]
    if len(positions) != len(new):
        raise ValueError("Insufficient positions visited exactly once in both CPU replays")
    by_position = dict(zip(positions, new, strict=True))
    old_rows = iter(deepcopy(old))
    order = [by_position[i] if i in by_position else next(old_rows) for i in range(COUNTS["train"])]
    assert next(old_rows, None) is None
    for row in order:
        row["proposed_source_stage_sampling_probability"] = PROBABILITY
    return order


def configure(prior):
    config = yaml.safe_load((PARENT / "config.yml").read_text(encoding="utf-8"))
    config["optim"].update(eval_every=COUNTS["train"], checkpoint_every=COUNTS["train"])
    with (OUT / "config.yml").open("x", encoding="utf-8", newline="\n") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)
    request = deepcopy(prior)
    request["split_counts"] = COUNTS
    request["training_limits"]["max_optimizer_steps"] = 2 * COUNTS["train"]
    request["artifacts"] = [{"path": r["path"], "sha256": sha(local_path(OUT, r["path"]))} for r in prior["artifacts"]]
    assert request["training_authorized"] is False
    assert sha(Path(request["base_checkpoint"]["path"])) == request["base_checkpoint"]["sha256"]
    check_budget(request, config)
    check_database_labels(OUT, request)
    path = OUT / "training_request.review.json"
    save(path, request)
    assert verify_request(path)["training_authorized"] is False


def verify_epochs(new, manifest, probe):
    database_rows = list(connect(OUT / "train.db").select())
    ids = [r.data.sid for r in database_rows]
    assert len(ids) == len(set(ids)) == COUNTS["train"] and ids == [r["sample_id"] for r in manifest["splits"]["train"]]
    assert [r.id for r in database_rows] == list(range(1, COUNTS["train"] + 1))
    with np.load(OUT / "train_metadata.npz", allow_pickle=False) as metadata:
        weights = metadata["adsorption_sampling_probability"].copy()
        assert np.array_equal(metadata["row_ids"], [r.id for r in database_rows])
    assert np.all(weights == PROBABILITY) and not torch.cuda.is_initialized()
    expected = {r["sample_id"] for r in new}
    evidence = {}
    local = local_replay(weights, probe["database_positions_in_runtime_order"])
    for kind, epochs in (("native", probe["epoch_draws_db_positions_0based"]), ("desktop", local)):
        evidence[kind] = []
        for draws in epochs:
            selected = [(step, ids[position]) for step, position in enumerate(draws, 1) if ids[position] in expected]
            assert Counter(sid for _, sid in selected) == dict.fromkeys(expected, 1)
            evidence[kind].append({sid: step for step, sid in selected})
    assert not torch.cuda.is_initialized()
    return evidence


def main():
    frozen = protected_inputs()
    parent_inventory = inventory_entries(PARENT)
    prior = load(PARENT / "training_manifest.json")
    assert prior["training_authorized"] is False and len(prior["splits"]["train"]) == 545
    assert {k: len(v) for k, v in prior["splits"].items() if k != "train"} == {"development": 78, "heldout": 53}
    assert len(prior["quarantined_observed_heldout"]) == 16
    records = verified_review()
    probe, prior_request = native_replay()
    OUT.mkdir()
    copy_parent(parent_inventory)
    cpu = OUT / "provenance" / "cpu580"
    copy_metadata(NATIVE, cpu, ("native_cpu.stdout.json", "receipt.json", "executed_probe.py"))
    old_rows = list(chain(*prior["splits"].values(), prior["quarantined_observed_heldout"]))
    new = build_increment(records, old_rows)
    assert Counter(r["composition"] for r in new) == {"C2H3": 5, "C2HO": 12, "C2H2O": 7, "C3H2O": 11}
    owner.assert_group_isolation(old_rows + new)
    increment_manifest = OUT / "provenance/increment35/increment_manifest.json"
    save(
        increment_manifest,
        {
            "sample_count": len(new),
            "samples": new,
            "source_review": bind(REVIEW / "force_label_review.json"),
            "excluded_job_id": "9428",
            "training_authorized": False,
        },
    )
    manifest = deepcopy(prior)
    manifest["splits"]["train"] = ordered_training(prior["splits"]["train"], new, probe)
    manifest.update(
        package_version="20261120_580_v1",
        prior_manifest_sha256=sha(PARENT / "training_manifest.json"),
        increment_manifest_sha256=sha(increment_manifest),
        sampling_policy="uniform_with_replacement; fixed seed, native permutation and database order replayed for all 35 added frames",
        source_files=source_file_manifest(
            [
                PARENT / "training_manifest.json",
                PARENT / "package_inventory.json",
                REVIEW / "force_label_review.json",
                REVIEW / "isolation_review.json",
                NATIVE / "native_cpu.stdout.json",
                Path(__file__),
            ]
        ),
    )
    expected = {r["sample_id"] for r in new}
    retained = [r for r in manifest["splits"]["train"] if r["sample_id"] not in expected]
    assert retained == [{**r, "proposed_source_stage_sampling_probability": PROBABILITY} for r in prior["splits"]["train"]]
    assert {k: manifest["splits"][k] for k in ("development", "heldout")} == {k: prior["splits"][k] for k in ("development", "heldout")}
    assert manifest["quarantined_observed_heldout"] == prior["quarantined_observed_heldout"]
    save(OUT / "training_manifest.json", manifest)
    train = owner.database("train", OUT, manifest["splits"]["train"])
    assert train["rows"] == COUNTS["train"]
    assert not any((OUT / name).exists() for name in ("heldout.db", "observed_heldout.db"))
    configure(prior_request)
    epochs = verify_epochs(new, manifest, probe)
    assert protected_inputs() == frozen and inventory_entries(PARENT) == parent_inventory
    replay_path = OUT / "two_epoch_replay.json"
    save(
        replay_path,
        {
            "visits_1based_by_epoch": epochs,
            "seed": SEED,
            "model_training_calls": 0,
            "optimizer_steps": 0,
            "cuda_initialized": False,
            "sampling_proof_scope": "Full two-epoch replay with the bound database order, native loader mapping and seed",
            "native_cpu_probe": bind(cpu / "native_cpu.stdout.json"),
            "native_torch_version": probe["torch"],
            "training_database": bind(OUT / "train.db"),
            "training_metadata": bind(OUT / "train_metadata.npz"),
        },
    )
    save(
        OUT / "cpu_data_preflight.json",
        {
            "status": "PASS_STANDALONE_580_FORCE_ONLY_CPU_PREFLIGHT",
            "split_counts": COUNTS,
            "quarantined": 16,
            "admitted_additions": len(expected),
            "excluded_job_id": "9428",
            "train_database": train,
            "native_and_local_epoch_replay": bind(replay_path),
            "request": bind(OUT / "training_request.review.json"),
            "manifest": bind(OUT / "training_manifest.json"),
            "protected_guards": frozen,
            "frozen545_inventory_sha256": sha(PARENT / "package_inventory.json"),
            "training_authorized": False,
            "gpu_started": False,
            "optimizer_steps": 0,
            "dft_submissions": 0,
        },
    )
    files = [
        {
            "path": p.relative_to(OUT).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": sha(p),
        }
        for p in sorted(OUT.rglob("*"))
        if p.is_file()
    ]
    save(OUT / "package_inventory.json", {"files": files, "training_authorized": False})
    print("580 train + 78 development rows validated; all 35 new IDs drawn once in each CPU epoch.")


if __name__ == "__main__":
    main()
