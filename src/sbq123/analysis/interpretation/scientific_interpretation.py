"""Report what a numerical V3.1 comparison supports at its recorded conditions."""
from copy import deepcopy

from sbq123.common.artifacts.artifact_io import sha256_json


def summarize_comparison(result):
    result = deepcopy(result)
    if result.get("format") != "mkm-kmc-comparison-result/1":
        raise ValueError("Expected a V3.1 comparison")
    digest = sha256_json({k: v for k, v in result.items() if k != "comparison_sha256"})
    if digest != result.get("comparison_sha256"):
        raise ValueError("Comparison content differs from its identity")
    observations = [{"observable": row["observable"], "compatibility": row["compatibility"],
                     "difference": row["difference"], "reasons": row["reasons"]}
                    for row in result["comparisons"]]
    return {"comparison_sha256": digest, "observations": observations,
            "scope": result["interpretation"], "uncertainty": result["uncertainty"]}


def interpret_observation(observation, *, expected_sha256):
    """Describe an observation using the identity retained by its trusted producer."""
    record = deepcopy(observation)
    identity = record.pop("observation_sha256", None)
    if record.get("format") != "kinetic-observation/1" or sha256_json(record) != identity or identity != expected_sha256:
        raise ValueError("Observation differs from expected calculation")
    limits = {
        "mkm_local_source": "Signed species source at the measured operating point",
        "kmc_sampled_source": "Sample-specific species source; independent-seed convergence unestablished",
        "instantaneous_gas_balance": "Instantaneous isothermal well-mixed gas accumulation in mol/s",
    }
    return dict(observation_sha256=identity, description=limits[record["kind"]], **record)
