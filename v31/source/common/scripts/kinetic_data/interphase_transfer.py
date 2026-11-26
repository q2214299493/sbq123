"""Directional molecular and inventory checks for an explicitly declared transfer."""


def _endpoint(reaction, index, side, vacancy_field, sign):
    members = reaction[side]
    if len(members) != 1:
        raise ValueError("Interphase transfer requires one resident species on each side")
    species_id, count = next(iter(members.items()))
    row = index["species"][species_id]
    surfaces = set(row["surface_ids"])
    owners = {index["surfaces"][s].get("phase_id") for s in surfaces}
    if row["phase"] != "surface" or not surfaces or len(owners - {None}) > 1:
        raise ValueError("Transfer endpoint requires a surface resident of one phase")
    phase = None if None in owners else next(iter(owners))
    footprint = row.get("site_occupancy")
    vacant = reaction.get(vacancy_field)
    if vacant is not None and any(index["sites"][s]["surface_id"] not in surfaces for s in vacant):
        raise ValueError(f"{vacancy_field} outside transfer endpoint surfaces")
    if vacant == {}:
        raise ValueError(f"{vacancy_field}: transfer resident requires a nonzero vacancy exchange")
    if footprint == {}:
        raise ValueError("A transfer resident requires an occupied site")
    sites = {}
    for site in sorted(set(footprint or {}) | set(vacant or {})):
        occupied = sign * count * footprint.get(site, 0) if footprint is not None else None
        vacancy = -sign * vacant.get(site, 0) if vacant is not None else None
        residual = None if occupied is None or vacancy is None else occupied + vacancy
        if residual not in (None, 0):
            raise ValueError(f"{vacancy_field}: transfer inventory mismatch for {site}")
        required = reaction.get("required_sites")
        known_extent = max(abs(occupied or 0), abs(vacancy or 0))
        if required is not None and required.get(site, 0) < known_extent:
            raise ValueError(f"Insufficient required site footprint for transfer inventory {site}")
        sites[site] = {"occupied_change": occupied, "vacancy_change": vacancy, "capacity_change": residual}
    return {"species_id": species_id, "molecules": count, "phase_id": phase, "surface_ids": sorted(surfaces),
            "site_occupancy": footprint, "vacancies": vacant, "inventories": sites}


def assess_transfer(reaction, index):
    """Use catalog identities and gross stoichiometry already checked by the network or bundle."""
    source = _endpoint(reaction, index, "reactants", "sites_released", -1)
    destination = _endpoint(reaction, index, "products", "sites_consumed", 1)
    if source["molecules"] != destination["molecules"]:
        raise ValueError("Interphase transfer must conserve molecular count")
    if set(source["surface_ids"]) & set(destination["surface_ids"]):
        raise ValueError("Transfer endpoints cannot share a surface")
    source_owners, destination_owners = (
        {index["surfaces"][s].get("phase_id") for s in end["surface_ids"]} - {None}
        for end in (source, destination)
    )
    if source_owners & destination_owners:
        raise ValueError("Interphase transfer requires distinct catalyst phases")
    if set(reaction["surface_ids"]) != set(source["surface_ids"] + destination["surface_ids"]):
        raise ValueError("Reaction surfaces differ from transfer endpoints")
    src, dst = (index["species"][end["species_id"]] for end in (source, destination))
    if src["composition"] != dst["composition"]:
        raise ValueError("Transfer resident compositions differ")
    charges_known = src.get("charge") is not None and dst.get("charge") is not None
    if charges_known and src["charge"] != dst["charge"]:
        raise ValueError("Transfer resident charges differ")
    mapped = all(end["site_occupancy"] is not None and end["vacancies"] is not None for end in (source, destination))
    return {"source": source, "destination": destination, "interface_id": reaction.get("interface_id"),
            "operating_conditions_ref": reaction.get("operating_conditions_ref"),
            "molecule_change": 0, "charge_balanced": True if charges_known else None,
            "element_balanced": True, "stoichiometrically_valid": True if mapped and charges_known else None}
