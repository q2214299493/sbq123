"""Write-once recommendations and researcher decisions. All handoffs are planning only."""

from copy import deepcopy

from scripts.artifact_io import load_json_object as read, sha256_json, write_json_exclusive
from scripts.multiphase_contracts import read_artifact, read_unique_json
from scripts.scientific_interpretation import interpret_observation
from .observation_binding import replay_observation, validate_candidate, validate_objective
from .engine import rank
from .evidence import digest


def publish(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if sha256_json(read(path)) != sha256_json(value):
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


def _check_report(report, *, historical=False):
    version = report.get("format")
    if version not in ("scientific-priority/1", "scientific-priority/2"):
        raise ValueError("Unsupported ranking report schema")
    attribution = report.get("observation_evidence")
    if "interpretation" in report and attribution is None:
        raise ValueError("Observation-linked ranking requires independently replayable evidence")
    if attribution is not None:
        observation = attribution["observation"]
        description = interpret_observation(observation, expected_sha256=observation["observation_sha256"])
        if description != report["interpretation"]:
            raise ValueError("Planning report interpretation differs from bound observation")
        validate_objective(observation, report["objective"])
        replay = replay_observation(observation, attribution.get("mapping"))
        for row in report["ranked"]:
            reason = validate_candidate(row["candidate"], report["objective"], observation, replay)
            if reason:
                raise ValueError(reason)
    if "ranking_inputs" not in report:
        if historical and version == "scientific-priority/1":
            return
        raise ValueError("Missing ranking inputs")
    rebuilt = rank(report["ranking_inputs"], report["objective"], observation_network=replay[0] if attribution is not None else None)
    # Reports already issued under /1 with retained inputs use the same ranking algorithm.
    rebuilt["format"] = version
    actual = {k: v for k, v in report.items() if k not in ("interpretation", "observation_evidence")}
    if sha256_json(rebuilt) != sha256_json(actual):
        raise ValueError("Ranking report differs from independently replayed ranking inputs")


def _proposal(report, row, position, report_digest):
    attribution = report.get("observation_evidence")
    c = row["candidate"]
    item = dict(
        format="scientific-calculation-proposal/1",
        objective=report["objective"],
        parent_run_id=c["parent_run_id"],
        report_sha256=report_digest,
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
    if attribution is not None:
        item.update(format="scientific-observation-proposal/1", observation_evidence=attribution,
                    species_ids=c["species_ids"], scope=c["scope"])
        for field in ("phase_ids", "surface_ids", "site_context", "interface_id", "reaction_family", "direction", "reaction_direction", "event_geometry", "site_geometry", "structure_status"):
            if field in c:
                item[field] = c[field]
    if "ranking_inputs" in report:
        item.update(rank=position, reasons=row["reasons"], ranking_row_sha256=sha256_json(row))
    item["proposal_id"] = sha256_json(item)
    return item


def proposals(report, directory):
    report = deepcopy(report)
    _check_report(report)
    report_digest = sha256_json(report)
    report_path = directory / "reports" / (report_digest + ".json")
    publish(report_path, report)
    retained, file_digest = read_artifact(report_path)
    if sha256_json(retained) != report_digest:
        raise ValueError("Retained ranking report differs from published content")
    records = []
    for position, row in enumerate(report["ranked"], 1):
        item = _proposal(report, row, position, report_digest)
        key = item["proposal_id"]
        # Owned by the ranking producer. Reviewers choose this directory out of band.
        publish(directory / "issued" / (key + ".json"),
                dict(proposal_id=key, report_sha256=report_digest, report_file_sha256=file_digest,
                     candidate_id=item["candidate_id"], rank=position))
        publish(directory / (key + ".json"), item)
        records.append(deepcopy(item))
    return records


def verify(item, *, directory=None, expected_report_sha256=None, expected_observation_sha256=None):
    """Verify against the publisher-controlled directory, or an independently pinned historical report."""
    item = deepcopy(item)
    key = item["proposal_id"]
    if not digest(key) or sha256_json({k: v for k, v in item.items() if k != "proposal_id"}) != key:
        raise ValueError("Invalid proposal content binding")
    if item.get("format") == "scientific-observation-proposal/1":
        binding = item["observation_evidence"]
        observation = binding["observation"]
        if expected_observation_sha256 is not None and observation["observation_sha256"] != expected_observation_sha256:
            raise ValueError("Different expected observation")
        validate_objective(observation, item["objective"])
        reason = validate_candidate(item, item["objective"], observation, replay_observation(observation, binding.get("mapping")))
        if reason:
            raise ValueError(reason)
    elif (item.get("format") != "scientific-calculation-proposal/1" or expected_observation_sha256 is not None
          or "observation_evidence" in item):
        raise ValueError("Expected an observation-bound proposal")
    if item["review_required"] is not True or item["runnable"] is not False or item["execution_authorized"] is not False:
        raise ValueError("Priority proposals cannot grant execution")

    _verify_ranking_origin(item, key, directory, expected_report_sha256)


def _load_ranking_origin(item, key, directory, expected_report_sha256):
    if directory is None:
        raise ValueError("Trusted ranking report directory required")
    historical = False
    try:
        origin = directory / "issued" / (key + ".json")
        if origin.is_file():
            receipt = read_unique_json(origin)
            issued_rank = receipt["rank"]
            if type(issued_rank) is not int or issued_rank < 1:
                raise ValueError("Invalid rank in current proposal issuance")
            report_digest = receipt["report_sha256"]
            if receipt["proposal_id"] != key or receipt["candidate_id"] != item["candidate_id"]:
                raise ValueError("Proposal differs from retained issuance")
        elif expected_report_sha256 is not None:
            historical = True
            issued_rank = None
            report_digest = expected_report_sha256
        else:
            raise ValueError("Missing independently retained proposal issuance")
        if (not digest(report_digest) or report_digest != item.get("report_sha256")
                or expected_report_sha256 not in (None, report_digest)):
            raise ValueError("Different originating ranking report")
        file_digest = None if historical else receipt["report_file_sha256"]
        if not historical and not digest(file_digest):
            raise ValueError("Invalid retained report byte identity")
        report, _ = read_artifact(directory / "reports" / (report_digest + ".json"), expected_sha256=file_digest)
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError("Missing or invalid retained ranking evidence") from exc
    if sha256_json(report) != report_digest:
        raise ValueError("Retained ranking report digest mismatch")
    if historical and (report.get("format") != "scientific-priority/1" or "ranking_inputs" in report):
        raise ValueError("Missing independently retained proposal issuance")
    return report_digest, report, historical, issued_rank


def _verify_ranking_origin(item, key, directory, expected_report_sha256):
    report_digest, report, historical, issued_rank = _load_ranking_origin(item, key, directory, expected_report_sha256)
    _check_report(report, historical=historical)
    matches = [(pos, row) for pos, row in enumerate(report["ranked"], 1)
               if row["candidate"]["id"] == item["candidate_id"]]
    if len(matches) != 1:
        raise ValueError("Expected one originating ranking row")
    position, row = matches[0]
    if not historical and issued_rank != position:
        raise ValueError("Different rank in retained issuance")
    if sha256_json(_proposal(report, row, position, report_digest)) != sha256_json(item):
        raise ValueError("Proposal differs from originating ranking row")


def review(directory, decision):
    key = decision["proposal_id"]
    if not digest(key):
        raise ValueError("Invalid reviewed proposal")
    item = read(directory / (key + ".json"))
    verify(item, directory=directory, expected_report_sha256=decision.get("expected_report_sha256"))
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
        verify(replacement, directory=directory, expected_report_sha256=decision.get("replacement_report_sha256"))
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


def proposals_for_observation(observation, *, expected_sha256, data, objective, directory, mapping_evidence=None):
    """Validate all candidate attributions before scoring or creating any report."""
    observation, data, objective, mapping = deepcopy((observation, data, objective, mapping_evidence))
    interpretation = interpret_observation(observation, expected_sha256=expected_sha256)
    validate_objective(observation, objective)
    replay = replay_observation(observation, mapping)
    for candidate in data["candidates"]:
        reason = validate_candidate(candidate, objective, observation, replay)
        if reason:
            candidate.setdefault("blockers", []).append(reason)
    report = rank(data, objective, observation_network=replay[0])
    report["interpretation"] = interpretation
    report["observation_evidence"] = {"observation": observation, "mapping": mapping}
    return proposals(report, directory)
