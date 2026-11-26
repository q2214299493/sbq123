"""Molecules per declared reference and site fractions on independent inventories."""

from math import fsum, isclose

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


def inventory_basis(result, references, measured):
    """Bind optional count output to one declared repeat or finite sample."""
    reference = result.get("inventory_reference")
    members = {site: row["physical_site_ids"] for site, row in measured.items() if row.get("physical_site_ids") is not None}
    if reference is None:
        if members:
            raise ValueError("physical_site_ids require an inventory_reference")
        return None, {}, {}
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("Expected a named inventory_reference")
    capacities = dict(references.get(reference) or {})
    owners = {}
    conflicts = {}
    for site, ids in members.items():
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i.strip() for i in ids):
            raise ValueError(f"{site}: expected a nonempty list of physical site IDs or null")
        if len(set(ids)) != len(ids) or capacities.get(site) not in (None, len(ids)):
            conflicts[site] = "physical membership conflicts with capacity or repeats a physical site"
        for member in set(ids):
            owners.setdefault(member, set()).add(site)
        capacities[site] = len(ids)
    for member, sites in sorted(owners.items()):
        if len(sites) > 1:
            for site in sites:
                conflicts[site] = f"physical site {member} claimed by {sorted(sites)}; declare one shared inventory ID"
    for site in conflicts:
        capacities[site] = None
    return reference, capacities, conflicts


def count_on_reference(amount, basis, sizes, reference, capacities):
    if amount is None or basis is None:
        return None
    if basis["kind"] == "declared" and basis["id"] == reference:
        return amount
    ratios = [capacities[q] / size for q, size in sizes.items() if size is not None and capacities.get(q) is not None]
    if not ratios or not isclose(min(ratios), max(ratios), rel_tol=1e-12):
        return None
    return finite_number(amount * min(ratios), f"molecules per {reference}")


def occupied_share(amount, multiplicity, size, *, label, count_reference, count, capacity, conflicted):
    fraction = amount * multiplicity / size if amount is not None and size is not None and not conflicted else None
    share = {"multiplicity": multiplicity}
    if count_reference is not None:
        occupied = finite_number(count * multiplicity, f"{label} occupied sites") if count is not None and not conflicted else None
        share["occupied_sites"] = occupied
        if fraction is None and occupied is not None and capacity is not None:
            fraction = occupied / capacity
    if fraction is not None and finite_number(fraction, f"{label} occupied_fraction", nonnegative=True) > 1:
        raise ValueError(f"{label}: occupied fraction exceeds one")
    share["occupied_fraction"] = fraction
    return share


def molecular_basis(sid, footprint, observation, references):
    reference = observation.get("molecular_reference")
    if reference is not None:
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError(f"{sid}: invalid molecular_reference")
        return {"kind": "declared", "id": reference}, references.get(reference) or {}
    if footprint and len(footprint) == 1 and "molecular_reference" not in observation:
        # Phase 3.0 single-inventory coverage is molecules per site of that inventory.
        site = next(iter(footprint))
        return {"kind": "inventory_site", "id": site}, {site: 1}
    return None, {}


def footprint_evidence(species, observation, inventory, *, localize_conflicts):
    domains = species["surface_ids"]
    sid = species["species_id"]
    catalog = {"sites": inventory}
    footprint = counts(species["site_occupancy"], catalog, domains, species.get("interface_id"))
    if "site_occupancy" in observation:
        repeated = counts(observation["site_occupancy"], catalog, domains, species.get("interface_id"))
        if repeated != footprint:
            if not localize_conflicts:
                raise ValueError(f"{sid}: observed occupancy conflicts with network")
            if repeated is not None and footprint is not None:
                disputed = {q for q in repeated.keys() | footprint.keys() if repeated.get(q, 0) != footprint.get(q, 0)}
                agreed = {q: n for q, n in footprint.items() if q not in disputed}
                return None, agreed, disputed, [f"{sid}: conflicting multiplicity on {sorted(disputed)}"]
    if footprint is None:
        possible = {q for q, desc in inventory.items() if (not domains or desc["surface_id"] in domains)
                    and desc.get("interface_id") in (None, species.get("interface_id"))}
        return None, {}, possible, [f"{sid}: site_occupancy on {domains}"]
    return footprint, footprint, set(), []


def molecular_row(species, observation, references, inventory, *, count_reference=None, conflicts=()):
    sid = species["species_id"]
    domains = species["surface_ids"]
    footprint, agreed, unknown, mapping_gaps = footprint_evidence(
        species, observation, inventory, localize_conflicts=count_reference is not None
    )
    amount = observation.get("coverage")
    if amount is not None:
        amount = quantity(amount, f"{sid} coverage", nonnegative=True)
    missing = []
    basis, sizes = molecular_basis(sid, footprint, observation, references)
    if basis is None:
        missing.append(f"{sid}: molecular_reference")
    if amount is None:
        missing.append(f"{sid}: coverage measurement")
    capacities = references.get(count_reference) or {}
    count = None
    if count_reference is not None:
        count = count_on_reference(amount, basis, sizes, count_reference, capacities)
        if amount is not None and basis is not None and count is None:
            missing.append(f"{sid}: consistent capacity ratio to {count_reference}")
    missing.extend(mapping_gaps)
    contributions = {}
    for site in sorted(unknown):
        contributions[site] = {"multiplicity": None, "occupied_fraction": None}
        if count_reference is not None:
            contributions[site]["occupied_sites"] = None
    for site, multiplicity in agreed.items():
        size = sizes.get(site)
        share = occupied_share(amount, multiplicity, size, label=f"{sid}/{site}", count_reference=count_reference,
                               count=count, capacity=capacities.get(site), conflicted=site in conflicts)
        if basis is not None and size is None and share["occupied_fraction"] is None:
            missing.append(f"{sid}: sites_per_molecular_reference[{basis['id']}][{site}]")
        contributions[site] = share
    molecule = dict(
        species_id=sid,
        surface_ids=domains,
        interface_id=species.get("interface_id"),
        site_occupancy=footprint,
        molecular_reference=basis,
        molecular_coverage=amount if basis is not None else None,
        missing=missing,
    )
    if count_reference is not None:
        molecule["molecule_count"] = {"reference": count_reference, "value": count}
    return molecule, contributions


def inventory_balance(site, contributions, measurement, *, conflicted=False):
    occupied = measurement.get("occupied_fraction")
    vacant = measurement.get("vacancy_fraction")
    for value in (occupied, vacant):
        if value is not None and quantity(value, f"{site} fraction", nonnegative=True) > 1:
            raise ValueError(f"{site}: fraction exceeds one")
    if occupied is not None and vacant is not None:
        check_close(occupied + vacant, 1, f"{site} vacancy balance", absolute=1e-8)
    shares = {s: c["occupied_fraction"] for s, c in contributions.items()}
    known = fsum(x for x in shares.values() if x is not None)
    complete = not conflicted and all(x is not None for x in shares.values())
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


def inventory_amounts(site, reference, capacity, shares, measurement, conflict):
    missing = []
    occupied = vacant = None
    if conflict:
        missing.append(conflict)
    else:
        if capacity is None:
            missing.append(f"{site}: capacity per {reference}")
        amounts = [share["occupied_sites"] for share in shares.values()]
        if all(value is not None for value in amounts):
            occupied = fsum(amounts)
        if capacity is not None:
            observed = measurement.get("occupied_fraction")
            if observed is None and measurement.get("vacancy_fraction") is not None:
                observed = 1 - measurement["vacancy_fraction"]
            if observed is not None:
                if occupied is None:
                    occupied = observed * capacity
                else:
                    check_close(occupied / capacity, observed, f"{site} occupied count", absolute=1e-8)
            if occupied is not None:
                if occupied > capacity:
                    check_close(occupied / capacity, 1, f"{site} exceeds capacity", absolute=1e-8)
                    occupied = capacity
                vacant = capacity - occupied
        if occupied is None:
            missing.append(f"{site}: complete species counts or independent total with capacity")
    return dict(reference=reference, capacity=capacity, occupied=occupied, vacant=vacant, missing=missing)


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
                relevant.update(s for s, v in sites.items() if v["surface_id"] in reaction["surface_ids"]
                                and v.get("interface_id") in (None, reaction.get("interface_id")))
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
    reference, capacities, conflicts = inventory_basis(result, references, measured)
    if reference is not None:
        references = {**references, reference: capacities}
    contributions = {site: {} for site in inventory}
    molecules = []
    for sid, species in adsorbates.items():
        obs = observed.get(sid, {})
        if obs.get("phase", "surface") != "surface":
            raise ValueError(f"{sid}: observed phase differs")
        molecule, shares = molecular_row(species, obs, references, inventory, count_reference=reference, conflicts=conflicts)
        molecule["phase_ids"] = list(dict.fromkeys(surfaces[s].get("phase_id") for s in species["surface_ids"]))
        molecules.append(molecule)
        for site, share in shares.items():
            contributions[site][sid] = share
    sites = {}
    for site, desc in inventory.items():
        surface = desc["surface_id"]
        sites[site] = dict(
            phase_id=surfaces[surface].get("phase_id"),
            surface_id=surface,
            site_type=desc["site_type"],
            **inventory_balance(site, contributions[site], {} if site in conflicts else measured.get(site, {}),
                                conflicted=site in conflicts),
        )
        if desc.get("interface_id") is not None:
            sites[site]["interface_id"] = desc["interface_id"]
        if reference is not None:
            sites[site]["site_counts"] = inventory_amounts(
                site, reference, capacities.get(site), contributions[site], measured.get(site, {}), conflicts.get(site)
            )
    vacancy_requirements(network, sites)
    return molecules, sites
