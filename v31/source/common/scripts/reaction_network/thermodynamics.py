"""Check reaction energy triples and closed stoichiometric cycles within one convention."""
import math

import numpy as np

from scripts.multiphase_contracts import ENERGY_ATOL_EV
from scripts.scientific_validation import finite_number

NAMES = ("forward", "reverse", "reaction")


def check_closure(values):
    if all(values.get(k) is not None for k in NAMES):
        if abs(values["forward"] - values["reverse"] - values["reaction"]) > ENERGY_ATOL_EV:
            raise ValueError("Forward/reverse barrier closure disagrees with reaction energy")


def triple(entries, reference):
    values = {}
    for name in NAMES:
        term = (entries or {}).get(name)
        values[name] = None
        if term is not None:
            if not reference or term["unit"] != "eV" or term["reference_id"] != reference:
                raise ValueError("Incompatible energy unit or reference")
            if not term.get("source"):
                raise ValueError("Energy value needs a source")
            values[name] = finite_number(term["value"], "energy")
    check_closure(values)
    return values


def match_values(existing, supplied):
    merged = existing.copy()
    for name in NAMES:
        value = supplied.get(name)
        if value is None:
            continue
        number = finite_number(value, name)
        if existing[name] is not None and abs(existing[name] - number) > ENERGY_ATOL_EV:
            raise ValueError(f"Conflicting {name} energy")
        merged[name] = number
    check_closure(merged)
    return merged


def bind_state_energies(reaction, calc):
    ids = reaction.get("state_identities") or dict(IS=reaction.get("initial_structure_id"),
                                                  TS=reaction.get("ts_id"), FS=reaction.get("final_structure_id"))
    reference = reaction.get("electronic_reference_convention") or reaction.get("energy_reference_id")
    energies = {}
    for state in ("IS", "TS", "FS"):
        identity = ids.get(state)
        source = (calc["electronic_sources"].get(state) or {}).get("value")
        if source:
            if not identity or identity != source["structure_identity"] or reference != source["energy_reference"]:
                raise ValueError(f"{state}: incompatible structure or electronic reference")
            energies[state] = finite_number(source["value_ev"], "electronic energy")
        correction = calc["states"].get(state)
        if correction and (not identity or correction["structure_identity"] != identity):
            raise ValueError(f"{state}: thermal structure differs from the reaction")
    return energies


def differences(states):
    return {"reaction": states["FS"] - states["IS"], "forward": states["TS"] - states["IS"],
            "reverse": states["TS"] - states["FS"]}


def thermal_evidence(reaction, calc):
    reference = reaction.get("energy_reference_id")
    electronic = triple(reaction.get("electronic_energies"), reference)
    free = reaction.get("free_energies") or {}
    gibbs = triple(free.get("values"), reference)
    for entries in (reaction.get("electronic_energies") or {}, free.get("values") or {}):
        if any(term and term["source"] not in reaction.get("provenance", []) for term in entries.values()):
            raise ValueError("Energy source absent from reaction provenance")
    temp = free.get("temperature_K")
    standard = free.get("standard_state_id")
    if free:
        finite_number(temp, "temperature", positive=True)
        if not standard:
            raise ValueError("Gibbs data need a standard state")
    basis = free.get("thermal_basis")
    if calc is not None:
        energies = bind_state_energies(reaction, calc)
        if calc.get("electronic_ev") is not None:
            if set(energies) != {"IS", "TS", "FS"}:
                raise ValueError("Electronic differences lack bound state energies")
            match_values(differences(energies), calc["electronic_ev"])
            electronic = match_values(electronic, calc["electronic_ev"])
        if calc.get("reaction") is not None:
            gibbs, temp, standard, actual_basis = bind_gibbs(calc, energies, gibbs, temp, standard)
            if basis and basis != actual_basis:
                raise ValueError("Incompatible reaction thermal basis")
            basis = actual_basis
    return {"electronic_ev": electronic, "gibbs_ev": gibbs, "temperature_k": temp, "standard_state": standard, "thermal_basis": basis}


def bind_gibbs(calc, energies, gibbs, temp, standard):
    if calc["status"] not in ("complete", "scoped_estimate") or calc.get("issues"):
        raise ValueError("Inconsistent combined thermochemistry status")
    conditions = calc["condition_values"]
    t = finite_number(conditions["temperature_k"], "temperature", positive=True)
    s = conditions["standard_state"]
    if not s or (temp is not None and (temp != t or standard != s)):
        raise ValueError("Gibbs temperature or standard state mismatch")
    bases, states, corrections = set(), {}, {}
    for state in ("IS", "TS", "FS"):
        c = calc["states"][state]
        if not c or state not in energies or (c["temperature_k"], c["standard_state"]) != (t, s):
            raise ValueError("Missing or incompatible state correction")
        bases.add(c["thermal_basis"])
        corrections[state] = finite_number(c["gibbs_correction_ev"], "Gibbs correction")
        states[state] = energies[state] + corrections[state]
        if abs(states[state] - finite_number(calc["state_free_energy_ev"][state], "state Gibbs energy")) > ENERGY_ATOL_EV:
            raise ValueError("Inconsistent state Gibbs energy")
    if len(bases) != 1 or not all(bases):
        raise ValueError("Incompatible thermal bases")
    for name, state_values in (("electronic_ev", energies), ("thermal_ev", corrections), ("free_energy_ev", states)):
        declared = calc["reaction"][name]
        if any(declared.get(k) is None for k in NAMES):
            raise ValueError("Combined reaction has an incomplete energy triple")
        match_values(differences(state_values), declared)
    return match_values(gibbs, calc["reaction"]["free_energy_ev"]), t, s, bases.pop()


def check_cycles(reactions):
    groups = {}
    for entry in reactions:
        r, e = entry["definition"], entry["energies"]
        # Use only known stoichiometry including vacancies; unknown sites cannot close a cycle.
        if entry["site_balance"] is None:
            continue
        for key in ("electronic_ev", "gibbs_ev"):
            energy = e[key]["reaction"]
            if energy is None:
                continue
            convention = (key, r["energy_reference_id"], e["temperature_k"] if key == "gibbs_ev" else None,
                          e["standard_state"] if key == "gibbs_ev" else None, e.get("thermal_basis") if key == "gibbs_ev" else None)
            groups.setdefault(convention, []).append((entry["net_stoichiometry"], energy))
    checked = 0
    for group in groups.values():
        names = sorted({n for row, _ in group for n in row})
        matrix = np.array([[row.get(n, 0) for n in names] for row, _ in group], dtype=float)
        values = np.array([e for _, e in group])
        potential, _, rank, _ = np.linalg.lstsq(matrix, values, rcond=None)
        checked += len(group) - rank
        if not math.isclose(float(np.max(np.abs(matrix @ potential - values))), 0, abs_tol=ENERGY_ATOL_EV):
            raise ValueError("Inconsistent thermodynamic cycle within a common energy convention")
    return int(checked)
