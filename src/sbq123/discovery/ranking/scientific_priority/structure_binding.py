"""Select named endpoints from a single reaction record in the reviewed network."""
from hashlib import sha256
from pathlib import Path

from sbq123.common.artifacts.artifact_io import canonical_json, require_sha256, sha256_json
from sbq123.common.workflow.multiphase_contracts import read_artifact
from sbq123.common.workflow.runtime_resources import resource_path
from sbq123.common.validation.scientific_validation import finite_number
from sbq123.common.evidence.kinetic_data.scientific_identity import _local_geometry
from sbq123.common.evidence.kinetic_data.analysis_evidence import reviewed_event


def endpoint_records(row, direction):
    definition = row["definition"]
    fields = {"IS": "initial_structure_id", "TS": "ts_id", "FS": "final_structure_id"}
    if direction not in ("forward", "reverse") or not row["direction"].get(direction):
        raise ValueError("Reaction direction unavailable in approved network")
    if direction == "reverse":
        fields["IS"], fields["FS"] = fields["FS"], fields["IS"]
    record_digest = sha256_json(row)
    records = {}
    for role, field in fields.items():
        identity = definition.get(field)
        if identity:
            selector = {"reaction_id": definition["reaction_id"], "field": field}
            records[role] = {"id": identity, "selector": selector, "record_sha256": record_digest}
    return records


def check_structure_claim(claim, record, mock_frame=None):
    if isinstance(claim, str):
        claim = {"id": claim}
    if not isinstance(claim, dict) or claim.get("id") != record["id"]:
        raise ValueError("Structure identity differs from approved reaction endpoint")
    for key, value in claim.items():
        if key == "mock_structure_sha256":
            expected = sha256_json(mock_frame) if mock_frame is not None else sha256(record["id"].encode()).hexdigest()
            if value != expected:
                raise ValueError("Unverified synthetic endpoint target")
        elif key not in record or value != record[key]:
            raise ValueError("Structure selector or record identity differs from approved endpoint")


_CORE_FIELDS = {"site_ids", "initial", "final", "neighbors_zero_based"}
_ENVIRONMENT_FIELDS = {"site_ids", "state", "neighbors_zero_based"}
_MODEL_FIELDS = {"patterns_per_reference_site", "coefficient_basis", "energetics_sha256", "forward_proximity_factor"}


def _validate_model_fields(event):
    if "patterns_per_reference_site" in event:
        counts = event["patterns_per_reference_site"]
        if not isinstance(counts, dict) or "forward" not in counts or counts.keys() - {"forward", "reverse"}:
            raise ValueError("Invalid local event pattern directions")
        for count in counts.values():
            if type(count) not in (int, float):
                raise ValueError("Local event pattern count must be a JSON number")
            finite_number(count, "patterns per reference site", positive=True)
    if "forward_proximity_factor" in event:
        value = event["forward_proximity_factor"]
        if type(value) not in (int, float) or not 0 <= value <= 1:
            raise ValueError("Invalid local event proximity factor")
    if "coefficient_basis" in event:
        basis = event["coefficient_basis"]
        if not isinstance(basis, str) or not basis.strip():
            raise ValueError("Invalid local event coefficient basis")
    if "energetics_sha256" in event:
        digest = event["energetics_sha256"]
        if not isinstance(digest, str):
            raise ValueError("Local event energetics digest must be text")
        require_sha256(digest, label="local event energetics")


def _validate_geometry(event, sites, oriented, species):
    if not isinstance(event, dict) or not _CORE_FIELDS <= event.keys() <= _CORE_FIELDS | {"environment"} | _MODEL_FIELDS:
        raise ValueError("Missing or unknown local event field")
    parts = [event]
    if "environment" in event:
        environment = event["environment"]
        if not isinstance(environment, dict) or environment.keys() != _ENVIRONMENT_FIELDS:
            raise ValueError("Missing or unknown local environment field")
        parts.append(environment)
    for part in parts:
        if not isinstance(part["site_ids"], list) or not all(
            isinstance(site, str) and site in sites for site in part["site_ids"]
        ):
            raise ValueError("Local event site outside approved catalog")
    _validate_model_fields(event)
    _local_geometry(event, oriented, species)
    return canonical_json(event)


def _check_event(candidate, network, row, direction):
    sites = {site["site_id"] for site in network["catalog"]["sites"]}
    species = {s["species_id"]: s for s in network["species"]}
    oriented = dict(row, direction={"forward": row["direction"][direction]})
    declarations = [candidate[key] for key in ("event_geometry", "site_geometry") if key in candidate]
    canonical = [_validate_geometry(event, sites, oriented, species) for event in declarations]
    if len(canonical) == 2 and canonical[0] != canonical[1]:
        raise ValueError("Conflicting local site geometries")
    event = declarations[0]
    if candidate.get("structure_status") == "unverified_hypothesis":
        return  # The caller still validates known endpoint identities and defers the hypothesis.
    approved = reviewed_event(network["network_version"], candidate["scope"]["dataset_version"],
                              row["definition"]["reaction_id"])
    if not isinstance(approved, dict):
        raise ValueError("No approved local event for this geometry")
    # Every structural field is mandatory, including environment when present in the source.
    # Other model parameters are optional claims, checked exactly whenever supplied.
    structural = _CORE_FIELDS | {"environment"}
    expected = {k: v for k, v in approved.items() if k in structural or k in event}
    if direction == "reverse":
        expected["initial"], expected["final"] = approved["final"], approved["initial"]
        if "patterns_per_reference_site" in expected:
            counts = expected["patterns_per_reference_site"]
            expected["patterns_per_reference_site"] = {"forward": counts["reverse"], "reverse": counts["forward"]}
    if canonical[0] != canonical_json(expected):
        raise ValueError("Candidate geometry differs from approved local event")


def _selected_endpoints(candidate, network):
    direction = candidate.get("direction", candidate.get("reaction_direction", "forward"))
    if candidate.get("reaction_direction", direction) != direction:
        raise ValueError("Conflicting reaction directions")
    refs = candidate.get("reaction_structures")
    ids = candidate["reaction_ids"]
    if not ids or (refs is not None and (not isinstance(refs, dict) or set(refs) != set(ids))):
        raise ValueError("Structure map must select exactly the candidate reactions")
    selected = {}
    for rid in ids:
        matches = [r for r in network["reactions"] if r["definition"]["reaction_id"] == rid]
        if len(matches) != 1:
            raise ValueError("Reaction selector must match exactly one approved record")
        row, = matches
        endpoints = endpoint_records(row, direction)
        if refs is not None:
            states = refs[rid]
            if not isinstance(states, dict) or states.keys() != endpoints.keys():
                raise ValueError("Incomplete or unsupported reaction endpoint map")
            for state, claim in states.items():
                check_structure_claim(claim, endpoints[state])
        if "event_geometry" in candidate or "site_geometry" in candidate:
            _check_event(candidate, network, row, direction)
        selected[rid] = endpoints
    return selected[ids[0]]


def _hypothesis(candidate, network, endpoints):
    known = {r["definition"].get(field) for r in network["reactions"]
             for field in ("initial_structure_id", "ts_id", "final_structure_id")} - {None}
    frames = candidate.get("structures")
    if isinstance(frames, dict):
        for state, claim in frames.items():
            identity = claim.get("id") if isinstance(claim, dict) else claim
            if isinstance(identity, str) and identity in known:
                if state not in endpoints:
                    raise ValueError("Unexpected known endpoint in hypothesis")
                check_structure_claim(claim, endpoints[state])
    return "Unverified structure hypothesis requires owner review"


def validate_structures(candidate, network, *, fixture=None):
    """Check every declared identity and return a reason if verified ranking is unsupported."""
    endpoints = _selected_endpoints(candidate, network)
    status = candidate.get("structure_status")
    if status == "unverified_hypothesis":
        return _hypothesis(candidate, network, endpoints)
    if status is not None:
        raise ValueError("Unknown structure qualification")
    structures = candidate.get("structures")
    if not isinstance(structures, dict) or not structures:
        return "Explicit network structure records required to qualify target"
    if fixture is not None and set(structures) == {"species"}:
        # The published generic benchmark also ranks a named intermediate.
        matches = [s for s in network["species"] if s["species_id"] == candidate["parameter"]]
        if len(matches) != 1 or matches[0]["species_id"] not in candidate["species_ids"]:
            raise ValueError("Intermediate does not select a network species")
        endpoints = {"species": {"id": matches[0]["structure_id"], "record_sha256": sha256_json(matches[0])}}
    if set(structures) - endpoints.keys():
        raise ValueError("Unknown structure role for approved reaction")
    targets = candidate.get("targets")
    if not isinstance(targets, dict) or not targets or set(targets) - structures.keys():
        raise ValueError("Target lacks a selected reaction endpoint")
    for state, claim in structures.items():
        record = endpoints[state]
        frame = fixture.get(candidate["parameter"] + "/" + state) if fixture is not None else None
        check_structure_claim(claim, record, frame)
        expected = claim.get("mock_structure_sha256", sha256_json(record)) if isinstance(claim, dict) else sha256_json(record)
        if state in targets and targets[state] != expected:
            raise ValueError("Target digest differs from selected reaction endpoint")
    if candidate.get("reaction_structures") is None:
        return "Explicit network structure records required to qualify target"
    return None

def _source(ref):
    path = Path(ref["path"])
    return read_artifact(path if path.is_absolute() else resource_path(path),
                         expected_sha256=require_sha256(ref["sha256"], label="planning input"))[0]


def ranking_structure_context(data, objective):
    sources = data["sources"]
    ref = sources.get(data.get("planning_network_source", "network"))
    if not isinstance(ref, dict):
        return None, None
    network = _source(ref)
    version = network["network_version"]
    if version != objective["scope"]["network_version"] or version != sha256_json(
            {key: value for key, value in network.items() if key != "network_version"}):
        raise ValueError("Priority network differs from bound model")
    fixture_ref = sources.get("fixture")
    fixture = _source(fixture_ref).get("structures", {}) if isinstance(fixture_ref, dict) else None
    return network, fixture


def qualified_ranking_candidate(candidate, network, fixture):
    if network is None:
        reason = "Reaction structure evidence unavailable"
    else:
        try:
            reason = validate_structures(candidate, network, fixture=fixture)
        except ValueError as error:
            reason = str(error)
    if reason and reason not in candidate.get("blockers", ()):
        return dict(candidate, blockers=[*candidate.get("blockers", ()), reason])
    return candidate
