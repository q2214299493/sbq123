"""Public isothermal Cantera reactor interface."""

from copy import deepcopy
import hashlib
import math
import cantera as ct
from sbq123.common.evidence.registry import entry
from sbq123.common.kinetic_model.contracts import RootFailure, identity, integer, number
from ._trust import COMPANION_SHA256
from .mechanism import mechanism, verify_conversion
from .models.cstr import stirred_tank
from .models.pfr import plug_flow
from .state import Case


def _finite_diagnostic(value):
    """JSON null denotes a diagnostic quantity unavailable in a failed solve."""
    if isinstance(value, dict):
        return {k: _finite_diagnostic(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_diagnostic(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def simulate(
    kind: str,
    *,
    dataset_id: str,
    mode: str,
    temperature_K: float,
    pressure_Pa: float,
    composition: dict[str, float],
    volume_m3: float,
    reactant: str,
    product: str,
    inlet_mol_s: float,
    area_m2: float | None = None,
    points: int = 11,
    catalyst_loading_kg: float | None = None,
    catalyst: str | None = None,
    conversion_id: str | None = None,
    initial_coverage: tuple | list = (),
    max_root_distance: float = 0.25,
    cstr_seeds: tuple | list = (),
    analysis_profile: str = "molar",
    axial_intervals: int = 32,
) -> dict:
    """Solve an isothermal PFR or a continuously fed CSTR using a registered kinetic dataset.

    Feed is mol/s, pressure Pa, volume m³ and area m². Initial adsorbate amounts
    are mol per mol of reference sites. Additional CSTR seeds are outlet mol/s.
    """
    inputs = deepcopy(dict(locals()))
    input_hash = identity(inputs)
    if kind not in ("PFR", "CSTR") or not isinstance(cstr_seeds, (list, tuple)):
        raise ValueError("Expected a PFR or CSTR request with a sequence of seeds")
    if not 2 <= integer(points, "output points") <= 10001 or not 4 <= integer(axial_intervals, "axial intervals") <= 2048:
        raise ValueError("Invalid sampling or axial mesh size")
    if kind == "CSTR" and area_m2 is not None or kind == "PFR" and cstr_seeds:
        raise ValueError("Geometry or seeds do not apply to this reactor")
    profile = entry("analysis", analysis_profile)
    if profile != {"mode": "molar", "yield_denominator": "reactant_fed", "selectivity_denominator": "reactant_consumed"}:
        raise ValueError("Unsupported observation profile")
    m = mechanism(dataset_id, volume_m3=volume_m3, catalyst_loading_kg=catalyst_loading_kg, catalyst=catalyst, conversion_id=conversion_id)
    case = Case(m, inputs)
    mismatch = verify_conversion(m, case.t, case.p)
    try:
        if kind == "PFR":
            rows, solver, receipts = plug_flow(case, number(area_m2, "PFR area", positive=True), points, axial_intervals)
        else:
            rows, solver, receipts = stirred_tank(case, inputs["cstr_seeds"])
    except (ValueError, ArithmeticError, ct.CanteraError) as error:
        exc = error if isinstance(error, RootFailure) else RootFailure(str(error))
        original = exc.receipt
        exc.receipt = _finite_diagnostic(original)
        if "receipt_sha256" in original:
            # Preserve the signed local evidence before adding reactor input identity.
            exc.receipt = {"local_failure": exc.receipt}
        exc.receipt.update(converged=False, input_sha256=input_hash)
        exc.receipt.setdefault("species", case.names)
        if "residual_per_feed" not in exc.receipt:
            exc.receipt.update(residual_per_feed=[None] * len(case.names),
                               tolerance_basis="inlet state; verified outlet unavailable")
        exc.receipt.setdefault("tolerance_per_feed", (2e-8 * case.x).tolist())
        exc.receipt.setdefault("residual_mol_s", [None if v is None else v * case.fin for v in exc.receipt["residual_per_feed"]])
        exc.receipt.setdefault("tolerance_mol_s", [None if v is None else v * case.fin for v in exc.receipt["tolerance_per_feed"]])
        exc.receipt = _finite_diagnostic(exc.receipt)
        if exc is error:
            raise
        raise exc from error
    doc = dict(
        schema_version=2,
        model=kind,
        kinetic_mode=mode,
        cantera_version=ct.__version__,
        input_sha256=input_hash,
        conditions=inputs,
        model_sha256=m.model.digest,
        mechanism_sha256=hashlib.sha256(m.text.encode()).hexdigest(),
        rate_basis=m.model.rate_basis,
        rate_factor_to_volume=m.factor,
        coordinate_unit="m" if kind == "PFR" else "m³",
        amount_or_flow_unit="mol/s",
        species_source_unit="mol/(m³ reactor s)",
        denominators=profile,
        scope=m.model.provenance,
        evidence_provenance={
            "dataset_id": dataset_id,
            "dataset_sha256": m.model.digest,
            "thermo_registry_sha256": COMPANION_SHA256,
            "scope": m.model.provenance,
            "catalyst_profile": catalyst,
            "site_conversion_approval": conversion_id,
            "site_geometry": deepcopy(m.companion["site_geometry"]),
            "mechanism_rate_comparison_max_relative": mismatch,
        },
        assumptions=["isothermal", "ideal gas", "validated isobaric domain"],
        points=rows,
        solver=solver,
        uncertainty=None,
        local_solver_receipts=receipts,
    )
    doc["result_sha256"] = identity(doc)
    return doc
