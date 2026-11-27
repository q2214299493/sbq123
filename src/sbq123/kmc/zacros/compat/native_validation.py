"""Read back the native text without evaluating MATLAB commands or running a solver."""
import math
import re
from collections import Counter

from scripts.physical_constants import H_J_S, KB, KB_J_K


def cat_side(text):
    terms = Counter()
    for term in text.split("+"):
        m = re.fullmatch(r"\s*(\d*)([A-Za-z#][A-Za-z_0-9#]*)\s*", term)
        if not m:
            raise ValueError("Invalid CATKINAS stoichiometry")
        terms[m[2]] += int(m[1] or 1)
    return terms


def check_initial_coverages(settings, details, coverages):
    vacancies = {str(i) if len(details["site_indices"]) > 1 else "": 1.0 for i in details["site_indices"].values()}
    expected = {}
    for sid, value in coverages.items():
        alias, site = details["species_tokens"][sid].rsplit("#", 1)
        expected[f"Q{site}_{alias}_INIT"] = value
        vacancies[site] -= value
    expected.update({f"Q{site}_v_INIT": value for site, value in vacancies.items()})
    parsed = {key: v for key, v in settings.items() if key.startswith("Q") and key.endswith("_INIT")}
    if parsed.keys() != expected.keys() or any(not math.isclose(parsed[k], v, abs_tol=1e-15, rel_tol=0)
                                               for k, v in expected.items()):
        raise ValueError("Native initial coverage or independent vacancy fraction differs")


def cat_readback(files, table, details, *, initial_coverages=None):
    rx, settings = [], {}
    for line in files["INPUT_phase25.m"].splitlines():
        if line.startswith("("):
            m = re.fullmatch(r"\((\d+)\): (.+) <-> (.+) \[([^ ]+) ([^ ]+)\]", line)
            if not m or int(m[1]) != len(rx)+1:
                raise ValueError("Invalid CATKINAS equation/index")
            rx.append((cat_side(m[2]), cat_side(m[3]), float(m[4]), float(m[5])))
        else:
            m = re.fullmatch(r"(\w+) = ([-+.eE0-9]+);", line)
            if not m or m[1] in settings:
                raise ValueError("Invalid CATKINAS setting")
            settings[m[1]] = float(m[2])
    if [settings[k] for k in ("ThermoMode", "BarrierMode", "ConsMode")] != [0, -2, 0]:
        raise ValueError("Native correction switches would alter point coefficients")
    if initial_coverages is not None:
        check_initial_coverages(settings, details, initial_coverages)
    idx = details["site_indices"]
    if any(settings.get(f"P_{details['species_tokens'][s]}_FROZ") != v for s, v in details["partial_pressure_bar"].items()):
        raise ValueError("Parsed frozen partial pressure differs")
    for (left, right, ea, dg), row in zip(rx, table["rows"], strict=True):
        for side, key, vacancies in ((left, "reactants", "sites_consumed"), (right, "products", "sites_released")):
            f = row["directions"]["forward"]
            expected = {details["species_tokens"][s]: n for s, n in f[key].items()}
            expected.update({("#"+str(idx[s]) if len(idx)>1 else "#"): n for s, n in f[vacancies].items()})
            if side != expected:
                raise ValueError("Parsed CATKINAS species or vacancy order differs")
        for name, barrier in (("forward", ea), ("reverse", ea-dg)):
            t = settings["T"]
            if t != row["T_K"] or not math.isclose(KB_J_K*t/H_J_S*math.exp(-barrier/(KB*t)), row[name]["coefficient"], rel_tol=1e-10):
                raise ValueError("Parsed CATKINAS rate differs")
    return {"equation_count": len(rx), "correction_switches": [0, -2, 0], "coefficients_round_trip": True}


def block_value(lines, key):
    found = [line.split()[1:] for line in lines if line.split()[:1] == [key]]
    if len(found) != 1:
        raise ValueError(f"Ambiguous or missing Zacros field {key}")
    return found[0]


def check_zac_gas(block, event, names, gas_ids):
    fields = [line.split()[1:] for line in block if line.startswith("gas_reacs_prods ")]
    f = event["reaction"]
    expected = {names[s]: n for s in gas_ids if (n := f["products"].get(s, 0)-f["reactants"].get(s, 0))}
    terms = fields[0] if fields else []
    pairs = list(zip(terms[::2], terms[1::2], strict=True))
    if len(fields) > 1 or len(pairs) != len(expected) or {s: int(n) for s, n in pairs} != expected:
        raise ValueError("Parsed gas pressure orders or products differ")


def _check_lattice_types(lat, details):
    labels = block_value(lat, "site_type_names")
    if lat[0] == "lattice explicit":
        walk = details["topology"]
        adjacency = {n["index"]: [] for n in walk["nodes"]}
        for i, j, _ in walk["edges"]:
            adjacency[i].append(j)
            adjacency[j].append(i)
        max_coord = block_value(lat, "max_coord")
        if len(max_coord) != 1 or int(max_coord[0]) != max(map(len, adjacency.values())):
            raise ValueError("Explicit lattice max_coord differs from adjacency")
        rows = lat[lat.index("lattice_structure")+1:lat.index("end_lattice_structure")]
        if int(block_value(lat, "n_sites")[0]) != len(rows):
            raise ValueError("Explicit site count differs")
        for row, node in zip(rows, walk["nodes"], strict=True):
            idx, x, y, alias, degree, *neighbors = row.split()
            i = node["index"]
            if (int(idx) != i or alias != details["site_aliases"][node["inventory_id"]]
                    or [float(x), float(y)] != node["xy_angstrom"]
                    or int(degree) != len(adjacency[i]) or list(map(int, neighbors)) != sorted(adjacency[i])):
                raise ValueError("Explicit lattice topology differs")
        used = set(details["site_aliases"].values())
    else:
        used = set(block_value(lat, "site_types"))
    if len(labels) != int(block_value(lat, "n_site_types")[0]) or used != set(labels):
        raise ValueError("Native lattice type count differs")


def zac_readback(files, table, details):
    sim = files["simulation_input.dat"].splitlines()
    lat = files["lattice_input.dat"].splitlines()
    mech = files["mechanism_input.dat"].splitlines()
    _check_lattice_types(lat, details)
    start = [i for i, line in enumerate(mech) if line.startswith("step ")]
    end = [i for i, line in enumerate(mech) if line == "end_step"]
    names = details["species_names"]
    gas = sorted(details["gas_indices"], key=details["gas_indices"].get)
    if gas and (block_value(sim, "gas_specs_names") != [names[s] for s in gas]
                or list(map(float, block_value(sim, "gas_molar_fracs"))) != [
                    details["partial_pressure_bar"][s]/table["events"][0]["pressure_bar"] for s in gas]):
        raise ValueError("Native gas mixture differs")
    for a, b, e in zip(start, end, table["events"], strict=True):
        block = mech[a:b]
        count = int(block_value(block, "sites")[0])
        types = block_value(block, "site_types")
        if count != len(e["site_ids"]) or types != [details["site_aliases"][s] for s in e["site_ids"]]:
            raise ValueError("Invalid native event size or type")
        if e["neighbors_zero_based"] and block_value(block, "neighboring") != [f"{i+1}-{j+1}" for i, j in e["neighbors_zero_based"]]:
            raise ValueError("Parsed event connectivity differs")
        check_zac_gas(block, e, names, gas)
        for side in ("initial", "final"):
            index = block.index(side)+1
            assignments = {}
            for i, slot in enumerate(e[side]):
                entity, label, leg = block[index+i].split()
                expected_name = names[slot[0]] if slot else "*"
                members = assignments.setdefault(int(entity), [])
                if label != expected_name or int(leg) != len(members)+1:
                    raise ValueError("Native event species/dentate mismatch")
                members.append(i)
            groups = {}
            for j, slot in enumerate(e[side]):
                groups.setdefault(tuple(slot) if slot else (None, j), []).append(j)
            if sorted(assignments.values()) != sorted(groups.values()):
                raise ValueError("Native molecular entity grouping differs")
        if float(block_value(block, "pre_expon")[0]) != e["pre_expon"] or float(block_value(block, "activ_eng")[0]) != e["activ_eng_eV"]:
            raise ValueError("Native Zacros event coefficient differs")
        if float(block_value(sim, "temperature")[0]) != e["T_K"] or float(block_value(sim, "pressure")[0]) != e["pressure_bar"]:
            raise ValueError("Native Zacros conditions differ")
    return {"step_count": len(start), "species_and_dentates_round_trip": True, "coefficients_round_trip": True}
