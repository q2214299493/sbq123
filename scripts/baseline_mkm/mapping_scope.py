"""Structural scope evidenced by the archived two-inventory CATKINAS turnover."""
from itertools import permutations, product

from scripts.kinetic_data.interphase_transfer import assess_transfer
from scripts.reaction_network.builder import directions, structural_gaps
from scripts.reaction_network.catalog import catalog, check_network_version, register_species

# Abstract species and inventory roles in native equations 1-4 of the accepted cycle.
# A token with no molecule before @ is a vacancy. A bare molecule is in the gas phase.
NATIVE_FORMS = {
    "dissociative_adsorption": ("g @a @b", "x@a y@b"),
    "resident_transfer": ("y@b @a", "x@a @b"),
    "gas_surface_association": ("x@a h", "z@a"),
    "desorption": ("z@a", "p @a"),
}


def issue(status, entity, identity, reason):
    return {"status": status, "entity": entity, "id": identity, "reason": reason}


class MappingBlocked(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__("; ".join(f"{i['entity']} {i['id']}: {i['reason']}" for i in issues))


def bijection(bindings):
    # Both species and sites must stay one-to-one across the ENTIRE network.
    return len({(kind, key) for kind, key, _ in bindings}) == len(bindings) == len(
        {(kind, role) for kind, _, role in bindings})


def side_bindings(actual, form):
    tokens = [tuple(part or None for part in word.partition("@")[::2]) for word in form.split()]
    if len(tokens) != len(actual):
        return
    for order in permutations(actual):
        links = set()
        for (sid, site, n), (mol_role, site_role) in zip(order, tokens, strict=True):
            if n != 1 or (sid is None) != (mol_role is None) or (site is None) != (site_role is None):
                break
            if sid is not None:
                links.add(("species", sid, mol_role))
            if site is not None:
                links.add(("site", site, site_role))
        else:
            yield links


def options(r, species):
    sides = []
    for part, vacant in (("reactants", "sites_consumed"), ("products", "sites_released")):
        if r.get(vacant) is None:
            return []
        side = [(None, site, n) for site, n in r[vacant].items()]
        for sid, n in r[part].items():
            s = species[sid]
            footprint = s.get("site_occupancy")
            if s["phase"] == "gas":
                site = None
            elif s["phase"] == "surface" and footprint and list(footprint.values()) == [1]:
                site = next(iter(footprint))
            else:
                return []
            side.append((sid, site, n))
        sides.append(side)
    matches = []
    for name, pair in NATIVE_FORMS.items():
        for a, b in (pair, pair[::-1]):
            for left, right in product(side_bindings(sides[0], a), side_bindings(sides[1], b)):
                links = left | right
                if bijection(links):
                    matches.append((name, links))
    return matches


def matches_cycle(matches, index):
    if len(matches) != len(NATIVE_FORMS) or len(index["sites"]) != 2 or len(index["species"]) != 6:
        return False
    for assignment in product(*matches):
        if len({name for name, _ in assignment}) == len(NATIVE_FORMS):
            if bijection(set().union(*(links for _, links in assignment))):
                return True
    return False


def species_issues(species):
    sid = species["species_id"]
    if species["phase"] == "liquid":
        yield issue("unsupported", "species", sid, "No liquid activity token in the fixed-temperature adapter")
    if species["phase"] == "surface":
        footprint = species.get("site_occupancy")
        if footprint is None:
            yield issue("missing_evidence", "species", sid, "Unknown molecular footprint")
        elif len(footprint) != 1 or sum(footprint.values()) != 1:
            yield issue("unsupported", "species", sid, f"No verified multidentate or empty native site token for footprint {footprint}")
        if species.get("interface_id"):
            yield issue("unverified", "species", sid, f"Interface-bound resident on {species['interface_id']} has no verified native identity")


def domain_issues(sites, species, definitions):
    issues = [i for s in species for i in species_issues(s)]
    site_owners = {s["surface_id"] for s in sites}
    if len(sites) > 2:
        issues.append(issue("unverified", "inventories", sorted(s["site_id"] for s in sites), "Closed multiphase benchmark has two independent inventories"))
    for site in sites:
        sid = site["site_id"]
        if site.get("interface_id"):
            issues.append(issue("unverified", "site", sid, "Native site token lacks verified contact-private semantics"))
    if len(site_owners) > 2:
        issues.append(issue("unverified", "surfaces", sorted(site_owners), "More than two inventory-bearing surfaces"))
    contacts = {r["interface_id"] for r in definitions if r.get("interface_id")}
    if len(contacts) > 1:
        issues.append(issue("unverified", "interfaces", sorted(contacts), "No verified native distinction between multiple contacts"))
    return issues


def check_configuration(configuration):
    allowed = {"dataset_version", "partial_pressure_bar", "temperature_K", "total_pressure_bar", "catkinas",
               "overall_stoichiometry", "turnover_basis", "selectivity_products", "zacros"}
    extra = configuration.keys() - allowed
    if extra:
        raise ValueError(f"Unmapped point configuration fields: {sorted(extra)}")
    extra = configuration["catkinas"].keys() - {"aliases", "initial_coverages", "MaxTime", "MaxOdeTime"}
    if extra:
        raise ValueError(f"Unmapped CATKINAS solver settings: {sorted(extra)}")
    if configuration.get("turnover_basis") not in (None, "one_event_per_reference_site"):
        raise ValueError("Turnover observable is outside the verified native reference-pair scope")


def check_table_scope(dataset, table):
    """Protect input-only assembly too. A matching isolated equation remains a syntax diagnostic."""
    issues = domain_issues(table["sites"], table["species"], dataset["reactions"])
    if issues:
        raise MappingBlocked(issues)
    if len(table["sites"]) > 1:
        species = {row["species_id"]: row for row in table["species"]}
        for row in table["rows"]:
            if not options(row["directions"]["forward"], species):
                raise MappingBlocked([issue("unverified", "reaction", row["reaction_id"], "No verified dual-inventory native equation form")])


def topology(network):
    """Inspect a snapshot without rates. Return located blockers and observed per-step forms."""
    check_network_version(network)
    if network.get("format") != "reaction-network/1":
        raise ValueError("Expected a versioned reaction-network/1 snapshot")
    definitions = [s["definition"] for s in network["reactions"]]
    index = catalog(dict(network["catalog"], species=network["species"], reactions=definitions))
    register_species(index)
    if network["project_id"] not in index["projects"]:
        raise ValueError("Snapshot project differs from the catalyst catalog")
    issues = domain_issues(network["catalog"]["sites"], network["species"], definitions)
    matches, forms = [], {}
    for step in network["reactions"]:
        r = step["definition"]
        rid = r["reaction_id"]
        try:
            gaps, balance = structural_gaps(r, index)
            if directions(r) != step["direction"]:
                raise ValueError("Snapshot direction differs from molecular or vacancy stoichiometry")
            if r["reaction_type"] == "interphase_transfer":
                assess_transfer(r, index)
        except (ValueError, KeyError, TypeError) as exc:
            issues.append(issue("invalid", "reaction", rid, str(exc)))
            continue
        issues.extend(issue("missing_evidence", "reaction", rid, g) for g in gaps)
        if balance is not None and balance != r.get("required_sites"):
            issues.append(issue("unverified", "reaction", rid, "Required ensemble differs from sites in the native equation"))
        if r.get("reversible") is not True:
            status = "unsupported" if r.get("reversible") is False else "missing_evidence"
            issues.append(issue(status, "reaction", rid, "Explicit forward-only direction" if r.get("reversible") is False else "Reversibility unknown"))
        if len(r.get("phase_ids") or []) > 2:
            issues.append(issue("unverified", "reaction", rid, f"Three-or-more-phase contact {r.get('interface_id')}"))
        if r.get("operating_conditions_ref"):
            issues.append(issue("unverified", "reaction", rid, "Separate operating-condition profile has no verified native point binding"))
        candidates = options(r, index["species"])
        forms[rid] = sorted({name for name, _ in candidates})
        matches.append(candidates)
        if not candidates:
            issues.append(issue("unverified", "reaction", rid, "No matching reversible native equation in the accepted cycle"))
    if not matches_cycle(matches, index):
        issues.append(issue("unverified", "network", network["network_version"],
                            "No verified closed turnover with these connected molecular and vacancy roles"))
    return issues, forms
