"""Cantera steady FlowReactor and local-MKM Lagrangian parcel integration."""

from dataclasses import dataclass

import cantera as ct
import numpy as np
from scipy.integrate import cumulative_simpson, simpson
from scipy.interpolate import BSpline, CubicSpline, make_interp_spline

from sbq123.common.kinetic_model.contracts import RootFailure
from ..balance import account, configure_precision
from ..kinetics.source import AxialParcel
from ..state import network, propagate


@dataclass(frozen=True)
class _Trajectory:
    grid: np.ndarray
    states: np.ndarray
    residence_times: np.ndarray
    checkpoints: tuple
    branch: object
    solver: dict
    progress: BSpline
    check_progress: BSpline
    stretch: float


def plug_flow(case, area, points, intervals):
    trajectory = _integrate(case, area, intervals)
    rows = _profiles(case, trajectory, points)
    return rows, trajectory.solver, trajectory.branch.receipts if trajectory.branch else []


def _integrate(case, area, intervals):
    """Advance the physical trajectory without access to the requested report grid."""
    guarded = bool(case.m.surfaces) and not case.dynamic
    gas, surf = case.phases(case.x, flow_guard=guarded)
    physical_gas, physical_surface = case.phases(case.x)
    branch = case.branch(gas)
    initial_checkpoint = branch.checkpoint.receipt_sha256 if branch else None
    length = case.volume / area
    speed = case.mdot / (gas.density * area)
    if not np.isfinite(length) or not np.isfinite(speed) or min(length, speed) <= 0:
        raise ValueError("Invalid PFR span or velocity")
    if branch:
        reactor = AxialParcel(gas, energy="off", clone=False, volume=1.0)
        reactor.area_per_mdot = area / case.mdot
        reactor.chemistry_enabled = False
        reactor.local_source = branch
        surface = []
    else:
        reactor = ct.FlowReactor(gas, energy="off", clone=False)
        reactor.area = area
        reactor.mass_flow_rate = case.mdot
        surface = [ct.ReactorSurface(s, reactor, clone=False, A=1.0) for s in surf]
        if surface:
            reactor.surface_area_to_volume_ratio = case.m.area_per_volume
    net = network(reactor)
    if len(surf) > 1 and not branch:
        # IDA's local truncation error applies to the differential gas state.
        # All algebraic site inventories and steady production rates are checked independently.
        net.include_algebraic_in_error_test = False
    # Resolve rapid inlet layers using the turnover time of the feed.
    inlet_rates = case.m.signed_rates(physical_gas, physical_surface)
    damkohler = max(abs(inlet_rates)) * length / (speed * sum(physical_gas.concentrations) * 1000)
    scales = configure_precision(case, net, physical_gas, inlet_rates)
    stretch = np.log1p(damkohler)
    n = max(intervals, int(np.ceil(16 * stretch)))
    s = np.linspace(0, 1, 2 * n + 1)
    if stretch > 1e-5:
        grid = length * np.expm1(stretch * s) / np.expm1(stretch)
        jacobian = length * stretch * np.exp(stretch * s) / np.expm1(stretch)
    else:
        grid, jacobian = length * s, np.full_like(s, length)
    grid[-1] = length
    inlet_momentum = gas.P + gas.density * speed**2
    states, velocities, anchors, branch_ids = [], [], [], []
    directional = []
    try:
        net.initialize()
        for i, z in enumerate(grid):
            if i:
                net.advance(z)
            gas = reactor.phase
            current_surface = tuple(s.phase for s in surface)
            gas, current_surface = _physical_state(gas, current_surface, guarded, physical_gas, physical_surface)
            obs = case.observe(gas, current_surface, branch, z, 0, commit=True)
            velocity = case.mdot / gas.density / area if branch else reactor.speed
            pressure_error = abs(gas.P / case.p - 1) if branch else abs((gas.P + gas.density * velocity**2) / inlet_momentum - 1)
            mass_error = abs(gas.density * velocity * area / case.mdot - 1)
            if pressure_error > 2e-7 or mass_error > 2e-7 or abs(gas.T / case.t - 1) > 1e-9:
                raise RootFailure(
                    "PFR mass, pressure/momentum or isothermal balance failed",
                    {"converged": False, "z": float(z), "T": gas.T, "P": gas.P, "target_P": case.p},
                )
            velocities.append(velocity)
            states.append([gas.T, gas.P, *gas.X, *(v for s in current_surface for v in s.coverages)])
            directional.append([list(obs[key].values()) for key in (
                "source_mol_m3_s", "creation_mol_m3_s", "destruction_mol_m3_s"
            )])
            if branch:
                anchors.append(branch.checkpoint)
                branch_ids.append(obs["local_receipt_sha256"])
    except ct.CanteraError as exc:
        propagate(exc, branch)
    velocities = np.asarray(velocities)
    if not np.isfinite(velocities).all() or min(velocities) <= 0:
        raise RootFailure("Invalid PFR local velocity")
    tau = cumulative_simpson(jacobian / velocities, x=s, initial=0)
    outlet = np.array(list(obs["amount_or_flow"].values()))
    # Integrate in the physical mesh parameter. Both polynomials interpolate
    # signed and directional sources, never the requested reporting stations.
    weighted = np.asarray(directional) * (area * jacobian[:, None, None])
    progress = make_interp_spline(s, weighted, k=5).antiderivative()
    check_progress = make_interp_spline(s, weighted[:, 0], k=3).antiderivative()
    simpson_flow = simpson(weighted[:, 0], x=s, axis=0)
    if guarded:
        # Retain the independent full/alternate Simpson test of the area correction.
        integrated = simpson_flow
        reference = simpson(weighted[::2, 0], x=s[::2], axis=0)
    else:
        integrated = progress(1.0)[0]
        reference = check_progress(1.0)
        original_residual = (outlet - case.feed - simpson_flow) / case.fin
        if not np.isfinite(original_residual).all() or np.any(abs(original_residual) > 2e-6):
            raise RootFailure("Independent axial species balance failed", {
                "converged": False, "residual_per_feed": original_residual.tolist(),
                "tolerance_per_feed": [2e-6] * len(case.names), "method": "full-grid Simpson",
            })
    residual = (outlet - case.feed - integrated) / case.fin
    gross = progress(1.0)[1:]
    diagnostics = _axial_balance(case, net, scales, outlet, integrated, residual, reference, gross)
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
    return _Trajectory(grid, np.asarray(states), tau, tuple(anchors), branch, solver, progress, check_progress, stretch)


def _axial_balance(case, net, scales, outlet, integrated, residual, reference, gross):
    """Compare molar-flow closure and quadrature accuracy on each species basis."""
    extent = abs(integrated) / case.fin
    population = np.maximum(case.feed, outlet) / case.fin
    # Preserve the prior bulk and trace-product bounds, and bound error
    # relative to each species even if native integration was inaccurate.
    scale = np.maximum(population, extent)
    budget = 2e-6 * np.minimum(1.0, scale)
    tolerance = np.minimum(budget, 32 * net.atol + 2 * net.rtol * population + 2e-6 * extent)
    relative = np.divide(residual, scale, out=np.zeros_like(residual), where=scale > 0)
    # A second physical quadrature also checks small
    # net production when subtraction from a large inlet loses precision.
    quadrature_error = abs(integrated - reference) / case.fin
    # Roundoff in two opposing traffic integrals does not relax the outlet balance.
    opposing = np.minimum(gross[0], gross[1]) / case.fin
    quadrature_budget = 2e-6 * extent + 4 * net.rtol * np.maximum(opposing, 0)
    receipt = {
        "species": case.names, "native_atol": net.atol, "native_rtol": net.rtol,
        "inlet_mass_fraction_scales": dict(zip(case.names, scales.tolist())),
        "residual_per_feed": residual.tolist(), "tolerance_per_feed": tolerance.tolist(),
        "relative_species_residual": relative.tolist(),
        "residual_mol_s": (residual * case.fin).tolist(), "tolerance_mol_s": (tolerance * case.fin).tolist(),
        "quadrature_difference_per_feed": quadrature_error.tolist(),
        "quadrature_tolerance_per_feed": quadrature_budget.tolist(),
    }
    if (not np.isfinite(residual).all() or np.any(abs(residual) > tolerance)
            or not np.isfinite(quadrature_error).all() or np.any(quadrature_error > quadrature_budget)):
        # JSON cannot carry NaN or infinity in a failure receipt.
        for key, value in receipt.items():
            if isinstance(value, list) and key != "species":
                receipt[key] = [x if np.isfinite(x) else None for x in value]
        raise RootFailure("Independent axial species balance failed", {"converged": False, **receipt})
    return {"species_balance": receipt, "species_tolerance_per_feed": dict(zip(case.names, tolerance.tolist()))}


def _physical_state(gas, current_surface, guarded, physical_gas, physical_surface):
    if guarded:
        wall = sum(s.get_net_production_rates(gas) for s in current_surface) * gas.molecular_weights
        wall_traffic = sum(s.get_creation_rates(gas) + s.get_destruction_rates(gas) for s in current_surface) * gas.molecular_weights
        if abs(gas.X[-1]) > 1e-14 or abs(sum(wall)) > 1e-8 * max(sum(wall_traffic), 1e-25):
            raise RootFailure("Native FlowReactor requires zero net wall mass exchange")
        physical_gas.TPX = gas.T, gas.P, gas.X[:-1]
        for actual, physical in zip(current_surface, physical_surface, strict=True):
            physical.TP = gas.TP
            physical.coverages = actual.coverages
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
    precision = trajectory.solver["species_balance"]
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
        else:
            offset = 2 + report_gas.n_species
            for surface in report_surface:
                fractions = state[offset:offset + surface.n_species]
                if min(fractions) < -1e-9 or abs(sum(fractions) - 1) > 1e-8:
                    raise RootFailure("Nonphysical interpolated surface inventory")
                surface.TP = report_gas.TP
                surface.coverages = np.maximum(fractions, 0)
                offset += surface.n_species
        row = case.observe(report_gas, report_surface, report_source, z, float(time_at(z)))
        distance = z / length
        if trajectory.stretch > 1e-5:
            distance = np.log1p(distance * np.expm1(trajectory.stretch)) / trajectory.stretch
        signed, created, destroyed = trajectory.progress(distance)
        population = np.maximum(case.feed, list(row["amount_or_flow"].values()))
        scale = np.maximum(population, abs(signed))
        tol = np.minimum(2e-6 * np.minimum(case.fin, scale),
                         32 * precision["native_atol"] * case.fin + 2 * precision["native_rtol"] * population + 2e-6 * abs(signed))
        row["species_balance"] = account(case, row, signed, created, destroyed, tol,
                                         rtol=precision["native_rtol"], error=signed - trajectory.check_progress(distance))
        rows.append(row)
    return rows
