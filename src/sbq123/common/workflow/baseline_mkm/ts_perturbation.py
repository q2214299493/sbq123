"""Reproduce a single, benchmark-scoped transition-state displacement from its reviewed parent."""

from copy import deepcopy

from scripts.artifact_io import sha256_json
from scripts.kinetic_data.local_sensitivity import central_difference as central_difference
from scripts.kinetic_parameters.engine import calculate, check_version, generate
from scripts.kinetic_parameters.export_contract import validate_export

PARENT = "417cf1dc3236175476441c4c4e7b4bd5771bc4a7062aa5e34eff69070483d11b"
REACTION = "transfer"
DELTA_EV = 0.01
HALF_STEP_EV = 0.005


def reviewed_reaction(network, dataset, reaction_id):
    entries = {r["definition"]["reaction_id"]: r for r in network["reactions"]}
    rows = {r["reaction_id"]: r for r in dataset["reactions"]}
    if len(entries) != len(network["reactions"]) or len(rows) != len(dataset["reactions"]):
        raise ValueError("Duplicate reaction ID in network or dataset")
    if reaction_id not in entries or reaction_id not in rows:
        raise ValueError(f"Unknown reaction ID: {reaction_id}")
    entry, row = entries[reaction_id], rows[reaction_id]
    definition, param = entry["definition"], row["parameter_set"]
    review = entry.get("ts_review") or {}
    if (
        review.get("grade") != "A"
        or not review.get("review_sha256")
        or not definition.get("ts_id")
        or review.get("structure_identity") != definition["ts_id"]
        or entry["network_review"]["decision"] != "accepted"
        or not row["scientifically_validated"]
        or param["validation"]["status"] != "accepted"
        or param["reaction_id"] != reaction_id
        or param["parameter_set_id"] not in entry["parameter_set_ids"]
        or param["parameter_set_id"] != row["model"]["parameter_set_id"]
        or row["direction"]["status"] != "reversible"
    ):
        raise ValueError(f"{reaction_id}: missing reviewed TS or parameter binding")
    for side in ("forward", "reverse"):
        barrier = param[side]["activation_energy"]
        if (
            barrier != definition["free_energies"]["values"][side]
            or barrier["unit"] != "eV"
            or barrier["reference_id"] != param["energy_reference_id"]
            or barrier["value"] != row["energies"]["gibbs_ev"][side]
        ):
            raise ValueError(f"{reaction_id}: incompatible {side} Gibbs barrier")
    return entry, row


def derivative(network, parent, sign, delta_eV=DELTA_EV, reaction_id=REACTION):
    if delta_eV not in (DELTA_EV, HALF_STEP_EV):
        raise ValueError("Unsupported synthetic TS benchmark step size")
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
    entry, row = reviewed_reaction(network, child, reaction_id)
    g = row["energies"]["gibbs_ev"]
    param = row["parameter_set"]
    before = g.copy()
    parameter_hash = sha256_json(param)
    for direction in ("forward", "reverse"):
        g[direction] += sign * delta_eV
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
        reaction_id=reaction_id,
        sign=sign,
        delta_eV=delta_eV,
        temperature_K=param["temperature_K"],
        parent_gibbs_eV=before,
        derived_gibbs_eV=g.copy(),
        parent_parameter_sha256=parameter_hash,
        method="Shift absolute TS Gibbs energy at fixed endpoints and prefactors; review and sources refer to parent.",
    )
    del child["dataset_version"]
    return {"dataset_version": sha256_json(child), **child}


def reproduce(network, dataset):
    models = [r["model"] for r in dataset["reactions"] if r["model"]]
    parent = generate(network, {"network_version": network["network_version"], "models": models})
    if "ts_perturbation" in dataset:
        displacement = dataset["ts_perturbation"]
        return derivative(network, parent, displacement["sign"], displacement["delta_eV"], displacement["reaction_id"])
    return parent
