"""Observable definitions for the read-only MKM point / KMC window comparison."""
import math

from scripts.kinetic_data.native_rate_output import require
from scripts.kinetic_data.scientific_identity import IncompatibleIdentity
from scripts.kinetic_data.stoichiometric_sources import build_matrices
from scripts.kinetic_parameters.rate_normalization import convert_checked_rate
from scripts.scientific_validation import finite_number


FIELDS = {
    "coverage": {"species", "inventory"}, "site_utilization": {"inventory"},
    "molecular_population": {"species"}, "reaction_rate": {"reaction", "direction"},
    "tof": {"overall_stoichiometry"}, "selectivity": {"species", "products"},
}


def _row(rows, key, value):
    return next((row for row in rows if row[key] == value), {})


def _window_counts(record):
    # Use the owner's signed stoichiometric matrix with integer event counts. One
    # residual molecule must remain visible even in a very long window.
    matrix = build_matrices(record["rate_output"]["reaction_rates"]).species
    events = record["window"]["observation"]["pathway_flux"]
    net = {r: counts["forward"] - counts["reverse"] for r, counts in events.items()}
    return {species: sum(n * net[r] for r, n in row.items()) for species, row in matrix.items()}


def measure(q, record, dataset, *, mkm):
    kind = q["kind"]
    require(kind in FIELDS and set(q) == FIELDS[kind] | {"kind"}, "Unsupported observable definition")
    obs, rates = record["observations"], record["rate_output"]
    basis = rates["native_normalization"]
    sid, site = q.get("species"), q.get("inventory")
    if kind in ("coverage", "site_utilization", "molecular_population"):
        if mkm:
            inventory = _row(obs["sites"], "site_id", site) if site else None
            if site:
                require(math.isclose(inventory["occupied_fraction"] + inventory["vacancy_fraction"], 1,
                                     abs_tol=1e-8), "MKM vacancy closure differs")
            if kind == "site_utilization":
                value = inventory["occupied_fraction"]
            else:
                row = _row(obs["species"], "species_id", sid)
                require(row.get("phase") == "surface", "Missing MKM surface molecule")
                if kind == "coverage":
                    value = row["coverage"] * row["site_occupancy"][site] / inventory["inventory"]
                else:
                    counts = record["binding"]["normalization"]["sites_per_reference"]
                    # Legacy coverage represents a count only for a monodentate on a unit inventory.
                    if "molecular_reference" in row:
                        require(obs["sites_per_molecular_reference"][row["molecular_reference"]] == counts,
                                "Molecular and rate reference inventories differ")
                        value = row["molecules_per_reference"]
                    else:
                        require(sum(row["site_occupancy"].values()) == 1 and
                                all(counts.get(i) == 1 for i in row["site_occupancy"]),
                                "Legacy population has no molecular reference mapping")
                        value = row["coverage"]
        elif kind == "molecular_population":
            value = obs["mean_molecules_per_cell"][sid]
        else:
            inventory = obs["time_weighted_site_utilization"][site]
            require(math.isclose(inventory["occupied_fraction"] + inventory["vacancy_fraction"], 1,
                                 abs_tol=1e-8), "KMC vacancy closure differs")
            value = (inventory["occupied_fraction"] if kind == "site_utilization" else
                     obs["time_weighted_occupied_fraction_by_species"][site][sid])
        if kind == "molecular_population":
            return _value(value, "molecules", dict(basis, denominator_value=1))
        require(0 <= value <= 1, "Nonphysical occupied-site fraction")
        return _value(value, "occupied sites / inventory sites", site)
    if kind == "reaction_rate":
        direction = q["direction"]
        require(direction in ("forward", "reverse", "net"), "Unsupported rate direction")
        value = _row(rates["reaction_rates"], "reaction_id", q["reaction"])[direction]
        require(value != "not_applicable", "Requested direction unavailable")
        return _value(value, "events / denominator / s", basis)
    all_sources = ({r["species_id"]: r["net_production_rate"] for r in rates["source_terms"]["species"]}
                   if mkm else _window_counts(record))
    gases = {s["species_id"] for s in dataset["species"] if s["phase"] == "gas"}
    sources = {s: n for s, n in all_sources.items() if s in gases}
    if kind == "selectivity":
        products = q["products"]
        require(isinstance(products, list) and len(set(products)) == len(products) and sid in products
                and set(products) <= sources.keys(), "Incomplete named gas product set")
        require(all(v <= 0 or s in products for s, v in sources.items()), "Competing gas product omitted")
        total = math.fsum(max(0, sources[s]) for s in products)
        require(total > 0, "Zero positive net molar production")
        value = max(0, sources[sid]) / total
        if mkm:
            declared = obs["molar_selectivity"]
            require(declared and set(declared) == set(products) and math.isclose(declared[sid], value),
                    "MKM selectivity product definition differs")
            value = declared[sid]
        return _value(value, "molar fraction", sorted(products))
    overall = q["overall_stoichiometry"]
    require(isinstance(overall, dict) and overall and set(overall) <= sources.keys() and
            all(type(n) is int and n != 0 for n in overall.values()) and min(overall.values()) < 0 < max(overall.values()),
            "Invalid signed overall gas reaction")
    product = min(s for s, n in overall.items() if n > 0)
    extent = sources[product] / overall[product]
    require(extent != 0, "No observed net cycle extent")
    if mkm:
        # The owning reader already replayed gas closure and species-specific steady-state residuals.
        require(obs["total_reaction"] == overall and obs["tof_s_inverse"] is not None and
                math.isclose(obs["tof_s_inverse"], extent / basis["denominator_value"], abs_tol=1e-12),
                "MKM turnover definition differs")
        return _value(obs["tof_s_inverse"], "cycles / denominator / s", dict(basis, denominator_value=1))
    require(all(n * overall[product] == sources[product] * overall.get(s, 0) for s, n in sources.items()),
            "Gas counts do not close the declared overall cycle")
    require(all(n == 0 for s, n in all_sources.items() if s not in gases),
            "Surface accumulation prevents cycle interpretation")
    start, end = record["window"]["definition"]["bounds_s"]
    return _value(extent / (end - start), "cycles / denominator / s", basis)


def _value(value, unit, denominator):
    return dict(value=finite_number(value, "observable"), unit=unit, denominator=denominator)


def difference(query, left, right, mapping, point, window):
    a, b = left["value"], right["value"]
    rule = None
    if query["kind"] in ("reaction_rate", "tof", "molecular_population"):
        require(mapping is not None, "Missing references_per_cell evidence")
        counts = point["normalization"]["sites_per_reference"]
        capacities = window["site_capacities"]
        require(mapping["quantity"] == "references_per_cell" and mapping["unit"] == "1",
                "Unverified references_per_cell quantity or unit")
        kind = {"forward": "forward_flux", "reverse": "reverse_flux"}.get(query.get("direction"), "net_progress")
        if query["kind"] == "molecular_population":
            # Only the count denominator changes. There is no integration over time.
            kind = "species_source"
        converted = convert_checked_rate(b, kind, right["denominator"], left["denominator"], mapping)
        require(converted["status"] == "available", "Unqualified denominator mapping")
        require(counts and capacities, "Missing inventory capacity evidence")
        if counts.keys() != capacities.keys() or any(mapping["value"] * n != capacities[s] for s, n in counts.items()):
            raise IncompatibleIdentity("Reference multiplicity conflicts with physical inventory capacities")
        b = converted["value"]
        rule = dict(evidence=mapping, kmc_in_mkm_basis=b, target_unit=left["unit"])
    else:
        require(left["unit"] == right["unit"] and left["denominator"] == right["denominator"],
                "Observable units or denominators differ")
    delta = finite_number(b - a, "signed difference")
    return dict(signed_kmc_minus_mkm=delta, absolute=abs(delta),
                relative_to_abs_mkm=finite_number(abs(delta) / abs(a), "relative difference") if a else None,
                relative_unavailable_reason=None if a else "zero MKM reference"), rule
