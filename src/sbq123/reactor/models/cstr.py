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

    try:
        if surface is None and not branch:
            net.solve_steady()
            return _verified_outlet(case, reactor, surface, None, outlet_device), []
        # ReactorNet's direct steady solver does not support reacting surfaces.
        # Integrate its actual open tank and inspect independent outlet balances.
        for i in range(90):
            net.advance((i + 1) * tau)
            if branch:
                branch.evaluate(reactor.phase, commit=True)
            try:
                row = _verified_outlet(case, reactor, surface, branch, outlet_device)
            except RootFailure:
                if i == 89 or (branch and branch.failure):
                    raise
                continue
            if branch:
                # Only a physically verified outlet gets a final report evaluation.
                return _verified_outlet(case, reactor, surface, branch.report_at(branch.checkpoint), outlet_device), branch.receipts
            return row, []
    except RootFailure as exc:
        if branch:
            exc.prior_receipts = tuple(branch.receipts)
        raise
    except ct.CanteraError as exc:
        if branch and getattr(branch, "failure", None):
            raise branch.failure from exc
        failure = RootFailure("Cantera CSTR solve failed", {"converged": False, "reason": str(exc)})
        failure.prior_receipts = tuple(branch.receipts) if branch else ()
        raise failure from exc


def _verified_outlet(case, reactor, surface, source, outlet_device):
    actual_mdot = outlet_device.mass_flow_rate * case.volume
    if not np.isfinite(actual_mdot) or actual_mdot <= 0:
        raise RootFailure("Nonphysical CSTR withdrawal")
    row = case.observe(
        reactor.phase,
        surface.phase if surface is not None else None,
        source,
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
    )
    return row


def _joint_state(row, surface_names):
    return {
        "mole_fractions": row["mole_fractions"],
        "surface_coverage": dict(zip(surface_names, row["coverage"] or [], strict=True)),
    }


def _same_root(left, right):
    # Compare matching named components before assigning a common representative.
    for field in ("mole_fractions", "surface_coverage"):
        a, b = left[field], right[field]
        if a.keys() != b.keys() or not np.allclose(list(a.values()), [b[name] for name in a], atol=1e-8, rtol=1e-7):
            return False
    return True


def stirred_tank(case, extra_seeds):
    # Retain every seed's origin while solving each normalized start only once.
    starts = {}
    invalid = []
    outcomes = []

    def add(start, origin):
        key = tuple(start)
        starts.setdefault(key, []).append(origin)
        origin["seed_mole_fractions"] = list(key)
        outcomes.append(origin)

    add(case.x, {"source": "feed"})
    for index, seed in enumerate(extra_seeds):
        origin = {"source": "request", "index": index, "seed": seed}
        try:
            if not isinstance(seed, (tuple, list)) or len(seed) != len(case.x):
                raise ValueError("Invalid CSTR seed dimension")
            y = np.array([number(v, "seed mol/s", nonnegative=True) for v in seed])
            if not 0 < sum(y) < float("inf"):
                raise ValueError("Seed total must be finite and positive")
            add(y / sum(y), origin)
        except ValueError as exc:
            origin.update(status="rejected", reason=str(exc))
            invalid.append(origin.copy())
            outcomes.append(origin)
    for name, vertex in zip(case.names, np.eye(len(case.x))):
        for weight in (0.1, 0.5, 0.9):
            add((1 - weight) * case.x + weight * vertex, {"source": "vertex", "species": name, "weight": weight})

    rows, roots, receipts = [], [], []
    for start, origins in starts.items():
        try:
            row, local = _one(case, start)
        except (RootFailure, ValueError) as exc:
            rejection = dict(
                seed_mole_fractions=list(start),
                reason=str(exc),
                failure=getattr(exc, "receipt", None),
                prior_receipts=list(getattr(exc, "prior_receipts", ())),
                subdivision_failures=list(getattr(exc, "subdivision_failures", ())),
            )
            invalid.append(rejection)
            for origin in origins:
                origin.update(status="rejected", rejection_index=len(invalid) - 1)
            continue
        state = _joint_state(row, case.surface_names)
        candidate = identity(state)
        representative = next((digest for other, digest in roots if _same_root(state, other)), None)
        if representative is None:
            representative = candidate
            roots.append((state, candidate))
            row.update(root_sha256=candidate, root_state=state)
            rows.append(row)
        for origin in origins:
            origin.update(
                status="converged",
                root_sha256=representative,
                candidate_root_sha256=candidate,
                local_receipt_sha256=row["local_receipt_sha256"],
                receipt_start=len(receipts),
                receipt_count=len(local),
            )
        receipts.extend(local)
    if not rows:
        raise RootFailure("No physically converged CSTR outlet", {"converged": False, "rejected_seeds": invalid, "seed_outcomes": outcomes})
    return (
        rows,
        dict(
            success=True,
            method="Cantera/IdealGasReactor/ReactorNet",
            roots_found=len(rows),
            seeds=len(starts),
            seed_outcomes=outcomes,
            rejected_seeds=invalid,
            global_uniqueness=None,
            stability=None,
        ),
        receipts,
    )
