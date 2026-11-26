"""Report what a numerical V3.1 comparison supports at its recorded conditions."""
from scripts.artifact_io import sha256_json


def summarize_comparison(result):
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
