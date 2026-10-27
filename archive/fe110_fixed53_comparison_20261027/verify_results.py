"""Independent scalar arithmetic and frozen-source audit;never runs inference."""
from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .prepare import MODELS, OUTPUT, PACKAGE


def check_splits(splits):
    if {k: len(v) for k, v in splits.items()} != {"train": 512, "development": 78, "heldout": 53}:
        raise ValueError("split sizes changed")
    for field in ("sample_id", "calculation_group", "structure_sha256", "structure_equivalence_sha256"):
        sets = {k: {r[field] for r in rows} for k, rows in splits.items()}
        if sets["heldout"] & (sets["train"] | sets["development"]) or sets["train"] & sets["development"]:
            raise ValueError("split leakage: " + field)
    return splits["heldout"]


def group_specs(analysis, rows):
    group_specs = [("all53", rows, analysis["all53"])]
    for dimension in ("source_collection", "composition", "calculation_group", "force_bin"):
        for key, summary in analysis["dimensions"][dimension].items():
            selected = [r for r, f in zip(rows, analysis["frames"], strict=True) if (f[dimension] if dimension == "force_bin" else r[dimension]) == key]
            group_specs.append((dimension + ":" + key, selected, summary))
    return group_specs


def scalar_errors(rows, predictions, role):
    squared, count, abs_sum = 0.0, 0, 0.0
    for row in rows:
        predicted = predictions[row["sample_id"]]
        if predicted["structure_sha256"] != row["structure_sha256"]:
            raise ValueError("geometry-force mismatch")
        fixed = set(row["fixed_atom_indices_0based"])
        for i, symbol in enumerate(row["symbols"]):
            if i in fixed:
                continue
            include = (role == "movable" or (role == "adsorbate" and symbol != "Fe") or symbol == role
                or (role in ("near_Fe", "other_Fe") and i in row["force_role_groups"][role]))
            if include:
                differences = [p - d for p, d in zip(predicted["predicted_forces_eV_per_A"][i], row["forces_eV_per_A"][i], strict=True)]
                squared += sum(d * d for d in differences)
                abs_sum += sum(abs(d) for d in differences)
                count += 1
    return squared, count, abs_sum


def check_aggregates(raw, request, groups):
    checked = 0
    for model, checkpoint in MODELS.items():
        samples = raw["predictions"][model]["samples"]
        if raw["predictions"][model]["checkpoint_sha256"] != checkpoint["sha256"] or [r["sample_id"] for r in samples] != request["sample_ids"]:
            raise ValueError("model/sample mismatch")
        by_id = {r["sample_id"]: r for r in samples}
        for label, selected, summary in groups:
            if not selected:
                if summary["coverage"] != "NO_TEST_COVERAGE":
                    raise ValueError("empty coverage misrepresented")
                continue
            for role in summary["models"][model]:
                squared, count, abs_sum = scalar_errors(selected, by_id, role)
                actual = summary["models"][model][role]
                if actual["atom_count"] != count:
                    raise ValueError("atom aggregation mismatch")
                if count:
                    if not math.isclose(math.sqrt(squared / count), actual["vector_rmse_eV_A"], rel_tol=1e-12, abs_tol=1e-14):
                        raise ValueError("independent RMSE mismatch: " + label + ":" + role)
                    if not math.isclose(abs_sum / (3 * count), actual["component_mae_eV_A"], rel_tol=1e-12, abs_tol=1e-14):
                        raise ValueError("independent componentMAE mismatch")
                    checked += 2
                elif actual["vector_rmse_eV_A"] is not None:
                    raise ValueError("absent role reported numerical error")
    return checked


def verify_results():
    analysis = load_json_object(OUTPUT / "analysis.json")
    request = load_json_object(PACKAGE / "request.json")
    manifest = load_json_object(PACKAGE / "data/training_manifest.json")
    raw = load_json_object(OUTPUT / "result.stdout")
    for source in analysis["source_files"]:
        if sha256_file(Path(source["path"])) != source["sha256"]:
            raise ValueError("analysis source hash changed")
    rows = check_splits(manifest["splits"])
    checked = check_aggregates(raw, request, group_specs(analysis, rows))
    # Reproduces prior published46-frame results without rerunning or reselecting anything.
    historical = analysis["dimensions"]["source_collection"]["legacy_control_20261019"]["models"]
    for model, target in [("baseline", 0.200850), ("control", 0.062348)]:
        if abs(historical[model]["adsorbate"]["vector_rmse_eV_A"] - target) > 0.0000005:
            raise ValueError("prior46 comparison did not reproduce")
    suite = ET.parse(OUTPUT / "primary_tests_final.xml").getroot().find("testsuite")
    if any(int(suite.attrib[k]) for k in ("errors", "failures", "skipped")):
        raise ValueError("related tests not fully passed")
    output = {"status": "PASS_FIXED53_INDEPENDENT_ARITHMETIC_AND_SPLIT_AUDIT", "checked_scalar_metrics": checked,
        "frame_count": 53, "prediction_count": 159, "composition_counts": dict(Counter(r["composition"] for r in rows)),
        "source_counts": dict(Counter(r["source_collection"] for r in rows)),
        "prior46_baseline_and_control_reproduced_to_6dp": True, "split_field_intersections_empty": True,
        "related_tests_passed": int(suite.attrib["tests"]),
        "not_proven": ["optimization_speedup", "C3H2O_low_force_accuracy", "adsorption_energy_accuracy", "statistical_generalization"],
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "analysis.json", OUTPUT / "primary_tests_final.xml", OUTPUT / "result.stdout", PACKAGE / "request.json", PACKAGE / "data/training_manifest.json"])}
    write_json_exclusive(OUTPUT / "independent_verification_v2.json", output)
    print({k: v for k, v in output.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    verify_results()
