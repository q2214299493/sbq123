"""Reviewed static energy relationships evaluated upstream of fixed-temperature MKM rates."""
import json
import math
from functools import lru_cache

import numpy as np
from jsonschema import Draft202012Validator, FormatChecker

from sbq123.common.artifacts.artifact_io import sha256_json
from sbq123.common.workflow.multiphase_contracts import ENERGY_ATOL_EV
from sbq123.common.workflow.runtime_resources import resource_path
from sbq123.common.validation.scientific_validation import validate_finite_tree

# Exact SI definitions of the elementary charge and Avogadro constant.
EV_PER_UNIT = {"eV": 1.0, "meV": 0.001, "kJ/mol": 1000 / (1.602176634e-19 * 6.02214076e23)}
ORDER = ("reaction", "forward", "reverse")


@lru_cache(maxsize=2)
def validator(suffix):
    path = resource_path(f"configs/kinetics/mkm_energy_prediction{suffix}.schema.json")
    return Draft202012Validator(json.loads(path.read_bytes()), format_checker=FormatChecker())


def covariance(values, size):
    matrix = np.asarray(values, dtype=float)
    if size == 0 and not matrix.size:
        return np.empty((0, 0))
    if matrix.shape != (size, size) or not np.isfinite(matrix).all():
        raise ValueError("Prediction covariance dimensions or entries invalid")
    if not np.array_equal(matrix, matrix.T) or (matrix.diagonal() < 0).any():
        raise ValueError("Prediction covariance must be symmetric with nonnegative variances")
    # Normalize scales before the PSD test so tiny, indefinite covariance cannot pass.
    scales = np.sqrt(matrix.diagonal())
    if np.any(matrix[scales == 0] != 0):
        raise ValueError("Nonzero covariance with a deterministic input")
    scales[scales == 0] = 1
    corr = matrix / scales[:, None] / scales
    if not np.isfinite(corr).all() or np.linalg.eigvalsh(corr).min() < -1e-12:
        raise ValueError("Prediction covariance is not positive semidefinite")
    return matrix


def fit_scope(fit, spec, reaction, param, sites, project):
    scope = fit["scope"]
    if (scope["family_id"] is None) == (scope["reaction_id"] is None):
        raise ValueError("Declare exactly one reaction or family scope per fit")
    for field in ("temperature_K", "pressure_Pa"):
        lo, hi = scope[field]
        if hi < lo or lo < 0 or (field == "temperature_K" and lo == 0):
            raise ValueError("Invalid fit condition interval")
        if not lo <= param[field] <= hi:
            return False
    applies = (scope["reaction_id"] == reaction["reaction_id"] if scope["reaction_id"] is not None
               else scope["family_id"] == spec["family_id"])
    return (scope["project_id"] == project and applies
            and set(scope["phase_ids"]) == set(reaction["phase_ids"])
            and set(scope["surface_ids"]) == set(reaction["surface_ids"])
            and scope["interface_id"] == reaction.get("interface_id") and set(scope["site_ids"]) == sites
            and fit["energy_basis"] == spec["energy_basis"]
            and fit["reference_id"] == param["energy_reference_id"]
            and fit["standard_state_id"] == param["standard_state_id"]
            and fit["standard_states_sha256"] == sha256_json(param["standard_states"]))


def validate_fit(fit, evidence):
    payload = {k: v for k, v in fit.items() if k not in ("model_version", "approval")}
    if fit["model_version"] != sha256_json(payload) or fit["approval"]["subject_sha256"] != fit["model_version"]:
        raise ValueError("Stale prediction model version or approval")
    if not {fit[k] for k in ("training_sha256", "validation_sha256", "fit_source_sha256")} <= evidence:
        raise ValueError("Unverified fit, training or validation evidence")
    axes = [a["id"] for a in fit["axes"]]
    if not {a["definition_sha256"] for a in fit["axes"]} <= evidence:
        raise ValueError("Unverified model axis definition")
    size = len(axes)
    if len(set(axes)) != size or ("reaction_energy" in axes) != (fit["kind"] == "bep"):
        raise ValueError("Invalid or repeated prediction axis")
    if fit["kind"] == "bep" and axes != ["reaction_energy"]:
        raise ValueError("BEP requires the single reaction energy axis")
    if len(fit["coefficients"]) != size + 1 or len(fit["bounds_eV"]) != size:
        raise ValueError("Prediction coefficient/domain dimensions disagree with axes")
    if any(lo > hi for lo, hi in fit["bounds_eV"]) or any(len(h["normal"]) != size for h in fit["halfspaces"]):
        raise ValueError("Invalid joint training domain")
    covariance(fit["covariance"], size + 1)


def select(fits, points, decisions, stage):
    matches = []
    for fit in fits:
        axes = fit["axes"]
        if any(a["id"] not in points or points[a["id"]][0] != a["definition_sha256"] for a in axes):
            decisions[fit["model_version"]] = "unavailable_axes"
            continue
        x = [points[a["id"]][1] for a in axes]
        inside = (all(lo <= v <= hi for v, (lo, hi) in zip(x, fit["bounds_eV"], strict=True))
                  and all(np.dot(h["normal"], x) <= h["upper_eV"] for h in fit["halfspaces"]))
        decisions[fit["model_version"]] = "selected" if inside else "outside_domain"
        if inside:
            matches.append((fit, x))
    if len(matches) != 1:
        raise ValueError(f"{stage}: expected one applicable model, found {len(matches)} (conflict, scope or extrapolation)")
    fit, x = matches[0]
    return fit, x, float(fit["coefficients"][0] + np.dot(fit["coefficients"][1:], x))


def input_points(spec, evidence):
    observations = spec["observations"]
    points, inputs, factors = {}, [], []
    for o in observations:
        key = o["id"]
        if key in points or o["source_sha256"] not in evidence or o["definition_sha256"] not in evidence:
            raise ValueError("Duplicate descriptor or unverified observation/definition")
        factor = EV_PER_UNIT[o["unit"]]
        value = o["value"] * factor
        factors.append(factor)
        points[key] = o["definition_sha256"], value
        inputs.append(dict(id=key, definition_sha256=o["definition_sha256"], value=value, source_sha256=o["source_sha256"]))
    if spec["reaction_axis_sha256"] not in evidence:
        raise ValueError("Unverified reaction energy convention")
    if spec["family_id"] is not None and spec["family_evidence_sha256"] not in evidence:
        raise ValueError("Unverified reaction-family membership evidence")
    return points, inputs, factors


def energy_chain(entry, spec, points, applicable, decisions):
    selected = []
    reaction_fits = [f for f in applicable if f["kind"] == "descriptor_reaction"]
    if spec["reaction_source"] == "descriptor":
        if "reaction_energy" in points:
            raise ValueError("Duplicate reaction energy producer")
        selected.append(select(reaction_fits, points, decisions, "reaction energy"))
        d = selected[-1][2]
        points["reaction_energy"] = spec["reaction_axis_sha256"], d
    else:
        if reaction_fits or points.get("reaction_energy", (None,))[0] != spec["reaction_axis_sha256"]:
            raise ValueError("Missing or conflicting reaction energy producer")
        d = points["reaction_energy"][1]
        measured = entry["energies"].get(spec["energy_basis"] + "_ev", {}).get("reaction")
        if measured is not None and abs(measured - d) > ENERGY_ATOL_EV:
            raise ValueError("Reaction energy observation conflicts with network evidence")
    selected.append(select([f for f in applicable if f["kind"] != "descriptor_reaction"], points, decisions, "forward barrier"))
    forward = selected[-1][2]
    used = {a["id"] for fit in spec["models"] for a in fit["axes"]}
    if spec["reaction_source"] == "observation":
        used.add("reaction_energy")
    if {o["id"] for o in spec["observations"]} - used:
        raise ValueError("Unused observation in reviewed descriptor vector")
    return selected, dict(reaction=d, forward=forward, reverse=forward-d)


def gibbs_energies(raw, spec, param, evidence):
    basis = spec["energy_basis"]
    bridge = spec["gibbs_bridge"]
    if basis == "gibbs":
        if bridge is not None:
            raise ValueError("Duplicate Gibbs correction")
    elif (not bridge or bridge["from_basis"] != basis or bridge["source_sha256"] not in evidence
          or any(bridge[k] != param[p] for k, p in (("temperature_K", "temperature_K"),
                  ("standard_state_id", "standard_state_id"), ("reference_id", "energy_reference_id")))):
        raise ValueError("Compatible reviewed Gibbs bridge required")
    g = dict(raw)
    if bridge:
        g.update(reaction=raw["reaction"]+bridge["reaction_eV"], forward=raw["forward"]+bridge["forward_eV"])
        g["reverse"] = g["forward"] - g["reaction"]
    if min(g["forward"], g["reverse"], raw["forward"], raw["reverse"]) < 0:
        raise ValueError("Negative predicted barrier; no qualified barrierless law")
    return g


def evaluate(entry, model, param, species, network, verified):
    spec = model["energy_prediction"]
    validator("").validate(spec)
    evidence = {s["sha256"] for s in model["sources"]} & verified
    fits = spec["models"]
    decisions = dict.fromkeys((f["model_version"] for f in fits), "outside_scope")
    if len(decisions) != len(fits):
        raise ValueError("Duplicate prediction candidate")
    if param["coverage_terms"] or model.get("coverage_fractions") or param["uncertainty"] is not None:
        raise ValueError("Prediction owns the barrier and uncertainty; duplicate corrections are unsupported")
    reaction = entry["definition"]
    if reaction.get("reversible") is not True:
        raise ValueError("Prediction requires a reviewed reversible step")
    sites = set().union(*(reaction.get(k) or {} for k in ("required_sites", "sites_consumed", "sites_released")))
    for sid in reaction["products"].keys() | reaction["reactants"].keys():
        sites.update(species[sid].get("site_occupancy") or {})
    for fit in fits:
        validate_fit(fit, evidence)
    applicable = [f for f in fits if fit_scope(f, spec, reaction, param, sites, network["project_id"])]
    points, inputs, factors = input_points(spec, evidence)
    selected, raw = energy_chain(entry, spec, points, applicable, decisions)
    g = gibbs_energies(raw, spec, param, evidence)
    bridge = spec["gibbs_bridge"]
    matrix = propagate(spec, selected, factors)
    trace = dict(format="mkm-energy-prediction-result/1", provenance="model_prediction",
                 qualification="reviewed_mkm_prediction", network_version=network["network_version"], reaction_id=reaction["reaction_id"],
                 binding_sha256=sha256_json(spec), review_sha256=model["scientific_review"]["subject_sha256"],
                 energy_basis=spec["energy_basis"], reference_id=param["energy_reference_id"], standard_state_id=param["standard_state_id"],
                 temperature_K=param["temperature_K"], pressure_Pa=param["pressure_Pa"], inputs_eV=inputs,
                 selected=[dict(**{k: f[k] for k in ("model_id", "model_version", "kind", "training_sha256",
                                                       "validation_sha256", "fit_source_sha256")},
                                axis_values_eV=x, output_eV=y) for f, x, y in selected],
                 candidate_decisions=[dict(model_id=f["model_id"], model_version=f["model_version"],
                                           outcome=decisions[f["model_version"]]) for f in fits],
                 basis_energies_eV=raw, gibbs_eV=g, uncertainty_order=list(ORDER), covariance_eV2=matrix.tolist(),
                 sigma_eV={k: math.sqrt(max(0.0, matrix[i, i])) for i, k in enumerate(ORDER)},
                 uncertainty_method="first_order_joint_covariance", bridge_source_sha256=bridge["source_sha256"] if bridge else None)
    validate_finite_tree(trace)
    validator("_result").validate(trace)
    return trace


def propagate(spec, selected, factors):
    """Propagate shared input, fit, intrinsic residual and bridge errors with one joint Jacobian."""
    obs = spec["observations"]
    scales = np.array(factors)
    blocks = [([f"x:{o['id']}" for o in obs],
               covariance(spec["observation_covariance"], len(obs)) * scales[:, None] * scales)]
    for fit, x, _ in selected:
        prefix = fit["model_version"]
        labels = [f"{prefix}:b{i}" for i in range(len(x) + 1)]
        blocks.append((labels, covariance(fit["covariance"], len(labels))))
        blocks.append(([f"{prefix}:residual"], [[fit["residual_sigma_eV"] ** 2]]))
    if spec["gibbs_bridge"]:
        blocks.append((["bridge:reaction", "bridge:forward"], covariance(spec["gibbs_bridge"]["covariance_eV2"], 2)))
    labels = [name for names, _ in blocks for name in names]
    indices = {name: i for i, name in enumerate(labels)}
    size = len(labels)
    joint = np.zeros((size, size))
    offset = 0
    owners = {}
    for group, values in blocks:
        end = offset + len(group)
        joint[offset:end, offset:end] = values
        owners.update(dict.fromkeys(group, offset))
        offset = end
    seen = set()
    for cross in spec["cross_covariances"]:
        a, b = cross["left"], cross["right"]
        pair = frozenset((a, b))
        if a not in indices or b not in indices or owners[a] == owners[b] or pair in seen:
            raise ValueError("Invalid cross-block covariance labels")
        seen.add(pair)
        joint[indices[a], indices[b]] = joint[indices[b], indices[a]] = cross["value"]
    covariance(joint, size)
    identity = np.eye(size)
    gradients = {o["id"]: identity[indices["x:"+o["id"]]] for o in obs}
    for fit, x, _ in selected:
        prefix = fit["model_version"]
        grad = identity[indices[prefix+":residual"]].copy()
        for i, value in enumerate([1., *x]):
            grad[indices[f"{prefix}:b{i}"]] += value
        for axis, slope in zip(fit["axes"], fit["coefficients"][1:], strict=True):
            grad += slope * gradients[axis["id"]]
        if fit["kind"] == "descriptor_reaction":
            gradients["reaction_energy"] = grad
    reaction = gradients["reaction_energy"]
    if spec["gibbs_bridge"]:
        reaction = reaction + identity[indices["bridge:reaction"]]
        grad = grad + identity[indices["bridge:forward"]]
    jac = np.array([reaction, grad, grad - reaction])
    return jac @ joint @ jac.T
