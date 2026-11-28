"""Network projection of explicit cross-phase scope, evidence and independent engine gates."""
from sbq123.common.reaction_network.reaction_network.catalog import check_record_field


def validate_scope_fields(record):
    if record["reaction_type"] == "cross_phase_elementary":
        if "interface_ids" in record:
            raise ValueError("One cross-phase event supports one declared contact")
        for field in ("phase_ids", "surface_ids", "interface_id"):
            if field not in record:
                raise ValueError(f"Missing explicit cross-phase scope field {field}")
            check_record_field("reaction", field, record[field])
    if "ts_species_id" in record:
        if record["reaction_type"] != "cross_phase_elementary":
            raise ValueError("ts_species_id requires a cross-phase elementary reaction")
        check_record_field("reaction", "ts_species_id", record["ts_species_id"])


def energy_status(values, needed):
    if all(values[k] is not None for k in needed):
        return "supplied"
    return "partial" if any(v is not None for v in values.values()) else "missing"


def qualification(r, index, site_balance, energies, needed, params, parameter_gaps):
    phase_owners_known = all(index["surfaces"][s].get("phase_id") is not None for s in r["surface_ids"])
    participants = (index["species"][s] for s in r["reactants"].keys() | r["products"].keys())
    chemistry_known = all(s.get("composition") is not None and s.get("charge") is not None for s in participants)
    return {
        "structurally_represented": True,
        "interface_scope_verified": True if r.get("interface_id") and phase_owners_known else None,
        "stoichiometrically_valid": True if site_balance is not None and chemistry_known else None,
        "electronic_evidence": energy_status(energies["electronic_ev"], needed),
        "thermal_evidence": energy_status(energies["gibbs_ev"], needed),
        "kinetic_parameterization": "supplied" if not parameter_gaps else "partial" if params else "missing",
    }


def record_review_status(result, accepted_levels):
    if "cross_phase_qualification" in result:
        accepted = result["level"] in accepted_levels
        rejected = ((result["network_review"] or {}).get("decision") == "rejected"
                    or (result["scientific_review"] or {}).get("status") == "rejected")
        result["cross_phase_qualification"].update(
            scientific_review="accepted" if accepted else "rejected" if rejected else "unaccepted",
            mkm_eligibility="requires_native_qualification" if result["mkm_status"] == "eligible" else "blocked",
            kmc_eligibility="unassessed" if accepted else "blocked",
        )
