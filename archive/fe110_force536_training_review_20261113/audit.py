"""Read-only configuration, sampling and budget evidence; no training requests."""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from archive.fe110_combined_force_package_20261023.prepare import save_once
from scripts.adsorption.force_training_preflight import check_budget
from scripts.artifact_io import load_json_object as load
from scripts.artifact_io import sha256_file, source_file_manifest, source_file_manifest_valid

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
PACKAGE = BASE / "combined_force_package_20261113_v1"
OUTPUT = BASE / "force536_training_review_20261113_v1"
HISTORY = BASE / "scratch512_20261028_v1"
CONTROL = HISTORY / "package/finetune/control"
OLD = BASE / "training512_gpu0_20261027_v1"
NEW_COLLECTION = "c3_lowforce24_job9924387_20261109"


def phase(row):
    fixed = set(row["fixed_atom_indices_0based"])
    free = [i for i in range(len(row["symbols"])) if i not in fixed]
    fmax = float(np.linalg.norm(np.asarray(row["forces_eV_per_A"])[free], axis=1).max())
    if "movable_fmax_eV_A" in row and abs(fmax - row["movable_fmax_eV_A"]) > 1e-10:
        raise ValueError("cached force maximum differs from raw labels")
    label = "le0p05" if fmax <= .05 else "0p05_to0p10" if fmax <= .10 else "0p10_to0p50" if fmax <= .50 else "gt0p50"
    return label, fmax


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["composition"]].append(row)
    result = {}
    for composition, group in sorted(groups.items()):
        low = [r for r in group if phase(r)[1] <= .05]
        fe_masses = [sum(w for s, w in zip(r["symbols"], r["proposed_per_atom_loss_weights"], strict=True) if s == "Fe")
                     for r in group]
        result[composition] = {
            "frames": len(group), "force_bins": dict(Counter(phase(r)[0] for r in group)),
            "low_force_family_counts": dict(Counter(r["calculation_group"] for r in low)),
            "low_force_magnetic_levels": dict(Counter(r["magnetic_review_level"] for r in low)),
            "mean_Fe_loss_mass": float(np.mean(fe_masses)),
            "minimum_movable_fmax_eV_A": min(phase(r)[1] for r in group)}
    return result


def sampling_sensitivity(rows):
    result = []
    for multiplier in (1, 2, 4):
        masses = np.asarray([multiplier if phase(r)[1] <= .05 else 1 for r in rows], dtype=float)
        probabilities = masses / masses.sum()
        by_family = defaultdict(float)
        for row, probability in zip(rows, probabilities, strict=True):
            by_family[row["calculation_group"]] += float(probability)
        result.append({"illustrative_only_not_approved": True, "low_force_multiplier": multiplier,
                       "normalization": "global;all fmax<=0.05 frames only;not a selected policy",
                       "new24_mass": float(sum(p for r, p in zip(rows, probabilities, strict=True)
                                                if r.get("source_collection") == NEW_COLLECTION)),
                       "C3_mass": float(sum(p for r, p in zip(rows, probabilities, strict=True) if r["composition"] == "C3H2O")),
                       "family0099_mass": by_family["reico_family_0099"],
                       "C2H3_low_force_mass": float(sum(p for r, p in zip(rows, probabilities, strict=True)
                                                       if r["composition"] == "C2H3" and phase(r)[1] <= .05)),
                       "largest_family": max(by_family, key=by_family.get), "largest_family_mass": max(by_family.values())})
    return result


def budget_probes(request, config):
    check_budget(request, config)
    future, settings = copy.deepcopy(request), copy.deepcopy(config)
    future.pop("preparation_contract", None)
    future["split_counts"]["train"] = 536
    future["training_limits"].update(epochs=2, max_optimizer_steps=1072)
    settings["optim"].update(max_epochs=2, eval_every=536, checkpoint_every=536)
    settings["optim"]["scheduler_params"]["epochs"] = 2
    check_budget(future, settings)
    failures = {}
    wrong_steps = copy.deepcopy(future)
    wrong_steps["training_limits"]["max_optimizer_steps"] = 1024
    old_contract = copy.deepcopy(request)
    old_contract["split_counts"]["train"] = 536
    for name, probe, params in (("536_with_old1024_limit", wrong_steps, settings),
                                ("536_reusing_scratch512_twenty_epoch_contract", old_contract, config)):
        try:
            check_budget(probe, params)
        except ValueError as error:
            failures[name] = str(error)
        else:
            raise ValueError("expected stale-scope rejection missing: " + name)
    return {"historical512_twenty_epoch_budget_check": "PASS", "in_memory536_two_epoch_budget_check": "PASS",
            "expected_rejections": failures, "full_package_preflight_run": False,
            "training_request_created": False, "execution_authorized": False}


def frozen_hashes():
    keys = ("training_manifest.json", "train.db", "development.db", "train_metadata.npz",
            "development_metadata.npz", "package_inventory.json")
    return {str(root.relative_to(BASE) / name): sha256_file(root / name)
            for root in (PACKAGE, BASE / "combined_force_package_20261027_v3") for name in keys}


def run():
    before = frozen_hashes()
    if sha256_file(PACKAGE / "training_manifest.json") != "02ef3dcbf5306733856429b51406767d6e62f6fbc200c13b91a117a4a737bcd2":
        raise ValueError("frozen536 manifest identity changed")
    for name in ("training_manifest.json", "independent_verification.json"):
        if not source_file_manifest_valid(load(PACKAGE / name)):
            raise ValueError("frozen package evidence binding stale")
    manifest = load(PACKAGE / "training_manifest.json")
    rows, development = manifest["splits"]["train"], manifest["splits"]["development"]
    # Check a bounded sample before processing the complete train/development sets.
    for row in rows[:5]:
        phase(row)
        if not np.isclose(sum(row["proposed_per_atom_loss_weights"]), 1):
            raise ValueError("per-frame weights are not normalized")
    if len(rows) != 536 or len(development) != 78:
        raise ValueError("training/development counts differ")
    if any(r["proposed_source_stage_sampling_probability"] != 1 / 536 for r in rows):
        raise ValueError("frozen uniform sampler changed")
    old_snapshot = load(OLD / "status_completion_check.json")
    producer = old_snapshot["producer"]
    seconds = (datetime.fromisoformat(producer["producer_exit_record.json"]["finished_at"])
               - datetime.fromisoformat(producer["started.json"]["started_at"])).total_seconds()
    scratch = load(HISTORY / "terminal_review_20261028.json")
    historical_rows = load(OLD / "collection_receipt.json")
    candidate_path = Path(historical_rows["candidate_path"])
    if sha256_file(candidate_path) != historical_rows["candidate_sha256"]:
        raise ValueError("historical two-epoch candidate hash changed")
    request = load(CONTROL / "training_request.json")
    config = yaml.safe_load((CONTROL / "config.yml").read_text(encoding="utf-8"))
    dependencies = [Path(__file__), PACKAGE / "training_manifest.json", PACKAGE / "independent_verification.json",
                    PACKAGE / "package_inventory.json", CONTROL / "training_request.json", CONTROL / "config.yml",
                    OLD / "status_completion_check.json", OLD / "collection_receipt.json", HISTORY / "terminal_review_20261028.json",
                    ROOT / "configs/execution_backends.yaml", ROOT / "scripts/adsorption/force_training_preflight.py",
                    ROOT / "scripts/adsorption/force_finetune.py", ROOT / "scripts/adsorption/force_role_data.py",
                    ROOT / "scripts/adsorption/force_role_runtime.py", ROOT / "scripts/adsorption/role_force_trainer.py",
                    ROOT / "scripts/adsorption/direct_training_arm.py", ROOT / "scripts/adsorption/direct_force_training.py"]
    facts = {"document_kind": "force536_configuration_weight_budget_audit_evidence", "status": "READ_ONLY_AUDIT_FACTS",
             "train": summarize(rows), "development": summarize(development),
             "hypothetical_weight_sensitivity": sampling_sensitivity(rows), "budget_probes": budget_probes(request, config),
             "historical_pretrained_initializer": request["base_checkpoint"],
             "historical_two_epoch512": {"checkpoint_sha256": historical_rows["candidate_sha256"],
                                          "producer_elapsed_seconds": seconds, "native_iterations": 1024,
                                          "all_AMP_updates_independently_counted": False},
             "historical_partial512": {"checkpoint_sha256": scratch["candidates"]["finetune_best"]["sha256"],
                                        "last_saved": scratch["finetune_last_saved_metadata_not_final_iteration"],
                                        "controller_elapsed_seconds": scratch["recorded_seconds"]["finetune_controller"]},
             "new_two_epoch_native_iterations": 1072, "new_twenty_epoch_native_iterations": 10720,
             "two_epoch_expected_distinct_new24_seen": 24 * (1 - (1 - 1 / 536) ** 1072),
             "historical_configuration": {k: config[k] for k in ("model", "optim", "loss_functions", "evaluation_metrics")},
             "normalizers": {k: v["transforms"]["normalizer"] for k, v in config["dataset"].items()},
             "trainable_parameter_receipt_found": False, "fresh_GPU_check_run": False,
             "fresh_remote_pretrained_hash_check_run": False, "heldout_forces_used_for_weight_selection": False,
             "new_inference_or_training": False, "source_files": source_file_manifest(dependencies)}
    after = frozen_hashes()
    if before != after:
        raise ValueError("frozen package changed during audit")
    facts["frozen_packages_unchanged"] = True
    facts["frozen_hashes_before_after"] = before
    save_once(OUTPUT / "audit_facts.json", facts)
    return facts


if __name__ == "__main__":
    result = run()
    print({"status": result["status"], "budget_probes": result["budget_probes"],
           "hypothetical_weight_sensitivity": result["hypothetical_weight_sensitivity"]})
