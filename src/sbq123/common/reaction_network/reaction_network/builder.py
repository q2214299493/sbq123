"""Assemble one immutable, evidence-bound network from exchange records."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime

from sbq123.common.artifacts.artifact_io import sha256_json
from sbq123.common.evidence.kinetic_data.interphase_transfer import assess_transfer
from sbq123.common.evidence.kinetic_data.stoichiometric_sources import stoichiometric_totals
from sbq123.common.workflow.multiphase_contracts import COLLECTIONS, ENERGY_ATOL_EV, _check_species_context, check_cross_phase_scope, validate_bundle
from sbq123.common.evidence.kinetic_data.reaction_intake import report as intake_report
from sbq123.common.validation.scientific_validation import finite_number, validate_finite_tree
from sbq123.common.thermochemistry.thermochemistry.engine import ts_binding
from sbq123.common.reaction_network.reaction_network.catalog import catalog, check_context, check_record_field, register_species, site_counts, site_mapping
from sbq123.common.reaction_network.reaction_network.cross_phase import qualification, record_review_status, validate_scope_fields
from sbq123.common.reaction_network.reaction_network.thermodynamics import check_cycles, thermal_evidence
from sbq123.common.reaction_network.reaction_network.site_review import apply_review, domain_balance

LEVELS = ("DRAFT", "STRUCTURALLY_VALID", "THERMODYNAMICALLY_VALID", "SCIENTIFICALLY_ACCEPTED", "KINETICALLY_ELIGIBLE")
TYPES = {"adsorption", "desorption", "dissociation", "hydrogenation", "dehydrogenation", "c_c_coupling",
         "c_o_cleavage", "diffusion", "association", "interfacial", "interphase_transfer", "cross_phase_elementary", "surface_reaction", "multi_site", "other"}


def from_registry_mapping(mapping, project_id):
    """Read the archived Phase 1 partial mapping without inventing missing catalog records."""
    surface = mapping["surface_context"]
    rid = mapping["reaction_mapping"]
    states = mapping["source_states"]
    if (rid["initial_structure_id"], rid["final_structure_id"], rid["ts_id"]) != (
            states["IS"]["structure_id"], states["FS"]["structure_id"], states["TS"]["calculation_id"]):
        raise ValueError("Mapped reaction does not match its registry states")
    for state in states.values():
        if state["reference_convention"] != mapping["energy_convention"] or state["unit"] != "eV":
            raise ValueError("Incompatible registry state energy")
    reaction = dict(rid, origin="registry_endpoint_mapping", state_identities={key: v["structure"]["sha256"] for key, v in states.items()},
                    electronic_reference_convention=mapping["energy_convention"], source_states=states)
    return {"format": "network-definition/1", "projects": [{"project_id": project_id}],
            "materials": [{"project_id": project_id, "material_id": surface["material"]}],
            "surfaces": [{"surface_id": surface["surface"], "phase_id": None, "source_context": surface}],
            "species": mapping["species_mapping"], "reactions": [reaction]}


def endpoint_candidate(pair):
    """Use assigned species at each endpoint, without inferring a site count or a reverse rate."""
    reaction = {k: v for k, v in pair.items() if k not in ("initial", "final")}
    for key, role, side_key in (("initial", "initial_structure_id", "reactants"), ("final", "final_structure_id", "products")):
        endpoint = pair[key]
        if not isinstance(endpoint["species_ids"], list) or not endpoint["species_ids"] or not endpoint.get("structure_id"):
            raise ValueError("An endpoint candidate needs a structure and assigned species IDs")
        reaction[role] = endpoint["structure_id"]
        reaction[side_key] = dict(Counter(endpoint["species_ids"]))
    reaction.setdefault("reaction_type", "other")
    reaction.setdefault("reversible", None)
    reaction.update(origin="geometric_inference", eligibility="draft", validation={"status": "unreviewed", "review": None})
    return reaction


def side(stoich, vacant, reaction, index):
    if not isinstance(stoich, dict) or not stoich:
        raise ValueError("Empty reaction side")
    terms = []
    for key, number in stoich.items():
        if type(number) is not int or number <= 0 or key not in index["species"]:
            raise ValueError(f"Invalid stoichiometry or unknown species {key}")
        species = index["species"][key]
        _check_species_context(species, reaction)
        composition = species.get("composition")
        if composition is None and reaction["reaction_type"] != "cross_phase_elementary":
            raise ValueError(f"Missing species composition for {key}")
        terms.append((number, composition, species.get("charge"), species.get("site_occupancy")))
    return stoichiometric_totals(terms, vacant)


def balance(reaction, index, gaps):
    for key in ("sites_consumed", "sites_released", "required_sites"):
        site_counts(reaction.get(key), index, reaction["surface_ids"], reaction.get("interface_id"))
    left = side(reaction["reactants"], reaction.get("sites_consumed"), reaction, index)
    right = side(reaction["products"], reaction.get("sites_released"), reaction, index)
    for label, a, b in zip(("element", "charge", "site"), left, right, strict=True):
        if a is None or b is None:
            gaps.append(f"Unknown {label} balance")
        elif a != b:
            raise ValueError(f"{label} conservation failed for {reaction['reaction_id']}: {a} != {b}")
    if reaction["reaction_type"] == "cross_phase_elementary":
        gaps.extend(check_cross_phase_scope(reaction, index, left, right))
    footprint = reaction.get("required_sites")
    if footprint is not None and left[2] is not None and not left[2] <= Counter(footprint):
        raise ValueError("Insufficient required site footprint")
    return dict(left[2]) if left[2] is not None and right[2] is not None else None


def directions(reaction):
    reversible = reaction.get("reversible")
    if reversible is not None and type(reversible) is not bool:
        raise ValueError("reversible must be true, false or null")
    forward = {key: reaction.get(key) for key in ("reactants", "products", "sites_consumed", "sites_released")}
    reverse = None
    if reversible:
        reverse = dict(reactants=forward["products"], products=forward["reactants"],
                       sites_consumed=forward["sites_released"], sites_released=forward["sites_consumed"])
    return {"status": "unknown" if reversible is None else "reversible" if reversible else "irreversible",
            "forward": forward, "reverse": reverse}


def validate_confirmation(reaction):
    decision = reaction.get("user_confirmation")
    if decision is None:
        return
    subject = {k: v for k, v in reaction.items() if k != "user_confirmation"}
    if decision.get("definition_sha256") != sha256_json(subject):
        raise ValueError("User confirmation refers to a different reaction definition")
    if (decision.get("acceptance_status") not in ("accepted", "rejected")
            or "reaction_definition" not in decision.get("acceptance_scope", [])
            or not decision.get("accepted_by") or not decision.get("acceptance_reason")):
        raise ValueError("Incomplete user reaction decision")
    if datetime.fromisoformat(decision.get("acceptance_timestamp", "")).tzinfo is None:
        raise ValueError("User decision requires a timestamp with time zone")


def artifact_hashes(value):
    if isinstance(value, list):
        for item in value:
            yield from artifact_hashes(item)
    elif isinstance(value, dict):
        if "sha256" in value:
            yield value["sha256"]
        for child in value.values():
            yield from artifact_hashes(child)


def reviewed(rows, verified):
    for row in rows:
        decision = row.get("validation") or {}
        receipt = decision.get("review") or {}
        if decision.get("status") != "accepted" or receipt.get("sha256") not in verified:
            return False
        if not set(artifact_hashes(row)) <= verified:
            return False
    return True


def scientific_level(reaction, index, verified, params, strict):
    species = [index["species"][s] for s in reaction["reactants"].keys() | reaction["products"].keys()]
    if reaction.get("ts_species_id") is not None:
        species.append(index["species"][reaction["ts_species_id"]])
    domains = [index["surfaces"][s] for s in reaction["surface_ids"]]
    phases = [index["phases"][s["phase_id"]] for s in domains]
    materials = [index["materials"][p["material_id"]] for p in phases]
    site_ids = set(reaction.get("required_sites") or {}) | set(reaction.get("sites_consumed") or {}) | set(reaction.get("sites_released") or {})
    site_ids.update(s for row in species for s in row.get("site_occupancy") or {})
    sites = [index["sites"][s] for s in site_ids]
    interface = [index["interfaces"][reaction["interface_id"]]] if reaction.get("interface_id") else []
    records = [reaction, *species, *domains, *phases, *materials, *sites, *interface, *index["projects"].values()]
    if not reaction.get("provenance") or not reviewed(records, verified):
        return LEVELS[2]
    if any(s.get("kind", s.get("source_type")) in ("model_prediction", "synthetic", "assumption") for s in reaction["provenance"]):
        return LEVELS[2]
    if not strict:
        return LEVELS[3]
    eligible = [p for p in params if p["eligibility"] == "eligible" and reviewed([p], verified)
                and reviewed([index["species"][c["species_id"]] for c in p["coverage_terms"]], verified)]
    return LEVELS[4] if reaction["eligibility"] == "eligible" and eligible else LEVELS[3]


def structural_gaps(r, index):
    phases = check_context(r, index)
    if r["reaction_type"] not in TYPES or (r["reaction_type"] == "interfacial" and not r.get("interface_id")):
        raise ValueError("Invalid reaction classification/interface")
    interface = index["interfaces"].get(r.get("interface_id"), {})
    participants = set(interface.get("phase_ids") or [])
    declared = r.get("phase_ids")
    if declared is not None and (set(declared) - index["phases"].keys() or not (phases - {None}) <= set(declared)
                                 or (None not in phases and set(declared) - (phases | participants))
                                 or (participants and set(declared) - participants)):
        raise ValueError("Reaction phases differ from surface domains")
    gaps = []
    if "operating_conditions_ref" in r:
        if r["reaction_type"] not in ("interphase_transfer", "cross_phase_elementary"):
            raise ValueError("operating_conditions_ref requires a declared cross-phase event")
        check_record_field("reaction", "operating_conditions_ref", r["operating_conditions_ref"])
    if r["reaction_type"] in ("interphase_transfer", "cross_phase_elementary"):
        if r.get("provenance") not in (None, []):
            check_record_field("reaction", "provenance", r["provenance"])
        if r["reaction_type"] == "cross_phase_elementary" and r.get("required_sites") is None:
            gaps.append("Required site footprint unconfirmed")
        if not r.get("interface_id"):
            gaps.append("Transfer interface unconfirmed" if r["reaction_type"] == "interphase_transfer" else "Reaction interface unconfirmed")
    site_balance = balance(r, index, gaps)
    if None in phases:
        gaps.append("Catalyst phase unconfirmed")
    if participants - phases:
        gaps.append("Interface surface assignment incomplete")
    if not all(r.get(k) for k in ("initial_structure_id", "final_structure_id")):
        gaps.append("Endpoint structure reference missing")
    participants = r["reactants"].keys() | r["products"].keys()
    if any(not index["species"][s].get("structure_id") for s in participants):
        gaps.append("Missing species structure association")
    if r.get("ts_treatment") == "located" and not r.get("ts_id"):
        raise ValueError("Located TS lacks a structure or calculation reference")
    return gaps, site_balance


def check_parameter_basis(p, energies, reference):
    basis = p.get("energy_basis")
    if basis not in ("gibbs", "electronic", None):
        raise ValueError("Unknown rate energy basis")
    if basis == "gibbs" and energies["temperature_k"] is not None:
        for key, expected in (("temperature_K", energies["temperature_k"]), ("standard_state_id", energies["standard_state"])):
            if p.get(key) is not None and p[key] != expected:
                raise ValueError(f"Rate {key} differs from Gibbs convention")
    for direction in ("forward", "reverse"):
        activation = (p.get(direction) or {}).get("activation_energy")
        if not activation or not basis:
            continue
        expected = energies[basis + "_ev"][direction]
        if activation["unit"] != "eV" or activation["reference_id"] != reference:
            raise ValueError("Rate barrier has incompatible units or energy reference")
        if expected is not None and abs(finite_number(activation["value"], "activation energy") - expected) > ENERGY_ATOL_EV:
            raise ValueError("Rate activation energy differs from reaction barrier")


def rate_gaps(reaction, parameters, energies):
    if not parameters or not reaction.get("rate_law_id"):
        return ["Missing kinetic parameters or rate law"]
    result = []
    for p in parameters:
        if p.get("rate_law_id") != reaction["rate_law_id"] or p.get("energy_reference_id") != reaction.get("energy_reference_id"):
            raise ValueError("Parameter and reaction rate law or energy reference differ")
        check_parameter_basis(p, energies, reaction.get("energy_reference_id"))
        needed = ["forward", "temperature_K", "standard_state_id", "energy_basis"]
        if reaction.get("reversible") is True:
            needed.append("reverse")
        missing = [field for field in needed if p.get(field) is None]
        if missing:
            result.append(f"{p['parameter_set_id']} missing " + ", ".join(missing))
    return result


def inspect_reaction(r, index, calc, mapping):
    gaps, site_balance = structural_gaps(r, index)
    level = LEVELS[0] if gaps else LEVELS[1]
    direction = directions(r)
    energies = thermal_evidence(r, calc)
    free = energies["gibbs_ev"]
    needed = ("forward", "reaction") if r.get("reversible") is False else ("forward", "reverse", "reaction")
    missing_ts = r.get("ts_treatment") not in ("located", "barrierless")
    if any(free[k] is None for k in needed):
        gaps.append("Missing compatible free energies")
        if missing_ts and r["reaction_type"] in ("interphase_transfer", "cross_phase_elementary"):
            gaps.append("Unresolved transition-state treatment")
    elif missing_ts:
        gaps.append("Unresolved transition-state treatment")
    elif level == LEVELS[1] and (calc is None or calc["status"] == "complete"):
        level = LEVELS[2]
    params = [p for p in index["parameter_sets"].values() if p["reaction_id"] == r["reaction_id"]]
    parameter_gaps = rate_gaps(r, params, energies)
    gaps.extend(parameter_gaps)
    if r.get("reversible") is None:
        gaps.append("Reversibility unconfirmed")
    net = Counter({"species:" + k: n for k, n in r["products"].items()})
    net.subtract({"species:" + k: n for k, n in r["reactants"].items()})
    net.update({"site:" + k: n for k, n in (r.get("sites_released") or {}).items()})
    net.subtract({"site:" + k: n for k, n in (r.get("sites_consumed") or {}).items()})
    attributes = {}
    if r["reaction_type"] == "interphase_transfer":
        transfer = assess_transfer(r, index)
        attributes["interphase_transfer"] = transfer
        for endpoint in (transfer["source"], transfer["destination"]):
            for site, changes in endpoint["inventories"].items():
                net["site:" + site] = changes["vacancy_change"]
    if r["reaction_type"] == "cross_phase_elementary":
        inventories = domain_balance(r, index, by_inventory=True)
        if r.get("sites_released") is None or r.get("sites_consumed") is None:
            for site in inventories:
                net["site:" + site] = None
        attributes["site_balance_by_inventory"] = inventories
        attributes["cross_phase_qualification"] = qualification(r, index, site_balance, energies, needed, params, parameter_gaps)
    return {**attributes, "definition": r, "direction": direction, "net_stoichiometry": dict(sorted(net.items())),
            "site_balance": site_balance, "energies": energies, "thermochemistry": calc, "level": level,
            "origin": r.get("origin", "supplied_definition"), "site_mapping": mapping,
            "user_confirmation": (mapping or {}).get("user_confirmation", r.get("user_confirmation")),
            "scientific_review": r.get("validation"), "parameter_set_ids": [p["parameter_set_id"] for p in params],
            "gaps": gaps, "mkm_status": "eligible" if level == LEVELS[4] else "blocked"}


def intake_states(docs, reaction, records):
    """Bind accepted intake structures and energies; derive only differences with both operands."""
    fields = intake_report(docs, "electronic")["fields"]
    values, selected, limited = {}, {}, []
    ids = reaction.get("state_identities", {})
    for state, role in (("IS", "initial_structure_id"), ("TS", "ts_id"), ("FS", "final_structure_id")):
        structure = fields[f"{state}.structure"]
        if not structure["usable"]:
            continue
        identity = records[structure["selected"]]["value"]["identity"]
        if ids.get(state, reaction.get(role)) not in (None, identity):
            raise ValueError(f"{state}: intake structure differs from reaction")
        if not reaction.get(role):
            reaction[role] = identity
        entry = fields[f"{state}.electronic_energy"]
        if not entry["usable"]:
            continue
        record = records[entry["selected"]]
        value = record["value"]
        convention = value["energy_reference"]
        if (reaction.get("electronic_reference_convention") or reaction.get("energy_reference_id") or convention) != convention:
            raise ValueError("Intake and reaction energy references differ")
        if not reaction.get("energy_reference_id"):
            reaction["energy_reference_id"] = convention
        values[state] = value["value_ev"]
        selected[state] = record["id"]
        if entry["evidence_status"] != "AVAILABLE" or structure["evidence_status"] != "AVAILABLE":
            limited.append(state)
    terms = reaction.get("electronic_energies") or dict.fromkeys(("reaction", "forward", "reverse"))
    for key, a, b in (("reaction", "FS", "IS"), ("forward", "TS", "IS"), ("reverse", "TS", "FS")):
        if a not in values or b not in values or ("TS" in (a, b) and reaction.get("ts_treatment") != "located"):
            continue
        difference = values[a] - values[b]
        if terms.get(key) is not None:
            if abs(terms[key]["value"] - difference) > ENERGY_ATOL_EV:
                raise ValueError("Intake state energies disagree with supplied difference")
            continue
        source = {"kind": "intake_state_difference", "record_ids": [selected[a], selected[b]],
                  "records_sha256": sha256_json([records[selected[a]], records[selected[b]]])}
        reaction.setdefault("provenance", []).append(source)
        terms[key] = {"value": difference, "unit": "eV", "reference_id": reaction["energy_reference_id"], "source": source}
    reaction["electronic_energies"] = terms
    return {"selected_records": selected, "limited_states": limited}


def apply_intakes(documents, index):
    grouped = defaultdict(list)
    for doc in documents:
        grouped[doc["reaction_id"]].append(doc)
    mappings = {}
    for rid, docs in grouped.items():
        if rid not in index["reactions"]:
            raise ValueError("Unknown intake reaction")
        report = intake_report(docs, "site_mapping")
        records = {r["id"]: r for d in docs for r in d["records"]}
        field = report["fields"]["reaction.site_mapping"]
        original = index["reactions"][rid]
        mapping = {"evidence": list(records.values()), "assessment": field,
                   "electronic_intake": intake_states(docs, original, records)}
        mappings[rid] = mapping
        if field["usable"]:
            selected = records[field["selected"]]
            effective = site_mapping(selected, original, index)
            if (selected["acceptance"]["acceptance_status"] == "accepted"
                    and "site_mapping" in selected["acceptance"]["acceptance_scope"]):
                mapping["user_confirmation"] = {"classification": selected["value"]["reaction_classification"],
                                                "acceptance": selected["acceptance"], "record_id": selected["id"]}
            for sid, counts in effective["occupancies"].items():
                previous = index["species"][sid].get("site_occupancy")
                if previous is not None and previous != counts:
                    raise ValueError("Conflicting occupancy for one physical species")
                index["species"][sid]["site_occupancy"] = counts
            for key in ("sites_consumed", "sites_released"):
                if original.get(key) is not None and original[key] != effective[key]:
                    raise ValueError(f"Conflicting site mapping for {key}")
                original[key] = effective[key]
            mapping["effective"] = effective
    return mappings


def reaction_keys(r):
    sides = [(r["reactants"], r.get("sites_consumed")), (r["products"], r.get("sites_released"))]
    hashed = [sha256_json(side) for side in sides]
    directions = [hashed, hashed[::-1]] if r.get("reversible") else [hashed]
    return {sha256_json([order, sorted(r["surface_ids"]), r.get("interface_id"), r.get("ts_id")]) for order in directions}


def apply_decision(result, decision, index, strict, verified):
    r = result["definition"]
    # Bind the whole catalyst/species catalog, effective mapping, parameter and energy evidence.
    subject = sha256_json([result, {k: index[k] for k, _, _ in COLLECTIONS if k not in ("runs", "reactions")}])
    result["subject_sha256"] = subject
    result["network_review"] = decision
    if decision is None:
        return
    if decision.get("subject_sha256") != subject:
        raise ValueError("Stale network review: reaction subject changed")
    if (decision.get("decision") not in ("accepted", "rejected") or not decision.get("reviewer")
            or not decision.get("reason") or datetime.fromisoformat(decision.get("reviewed_at", "")).tzinfo is None):
        raise ValueError("Incomplete network review")
    if decision["decision"] == "accepted" and result["level"] == LEVELS[2]:
        if r.get("ts_treatment") == "located" and not result.get("ts_review"):
            return
        if (result.get("user_confirmation") or {}).get("acceptance_status") == "rejected":
            return
        mapping = result["site_mapping"] or {}
        if mapping.get("electronic_intake", {}).get("limited_states"):
            return
        if mapping.get("effective") and mapping["assessment"]["evidence_status"] != "AVAILABLE":
            return
        params = [index["parameter_sets"][p] for p in result["parameter_set_ids"]]
        result["level"] = scientific_level(r, index, verified, params, strict)
        result["mkm_status"] = "eligible" if result["level"] == LEVELS[4] else "blocked"


def by_reaction(records, index, name):
    result = {}
    for item in records:
        key = item["reaction_id"]
        if key not in index["reactions"] or key in result:
            raise ValueError(f"Unknown or duplicate {name} reaction")
        result[key] = item
    return result


def bind_ts_review(result, review):
    binding = ts_binding(review)
    r = result["definition"]
    identity = (r.get("state_identities") or {}).get("TS") or r.get("ts_id")
    if (binding.get("grade") != "A" or not binding.get("assignment") or not binding.get("review_reference")
            or not identity or binding.get("structure_identity") != identity):
        raise ValueError("TS review lacks a matching Grade A structure and assignment")
    result["ts_review"] = {"review_sha256": sha256_json(review), "grade": "A", "structure_identity": identity,
                           "assignment": binding["assignment"], "review_reference": binding["review_reference"]}


def build_network(definition, *, intakes=(), thermochemistry=(), sources=(), verified_hashes=(), decisions=(), ts_reviews=(),
                  site_proposal=None, site_confirmation=None, site_catalog=None):
    """Build a snapshot in memory. Only an imported validated Phase 1 bundle can convey kinetic eligibility."""
    if site_proposal is None and (site_confirmation is not None or site_catalog is not None):
        raise ValueError("A site confirmation or catalog needs its original proposal")
    inputs = dict(intakes=intakes, thermochemistry=thermochemistry, sources=sources,
                  verified_hashes=verified_hashes, decisions=decisions, ts_reviews=ts_reviews)
    if site_proposal is not None:
        if decisions:
            raise ValueError("Review the rebuilt scientific subject separately")
        parent = _assemble_network(definition, None, None, None, **inputs)
        if (site_proposal.get("format") != "site-mapping-proposal/1"
                or site_proposal.get("parent_network_version") != parent["network_version"]
                or site_proposal.get("reaction_id") not in parent["validation_report"]["levels"]):
            raise ValueError("Site proposal does not match the parent network or reaction")
    return _assemble_network(definition, site_proposal, site_confirmation, site_catalog, **inputs)


def _review_sites(index, proposal, confirmation, configuration):
    if proposal is None:
        return None, set()
    review = apply_review(index, proposal, confirmation, configuration)
    if confirmation is None:
        return review, set()
    validate_confirmation(index["reactions"][proposal["reaction_id"]])
    zero_species = {sid for sid, v in confirmation["mapping"]["occupancies"].items()
                    if v is not None and not any(v.values())}
    return review, zero_species


def _assemble_network(definition, site_proposal, site_confirmation, site_catalog, *, intakes, thermochemistry, sources,
                      verified_hashes, decisions, ts_reviews):
    data = deepcopy(definition)
    strict = data.get("format") != "network-definition/1"
    if strict:
        validate_bundle(data)
    else:
        data.setdefault("reactions", []).extend(endpoint_candidate(p) for p in data.get("endpoint_candidates", []))
    validate_finite_tree(data)
    index = catalog(data)
    for record in index["reactions"].values():
        validate_scope_fields(record)
        validate_confirmation(record)
    mappings = apply_intakes(intakes, index)
    review, zero_species = _review_sites(index, site_proposal, site_confirmation, site_catalog)
    strict_unchanged = strict and data == definition
    fingerprints = register_species(index, zero_species, snapshot_v1=True)
    reviews = by_reaction(decisions, index, "network review")
    thermal = by_reaction(thermochemistry, index, "thermochemistry")
    ts = by_reaction(ts_reviews, index, "TS review")
    if not index["reactions"]:
        raise ValueError("Network needs at least one reaction")
    results, seen = [], set()
    for key, record in index["reactions"].items():
        keys = reaction_keys(record)
        if keys & seen:
            raise ValueError("Duplicate elementary reaction")
        seen.update(keys)
        result = inspect_reaction(record, index, thermal.get(key), mappings.get(key))
        if review and key == site_proposal["reaction_id"]:
            result["site_review"] = review
            result["site_balance_by_domain"] = domain_balance(record, index)
        if key in ts:
            bind_ts_review(result, ts[key])
        apply_decision(result, reviews.get(key), index, strict_unchanged, set(verified_hashes))
        record_review_status(result, LEVELS[3:])
        results.append(result)
    for p in index["parameter_sets"].values():
        if p["reaction_id"] not in index["reactions"]:
            raise ValueError("Unknown parameter reaction")
        reaction = index["reactions"][p["reaction_id"]]
        if reaction.get("reversible") is False and p.get("reverse") is not None:
            raise ValueError("Irreversible reaction has a reverse rate")
        for term in p.get("coverage_terms", []):
            species = index["species"].get(term["species_id"])
            if not species or species["phase"] != "surface":
                raise ValueError("Unknown or non-surface coverage species")
            _check_species_context(species, reaction)
    cycles = check_cycles(results)
    summary = {"levels": {r["definition"]["reaction_id"]: r["level"] for r in results},
               "independent_cycles_checked": cycles, "reactions": {r["definition"]["reaction_id"]: r["gaps"] for r in results},
               "mkm_status": "eligible" if all(r["mkm_status"] == "eligible" for r in results) else "blocked",
               "execution_authorized": False}
    payload = {"format": "reaction-network/1", "project_id": next(iter(index["projects"])),
               "catalog": {g: list(index[g].values()) for g, _, _ in COLLECTIONS[:6]},
               "species": list(index["species"].values()), "species_fingerprints": fingerprints, "reactions": results,
               "parameter_sets": list(index["parameter_sets"].values()), "source_artifacts": list(sources),
               "definition_sha256": sha256_json(definition), "site_mapping_version": sha256_json([
                   index["sites"], {s: r.get("site_occupancy") for s, r in index["species"].items()},
                   {rid: [e for e in m["evidence"] if e["kind"] in ("site_mapping", "site_inference")] for rid, m in mappings.items()},
                   [[entry["direction"]["forward"], entry["definition"].get("required_sites")] for entry in results]]),
               "thermochemistry_version": sha256_json([[r["energies"], r["thermochemistry"]] for r in results]),
               "acceptance_record": {r["definition"]["reaction_id"]: {"scientific_review": r["scientific_review"],
                                      "user_confirmation": r["user_confirmation"], "network_review": r["network_review"]} for r in results},
               "validation_report": summary}
    if review:
        payload["site_mapping_version"] = sha256_json([payload["site_mapping_version"], review])
    return {"network_version": sha256_json(payload), **payload}
