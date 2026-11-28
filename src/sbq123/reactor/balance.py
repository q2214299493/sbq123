"""Species-scaled native error weights and signed steady-flow accounting (mol/s)."""

import numpy as np

from sbq123.common.kinetic_model.contracts import RootFailure


def configure_precision(case, net, gas, inlet_rates):
    """Resolve fed mass fractions and the one-residence production of absent species."""
    generated = np.minimum(1.0, abs(inlet_rates) * case.volume * gas.molecular_weights / (1000 * case.mdot))
    scales = np.where(gas.Y > 0, gas.Y, generated)
    atol = min(net.atol, net.rtol * min(scales[scales > 0]))
    if atol < np.finfo(float).tiny or case.feed[case.ia] == 0:
        raise RootFailure("Species scale is below the native integration range", {
            "converged": False, "requested_native_atol": float(atol),
        })
    net.atol = atol
    return scales


def account(case, row, net_flow, created, destroyed, tolerance, *, rtol, error=None):
    """Compare independent signed progress with the native outlet before publishing ratios."""
    flow = np.array(list(row["amount_or_flow"].values()))
    residual = (flow - case.feed) - net_flow
    traffic = created + destroyed
    # Forward/reverse cancellation can lose all significant digits even when
    # both one-way rates are accurate. Include the state accuracy as well as
    # floating-point accumulation in the uncertainty of the signed increment.
    uncertainty = 2 * max(rtol, np.finfo(float).eps) * traffic + abs((created - destroyed) - net_flow)
    if error is not None:
        uncertainty += abs(error)
    progress_budget = 2e-6 * abs(net_flow)
    receipt = dict(
        species=case.names, residual_per_feed=(residual / case.fin).tolist(),
        tolerance_per_feed=(tolerance / case.fin).tolist(), residual_mol_s=residual.tolist(),
        tolerance_mol_s=tolerance.tolist(), net_production_mol_s=net_flow.tolist(),
        progress_uncertainty_mol_s=uncertainty.tolist(), progress_tolerance_mol_s=progress_budget.tolist(),
    )
    if (not np.isfinite([residual, tolerance, uncertainty, progress_budget]).all()
            or np.any(abs(residual) > tolerance) or np.any(uncertainty > progress_budget)
            or np.any(created < 0) or np.any(destroyed < 0)):
        raise RootFailure("Species outlet or signed reaction progress is unresolved", {"converged": False, **receipt})
    # Preserve native flow observables when both increments are resolvable
    # and confirmed by stoichiometry. Otherwise use one signed source basis
    # for both numerator and denominator, including co-fed products.
    targets = [case.ia, case.ib]
    delta = flow - case.feed
    rounding = 2 * np.finfo(float).eps * np.maximum(flow, case.feed)
    resolved = (rounding + abs(residual)) <= 2e-6 * abs(net_flow)
    # A co-fed product can carry bulk-state integration error as well as ULP loss.
    # Use signed reaction progress for co-feeds regardless of apparent significance.
    use_flow = case.feed[case.ib] == 0 and resolved[targets].all() and np.any(net_flow[targets] != 0)
    progress = delta if use_flow else net_flow
    consumed, formed = -progress[case.ia], progress[case.ib]
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        conversion = consumed / case.feed[case.ia]
        yield_value = formed / case.feed[case.ia]
        selectivity = formed / consumed if consumed != 0 else None
    if not np.isfinite([conversion, yield_value]).all() or (selectivity is not None and not np.isfinite(selectivity)):
        raise RootFailure("Reaction observable outside floating-point range", {"converged": False, **receipt})
    row.update(
        observable_basis="verified_outlet_flows" if use_flow else "signed_reaction_progress",
        gross_production_mol_s=dict(zip(case.names, created.tolist())),
        gross_consumption_mol_s=dict(zip(case.names, destroyed.tolist())),
        net_production_mol_s=dict(zip(case.names, net_flow.tolist())),
        conversion=float(conversion),
        yield_mol_per_mol_fed=float(yield_value),
        selectivity_mol_per_mol_consumed=float(selectivity) if selectivity is not None else None,
    )
    return receipt
