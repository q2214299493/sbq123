"""Cantera open mixed tank. Verify every candidate against the original species source."""

import cantera as ct
import numpy as np

from sbq123.common.kinetic_model.contracts import RootFailure, identity, number
from ..balance import account, configure_precision
from ..kinetics.source import CoupledTank
from ..state import network


def _one(case, start, coverage=None):
    inlet, inlet_surface = case.phases(case.x)
    gas, surf = case.phases(start, coverage=coverage)
    branch = case.branch(gas, coverage=coverage)
    if branch:
        reactor = CoupledTank(gas, energy="off", clone=False, volume=1.0)
        reactor.chemistry_enabled = False
        reactor.local_source = branch
    else:
        reactor = ct.IdealGasReactor(gas, energy="off", clone=False, volume=1.0)
    surfaces = [ct.ReactorSurface(s, reactor, clone=False, A=case.m.area_per_volume) for s in surf] if not branch else []
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
    scales = configure_precision(case, net, inlet, case.m.signed_rates(inlet, inlet_surface))
    net.initialize()

    try:
        if not surfaces and not branch:
            net.solve_steady()
            return _verified_outlet(case, reactor, surfaces, None, outlet_device, net, scales), []
        # ReactorNet's direct steady solver does not support reacting surfaces.
        # Integrate its actual open tank and inspect independent outlet balances.
        # Accept only on independently checked surface and species balances.
        # Limit adaptive solver work rather than time in units of gas residence.
        net.advance(tau)
        for i in range(1024):
            if i:
                for _ in range(8):
                    net.step()
            if branch:
                branch.evaluate(reactor.phase, commit=True)
            try:
                row = _verified_outlet(case, reactor, surfaces, branch, outlet_device, net, scales)
            except RootFailure:
                if i == 1023 or (branch and branch.failure):
                    raise
                continue
            if branch:
                # Only a physically verified outlet gets a final report evaluation.
                return _verified_outlet(case, reactor, surfaces, branch.report_at(branch.checkpoint), outlet_device, net, scales), branch.receipts
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


def _verified_outlet(case, reactor, surfaces, source, outlet_device, net, scales):
    actual_mdot = outlet_device.mass_flow_rate * case.volume
    if not np.isfinite(actual_mdot) or actual_mdot <= 0:
        raise RootFailure("Nonphysical CSTR withdrawal")
    row = case.observe(
        reactor.phase,
        tuple(s.phase for s in surfaces),
        source,
        case.volume,
        case.volume * reactor.phase.density / actual_mdot,
        mdot=actual_mdot,
    )
    out = np.array(list(row["amount_or_flow"].values())) / case.fin
    volumetric_source = np.array(list(row["source_mol_m3_s"].values()))
    produced = volumetric_source * (case.volume / case.fin)
    residual = case.x - out + produced
    scale = np.maximum.reduce([case.x, abs(out), abs(produced)])
    tolerance = 2e-8 * scale
    signed = volumetric_source * case.volume
    created = np.array(list(row["creation_mol_m3_s"].values())) * case.volume
    destroyed = np.array(list(row["destruction_mol_m3_s"].values())) * case.volume
    diagnostics = account(case, row, signed, created, destroyed, tolerance * case.fin, rtol=net.rtol)
    row["species_balance"] = dict(diagnostics, native_rtol=net.rtol, native_atol=net.atol,
                                  inlet_mass_fraction_scales=dict(zip(case.names, scales.tolist())))
    if (
        not np.isfinite(residual).all()
        or np.any(abs(residual) > tolerance)
        or abs(actual_mdot / case.mdot - 1) > 2e-8
        or abs(reactor.phase.P / case.p - 1) > 2e-7
    ):
        raise RootFailure(
            "Independent CSTR species or withdrawal balance failed",
            {**diagnostics, "converged": False, "species_residual_per_feed": residual.tolist()},
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

    def add(start, origin, coverage=None):
        key = (tuple(start), None if coverage is None else tuple(coverage))
        starts.setdefault(key, []).append(origin)
        origin["seed_mole_fractions"] = list(start)
        if coverage is not None:
            origin["seed_surface_coverage"] = list(coverage)
        outcomes.append(origin)

    add(case.x, {"source": "feed"})
    for index, seed in enumerate(extra_seeds):
        origin = {"source": "request", "index": index, "seed": seed}
        try:
            coverage = None
            if isinstance(seed, dict):
                if set(seed) != {"gas_flow_mol_s", "surface_coverage"}:
                    raise ValueError("Invalid joint gas/surface seed")
                coverage = case.checked_coverage(seed["surface_coverage"])
                seed = seed["gas_flow_mol_s"]
            if not isinstance(seed, (tuple, list)) or len(seed) != len(case.x):
                raise ValueError("Invalid CSTR seed dimension")
            y = np.array([number(v, "seed mol/s", nonnegative=True) for v in seed])
            if not 0 < sum(y) < float("inf"):
                raise ValueError("Seed total must be finite and positive")
            add(y / sum(y), origin, coverage)
        except ValueError as exc:
            origin.update(status="rejected", reason=str(exc))
            invalid.append(origin.copy())
            outcomes.append(origin)
    for name, vertex in zip(case.names, np.eye(len(case.x))):
        for weight in (0.1, 0.5, 0.9):
            add((1 - weight) * case.x + weight * vertex, {"source": "vertex", "species": name, "weight": weight})

    rows, roots, receipts = [], [], []
    for (start, coverage), origins in starts.items():
        try:
            row, local = _one(case, start) if coverage is None else _one(case, start, coverage)
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
        detail = next((seed["failure"] for seed in invalid
                       if (seed.get("failure") or {}).get("residual_per_feed") is not None), {})
        raise RootFailure("No physically converged CSTR outlet", {
            **detail, "converged": False, "rejected_seeds": invalid, "seed_outcomes": outcomes,
        })
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
