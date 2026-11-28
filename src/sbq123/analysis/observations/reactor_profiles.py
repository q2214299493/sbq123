"""Point-resolved reactor observations and matched, single-factor operating contrasts."""
from copy import deepcopy

from sbq123.analysis.observations.reactor import reactor_observation
from sbq123.common.evidence.registry import dataset
from sbq123.common.kinetic_model.contracts import identity


def analyze_profile(result, expected_sha256):
    result = deepcopy(result)
    summary = reactor_observation(result, expected_sha256)
    if result["schema_version"] != 2:
        raise ValueError("A schema 2 result is required for point-resolved source and flow analysis")
    fields = ("coordinate", "residence_time_s", "temperature_K", "pressure_Pa", "amount_or_flow",
              "source_mol_m3_s", "creation_mol_m3_s", "destruction_mol_m3_s", "conversion",
              "yield_mol_per_mol_fed", "selectivity_mol_per_mol_consumed", "coverage", "vacancy",
              "gross_production_mol_s", "gross_consumption_mol_s", "net_production_mol_s", "observable_basis")
    rows = [{k: p.get(k) for k in fields} for p in result["points"]]
    if result["model"] == "PFR":
        explanation = "Axial conversion follows the integrated species balance from the inlet."
        alternative = "Changes in residence time or surface state can change the local source along the reactor."
        prediction = "Compare local sources at matched temperature, pressure and composition along a second profile."
    else:
        explanation = "Each outlet satisfies the reported steady feed, withdrawal and reaction balance."
        alternative = "A different admissible surface branch can yield a different steady outlet."
        prediction = "Check continuation and alternative initial seeds before inferring branch uniqueness."
    interpretation = dict(source_sha256=expected_sha256, supported_explanation=explanation,
                          alternative_explanation=alternative, mechanism_hypothesis=None,
                          prediction_requiring_validation=prediction, uncertainty=summary["uncertainty"])
    return dict(**summary, interpretation=interpretation, points=rows, conditions=result["conditions"], flow_unit=result["amount_or_flow_unit"],
                local_source_unit=result["species_source_unit"], quantity="axial_profile" if result["model"] == "PFR"
                else "steady_outlet_roots", assumptions=result["assumptions"],
                branches="Each CSTR point is a separate converged outlet root" if result["model"] == "CSTR" else None)


def compare_operating_points(left, right, variable):
    """Pairs are (schema-2 result, independently retained digest). Compare one varied input at a time."""
    a, b = (analyze_profile(*side) for side in (left, right))
    if variable not in ("temperature_K", "pressure_Pa"):
        raise ValueError("Choose temperature_K or pressure_Pa")
    result = dict(source_sha256=[a["result_sha256"], b["result_sha256"]], variable=variable,
                  change=None, interpretation=None, scope=[a["scope"], b["scope"]])
    conditions = [dict(r["conditions"]) for r in (a, b)]
    levels = [c.pop(variable) for c in conditions]
    # Project selectors may carry different approved companion or conversion records across deployments.
    bindings = ("mechanism_sha256", "rate_basis", "rate_factor_to_volume", "denominators", "scope")
    same_basis = all(left[0][field] == right[0][field] for field in bindings)
    if (not same_basis or a["dataset_sha256"] != b["dataset_sha256"] or conditions[0] != conditions[1] or levels[0] == levels[1]
            or any(r["reactor"] == "CSTR" and len(r["points"]) != 1 for r in (a, b))):
        return dict(result, status="insufficient_evidence", reason="Require matched mechanism, physical basis, feed, geometry, unique outlet and one changed input")
    changes = {}
    for k in ("conversion", "yield_mol_per_mol_fed", "selectivity_mol_per_mol_consumed"):
        x, y = [r["points"][-1][k] for r in (a, b)]
        changes[k] = None if x is None or y is None else y - x
    return dict(result, status="available", levels=levels, change=changes,
                interpretation="Finite outlet contrast at the stated feed, geometry and molar flow.",
                alternative_explanation="Residence time and local composition may also change.",
                limitation="Two outlets do not isolate an elementary activation energy or prove branch continuity.")


def compare_local_mkm(result, expected_sha256):
    """Re-evaluate registered kinetics at each retained local MKM state, in reactor volume units."""
    result = deepcopy(result)
    obs = reactor_observation(result, expected_sha256)
    unavailable = dict(status="insufficient_evidence", differences=None, source_sha256=expected_sha256)
    if result["schema_version"] != 2 or obs["kinetic_mode"] != "dynamic_mkm":
        return dict(unavailable, reason="No local MKM state recorded")
    model = dataset(result["conditions"]["dataset_id"])
    if model.digest != obs["dataset_sha256"]:
        raise ValueError("Local kinetic model identity mismatch")
    receipts = {r["receipt_sha256"]: r for r in result["local_solver_receipts"]}
    gas = [s for s, p in zip(model.species, model.phases, strict=True) if p == "gas"]
    rows = []
    for p in result["points"]:
        key = p["local_receipt_sha256"]
        rec = receipts[key]
        raw = {k: v for k, v in rec.items() if k != "receipt_sha256"}
        if (identity(raw) != key or rec["model_sha256"] != model.digest or not rec["converged"]
                or rec["coverage"] != p["coverage"] or rec["temperature_K"] != p["temperature_K"]
                or rec["pressure_Pa"] != p["pressure_Pa"]):
            raise ValueError("Reported local state differs from MKM receipt")
        concentrations = [p["concentration_mol_m3"][s] for s in gas]
        if concentrations != rec["gas_concentration_mol_m3"]:
            raise ValueError("Local gas state differs from MKM receipt")
        rates, _ = model.source(concentrations, rec["coverage"], rec["temperature_K"], rec["pressure_Pa"])
        projected = {s: v * result["rate_factor_to_volume"] for s, v, phase in
                     zip(model.species, rates, model.phases, strict=True) if phase == "gas"}
        rows.append(dict(coordinate=p["coordinate"], receipt_sha256=key,
                         reactor_minus_local={s: p["source_mol_m3_s"][s] - projected[s] for s in gas}))
    return dict(status="available", differences=rows, unit=result["species_source_unit"], source_sha256=expected_sha256,
                scope=obs["scope"], limitation="Consistency of a coupled calculation using the same model and accepted state.")
