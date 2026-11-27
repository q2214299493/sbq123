"""Optional isothermal, well-mixed gas balance at a single evidenced operating point."""
from copy import deepcopy

from scripts.artifact_io import sha256_json
from scripts.kinetic_data.analysis_contracts import local_species_sources
from scripts.kinetic_data.observations import _observation
from scripts.scientific_validation import finite_number


def gas_accumulation(payload, network_path, *, conditions, volume_m3, target, evidence,
                     inlet_mol_s, outlet_mol_s, rate_evidence=None):
    """Compute instantaneous dN/dt in mol/s on the named reactor-volume basis."""
    # Own the flows here. Analysis takes the shared inputs into its snapshot.
    inlet_mol_s, outlet_mol_s = deepcopy((inlet_mol_s, outlet_mol_s))
    local = local_species_sources(payload, network_path, conditions=conditions, target=target,
                                  evidence=evidence, rate_evidence=rate_evidence)
    volume = finite_number(volume_m3, "reactor volume", positive=True)
    if local["status"] == "insufficient_evidence":
        return {"status": local["status"], "reason_code": local["reason_code"],
                "reason": local["reason"], "accumulation_mol_s": None}
    target = local["basis"]
    conditions = local["conditions"]
    if (target["basis_kind"], target["extent_unit"], target["denominator_unit"],
            target["time_unit"], target["denominator_value"]) != ("reactor_volume", "mol", "m³", "s", 1):
        return {"status": "insufficient_evidence", "reason_code": "invalid_reactor_basis",
                "reason": "Gas balance requires mol/(m³ s) on the named reactor volume", "accumulation_mol_s": None}
    if conditions.get("partial_pressures") is None:
        return {"status": "insufficient_evidence", "reason_code": "missing_gas_composition",
                "reason": "Local gas composition is required", "accumulation_mol_s": None}
    gases = {k: v["value"] for k, v in local["species"].items() if v["phase"] == "gas"}
    if not gases or gases.keys() != inlet_mol_s.keys() or gases.keys() != outlet_mol_s.keys():
        raise ValueError("Supply inlet and outlet flows for the same modeled gas species")
    rates = {}
    for sid, source in gases.items():
        inlet = finite_number(inlet_mol_s[sid], "inlet mol/s", nonnegative=True)
        outlet = finite_number(outlet_mol_s[sid], "outlet mol/s", nonnegative=True)
        rates[sid] = finite_number(inlet - outlet + volume * source, "gas accumulation")
    result = {
        "status": "available", "rate_dataset_id": local["rate_dataset_id"],
        "rate_sha256": local["rate_sha256"], "rate_review_sha256": local["rate_review_sha256"],
        "mapping_approval_sha256": local["mapping_approval_sha256"], "evidence_scope": local["evidence_scope"],
        "conditions": conditions, "basis": target, "reactor_volume_m3": volume,
        "inlet_mol_s": inlet_mol_s, "outlet_mol_s": outlet_mol_s, "accumulation_mol_s": rates,
    }
    result["result_sha256"] = sha256_json(result)
    return result


def balance_observation(payload, network_path, **request):
    """Describe a validated instantaneous balance, preserving its volumetric context."""
    rates = deepcopy(payload)
    result = gas_accumulation(rates, network_path, **request)
    if result["status"] != "available":
        return result
    return _observation(rates, result, "instantaneous_gas_balance", {
        "accumulation_mol_s": result["accumulation_mol_s"], "reactor_volume_m3": result["reactor_volume_m3"],
        "inlet_mol_s": result["inlet_mol_s"], "outlet_mol_s": result["outlet_mol_s"],
    })
