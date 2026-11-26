"""Resolve scientific analysis evidence against release-controlled review identities."""
from pathlib import Path

from scripts.artifact_io import canonical_json, require_sha256, sha256_file, sha256_json
from scripts.multiphase_contracts import read_artifact
from scripts.rate_output_v2 import validate_conversion_bases
from scripts.runtime_resources import resource_path


# B.1 independently replayed outputs. The acceptance scope is the archived software benchmarks.
_REPLAY_PATH = "reports/multiphase/stage_b1_5/independent_replay.json"
_REPLAY_SHA256 = "5eeb6ddcdcfdc7c0f87ff22c66916728122ad4427b0774c04be640d04ca4d5bb"


def _locator(reference, expected):
    if not isinstance(reference, dict) or not isinstance(reference.get("path"), (str, Path)):
        raise ValueError("Missing evidence file reference")
    if require_sha256(reference.get("sha256"), label="Evidence digest") != expected:
        raise ValueError("Evidence digest differs from independent review")
    return Path(reference["path"])


def same_json_content(left, right):
    try:
        return canonical_json(left) == canonical_json(right)
    except TypeError as exc:
        raise ValueError("Expected JSON content") from exc


def reviewed_rates(payload, reference):
    """The caller's digest selects a replay row; only the release pin authenticates it."""
    replay, _ = read_artifact(resource_path(_REPLAY_PATH), expected_sha256=_REPLAY_SHA256)
    if not isinstance(reference, dict):
        raise ValueError("Missing rate dataset reference")
    if "approval" in reference:
        path = _locator(reference["approval"], _REPLAY_SHA256)
        read_artifact(path, expected_sha256=_REPLAY_SHA256)
    selector = require_sha256(reference.get("sha256"), label="Rate digest")
    matches = [row for engine in replay["replay"].values() for row in engine["runs"]
               if row["output_sha256"] == selector]
    if len(matches) != 1:
        raise ValueError("Rate artifact has no unique independently reviewed replay")
    row, = matches
    path = _locator(reference, row["output_sha256"])
    rates, digest = read_artifact(path, expected_sha256=row["output_sha256"])
    if not same_json_content(rates, payload):
        raise ValueError("Submitted rate content differs from the reviewed dataset")
    if (rates["provenance"]["network"] != row["provenance"]["network"]
            or rates["network_version"] != row["network_version"]
            or rates["output_binding"]["dataset_id"] != row["dataset_id"]):
        raise ValueError("Rate identity or network differs from the reviewed replay row")
    return rates, digest, _REPLAY_SHA256


# No production conversion approval has been issued. A deployment may pin a reviewed
# receipt here in a separately reviewed release. Requests cannot configure this pin.
_MAPPING_APPROVAL_SHA256 = None


def reviewed_mapping(reference, rate_sha256, network_sha256, conditions, basis, target):
    """Authenticate the detached approval before opening the caller's mapping."""
    if _MAPPING_APPROVAL_SHA256 is None:
        raise ValueError("No independent conversion approval is installed")
    if not isinstance(reference, dict):
        raise ValueError("Missing physical mapping reference")
    approval_path = _locator(reference.get("approval"), _MAPPING_APPROVAL_SHA256)
    approval, approval_id = read_artifact(approval_path, expected_sha256=_MAPPING_APPROVAL_SHA256)
    context = {
        "rate_sha256": rate_sha256,
        "network_sha256": network_sha256,
        "conditions_sha256": sha256_json(conditions),
        "source_basis_sha256": sha256_json(basis),
        "target_basis_sha256": sha256_json(target),
    }
    if (approval.get("format") != "kinetic-conversion-approval/1"
            or approval.get("decision") != "approved" or approval.get("context") != context):
        raise ValueError("Conversion approval does not cover this rate, network, state and basis")
    # The approved mapping bytes include the factor, unit, both physical identities,
    # and the source's exact path and SHA. Resolve a relative source beside the mapping.
    expected = approval["mapping_sha256"]
    path = _locator(reference, expected)
    mapping, _ = read_artifact(path, expected_sha256=expected)
    validate_conversion_bases(basis, target, mapping)
    source = mapping["source"]
    if sha256_file(path.parent / source["path"]) != source["sha256"]:
        raise ValueError("Physical conversion factor source SHA-256 mismatch")
    return mapping, approval_id
