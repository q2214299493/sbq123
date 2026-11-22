"""Apply a researcher decision to a specific version of a site-mapping proposal."""
from collections import Counter
from datetime import datetime

from scripts.artifact_io import sha256_json
from scripts.multiphase_contracts import check_site_interface
from scripts.reaction_network.catalog import check_common, check_context, site_counts, validate_site_types


def agreed(row, field, value):
    if value is None:
        return
    if row.get(field) is not None and row[field] != value:
        raise ValueError(f"Conflicting confirmed {field}")
    row[field] = value


def counts(value, index, domains, interface_id=None):
    """Null is unknown. A supplied empty object or explicit integer zero is known."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Expected a site-count object or null")
    for site, n in value.items():
        if type(n) is not int or n < 0:
            raise ValueError("Site multiplicity must be a nonnegative integer")
        site_counts({site: 1}, index, domains, interface_id)
    return {site: n for site, n in value.items() if n}


def configured_types(index, configuration):
    """Resolve each allowed vocabulary from its own project and surface."""
    types = {}
    for surface, row in index["surfaces"].items():
        declared = row.get("site_types", [s["site_type"] for s in index["sites"].values() if s["surface_id"] == surface])
        types[surface] = set(declared)
    if configuration is not None:
        if (configuration.get("format") != "surface-site-types/1"
                or configuration.get("project_id") not in index["projects"]):
            raise ValueError("Site catalog belongs to a different project or format")
        for surface, labels in configuration["surface_site_types"].items():
            if surface not in types:
                raise ValueError("Unknown site catalog surface")
            validate_site_types(labels)
            if not types[surface].issubset(labels):
                raise ValueError("Site catalog conflicts with existing surface types")
            types[surface] = set(labels)
    return types


def register_sites(index, reaction, definitions, allowed):
    sites = index["sites"]
    seen = set()
    for row in definitions:
        site = row["site_id"]
        for key in ("site_id", "site_type"):
            check_common(row[key], "id")
        geometry = row.get("local_geometry")
        if row["surface_id"] not in reaction["surface_ids"] or not isinstance(geometry, str) or not geometry.strip():
            raise ValueError("Unlocated site or site outside the reaction domain")
        check_site_interface(row, reaction.get("interface_id"))
        if site in sites:
            check_site_interface(sites[site], reaction.get("interface_id"))
        fields = ("surface_id", "site_type", "local_geometry") + (("interface_id",) if "interface_id" in row else ())
        if site in seen or (site in sites and any(sites[site].get(k) != row[k] for k in fields)):
            raise ValueError(f"Conflicting site identity {site}")
        if row["site_type"] not in allowed[row["surface_id"]]:
            raise ValueError("Site type is outside the configured surface catalog")
        seen.add(site)
        sites.setdefault(site, {k: row[k] for k in ("site_id", *fields)})


def apply_review(index, proposal, decision, configuration=None):
    rid = proposal["reaction_id"]
    reaction = index["reactions"][rid]
    record = {"proposal": proposal, "confirmation": decision}
    allowed = configured_types(index, configuration)
    if configuration is not None:
        record["site_catalog"] = configuration
    if decision is None:
        return record
    if (decision.get("proposal_sha256") != sha256_json(proposal)
            or decision.get("scope") != "site_mapping" or decision.get("decision") != "confirmed"):
        raise ValueError("Missing or stale site-mapping confirmation")
    expected = sha256_json(configuration) if configuration is not None else None
    if decision.get("site_catalog_sha256") != expected:
        raise ValueError("Confirmation does not bind the supplied site catalog")
    for field in ("reviewer", "reason", "source_reference"):
        if not isinstance(decision.get(field), str) or not decision[field].strip():
            raise ValueError(f"Confirmation needs {field}")
    if datetime.fromisoformat(decision.get("reviewed_at", "")).tzinfo is None:
        raise ValueError("Confirmation needs a timezone")
    mapping = decision["mapping"]
    if set(mapping) != {"surface_ids", "interface_id", "site_definitions", "occupancies", "sites_consumed",
                        "sites_released", "reaction_type", "reversible"}:
        raise ValueError("Incomplete or unknown mapping fields; use null for unknown counts")
    reaction.update(surface_ids=mapping["surface_ids"], interface_id=mapping["interface_id"])
    check_context(reaction, index)
    register_sites(index, reaction, mapping["site_definitions"], allowed)
    participants = reaction["reactants"].keys() | reaction["products"].keys()
    if set(mapping["occupancies"]) != participants:
        raise ValueError("Identify every participating species; use null for unknown occupancy")
    for sid, values in mapping["occupancies"].items():
        species = index["species"][sid]
        occupied = counts(values, index, species["surface_ids"], species.get("interface_id"))
        agreed(species, "site_occupancy", occupied)
    for field in ("sites_consumed", "sites_released"):
        agreed(reaction, field, counts(mapping[field], index, reaction["surface_ids"], reaction.get("interface_id")))
    if mapping["reaction_type"] is not None:
        reaction["reaction_type"] = mapping["reaction_type"]
    agreed(reaction, "reversible", mapping["reversible"])
    return record


def domain_balance(reaction, index):
    """Report both sides independently for each site inventory; preserve unknowns."""
    report = {}
    for domain in reaction["surface_ids"]:
        sides = []
        for participants, vacancies in (("reactants", "sites_consumed"), ("products", "sites_released")):
            occupied = Counter()
            known = True
            for sid, coefficient in reaction[participants].items():
                species = index["species"][sid]
                if domain not in species["surface_ids"]:
                    continue
                footprint = species.get("site_occupancy")
                if footprint is None:
                    known = False
                else:
                    occupied.update({s: coefficient * n for s, n in footprint.items()
                                     if index["sites"][s]["surface_id"] == domain})
            vacant = reaction.get(vacancies)
            if vacant is not None:
                vacant = {s: n for s, n in vacant.items() if index["sites"][s]["surface_id"] == domain}
            total = dict(occupied + Counter(vacant)) if known and vacant is not None else None
            sides.append({"occupied": dict(occupied) if known else None, "vacant": vacant, "total": total})
        left, right = sides
        complete = left["total"] is not None and right["total"] is not None
        if complete and left["total"] != right["total"]:
            raise ValueError(f"Site conservation failed in domain {domain}")
        report[domain] = {"reactants": left, "products": right, "balanced": True if complete else None}
    return report
