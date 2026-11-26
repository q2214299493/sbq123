"""Generate rate records from an immutable network and optional reviewed model bindings."""
import math
from datetime import datetime

from scripts.artifact_io import require_sha256, sha256_json
from scripts.kinetic_parameters.laws import activation_shift, coefficient, exp_rate, gas_powers, positive
from scripts.multiphase_contracts import _bundle_validator, _check_species_context
from scripts.reaction_network.builder import check_parameter_basis, reviewed as reviewed_records, scientific_level
from scripts.reaction_network.catalog import index_records
from scripts.reaction_network.thermodynamics import check_closure, check_cycles
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
    allowed = SOURCES | {"model_prediction"} if "energy_prediction" in model else SOURCES
    for source in sources:
        if source.get("kind") not in allowed or not str(source.get("reference") or "").strip():
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


MOLECULAR_ACTIVITY = "molecules per reference with one site of each inventory"


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
    if states["surface_activity_convention"] not in ("fractional site occupation", MOLECULAR_ACTIVITY):
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


def predicted_view(entry, model, param, network, species):
    """Qualify structural and kinetic inputs separately from the measured TS pathway."""
    from scripts.kinetic_parameters.prediction import evaluate

    # Single-point preflight replays from network evidence alone. An ephemeral
    # --evidence argument cannot grant a prediction which that preflight cannot reproduce.
    verified = {s["sha256"] for s in network["source_artifacts"] if s["role"] == "verified_evidence"}
    if any(s["sha256"] not in verified for s in model["sources"]):
        raise ValueError("Prediction evidence must be bound to the network snapshot")
    r = entry["definition"]
    decision = entry.get("network_review") or {}
    if (decision.get("decision") != "accepted" or decision.get("subject_sha256") != entry.get("subject_sha256")
            or (entry.get("user_confirmation") or {}).get("acceptance_status") == "rejected"
            or entry["level"] == "DRAFT" or entry["site_balance"] is None):
        raise ValueError("MKM prediction requires an independently reviewed balanced reaction")
    index = index_records(dict(network["catalog"], species=network["species"]))
    if scientific_level(r, index, verified, [], False) != "SCIENTIFICALLY_ACCEPTED":
        raise ValueError("MKM prediction lacks reviewed structural context")
    mapping = entry.get("site_mapping") or {}
    if ((mapping.get("electronic_intake") or {}).get("limited_states")
            or (mapping.get("effective") and mapping["assessment"]["evidence_status"] != "AVAILABLE")):
        raise ValueError("Unresolved reaction mapping in prediction context")
    # The existing parameter record supplies the rate law, conditions and prefactors.
    # An explicitly reviewed binding may also supply a barrier-free TST template.
    if (not reviewed_records([param], verified) or param["eligibility"] == "blocked"
            or not r.get("rate_law_id") or param["rate_law_id"] != r["rate_law_id"]):
        raise ValueError("Unreviewed or incompatible prediction rate-law inputs")
    if param["eligibility"] == "draft" and (param["forward"] is not None or param["reverse"] is not None):
        raise ValueError("A draft prediction template may not supply directional rate parameters")
    if (entry.get("thermochemistry") or {}).get("issues"):
        raise ValueError("Unresolved parent thermochemistry issues")
    replaced = {"Missing compatible free energies", "Unresolved transition-state treatment"}
    if not entry["parameter_set_ids"] and model.get("parameter_input") == param:
        replaced.add("Missing kinetic parameters or rate law")
    gaps = [gap for gap in entry["gaps"] if gap not in replaced]
    if gaps:
        raise ValueError("Unresolved prediction context: " + ", ".join(gaps))
    trace = evaluate(entry, model, param, species, network, verified)
    original = entry["energies"]
    for key, expected in (("temperature_k", param["temperature_K"]), ("standard_state", param["standard_state_id"])):
        if original[key] is not None and original[key] != expected:
            raise ValueError("Prediction conflicts with network energy convention")
    electronic = trace["basis_energies_eV"] if trace["energy_basis"] == "electronic" else dict.fromkeys(trace["gibbs_eV"])
    energies = dict(original, gibbs_ev=trace["gibbs_eV"], electronic_ev=electronic,
                    temperature_k=param["temperature_K"], thermal_basis="reviewed_model_prediction",
                    standard_state=param["standard_state_id"])
    return dict(entry, energies=energies), trace


def reaction_record(entry, parameters, model, species, network, verified):
    version = network["network_version"]
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
    predicted = "energy_prediction" in model
    if predicted:
        if not valid:
            raise ValueError("Prediction requires a verified network-bound model review")
        entry, trace = predicted_view(entry, model, param, network, species)
        gaps = []
        row.update(energies=entry["energies"], prediction=trace, missing=gaps, ts_local_zpe_ev=None,
                   local_event_missing=["Energy prediction is qualified for MKM only"])
    if not valid:
        gaps.append("Scientific model review with verified source artifacts required")
    if not predicted and entry["level"] not in ("SCIENTIFICALLY_ACCEPTED", "KINETICALLY_ELIGIBLE"):
        gaps.append("Accepted reaction and thermochemistry required")
    absent = missing_law_fields(model)
    gaps.extend(absent)
    if absent or entry["energies"]["temperature_k"] is None or entry["energies"]["gibbs_ev"]["forward"] is None:
        return row
    rates, balance, shift = calculate(entry, param, model, species)
    row.update(rates=rates, equilibrium=balance, coverage_shift_ev=shift)
    for name, rate in rates.items():
        if rate:
            if predicted:
                rate["sigma_ln_k"] = row["prediction"]["sigma_eV"][name] / (KB * param["temperature_K"])
            side = entry["direction"][name] or entry["direction"]["forward"]
            rate["rate_kind"] = ("gas_activity_coefficient" if rate["gas_orders"] else
                                 "surface_elementary_rate_constant" if r["surface_ids"] else "elementary_rate_constant")
            rate["activity_orders"] = {"species": side["reactants"], "vacant_sites": side["sites_consumed"]}
    if not rates["forward"] or (r["reversible"] is True and (not rates["reverse"] or balance["log_ratio_residual"] is None)):
        gaps.append("Missing rate or equilibrium evidence for the specified directions")
    if predicted:
        row["export_eligible"] = not gaps
        return row
    row["scientifically_validated"] = valid and entry["level"] in ("SCIENTIFICALLY_ACCEPTED", "KINETICALLY_ELIGIBLE")
    if param["parameter_set_id"] not in entry["parameter_set_ids"] or not reviewed_records([param], verified):
        gaps.append("Selected Phase 1 parameter set requires a network-bound verified review")
    row["export_eligible"] = (not gaps and row["scientifically_validated"] and entry["mkm_status"] == "eligible"
                              and param["eligibility"] == "eligible")
    return row


def _bound_inputs(network, bindings, verified_hashes):
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
    return models, parameters, species, verified


def _dataset(network, records):
    version = network["network_version"]
    if any("prediction" in row for row in records):
        references = {row["parameter_set"]["energy_reference_id"] for row in records if row["export_eligible"]}
        if len(references) > 1:
            raise ValueError("Mixed prediction network requires a common energy reference")
        # The derived and fixed rows represent one physical mechanism at this point.
        # Use one Gibbs convention for cycle closure even when the data origins differ.
        by_id = {r["reaction_id"]: r for r in records}
        check_cycles([dict(e, energies=dict(by_id[e["definition"]["reaction_id"]]["energies"], thermal_basis="MKM point"))
                      for e in network["reactions"] if e["definition"]["reaction_id"] in by_id])
    payload = {"format": "kinetic-dataset/1", "network_version": version, "project_id": network["project_id"],
               "catalog": network["catalog"], "species": network["species"], "source_artifacts": network["source_artifacts"],
               "reactions": records, "export_eligible": bool(records) and all(r["export_eligible"] for r in records),
               "execution_authorized": False}
    return {"dataset_version": sha256_json(payload), **payload}


def generate(network, bindings=None, *, verified_hashes=()):
    models, parameters, species, verified = _bound_inputs(network, bindings, verified_hashes)
    records = [reaction_record(r, parameters, models.get(r["definition"]["reaction_id"]), species, network, verified)
               for r in network["reactions"]]
    return _dataset(network, records)


def _thermal_input(entry, intake, review, phase):
    """Re-bind raw or precomputed state evidence using the thermochemistry and network owners."""
    from scripts.reaction_network.thermodynamics import thermal_evidence
    from scripts.thermochemistry.engine import calculate as calculate_thermochemistry, ts_binding

    definition = entry["definition"]
    calc = entry.get("thermochemistry")
    route = "network_state_record" if calc else "network_energy_terms"
    if intake is not None:
        calc = calculate_thermochemistry([intake], ts_review=review, phase=phase)
        route = "state_intake"
    energies = thermal_evidence(definition, calc)
    complete = all(v is not None for v in energies["gibbs_ev"].values())
    return energies, calc, {
        "route": route, "status": "available" if complete else "partial",
        "energies": energies, "closure_checked": complete,
        "states": (calc or {}).get("states"), "state_free_energy_ev": (calc or {}).get("state_free_energy_ev"),
        "electronic_sources": (calc or {}).get("electronic_sources"),
        "closure_residual_ev": ((calc or {}).get("reaction") or {}).get("closure_residual_ev"),
        "issues": (calc or {}).get("issues", []),
        "ts_review": ts_binding(review) if intake is not None and review is not None else entry.get("ts_review"),
    }


def qualify_network_rows(network, bindings, *, conservation, intake=None, review=None, phase=None,
                         verified_hashes=(), input_errors=None, intake_bound=False):
    """Qualify each row independently. Only a complete, unmodified network can yield an engine handoff."""
    from jsonschema import ValidationError
    from scripts.reaction_network.builder import directions

    models, parameters, species, verified = _bound_inputs(network, bindings, verified_hashes)
    version = network["network_version"]
    rows, records = {}, []
    for entry in network["reactions"]:
        definition = entry["definition"]
        rid = definition["reaction_id"]
        state_ids = definition.get("state_identities") or {
            "IS": definition.get("initial_structure_id"), "TS": definition.get("ts_id"),
            "FS": definition.get("final_structure_id"),
        }
        errors = (input_errors or {}).get(rid, {})
        row = rows[rid] = {
            "network_version": version, "reaction_id": rid, "state_identities": state_ids,
            "direction": entry["direction"], "phase_ids": definition.get("phase_ids"),
            "surface_ids": definition.get("surface_ids"), "interface_id": definition.get("interface_id"),
            "required_sites": definition.get("required_sites"), "conservation": conservation[rid],
            "provenance": definition.get("provenance", []), "thermochemistry": None, "kinetics": None,
            "status": "blocked", "missing": list(errors.values()),
        }
        if "invalid" in conservation[rid]:
            row["status"] = "invalid_input"
            row["missing"].append(conservation[rid]["invalid"])
            continue
        try:
            if directions(definition) != entry["direction"]:
                raise ValueError("Snapshot direction differs from reaction definition")
            if "site_balance" in conservation[rid] and conservation[rid]["site_balance"] != entry["site_balance"]:
                raise ValueError("Snapshot site balance differs from reaction inventories")
            state_input = intake if intake and intake["reaction_id"] == rid else None
            if not ({"intake", "ts_review"} & errors.keys()):
                energies, calc, summary = _thermal_input(entry, state_input, review, phase)
                row["thermochemistry"] = summary
            if errors:
                row["status"] = "blocked" if all(e.endswith(": missing_local_file") for e in errors.values()) else "invalid_input"
                continue
            archived_review = entry.get("ts_review")
            review_changed = (state_input is not None and review is not None and archived_review is not None
                              and archived_review["review_sha256"] != sha256_json(review))
            changed_evidence = state_input is not None and (not intake_bound or review_changed or
                               (entry["level"] == "KINETICALLY_ELIGIBLE" and calc != entry.get("thermochemistry")))
            if energies != entry["energies"] or changed_evidence:
                row["missing"].append("State evidence differs from this network version; bind a new snapshot and review")
                continue
            replay = dict(entry, energies=energies, thermochemistry=calc)
            kinetic = reaction_record(replay, parameters, models.get(rid), species, network, verified)
            records.append(kinetic)
            row["kinetics"] = {k: kinetic[k] for k in ("rates", "equilibrium", "parameter_set", "export_eligible",
                                                       "local_event_missing", "scientifically_validated")}
            row["kinetics"]["detailed_balance_established"] = (kinetic["equilibrium"] or {}).get("log_ratio_residual") is not None
            row["kinetics"]["directions"] = {
                name: {"status": "available" if rate else
                       "not_applicable" if name == "reverse" and definition["reversible"] is False else "unknown",
                       "unit": "s^-1" if rate else None}
                for name, rate in kinetic["rates"].items()
            }
            row["kinetics"]["local_event"] = (kinetic["model"] or {}).get("local_event")
            if "prediction" in kinetic:
                row["kinetics"]["prediction"] = kinetic["prediction"]
                row["kinetics"]["local_event"] = None
            row["kinetics"]["model_sources"] = (kinetic["model"] or {}).get("sources", [])
            row["missing"] = list(dict.fromkeys(conservation[rid]["unresolved"] + summary["issues"] + kinetic["missing"]))
            if kinetic["export_eligible"] and not row["missing"]:
                row["status"] = "qualified"
        except (ValueError, TypeError, KeyError, IndexError, ValidationError) as exc:
            row["status"] = "invalid_input"
            row["missing"].append(str(exc))
    dataset = _dataset(network, records) if len(records) == len(rows) else None
    return rows, dataset
