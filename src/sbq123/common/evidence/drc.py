"""Apply a released DRC profile to observations with a matched denominator and branch."""

from sbq123.common.evidence.registry import entry
from sbq123.common.kinetic_model.contracts import number
from sbq123.common.kinetic_model.physical_constants import KB
from math import log


def degree_of_rate_control(profile_id, baseline, raised, lowered, temperature_K, delta_eV):
    policy = entry("drc", profile_id)
    for obs in (baseline, raised, lowered):
        if obs["target"] != policy["target"] or obs["denominator"] != policy["denominator"]:
            raise ValueError("DRC target or denominator differs from profile")
        if obs["branch"] != baseline["branch"] or obs["conditions_sha256"] != baseline["conditions_sha256"]:
            raise ValueError("DRC root or operating conditions changed")
        number(obs["value"], "positive TOF", positive=True)
    t = number(temperature_K, "temperature", positive=True)
    delta = number(delta_eV, "symmetric TS displacement", positive=True)
    return -KB * t * (log(raised["value"]) - log(lowered["value"])) / (2 * delta)
