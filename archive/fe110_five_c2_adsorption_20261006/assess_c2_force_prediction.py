"""Assess frozen adsorption-force predictions without training or global promotion."""

import csv
import json

import numpy as np
import yaml

from archive.fe110_five_c2_adsorption_20261006.c2_force_gpu import EVIDENCE, PACKAGE, ROOT, SOURCE
from scripts.aqcat25_calibration import calibrate
from scripts.artifact_io import sha256_file, write_json


def metrics(delta):
    norms = np.linalg.norm(delta, axis=1)
    return {
        "atom_vectors": len(delta),
        "component_mae_eV_per_A": float(np.mean(np.abs(delta))),
        "vector_rmse_eV_per_A": float(np.sqrt(np.mean(norms**2))),
        "vector_p95_eV_per_A": float(np.percentile(norms, 95)),
        "vector_max_eV_per_A": float(norms.max()),
    }


def review_local_residuals():
    result = json.loads((EVIDENCE / "force_error_assessment.json").read_text())
    target = EVIDENCE / "local_residual_review.json"
    assert not target.exists(), "Preserve completed diagnostic interpretation"
    write_json(
        target,
        {
            "assessment_sha256": sha256_file(EVIDENCE / "force_error_assessment.json"),
            "overall_reference_checks": result["all_movable_threshold_checks"],
            "interpretation": "Aggregate passes reference thresholds, but Fe dominates atom count. Adsorbate RMSE is 0.265 initial/0.185 final; final oxygen RMSE is 0.332 eV/A on only two O atoms. These are localized residual warnings, not a new hard calibration gate.",
            "recommendation": "Prepare a C/O-focused adsorption fine-tuning candidate only after completing species03 coverage and freezing disjoint validation structures; retain adsorption replay and validate against the unchanged checkpoint. Do not claim guaranteed acceleration or start training automatically.",
            "global_calibration_modified": False,
            "hard_thresholds_modified": False,
            "independent_generalization_test_completed": False,
            "training_submitted": False,
        },
    )


def main():
    receipt = json.loads((EVIDENCE / "producer_exit_record.json").read_text())
    batch = json.loads((PACKAGE / "batch_manifest.json").read_text())
    assert receipt["gpu_job_id"] == "2177" and receipt["exit_code"] == 0
    assert receipt["source_batch_sha256"] == sha256_file(PACKAGE / "batch_manifest.json")
    assert receipt["checkpoint_sha256"] == batch["checkpoint_sha256"]
    prediction_path = EVIDENCE / "predictions.returned.json"
    assert receipt["predictions_sha256"] == sha256_file(prediction_path)
    labels = json.loads((SOURCE / "labels.json").read_text())
    predictions = json.loads(prediction_path.read_text())
    plan = json.loads((SOURCE / "assessment_plan.json").read_text())
    assert sha256_file(SOURCE / "labels.json") == plan["labels_sha256"]
    assert predictions["checkpoint_sha256"] == plan["checkpoint_sha256"]
    assert predictions["calibration_id"] == labels["calibration_id"]
    ids = [p["sample_id"] for p in predictions["samples"]]
    assert len(ids) == len(set(ids)) == 10
    assert set(ids) == {s["sample_id"] for s in labels["samples"]}
    by_id = {p["sample_id"]: p for p in predictions["samples"]}
    buckets, rows = {}, []
    for label in labels["samples"]:
        prediction = by_id[label["sample_id"]]
        assert prediction["structure_sha256"] == label["structure_sha256"]
        assert sha256_file(SOURCE / "structures" / (label["sample_id"] + ".vasp")) == label["structure_sha256"]
        reference = np.asarray(label["forces_eV_per_A"], dtype=float)
        inferred = np.asarray(prediction["forces_eV_per_A"], dtype=float)
        assert reference.shape == inferred.shape == (len(label["symbols"]), 3)
        assert np.isfinite(reference).all() and np.isfinite(inferred).all()
        fixed = set(label["fixed_atom_indices_1based"])
        for index, symbol in enumerate(label["symbols"]):
            if index + 1 in fixed:
                continue
            delta = inferred[index] - reference[index]
            group = "movable_Fe" if symbol == "Fe" else "adsorbate"
            for stage in ("all", label["label_stage"]):
                for kind in ("all_movable", group, "element_" + symbol):
                    buckets.setdefault(stage + "/" + kind, []).append(delta)
            row = {
                "sample_id": label["sample_id"],
                "label_stage": label["label_stage"],
                "atom_index_0based": index,
                "element": symbol,
                "group": group,
                "error_vector_norm_eV_per_A": float(np.linalg.norm(delta)),
            }
            for axis, number in zip("xyz", range(3)):
                row["VASP_F" + axis + "_eV_per_A"] = float(reference[index, number])
                row["AQCat_F" + axis + "_eV_per_A"] = float(inferred[index, number])
                row["delta_F" + axis + "_eV_per_A"] = float(delta[number])
            rows.append(row)
    gate_path = ROOT / "configs/aqcat25_domain_gate.yaml"
    gate = yaml.safe_load(gate_path.read_text())
    canonical = calibrate(labels, predictions, gate)
    write_json(EVIDENCE / "canonical_calibration_diagnostic.json", canonical)
    grouped = {key: metrics(np.asarray(values)) for key, values in buckets.items()}
    with (EVIDENCE / "per_atom_force_errors.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = {
        "status": "EXACT_STRUCTURE_FORCE_DIAGNOSTIC_COMPLETE",
        "checkpoint_sha256": predictions["checkpoint_sha256"],
        "labels_sha256": sha256_file(SOURCE / "labels.json"),
        "predictions_sha256": sha256_file(prediction_path),
        "force_gate_sha256": sha256_file(gate_path),
        "sample_count": 10,
        "groups": grouped,
        "reference_thresholds": canonical["thresholds"],
        "all_movable_threshold_checks": canonical["threshold_checks"],
        "global_scope_failures": canonical["scope_failures"],
        "scope_note": "C2-only correlated initial/final diagnostic; not independent held-out validation or global domain recalibration. No species03 CH-C-O coverage.",
        "decision": "PREPARE_LOCAL_FINETUNING_REVIEW"
        if not all(canonical["threshold_checks"].values())
        else "NO_FORCE_GATE_BASED_FINETUNING_TRIGGER",
        "fixed_atoms_excluded": list(range(18)),
        "training_submitted": False,
        "actual_speedup_measured": False,
    }
    write_json(EVIDENCE / "force_error_assessment.json", result)
    print(
        json.dumps(
            {"sample_count": 10, "groups": grouped, "threshold_checks": canonical["threshold_checks"], "decision": result["decision"]}
        )
    )


if __name__ == "__main__":
    main()
