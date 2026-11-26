"""CATKINAS fixed-temperature INPUT_*.m contract from the installed ReadMe.m."""
import math

from scripts.native_inputs import conditions, integer, token
from scripts.scientific_validation import finite_number
from scripts.physical_constants import H_J_S, KB, KB_J_K


def site_token(site, indices):
    return "#" + (str(indices[site]) if len(indices) > 1 else "")


def native_names(species, aliases, indices):
    if set(aliases) != {s["species_id"] for s in species}:
        raise ValueError("CATKINAS species map is incomplete")
    names = {}
    for s in species:
        name = token(aliases[s["species_id"]])
        if s["phase"] == "surface":
            if name == "v":
                raise ValueError("CATKINAS reserves v for a site vacancy")
            footprint = s["site_occupancy"]
            if sum(footprint.values()) != 1:
                raise ValueError("Installed CATKINAS syntax lacks a verified multidentate molecule representation")
            name += site_token(next(iter(footprint)), indices)
        names[s["species_id"]] = name
    if len(set(names.values())) != len(names):
        duplicates = {s: n for s, n in names.items() if list(names.values()).count(n) > 1}
        raise ValueError(f"Ambiguous CATKINAS alias within a site or gas phase: {duplicates}")
    return names


def side(stoich, vacant, names, indices):
    terms = [(names[s], stoich[s]) for s in sorted(stoich, key=names.get)]
    terms += [(site_token(s, indices), vacant[s]) for s in sorted(vacant, key=indices.get)]
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


def render(table, config, dataset):
    rows = table["rows"]
    t = rows[0]["T_K"]
    pressures = conditions(dataset, config, rows[0]["P_bar"])
    indices = {s["site_id"]: i for i, s in enumerate(table["sites"], 1)}
    settings = config["catkinas"]
    if settings.get("ThermoMode", 0) != 0 or config.get("ThermoMode", 0) != 0:
        raise ValueError("ThermoMode requires reviewed species thermochemistry; only fixed-temperature kinetics is qualified")
    names = native_names(table["species"], settings["aliases"], indices)
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
        lhs = side(f["reactants"], f["sites_consumed"], names, indices)
        rhs = side(f["products"], f["sites_released"], names, indices)
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
        site = next(iter(surface[sid]["site_occupancy"]))
        vacant[site] -= value
        label = site_token(site, indices)[1:]
        lines.append(f"Q{label}_{settings['aliases'][sid]}_INIT = {value:.17g};")
    for site, v in vacant.items():
        if v < 0:
            raise ValueError("Initial coverage exceeds site inventory")
        lines.append(f"Q{site_token(site, indices)[1:]}_v_INIT = {v:.17g};")
    return {"INPUT_phase25.m": "\n".join(lines)+"\n"}, {"species_tokens": names, "site_indices": indices,
            "reaction_indices": checks, "fixed_temperature_K": t, "partial_pressure_bar": pressures,
            "input_only_checks": "balances, symbols, conditions and both coefficients"}
