"""Objective-specific normalized scores and Pareto fronts for scientific proposals."""

from copy import deepcopy

from scripts.artifact_io import sha256_json
from scripts.scientific_validation import finite_number
from scripts.physical_constants import KB

from .evidence import OPERATIONS, digest, match_evidence, reliability
from .structure_binding import qualified_ranking_candidate, ranking_structure_context

DIMENSIONS = {
    "kinetic_importance",
    "product_relevance",
    "reliability_gap",
    "novelty",
    "evidence_deficiency",
    "information_value",
    "cost",
    "downstream_impact",
    "flux",
    "interface_site_types",
}
OBJECTIVES = {"overall_activity", "product_selectivity", "carbon_chain_selectivity", "phase_comparison", "interface_importance"}


def validate_objective(obj):
    scope = obj["scope"]
    if obj["kind"] not in OBJECTIVES or not obj["id"] or not obj["observable"] or not obj["weights"]:
        raise ValueError("Explicit objective, observable and weight configuration required")
    if not all(scope.get(k) for k in ("network_version", "dataset_version", "baseline_result_sha256", "normalization")):
        raise ValueError("Bind baseline, model and observable normalization")
    finite_number(scope["temperature_K"], "temperature", positive=True)
    if not scope["feed_bar"]:
        raise ValueError("Operating feed required")
    for v in scope["feed_bar"].values():
        finite_number(v, "pressure", nonnegative=True)
    if obj["kind"] in ("product_selectivity", "carbon_chain_selectivity", "phase_comparison") and not obj.get("target"):
        raise ValueError("An explicit product, carbon range or phase contrast is required")
    if not set(obj.get("critical", [])) <= DIMENSIONS:
        raise ValueError("Unrecognized critical dimension")
    for k, w in obj["weights"].items():
        if k not in DIMENSIONS:
            raise ValueError("Unknown ranking dimension: " + k)
        finite_number(w, "objective weight", positive=True)
        finite_number(obj["scales"][k], "normalization scale", positive=True)


def importance(candidate, metrics, objective):
    rows = [
        m
        for m in metrics
        if m["parameter"] == candidate["parameter"]
        and m["parameter_type"] == candidate["parameter_type"]
        and m["observable"] == objective["observable"]
        and m["scope"] == objective["scope"]
        and m["status"] == "accepted"
        and m.get("target") == objective.get("target")
        and (objective["kind"] == "interface_importance" or m["observable_kind"] == objective["kind"])
        and m["kind"] in ("ts_drc", "intermediate_G", "selectivity_sensitivity")
        and m.get("source")
    ]
    if len(rows) > 1:
        raise ValueError("Multiple applicable sensitivity records require explicit selection")
    if rows:
        finite_number(rows[0]["value"], "sensitivity")
    return rows[0] if rows else None


def information_value(metric, rel, candidate, scope):
    """Expected reduction of Bayes risk for a local log-observable under squared-error loss."""
    cal, experiment = rel["calibration"], candidate.get("information_model")
    if not metric or not cal or not experiment or metric.get("coordinate") != "G_over_kBT":
        return None
    if experiment.get("loss") != "squared_log_observable" or not experiment.get("reference"):
        return None
    post = finite_number(experiment["expected_posterior_variance_eV2"], "expected posterior variance", nonnegative=True)
    prior = cal["prior_sd_eV"] ** 2
    if post > prior:
        raise ValueError("Expected posterior variance exceeds prior")
    return (metric["value"] / (KB * scope["temperature_K"])) ** 2 * (prior - post)


def blockers(c, data, obj, matches):
    reasons = list(c.get("blockers", []))
    if not c["protocol"]:
        reasons.append("Missing compatible scientific protocol")
    if c["scope"] != obj["scope"]:
        reasons.append("Candidate and objective have different operating or evidence scope")
    if not c["targets"] or not all(map(digest, c["targets"].values())):
        reasons.append("Missing target structure identity")
    unresolved = sorted(
        {r["calculation_id"] for t in c["targets"].values() for r in data.get("registry_hits", {}).get(t, [])}
        - set(c.get("reviewed_registry_ids", []))
    )
    if unresolved:
        reasons.append("Assess exact registry matches before proposing repeat work: " + ", ".join(unresolved))
    if data.get("inventory_source") not in data["sources"]:
        reasons.append("Existing evidence inventory unavailable")
    if c["need"] in ("saddle_refinement", "reaction_path") and not matches:
        strategy = c.get("strategy") or {}
        path = (c.get("path_quality") or {}).get("evidence", {})
        if path.get("PATH_QUALITY_STATUS") in ("UNDERRESOLVED_REACTION_COORDINATE", "ELECTRONIC_FAILURE"):
            reasons.append("Resolve existing NEB Agent path-quality failure first")
        if c["need"] == "reaction_path" and not {"IS", "FS"} <= c["targets"].keys():
            reasons.append("Mapped IS and FS structures required for a path")
        if c["need"] == "saddle_refinement" and "TS" not in c["targets"]:
            reasons.append("Saddle candidate required for refinement")
        if strategy.get("reaction_family") != c["reaction_family"] or strategy.get("automatic_submission") is not False:
            reasons.append("Unbound TS family or strategy")
        if strategy.get("status") != "NEEDS_GPU_PATH_OR_VASP_PATH_REVIEW" or not digest(strategy.get("source_sha256")):
            reasons.append("TS Strategy Engine review required")
    return reasons


def evaluate(c, data, obj):
    requirements = c.get("needs", [c["need"]])
    if not requirements or any(k not in OPERATIONS for k in requirements):
        raise ValueError("Unknown or empty evidence requirements")
    covered = {k: match_evidence(dict(c, need=k), data["evidence"], data.get("equivalences", [])) for k in requirements}
    needed = next((k for k in requirements if not covered[k]), requirements[-1])
    c = dict(c, need=needed)
    op = OPERATIONS[needed]
    matches = covered[needed]
    rel = reliability(c, data["reliability"])
    metric = importance(c, data["metrics"], obj) if c["scope"] == obj["scope"] else None
    value = information_value(metric, rel, c, obj["scope"])
    cost = c.get("cost_by_need", {}).get(needed) if len(requirements) > 1 else c.get("cost")
    if cost and (cost["unit"] != obj["cost_unit"] or cost.get("source") not in data["sources"]):
        cost = None
    context = c.get("objective_metrics", {}).get(obj["id"], {})
    structural = rel["structural_distance"] if rel.get("distance_definition") == obj.get("distance_definition") else None
    reliability_key = obj.get("reliability_metric")
    gap = rel["validation_errors"].get(reliability_key)
    if reliability_key == "calibrated_sd_eV" and rel["calibration"]:
        gap = rel["calibration"]["prior_sd_eV"]
    elif reliability_key == "ensemble_sd_eV":
        gap = rel["ensemble_sd_eV"]
    elif reliability_key == "extrapolation_grade":
        gap = obj.get("grade_scores", {}).get(rel["extrapolation_grade"])
    raw = dict(
        kinetic_importance=abs(metric["value"]) if metric else None,
        product_relevance=context.get("product_relevance"),
        downstream_impact=context.get("downstream_impact"),
        reliability_gap=gap,
        novelty=structural,
        evidence_deficiency=(0 if matches else 1) if data.get("inventory_source") else None,
        information_value=value,
        cost=cost["value"] if cost else None,
        flux=c.get("absolute_net_flux"),
        interface_site_types=len(c["site_context"]) if c.get("interface_id") and c.get("site_context") else None,
    )
    normalized = {}
    for k in obj["weights"]:
        v = raw[k]
        if v is not None:
            finite_number(v, k, nonnegative=True)
            scale = obj["scales"][k]
            normalized[k] = scale / (scale + v) if k == "cost" else min(v / scale, 1.0)
    weights = obj["weights"]
    subtotal = sum(weights[k] * v for k, v in normalized.items())
    missing = sorted(weights.keys() - normalized.keys())
    weight = sum(weights.values())
    bounds = [subtotal / weight, (subtotal + sum(weights[k] for k in missing)) / weight]
    reasons = blockers(c, data, obj, matches)
    reasons.extend("Missing " + k for k in sorted(set(missing) | {k for k in obj.get("critical", []) if raw[k] is None}))
    status = "reuse" if matches else "deferred" if reasons else "ranked"
    return dict(
        candidate=c,
        status=status,
        matching_evidence=matches,
        covered_requirements=covered,
        registry_evidence={t: data.get("registry_hits", {}).get(t, []) for t in c["targets"].values()},
        related_records=[r for r in data["evidence"] if set(r["targets"].values()) & set(c["targets"].values())],
        recommendation="reuse" if matches else op,
        sensitivity=metric,
        reliability=rel,
        cost=cost,
        expected_information_value=value,
        raw_metrics=raw,
        normalized_scores=normalized,
        missing_dimensions=missing,
        score_bounds=bounds,
        ranking_uncertainty="Bounds span unknown normalized dimensions at fixed weights; model/weight confidence interval unavailable",
        score=bounds[0] if status == "ranked" else None,
        reasons=reasons,
        rationale=f"Reviewed evidence covers {c['need']}" if matches else f"Acquire {c['need']} for {c['parameter']}",
        weighted_contributions={k: v * weights[k] / weight for k, v in normalized.items()},
    )


def pareto(rows):
    remaining = list(rows)
    front = 1
    while remaining:

        def dominates(a, b):
            x, y = a["normalized_scores"], b["normalized_scores"]
            return all(x[k] >= y[k] for k in x) and any(x[k] > y[k] for k in x)

        current = [r for r in remaining if not any(dominates(q, r) for q in remaining)]
        for r in current:
            r["pareto_front"] = front
            remaining.remove(r)
        front += 1


def rank(data, objective, *, observation_network=None):
    validate_objective(objective)
    for record in [*data["metrics"], *data["reliability"], *data["evidence"]]:
        if record.get("source") not in data["sources"]:
            raise ValueError("Unbound source for scientific evidence")
    if len({c["id"] for c in data["candidates"]}) != len(data["candidates"]):
        raise ValueError("Duplicate candidate identity")
    network, fixture = (observation_network, None) if observation_network is not None else ranking_structure_context(data, objective)
    checked = (qualified_ranking_candidate(c, network, fixture) for c in data["candidates"])
    rows = [evaluate(c, data, objective) for c in checked]
    rows.sort(key=lambda r: (-(r["score"] or 0), r["candidate"]["id"]))
    seen = {}
    for row in rows:
        c = row["candidate"]
        key = sha256_json(
            [
                c["need"],
                c["targets"],
                c["protocol"],
                c.get("model_version") if c["need"] in ("training_labels", "validation_set", "candidate_geometry") else None,
            ]
        )
        if row["status"] == "ranked":
            if key in seen:
                row.update(status="duplicate", score=None, reasons=["Same proposed operation as " + seen[key]])
            else:
                seen[key] = c["id"]
    ranked = [r for r in rows if r["status"] == "ranked"]
    pareto(ranked)
    return dict(
        format="scientific-priority/2",
        ranking_inputs=deepcopy(data),
        objective=objective,
        provenance=data["sources"],
        inventory_source=data.get("inventory_source"),
        context_evidence=data.get("context_evidence", []),
        ranked=ranked,
        deferred=[r for r in rows if r["status"] != "ranked"],
    )
