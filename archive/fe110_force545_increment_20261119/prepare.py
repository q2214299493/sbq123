"""Freeze the nine-label increment and preflight the 536/545 comparison on CPU."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
from pathlib import Path
import re

import numpy as np
import yaml
from ase.io import read

from archive.fe110_combined_force_package_20261023.prepare import assert_group_isolation
from archive.fe110_combined_force_package_20261023.role_helpers import role_groups
from archive.fe110_joint_priority_20261117.analyze import BASE, MODEL, ROOT, guard_hashes, load, sha
from scripts.adsorption.force_finetune import validate_label_row
from scripts.adsorption.force_role_data import role_metadata
from scripts.adsorption.force_training_preflight import check_budget
from scripts.artifact_io import sha256_bytes, sha256_json, source_file_manifest, source_file_manifest_valid, write_json_exclusive

OUT = BASE / "force545_increment9_20261119_v2"
BATCH = BASE / "c2_c3_label9_lsf_20261118_v1"
FROZEN = BASE / "combined_force_package_20261113_v1"
TEMPLATE = BASE / "training536_smoke_20261113_v1/package/control/config.yml"
HISTORICAL = BASE / "training536_execution_20261113_v4/final_verification.json"
DOMAINS = ("development", "heldout", "observed_heldout")
EXPECTED_ADDITIONS = {"C2H2O": 3, "C2H3": 1, "C3H2O": 5}
FORCE_TABLE = re.compile(rb"(?m)^ *POSITION\s+TOTAL-FORCE \(eV/Angst\)[^\r\n]*\r?$")


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def force_table_locator(path: Path, count: int, canonical_digest: str) -> dict:
    raw = path.read_bytes()
    matches = list(FORCE_TABLE.finditer(raw))
    if len(matches) != 1:
        raise ValueError("Expected one static force table")
    offset = matches[0].start()
    block_lines = raw[offset:].splitlines(keepends=True)[: count + 2]
    rows = [line.split() for line in block_lines[2:]]
    if len(rows) != count or any(len(row) != 6 for row in rows):
        raise ValueError("Raw force-table locator has the wrong row count")
    normalized = b"\n".join(b" ".join(row) for row in rows) + b"\n"
    if sha256_bytes(normalized) != canonical_digest:
        raise ValueError("Raw force-table locator does not reproduce the reviewed digest")
    block = b"".join(block_lines)
    assert raw[offset : offset + len(block)] == block
    return {
        "byte_offset_0based": offset,
        "byte_length": len(block),
        "atom_rows": count,
        "exact_header_and_table_sha256": sha256_bytes(block),
        "canonical_coordinate_force_rows_sha256": canonical_digest,
    }


def assemble(plan: dict, original: dict) -> tuple[list[dict], Path]:
    proof_path = OUT / "isolation_review.json"
    proof = load(proof_path)
    if not source_file_manifest_valid(proof):
        raise ValueError("The reference-source proof has changed")
    proof_rows = {row["id"]: row for row in proof["samples"]}
    collection_path = OUT / "source_collection.json"
    collection = load(collection_path)
    assert collection["final_submission_list_sha256"] == sha(BATCH / "final_submission_list.json")
    terminals = OUT / "remote_terminal_and_potcar.stdout"
    assert collection["terminal_evidence_sha256"] == sha(terminals)
    collected = {row["id"]: row for row in collection["records"]}
    assert len(collected) == len(proof_rows) == len(plan["jobs"]) == 9
    old_rows = [row for group in original["splits"].values() for row in group] + original["quarantined_observed_heldout"]
    side = load(BASE / "energy_reaction_sidecar_20261113_v1/energy_label_sidecar_final_v2.json")["records"]
    previous = old_rows + side
    old_ids = {row["sample_id"] for row in previous}
    old_jobs = {str(row.get("source_job_id")) for row in previous}
    old_hashes = {row.get("source_OUTCAR_sha256") for row in previous}
    old_force_tables = {row.get("source_force_table_sha256") for row in previous}
    labels, rows = [], []
    for job in plan["jobs"]:
        sid = job["id"]
        artifact = collected[sid]
        label_path = OUT / artifact["label_path"]
        directory = OUT / "source_evidence" / sid
        if label_path.resolve() != (directory / "label_review.json").resolve() or sha(label_path) != artifact["label_sha256"]:
            raise ValueError(f"Collected label artifact changed for {sid}")
        label = load(label_path)
        iso = proof_rows[sid]
        bindings = {
            Path(row["path"]).suffix: row for row in iso["source_bindings"] if Path(row["path"]).stem == f"step_{iso['source_step']:03d}"
        }
        geometry_path = Path(bindings[".vasp"]["path"])
        meta_path = Path(bindings[".json"]["path"])
        structure = directory / "POSCAR"
        outcar = directory / "OUTCAR"
        source_job = label["source_job_id"]
        static_input = Path(job["local_input_directory"])
        if (
            source_job != artifact["job"]
            or source_job != iso["job"]
            or sid in old_ids
            or source_job in old_jobs
            or label["source_OUTCAR_sha256"] in old_hashes
            or label["source_force_table_sha256"] in old_force_tables
        ):
            raise ValueError(f"Old or inconsistent physical label: {sid}")
        if (
            label["source_terminal_status"] != "DONE"
            or not label["normal_completion"]
            or not label["electronic_converged"]
            or label["Fe_positive_moment_count"] != 45
            or not iso["compatible_training_source_family"]
            or iso["exact_train_or_existing_label_match"]
        ):
            raise ValueError(f"Label or split proof is incomplete: {sid}")
        for name, digest in artifact["source_files"].items():
            if sha(directory / name) != digest:
                raise ValueError(f"Collected bytes changed: {sid}/{name}")
        structure_hash = sha(structure)
        if not (
            structure_hash
            == sha(geometry_path)
            == bindings[".vasp"]["sha256"]
            == label["source_POSCAR_sha256"]
            == job["input_sha256"]["POSCAR"]
            == iso["source_poscar_sha"]
        ):
            raise ValueError(f"Source frame coordinate changed: {sid}")
        if sha(meta_path) != bindings[".json"]["sha256"] or sha(outcar) != label["source_OUTCAR_sha256"]:
            raise ValueError(f"Original frame metadata or OUTCAR changed: {sid}")
        receipt = static_input / "submission_record.json"
        if sha(receipt) != label["source_submission_receipt_sha256"]:
            raise ValueError(f"LSF submission receipt changed: {sid}")
        locator = force_table_locator(outcar, len(label["symbols"]), label["source_force_table_sha256"])
        atoms = read(structure, format="vasp")
        symbols = label["symbols"]
        fixed = label["fixed_atom_indices_0based"]
        free_count = len(symbols) - len(fixed)
        forces = np.asarray(label["forces_eV_per_A"])
        maximum = float(np.linalg.norm(forces[18:], axis=1).max())
        assert maximum > 0.5 and fixed == list(range(18))
        row = {
            "sample_id": sid,
            "family_id": iso["family_id"],
            "calculation_group": "reico_" + iso["family_id"],
            "source_name": sid,
            "source_job_id": source_job,
            "composition": job["composition"],
            "partition": "train",
            "split": "train",
            "ionic_step": 1,
            "reico_step": iso["source_step"],
            "stage": "random_static",
            "optimization_phase_annotation": "off_equilibrium_high_force_static",
            "source_collection": "fe110_c2_c3_statics9_20261118",
            "structure_path": structure.relative_to(OUT).as_posix(),
            "structure_sha256": structure_hash,
            "structure_equivalence_sha256": structure_hash,
            "symbols": symbols,
            "source_OUTCAR_sha256": label["source_OUTCAR_sha256"],
            "source_POTCAR_sha256": label["source_POTCAR_sha256"],
            "source_force_table_sha256": label["source_force_table_sha256"],
            "fixed_atom_indices_0based": fixed,
            "forces_eV_per_A": label["forces_eV_per_A"],
            "force_role_groups": role_groups(atoms),
            "proposed_per_atom_loss_weights": [0.0] * 18 + [1 / free_count] * free_count,
            "proposed_source_stage_sampling_probability": 1 / 545,
            "energy_eV_force_label_only": label["toten_eV_force_label_only"],
            "magnetic_review_level": "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE",
            "electronic_converged": True,
            "geometry_review_pass": True,
            "accepted_endpoint": False,
            "reportable_final_energy": False,
            "training_authorized": False,
            "movable_fmax_eV_A": maximum,
            "binding": {
                "reico_frame": bind(geometry_path),
                "reico_frame_metadata": bind(meta_path),
                "outcar": {**bind(outcar), "source_host": plan["backend"], "source_path": job["remote_directory"] + "/OUTCAR"},
                "force_table": locator,
                "source_static_review": bind(label_path),
                "lsf_receipt": bind(receipt),
                "terminal_snapshot": bind(terminals),
                "isolation_review": {**bind(proof_path), "sample_id": sid, "row_sha256": sha256_json(iso)},
            },
        }
        role_metadata(row, "train")
        rows.append(row)
        labels.append({**label, "structure_sha256": structure_hash})
    assert Counter(row["composition"] for row in rows) == EXPECTED_ADDITIONS
    for field in ("source_job_id", "source_OUTCAR_sha256", "source_force_table_sha256", "structure_sha256"):
        assert len({row[field] for row in rows}) == 9, field
    label_source_path = OUT / "force_label_source.json"
    write_json_exclusive(
        label_source_path,
        {
            "samples": labels,
            "source_collection": bind(collection_path),
            "force_unit": "eV/Angstrom",
            "training_authorized": False,
            "reportable_final_energy": False,
        },
    )
    for row in rows:
        row["label_source"] = {
            "path": label_source_path.name,
            "sha256": sha(label_source_path),
            "sample_id": row["sample_id"],
        }
        validate_label_row(OUT, row)
    assert_group_isolation(old_rows + rows)
    return rows, label_source_path


def comparison(rows: list[dict], original: dict, ref: dict) -> None:
    cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    original_config_model = deepcopy(cfg["model"])
    limits_and_configs = {}
    plan_weights = {}
    ids = [row["sample_id"] for row in original["splits"]["train"]]
    assert len(ids) == 536 and len(set(ids)) == 536
    assert set(cfg["dataset"]) == {"train", "val"}
    assert cfg["loss_functions"] == [{"energy": {"coefficient": 0.0, "fn": "mae"}}, {"forces": {"coefficient": 1, "fn": "l2mae"}}]
    assert cfg["evaluation_metrics"]["primary_metric"] == "forces_role_vector_mae"
    assert cfg["trainer"] == "scripts.adsorption.role_force_trainer.RoleForceTrainer" and cfg["seed"] == 42
    assert cfg["optim"]["lr_initial"] == 1e-5 and cfg["optim"]["batch_size"] == cfg["optim"]["grad_accumulation_steps"] == 1
    assert all(row["proposed_source_stage_sampling_probability"] == 1 / 536 for row in original["splits"]["train"])
    for row in original["splits"]["development"]:
        role_metadata(row, "development")
    folder = OUT / "review_configs"
    folder.mkdir()
    for name, extra_ids in (("control536", []), ("increment545", [row["sample_id"] for row in rows])):
        count = len(ids) + len(extra_ids)
        config = deepcopy(cfg)
        config["optim"].update(eval_every=count, checkpoint_every=count)
        config["dataset"]["train"].update(src="${ARM_ROOT}/train.db", metadata_path="${ARM_ROOT}/train_metadata.npz")
        config["dataset"]["val"].update(
            src="${FROZEN_DEV_ROOT}/development.db", metadata_path="${FROZEN_DEV_ROOT}/development_metadata.npz"
        )
        expected = {
            "epochs": 2,
            "learning_rate": 1e-5,
            "seed": 42,
            "batch_size": 1,
            "GPU_count": 1,
            "CPU_count": 4,
            "memory_GB": 32,
            "walltime_minutes": 30,
            "unattended_retries": 0,
            "max_optimizer_steps": 2 * count,
        }
        request = {"training_limits": expected, "split_counts": {"train": count, **ref["split_counts"]}}
        check_budget(request, config)
        assert config["model"] == original_config_model and config["dataset"]["val"]["a2g_args"]["r_energy"] is False
        weights = [{"sample_id": sid, "sampling_probability": 1 / count} for sid in ids + extra_ids]
        assert len({r["sample_id"] for r in weights}) == count
        assert math.isclose(math.fsum(r["sampling_probability"] for r in weights), 1.0, abs_tol=1e-14, rel_tol=0.0)
        config_path = folder / f"{name}.yml"
        with config_path.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(config, handle, sort_keys=False)
        assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == config
        limits_and_configs[name] = {
            "config_review_template": bind(config_path),
            "split_counts": request["split_counts"],
            "limits": expected,
            "planned_native_iterations": 2 * count,
            "actual_optimizer_updates_measured": False,
            "historical_allocation_seconds_scaled_by_iterations": ref["prior_allocation_seconds"] * count / 536,
        }
        plan_weights[name] = weights
    weights_path = OUT / "sampling_weights.json"
    write_json_exclusive(
        weights_path,
        {
            "sampler": "uniform_with_replacement",
            "stage_factor": 1,
            "composition_factor": 1,
            "new_frames_probability_mass": 9 / 545,
            "expected_increment_draws_in_two_epochs": 18,
            "expected_unique_increment_frames_in_two_epochs": 9 * (1 - (544 / 545) ** 1090),
            "arms": plan_weights,
            "training_authorized": False,
        },
    )
    write_json_exclusive(
        OUT / "comparison_preflight.json",
        {
            "status": "PASS_LOCAL_DATA_BINDING_ROLE_METADATA_AND_CANONICAL_BUDGET_CHECK",
            "baseline": {**ref, "optimizer_updates_in_this_plan": 0},
            "arms": limits_and_configs,
            "common_initialization": ref["checkpoint"],
            "fresh_optimizer_scheduler_scaler_progress": True,
            "amp_proposed_per_arm": True,
            "trainable_scope_proposed": "Same full parameter scope and normalizers as frozen536 recipe",
            "energy_loss_coefficient": 0.0,
            "force_objective": "Weighted vector L2 MAE with uniform free-atom weights",
            "evaluation": {
                "development_only_for_model_choice": True,
                "primary_metric": "forces_role_vector_mae",
                "heldout_and_quarantine_loader_allowed": False,
            },
            "weights": bind(weights_path),
            "increment_manifest": bind(OUT / "increment_manifest.json"),
            "reference_training_config": bind(TEMPLATE),
            "budget_check_implementation": bind(ROOT / "scripts/adsorption/force_training_preflight.py"),
            "nominal_iteration_difference_increment_minus_control": 18,
            "preflight_status": {
                "canonical_budget": "PASS",
                "frame_probability_totals": "PASS",
                "role_metadata": "PASS",
                "native_runtime_and_checkpoint_strict_load_for_new_configs": "PENDING",
                "new_545_database_and_metadata": "PENDING_MATERIALIZATION_IN_SEPARATE_VIEW",
                "host_selection_and_allocation_cuda_check": "PENDING_FRESH_AUTHORIZATION",
            },
            "cap_gpu_hours_per_arm": 0.5,
            "cap_gpu_hours_for_two_arms": 1.0,
            "gpu_hours_consumed": 0,
            "wallclock_estimate_warning": "Historical scaling reference only. The host has not been selected.",
            "fixed_step_causal_control": False,
            "training_authorized": False,
            "dft_jobs_submitted": 0,
        },
    )


def main() -> None:
    plan = load(BATCH / "final_submission_list.json")
    assert guard_hashes() == plan["frozen_hashes"]
    original = load(FROZEN / "training_manifest.json")
    assert {split: len(rows) for split, rows in original["splits"].items()} == {"train": 536, "development": 78, "heldout": 53}
    assert len(original["quarantined_observed_heldout"]) == 16
    historical = load(HISTORICAL)
    assert sha(MODEL) == historical["candidate_sha256"] == plan["frozen_hashes"][str(MODEL)]
    ref = {
        "checkpoint": bind(MODEL),
        "source_training_manifest": bind(FROZEN / "training_manifest.json"),
        "reference_execution": bind(HISTORICAL),
        "split_counts": {"development": 78, "heldout": 53, "observed_heldout": 16},
        "prior_development_force_role_vector_mae_eV_A": 0.06199433411567066,
        "prior_allocation_seconds": 177,
    }
    rows, label_source = assemble(plan, original)
    write_json_exclusive(
        OUT / "increment_manifest.json",
        {
            "schema_version": 1,
            "document_kind": "aqcat25_force_training_increment_review",
            "status": "NINE_LABELS_BOUND_FOR_FORCE_ONLY_TRAINING_REVIEW",
            "training_target": "forces_only",
            "energy_loss_coefficient": 0,
            "sample_count": len(rows),
            "composition_counts": dict(Counter(r["composition"] for r in rows)),
            "parent_train_count": 536,
            "proposed_train_count": 545,
            "parent_training_manifest": ref["source_training_manifest"],
            "frozen_checkpoint": ref["checkpoint"],
            "protected_split_counts": ref["split_counts"],
            "source_files": source_file_manifest(
                [
                    BATCH / "final_submission_list.json",
                    OUT / "source_collection.json",
                    OUT / "isolation_review.json",
                    label_source,
                    OUT / "remote_terminal_and_potcar.stdout",
                    FROZEN / "training_manifest.json",
                    Path(__file__),
                    ROOT / "scripts/adsorption/force_finetune.py",
                    ROOT / "archive/fe110_combined_force_package_20261023/role_helpers.py",
                ]
            ),
            "samples": rows,
            "training_authorized": False,
            "reportable_final_energy": False,
        },
    )
    comparison(rows, original, ref)
    assert guard_hashes() == plan["frozen_hashes"]
    print("9 increment rows, two comparison templates and local budget checks passed")


if __name__ == "__main__":
    main()
