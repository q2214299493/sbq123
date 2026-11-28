"""Checked rates at one measured state, for numerical consumers including Reactor."""
from copy import deepcopy
from pathlib import Path

from sbq123.common.evidence import trust
from sbq123.common.artifacts.artifact_io import sha256_json
from sbq123.common.evidence.kinetic_data.analysis_evidence import reviewed_mapping, reviewed_rates, same_json_content
from sbq123.common.kinetic_model.kinetic_parameters.rate_normalization import basis_identity, convert_checked_rate
from sbq123.common.kinetic_model.rate_output_v2 import read_bound_rate_network, validate_conversion_bases


def local_species_sources(payload, network_path, *, conditions, target, evidence=None, rate_evidence=None):
    """Consume an independently replayed benchmark; conversions require a separate approval."""
    # Own the complete mutable request before reading or validating any evidence.
    # Paths are immutable locators. The evidence readers authenticate the bytes they use.
    payload, conditions, target, evidence, rate_evidence = deepcopy(
        (payload, conditions, target, evidence, rate_evidence))
    code = "rate_evidence_unverified"
    try:
        rates, digest, replay_id = reviewed_rates(payload, rate_evidence)
        code = "network_evidence_unverified"
        if not isinstance(network_path, (str, Path)):
            raise ValueError("Missing reaction network file")
        network_sha256 = rates["provenance"]["network"]["sha256"]
        network = read_bound_rate_network(rates, network_path, expected_network_sha256=network_sha256)
        code = "conditions_mismatch"
        if not same_json_content(conditions, rates["conditions"]):
            raise ValueError("Local conditions differ from the reviewed rate observation")
        code = "invalid_normalization"
        basis = rates["native_normalization"]
        validate_conversion_bases(basis, target)
        if target["reference_scope"] != basis["reference_scope"]:
            raise ValueError("Target scope differs from the bound network")
        mapping = mapping_id = None
        if evidence is not None or basis_identity(target) != basis_identity(basis):
            code = "conversion_approval_unverified"
            mapping, mapping_id = reviewed_mapping(
                evidence, digest, network_sha256, conditions, basis, target)
        code = "source_conversion_unavailable"
        phases = {s["species_id"]: s["phase"] for s in network["species"]}
        sources = {}
        for row in rates["source_terms"]["species"]:
            sid = row["species_id"]
            value = convert_checked_rate(row["net_production_rate"], "species_source", basis, target, mapping)
            if value["status"] != "available":
                raise ValueError(f"Missing source conversion for {sid}: {value['missing']}")
            sources[sid] = {"phase": phases[sid], "value": value["value"]}
    except (OSError, ValueError) as exc:
        return {"status": "insufficient_evidence", "reason_code": code, "reason": str(exc), "species": None}
    result = {
        "status": "available", "rate_dataset_id": rates["output_binding"]["dataset_id"],
        "rate_sha256": digest, "rate_review_sha256": replay_id, "mapping_approval_sha256": mapping_id,
        "evidence_scope": "reviewed_project" if trust.approved("rate_review", replay_id) else "archived_software_benchmark", "conditions": conditions,
        "basis": target, "species": sources,
    }
    result["result_sha256"] = sha256_json(result)
    return result
