"""Generate testable alternatives from independently replayed directional flux."""
from sbq123.analysis.observations.rates import analyze_rates


def investigate(role, path, *, expected_sha256):
    analysis = analyze_rates(role, path, expected_sha256=expected_sha256)
    if "observation" not in analysis:
        return analysis
    obs = analysis["observation"]
    flags, hypotheses = [], []
    for row in analysis["elementary_rates"]:
        forward, reverse = row["forward"], row["reverse"]
        if any(type(v) not in (int, float) for v in (forward, reverse)) or min(forward, reverse) <= 0:
            continue
        fraction = min(forward, reverse) / max(forward, reverse)
        if fraction < 0.5:
            continue
        reaction = row["reaction_id"]
        flags.append(dict(reaction_id=reaction, reverse_exchange_fraction=fraction,
                          forward=forward, reverse=reverse, net=row["net"], basis=obs["basis"]))
        hypotheses.append(dict(reaction_id=reaction, evidence_sha256=obs["observation_sha256"],
            hypothesis="Bidirectional exchange can mask turnover through this elementary channel.",
            alternative="Opposing directional events can coexist with substantial local kinetic control.",
            prediction="If the step is near partial equilibrium, a common scaling of both directions "
                       "will change net cycle TOF weakly on the same steady branch.",
            validation="Compare step-size-stable TS perturbations at fixed equilibrium constant and "
                       "operating point; for KMC use independent seed ensembles and uncertainty.",
            limitation="The exchange fraction is descriptive. A flux ratio does not establish rate control.",
            status="hypothesis", execution_authorized=False))
    alternatives = []
    for sid, source in analysis["species_sources"].items():
        gross = source["gross_production"]
        if gross is None or gross <= 0:
            continue
        routes = []
        for row in analysis["elementary_rates"]:
            for direction, side in (("forward", "products"), ("reverse", "reactants")):
                count = row[side].get(sid, 0)
                if count and type(row[direction]) in (int, float) and row[direction] > 0:
                    routes.append(dict(reaction_id=row["reaction_id"], direction=direction,
                                       gross_fraction=count * row[direction] / gross))
        if len({r["reaction_id"] for r in routes}) > 1:
            alternatives.append(dict(species_id=sid, evidence_sha256=obs["observation_sha256"],
                routes=sorted(routes, key=lambda r: -r["gross_fraction"]),
                hypothesis="The named elementary channels offer alternative routes for forming this species.",
                limitation="Gross formation includes recycled molecules; fractions are not net pathway yields.",
                validation="Resolve direction and isotope origin of the product, or compare channel-specific "
                           "perturbations on the same branch with competing-channel responses.",
                status="hypothesis", execution_authorized=False))
    return dict(analysis=analysis, diagnostic=dict(
                criterion="min(forward,reverse)/max(forward,reverse) >= 0.5 for positive directional rates",
                flags=flags), alternative_routes=alternatives, hypotheses=hypotheses, source_sha256=obs["observation_sha256"],
                scope=obs["evidence_scope"], scientific_promotion=False)


def follow_up_study(root, rate_path, rate_sha256, directory, objective_id="activity"):
    """Join the published perturbation study to its original point and retain the owner's ranked decisions."""
    from pathlib import Path
    from sbq123.analysis.interpretation.kinetics import archived_study

    evidence = investigate("mkm", rate_path, expected_sha256=rate_sha256)
    if "analysis" not in evidence:
        return evidence
    from scripts.multiphase_contracts import read_artifact
    from scripts.scientific_priority.engine import rank
    from scripts.scientific_priority.proposals import proposals

    obs = evidence["analysis"]["observation"]
    packet, objective, _ = archived_study(root, objective_id)
    # Proposal verification can run later in a process with a different active role-data root.
    # Persist locators for the actual study just authenticated; the reviewed source digests stay fixed.
    for source in packet["sources"].values():
        source["path"] = str((Path(root) / source["path"]).resolve())
    ref = packet["sources"]["baseline"]
    receipt, _ = read_artifact(Path(root) / ref["path"], expected_sha256=ref["sha256"])
    if (obs["run_id"] != receipt["run_id"] or obs["network_version"] != receipt["network_version_id"]
            or obs["dataset_version"] != receipt["kinetic_dataset_version"]
            or obs["native_output"]["sha256"] not in receipt["output_hashes"].values()):
        return dict(status="insufficient_evidence", reason="Perturbation study belongs to another calculation",
                    source_sha256=obs["observation_sha256"], hypotheses=evidence["hypotheses"])
    # Only propose structural follow-up for a channel actually flagged at this point.
    flagged = {h["reaction_id"] for h in evidence["hypotheses"]}
    for c in list(packet["candidates"]):
        if c["id"] != c["parameter"] or c["parameter"] not in flagged or c["parameter_type"] != "transition_state":
            continue
        for need, roles in (("reaction_path", ("IS", "FS")), ("candidate_geometry", ("TS",))):
            targets = {k: c["structures"][k]["mock_structure_sha256"] for k in roles}
            # The archived single-point cost and error model do not price or validate these operations.
            variant = dict(c, id=c["id"] + "-" + need, need=need, targets=targets, cost=None,
                           blockers=["Method-specific cost and local geometry validation remain to be reviewed"])
            variant.pop("information_model", None)
            packet["candidates"].append(variant)
    report = rank(packet, objective)
    items = proposals(report, Path(directory))
    for hypothesis in evidence["hypotheses"]:
        rid = hypothesis["reaction_id"]
        hypothesis["proposals"] = [item["proposal_id"] for item in items if rid in item["reaction_ids"]]
        hypothesis["local_responses"] = [dict(value=m["value"], parameter=m["parameter"],
                                             source_sha256=packet["sources"][m["source"]]["sha256"])
                                         for m in packet["metrics"] if m["kind"] == "ts_drc" and m["parameter"] == rid]
    return dict(status="planning_only", hypotheses=evidence["hypotheses"], alternative_routes=evidence["alternative_routes"], proposals=items,
                deferred=[dict(id=r["candidate"]["id"], calculation=r["recommendation"], reaction_ids=r["candidate"]["reaction_ids"],
                               status=r["status"], reasons=r["reasons"], evidence_sha256=obs["observation_sha256"])
                          for r in report["deferred"]], baseline_sha256=ref["sha256"],
                objective=objective, scope=obs["evidence_scope"], execution_authorized=False)
