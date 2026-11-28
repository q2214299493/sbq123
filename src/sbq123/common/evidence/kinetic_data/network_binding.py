"""Bind V2.1 rate rows to one independently supplied reaction network."""
from sbq123.common.evidence.kinetic_data.stoichiometric_sources import indexed
from sbq123.common.workflow.multiphase_contracts import _check_species_context
from sbq123.common.reaction_network.reaction_network.builder import directions
from sbq123.common.reaction_network.reaction_network.catalog import check_context, check_record_field, index_records, site_counts


def _check_direction(name, applicable, flux, coefficient, parameter):
    if applicable is None:
        if any(value is not None for value in (flux, coefficient, parameter)):
            raise ValueError(f"Unknown {name} direction must remain unknown")
    elif not applicable:
        if flux != "not_applicable" or coefficient not in (None, "not_applicable") or parameter is not None:
            raise ValueError(f"Excluded {name} direction has a rate or parameter")
    else:
        if flux == "not_applicable" or coefficient == "not_applicable":
            raise ValueError(f"Applicable {name} direction cannot be excluded")
        if (flux is not None or coefficient is not None) and not isinstance(parameter, dict):
            raise ValueError(f"Missing {name} parameter binding")


def _check_row(row, entry, parameter, coefficients, catalog):
    definition = entry["definition"]
    for field in ("reaction_type", "surface_ids", "phase_ids", "interface_id"):
        check_record_field("reaction", field, definition[field])
    phases = check_context(definition, catalog)
    if set(definition["phase_ids"]) != phases or not phases <= catalog["phases"].keys():
        raise ValueError("Reaction scope differs from the bound phase catalog")
    if definition["reaction_type"] in ("interfacial", "interphase_transfer", "cross_phase_elementary") and not definition["interface_id"]:
        raise ValueError("Missing bound reaction interface")
    for sid in row["reactants"].keys() | row["products"].keys():
        _check_species_context(catalog["species"][sid], definition)
    for field in ("sites_consumed", "sites_released"):
        site_counts(row[field], catalog, definition["surface_ids"], definition["interface_id"])
    expected = directions(definition)
    for field, counts in expected["forward"].items():
        check_record_field("reaction", field, counts)
    if entry["direction"] != expected or any(row[k] != v for k, v in expected["forward"].items()):
        raise ValueError("Reaction direction or signed stoichiometry differs from the network")
    allowed = entry["parameter_set_ids"]
    if not isinstance(allowed, list) or row["parameter_set_id"] not in allowed or parameter["reaction_id"] != row["reaction_id"]:
        raise ValueError("Parameter set does not belong to this reaction")
    for name, applicable in (("forward", True), ("reverse", definition["reversible"])):
        check_record_field("kinetic_parameter", name, parameter[name])
        _check_direction(name, applicable, row[name], coefficients.get(name), parameter[name])


def validate_bound_rows(payload, network, reaction_ids=None):
    """Check schema-validated rows after network digest and catalog validation."""
    try:
        entries = network["reactions"]
        definitions = [entry["definition"] for entry in entries]
        catalog = index_records(dict(network["catalog"], species=network["species"], reactions=definitions,
                                     parameter_sets=network["parameter_sets"]))
        if network["project_id"] not in catalog["projects"]:
            raise ValueError("Network project differs from the catalog")
        by_id = {entry["definition"]["reaction_id"]: entry for entry in entries}
        expected = set(by_id)
        if reaction_ids is not None:
            if isinstance(reaction_ids, str):
                raise ValueError("Expected a sequence of reaction IDs")
            ids = tuple(reaction_ids)
            expected = set(ids)
            if not expected or len(expected) != len(ids) or not expected <= by_id.keys():
                raise ValueError("Invalid declared reaction subset")
        if {row["reaction_id"] for row in payload["reaction_rates"]} != expected:
            raise ValueError("Rate reactions differ from the declared network subset")
        coefficients = indexed(payload.get("rate_coefficients", []), "reaction_id")
        for row in payload["reaction_rates"]:
            rid = row["reaction_id"]
            parameter = catalog["parameter_sets"][row["parameter_set_id"]]
            _check_row(row, by_id[rid], parameter, coefficients.get(rid, {}), catalog)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Incomplete network reaction or parameter binding: {exc}") from exc
