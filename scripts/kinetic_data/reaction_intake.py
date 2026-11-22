"""Inspect reaction evidence and scoped human decisions without executing a workflow."""
from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache

from jsonschema import Draft202012Validator, FormatChecker

from scripts.runtime_resources import resource_path

STATES = ("IS", "TS", "FS")
STATE_FIELDS = ("structure", "electronic_energy", "spectrum", "corrections")
REACTION_FIELDS = ("temperature", "pressure", "standard_state", "site_inference",
                   "site_mapping", "forward_rate", "reverse_rate")
OPERATIONS = ("electronic", "zpe", "thermochemistry", "site_mapping", "kinetic_handoff")
AVAILABLE = "AVAILABLE"
UNVERIFIED = "AVAILABLE_BUT_UNVERIFIED"
MISSING = "MISSING"
INCOMPATIBLE = "INCOMPATIBLE"
OPTIONAL = "NOT_REQUIRED_FOR_CURRENT_OPERATION"


@lru_cache(maxsize=1)
def validator():
    path = resource_path("configs/kinetics/scientific_intake.schema.json")
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")), format_checker=FormatChecker())


def inspect_record(record, operation, context):
    kind = record["kind"]
    value = record["value"]
    review = record["validation"]
    decision = record["acceptance"]
    accepted = decision["acceptance_status"] == "accepted" and operation in decision["acceptance_scope"]
    reasons = []
    if (review["validation_status"] == "rejected" or review["compatibility_status"] == "incompatible"
            or (decision["acceptance_status"] == "rejected" and operation in decision["acceptance_scope"])):
        return INCOMPATIBLE, False, ["Rejected evidence or incompatible method/context"]
    required = validator().schema["$defs"][kind]["properties"]
    if operation == "zpe" and kind == "corrections":
        required = ("structure_identity", "thermal_basis", "zpe_ev")
    reasons.extend(f"Missing {field}" for field in required if value.get(field) is None)
    if kind == "spectrum" and value.get("frequencies_cm1"):
        frequencies = value["frequencies_cm1"]
        if value.get("expected_modes") is not None and value["expected_modes"] != len(frequencies):
            reasons.append("Incomplete spectrum for the declared constraint subspace")
        if sum(f < 0 for f in frequencies) != int(record["state"] == "TS"):
            return INCOMPATIBLE, False, ["Imaginary-mode count inconsistent with state assignment"]
    if reasons:
        return UNVERIFIED, False, reasons
    for name, expected in context.items():
        if name in value and value[name] != expected:
            return INCOMPATIBLE, False, [f"{name} differs from the selected reaction context"]
    validated = (review["validation_status"] == "validated" and kind in review["validated_properties"]
                 and bool(review.get("validation_method")) and review["compatibility_status"] == "compatible")
    if kind == "site_mapping" and not (accepted or validated):
        reasons.append("Site assignment needs review or a scoped human decision")
    if record["mode"] == "USER_APPROVED_ASSUMPTION" or record.get("provenance", {}).get("source_type") == "assumption":
        if not accepted or not review["limitations"]:
            return UNVERIFIED, False, ["Assumption needs scoped acceptance and explicit limitations"]
        return UNVERIFIED, True, ["Assumption accepted only for the stated operation"]
    if validated:
        return AVAILABLE, True, []
    if accepted and review["limitations"]:
        return UNVERIFIED, True, ["Accepted for this operation with the recorded limitations"]
    return UNVERIFIED, False, reasons or ["Scientific review or scoped acceptance with limitations needed"]


def assess_field(records, operation, context):
    candidates = []
    for record in records:
        status, usable, reasons = inspect_record(record, operation, context)
        candidates.append({"record_id": record["id"], "status": status, "usable": usable, "reasons": reasons})
    usable_records = [record for record, result in zip(records, candidates) if result["usable"]]
    reasons = []
    if any(r["value"] != usable_records[0]["value"] for r in usable_records):
        status, selected = INCOMPATIBLE, None
        reasons.append("Conflicting admissible values; reconcile their context")
    elif usable_records:
        statuses = {entry["record_id"]: entry["status"] for entry in candidates}
        selected = next((r for r in usable_records if statuses[r["id"]] == AVAILABLE), usable_records[0])
        status = statuses[selected["id"]]
    else:
        selected = None
        statuses = {candidate["status"] for candidate in candidates}
        status = UNVERIFIED if UNVERIFIED in statuses else INCOMPATIBLE if candidates else MISSING
        if not candidates:
            reasons.append("No evidence supplied")
    return {"evidence_status": status, "usable": selected is not None,
            "selected": selected["id"] if selected else None, "reasons": reasons, "candidates": candidates}


def collect_records(documents):
    reaction = documents[0].get("reaction_id")
    groups = defaultdict(list)
    by_id = {}
    warnings = []
    conditions_policy = {}
    for document in documents:
        json.dumps(document, allow_nan=False)
        validator().validate(document)
        if reaction != document["reaction_id"]:
            raise ValueError("Cannot combine different reaction IDs")
        for key in ("reversible", "pressure_dependent"):
            if document.get(key) is not None and conditions_policy.setdefault(key, document[key]) != document[key]:
                raise ValueError(f"Conflicting reaction setting: {key}")
        for record in document["records"]:
            rid = record["id"]
            if rid in by_id:
                if record != by_id[rid]:
                    raise ValueError(f"Conflicting evidence ID: {rid}")
                continue
            by_id[rid] = record
            groups[record["state"], record["kind"]].append(record)
            missing = [p for p in ("source_type", "source_reference", "source_artifact_hash",
                                   "supplied_by", "source_date") if not record.get("provenance", {}).get(p)]
            if missing:
                warnings.append({"record_id": rid, "missing_provenance": missing})
            if not record.get("uncertainty"):
                warnings.append({"record_id": rid, "missing_metadata": ["uncertainty"]})

    return groups, by_id, warnings, conditions_policy


def assess_states(groups, by_id, operation):
    fields = {}

    def selected(key):
        return by_id.get(fields[key]["selected"], {}).get("value", {})

    for kind in REACTION_FIELDS:
        fields[f"reaction.{kind}"] = assess_field(groups["reaction", kind], operation, {})
    conditions = {}
    if operation != "zpe":
        if temperature := selected("reaction.temperature"):
            conditions["temperature_k"] = temperature["kelvin"]
        if standard := selected("reaction.standard_state"):
            conditions["standard_state"] = standard["convention"]
    for state in STATES:
        context = conditions.copy()
        for kind in STATE_FIELDS:
            fields[f"{state}.{kind}"] = assess_field(groups[state, kind], operation, context)
            if kind == "structure" and (structure := selected(f"{state}.structure")):
                context["structure_identity"] = structure["identity"]
    references = {selected(f"{s}.electronic_energy").get("energy_reference") for s in STATES} - {None}
    if len(references) > 1:
        for state in STATES:
            key = f"{state}.electronic_energy"
            if selected(key):
                incompatible(fields[key], "Electronic energy references differ between states")

    return fields


def incompatible(field, reason):
    field.update(evidence_status=INCOMPATIBLE, usable=False, selected=None)
    field["reasons"].append(reason)


def thermal_routes(fields, by_id):
    def selected(key):
        return by_id.get(fields[key]["selected"], {}).get("value", {})

    required = set()
    routes = {}
    bases_by_state = {}
    for state in STATES:
        bases_by_state[state] = {selected(f"{state}.{k}")["thermal_basis"]
                                 for k in ("corrections", "spectrum") if selected(f"{state}.{k}")}
    available_bases = [b for b in bases_by_state.values() if b]
    common_bases = set.intersection(*available_bases) if available_bases else set()
    basis = min(common_bases, default=None)
    for state in STATES:
        keys = [f"{state}.corrections", f"{state}.spectrum"]
        choice = next((k for k in keys if basis and selected(k).get("thermal_basis") == basis), None)
        routes[state] = choice
        if choice:
            required.add(choice)
        else:
            required.update(keys)
            if bases_by_state[state] and not common_bases:
                for k in keys:
                    if selected(k):
                        incompatible(fields[k], "No common thermal basis across supplied states")
    return routes, required


def operation_requirements(operation, conditions_policy):
    required = set()
    if operation in ("electronic", "thermochemistry", "kinetic_handoff"):
        required.update(f"{s}.{k}" for s in STATES for k in ("structure", "electronic_energy"))
    if operation == "zpe":
        required.update(f"{s}.structure" for s in STATES)
    if operation in ("thermochemistry", "kinetic_handoff"):
        required.update(("reaction.temperature", "reaction.standard_state"))
        if conditions_policy.get("pressure_dependent"):
            required.add("reaction.pressure")
    if operation in ("site_mapping", "kinetic_handoff"):
        required.add("reaction.site_mapping")
    if operation == "kinetic_handoff":
        required.update(("reaction.pressure", "reaction.forward_rate", "reaction.reversible"))
        if conditions_policy.get("reversible", True):
            required.add("reaction.reverse_rate")
    return required


def reuse_correction_conditions(fields, by_id, routes):
    corrections = [fields[k] for k in routes.values() if k and k.endswith(".corrections")]
    for kind, name in (("temperature", "temperature_k"), ("standard_state", "standard_state")):
        field = fields[f"reaction.{kind}"]
        if not corrections or field["candidates"]:
            continue
        sources = [f["selected"] for f in corrections]
        values = {by_id[rid]["value"][name] for rid in sources}
        if len(values) != 1:
            incompatible(field, f"Selected corrections have different {name} values")
            continue
        status = AVAILABLE if all(f["evidence_status"] == AVAILABLE for f in corrections) else UNVERIFIED
        field.update(evidence_status=status, usable=True, derived_from=sources, value=values.pop(),
                     reasons=["Condition documented in the selected precomputed corrections"])


def report(documents, operation="thermochemistry"):
    if operation not in OPERATIONS or not documents:
        raise ValueError("Supply a reaction intake and a supported operation")
    groups, by_id, warnings, conditions_policy = collect_records(documents)
    fields = assess_states(groups, by_id, operation)
    direction_known = "reversible" in conditions_policy
    fields["reaction.reversible"] = {
        "evidence_status": AVAILABLE if direction_known else MISSING, "usable": direction_known,
        "value": conditions_policy.get("reversible"),
        "reasons": [] if direction_known else ["Confirm whether the kinetic model includes the reverse reaction"],
    }
    required = operation_requirements(operation, conditions_policy)
    routes = {}
    if operation in ("zpe", "thermochemistry", "kinetic_handoff"):
        routes, thermal_required = thermal_routes(fields, by_id)
        required.update(thermal_required)
        if operation != "zpe":
            reuse_correction_conditions(fields, by_id, routes)
    for key, field in fields.items():
        field["status"] = field["evidence_status"] if key in required else OPTIONAL
    gaps = sorted(key for key in required if not fields[key]["usable"])
    alternatives = [[f"{state}.corrections", f"{state}.spectrum"] for state, route in routes.items()
                    if route is None]
    return {"reaction_id": documents[0]["reaction_id"], "operation": operation, "fields": fields,
            "thermal_routes": routes, "unresolved_one_of": alternatives, "unresolved_fields": gaps,
            "inputs_complete": not gaps,
            "warnings": warnings, "execution_authorized": False,
            "mkm_status": "blocked" if gaps and operation == "kinetic_handoff" else "requires_existing_kinetic_contract"}
