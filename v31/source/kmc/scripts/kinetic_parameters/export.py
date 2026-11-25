"""Condition-specific parameter handoffs for mean-field activities and lattice event occurrences."""
import math
from collections import Counter, defaultdict

from scripts.kinetic_parameters.engine import check_version
from scripts.kinetic_parameters.laws import positive, pressure_unit
from scripts.thermochemistry.harmonic import H_J_S, KB, KB_J_K


def validate_export(dataset, *, fixed_mkm=False):
    check_version(dataset, "dataset_version")
    if "coverage_iteration" in dataset and not fixed_mkm:
        raise ValueError("Expected an unmodified parent or a fixed MKM consumer; no qualified lattice-event export")
    if (dataset.get("format") != "kinetic-dataset/1" or not dataset["export_eligible"] or not dataset["reactions"]
            or any(not r["export_eligible"] or r["missing"] for r in dataset["reactions"])):
        raise ValueError("Kinetic dataset is blocked for export")
    conditions, fractions = set(), {}
    for r in dataset["reactions"]:
        p = r["parameter_set"]
        conditions.add((r["model"].get("use_scope", "project"), p["temperature_K"], p["pressure_Pa"], p["standard_state_id"],
                        p["standard_states"]["gas_pressure_Pa"], p["standard_states"]["surface_activity_convention"]))
        for sid, theta in r["model"].get("coverage_fractions", {}).items():
            if fractions.setdefault(sid, theta) != theta:
                raise ValueError("Conflicting coverage conditions in one export")
    if len(conditions) != 1:
        raise ValueError("A parameter export requires a common temperature, pressure and standard state")


def per_bar(rate, p0, factor=1):
    order = sum(rate["gas_orders"].values())
    k = rate["activity_coefficient_s^-1"] * (100000 / p0) ** order / factor
    return {"coefficient": positive(k, "converted rate"), "unit": pressure_unit(order, "bar"),
            "gas_partial_pressure_orders": rate["gas_orders"]}


def source_info(row):
    model = row["model"]
    source = {"parameter_set_id": row["parameter_set"]["parameter_set_id"], "sources": model["sources"],
            "review_subject": model["scientific_review"]["subject_sha256"], "use_scope": model.get("use_scope", "project")}
    if "coverage_energy" in row:
        source["coverage_energy"] = row["coverage_energy"]
    if "prediction" in row:
        source["energy_prediction"] = row["prediction"]
    return source


def catkinas_energy_pair(forward, reverse, temperature):
    """Apparent Ea/G0 at this T for the numerical 1-bar mass-action coefficients."""
    if reverse is None:
        return None
    log_f = math.log(forward["coefficient"])
    log_r = math.log(reverse["coefficient"])
    return {"Ea_eV": KB * temperature * (math.log(KB_J_K * temperature / H_J_S) - log_f),
            "G0_eV": -KB * temperature * (log_f - log_r),
            "ThermoMode": 0, "BarrierMode": -2, "ConsMode": 0}


def catkinas(dataset):
    validate_export(dataset, fixed_mkm=True)
    rows = []
    for r in dataset["reactions"]:
        p = r["parameter_set"]
        p0 = p["standard_states"]["gas_pressure_Pa"]
        forward = per_bar(r["rates"]["forward"], p0)
        reverse = per_bar(r["rates"]["reverse"], p0) if r["rates"]["reverse"] else None
        rows.append({"reaction_id": r["reaction_id"], "provenance": source_info(r),
                     "T_K": p["temperature_K"], "P_bar": p["pressure_Pa"] / 100000,
                     "forward": forward, "reverse": reverse,
                     "fixed_T_energy_input": catkinas_energy_pair(forward, reverse, p["temperature_K"]),
                     "directions": r["direction"], "standard_states": p["standard_states"],
                     "site_balance": r["site_balance"], "delta_G_standard_eV": r["energies"]["gibbs_ev"]["reaction"],
                     "delta_G_forward_eV": r["energies"]["gibbs_ev"]["forward"] + r["coverage_shift_ev"],
                     "coverage_fractions": r["model"].get("coverage_fractions", {})})
    return {"format": "catkinas-parameter-table/1", "dataset_version": dataset["dataset_version"],
            "normalization": "mean-field per reference site; gas partial pressures in bar",
            "species": dataset["species"], "sites": dataset["catalog"]["sites"], "rows": rows}


def verify_pattern(sites, slots, direction, species, side, vacancy_key):
    if len(slots) != len(sites):
        raise ValueError("Lattice pattern length differs from footprint")
    fragments = defaultdict(Counter)
    vacancies = Counter()
    for site, slot in zip(sites, slots, strict=True):
        if slot is None:
            vacancies[site] += 1
        else:
            sid, entity = slot
            if sid not in direction[side] or type(entity) is not int or entity < 1:
                raise ValueError("Unknown or invalid lattice entity")
            fragments[sid, entity][site] += 1
    observed = Counter()
    if len({entity for _, entity in fragments}) != len(fragments):
        raise ValueError("Distinct lattice molecules share an entity number")
    for (sid, _entity), occupancy in fragments.items():
        if species[sid]["site_occupancy"] != dict(occupancy):
            raise ValueError("Pattern occupancy conflicts with species site inventory")
        observed[sid] += 1
    expected = {s: n for s, n in direction[side].items() if species[s]["phase"] == "surface"}
    if vacancies != Counter(direction[vacancy_key]) or observed != expected:
        raise ValueError("Event pattern disagrees with reaction stoichiometry")


def verify_event(event, r, species):
    if not event:
        raise ValueError("Zacros requires reviewed local site pattern and event normalization")
    sites = event["site_ids"]
    if not sites or Counter(sites) != Counter(r["site_balance"]):
        raise ValueError("Event sites differ from the reaction footprint")
    graph = {i: set() for i in range(len(sites))}
    for i, j in event["neighbors_zero_based"]:
        if type(i) is not int or type(j) is not int or i not in graph or j not in graph or i == j:
            raise ValueError("Invalid event neighbor pair")
        graph[i].add(j)
        graph[j].add(i)
    seen, todo = set(), [0]
    while todo:
        node = todo.pop()
        if node not in seen:
            seen.add(node)
            todo.extend(graph[node] - seen)
    if len(seen) != len(sites):
        raise ValueError("Disconnected local event graph")
    fwd = r["direction"]["forward"]
    verify_pattern(sites, event["initial"], fwd, species, "reactants", "sites_consumed")
    verify_pattern(sites, event["final"], fwd, species, "products", "sites_released")


def zacros(dataset):
    validate_export(dataset)
    if any("energy_prediction" in r["model"] for r in dataset["reactions"]):
        raise ValueError("MKM energy predictions have no qualified lattice-event export")
    species = {s["species_id"]: s for s in dataset["species"]}
    rows = []
    for r in dataset["reactions"]:
        event = r["model"].get("local_event")
        verify_event(event, r, species)
        p = r["parameter_set"]
        for name, rate in r["rates"].items():
            if rate is None:
                continue
            count = positive(event["patterns_per_reference_site"][name], "patterns per reference site")
            initial, final = event["initial"], event["final"]
            if name == "reverse":
                initial, final = final, initial
            converted = per_bar(rate, p["standard_states"]["gas_pressure_Pa"], count)
            rows.append({"reaction_id": r["reaction_id"], "provenance": source_info(r),
                         "direction": name, "rate_kind": "kmc_event_coefficient", "T_K": p["temperature_K"],
                         "pressure_bar": p["pressure_Pa"] / 100000, "site_ids": event["site_ids"],
                         "neighbors_zero_based": event["neighbors_zero_based"], "initial": initial, "final": final,
                         "reaction": r["direction"][name], "pre_expon": converted["coefficient"], "activ_eng_eV": 0.0,
                         "unit": converted["unit"], "gas_partial_pressure_orders": converted["gas_partial_pressure_orders"],
                         "coverage_fractions": r["model"].get("coverage_fractions", {})})
    from scripts.surface_kmc.parameters import qualify_events

    table = {"format": "zacros-event-rate-table/1", "dataset_version": dataset["dataset_version"],
            "normalization": "per matching event at listed conditions; distinct directed steps", "events": rows}
    return qualify_events(dataset, table)
