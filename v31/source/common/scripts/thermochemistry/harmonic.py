"""Per-state energies in eV, entropy in eV/K, signed wavenumbers in cm^-1."""
from __future__ import annotations

import math

from scripts.physical_constants import AMU_KG, CM1_EV, EV_J as EV_J, H_J_S, KB, KB_J_K
from scripts.scientific_validation import finite_number, integer_number



def oscillator(quantum, temperature):
    """Thermal increment excludes ZPE. The occupation is also dF/d(quantum) - 1/2."""
    x = quantum / (KB * temperature)
    denominator = -math.expm1(-x)
    occupation = math.exp(-x) / denominator
    increment = quantum * occupation
    entropy = increment / temperature - KB * math.log(denominator)
    return increment, entropy, occupation


def harmonic(frequencies, *, temperature=None, scale=1.0, scaling_reference=None,
             excluded_mode=None, mode_sigma_cm1=None):
    scale = finite_number(scale, "frequency scale", positive=True)
    if scale != 1.0 and not (isinstance(scaling_reference, str) and scaling_reference.strip()):
        raise ValueError("Frequency scaling requires a reference")
    if temperature is not None:
        temperature = finite_number(temperature, "temperature", positive=True)
    if not frequencies:
        raise ValueError("Missing spectrum")
    signed = [finite_number(v, "wavenumber") for v in frequencies]
    imaginary = [i for i, v in enumerate(signed, 1) if v < 0]
    if imaginary != ([] if excluded_mode is None else [excluded_mode]):
        raise ValueError("Imaginary modes disagree with the reviewed reaction coordinate")
    if mode_sigma_cm1 is not None and len(mode_sigma_cm1) != len(signed):
        raise ValueError("Supply one independent standard uncertainty per input mode")
    terms, increments, entropies, z_errors, g_errors, included = [], [], [], [], [], []
    for i, v in enumerate(signed, 1):
        sigma = None if mode_sigma_cm1 is None else finite_number(mode_sigma_cm1[i-1], "mode sigma", nonnegative=True)
        if i == excluded_mode:
            continue
        quantum = finite_number(v * scale * CM1_EV, "included mode quantum", positive=True)
        included.append(i)
        terms.append(quantum / 2)
        if sigma is not None:
            z_errors.append(CM1_EV * scale * sigma / 2)
        if temperature is not None:
            h, s, occupation = oscillator(quantum, temperature)
            increments.append(h)
            entropies.append(s)
            if sigma is not None:
                g_errors.append(CM1_EV * scale * sigma * (0.5 + occupation))
    zpe = math.fsum(terms)
    h = math.fsum(increments) if temperature is not None else None
    s = math.fsum(entropies) if temperature is not None else None
    return {"zpe_ev": zpe, "thermal_enthalpy_ev": h, "entropy_ev_per_k": s,
            "gibbs_correction_ev": None if temperature is None else zpe + h - temperature * s,
            "temperature_k": temperature, "frequencies_cm1": signed, "included_modes_one_based": included,
            "excluded_reaction_coordinate_one_based": excluded_mode, "scale": scale,
            "scaling_reference": scaling_reference,
            "zpe_sigma_ev": math.hypot(*z_errors) if mode_sigma_cm1 is not None else None,
            "gibbs_sigma_ev": math.hypot(*g_errors) if temperature is not None and mode_sigma_cm1 is not None else None}


def add_ideal_gas(correction, model, pressure):
    """Classical ideal gas translation, rigid rotation and ground-state electronic degeneracy."""
    temperature = correction["temperature_k"]
    pressure = finite_number(pressure, "gas pressure (Pa)", positive=True)
    mass = finite_number(model.get("mass_amu"), "gas molecular mass (u)", positive=True) * AMU_KG
    moments = [finite_number(v, "principal moment", positive=True) * AMU_KG * 1e-20
               for v in model.get("moments_amu_angstrom2", [])]
    if len(moments) not in (1, 3):
        raise ValueError("Supply one perpendicular moment for linear gas, or three moments for nonlinear gas")
    symmetry = integer_number(model.get("symmetry_number"), "rotational symmetry number", positive=True)
    degeneracy = integer_number(model.get("electronic_degeneracy"), "electronic degeneracy", positive=True)
    kt = KB_J_K * temperature
    log_q_trans = 1.5 * math.log(2 * math.pi * mass * kt / H_J_S**2) + math.log(kt / pressure)
    rotational_dof = 1 if len(moments) == 1 else 1.5
    factor = 8 * math.pi**2 * kt / H_J_S**2
    if len(moments) == 1:
        log_q_rot = math.log(moments[0] * factor / symmetry)
    else:
        log_q_rot = 0.5 * (math.log(math.pi) + sum(math.log(i * factor) for i in moments)) - math.log(symmetry)
    h = (2.5 + rotational_dof) * KB * temperature
    s = KB * (log_q_trans + 2.5 + log_q_rot + rotational_dof + math.log(degeneracy))
    correction["thermal_enthalpy_ev"] += h
    correction["entropy_ev_per_k"] += s
    correction["gibbs_correction_ev"] += h - temperature * s
    correction["gas_contributions"] = {"enthalpy_ev": h, "entropy_ev_per_k": s, "pressure_pa": pressure}
