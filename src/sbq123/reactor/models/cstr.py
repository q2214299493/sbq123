"""Cantera open mixed tank. Verify every candidate against the original species source."""

import cantera as ct
import numpy as np

from sbq123.common.kinetic_model.contracts import RootFailure, identity, number
from ..kinetics.source import CoupledTank
from ..state import network


def _one(case, start):
    inlet, _ = case.phases(case.x)
    gas, surf = case.phases(start)
    branch = case.branch(inlet)
    if branch:
        reactor = CoupledTank(gas, energy="off", clone=False, volume=1.0)
        reactor.chemistry_enabled = False
        reactor.local_source = branch
    else:
        reactor = ct.IdealGasReactor(gas, energy="off", clone=False, volume=1.0)
    surface = ct.ReactorSurface(surf, reactor, clone=False, A=case.m.area_per_volume) if surf is not None and not branch else None
    # The intensive equations are identical in this unit-volume representative
    # vessel. Physical outlet flow and per-species residuals are restored below.
    boundary = ct.Reservoir(inlet, clone=False)
    exhaust_gas, _ = case.phases(case.x)
    exhaust = ct.Reservoir(exhaust_gas, clone=False)
    specific_mdot = case.mdot / case.volume
    tau = inlet.density / specific_mdot
    if not np.isfinite(tau) or tau <= 0:
        raise ValueError("CSTR residence time outside floating-point domain")
    feed_device = ct.MassFlowController(boundary, reactor, mdot=specific_mdot)
    outlet_device = ct.PressureController(reactor, exhaust, primary=feed_device, K=specific_mdot / case.p)
    net = network(reactor)
    net.initialize()

    def verify():
        actual_mdot = outlet_device.mass_flow_rate * case.volume
        if not np.isfinite(actual_mdot) or actual_mdot <= 0:
            raise RootFailure("Nonphysical CSTR withdrawal")
        row = case.observe(
            reactor.phase,
            surface.phase if surface is not None else None,
            branch,
            case.volume,
            case.volume * reactor.phase.density / actual_mdot,
            mdot=actual_mdot,
        )
        out = np.array(list(row["amount_or_flow"].values())) / case.fin
        volumetric_source = np.array(list(row["source_mol_m3_s"].values()))
        produced = volumetric_source * (case.volume / case.fin)
        residual = case.x - out + produced
        tolerance = 2e-10 + 2e-8 * np.maximum.reduce([case.x, abs(out), abs(produced)])
        if (
            not np.isfinite(residual).all()
            or np.any(abs(residual) > tolerance)
            or abs(actual_mdot / case.mdot - 1) > 2e-8
            or abs(reactor.phase.P / case.p - 1) > 2e-7
        ):
            raise RootFailure(
                "Independent CSTR species or withdrawal balance failed",
                {"converged": False, "species_residual_per_feed": residual.tolist()},
            )
        row.update(
            balance_residual_per_inlet_flow=residual.tolist(),
            balance_residual_mol_s=(case.fin * residual).tolist(),
            balance_tolerance_per_inlet_flow=tolerance.tolist(),
            root_sha256=identity(row["mole_fractions"]),
        )
        return row

    try:
        if surface is None and not branch:
            net.solve_steady()
            return verify(), []
        # ReactorNet's direct steady solver does not support reacting surfaces.
        # Integrate its actual open tank and inspect independent outlet balances.
        for i in range(90):
            net.advance((i + 1) * tau)
            if branch:
                branch.evaluate(reactor.phase, commit=True)
            try:
                return verify(), branch.receipts if branch else []
            except RootFailure:
                if i == 89:
                    raise
    except ct.CanteraError as exc:
        if branch and getattr(branch, "failure", None):
            raise branch.failure from exc
        raise RootFailure("Cantera CSTR solve failed", {"converged": False, "reason": str(exc)}) from exc


def stirred_tank(case, extra_seeds):
    seeds = [case.x]
    invalid = []
    for seed in extra_seeds:
        try:
            if not isinstance(seed, (tuple, list)) or len(seed) != len(case.x):
                raise ValueError("Invalid CSTR seed dimension")
            y = np.array([number(v, "seed mol/s", nonnegative=True) for v in seed])
            if not 0 < sum(y) < float("inf"):
                raise ValueError("Seed total must be finite and positive")
            seeds.append(y / sum(y))
        except ValueError as exc:
            invalid.append({"seed": seed, "reason": str(exc)})
    for vertex in np.eye(len(case.x)):
        for w in (0.1, 0.5, 0.9):
            seeds.append((1 - w) * case.x + w * vertex)
    roots, rows, receipts = [], [], []
    unique = list(dict.fromkeys(tuple(s) for s in seeds))
    for start in unique:
        try:
            row, local = _one(case, start)
        except (RootFailure, ValueError) as exc:
            invalid.append({"seed_mole_fractions": list(start), "reason": str(exc), "failure": getattr(exc, "receipt", None)})
            continue
        x = np.array(list(row["mole_fractions"].values()))
        receipts.extend(local)
        if not any(np.allclose(x, root, atol=1e-8, rtol=1e-7) for root in roots):
            roots.append(x)
            rows.append(row)
    if not rows:
        raise RootFailure("No physically converged CSTR outlet", {"converged": False, "rejected_seeds": invalid})
    return (
        rows,
        dict(
            success=True,
            method="Cantera/IdealGasReactor/ReactorNet",
            roots_found=len(rows),
            seeds=len(unique),
            rejected_seeds=invalid,
            global_uniqueness=None,
            stability=None,
        ),
        receipts,
    )
