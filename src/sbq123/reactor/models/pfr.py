"""Cantera steady FlowReactor and local-MKM Lagrangian parcel integration."""

from dataclasses import dataclass

import cantera as ct
import numpy as np
from scipy.integrate import cumulative_simpson, simpson
from scipy.interpolate import CubicSpline

from sbq123.common.kinetic_model.contracts import RootFailure
from ..kinetics.source import CoupledTank
from ..state import network, propagate


@dataclass(frozen=True)
class _Trajectory:
    grid: np.ndarray
    states: np.ndarray
    residence_times: np.ndarray
    checkpoints: tuple
    branch: object
    solver: dict
    integrated_flows: np.ndarray | None


def plug_flow(case, area, points, intervals):
    trajectory = _integrate(case, area, intervals)
    rows = _profiles(case, trajectory, points)
    return rows, trajectory.solver, trajectory.branch.receipts if trajectory.branch else []


def _integrate(case, area, intervals):
    """Advance the physical trajectory without access to the requested report grid."""
    guarded = case.m.surface is not None and not case.dynamic
    gas, surf = case.phases(case.x, flow_guard=guarded)
    physical_gas, physical_surface = case.phases(case.x)
    branch = case.branch(gas)
    initial_checkpoint = branch.checkpoint.receipt_sha256 if branch else None
    length = case.volume / area
    speed = case.mdot / (gas.density * area)
    if not np.isfinite(length) or not np.isfinite(speed) or min(length, speed) <= 0:
        raise ValueError("Invalid PFR span or velocity")
    if branch:
        # For the qualified equal-molar-mass gas family, mass conservation at
        # fixed T and P makes the Lagrangian residence coordinate exactly z/u.
        if not np.allclose(gas.molecular_weights, gas.molecular_weights[0], rtol=1e-12, atol=0):
            raise ValueError("Dynamic parcel mapping requires equal gas molecular weights")
        reactor = CoupledTank(gas, energy="off", clone=False, volume=1.0)
        reactor.chemistry_enabled = False
        reactor.local_source = branch
        surface = None
    else:
        reactor = ct.FlowReactor(gas, energy="off", clone=False)
        reactor.area = area
        reactor.mass_flow_rate = case.mdot
        if surf is not None:
            # A unit reference patch leaves the physical active area entirely in S/V.
            surface = ct.ReactorSurface(surf, reactor, clone=False, A=1.0)
            reactor.surface_area_to_volume_ratio = case.m.area_per_volume
        else:
            surface = None
    net = network(reactor)
    # Resolve rapid inlet layers using the turnover time of the feed.
    inlet_rates = case.m.signed_rates(physical_gas, physical_surface)
    damkohler = max(abs(inlet_rates)) * length / (speed * sum(physical_gas.concentrations) * 1000)
    if guarded:
        scales = _configure_surface_precision(case, net, physical_gas, inlet_rates)
    stretch = np.log1p(damkohler)
    n = max(intervals, int(np.ceil(16 * stretch)))
    s = np.linspace(0, 1, 2 * n + 1)
    if stretch > 1e-5:
        grid = length * np.expm1(stretch * s) / np.expm1(stretch)
        jacobian = length * stretch * np.exp(stretch * s) / np.expm1(stretch)
    else:
        grid, jacobian = length * s, np.full_like(s, length)
    grid[-1] = length
    states, rates, velocities, anchors, branch_ids = [], [], [], [], []
    try:
        net.initialize()
        for i, z in enumerate(grid):
            if i:
                net.advance(z / speed if branch else z)
            gas = reactor.phase
            current_surface = surface.phase if surface is not None else None
            gas, current_surface = _physical_state(gas, current_surface, guarded, physical_gas, physical_surface)
            obs = case.observe(gas, current_surface, branch, z, 0, commit=True)
            if abs(gas.P / case.p - 1) > 2e-7 or abs(gas.T / case.t - 1) > 1e-9:
                raise RootFailure(
                    "Flow left the validated isothermal, isobaric domain",
                    {"converged": False, "z": float(z), "T": gas.T, "P": gas.P, "target_P": case.p},
                )
            velocities.append(case.mdot / gas.density / area if branch else reactor.speed)
            states.append([gas.T, gas.P, *gas.X, *(current_surface.coverages if current_surface is not None else [])])
            rates.append(list(obs["source_mol_m3_s"].values()))
            if branch:
                anchors.append(branch.checkpoint)
                branch_ids.append(obs["local_receipt_sha256"])
    except ct.CanteraError as exc:
        propagate(exc, branch)
    velocities = np.asarray(velocities)
    if not np.isfinite(velocities).all() or min(velocities) <= 0:
        raise RootFailure("Invalid PFR local velocity")
    tau = cumulative_simpson(jacobian / velocities, x=s, initial=0)
    integrated = area * simpson(np.asarray(rates) * jacobian[:, None], x=s, axis=0)
    outlet = np.array(list(obs["amount_or_flow"].values()))
    residual = (outlet - case.feed - integrated) / case.fin
    integrated_flows = None
    diagnostics = {}
    if guarded:
        source = np.asarray(rates) * jacobian[:, None] * area
        integrated_flows = cumulative_simpson(source, x=s, axis=0, initial=0)
        diagnostics = _surface_balance(case, net, scales, outlet, integrated, residual, source, s)
    elif not np.isfinite(residual).all() or max(abs(residual)) > 2e-6:
        raise RootFailure("Independent axial species balance failed", {"converged": False, "residual_per_feed": residual.tolist()})
    solver = dict(
        success=True,
        method="Cantera/ReactorNet/CVODES local-source parcel" if branch else "Cantera/FlowReactor/IDA",
        flow_surface_inert_coordinate=guarded,
        physical_intervals=len(grid) - 1,
        initial_checkpoint_sha256=initial_checkpoint,
        continuation_receipts=branch_ids,
        integral_species_residual_per_feed=residual.tolist(),
        residual_tolerance=2e-6,
        **diagnostics,
    )
    return _Trajectory(grid, np.asarray(states), tau, tuple(anchors), branch, solver, integrated_flows)


def _configure_surface_precision(case, net, gas, inlet_rates):
    """Select a scalar IDA atol that resolves the smallest active mass fraction."""
    weights = gas.molecular_weights
    # For an initially absent species, V * |R_in| estimates its mol/s
    # production over one inlet residence time. IDA integrates mass fractions.
    generated = np.minimum(1.0, abs(inlet_rates) * case.volume * weights / (1000 * case.mdot))
    scales = np.where(gas.Y > 0, gas.Y, generated)
    target_atol = min(net.atol, net.rtol * min(scales[scales > 0]))
    if target_atol < np.finfo(float).tiny or case.feed[case.ia] == 0:
        raise RootFailure("Species scale is below the native integration range", {
            "converged": False, "requested_native_atol": target_atol,
            "tolerance_per_feed": (2e-6 * scales * gas.mean_molecular_weight / weights).tolist(),
            "tolerance_basis": "inlet state estimate; outlet unavailable",
        })
    net.atol = target_atol
    return scales


def _surface_balance(case, net, scales, outlet, integrated, residual, source, s):
    """Compare molar-flow closure and quadrature accuracy on each species basis."""
    extent = abs(integrated) / case.fin
    population = np.maximum(case.feed, outlet) / case.fin
    # Preserve the prior bulk and trace-product bounds, and bound error
    # relative to each species even if native integration was inaccurate.
    scale = np.maximum(population, extent)
    budget = 2e-6 * np.minimum(1.0, scale)
    tolerance = np.minimum(budget, 32 * net.atol + 2 * net.rtol * population + 2e-6 * extent)
    relative = np.divide(residual, scale, out=np.zeros_like(residual), where=scale > 0)
    # A second quadrature on alternate physical stations also checks small
    # net production when subtraction from a large inlet loses precision.
    quadrature_error = abs(integrated - simpson(source[::2], x=s[::2], axis=0)) / case.fin
    receipt = {
        "species": case.names, "native_atol": net.atol, "native_rtol": net.rtol,
        "inlet_mass_fraction_scales": dict(zip(case.names, scales.tolist())),
        "residual_per_feed": residual.tolist(), "tolerance_per_feed": tolerance.tolist(),
        "relative_species_residual": relative.tolist(),
        "residual_mol_s": (residual * case.fin).tolist(), "tolerance_mol_s": (tolerance * case.fin).tolist(),
        "quadrature_difference_per_feed": quadrature_error.tolist(),
        "quadrature_tolerance_per_feed": (2e-6 * extent).tolist(),
    }
    if (not np.isfinite(residual).all() or np.any(abs(residual) > tolerance)
            or not np.isfinite(quadrature_error).all() or np.any(quadrature_error > 2e-6 * extent)):
        # JSON cannot carry NaN or infinity in a failure receipt.
        for key, value in receipt.items():
            if isinstance(value, list) and key != "species":
                receipt[key] = [x if np.isfinite(x) else None for x in value]
        raise RootFailure("Independent axial species balance failed", {"converged": False, **receipt})
    return {"species_balance": receipt, "species_tolerance_per_feed": dict(zip(case.names, tolerance.tolist()))}


def _physical_state(gas, current_surface, guarded, physical_gas, physical_surface):
    if guarded:
        wall = current_surface.get_net_production_rates(gas) * gas.molecular_weights
        if abs(gas.X[-1]) > 1e-14 or abs(sum(wall)) > 1e-8 * max(sum(abs(wall)), 1e-25):
            raise RootFailure("Native FlowReactor requires zero net wall mass exchange")
        physical_gas.TPX = gas.T, gas.P, gas.X[:-1]
        physical_surface.TP = gas.T, gas.P
        physical_surface.coverages = current_surface.coverages
        gas, current_surface = physical_gas, physical_surface
    elif np.min(gas.X) < 0:
        # IDA's unconstrained trace species can cross zero by roundoff.
        if np.min(gas.X) < -1e-12:
            raise RootFailure("Negative native PFR mole fraction")
        physical_gas.TPX = gas.T, gas.P, np.maximum(gas.X, 0)
        gas = physical_gas
    return gas, current_surface


def _profiles(case, trajectory, points):
    grid = trajectory.grid
    length = grid[-1]
    interpolate = CubicSpline(grid, trajectory.states, axis=0)
    time_at = CubicSpline(grid, trajectory.residence_times)
    extent_at = CubicSpline(grid, trajectory.integrated_flows, axis=0) if trajectory.integrated_flows is not None else None
    report_gas, report_surface = case.phases(case.x)
    rows = []
    for z in np.linspace(0, length, points):
        state = interpolate(z)
        xs = state[2 : 2 + report_gas.n_species]
        if min(xs) < -1e-9 or abs(sum(xs) - 1) > 1e-8:
            raise RootFailure("Nonphysical interpolated gas state")
        report_gas.TPX = state[0], state[1], np.maximum(xs, 0)
        report_source = None
        if trajectory.branch:
            left = int(np.searchsorted(grid, z, side="right") - 1)
            report_source = trajectory.branch.report_at(trajectory.checkpoints[left])
        elif report_surface is not None:
            fractions = state[2 + report_gas.n_species :]
            if min(fractions) < -1e-9 or abs(sum(fractions) - 1) > 1e-8:
                raise RootFailure("Nonphysical interpolated surface inventory")
            report_surface.TP = report_gas.TP
            report_surface.coverages = np.maximum(fractions, 0)
        row = case.observe(report_gas, report_surface, report_source, z, float(time_at(z)))
        if extent_at is not None:
            # A trace increment on top of a bulk co-feed can be smaller than
            # one ULP of its outlet. Recover that increment from signed flux.
            flows = np.array(list(row["amount_or_flow"].values()))
            delta = flows - case.feed
            cancellation = abs(delta) * 2e-6 <= 2 * np.finfo(float).eps * np.maximum(flows, case.feed)
            delta = np.where(cancellation, extent_at(z), delta)
            consumed, formed = -delta[case.ia], delta[case.ib]
            row.update(conversion=float(consumed / case.feed[case.ia]),
                       yield_mol_per_mol_fed=float(formed / case.feed[case.ia]),
                       selectivity_mol_per_mol_consumed=float(formed / consumed)
                       if abs(consumed) > 1e-12 * case.feed[case.ia] else None)
        rows.append(row)
    return rows
