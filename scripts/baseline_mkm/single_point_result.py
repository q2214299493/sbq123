"""Normalize CATKINAS symbols against the reviewed model and independently check one steady state."""

import math
import re

from scripts.baseline_mkm.native import site_token
from scripts.kinetic_parameters.export import catkinas
from scripts.thermochemistry.harmonic import KB


def check_close(actual, expected, label, *, rel=1e-9, absolute=1e-12):
    if not math.isclose(actual, expected, rel_tol=rel, abs_tol=absolute):
        raise ValueError(f"{label}: observed {actual}, expected {expected}")


def species_and_sites(table, mapping, native, config):
    by_id = {s["species_id"]: s for s in table["species"]}
    sites = mapping["site_indices"]
    vacancy = {}
    inventory = {}
    expected_symbols = set()
    for site in sites:
        label = "Q" + site_token(site, sites)[1:] + "_v"
        vacancy[site] = native["coverages"][label]
        expected_symbols.add(label)
        inventory[site] = 0.0
    activities, gas_rates, species_rows = {}, {}, []
    pressure_symbols = set()
    for sid, species in by_id.items():
        name = mapping["species_tokens"][sid]
        footprint = species["site_occupancy"]
        surface = species["phase"] == "surface"
        if surface:
            site = next(iter(footprint))
            symbol = "Q" + site_token(site, sites)[1:] + "_" + name.split("#")[0]
            expected_symbols.add(symbol)
            value = native["coverages"][symbol]
            inventory[site] += value * footprint[site]
        else:
            symbol = "P_" + name
            pressure_symbols.add(symbol)
            value = native["partial_pressures_bar"][symbol]
            check_close(value, config["partial_pressure_bar"][sid], "gas pressure")
            gas_rates[sid] = native["net_gas_flux_per_reference_site_s"][name]
        activities[sid] = value
        species_rows.append(
            dict(
                species_id=sid,
                phase=species["phase"],
                site_occupancy=footprint,
                site_types=[s["site_type"] for s in table["sites"] if s["site_id"] in (footprint or {})],
                coverage=value if surface else None,
                pressure_bar=None if surface else value,
            )
        )
    if (
        expected_symbols != native["coverages"].keys()
        or pressure_symbols != native["partial_pressures_bar"].keys()
    ):
        raise ValueError("Unexpected species symbol inventory")
    site_rows = []
    for site, occupied in inventory.items():
        residual = occupied + vacancy[site] - 1
        check_close(residual, 0, "site inventory", absolute=1e-8)
        site_rows.append(
            dict(
                site_id=site,
                inventory=1,
                occupied_fraction=occupied,
                vacancy_fraction=vacancy[site],
                balance_residual=residual,
            )
        )

    return by_id, sites, vacancy, activities, gas_rates, species_rows, site_rows


def reconstruct(table, mapping, native, temperature, by_id, sites, vacancy, activities):
    source = dict.fromkeys(by_id, 0.0)
    reactions = []
    coefficient_errors = []
    element_keys = set().union(*(s["composition"] for s in by_id.values()))
    for row, obs in zip(table["rows"], native["reactions"], strict=True):
        rid = row["reaction_id"]
        if obs["index"] != mapping["reaction_indices"][rid]:
            raise ValueError("Native reaction index differs")
        forward = row["directions"]["forward"]
        nu = {s: forward["products"].get(s, 0) - forward["reactants"].get(s, 0) for s in by_id}
        for key in element_keys:
            if sum(n * by_id[s]["composition"].get(key, 0) for s, n in nu.items()):
                raise ValueError(f"Element imbalance: {rid} {key}")
        if sum(n * by_id[s]["charge"] for s, n in nu.items() if n):
            raise ValueError(f"Charge imbalance: {rid}")
        for site in sites:
            occupied_change = sum(n * (by_id[s]["site_occupancy"] or {}).get(site, 0) for s, n in nu.items())
            if occupied_change + forward["sites_released"].get(site, 0) != forward["sites_consumed"].get(site, 0):
                raise ValueError(f"Site stoichiometry imbalance: {rid} {site}")
        fluxes = {}
        for direction, k in (("forward", "kf"), ("reverse", "kr")):
            law = row["directions"][direction]
            expected = row[direction]["coefficient"]
            check_close(obs[k], expected, "rate coefficient", rel=1e-4, absolute=0)
            coefficient_errors.append(abs(obs[k] / expected - 1))
            flux = obs[k] * math.prod(activities[s] ** n for s, n in law["reactants"].items())
            flux *= math.prod(vacancy[s] ** n for s, n in law["sites_consumed"].items())
            check_close(obs[direction + "_flux"], flux, f"{rid} {direction} flux")
            fluxes[direction] = flux
        net = fluxes["forward"] - fluxes["reverse"]
        check_close(net, obs["net_flux"], "reconstructed net flux", absolute=1e-10 * max(fluxes.values()))
        for sid, count in nu.items():
            source[sid] += count * net
        for field, key in (("applied_forward_barrier_eV", "Ea_eV"), ("applied_reaction_energy_eV", "G0_eV")):
            check_close(obs[field], row["fixed_T_energy_input"][key], field)
        # Convert pressure-based coefficients back to dimensionless standard-state activities.
        order = sum(row["forward"]["gas_partial_pressure_orders"].values()) - sum(
            row["reverse"]["gas_partial_pressure_orders"].values()
        )
        ln_k = (
            math.log(obs["kf"])
            - math.log(obs["kr"])
            + order * math.log(row["standard_states"]["gas_pressure_Pa"] / 100000)
        )
        check_close(
            ln_k, -row["delta_G_standard_eV"] / (KB * temperature), "detailed balance", rel=0, absolute=1e-4
        )
        reactions.append(
            dict(obs, reaction_id=rid, forward_unit=row["forward"]["unit"], reverse_unit=row["reverse"]["unit"])
        )

    return source, reactions, coefficient_errors


def check_steady_state(source, reactions, gas_rates, by_id):
    element_keys = set().union(*(s["composition"] for s in by_id.values()))
    scale = max(abs(r["net_flux"]) for r in reactions)
    tolerance = max(1e-12, scale * 1e-7)
    residual = max((abs(v) for s, v in source.items() if s not in gas_rates), default=0)
    check_close(residual, 0, "steady-state residual", absolute=tolerance)
    for sid, rate in gas_rates.items():
        check_close(rate, source[sid], "net gas flux", absolute=tolerance)
    for key in element_keys:
        check_close(
            sum(by_id[s]["composition"].get(key, 0) * v for s, v in gas_rates.items()),
            0,
            "gas element balance",
            absolute=tolerance,
        )
    return residual, tolerance


def normalize_overall(config, gas_rates, by_id, tolerance):
    element_keys = set().union(*(s["composition"] for s in by_id.values()))
    overall = config.get("overall_stoichiometry")
    rate = tof = None
    if overall is not None:
        if (
            not overall
            or overall.keys() - gas_rates.keys()
            or any(type(n) is not int or n == 0 for n in overall.values())
        ):
            raise ValueError("Invalid signed gas stoichiometry")
        for key in element_keys:
            if sum(by_id[s]["composition"].get(key, 0) * n for s, n in overall.items()):
                raise ValueError("Overall stoichiometry is not balanced")
        first = next(iter(overall))
        rate = gas_rates[first] / overall[first]
        for s, observed in gas_rates.items():
            check_close(observed, rate * overall.get(s, 0), "overall reaction rate", absolute=tolerance)
        if config.get("turnover_basis") == "one_event_per_reference_site":
            tof = rate
    products = config.get("selectivity_products")
    selectivity = None
    if products is not None:
        if not products or len(set(products)) != len(products) or set(products) - gas_rates.keys():
            raise ValueError("Invalid molar selectivity product set")
        amounts = {s: max(0, gas_rates[s]) for s in products}
        total = sum(amounts.values())
        if total:
            selectivity = {s: v / total for s, v in amounts.items()}
    return overall, rate, tof, selectivity


def validate_result(dataset, config, mapping, native, log, input_text):
    table = catkinas(dataset)
    temperature = mapping["fixed_temperature_K"]
    expected_lines = [line for line in input_text.splitlines() if line.startswith("(")]
    observed_lines = re.findall(r"^\(\d+\):[^\r\n]*\[[^\r\n]*\]\s*$", log, re.MULTILINE)
    if [s.strip() for s in observed_lines] != expected_lines:
        raise ValueError("Native reaction ordering differs from generated input")
    temperatures = re.findall(r"^\s*T\s*=\s*([\d.eE+-]+);", log, re.MULTILINE)
    if not temperatures or any(float(t) != temperature for t in temperatures):
        raise ValueError("Native temperature differs from kinetic dataset")

    by_id, sites, vacancy, activities, gas_rates, species_rows, site_rows = species_and_sites(
        table, mapping, native, config
    )
    source, reactions, coefficient_errors = reconstruct(
        table, mapping, native, temperature, by_id, sites, vacancy, activities
    )
    residual, tolerance = check_steady_state(source, reactions, gas_rates, by_id)
    overall, rate, tof, selectivity = normalize_overall(config, gas_rates, by_id, tolerance)
    return dict(
        format="mkm-single-point-result/1",
        reactions=reactions,
        species=species_rows,
        sites=site_rows,
        total_reaction=overall,
        overall_rate=rate,
        tof_s_inverse=tof,
        turnover_basis=config.get("turnover_basis"),
        gas_net_production=gas_rates,
        molar_selectivity=selectivity,
        numerical_convergence="converged",
        flux_unit="events per reference site per second",
        steady_state_residual=residual,
        validation=dict(
            status="passed",
            max_relative_coefficient_error=max(coefficient_errors),
            steady_state_absolute_tolerance=tolerance,
        ),
    )
