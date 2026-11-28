"""Mass action uses fractional surface activities and ideal gas activities p/p0."""
import math

from sbq123.common.validation.scientific_validation import finite_number, integer_number
from sbq123.common.kinetic_model.physical_constants import AMU_KG, H_J_S, KB, KB_J_K


def positive(value, label):
    return finite_number(value, label, positive=True)


def fraction(value, label):
    x = finite_number(value, label, nonnegative=True)
    if x > 1:
        raise ValueError(f"{label} exceeds one")
    return x


def exp_rate(log_value):
    try:
        return positive(math.exp(log_value), "rate outside representable range")
    except OverflowError as exc:
        raise ValueError("Rate outside representable range") from exc


def gas_powers(stoichiometry, species):
    if any(species[s]["phase"] == "liquid" for s in stoichiometry):
        raise ValueError("Liquid concentration rate law needs a separate standard-state contract")
    return {s: n for s, n in stoichiometry.items() if species[s]["phase"] == "gas"}


def pressure_unit(order, pressure):
    return "s^-1" if not order else f"{pressure}^-{order} s^-1"


def normalized_prefactor(value, unit, order, standard_pa):
    a = positive(value, "prefactor")
    if unit == "s^-1":
        return a
    for label, factor in (("Pa", 1), ("bar", 100000)):
        if unit == pressure_unit(order, label):
            return a * (standard_pa / factor) ** order
    raise ValueError("Prefactor unit disagrees with the gas order and activity convention")


def mean_field_rate(row, direction, *, partial_pressures_pa, surface_activities, vacancy_activities):
    """Evaluate one eligible elementary rate at a specified point, per reference site per second."""
    if not row["export_eligible"] or row["rates"].get(direction) is None:
        raise ValueError("No eligible coefficient for this direction")
    rate = row["rates"][direction]
    p = row["parameter_set"]
    for sid, coverage in row["model"].get("coverage_fractions", {}).items():
        if fraction(surface_activities.get(sid), sid) != coverage:
            raise ValueError("Activity differs from the coverage used for the barrier")
    pressures = {s: finite_number(v, "partial pressure", nonnegative=True) for s, v in partial_pressures_pa.items()}
    if sum(pressures.values()) > p["pressure_Pa"] * (1 + 1e-12):
        raise ValueError("Partial pressures exceed the bound total pressure")
    result = rate["activity_coefficient_s^-1"]
    for s, n in rate["activity_orders"]["species"].items():
        if s in rate["gas_orders"]:
            result *= (finite_number(pressures.get(s), s, nonnegative=True) / p["standard_states"]["gas_pressure_Pa"]) ** n
        else:
            result *= fraction(surface_activities.get(s), s) ** n
    for site, n in rate["activity_orders"]["vacant_sites"].items():
        result *= fraction(vacancy_activities.get(site), site) ** n
    return finite_number(result, "mean-field rate", nonnegative=True)


def activation_shift(terms, fractions, reference, *, reference_fractions=None):
    """Linear TS displacement. Legacy fixed terms use the zero-coverage intercept."""
    if set(fractions) != {t["species_id"] for t in terms}:
        raise ValueError("Supply the coverage of each declared barrier term")
    if reference_fractions is not None and reference_fractions.keys() != fractions.keys():
        raise ValueError("Reference coverage must name the same species")
    total = 0.0
    for term in terms:
        s = term["species_id"]
        theta = fraction(fractions[s], s)
        if not term["min_fraction"] <= theta <= term["max_fraction"]:
            raise ValueError("Coverage outside parameter validity range")
        c = term["coefficient"]
        if (term["expression"] != "linear_transition_state_shift" or c["unit"] != "eV"
                or c["reference_id"] != reference):
            raise ValueError("Unsupported coverage expression, unit or reference")
        origin = 0.0
        if reference_fractions is not None:
            origin = fraction(reference_fractions[s], s)
            if not term["min_fraction"] <= origin <= term["max_fraction"]:
                raise ValueError("Reference coverage outside parameter validity range")
        if not term["already_in_barrier"]:
            total += finite_number(c["value"], "coverage coefficient") * (theta - origin)
    return total


def log_uncertainty(uncertainty, temperature):
    if uncertainty is None:
        return None
    if uncertainty.get("quantity") != "activation_free_energy" or uncertainty.get("unit") != "eV":
        raise ValueError("Expected an activation free-energy standard uncertainty in eV")
    if uncertainty.get("method") != "one_sigma":
        raise ValueError("Unknown uncertainty convention")
    return finite_number(uncertainty["value"], "barrier sigma", nonnegative=True) / (KB * temperature)


def collision_prefactor(law, temperature, p0, gas, order, products):
    if order != 1 or len(gas) != 1 or law.get("gas_species_id") not in gas or products:
        raise ValueError("Collision adsorption requires one identified incoming gas molecule and surface products")
    sticking = fraction(law.get("sticking"), "sticking coefficient")
    mass = positive(law.get("mass_u"), "molecular mass") * AMU_KG
    area = positive(law.get("capture_area_m2"), "capture area per event")
    return positive(sticking, "sticking for an active event") * area * p0 / math.sqrt(2 * math.pi * mass * KB_J_K * temperature)


def coefficient(law, source_rate, *, gas, product_gas, temperature, standard_pa, barrier, degeneracy, sigma):
    """Coefficient at unit activities. Do not fold actual gas pressure into it."""
    method = law["method"]
    n = integer_number(degeneracy, "degeneracy", positive=True)
    if method == "tst":
        if gas:
            raise ValueError("Gas capture requires an adsorption rate law")
        kappa = positive(law.get("kappa"), "transmission coefficient")
        if kappa > 1 and law.get("transmission_model") != "tunneling":
            raise ValueError("Transmission above unity requires an explicit tunneling model")
        a = kappa * KB_J_K * temperature / H_J_S
    elif method in ("gas_adsorption", "dissociative_adsorption"):
        a = collision_prefactor(law, temperature, standard_pa, gas, sum(gas.values()), product_gas)
    elif method == "prefactor":
        if not source_rate:
            raise ValueError("A supplied prefactor requires its Phase 1 rate record")
        a = normalized_prefactor(source_rate["prefactor"], source_rate["prefactor_unit"], sum(gas.values()), standard_pa)
        exponent = finite_number(source_rate["temperature_exponent"], "temperature exponent")
        if exponent:
            a *= (temperature / positive(law.get("reference_temperature_K"), "prefactor reference temperature")) ** exponent
    else:
        raise ValueError(f"Unsupported rate law {method}")
    effective = finite_number(barrier, "activation free energy")
    log_k = math.log(positive(a, "rate prefactor")) + math.log(n) - effective / (KB * temperature)
    rate = exp_rate(log_k)
    return {"method": method, "activity_coefficient_s^-1": rate, "gas_orders": gas, "degeneracy": n,
            "prefactor_at_unit_activity_s^-1": a, "activation_free_energy_ev": effective,
            "sigma_ln_k": log_uncertainty(sigma, temperature)}

MOLECULAR_ACTIVITY = "molecules per reference with one site of each inventory"
