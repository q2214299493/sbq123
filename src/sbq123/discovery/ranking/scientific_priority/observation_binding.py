"""Check a planning attribution against the independently reviewed rate and its network."""
from sbq123.common.artifacts.artifact_io import sha256_json
from .structure_binding import validate_structures
from sbq123.common.evidence.kinetic_data.analysis_evidence import approved_replay_row, review_path
from sbq123.common.evidence.kinetic_data.observations import rate_observation
from sbq123.common.workflow.multiphase_contracts import read_artifact
from sbq123.common.workflow.runtime_resources import resource_path


def replay_observation(observation, mapping=None):
    family, row = approved_replay_row(observation.get("rate_sha256"))
    path = review_path(row, row["output"]) if "project_review_sha256" in row else resource_path(f"reports/multiphase/stage_b1_4/replay/{family}-{row['case']}.json")
    rates, digest = read_artifact(path, expected_sha256=row["output_sha256"])
    ref = row["provenance"]["network"]
    network_path = review_path(row, ref)
    network, _ = read_artifact(network_path, expected_sha256=ref["sha256"])
    if rates["output_binding"]["run_id"] != row["run_id"] or network["network_version"] != row["network_version"]:
        raise ValueError("Different reviewed run or reaction network")
    receipt = row["parent_receipt"]
    read_artifact(review_path(row, receipt), expected_sha256=receipt["sha256"])
    request = dict(conditions=rates["conditions"], target=observation["basis"], evidence=mapping,
                   rate_evidence={"path": path, "sha256": digest})
    if observation.get("kind") == "instantaneous_gas_balance":
        from sbq123.analysis.observations.reactor_balance import balance_observation

        values = observation["values"]
        rebuilt = balance_observation(rates, network_path, **request, volume_m3=values["reactor_volume_m3"],
                                      inlet_mol_s=values["inlet_mol_s"], outlet_mol_s=values["outlet_mol_s"])
        observed = values["accumulation_mol_s"]
    else:
        rebuilt = rate_observation(rates, network_path, **request)
        observed = observation["values"]
    if sha256_json(rebuilt) != sha256_json(observation):
        raise ValueError("Observation differs from independently replayed evidence")
    return network, {r["reaction_id"]: r for r in rates["reaction_rates"]}, observed


def validate_objective(observation, objective):
    conditions = observation["conditions"]
    pressures = conditions["partial_pressures"]
    if pressures is None:
        raise ValueError("Planning requires a measured composition")
    scope = dict(network_version=observation["network_version"], dataset_version=observation["dataset_version"],
                 baseline_result_sha256=observation["result_sha256"], normalization=observation["basis"],
                 temperature_K=conditions["temperature_K"],
                 feed_bar={p["species_id"]: p["pressure_Pa"] / 100000 for p in pressures})
    if objective["scope"] != scope:
        raise ValueError("Proposal objective differs from observed model, conditions or basis")


def _identifiers(values, label):
    if not isinstance(values, list) or not values or not all(isinstance(v, str) and v for v in values):
        raise ValueError(f"Expected nonempty {label} identifiers")
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate {label} identifier")
    return set(values)


def validate_candidate(candidate, objective, observation, replay):
    network, rates, observed = replay
    if candidate["parent_run_id"] != observation["run_id"]:
        raise ValueError("Candidate parent run differs from approved observation lineage")
    if candidate["scope"] != objective["scope"] or candidate["scope_label"] != {"archived_software_benchmark": "synthetic_benchmark", "reviewed_project": "reviewed_project"}.get(observation["evidence_scope"], ""):
        raise ValueError("Candidate scope differs from the approved benchmark")
    species = _identifiers(candidate.get("species_ids"), "observed species")
    target = objective.get("target")
    if not species <= observed.keys() or (target is not None and (not isinstance(target, str) or target not in species)):
        raise ValueError("Candidate species differ from the observed quantity or objective target")
    definitions = {r["definition"]["reaction_id"]: r["definition"] for r in network["reactions"]}
    for rid in _identifiers(candidate.get("reaction_ids"), "reaction"):
        if rid not in definitions or rid not in rates:
            raise ValueError("Candidate reaction absent from approved network or measured rates")
        reaction = definitions[rid]
        if rates[rid]["net"] == 0 or any(reaction["products"].get(s, 0) == reaction["reactants"].get(s, 0)
                                         for s in species):
            raise ValueError("Reaction has no measured net contribution to the claimed species source")
        if candidate.get("reaction_family") and candidate["reaction_family"] != reaction["reaction_type"]:
            raise ValueError("Candidate reaction family differs from the bound reaction")
        sites = candidate.get("site_context")
        if isinstance(sites, dict):
            if any(type(n) is not int or n < 1 or n > reaction["required_sites"].get(site, 0)
                   for site, n in sites.items()):
                raise ValueError("Candidate site inventory conflicts with the bound reaction")
        elif sites and not _identifiers(sites, "site") <= reaction["required_sites"].keys():
            raise ValueError("Candidate site inventory conflicts with the bound reaction")
        for key, allowed in (("phase_ids", reaction["phase_ids"]), ("surface_ids", reaction["surface_ids"])):
            if candidate.get(key) and not _identifiers(candidate[key], key) <= set(allowed):
                raise ValueError(f"Candidate {key} conflicts with the bound reaction")
        if candidate.get("interface_id") and candidate["interface_id"] != reaction.get("interface_id"):
            raise ValueError("Candidate interface conflicts with the bound reaction")
    return validate_structures(candidate, network)
