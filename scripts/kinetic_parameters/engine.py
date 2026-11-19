"""Generate rate records from an immutable network and optional reviewed model bindings."""
import math
from datetime import datetime

from scripts.artifact_io import require_sha256, sha256_json
from scripts.kinetic_parameters.laws import activation_shift, coefficient, exp_rate, gas_powers, positive
from scripts.multiphase_contracts import _bundle_validator, _check_species_context
from scripts.reaction_network.builder import check_parameter_basis, reviewed as reviewed_records
from scripts.reaction_network.thermodynamics import check_closure
from scripts.scientific_validation import finite_number, validate_finite_tree
from scripts.thermochemistry.harmonic import KB

SOURCES = {"local_calculation", "external_calculation", "literature", "user_provided", "approved_assumption", "synthetic"}


def check_version(document, field):
    if document.get(field) != sha256_json({k: v for k, v in document.items() if k != field}):
        raise ValueError(f"Invalid {field} digest")


def reviewed(model, network_version, verified):
    review = model.get("scientific_review")
    sources = model.get("sources", [])
    scope = model.get("use_scope", "project")
    if scope not in ("synthetic_benchmark", "project"):
        raise ValueError("Unknown kinetic dataset use scope")
    for source in sources:
        if source.get("kind") not in SOURCES or not str(source.get("reference") or "").strip():
            raise ValueError("Untraceable kinetic model source")
        require_sha256(source["sha256"], label="model source")
        if source["kind"] == "synthetic" and scope != "synthetic_benchmark":
            raise ValueError("Synthetic parameters require benchmark scope")
        if source["kind"] == "approved_assumption" and not model.get("accepted_by"):
            raise ValueError("Assumption lacks explicit user acceptance")
    if not review or review.get("status") != "validated":
        return False
    if review.get("subject_sha256") != sha256_json([network_version, {k: v for k, v in model.items() if k != "scientific_review"}]):
        raise ValueError("Stale kinetic model review")
    if (not review.get("reviewer") or not review.get("method")
            or datetime.fromisoformat(review.get("reviewed_at", "")).tzinfo is None):
        raise ValueError("Incomplete scientific review")
    return bool(sources) and all(s["sha256"] in verified for s in sources)


def missing(entry, parameter, model):
    gaps = list(entry["gaps"])
    for state in ("IS", "FS"):
        thermal = entry.get("thermochemistry")
        if thermal and (thermal["states"].get(state) or {}).get("gibbs_correction_ev") is None:
            gaps.append(f"{state}: compatible Gibbs correction missing")
    if parameter is None:
        gaps.append("Kinetic parameter set with units, standard states, validity range and sources missing")
    if model is None:
        gaps.append("Rate law, scoped parameter review and applicability not supplied")
    if entry["site_balance"] is None:
        gaps.append("Reviewed site occupancies and vacant-site counts required")
    return gaps


def conditions(entry, param, model):
    e = entry["energies"]
    t = positive(param["temperature_K"], "temperature")
    p = finite_number(param["pressure_Pa"], "pressure", nonnegative=True)
    ref = entry["definition"]["energy_reference_id"]
    if (param["energy_basis"] != "gibbs" or param["energy_reference_id"] != ref or t != e["temperature_k"]
            or param["standard_state_id"] != e["standard_state"] or model.get("standard_states") != param["standard_states"]):
        raise ValueError("Incompatible temperature, Gibbs reference or standard state")
    states = param["standard_states"]
    if model.get("normalization", "per_reference_site") != "per_reference_site":
        raise ValueError("Reactor or event normalization cannot substitute for elementary rate coefficients")
    if states["surface_activity_convention"] != "fractional site occupation":
        raise ValueError("Unsupported surface activity convention")
    vr = param["validity_range"]
    if not (vr["min_temperature_K"] <= t <= vr["max_temperature_K"] and vr["min_pressure_Pa"] <= p <= vr["max_pressure_Pa"]):
        raise ValueError("Condition outside parameter validity range")
    return t, positive(states["gas_pressure_Pa"], "standard pressure")


def check_law(law, direction, gas):
    if law["method"] not in ("gas_adsorption", "dissociative_adsorption"):
        return
    if gas != direction["reactants"] or not direction["sites_consumed"]:
        raise ValueError("Adsorption needs an incoming gas and explicit vacant sites")
    fragments = sum(direction["products"].values())
    if (law["method"] == "dissociative_adsorption") != (fragments > 1):
        raise ValueError("Adsorption law disagrees with the number of outgoing fragments")


def missing_law_fields(model):
    fields = {"tst": ["kappa"], "gas_adsorption": ["sticking", "mass_u", "capture_area_m2", "gas_species_id"],
              "dissociative_adsorption": ["sticking", "mass_u", "capture_area_m2", "gas_species_id"]}
    return [f"{name}: {field} required for {law['method']}" for name in ("forward", "reverse")
            if (law := model.get(name)) for field in fields.get(law["method"], []) if law.get(field) is None]


def calculate(entry, param, model, species):
    t, p0 = conditions(entry, param, model)
    r = entry["definition"]
    g = entry["energies"]["gibbs_ev"]
    check_closure(g)
    shift = activation_shift(param["coverage_terms"], model.get("coverage_fractions", {}), r["energy_reference_id"])
    gas = {k: gas_powers(r[k], species) for k in ("reactants", "products")}
    rates = {"forward": None, "reverse": None}
    log_eq = None if g["reaction"] is None else -g["reaction"] / (KB * t)
    for name, side, other in (("forward", "reactants", "products"), ("reverse", "products", "reactants")):
        law = model.get(name)
        if name == "reverse" and r["reversible"] is not True:
            if law is not None:
                raise ValueError("Reverse law requires confirmed reversibility")
            continue
        if not law:
            continue
        if name == "reverse" and law["method"] == "from_equilibrium":
            if rates["forward"] and log_eq is not None:
                rates[name] = {"method": "from_equilibrium", "gas_orders": gas[side], "sigma_ln_k": None,
                               "activity_coefficient_s^-1": exp_rate(math.log(rates["forward"]["activity_coefficient_s^-1"]) - log_eq)}
            continue
        if g[name] is None:
            continue
        check_law(law, entry["direction"][name], gas[side])
        rates[name] = coefficient(law, param[name], gas=gas[side], product_gas=gas[other], temperature=t,
                                  standard_pa=p0, barrier=g[name] + shift, degeneracy=param["degeneracy"], sigma=param["uncertainty"])
    residual = None
    if all(rates.values()) and log_eq is not None:
        residual = math.log(rates["forward"]["activity_coefficient_s^-1"]) - math.log(rates["reverse"]["activity_coefficient_s^-1"]) - log_eq
        if abs(residual) > 1e-6:
            raise ValueError("Detailed balance fails on dimensionless activities")
    return rates, {"ln_K_standard": log_eq, "log_ratio_residual": residual}, shift


def select_parameter(entry, parameters, model, species):
    if not model:
        return None
    selected = model["parameter_set_id"]
    supplied = model.get("parameter_input")
    registered = parameters.get(selected)
    if supplied is not None and registered is not None and registered != supplied:
        raise ValueError("Conflicting definition of a network parameter set")
    param = registered or supplied
    r = entry["definition"]
    if not param or param["reaction_id"] != r["reaction_id"] or param["parameter_set_id"] != selected:
        raise ValueError("Rate model refers to an unknown or unrelated parameter set")
    schema = {"$ref": "https://schemas.sbq123.invalid/multiphase/1.0.0/kinetic_parameter.schema.json"}
    _bundle_validator().evolve(schema=schema).validate(param)
    check_parameter_basis(param, entry["energies"], r["energy_reference_id"])
    for term in param["coverage_terms"]:
        other = species.get(term["species_id"])
        if not other or other["phase"] != "surface" or term["coefficient"]["source"] not in param["sources"]:
            raise ValueError("Unbound coverage species or source")
        _check_species_context(other, r)
    return param


def reaction_record(entry, parameters, model, species, version, verified):
    r = entry["definition"]
    param = select_parameter(entry, parameters, model, species)
    gaps = missing(entry, param, model)
    thermal = entry.get("thermochemistry") or {}
    row = {"reaction_id": r["reaction_id"], "network_level": entry["level"], "direction": entry["direction"],
           "site_balance": entry["site_balance"], "surface_ids": r["surface_ids"], "interface_id": r.get("interface_id"),
           "energies": entry["energies"], "ts_local_zpe_ev": ((thermal.get("states") or {}).get("TS") or {}).get("zpe_ev"),
           "parameter_set": param, "model": model, "rates": {"forward": None, "reverse": None}, "equilibrium": None,
           "local_event_missing": [] if (model or {}).get("local_event") else ["Local event pattern, neighbor graph and occurrence normalization"],
           "scientifically_validated": False, "export_eligible": False, "missing": gaps}
    if not model:
        return row
    valid = reviewed(model, version, verified)
    if not valid:
        gaps.append("Scientific model review with verified source artifacts required")
    if entry["level"] not in ("SCIENTIFICALLY_ACCEPTED", "KINETICALLY_ELIGIBLE"):
        gaps.append("Accepted reaction and thermochemistry required")
    absent = missing_law_fields(model)
    gaps.extend(absent)
    if absent or entry["energies"]["temperature_k"] is None or entry["energies"]["gibbs_ev"]["forward"] is None:
        return row
    rates, balance, shift = calculate(entry, param, model, species)
    row.update(rates=rates, equilibrium=balance, coverage_shift_ev=shift)
    for name, rate in rates.items():
        if rate:
            side = entry["direction"][name] or entry["direction"]["forward"]
            rate["rate_kind"] = ("gas_activity_coefficient" if rate["gas_orders"] else
                                 "surface_elementary_rate_constant" if r["surface_ids"] else "elementary_rate_constant")
            rate["activity_orders"] = {"species": side["reactants"], "vacant_sites": side["sites_consumed"]}
    if not rates["forward"] or (r["reversible"] is True and (not rates["reverse"] or balance["log_ratio_residual"] is None)):
        gaps.append("Missing rate or equilibrium evidence for the specified directions")
    row["scientifically_validated"] = valid and entry["level"] in ("SCIENTIFICALLY_ACCEPTED", "KINETICALLY_ELIGIBLE")
    if param["parameter_set_id"] not in entry["parameter_set_ids"] or not reviewed_records([param], verified):
        gaps.append("Selected Phase 1 parameter set requires a network-bound verified review")
    row["export_eligible"] = (not gaps and row["scientifically_validated"] and entry["mkm_status"] == "eligible"
                              and param["eligibility"] == "eligible")
    return row


def generate(network, bindings=None, *, verified_hashes=()):
    check_version(network, "network_version")
    if network.get("format") != "reaction-network/1":
        raise ValueError("Expected a Phase 2.3 reaction network")
    version = network["network_version"]
    validate_finite_tree(bindings)
    if bindings is not None and bindings.get("network_version") != version:
        raise ValueError("Rate model bindings belong to another network")
    rows = (bindings or {}).get("models", [])
    models = {m["reaction_id"]: m for m in rows}
    participants = {r["definition"]["reaction_id"] for r in network["reactions"]}
    if len(rows) != len(models) or models.keys() - participants:
        raise ValueError("Duplicate or unknown reaction model")
    species = {s["species_id"]: s for s in network["species"]}
    parameters = {p["parameter_set_id"]: p for p in network["parameter_sets"]}
    verified = set(verified_hashes)
    verified.update(s["sha256"] for s in network["source_artifacts"] if s["role"] == "verified_evidence")
    records = [reaction_record(r, parameters, models.get(r["definition"]["reaction_id"]), species, version, verified)
               for r in network["reactions"]]
    payload = {"format": "kinetic-dataset/1", "network_version": version, "project_id": network["project_id"],
               "catalog": network["catalog"], "species": network["species"], "source_artifacts": network["source_artifacts"],
               "reactions": records, "export_eligible": bool(records) and all(r["export_eligible"] for r in records),
               "execution_authorized": False}
    return {"dataset_version": sha256_json(payload), **payload}
