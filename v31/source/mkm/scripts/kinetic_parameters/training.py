"""Fit and compare review candidates for the existing MKM energy-prediction/1 evaluator."""

import argparse
import math
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator

from scripts.artifact_io import canonical_json, require_sha256, sha256_json, write_json_exclusive
from scripts.kinetic_parameters.prediction import validator
from scripts.multiphase_contracts import read_unique_json
from scripts.scientific_validation import finite_number, validate_finite_tree


def sample_arrays(rows, axes):
    x = [[finite_number(row["descriptors_eV"][axis], axis) for axis in axes] for row in rows]
    y = [finite_number(row["target_eV"], "target energy") for row in rows]
    return np.asarray(x), np.asarray(y)


def applicability(x, xv):
    limits = np.column_stack((x.min(axis=0), x.max(axis=0)))
    inside = ((xv >= limits[:, 0]) & (xv <= limits[:, 1])).all(axis=1)
    planes = []
    if x.shape[1] > 1:
        from scipy.spatial import ConvexHull

        for equation in ConvexHull(x).equations:
            normal = equation[:-1]
            upper = np.nextafter(max(-equation[-1], (x @ normal).max()), np.inf)
            planes.append(dict(normal=normal.tolist(), upper_eV=float(upper)))
            inside &= xv @ normal <= upper
    return limits, planes, inside


def training_rows(rows, candidate):
    if "training_ids" not in candidate:
        return rows
    ids = candidate["training_ids"]
    if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
        raise ValueError("Expected distinct candidate training IDs")
    wanted = set(ids)
    selected = [r for r in rows if r["sample_id"] in wanted]
    if len(selected) != len(ids):
        raise ValueError("Unknown candidate training ID")
    return selected


def fit_candidate(request, candidate, context_hash):
    common, target = request["context"], request["target"]
    training, validation = training_rows(request["training"], candidate), request["validation"]
    axes = candidate["axes"]
    kind = candidate["kind"]
    if (
        not axes
        or len(set(axes)) != len(axes)
        or (kind == "bep" and axes != ["reaction_energy"])
        or (kind != "bep" and "reaction_energy" in axes)
        or (kind == "descriptor_reaction") != (target == "reaction_energy")
    ):
        raise ValueError("Model axes or target disagree with prediction kind")
    x, y = sample_arrays(training, axes)
    xv, yv = sample_arrays(validation, axes)
    design = np.column_stack((np.ones(len(x)), x))
    u, singular, vt = np.linalg.svd(design, full_matrices=False)
    if len(x) <= design.shape[1] or singular[-1] <= np.finfo(float).eps * max(design.shape) * singular[0]:
        raise ValueError("Training design lacks independent parameters or residual degrees of freedom")
    inv = vt.T / singular
    beta = inv @ (u.T @ y)
    residual = y - design @ beta
    variance = float(residual @ residual / (len(y) - len(beta)))
    limits, planes, inside = applicability(x, xv)
    errors = beta[0] + xv @ beta[1:] - yv
    metric = float(np.sqrt(np.mean(errors**2))) if inside.all() else None
    evidence = dict(
        method="ols_svd/1",
        target=target,
        model_id=candidate["model_id"],
        axes=axes,
        context_sha256=context_hash,
        training_sha256=sha256_json(training),
        validation_sha256=sha256_json(validation),
        metric_role="model_selection_validation",
        held_out_rmse_eV=metric,
        outside_domain=[r["sample_id"] for r, ok in zip(validation, inside, strict=True) if not ok],
    )
    fit = dict(
        common,
        model_id=candidate["model_id"],
        kind=kind,
        axes=[dict(id=a, definition_sha256=request["descriptor_definitions"][a]) for a in axes],
        coefficients=beta.tolist(),
        covariance=(variance * (inv @ inv.T)).tolist(),
        bounds_eV=limits.tolist(),
        halfspaces=planes,
        residual_sigma_eV=math.sqrt(variance),
        training_sha256=evidence["training_sha256"],
        validation_sha256=evidence["validation_sha256"],
        fit_source_sha256=sha256_json(evidence),
    )
    validate_finite_tree(evidence)
    validate_finite_tree(fit)
    fit["model_version"] = sha256_json(fit)
    # Validate the unsigned candidate against the same fields consumed at prediction time.
    defs = validator("").schema["$defs"]
    shape = dict(defs["fit"], required=[k for k in defs["fit"]["required"] if k != "approval"])
    Draft202012Validator(dict(shape, **{"$defs": defs})).validate(fit)
    scope = fit["scope"]
    if any(lo > hi for lo, hi in (scope["temperature_K"], scope["pressure_Pa"])):
        raise ValueError("Invalid applicability interval")
    if (scope["reaction_id"] is None) == (scope["family_id"] is None) or "approval" in fit:
        raise ValueError("Fit requires one declared scope and independent review")
    return dict(fit=fit, evidence=evidence)


def check_splits(partitions):
    """An unlocated source denotes one observation; shared containers need observation-level evidence."""
    prior_ids, prior_cases, prior_observations = set(), set(), set()
    prior_sources = {}
    for rows in partitions:
        ids, cases, observations, sources = set(), set(), set(), {}
        for row in rows:
            sid = row["sample_id"]
            if not isinstance(sid, str) or not sid.strip() or sid in ids or sid in prior_ids:
                raise ValueError("Require distinct sample IDs across all splits")
            ids.add(sid)
            source = require_sha256(row["source_sha256"], label="sample provenance")
            case = row.get("case_id")
            if case is not None:
                if not isinstance(case, str) or not case.strip() or case != case.strip():
                    raise ValueError("Invalid case_id")
                cases.add(case)
            located = "observation_sha256" in row
            obs = require_sha256(row["observation_sha256"], label="observation") if located else source
            if located and (case is None or obs == source):
                raise ValueError("Located observations require case_id and a distinct observation digest")
            observations.add(obs)
            sources[source] = sources.get(source, True) and located
        if cases & prior_cases or observations & prior_observations:
            raise ValueError("Case or source observation occurs in multiple splits")
        if any(not (sources[k] and prior_sources[k]) for k in sources.keys() & prior_sources.keys()):
            raise ValueError("Shared source requires located observations in every split")
        prior_ids.update(ids)
        prior_cases.update(cases)
        prior_observations.update(observations)
        for k, located in sources.items():
            prior_sources[k] = prior_sources.get(k, True) and located


def evaluate_selected(fit, rows):
    axes = [axis["id"] for axis in fit["axes"]]
    x, y = sample_arrays(rows, axes)
    inside = np.ones(len(rows), dtype=bool)
    for col, (lo, hi) in enumerate(fit["bounds_eV"]):
        inside &= (x[:, col] >= lo) & (x[:, col] <= hi)
    for plane in fit["halfspaces"]:
        inside &= x @ plane["normal"] <= plane["upper_eV"]
    beta = fit["coefficients"]
    errors = beta[0] + x @ beta[1:] - y
    return dict(model_version=fit["model_version"], evaluation_sha256=sha256_json(rows),
                rmse_eV=float(np.sqrt(np.mean(errors**2))) if inside.all() else None,
                outside_domain=[row["sample_id"] for row, ok in zip(rows, inside, strict=True) if not ok])


def train(request):
    """OLS with external held-out cases. All energies are eV per forward event."""
    common = request["context"]
    target = request["target"]
    if target not in ("forward_barrier", "reaction_energy"):
        raise ValueError("Unknown energy target")
    training, validation = (request[k] for k in ("training", "validation"))
    evaluation = request.get("evaluation", [])
    if not training or not validation or ("evaluation" in request and not evaluation):
        raise ValueError("Require nonempty data for each supplied split")
    check_splits((training, validation, evaluation))
    context_hash = sha256_json(dict(common, target=target, descriptor_definitions=request["descriptor_definitions"]))
    if any(r["context_sha256"] != context_hash for r in training + validation + evaluation):
        raise ValueError("Mixed energy, descriptor, scope or standard-state context")
    products = [fit_candidate(request, c, context_hash) for c in request["candidates"]]
    names = {p["fit"]["model_id"] for p in products}
    if not names or len(names) != len(products):
        raise ValueError("Distinct candidate model IDs required")
    scores = {p["fit"]["model_id"]: p["evidence"]["held_out_rmse_eV"] for p in products if p["evidence"]["held_out_rmse_eV"] is not None}
    best = [k for k, v in scores.items() if math.isclose(v, min(scores.values()), rel_tol=1e-10, abs_tol=1e-12)]
    independent = None
    if len(best) == 1 and evaluation:
        fit = next(p["fit"] for p in products if p["fit"]["model_id"] == best[0])
        independent = evaluate_selected(fit, evaluation)
        validate_finite_tree(independent)
    return dict(
        independent_evaluation=independent,
        format="mkm-fit-comparison/1",
        recommendation=best[0] if len(best) == 1 else None,
        candidates=products,
        request_sha256=sha256_json(request),
        review_required=True,
    )


def publish_evidence(folder, request, comparison):
    """Store exactly the bytes whose hashes the prediction evidence checker consumes."""
    folder.mkdir(parents=True, exist_ok=True)
    records = [request["validation"]]
    if "evaluation" in request:
        records.append(request["evaluation"])
    for candidate, product in zip(request["candidates"], comparison["candidates"], strict=True):
        records.extend((training_rows(request["training"], candidate), product["evidence"]))
    for record in records:
        data = canonical_json(record)
        path = folder / (sha256_json(record) + ".json")
        try:
            with path.open("xb") as stream:
                stream.write(data)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError(f"Existing calibration evidence differs: {path}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("request", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--evidence-dir", type=Path, help="Publish canonical training, holdout and fit evidence bytes")
    args = p.parse_args()
    request = read_unique_json(args.request)
    result = train(request)
    if args.evidence_dir:
        publish_evidence(args.evidence_dir, request, result)
    write_json_exclusive(args.output, result)


if __name__ == "__main__":
    main()
