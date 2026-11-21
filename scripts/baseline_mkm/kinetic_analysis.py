"""Interpret fractional site activities and per-reference-event fluxes from an accepted point."""

from math import prod

from scripts.baseline_mkm.molecular_coverage import molecular_analysis
from scripts.baseline_mkm.single_point_result import check_close, check_steady_state, normalize_overall
from scripts.kinetic_data.stoichiometric_sources import build_matrices, project_progress
from scripts.scientific_validation import finite_number


def indexed(rows, key):
    items = {row[key]: row for row in rows}
    if len(items) != len(rows):
        raise ValueError(f"Duplicate {key}")
    return items


def fraction(value):
    number = finite_number(value, "fraction", nonnegative=True)
    if number > 1:
        raise ValueError("Fraction exceeds one")
    return number


def activity_factors(side, gas_orders, observed, vacancies):
    surface_orders = {s: n for s, n in side["reactants"].items() if observed[s]["phase"] == "surface"}
    adsorbate_factor = 1
    for sid, order in surface_orders.items():
        row = observed[sid]
        if len(row["site_occupancy"] or {}) != 1 or "molecular_reference" in row:
            activity = finite_number(row.get("surface_activity"), f"{sid} surface_activity", nonnegative=True)
        else:
            activity = row["coverage"]
        adsorbate_factor *= activity**order
    return dict(
        gas_orders=gas_orders,
        surface_orders=surface_orders,
        vacant_site_orders=side["sites_consumed"],
        gas_pressure_factor=prod(observed[s]["pressure_bar"] ** n for s, n in gas_orders.items()),
        adsorbate_factor=adsorbate_factor,
        vacancy_factor=prod(vacancies[s]["vacancy_fraction"] ** n for s, n in side["sites_consumed"].items()),
    )


def rate_analysis(network, dataset, result):
    species = indexed(network["species"], "species_id")
    records = indexed(result["reactions"], "reaction_id")
    models = indexed(dataset["reactions"], "reaction_id")
    definitions = {e["definition"]["reaction_id"]: e for e in network["reactions"]}
    if records.keys() != models.keys() or records.keys() != definitions.keys() or not records:
        raise ValueError("Incomplete reaction inventory")
    observed = indexed(result["species"], "species_id")
    vacancies = indexed(result["sites"], "site_id")
    rows = []
    gases = {s for s, v in species.items() if v["phase"] == "gas"}
    forward_rows = []
    net_rates = {}
    for rid, entry in definitions.items():
        r, m = records[rid], models[rid]
        f = entry["direction"]["forward"]
        reverse = entry["definition"]["reversible"]
        fw = finite_number(r["forward_flux"], "forward_flux", nonnegative=True)
        finite_number(r["kf"], "kf", nonnegative=True)
        rr = r["reverse_flux"]
        net = finite_number(r["net_flux"], "net flux")
        if reverse is True:
            finite_number(r["kr"], "kr", nonnegative=True)
            finite_number(rr, "reverse flux", nonnegative=True)
            check_close(net, fw - rr, "net flux", absolute=1e-10 * (fw + rr))
        elif reverse is False:
            if r["kr"] is not None or rr is not None:
                raise ValueError("Forward-only reaction has reverse measurements")
            check_close(net, fw, "forward-only net flux")
        else:
            raise ValueError("Unknown reversibility precludes validated kinetic attribution")
        forward = dict(f, reaction_id=rid)
        forward_rows.append(forward)
        net_rates[rid] = net
        contribution, _ = project_progress(build_matrices([forward]), {rid: net})
        factors = {}
        for direction in ("forward", "reverse"):
            side = entry["direction"][direction]
            factors[direction] = None
            if side is not None:
                terms = activity_factors(side, m["rates"][direction]["gas_orders"], observed, vacancies)
                coefficient = r["kf" if direction == "forward" else "kr"]
                check_close(
                    r[direction + "_flux"],
                    coefficient
                    * terms["gas_pressure_factor"]
                    * terms["adsorbate_factor"]
                    * terms["vacancy_factor"],
                    "directional mass action",
                )
                factors[direction] = terms
        g = m["energies"]["gibbs_ev"]
        ratio = abs(net) / (fw + rr) if rr is not None and fw + rr else None
        rows.append(
            dict(
                r,
                reversible=reverse,
                activity_factors=factors,
                reaction_free_energy_eV=g["reaction"],
                forward_activation_free_energy_eV=g["forward"] + m["coverage_shift_ev"],
                reverse_activation_free_energy_eV=g["reverse"] + m["coverage_shift_ev"]
                if reverse and g["reverse"] is not None
                else None,
                gas_contribution={s: v for s, v in contribution.items() if s in gases},
                flux_unit=result["flux_unit"],
                fractional_directional_imbalance=ratio,
                near_equilibrium=ratio <= 0.05 if ratio is not None else None,
            )
        )
    if set(result["gas_net_production"]) != gases:
        raise ValueError("Incomplete gas inventory")
    projected, _ = project_progress(build_matrices(forward_rows), net_rates)
    sources = dict.fromkeys(species, 0.0) | projected
    residual, tolerance = check_steady_state(sources, rows, result["gas_net_production"], species)
    gas = {s: sources[s] for s in sorted(gases)}
    ranking = {}
    for name in ("forward_flux", "reverse_flux", "net_flux"):
        values = {r["reaction_id"]: abs(r[name]) for r in rows if r[name] is not None}
        ranking[name] = sorted(values, key=lambda rid: (-values[rid], rid))
    extremes = {}
    for field, order in ranking.items():
        values = {r["reaction_id"]: abs(r[field]) for r in rows if r[field] is not None}
        extremes[field] = {
            "highest": [rid for rid in order if values[rid] == values[order[0]]],
            "lowest": [rid for rid in order if values[rid] == values[order[-1]]],
        }
    return dict(
        reactions=rows,
        descending_absolute_flux=ranking,
        relative_activity_extremes=extremes,
        near_equilibrium_definition="absolute net / gross directional flux <= 0.05; inactive undefined",
        steady_state_residual=residual,
        gas_net_production=gas,
        tolerance=tolerance,
    )


def coverage_analysis(network, result, options, rates=None):
    inventory = indexed(network["catalog"]["sites"], "site_id")
    surfaces = indexed(network["catalog"]["surfaces"], "surface_id")
    species = indexed(network["species"], "species_id")
    observed = indexed(result["species"], "species_id")
    measured = indexed(result["sites"], "site_id")
    counts = options.get("sites_per_reference")
    densities = options.get("site_density_mol_per_surface_m2", {})
    if (counts is not None and counts.keys() != inventory.keys()) or densities.keys() - inventory.keys():
        raise ValueError("Normalization site inventory differs")
    if rates is not None and (measured.keys() != inventory.keys() or observed.keys() != species.keys()):
        raise ValueError("Incomplete site or species inventory")
    if rates is None or "sites_per_molecular_reference" in result or "inventory_reference" in result or any(
        row.get("physical_site_ids") is not None for row in measured.values()
    ) or any(
        len(s["site_occupancy"] or {}) != 1 or "molecular_reference" in observed.get(sid, {})
        for sid, s in species.items() if s["phase"] == "surface"
    ):
        molecules, sites = molecular_analysis(network, result, observed, measured, inventory, surfaces)
        phases = {}
        for site, item in sites.items():
            if item["phase_id"] is not None:
                phases.setdefault(item["phase_id"], []).append(dict(
                    site_id=site, occupied_fraction=item["occupied_fraction"],
                    vacancy_fraction=item["vacancy_fraction"],
                ))
        return dict(
            format="mkm-molecular-coverage/1", species=molecules, sites=sites,
            phase_comparison={phase: phase_utilization(items, counts) for phase, items in phases.items()},
        )
    rows, sites, phase_report = [], {}, {}
    for site, desc in inventory.items():
        native = measured[site]
        vacant = fraction(native["vacancy_fraction"])
        surface = desc["surface_id"]
        phase = surfaces[surface]["phase_id"]
        members = []
        for sid, s in species.items():
            footprint = s["site_occupancy"]
            if site not in footprint:
                continue
            if observed[sid]["site_occupancy"] != footprint or s["phase"] != "surface":
                raise ValueError("Inconsistent site assignment")
            theta = fraction(observed[sid]["coverage"])
            occupied = fraction(theta * footprint[site])
            row = dict(
                species_id=sid,
                phase_id=phase,
                surface_id=surface,
                site_id=site,
                site_type=desc["site_type"],
                occupancy_multiplicity=footprint[site],
                species_coverage=theta,
                occupied_fraction=occupied,
                fraction_of_all_sites=occupied * counts[site] / sum(counts.values()) if counts else None,
                concentration_mol_per_surface_m2=theta * densities[site] if site in densities else None,
                vacancy_fraction=vacant,
                validation="balanced",
            )
            members.append(row)
        members.sort(key=lambda x: (-x["occupied_fraction"], x["species_id"]))
        rows.extend(members)
        occupied = sum(x["occupied_fraction"] for x in members)
        check_close(occupied, native["occupied_fraction"], "occupied site inventory", absolute=1e-8)
        check_close(occupied + vacant, 1, "vacancy balance", absolute=1e-8)
        phase_report.setdefault(phase, []).append(
            dict(site_id=site, occupied_fraction=occupied, vacancy_fraction=vacant)
        )
        ids = [x["species_id"] for x in members]
        sites[site] = dict(
            phase_id=phase,
            surface_id=surface,
            site_type=desc["site_type"],
            occupied_fraction=occupied,
            vacancy_fraction=vacant,
            balance_residual=occupied + vacant - 1,
            coverage_ranking=ids,
            dominant_adsorbates=[
                x["species_id"]
                for x in members
                if occupied and x["occupied_fraction"] == members[0]["occupied_fraction"]
            ],
            competitors=ids,
            activity=[],
            blocking_evidence="fraction unavailable to a vacant-site requirement",
        )
    for entry, r in zip(network["reactions"], rates["reactions"], strict=True):
        required = entry["definition"]["required_sites"]
        for site, multiplicity in required.items():
            factors = r["activity_factors"]
            f = factors["forward"]["vacant_site_orders"].get(site, 0)
            reverse = factors["reverse"]
            sites[site]["activity"].append(
                dict(
                    reaction_id=r["reaction_id"],
                    required_sites=multiplicity,
                    forward_flux=r["forward_flux"],
                    reverse_flux=r["reverse_flux"],
                    net_flux=r["net_flux"],
                    forward_vacancy_factor=sites[site]["vacancy_fraction"] ** f,
                    forward_fraction_blocked_by_vacancy_requirement=1 - sites[site]["vacancy_fraction"] ** f,
                    reverse_vacancy_factor=sites[site]["vacancy_fraction"]
                    ** reverse["vacant_site_orders"].get(site, 0)
                    if reverse
                    else None,
                )
            )
    return dict(
        species=rows,
        sites=sites,
        phase_comparison={phase: phase_utilization(items, counts) for phase, items in phase_report.items()},
    )


def phase_utilization(items, counts):
    if len(items) == 1:
        average = items[0]["occupied_fraction"]
    elif counts and all(item["occupied_fraction"] is not None for item in items):
        total = sum(counts[item["site_id"]] for item in items)
        average = sum(counts[item["site_id"]] * item["occupied_fraction"] for item in items) / total
    else:
        average = None
    return dict(
        inventories=items, occupied_fraction=average, vacancy_fraction=None if average is None else 1 - average
    )


def product_analysis(config, gas, species, tolerance, options):
    overall, extent, legacy_tof, molar = normalize_overall(config, gas, species, tolerance)
    products = config.get("selectivity_products") or []
    production = {s: max(v, 0) for s, v in gas.items()}
    consumption = {s: max(-v, 0) for s, v in gas.items()}
    atom_totals = {}
    elements = sorted(set().union(*(species[s]["composition"] for s in gas)))
    for atom in elements:
        out = sum(species[s]["composition"].get(atom, 0) * v for s, v in production.items())
        used = sum(species[s]["composition"].get(atom, 0) * v for s, v in consumption.items())
        check_close(out, used, "gas element " + atom, absolute=tolerance)
        atom_totals[atom] = dict(produced=out, consumed=used, residual=out - used)
    selectivity = {}
    for atom in sorted(set(elements) | {"C"}):
        carbon = {s: production[s] * species[s]["composition"].get(atom, 0) for s in products}
        total = sum(carbon.values())
        selectivity[atom] = {s: v / total for s, v in carbon.items()} if overall and total else None
    inlet = options.get("feed_inlet_per_reference_s", {})
    if inlet.keys() - gas.keys():
        raise ValueError("Unknown inlet species")
    outlet = {s: v + gas[s] for s, v in inlet.items()}
    if any(v < -tolerance for v in outlet.values()):
        raise ValueError("Net consumption exceeds declared inlet")
    target = options.get("target_products")
    if target is not None and (not target or set(target) - set(products)):
        raise ValueError("Target products must belong to declared product set")
    distribution = dict(
        molar=molar if overall else None,
        element_selectivity=selectivity,
        element_balance=atom_totals,
        product_set=products,
        production=production,
        consumption=consumption,
        byproduct_production={s: production[s] for s in products if s not in target} if target else None,
        unlisted_production={s: v for s, v in production.items() if s not in products and v > tolerance},
        unconverted_feed_outlet_per_reference_s=outlet or None,
    )
    turns = [(None, extent), *((s, production[s]) for s in products)]
    factors = physical_factors(options)
    basis = options.get("reference_basis", "model_reference" if legacy_tof is not None else None)
    counts = options.get("sites_per_reference")
    if basis == "reference_site_pair" and (not counts or sum(counts.values()) != 2):
        raise ValueError("Reference site pair requires evidence for exactly two sites")
    conversions = {}
    for name, value in turns:
        conversions[name] = dict(
            per_reference_s=value,
            per_site_pair_s=value if basis == "reference_site_pair" else None,
            per_site_s=value / sum(counts.values())
            if counts and value is not None
            else value
            if basis == "reference_site"
            else None,
            **{unit: value * f if value is not None and f is not None else None for unit, f in factors.items()},
        )
    return dict(
        overall_stoichiometry=overall,
        extent_per_reference_s=extent,
        reference_basis=basis,
        overall=conversions.pop(None),
        products=conversions,
    ), distribution


def physical_factors(options):
    area = options.get("reference_mol_per_catalyst_m2")
    mass = options.get("reference_mol_per_kg")
    volume = options.get("reference_mol_per_reactor_m3")
    if area is not None and "catalyst_m2_per_kg" in options:
        derived = area * options["catalyst_m2_per_kg"]
        if mass is not None:
            check_close(mass, derived, "mass normalization", absolute=0)
        mass = derived
    if mass is not None and "catalyst_kg_per_reactor_m3" in options:
        derived = mass * options["catalyst_kg_per_reactor_m3"]
        if volume is not None:
            check_close(volume, derived, "volume normalization", absolute=0)
        volume = derived
    return {"mol_per_m2_s": area, "mol_per_kg_s": mass, "mol_per_m3_reactor_s": volume}
