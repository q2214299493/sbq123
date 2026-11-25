"""Physical feedback at fixed gas activities; no integration or native execution."""

from itertools import combinations
import math

import numpy as np
from scipy.linalg import orth

from scripts.baseline_mkm import steady_states
from scripts.kinetic_parameters.laws import mean_field_rate
from scripts.thermochemistry.harmonic import KB


def fluxes(model, child, x, config):
    theta, vacancy = model.activities(x), model.check_x(x)
    pressure = {s: p * 1e5 for s, p in config["partial_pressure_bar"].items()}
    required = {gas for row in child["reactions"] for rate in row["rates"].values() for gas in rate["gas_orders"]}
    gases = {s for s, species in model.species.items() if species["phase"] == "gas"}
    if not required <= pressure.keys() <= gases:
        raise ValueError("Missing or unknown gas partial pressure in the feedback evaluation")
    flux = []
    for row in child["reactions"]:
        flux.append(
            [
                mean_field_rate(row, side, partial_pressures_pa=pressure, surface_activities=theta, vacancy_activities=vacancy)
                for side in ("forward", "reverse")
            ]
        )
    return np.asarray(flux)


def source_matrix(model):
    """Convert events/native denominator/s to molecules/reference/s."""
    columns = []
    for r in model.parent["reactions"]:
        rid = r["reaction_id"]
        scale = model.fit["reactions"][rid]["native_events_per_reference"]
        if scale is None:
            raise ValueError("Missing reviewed native extent to inventory conversion")
        definition = model.entries[rid]["definition"]
        columns.append(scale * (model.stoich(definition["products"]) - model.stoich(definition["reactants"])))
    return np.asarray(columns).T


def physical_source(model, child, x, config):
    flows = fluxes(model, child, x, config)
    return source_matrix(model) @ (flows[:, 0] - flows[:, 1])


def _analytic(model, child, x, config, matrix):
    vacancy = model.check_x(x)
    if min(x) <= 0 or min(vacancy.values()) <= 0:
        raise ValueError("Boundary state requires a one-sided stability qualification")
    rates = fluxes(model, child, x, config)
    fixed, feedback = [], []
    for row, pair in zip(child["reactions"], rates, strict=True):
        factors = []
        for side in ("forward", "reverse"):
            order = row["rates"][side]["activity_orders"]
            dlog = model.stoich(order["species"]) / x
            for idx, (site, capacity) in enumerate(model.fit["capacities"].items()):
                dlog -= order["vacant_sites"].get(site, 0) * model.footprint[idx] / (capacity * vacancy[site])
            factors.append(dlog)
        signed = pair * [1, -1]
        fixed.append(signed @ np.asarray(factors))
        kt = KB * row["parameter_set"]["temperature_K"]
        feedback.append(signed @ (-model.barrier_derivatives(row) / kt))
    return matrix @ fixed, matrix @ feedback


def stability(model, theta, config, policy):
    """Classify local dynamics in the reachable stoichiometric subspace, at a verified root."""
    try:
        x = model.coordinates(theta)
        child = model.child(theta)
        matrix = source_matrix(model)
        basis = orth(matrix)
        if not basis.shape[1]:
            raise ValueError("No independent reactive coordinate")
        if max(abs(physical_source(model, child, x, config) / model.capacity)) > policy["source_per_s"]:
            raise ValueError("Physical residual exceeds root tolerance")
        fixed, chain = _analytic(model, child, x, config, matrix)
        jac = basis.T @ (fixed + chain) @ basis

        def rhs(at):
            c = model.child(model.fractions(at))
            return basis.T @ physical_source(model, c, at, config)

        checks = []
        for h in (policy["fd_step"], policy["fd_step"] / 2):
            checks.append(np.column_stack([(rhs(x + h * v) - rhs(x - h * v)) / (2 * h) for v in basis.T]))
        error = max(float(np.linalg.norm(fd - jac, ord=2)) for fd in checks)
        if error > policy["jacobian_atol"] + policy["jacobian_rtol"] * np.linalg.norm(jac, ord=2):
            raise ValueError("Analytical and finite-difference Jacobians disagree")
        eig, vectors = np.linalg.eig(jac)
        margin = max(policy["eigen_margin_per_s"], float(np.linalg.cond(vectors)) * error)
        if not np.isfinite(margin):
            raise ValueError("Eigenvector conditioning prevents a reliable stability margin")
        largest = max(eig.real)
        label = "STABLE" if largest < -margin else "UNSTABLE" if largest > margin else "UNKNOWN"
        return dict(
            status=label,
            fixed=fixed.tolist(),
            feedback=chain.tolist(),
            basis=basis.tolist(),
            reduced=jac.tolist(),
            fd=[v.tolist() for v in checks],
            fd_max_error=error,
            margin=margin,
            eigenvalues_per_s=[[float(z.real), float(z.imag)] for z in eig],
        )
    except (ValueError, KeyError, np.linalg.LinAlgError, OverflowError) as exc:
        return dict(status="UNKNOWN", reason=str(exc))


def max_distance(a, b):
    if a.keys() != b.keys() or not a:
        raise ValueError("State identity mismatch")
    return max(abs(a[k] - b[k]) for k in a)


def assess_step(model, child, observed, config, history, policy):
    theta = child["coverage_iteration"]["evaluation_coverage"]
    end = observed["coverage"]
    x = model.coordinates(end)
    evaluated = model.child(end)
    energies, logs = [], []
    for old, new in zip(child["reactions"], evaluated["reactions"], strict=True):
        for name in ("forward", "reverse", "reaction"):
            energies.append(abs(old["energies"]["gibbs_ev"][name] - new["energies"]["gibbs_ev"][name]))
        for side in ("forward", "reverse"):
            logs.append(
                abs(math.log(old["rates"][side]["activity_coefficient_s^-1"]) - math.log(new["rates"][side]["activity_coefficient_s^-1"]))
            )
    vacancy = model.check_x(x)
    if max_distance(vacancy, observed["vacancy"]) > policy["coverage_atol"]:
        raise ValueError("Native vacancy differs from inventory reconstruction")
    defect = max(max_distance(theta, end), max_distance(model.check_x(model.coordinates(theta)), vacancy))
    if "initial_coverages" in observed:
        delta = x - model.coordinates(observed["initial_coverages"])
        basis = orth(source_matrix(model))
        if max(abs((delta - basis @ (basis.T @ delta)) / model.capacity)) > policy["coverage_atol"]:
            raise ValueError("Native state changed a conserved molecular total")
    residual = physical_source(model, evaluated, x, config) / model.capacity
    errors = dict(
        coverage_atol=defect,
        energy_eV=max(energies),
        log_k=max(logs),
        source_per_s=float(max(abs(residual))),
        native_residual=observed["residual"],
    )
    result = dict(errors=errors, source_fraction_per_s=dict(zip(model.ids, residual.tolist(), strict=True)))
    if all(value <= policy[key] for key, value in errors.items()):
        return dict(result, status="CONVERGED", stability=stability(model, end, config, policy))
    alpha = policy["damping"]
    next_theta = {s: theta[s] + alpha * (end[s] - theta[s]) for s in theta}
    model.coordinates(next_theta)
    if max_distance(theta, next_theta) <= policy["stagnation_atol"]:
        return dict(result, status="STAGNATED")
    for prior in history:
        earlier = prior["evaluation_coverage"]
        # A monotone sequence approaching a root also has nearly coincident points.
        toward_prior = sum((earlier[s] - theta[s]) * (next_theta[s] - theta[s]) for s in theta)
        if toward_prior > 0 and max_distance(earlier, next_theta) <= policy["cycle_atol"]:
            return dict(result, status="CYCLE")
    return dict(result, status="CONTINUE", next_coverage=next_theta)


def compare_roots(branches, policy, model):
    steady_states.check_policy(policy)
    roots = [b["history"][-1]["observation"] for b in branches if b["status"] == "CONVERGED"]
    roots = [obs for obs in roots if obs["residual"] <= policy["max_residual"]]
    comparisons = []
    for a, b in combinations(roots, 2):
        # Different conserved totals define different physical compatibility classes.
        basis = orth(source_matrix(model))
        delta = model.coordinates(a["coverage"]) - model.coordinates(b["coverage"])
        conserved = delta - basis @ (basis.T @ delta)
        if max(abs(conserved / model.capacity)) > policy["coverage"]:
            comparisons.append(dict(runs=[a["run"], b["run"]], classification="DIFFERENT_CONSERVED_TOTALS"))
        else:
            comparisons.append(steady_states.compare_pair(a, b, policy))
    labels = {p["classification"] for p in comparisons}
    verdict = steady_states.UNKNOWN
    if steady_states.MULTIPLE in labels:
        verdict = steady_states.MULTIPLE
    elif len(roots) == len(branches) and labels == {steady_states.SINGLE}:
        verdict = steady_states.SINGLE
    return dict(
        classification=verdict, comparisons=comparisons,
        root_partition=steady_states.root_partition([obs["run"] for obs in roots], comparisons),
        converged_branches=len(roots), incomplete_branches=len(branches) - len(roots)
    )
