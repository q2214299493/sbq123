"""Local symmetric TS perturbation at positive TOFs and fixed temperature; the caller qualifies the branch."""
from math import log

from sbq123.common.kinetic_model.physical_constants import KB
from sbq123.common.validation.scientific_validation import finite_number


def central_difference(baseline, plus, minus, temperature_K, delta_eV):
    finite_number(baseline, "positive baseline TOF", positive=True)
    rates = [finite_number(v, "positive perturbed TOF", positive=True) for v in (plus, minus)]
    t = finite_number(temperature_K, "temperature in K", positive=True)
    step = finite_number(delta_eV, "TS increment in eV", positive=True)
    return -KB * t * (log(rates[0]) - log(rates[1])) / (2 * step)
