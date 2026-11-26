"""Calculate traceable components from selected Phase 2.1 intake records."""
from __future__ import annotations

import math

from scripts.artifact_io import sha256_json
from scripts.kinetic_data.reaction_intake import AVAILABLE, STATES, report
from scripts.scientific_validation import validate_finite_tree
from scripts.thermochemistry.harmonic import add_ideal_gas, harmonic


def ts_binding(review):
    """Adapt the existing endpoint audit, or consume an equivalent documented Grade A review."""
    if review is None:
        return {}
    if "ts_mode_review" not in review:
        return review
    source = review["scientific_review_sources"]["TS"]
    mode = review["ts_mode_review"]
    if source["grade"] != mode["grade"] or source["geometry_status"] != "pass":
        raise ValueError("TS audit and scientific review disagree")
    state = review["states"]["TS"]
    return {"grade": source["grade"], "review_reference": source["ts_validation_id"],
            "structure_identity": state["structure"]["sha256"], "assignment": mode["assignment"],
            "mode_index": mode["index"], "frequencies_cm1": review["signed_modes_cm1"],
            "atom_map": state["frequency_active_atoms"], "constraints": state["frequency_constraints"],
            "source_artifact_hash": state["frequency_output"]["sha256"],
            "correction_review": review.get("correction_review")}


def check_ts_correction(record, review, operation):
    value = record["value"]
    if not isinstance(review, dict) or review.get("record_id") != record["id"]:
        raise ValueError("Missing TS correction review for this record")
    if review.get("value_sha256") != sha256_json(value) or review.get("thermal_basis") != value["thermal_basis"]:
        raise ValueError("TS correction values or thermal basis differ from the review")
    description = review.get("model_description")
    if review.get("model_phase") not in ("adsorbate", "gas") or not isinstance(description, str) or not description.strip():
        raise ValueError("TS correction review needs the model and its phase scope")
    if (review.get("reaction_coordinate_treatment") != "excluded_from_partition_function"
            or review.get("imaginary_mode_excluded") is not True):
        raise ValueError("TS correction review must confirm exclusion of the assigned imaginary mode")
    if operation == "zpe":
        return
    if review.get("gibbs_includes_zpe") is not True or review.get("enthalpy_increment_excludes_zpe") is not True:
        raise ValueError("TS correction review must confirm Gibbs includes ZPE once and thermal enthalpy excludes ZPE")
    if review.get("temperature_k") != value["temperature_k"] or review.get("standard_state") != value["standard_state"]:
        raise ValueError("TS correction temperature or standard state differs from the review")


def reviewed_mode(record, binding, operation="thermochemistry"):
    v = record["value"]
    if (binding.get("grade") != "A" or not binding.get("review_reference") or not binding.get("assignment")
            or binding.get("structure_identity") != v["structure_identity"]):
        raise ValueError("Missing matching Grade A TS structure and assigned reaction-coordinate review")
    if record["kind"] == "corrections":
        check_ts_correction(record, binding.get("correction_review"), operation)
        return None
    digest = record.get("provenance", {}).get("source_artifact_hash")
    if digest and binding.get("source_artifact_hash") != digest:
        raise ValueError("TS spectrum hash differs from the reviewed artifact")
    if binding.get("frequencies_cm1") != v["frequencies_cm1"] or binding.get("atom_map") != v["atom_map"]:
        raise ValueError("TS frequencies or active atom mapping differ from the review")
    if binding.get("constraints") != v["constraints"]:
        raise ValueError("TS constraints differ from the reviewed Hessian")
    index = binding.get("mode_index")
    if type(index) is not int or not 1 <= index <= len(v["frequencies_cm1"]) or v["frequencies_cm1"][index-1] >= 0:
        raise ValueError("Review does not identify the imaginary reaction coordinate")
    return index


def precomputed(record, operation):
    value = record["value"]
    model = record.get("thermal_model", {})
    if value["zpe_ev"] < 0:
        raise ValueError("Negative precomputed ZPE")
    output = {key: None for key in ("thermal_enthalpy_ev", "entropy_ev_per_k", "gibbs_correction_ev", "temperature_k")}
    output.update(zpe_ev=value["zpe_ev"], zpe_sigma_ev=model.get("zpe_sigma_ev"), gibbs_sigma_ev=None)
    if operation == "zpe":
        return output
    output.update({key: value[key] for key in output if key in value})
    expected = value["zpe_ev"] + value["thermal_enthalpy_ev"] - value["temperature_k"] * value["entropy_ev_per_k"]
    if not math.isclose(expected, value["gibbs_correction_ev"], abs_tol=1e-6, rel_tol=1e-9):
        raise ValueError("Precomputed G differs from ZPE + thermal enthalpy increment - T*S")
    output["gibbs_sigma_ev"] = model.get("gibbs_sigma_ev")
    return output


def condition(fields, by_id, kind, name):
    field = fields[f"reaction.{kind}"]
    if not field["usable"]:
        return None
    if field["selected"]:
        return by_id[field["selected"]]["value"][name]
    return field.get("value")


def state_correction(record, binding, operation, conditions, default_phase):
    value = record["value"]
    model = record.get("thermal_model", {})
    phase = model.get("phase", default_phase)
    index = reviewed_mode(record, binding, operation) if record["state"] == "TS" else None
    temp, standard, pressure = conditions
    if record["kind"] == "corrections":
        if model.get("pressure_pa") is not None and pressure is not None and model["pressure_pa"] != pressure:
            raise ValueError("Precomputed correction pressure differs from the requested pressure")
        result = precomputed(record, operation)
        if record["state"] == "TS":
            review = binding["correction_review"]
            if phase and phase != review["model_phase"]:
                raise ValueError("TS correction model phase differs from the review")
            phase = review["model_phase"]
            result["correction_review"] = review
    else:
        result = harmonic(value["frequencies_cm1"], temperature=temp if operation != "zpe" else None,
                          scale=model.get("frequency_scale", 1), scaling_reference=model.get("scaling_reference"),
                          excluded_mode=index, mode_sigma_cm1=model.get("independent_mode_sigma_cm1"))
        if operation != "zpe" and temp is not None:
            if phase not in ("gas", "adsorbate"):
                raise ValueError("Specify gas or adsorbate for finite-temperature raw frequencies")
            if phase == "gas":
                n = len(value["atom_map"])
                expected = 3 * n - (5 if len(model.get("moments_amu_angstrom2", [])) == 1 else 6)
                if expected != len(value["frequencies_cm1"]):
                    raise ValueError("Gas rigid-rotor model needs the full internal vibrational subspace")
                add_ideal_gas(result, model, pressure)
        result.update(atom_map=value["atom_map"], constraints=value["constraints"], method=value["method"])
    result.update(record_id=record["id"], route=record["kind"], thermal_basis=value["thermal_basis"],
                  structure_identity=value["structure_identity"], phase=phase, standard_state=value.get("standard_state", standard),
                  provenance=record.get("provenance", {}), uncertainty=record.get("uncertainty"),
                  validation=record["validation"], acceptance=record["acceptance"])
    if record["state"] == "TS":
        result["ts_review_reference"] = binding["review_reference"]
    if model:
        result["thermal_model"] = model
    validate_finite_tree(result, "thermochemistry result")
    return result


def differences(values):
    if any(values[s] is None for s in STATES):
        return None
    return {"forward": values["TS"] - values["IS"], "reverse": values["TS"] - values["FS"],
            "reaction": values["FS"] - values["IS"]}


def validate_subspace(record, structure, phase):
    """Check the spectrum against this geometry's Hessian, in its own atom numbering."""
    v = record["value"]
    model = record.get("thermal_model", {})
    if v["structure_identity"] != structure["value"]["identity"]:
        raise ValueError("Hessian and selected structure identity differ")
    indices = v["atom_map"]
    dimension = v["expected_modes"]
    if dimension != len(v["frequencies_cm1"]) or dimension > 3 * len(indices):
        raise ValueError("Spectrum dimension disagrees with its Hessian active degrees of freedom")
    supplied_flags = [f for f in (structure.get("thermal_model", {}).get("hessian_cartesian_flags"),
                                  model.get("hessian_cartesian_flags")) if f is not None]
    prefix = "Cartesian flags by atom: "
    if v["constraints"].startswith(prefix):
        supplied_flags.append(v["constraints"][len(prefix):].split())
    if not supplied_flags:
        validation = record["validation"]
        return (validation["validation_status"] == "validated" and bool(validation.get("validation_method"))
                and {"atom_map", "hessian_dimension", "structure_identity"} <= set(validation["validated_properties"]))
    flags = supplied_flags[0]
    if any(other != flags for other in supplied_flags[1:]):
        raise ValueError("Spectrum Cartesian constraints disagree with the structure's Hessian flags")
    if any(len(row) != 3 or set(row) - {"T", "F"} for row in flags):
        raise ValueError("Invalid Hessian Cartesian flags")
    if sorted(indices) != [i for i, row in enumerate(flags) if "T" in row]:
        raise ValueError("State active atom map disagrees with its structure's Hessian flags")
    expected = sum(row.count("T") for row in flags)
    if model.get("phase", phase) == "gas":
        if any(row != "TTT" for row in flags):
            raise ValueError("Gas internal-mode projection requires the full molecule")
        # Geometry fixes the 5/6 projected coordinates. Moments may be absent for ZPE-only data.
        moments = model.get("moments_amu_angstrom2")
        reductions = {5, 6} if moments is None else {5 if len(moments) == 1 else 6}
        if expected - dimension not in reductions:
            raise ValueError("Gas spectrum dimension disagrees with the internal-mode projection")
    elif dimension != expected:
        raise ValueError("Spectrum dimension disagrees with the structure's active Cartesian degrees of freedom")
    return True


def compare_subspaces(corrections):
    raw = [r for r in corrections.values() if r and r["route"] == "spectrum"]
    if len({r["scale"] for r in raw}) > 1:
        undocumented = [r["record_id"] for r in raw if not (r["scaling_reference"] or "").strip()]
        if undocumented:
            return "Different frequency scales need a rationale for each state: " + ", ".join(undocumented)
    scopes = {(tuple(r["atom_map"]), r["constraints"], len(r["frequencies_cm1"])) for r in raw}
    if len(scopes) > 1:
        missing = [r["record_id"] for r in raw if not r["subspace_verified"]]
        if missing:
            return "Differing active maps or subspaces need state-specific mapping evidence for " + ", ".join(missing)
    return None


def reaction_result(energies, corrections, energy_sigmas, independent):
    elec = differences(energies)
    thermal = differences({s: corrections[s]["gibbs_correction_ev"] for s in STATES})
    free = differences({s: energies[s] + corrections[s]["gibbs_correction_ev"] for s in STATES})
    residual = free["forward"] - free["reverse"] - free["reaction"]
    if abs(residual) > 1e-9:
        raise ValueError("Free-energy closure failed")
    sigmas = {}
    for label, a, b in (("forward", "TS", "IS"), ("reverse", "TS", "FS"), ("reaction", "FS", "IS")):
        errors = [energy_sigmas[a], energy_sigmas[b], corrections[a]["gibbs_sigma_ev"], corrections[b]["gibbs_sigma_ev"]]
        sigmas[label] = math.hypot(*errors) if independent and None not in errors else None
    return {"electronic_ev": elec, "thermal_ev": thermal, "free_energy_ev": free, "closure_residual_ev": residual,
            "free_energy_sigma_ev": sigmas, "assume_independent_energy_errors": independent}


def assess_state(record, structure, binding, operation, conditions, phase):
    raw = record["kind"] == "spectrum"
    try:
        verified = validate_subspace(record, structure, phase) if raw else False
    except ValueError as error:
        return None, str(error)
    issue = None
    try:
        result = state_correction(record, binding, operation, conditions, phase)
    except ValueError as error:
        issue = str(error)
        if operation == "zpe":
            return None, issue
        try:
            result = state_correction(record, binding, "zpe", conditions, phase)
        except ValueError:
            return None, issue
    if raw:
        result["subspace_verified"] = verified or record["state"] == "TS"
    return result, issue


def calculate(documents, *, operation="thermochemistry", ts_review=None, phase=None, independent_errors=False):
    if operation not in ("zpe", "thermochemistry"):
        raise ValueError("Expected zpe or thermochemistry")
    intake = report(documents, operation)
    fields = intake["fields"]
    by_id = {r["id"]: r for doc in documents for r in doc["records"]}
    binding = ts_binding(ts_review)
    conditions = tuple(condition(fields, by_id, k, n) for k, n in
                       (("temperature", "kelvin"), ("standard_state", "convention"), ("pressure", "pascal")))
    corrections = {}
    energies = {}
    energy_sigmas = {}
    sources = {}
    limited = []
    problems = list(intake["unresolved_fields"])
    for state in STATES:
        energy = by_id.get(fields[f"{state}.electronic_energy"]["selected"], {})
        energies[state] = energy.get("value", {}).get("value_ev")
        energy_sigmas[state] = energy.get("thermal_model", {}).get("electronic_sigma_ev")
        sources[state] = {k: energy.get(k) for k in ("id", "value", "provenance", "uncertainty", "validation", "acceptance")}
        route = intake["thermal_routes"][state]
        corrections[state] = None
        if not route or not fields[f"{state}.structure"]["usable"]:
            continue
        record = by_id[fields[route]["selected"]]
        structure = by_id[fields[f"{state}.structure"]["selected"]]
        corrections[state], issue = assess_state(record, structure, binding, operation, conditions, phase)
        if issue:
            problems.append(f"{state}: {issue}")
    mismatch = compare_subspaces(corrections)
    if mismatch:
        problems.append(mismatch)
    for key, field in fields.items():
        if field["status"] != "NOT_REQUIRED_FOR_CURRENT_OPERATION" and field["usable"] and field["evidence_status"] != AVAILABLE:
            limited.append(key)
    reaction = None
    if any(r and r.get("gas_contributions") for r in corrections.values()) and fields["reaction.pressure"]["evidence_status"] != AVAILABLE:
        limited.append("reaction.pressure")
    if not problems and operation == "thermochemistry":
        reaction = reaction_result(energies, corrections, energy_sigmas, independent_errors)
    state_g = {}
    for state, correction in corrections.items():
        g = correction.get("gibbs_correction_ev") if correction else None
        state_g[state] = (energies[state] + g if g is not None and energies[state] is not None
                          and correction.get("standard_state") else None)
    result = {"reaction_id": intake["reaction_id"], "operation": operation, "electronic_ev": differences(energies),
              "electronic_sources": sources, "states": corrections, "state_free_energy_ev": state_g,
              "reaction": reaction, "issues": problems, "unresolved_one_of": intake["unresolved_one_of"],
              "intake_diagnostics": {key: fields[key] for key in intake["unresolved_fields"]},
              "intake_warnings": intake["warnings"], "condition_values": dict(zip(("temperature_k", "standard_state", "pressure_pa"), conditions)),
              "scoped_unverified_inputs": limited, "status": "partial" if problems else "scoped_estimate" if limited else "complete",
              "execution_authorized": False}
    validate_finite_tree(result, "reaction thermochemistry")
    return result
