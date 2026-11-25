"""Write-once recommendations and researcher decisions. All handoffs are planning only."""

from scripts.artifact_io import load_json_object as read, sha256_json, write_json_exclusive
from .evidence import digest


def publish(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Immutable evidence conflict: {path.name}")
    else:
        write_json_exclusive(path, value)


def spc_reference(export):
    """Validate an already imported SPC Phase 3A proposal with its owning optional package."""
    from spc.models import ExecutionProposal

    p = ExecutionProposal.model_validate(export)
    return dict(
        proposal_id=p.proposal_id,
        source_plan_hash=p.source_plan_hash,
        approval_receipt_hash=p.approval_receipt_hash,
        execution_context_hash=p.execution_context_hash,
        capability=p.executable_capability_id,
        export_manifest_hash=p.export_manifest_hash,
    )


def proposals(report, directory):
    records = []
    for row in report["ranked"]:
        c = row["candidate"]
        item = dict(
            format="scientific-calculation-proposal/1",
            objective=report["objective"],
            parent_run_id=c["parent_run_id"],
            report_sha256=sha256_json(report),
            candidate_id=c["id"],
            reaction_ids=c["reaction_ids"],
            scope_label=c["scope_label"],
            model_version=c.get("model_version"),
            structures=c["structures"],
            targets=c["targets"],
            reaction_structures=c.get("reaction_structures"),
            protocol=c["protocol"],
            calculation=row["recommendation"],
            cost=row["cost"],
            score=row["score"],
            evidence_requirements=[c["need"], "Confirm target geometry, compatibility and operation-specific validation with owner"],
            rationale=row["rationale"],
            contributions=row["weighted_contributions"],
            ticket=c.get("ticket"),
            spc_reference=spc_reference(c["spc_execution_proposal"]) if c.get("spc_execution_proposal") else None,
            review_required=True,
            runnable=False,
            execution_authorized=False,
        )
        item["proposal_id"] = sha256_json(item)
        publish(directory / (item["proposal_id"] + ".json"), item)
        records.append(item)
    return records


def verify(item):
    key = item["proposal_id"]
    if not digest(key) or sha256_json({k: v for k, v in item.items() if k != "proposal_id"}) != key:
        raise ValueError("Invalid proposal content binding")
    if item["runnable"] is not False or item["execution_authorized"] is not False:
        raise ValueError("Priority proposals cannot grant execution")


def review(directory, decision):
    key = decision["proposal_id"]
    if not digest(key):
        raise ValueError("Invalid reviewed proposal")
    item = read(directory / (key + ".json"))
    verify(item)
    action = decision["decision"]
    if (
        item["proposal_id"] != key
        or action not in ("approve", "reject", "modify", "defer")
        or not all(isinstance(decision.get(k), str) and decision[k].strip() for k in ("reviewer", "reason"))
    ):
        raise ValueError("Explicit reviewer, explanation and bound decision required")
    successor = decision.get("replacement_proposal_id")
    if action == "modify":
        if not digest(successor) or successor == key:
            raise ValueError("Modification requires a separately ranked replacement proposal")
        replacement = read(directory / (successor + ".json"))
        verify(replacement)
        if replacement["proposal_id"] != successor or replacement["candidate_id"] != item["candidate_id"]:
            raise ValueError("Replacement targets another candidate")
    elif successor is not None:
        raise ValueError("Unexpected proposal replacement")
    handoff = None
    if action == "approve":
        if item["scope_label"] == "synthetic_benchmark":
            owner = "Synthetic fixture review only"
        elif item["calculation"] in ("NEB", "DIMER"):
            owner = "scripts.ts_strategy_engine.execution_gate"
        elif item["calculation"].startswith("DFT"):
            owner = "VASP input review and existing submission preflight"
        else:
            owner = "Model-specific preparation and execution preflight"
        handoff = dict(
            destination=owner,
            ticket=item["ticket"],
            proposal_sha256=key,
            targets=item["targets"],
            required="Fresh owner preflight and separate execution authorization",
            runnable=False,
        )
    receipt = dict(
        format="scientific-priority-review/1",
        proposal_id=key,
        decision=action,
        reviewer=decision["reviewer"],
        reason=decision["reason"],
        replacement_proposal_id=successor,
        handoff=handoff,
        execution_authorized=False,
    )
    decisions = directory / "decisions"
    dest = decisions / (key + ".json")
    prior = decision.get("after_defer")
    if prior is not None:
        if not digest(prior) or not dest.is_file():
            raise ValueError("Missing prior deferral")
        first = read(dest)
        if sha256_json(first) != prior or first["decision"] != "defer" or action == "defer":
            raise ValueError("Only a matching prior deferral can be resolved")
        receipt["after_defer"] = prior
        dest = decisions / (key + "-after-defer.json")
    publish(dest, receipt)
    return receipt
