"""CATKINAS fixed-temperature INPUT_*.m contract from the installed ReadMe.m."""
import math

from scripts.kinetic_parameters.engine import MOLECULAR_ACTIVITY
from scripts.native_inputs import conditions, integer, token
from scripts.scientific_validation import finite_number
from scripts.thermochemistry.harmonic import H_J_S, KB, KB_J_K


def site_token(site, indices):
    return "#" + (str(indices[site]) if len(indices) > 1 else "")


def coverage_symbol(name):
    alias, *labels = name.split("#")
    return "Q" + "x".join(labels) + "_" + alias


def native_names(species, aliases, indices, *, general=False):
    if set(aliases) != {s["species_id"] for s in species}:
        raise ValueError("CATKINAS species map is incomplete")
    names = {}
    for s in species:
        name = token(aliases[s["species_id"]])
        if s["phase"] == "surface":
            if name == "v":
                raise ValueError("CATKINAS reserves v for a site vacancy")
            footprint = s["site_occupancy"]
            if not footprint or any(type(n) is not int or n < 1 for n in footprint.values()):
                raise ValueError("Invalid molecular footprint")
            if not general and sum(footprint.values()) != 1:
                raise ValueError("Installed CATKINAS syntax lacks a verified multidentate molecule representation")
            labels = [indices[site] for site in sorted(footprint, key=indices.get) for _ in range(footprint[site])]
            name += ("#" if len(indices) == 1 and not general else "".join(f"#{i}" for i in labels))
        names[s["species_id"]] = name
    if len(set(names.values())) != len(names):
        duplicates = {s: n for s, n in names.items() if list(names.values()).count(n) > 1}
        raise ValueError(f"Ambiguous CATKINAS alias within a site or gas phase: {duplicates}")
    return names


def side(stoich, vacant, names, indices, *, numbered=False):
    terms = [(names[s], stoich[s]) for s in sorted(stoich, key=names.get)]
    terms += [(f"#{indices[s]}" if numbered else site_token(s, indices), vacant[s]) for s in sorted(vacant, key=indices.get)]
    return " + ".join((str(n) if n != 1 else "") + name for name, n in terms)


def check_coverage_points(rows, initial):
    """A fixed coverage is valid throughout a run if every reaction conserves it."""
    for row in rows:
        for sid, theta in row["coverage_fractions"].items():
            if initial.get(sid) != theta or any(
                f["reactants"].get(sid, 0) != f["products"].get(sid, 0)
                for f in (r["directions"]["forward"] for r in rows)
            ):
                raise ValueError("Fixed-coverage parameter requires a conserved, matching initial fraction")


def check_general_thermodynamics(rows, dataset):
    """Check standard-state rate ratios and the common energy reference."""
    refs = {r["parameter_set"]["energy_reference_id"] for r in dataset["reactions"]}
    if len(refs) != 1 or not all(refs):
        raise ValueError("General mapping requires a common energy reference")
    for r in rows:
        if not r["reverse"]:
            raise ValueError("General mapping requires reversible equations")
        gas_order = sum(r["forward"]["gas_partial_pressure_orders"].values()) - sum(r["reverse"]["gas_partial_pressure_orders"].values())
        log_ratio = math.log(r["forward"]["coefficient"]) - math.log(r["reverse"]["coefficient"])
        log_ratio += gas_order * math.log(r["standard_states"]["gas_pressure_Pa"] / 100000)
        if abs(log_ratio + r["delta_G_standard_eV"] / (KB * r["T_K"])) > 1e-6:
            raise ValueError("Native coefficients violate standard-state detailed balance")


def render(table, config, dataset, *, general=False):
    rows = table["rows"]
    molecular_activity = rows[0]["standard_states"]["surface_activity_convention"] == MOLECULAR_ACTIVITY
    multidentate = any(sum((s.get("site_occupancy") or {}).values()) > 1 for s in table["species"])
    if (general and multidentate and not molecular_activity) or (molecular_activity and not general):
        raise ValueError("Multidentate mapping requires reviewed molecular activity on equal unit inventories")
    if general:
        check_general_thermodynamics(rows, dataset)
    t = rows[0]["T_K"]
    pressures = conditions(dataset, config, rows[0]["P_bar"])
    indices = {s["site_id"]: i for i, s in enumerate(table["sites"], 1)}
    settings = config["catkinas"]
    if settings.get("ThermoMode", 0) != 0 or config.get("ThermoMode", 0) != 0:
        raise ValueError("ThermoMode requires reviewed species thermochemistry; only fixed-temperature kinetics is qualified")
    names = native_names(table["species"], settings["aliases"], indices, general=general)
    check_coverage_points(rows, settings["initial_coverages"])
    lines, checks = [], {}
    for i, row in enumerate(rows, 1):
        e = row["fixed_T_energy_input"]
        if not e:
            raise ValueError("Installed CATKINAS documents only reversible equations; no exact forward-only encoding")
        ea, g = e["Ea_eV"], e["G0_eV"]
        for key, barrier in (("forward", ea), ("reverse", ea-g)):
            actual = KB_J_K*t/H_J_S * math.exp(-barrier/(KB*t))
            if not math.isclose(actual, row[key]["coefficient"], rel_tol=1e-10):
                raise ValueError("Fixed-temperature native coefficient mismatch")
        f = row["directions"]["forward"]
        lhs = side(f["reactants"], f["sites_consumed"], names, indices, numbered=general)
        rhs = side(f["products"], f["sites_released"], names, indices, numbered=general)
        lines.append(f"({i}): {lhs} <-> {rhs} [{ea:.17g} {g:.17g}]")
        checks[row["reaction_id"]] = i
    lines += [f"T = {t:.17g};", "CalMode = 0;", "CalcDRC = 0;", "Istart = 0;", "npar = 0;",
              "ThermoMode = 0;", "BarrierMode = -2;", "ConsMode = 0;", "TimeMode = 0;", "PlotMode = 0;", "PlotType = 0;"]
    for field in ("MaxTime", "MaxOdeTime"):
        lines.append(f"{field} = {integer(settings[field], field)};")
    for sid in sorted(pressures):
        lines.append(f"P_{names[sid]}_FROZ = {pressures[sid]:.17g};")
    occ = settings["initial_coverages"]
    surface = {s["species_id"]: s for s in table["species"] if s["phase"] == "surface"}
    if set(occ) != set(surface):
        raise ValueError("Supply each initial surface coverage")
    vacant = dict.fromkeys(indices, 1.0)
    for sid in sorted(occ, key=names.get):
        value = finite_number(occ[sid], "initial coverage", nonnegative=True)
        for site, count in surface[sid]["site_occupancy"].items():
            vacant[site] -= count * value
        lines.append(f"{coverage_symbol(names[sid])}_INIT = {value:.17g};")
    for site, v in vacant.items():
        if v < 0:
            raise ValueError("Initial coverage exceeds site inventory")
        label = str(indices[site]) if general else site_token(site, indices)[1:]
        lines.append(f"Q{label}_v_INIT = {v:.17g};")
    return {"INPUT_phase25.m": "\n".join(lines)+"\n"}, {"species_tokens": names, "site_indices": indices,
            **({"population_basis": "molecules_per_equal_unit_inventory"} if general else {}),
            "reaction_indices": checks, "fixed_temperature_K": t, "partial_pressure_bar": pressures,
            "input_only_checks": "balances, symbols, conditions and both coefficients"}
