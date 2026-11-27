"""Training-only composition/contact/force diagnostics, with no selection authority."""
from __future__ import annotations

from collections import Counter, defaultdict

from scripts.adsorption.reico_environment_audit import frame_scores, nearest, stack
from scripts.adsorption.reico_force_coverage import force_histogram


def require_training(rows):
    if any(row.get("partition") != "train" for row in rows):
        raise ValueError("joint coverage accepts training records only")
    if len({row["sample_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate training sample")


def joint_force_table(rows, edges):
    """Empty bins are observations, not a demand to fill every graph/bin product."""
    require_training(rows)
    result = {}
    for composition in sorted({r["composition"] for r in rows}):
        subset = [r for r in rows if r["composition"] == composition]
        strata = defaultdict(list)
        for row in subset:
            strata[row["joint_signature"]].append(row)

        def summarize(group):
            values = [r["movable_fmax_eV_A"] for r in group]
            low = [r for r in group if r["movable_fmax_eV_A"] <= .05]
            return {"frames": len(group), "source_groups": len({r["source_group"] for r in group}),
                    "fmax_range_eV_A": [min(values), max(values)],
                    "fmax_histogram": force_histogram(values, edges),
                    "low_force_le_0p05": len(low),
                    "low_force_source_groups": sorted({r["source_group"] for r in low}),
                    "low_force_graphs": len({r["graph_signature"] for r in low}),
                    "low_force_joint_strata": len({r["joint_signature"] for r in low}),
                    "connected_low_force_frames": sum(r["adsorbate_component_count"] == 1 for r in low),
                    "magnetic_review_levels": dict(Counter(r["magnetic_review_level"] for r in group)),
                    "sample_ids": [r["sample_id"] for r in group]}

        result[composition] = {**summarize(subset),
                               "graphs": len({r["graph_signature"] for r in subset}),
                               "joint_strata": len(strata),
                               "strata": [{"joint_signature": key, **summarize(group)}
                                          for key, group in sorted(strata.items())]}
    return result


def fixed_threshold_soap(pool, references, prior_report):
    """Keep the original per-composition thresholds fixed when changing references."""
    require_training(pool)
    require_training(references)
    scores, report = [], {}
    for composition in sorted({r["composition"] for r in pool}):
        queries = [r for r in pool if r["composition"] == composition]
        ref = [r for r in references if r["composition"] == composition]
        if not ref:
            raise ValueError("missing composition reference")
        thresholds = prior_report[composition]["thresholds"]
        current = frame_scores(queries, stack(queries), nearest(stack(queries), stack(ref)), thresholds)
        scores.extend(current)
        report[composition] = {"pool_frames": len(queries), "reference_frames": len(ref),
                               "fixed_thresholds": thresholds,
                               "above_internal_threshold": sum(r["exceeds_internal_threshold"] for r in current),
                               "maximum_ratio": max(r["novelty_ratio"] for r in current)}
    return report, scores


def missing_environment_groups(pool, training, original_selected_ids):
    """Separate unlabeled geometric evidence from observed DFT force coverage."""
    require_training(pool)
    require_training(training)
    train_ids = {r["sample_id"] for r in training}
    reports, missing = {}, []
    for composition in sorted({r["composition"] for r in pool}):
        subset = [r for r in pool if r["composition"] == composition]
        refs = [r for r in training if r["composition"] == composition]
        selected = [r for r in subset if r["sample_id"] in original_selected_ids]
        dimensions = {}
        for key in ("graph_signature", "coordination_signature", "joint_signature"):
            target = {r[key] for r in subset}
            current = {r[key] for r in refs}
            original = {r[key] for r in selected}
            dimensions[key] = {"pool_types": len(target), "original233_covered": len(target & original),
                               "current366_covered": len(target & current),
                               "current_missing": len(target-current),
                               "missing_if_all_original_selected_labels_admitted": len(target-(current | original))}
        ref_scales = {s: {r["joint_by_scale"][s] for r in refs} for s in subset[0]["joint_by_scale"]}
        groups = defaultdict(list)
        for row in subset:
            if row["joint_signature"] not in {r["joint_signature"] for r in refs}:
                groups[row["joint_signature"]].append(row)
        for signature, group in groups.items():
            robust = [r for r in group if all(r["joint_by_scale"][s] not in ref_scales[s] for s in ref_scales)]
            # Prefer a cutoff-robust example, then the largest SOAP distance.
            representative = min(robust or group, key=lambda r: (-r["novelty_ratio"], r["sample_id"]))
            selected_members = [r["sample_id"] for r in group if r["sample_id"] in original_selected_ids-train_ids]
            missing.append({"composition": composition, "joint_signature": signature,
                            "pool_frames": len(group), "pool_families": len({r["family_id"] for r in group}),
                            "robust_missing_frames_all_scales": len(robust),
                            "original_selected_labels_not_in_package": selected_members,
                            "representative_id": representative["sample_id"],
                            "representative_SOAP_ratio": representative["novelty_ratio"],
                            "representative_exceeds_SOAP_threshold": representative["exceeds_internal_threshold"],
                            "sample_ids": [r["sample_id"] for r in group],
                            "DFT_force_of_missing_frames": "UNKNOWN_NOT_INFERRED_FROM_NEIGHBORS",
                            "reserved_isolation": "NOT_CHECKED_NOT_DFT_READY",
                            "next_action": "REVIEW_EXISTING_SELECTED_LABELS" if selected_members else "GEOMETRY_ONLY_CANDIDATE_NO_DFT_DECISION"})
        reports[composition] = dimensions
    return reports, sorted(missing, key=lambda r: (not bool(r["original_selected_labels_not_in_package"]),
                                                  -r["robust_missing_frames_all_scales"], -r["pool_families"],
                                                  -r["pool_frames"], -r["representative_SOAP_ratio"], r["representative_id"]))
