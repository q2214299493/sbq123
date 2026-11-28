"""Descriptive observations from an evidence-checked source or gas balance."""
from copy import deepcopy

from sbq123.common.artifacts.artifact_io import sha256_json
from sbq123.common.evidence.kinetic_data.analysis_contracts import local_species_sources


def _observation(rates, result, kind, values):
    observation = {
        "format": "kinetic-observation/1", "kind": kind, "engine": rates["engine"],
        "run_id": rates["output_binding"]["run_id"], "conditions": result["conditions"],
        "basis": result["basis"], "network_version": rates["network_version"],
        "native_output": rates["provenance"]["native_output"],
        "dataset_version": rates["dataset_version"], "values": values,
        "evidence_scope": result["evidence_scope"], "result_sha256": result["result_sha256"],
        "rate_sha256": result["rate_sha256"], "rate_review_sha256": result["rate_review_sha256"],
        "mapping_approval_sha256": result["mapping_approval_sha256"],
    }
    observation["observation_sha256"] = sha256_json(observation)
    return observation


def rate_observation(payload, network_path, **request):
    """Qualify the complete rate artifact through the same approval chain as Analysis."""
    rates = deepcopy(payload)
    result = local_species_sources(rates, network_path, **request)
    if result["status"] != "available":
        return result
    kind = {"CATKINAS": "mkm_local_source", "Zacros": "kmc_sampled_source"}[rates["engine"]["name"]]
    return _observation(rates, result, kind, result["species"])
