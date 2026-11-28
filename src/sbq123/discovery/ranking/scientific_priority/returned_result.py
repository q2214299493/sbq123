"""Ingest an owner-validated, independently reviewed network revision for an issued proposal."""
from pathlib import Path

from sbq123.common.evidence import trust
from scripts.artifact_io import require_sha256, sha256_json
from scripts.multiphase_contracts import read_artifact
from scripts.reaction_network.catalog import check_network_version
from scripts.reaction_network.__main__ import publish as publish_network
from .proposals import verify


def ingest(directory, review_path, review_sha256, network_directory):
    """The owner supplies a validated successor; persist it locally after the independent review."""
    if review_sha256 not in trust.DISCOVERY_RETURN_APPROVALS:
        raise ValueError("Missing independent scientific return approval")
    path = Path(review_path)
    review, _ = read_artifact(path, expected_sha256=review_sha256)
    if (review["format"] != "scientific-return-review/1" or review["decision"] != "accept_revision"
            or not isinstance(review["reviewer"], str) or not review["reviewer"].strip()):
        raise ValueError("Invalid scientific return decision")

    def artifact(key):
        ref = review.get(key)
        if not isinstance(ref, dict) or not isinstance(ref.get("path"), str) or not ref["path"]:
            raise ValueError(f"Missing reviewed {key} artifact")
        digest = require_sha256(ref.get("sha256"), label=key)
        return read_artifact(path.parent / ref["path"], expected_sha256=digest)[0]

    proposal, decision = artifact("proposal"), artifact("planning_decision")
    verify(proposal, directory=Path(directory), expected_report_sha256=review["ranking_sha256"])
    key = proposal["proposal_id"]
    if (decision["proposal_id"] != key or decision["decision"] != "approve" or
            decision["handoff"]["proposal_sha256"] != key or decision["execution_authorized"] is not False):
        raise ValueError("Missing bound human planning approval")
    decisions = Path(directory) / "decisions"
    resolved = decisions / (key + "-after-defer.json")
    retained = resolved if resolved.is_file() else decisions / (key + ".json")
    read_artifact(retained, expected_sha256=review["planning_decision"]["sha256"])
    if review["scope"] != proposal["scope_label"]:
        raise ValueError("Returned evidence scope differs from proposal")
    owner = artifact("owner_validation")
    binding = dict(proposal_id=key, calculation=proposal["calculation"], targets=proposal["targets"],
                   protocol=proposal["protocol"], scope=review["scope"], result_sha256=review["result"]["sha256"])
    if owner.get("status") != "validated_within_scope" or any(owner.get(k) != v for k, v in binding.items()):
        raise ValueError("Owner validation differs from the approved calculation or targets")
    origin = review["origin"]
    if origin == "completed_calculation":
        authorization = artifact("execution_authorization")
        if (authorization.get("execution_authorized") is not True
                or any(authorization.get(k) != binding[k] for k in ("proposal_id", "calculation", "targets", "protocol", "scope"))
                or owner.get("execution_authorization_sha256") != review["execution_authorization"]["sha256"]):
            raise ValueError("Owner execution authorization differs from the returned calculation")
    elif origin != "archived_result":
        raise ValueError("Unknown returned result origin")
    # Read the actual result, even if the retained digest also appears in the validated network.
    artifact("result")
    parent, child = artifact("parent_network"), artifact("successor_network")
    before, after = check_network_version(parent), check_network_version(child)
    if (before != proposal["objective"]["scope"]["network_version"] or before == after
            or parent["project_id"] != child["project_id"] or owner.get("parent_network_version") != before
            or owner.get("successor_network_version") != after):
        raise ValueError("Returned network lineage differs from owner validation")
    if not any(r.get("sha256") == binding["result_sha256"] for r in child["source_artifacts"]):
        raise ValueError("Successor lacks returned calculation as source evidence")
    targets = set(proposal["reaction_ids"])
    def reactions(net):
        return {r["definition"]["reaction_id"]: r for r in net["reactions"]}
    old, new = reactions(parent), reactions(child)
    if not targets <= new.keys() or any(old.get(k) != new.get(k) for k in (new.keys() | old.keys()) - targets):
        raise ValueError("Network revision changed an unrelated reaction")
    out = publish_network(child, Path(network_directory))
    return dict(parent_network_version=before, network_version=after, path=str(out), scope=review["scope"],
                owner_validation_sha256=review["owner_validation"]["sha256"], result_sha256=binding["result_sha256"],
                review_sha256=review_sha256, proposal_id=key, validation=child["validation_report"],
                content_sha256=sha256_json(child), execution_authorized=False)
