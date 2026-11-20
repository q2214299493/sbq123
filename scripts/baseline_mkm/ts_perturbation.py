"""Reproduce a single, benchmark-scoped transition-state displacement from its reviewed parent."""

from copy import deepcopy
from math import log

from scripts.artifact_io import sha256_json
from scripts.kinetic_parameters.engine import calculate, check_version, generate
from scripts.kinetic_parameters.export import validate_export
from scripts.scientific_validation import finite_number
from scripts.thermochemistry.harmonic import KB

PARENT = "417cf1dc3236175476441c4c4e7b4bd5771bc4a7062aa5e34eff69070483d11b"
REACTION = "transfer"
DELTA_EV = 0.01


def central_difference(baseline, plus, minus, temperature_K, delta_eV):
    finite_number(baseline, "positive baseline TOF", positive=True)
    rates = [finite_number(v, "positive perturbed TOF", positive=True) for v in (plus, minus)]
    t = finite_number(temperature_K, "temperature in K", positive=True)
    step = finite_number(delta_eV, "TS increment in eV", positive=True)
    return -KB * t * (log(rates[0]) - log(rates[1])) / (2 * step)


def derivative(network, parent, sign):
    check_version(network, "network_version")
    validate_export(parent)
    if (
        type(sign) is not int
        or sign not in (-1, 1)
        or parent["dataset_version"] != PARENT
        or parent["network_version"] != network["network_version"]
    ):
        raise ValueError("Expected the accepted synthetic parent and one signed perturbation")
    child = deepcopy(parent)
    row = next(r for r in child["reactions"] if r["reaction_id"] == REACTION)
    entry = next(r for r in network["reactions"] if r["definition"]["reaction_id"] == REACTION)
    g = row["energies"]["gibbs_ev"]
    param = row["parameter_set"]
    before = g.copy()
    for direction in ("forward", "reverse"):
        g[direction] += sign * DELTA_EV
        param[direction]["activation_energy"]["value"] = g[direction]
    rates, equilibrium, shift = calculate(
        dict(entry, energies=row["energies"]), param, row["model"], {s["species_id"]: s for s in network["species"]}
    )
    for direction, calculated in rates.items():
        row["rates"][direction].update(calculated)
    row.update(equilibrium=equilibrium, coverage_shift_ev=shift)
    child["ts_perturbation"] = dict(
        format="synthetic-ts-displacement/1",
        parent_dataset_sha256=PARENT,
        parent_network_sha256=network["network_version"],
        reaction_id=REACTION,
        sign=sign,
        delta_eV=DELTA_EV,
        temperature_K=param["temperature_K"],
        parent_gibbs_eV=before,
        derived_gibbs_eV=g.copy(),
        parent_parameter_sha256=sha256_json(next(r["parameter_set"] for r in parent["reactions"] if r["reaction_id"] == REACTION)),
        method="Shift absolute TS Gibbs energy at fixed endpoints and prefactors; review and sources refer to parent.",
    )
    del child["dataset_version"]
    return {"dataset_version": sha256_json(child), **child}


def reproduce(network, dataset):
    models = [r["model"] for r in dataset["reactions"] if r["model"]]
    parent = generate(network, {"network_version": network["network_version"], "models": models})
    if "ts_perturbation" in dataset:
        return derivative(network, parent, dataset["ts_perturbation"]["sign"])
    return parent
