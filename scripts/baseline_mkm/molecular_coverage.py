"""Molecules per declared reference and site fractions on independent inventories."""

from scripts.baseline_mkm.single_point_result import check_close
from scripts.reaction_network.site_review import counts
from scripts.scientific_validation import finite_number


def quantity(value, label, **limits):
    if not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return finite_number(value, label, **limits)


def reference_counts(result, inventory):
    references = result.get("sites_per_molecular_reference")
    if references is None:
        return {}
    if not isinstance(references, dict):
        raise ValueError("Expected sites_per_molecular_reference to be an object")
    for reference, sizes in references.items():
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("Expected a named molecular reference and a site inventory")
        if sizes is None:
            continue
        if not isinstance(sizes, dict):
            raise ValueError(f"Invalid inventory sizes for {reference}")
        if sizes.keys() - inventory.keys():
            raise ValueError(f"Unknown inventory in molecular reference {reference}")
        for site, size in sizes.items():
            if size is not None:
                quantity(size, f"{reference}/{site} sites per reference", positive=True)
    return references


def molecular_row(species, observation, references, inventory):
    sid = species["species_id"]
    domains = species["surface_ids"]
    footprint = counts(species["site_occupancy"], {"sites": inventory}, domains)
    if "site_occupancy" in observation and counts(observation["site_occupancy"], {"sites": inventory}, domains) != footprint:
        raise ValueError(f"{sid}: observed occupancy conflicts with network")
    amount = observation.get("coverage")
    if amount is not None:
        amount = quantity(amount, f"{sid} coverage", nonnegative=True)
    missing = []
    reference = observation.get("molecular_reference")
    sizes = {}
    if reference is not None:
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError(f"{sid}: invalid molecular_reference")
        basis = {"kind": "declared", "id": reference}
        sizes = references.get(reference) or {}
    elif footprint and len(footprint) == 1 and "molecular_reference" not in observation:
        # Phase 3.0 single-inventory coverage is molecules per site of that inventory.
        site = next(iter(footprint))
        basis = {"kind": "inventory_site", "id": site}
        sizes = {site: 1}
    else:
        basis = None
        missing.append(f"{sid}: molecular_reference")
    if amount is None:
        missing.append(f"{sid}: coverage measurement")
    contributions = {}
    if footprint is None:
        missing.append(f"{sid}: site_occupancy on {domains}")
        # The unknown footprint can affect only inventories in its possible domains.
        for site, desc in inventory.items():
            if not domains or desc["surface_id"] in domains:
                contributions[site] = {"multiplicity": None, "occupied_fraction": None}
    else:
        for site, multiplicity in footprint.items():
            size = sizes.get(site)
            if basis is not None and size is None:
                missing.append(f"{sid}: sites_per_molecular_reference[{reference}][{site}]")
            occupied = amount * multiplicity / size if amount is not None and size is not None else None
            if occupied is not None:
                if finite_number(occupied, f"{sid}/{site} occupied_fraction", nonnegative=True) > 1:
                    raise ValueError(f"{sid}/{site}: occupied fraction exceeds one")
            contributions[site] = {"multiplicity": multiplicity, "occupied_fraction": occupied}
    return dict(
        species_id=sid,
        surface_ids=domains,
        interface_id=species.get("interface_id"),
        site_occupancy=footprint,
        molecular_reference=basis,
        molecular_coverage=amount if basis is not None else None,
        missing=missing,
    ), contributions


def inventory_balance(site, contributions, measurement):
    occupied = measurement.get("occupied_fraction")
    vacant = measurement.get("vacancy_fraction")
    for value in (occupied, vacant):
        if value is not None and quantity(value, f"{site} fraction", nonnegative=True) > 1:
            raise ValueError(f"{site}: fraction exceeds one")
    if occupied is not None and vacant is not None:
        check_close(occupied + vacant, 1, f"{site} vacancy balance", absolute=1e-8)
    shares = {s: c["occupied_fraction"] for s, c in contributions.items()}
    known = sum(x for x in shares.values() if x is not None)
    complete = all(x is not None for x in shares.values())
    total = occupied if occupied is not None else (1 - vacant if vacant is not None else None)
    if known > (1 if total is None else total) + 1e-8:
        raise ValueError(f"{site}: known contributions exceed inventory")
    if complete:
        if total is not None:
            check_close(known, total, f"{site} occupied site inventory", absolute=1e-8)
        if total is None:
            total = min(known, 1)
    if vacant is None and total is not None:
        vacant = 1 - total
    ranking = sorted(shares, key=lambda s: (-shares[s], s)) if complete else None
    return dict(
        occupied_fraction=total,
        vacancy_fraction=vacant,
        contributions=contributions,
        balance_residual=known + vacant - 1 if complete else None,
        balance_status="balanced" if complete else "incomplete_attribution",
        vacancy_source="measured" if measurement.get("vacancy_fraction") is not None else ("site_balance" if vacant is not None else None),
        competitors=sorted(s for s, c in contributions.items() if c["multiplicity"] is not None),
        unresolved_membership=sorted(s for s, c in contributions.items() if c["multiplicity"] is None),
        coverage_ranking=ranking,
        dominant_adsorbates=([s for s in ranking if known and shares[s] == shares[ranking[0]]] if complete else None),
        activity=[],
    )


def vacancy_requirements(network, sites):
    for entry in network["reactions"]:
        reaction = entry["definition"]
        for direction in ("forward", "reverse"):
            side = entry["direction"][direction]
            if side is None:
                continue
            orders = side.get("sites_consumed")
            # Unknown orders remain explicit even if a particular site has vacancies.
            relevant = set(reaction.get("required_sites") or {}) | set(orders or {})
            if orders is None:
                relevant.update(s for s, v in sites.items() if v["surface_id"] in reaction["surface_ids"])
            for site in sorted(relevant):
                order = orders.get(site, 0) if orders is not None else None
                vacant = sites[site]["vacancy_fraction"]
                factor = None
                if order == 0:
                    factor = 1.0
                elif order is not None and vacant is not None:
                    factor = vacant**order
                sites[site]["activity"].append(
                    dict(
                        reaction_id=reaction["reaction_id"],
                        direction=direction,
                        vacant_site_order=order,
                        mean_field_vacancy_factor=factor,
                    )
                )


def molecular_analysis(network, result, observed, measured, inventory, surfaces):
    references = reference_counts(result, inventory)
    adsorbates = {s["species_id"]: s for s in network["species"] if s["phase"] == "surface"}
    if observed.keys() - {s["species_id"] for s in network["species"]} or measured.keys() - inventory.keys():
        raise ValueError("Unknown species or site observation")
    contributions = {site: {} for site in inventory}
    molecules = []
    for sid, species in adsorbates.items():
        obs = observed.get(sid, {})
        if obs.get("phase", "surface") != "surface":
            raise ValueError(f"{sid}: observed phase differs")
        molecule, shares = molecular_row(species, obs, references, inventory)
        molecule["phase_ids"] = list(dict.fromkeys(surfaces[s]["phase_id"] for s in species["surface_ids"]))
        molecules.append(molecule)
        for site, share in shares.items():
            contributions[site][sid] = share
    sites = {}
    for site, desc in inventory.items():
        surface = desc["surface_id"]
        sites[site] = dict(
            phase_id=surfaces[surface]["phase_id"],
            surface_id=surface,
            site_type=desc["site_type"],
            **inventory_balance(site, contributions[site], measured.get(site, {})),
        )
    vacancy_requirements(network, sites)
    return molecules, sites
