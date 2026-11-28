import math

from sbq123.common.kinetic_model.kinetic_parameters.export_contract import per_bar, source_info, validate_export
from sbq123.common.kinetic_model.physical_constants import H_J_S, KB, KB_J_K


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
